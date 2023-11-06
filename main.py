#!/usr/bin/env python3

################################################################################
# SPDX-FileCopyrightText: Copyright (c) 2019-2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
################################################################################

import sys
sys.path.append('../')
from pathlib import Path
import gi
import configparser
import argparse
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
from ctypes import *
import time
import sys
import math
import platform
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call
from common.FPS import PERF_DATA

import pyds

import ctypes
ctypes.cdll.LoadLibrary('/opt/nvidia/deepstream/deepstream-6.3/sources/models/deploy/retinaface/libdecodeplugin.so')
ctypes.cdll.LoadLibrary('/opt/nvidia/deepstream/deepstream-6.3/sources/models/deploy/yolov7/libmyplugins.so')

no_display = False
silent = False
file_loop = False
perf_data = None

MAX_DISPLAY_LEN=64
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_OUTPUT_WIDTH=1920
MUXER_OUTPUT_HEIGHT=1080
MUXER_BATCH_TIMEOUT_USEC=4000000
TILED_OUTPUT_WIDTH=1280
TILED_OUTPUT_HEIGHT=720
GST_CAPS_FEATURES_NVMM="memory:NVMM"
OSD_PROCESS_MODE= 0
OSD_DISPLAY_TEXT= 1
pgie_classes_str= ["Vehicle", "TwoWheeler", "Person","RoadSign"]

# pgie_src_pad_buffer_probe  will extract metadata received on tiler sink pad
# and update params for drawing rectangle, object information etc.
def pgie_src_pad_buffer_probe(pad,info,u_data):
    frame_number=0
    num_rects=0
    got_fps = False
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return
    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.NvDsFrameMeta.cast()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        frame_number=frame_meta.frame_num
        l_obj=frame_meta.obj_meta_list
        num_rects = frame_meta.num_obj_meta
        obj_counter = {
        PGIE_CLASS_ID_VEHICLE:0,
        PGIE_CLASS_ID_PERSON:0,
        PGIE_CLASS_ID_BICYCLE:0,
        PGIE_CLASS_ID_ROADSIGN:0
        }
        while l_obj is not None:
            try: 
                # Casting l_obj.data to pyds.NvDsObjectMeta
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            obj_counter[obj_meta.class_id] += 1
            try: 
                l_obj=l_obj.next
            except StopIteration:
                break
        if not silent:
            print("Frame Number=", frame_number, "Number of Objects=",num_rects,"Vehicle_count=",obj_counter[PGIE_CLASS_ID_VEHICLE],"Person_count=",obj_counter[PGIE_CLASS_ID_PERSON])

        # Update frame rate through this probe
        stream_index = "stream{0}".format(frame_meta.pad_index)
        global perf_data
        perf_data.update_fps(stream_index)

        try:
            l_frame=l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK



def cb_newpad(decodebin, decoder_src_pad,data):
    print("In cb_newpad\n")
    caps=decoder_src_pad.get_current_caps()
    if not caps:
        caps = decoder_src_pad.query_caps()
    gststruct=caps.get_structure(0)
    gstname=gststruct.get_name()
    source_bin=data
    features=caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    print("gstname=",gstname)
    if(gstname.find("video")!=-1):
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        print("features=",features)
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad=source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
        else:
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")

def decodebin_child_added(child_proxy,Object,name,user_data):
    print("Decodebin child added:", name, "\n")
    if(name.find("decodebin") != -1):
        Object.connect("child-added",decodebin_child_added,user_data)

    if "source" in name:
        source_element = child_proxy.get_by_name("source")
        if source_element.find_property('drop-on-latency') != None:
            Object.set_property("drop-on-latency", True)



def create_source_bin(index,uri):
    print("Creating source bin")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name="source-bin-%02d" %index
    print(bin_name)
    nbin=Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
    if file_loop:
        # use nvurisrcbin to enable file-loop
        uri_decode_bin=Gst.ElementFactory.make("nvurisrcbin", "uri-decode-bin")
        uri_decode_bin.set_property("file-loop", 1)
        uri_decode_bin.set_property("cudadec-memtype", 0)
    else:
        uri_decode_bin=Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri",uri)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added",cb_newpad,nbin)
    uri_decode_bin.connect("child-added",decodebin_child_added,nbin)

    # We need to create a ghost pad for the source bin which will act as a proxy
    # for the video decoder src pad. The ghost pad will not have a target right
    # now. Once the decode bin creates the video decoder and generates the
    # cb_newpad callback, we will set the ghost pad target to the video decoder
    # src pad.
    Gst.Bin.add(nbin,uri_decode_bin)
    bin_pad=nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin

def main(args, requested_pgie=None, config=None, disable_probe=False):
    global perf_data
    perf_data = PERF_DATA(len(args))

    number_sources=len(args)

    # Standard GStreamer initialization
    Gst.init(None)

    # Create gstreamer elements */
    # Create Pipeline element that will form a connection of other elements
    print("Creating Pipeline \n ")
    pipeline = Gst.Pipeline()
    is_live = False

    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline \n")

    print("Creating streamux \n ")
    # Create nvstreammux instance to form batches from one or more sources.
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux \n")

    print("Creating nvstreamdemux \n ")
    nvstreamdemux = Gst.ElementFactory.make("nvstreamdemux", "nvstreamdemux")
    if not nvstreamdemux:
        sys.stderr.write(" Unable to create nvstreamdemux \n")

    print("Creating nvdsmetamux \n ")
    metamux = Gst.ElementFactory.make("nvdsmetamux", "Meta-muxer")
    if not metamux:
        sys.stderr.write(" Unable to create NvDsMetaMux  \n")
    

    print("Creating tee \n ")
    tee_streammux = Gst.ElementFactory.make("tee", "Stream-muxer-tee")
    if not tee_streammux:
        sys.stderr.write(" Unable to create tee after streammux-main \n")

    print("Creating streamux-1 \n ")
    # Create nvstreammux instance to form batches from one or more sources.
    streammux_b1 = Gst.ElementFactory.make("nvstreammux", "Stream-muxer-branch-1")
    if not streammux_b1:
        sys.stderr.write(" Unable to create NvStreamMux-b1 \n")

    print("Creating streamux-2 \n ")
    # Create nvstreammux instance to form batches from one or more sources.
    streammux_b2 = Gst.ElementFactory.make("nvstreammux", "Stream-muxer-branch-2")
    if not streammux_b2:
        sys.stderr.write(" Unable to create NvStreamMux-b2 \n")

    print("Creating Pgie 1 \n ")
    pgie_branch_1 = Gst.ElementFactory.make("nvinfer", "primary-inference-1")
    if not pgie_branch_1:
        sys.stderr.write(" Unable to create pgie for branch 1 \n")

    print("Creating Pgie 2 \n ")
    pgie_branch_2 = Gst.ElementFactory.make("nvinfer", "primary-inference-2")
    if not pgie_branch_2:
        sys.stderr.write(" Unable to create pgie for branch 2 \n")

    print("Creating tiler \n ")
    tiler=Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
    if not tiler:
        sys.stderr.write(" Unable to create tiler \n")

    print("Creating nvvidconv \n ")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    if not nvvidconv:
        sys.stderr.write(" Unable to create nvvidconv \n")

    print("Creating nvosd \n ")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    if not nvosd:
        sys.stderr.write(" Unable to create nvosd \n")

    if is_aarch64():
        print("Creating nv3dsink \n")
        sink = Gst.ElementFactory.make("nv3dsink", "nv3d-sink")
        if not sink:
            sys.stderr.write(" Unable to create nv3dsink \n")
    else:
        print("Creating EGLSink \n")
        sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
        if not sink:
            sys.stderr.write(" Unable to create egl sink \n")

    if not sink:
        sys.stderr.write(" Unable to create sink element \n")



    pipeline.add(streammux)
    pipeline.add(streammux_b1)
    pipeline.add(streammux_b2)

    pipeline.add(metamux)
    pipeline.add(nvstreamdemux)

    for i in range(number_sources):
        print("Creating source_bin ",i," \n ")
        uri_name=args[i]
        if uri_name.find("rtsp://") == 0 :
            is_live = True
        source_bin=create_source_bin(i, uri_name)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
        pipeline.add(source_bin)
        padname="sink_%u" %i
        sinkpad= streammux.get_request_pad(padname) 
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
        srcpad=source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
        srcpad.link(sinkpad)
        
    queue1=Gst.ElementFactory.make("queue","queue1")
    queue2=Gst.ElementFactory.make("queue","queue2")
    queue3=Gst.ElementFactory.make("queue","queue3")
    queue4=Gst.ElementFactory.make("queue","queue4")
    queue5=Gst.ElementFactory.make("queue","queue5")

    pipeline.add(queue1)
    pipeline.add(queue2)
    pipeline.add(queue3)
    pipeline.add(queue4)
    pipeline.add(queue5)

    print("Set properties for elements...\n")

    metamux.set_property("config-file", 'config_metamux0.txt')
    pgie_branch_1.set_property('config-file-path', "config_trt_yolov7.txt")
    pgie_branch_2.set_property('config-file-path', "config_trt_retinaface.txt")
    nvosd.set_property('process-mode',OSD_PROCESS_MODE)
    nvosd.set_property('display-text',OSD_DISPLAY_TEXT)

    if file_loop:
        if is_aarch64():
            # Set nvbuf-memory-type=4 for aarch64 for file-loop (nvurisrcbin case)
            streammux.set_property('nvbuf-memory-type', 4)
        else:
            # Set nvbuf-memory-type=2 for x86 for file-loop (nvurisrcbin case)
            streammux.set_property('nvbuf-memory-type', 2)

    if is_live:
        print("At least one of the sources is live")
        streammux.set_property('live-source', 1)

    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', number_sources)
    streammux.set_property('batched-push-timeout', 4000000)

    streammux_b1.set_property('width', 1920)
    streammux_b1.set_property('height', 1080)
    streammux_b1.set_property('batch-size', number_sources)
    streammux_b1.set_property('batched-push-timeout', 4000000)

    streammux_b2.set_property('width', 1920)
    streammux_b2.set_property('height', 1080)
    streammux_b2.set_property('batch-size', number_sources)
    streammux_b2.set_property('batched-push-timeout', 4000000)

    tiler_rows=int(math.sqrt(number_sources))
    tiler_columns=int(math.ceil((1.0*number_sources)/tiler_rows))
    tiler.set_property("rows",tiler_rows)
    tiler.set_property("columns",tiler_columns)
    tiler.set_property("width", TILED_OUTPUT_WIDTH)
    tiler.set_property("height", TILED_OUTPUT_HEIGHT)
    sink.set_property("qos",0)
    sink.set_property("async",0)

    print("Adding elements to Pipeline \n")
    pipeline.add(pgie_branch_1)
    pipeline.add(pgie_branch_2)

    pipeline.add(tiler)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(sink)

    pipeline.add(tee_streammux)

    sink_pad = queue1.get_static_pad("sink")
    tee_demux_pad = tee_streammux.get_request_pad('src_%u')
    tee_mux_pad = tee_streammux.get_request_pad("src_%u")

    tee_mux_pad.link(sink_pad)
    sink_pad = queue2.get_static_pad("sink")
    tee_demux_pad.link(sink_pad)

    print("Linking elements in the Pipeline \n")
    streammux.link(tee_streammux)
    queue2.link(nvstreamdemux)

    queue_branch_1 = [None]*number_sources
    queue_branch_2 = [None]*number_sources

    for i in range(1):
        queue_branch_1[i]=Gst.ElementFactory.make("queue","queue_b1_%u"%i)
        pipeline.add(queue_branch_1[i])
        # connect nvstreamdemux -> queue
        padname = "src_%u" % i
        demuxsrcpad = nvstreamdemux.get_request_pad(padname)
        if not demuxsrcpad:
            sys.stderr.write("Unable to create demux src pad \n")

        queuesinkpad = queue_branch_1[i].get_static_pad("sink")
        if not queuesinkpad:
            sys.stderr.write("Unable to create queue sink pad \n")
        demuxsrcpad.link(queuesinkpad)

        queue_srcpad = queue_branch_1[i].get_static_pad("src")
        if not queue_srcpad:
            print("here.")
        padname = "sink_%u" % i
        sinkpad = streammux_b1.get_request_pad(padname)
        if not sinkpad:
            print("there")
        queue_srcpad.link(sinkpad)

    streammux_b1.link(pgie_branch_1)

    for i in range(1,2):
        queue_branch_2[i]=Gst.ElementFactory.make("queue","queue_b2_%u"%i)
        pipeline.add(queue_branch_2[i])
        # connect nvstreamdemux -> queue
        padname = "src_%u" % i
        demuxsrcpad = nvstreamdemux.get_request_pad(padname)
        if not demuxsrcpad:
            sys.stderr.write("Unable to create demux src pad \n")

        queuesinkpad = queue_branch_2[i].get_static_pad("sink")
        if not queuesinkpad:
            sys.stderr.write("Unable to create queue sink pad \n")
        demuxsrcpad.link(queuesinkpad)

        queue_srcpad = queue_branch_2[i].get_static_pad("src")
        padname = "sink_%u" % i
        sinkpad = streammux_b2.get_request_pad(padname)
        queue_srcpad.link(sinkpad)

    streammux_b2.link(pgie_branch_2)
    metamux_sink_pad_0 = metamux.get_request_pad('sink_0')
    metamux_sink_pad_1 = metamux.get_request_pad('sink_1')
    metamux_sink_pad_2 = metamux.get_request_pad('sink_2')

    pgie_1_src_pad = pgie_branch_1.get_static_pad('src')
    pgie_2_src_pad = pgie_branch_2.get_static_pad('src')
    queue1_src_pad = queue1.get_static_pad('src')
    
    pgie_1_src_pad.link(metamux_sink_pad_1)
    pgie_2_src_pad.link(metamux_sink_pad_2)
    queue1_src_pad.link(metamux_sink_pad_0)

    metamux.link(tiler)

    # queue2.link(tiler)
    tiler.link(queue3)
    queue3.link(nvvidconv)
    nvvidconv.link(queue4)
    queue4.link(nvosd)
    nvosd.link(queue5)
    queue5.link(sink)   

    # create an event loop and feed gstreamer bus mesages to it
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)
    # pgie_src_pad=pgie.get_static_pad("src")
    # if not pgie_src_pad:
    #     sys.stderr.write(" Unable to get src pad \n")
    # else:
    #     if not disable_probe:
    #         pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe, 0)
    #         # perf callback function to print fps every 5 sec
    #         GLib.timeout_add(5000, perf_data.perf_print_callback)

    # List the sources
    print("Now playing...")
    for i, source in enumerate(args):
        print(i, ": ", source)

    print("Starting pipeline \n")
    # start play back and listed to events		
    pipeline.set_state(Gst.State.PLAYING)
    try:
        loop.run()
    except:
        pass
    # cleanup
    print("Exiting app\n")
    pipeline.set_state(Gst.State.NULL)

def parse_args():

    parser = argparse.ArgumentParser(prog="deepstream_test_3",
                    description="deepstream-test3 multi stream, multi model inference reference app")
    parser.add_argument(
        "-i",
        "--input",
        help="Path to input streams",
        nargs="+",
        metavar="URIs",
        default=["a"],
        required=True,
    )
    parser.add_argument(
        "-c",
        "--configfile",
        metavar="config_location.txt",
        default=None,
        help="Choose the config-file to be used with specified pgie",
    )
    parser.add_argument(
        "-g",
        "--pgie",
        default=None,
        help="Choose Primary GPU Inference Engine",
        choices=["nvinfer", "nvinferserver", "nvinferserver-grpc"],
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        default=False,
        dest='no_display',
        help="Disable display of video output",
    )
    parser.add_argument(
        "--file-loop",
        action="store_true",
        default=False,
        dest='file_loop',
        help="Loop the input file sources after EOS",
    )
    parser.add_argument(
        "--disable-probe",
        action="store_true",
        default=False,
        dest='disable_probe',
        help="Disable the probe function and use nvdslogger for FPS",
    )
    parser.add_argument(
        "-s",
        "--silent",
        action="store_true",
        default=False,
        dest='silent',
        help="Disable verbose output",
    )
    # Check input arguments
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args = parser.parse_args()

    stream_paths = args.input
    pgie = args.pgie
    config = args.configfile
    disable_probe = args.disable_probe
    global no_display
    global silent
    global file_loop
    no_display = args.no_display
    silent = args.silent
    file_loop = args.file_loop

    if config and not pgie or pgie and not config:
        sys.stderr.write ("\nEither pgie or configfile is missing. Please specify both! Exiting...\n\n\n\n")
        parser.print_help()
        sys.exit(1)
    if config:
        config_path = Path(config)
        if not config_path.is_file():
            sys.stderr.write ("Specified config-file: %s doesn't exist. Exiting...\n\n" % config)
            sys.exit(1)

    print(vars(args))
    return stream_paths, pgie, config, disable_probe

if __name__ == '__main__':
    stream_paths, pgie, config, disable_probe = parse_args()
    sys.exit(main(stream_paths, pgie, config, disable_probe))

