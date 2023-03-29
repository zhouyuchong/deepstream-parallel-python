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
from util import *
from config import *

import ctypes
ctypes.cdll.LoadLibrary('/opt/models/yolov5/yolov5s/libplugin_yolo_3060.so')
ctypes.cdll.LoadLibrary('/opt/models/retinaface/libdecodeplugin.so')


import pyds

no_display = False
silent = False
file_loop = False
perf_data = None
perf_data_2 = None

pgie_classes_str= ["Vehicle", "TwoWheeler", "Person","RoadSign"]



def main(args, requested_pgie=None, config=None, disable_probe=False):
    global perf_data, perf_data_2
    perf_data = PERF_DATA(len(args))
    perf_data_2 = PERF_DATA(len(args))
    


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
    streammux_main = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux_main:
        sys.stderr.write(" Unable to create NvStreamMux \n")


    pipeline.add(streammux_main)


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
        sinkpad= streammux_main.get_request_pad(padname) 
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
    # pipeline.add(queue5)

    nvdslogger = None
    transform = None

    print("Creating Pgie \n ")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    pgie_2 = Gst.ElementFactory.make("nvinfer", "primary-inference-face")


    if not pgie:
        sys.stderr.write(" Unable to create pgie :  %s\n" % requested_pgie)

    if disable_probe:
        # Use nvdslogger for perf measurement instead of probe function
        print ("Creating nvdslogger \n")
        nvdslogger = Gst.ElementFactory.make("nvdslogger", "nvdslogger")

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
    nvosd.set_property('process-mode',OSD_PROCESS_MODE)
    nvosd.set_property('display-text',OSD_DISPLAY_TEXT)

    print("Creating EGLSink \n")
    # sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
    sink = Gst.ElementFactory.make("fakesink", "nvvideo-renderer")

    sink.set_property("qos",0)
    sink.set_property("async",0)
    
    if not sink:
        sys.stderr.write(" Unable to create sink element \n")

    if is_live:
        print("At least one of the sources is live")
        streammux_main.set_property('live-source', 1)

    memtype = int(pyds.NVBUF_MEM_CUDA_UNIFIED)

    streammux_main.set_property('width', 1920)
    streammux_main.set_property('height', 1080)
    streammux_main.set_property('batch-size', number_sources)
    streammux_main.set_property('batched-push-timeout', 4000000)
    streammux_main.set_property('buffer-pool-size', 4)
    streammux_main.set_property('nvbuf-memory-type', memtype)
    
    
    pgie.set_property('config-file-path', "config/config_yolov5.txt")
    pgie_2.set_property('config-file-path', "config/config_retinaface.txt")

    pgie_batch_size=pgie.get_property("batch-size")
    if(pgie_batch_size != number_sources):
        print("WARNING: Overriding infer-config batch-size",pgie_batch_size," with number of sources ", number_sources," \n")
        pgie.set_property("batch-size",number_sources)
        pgie_2.set_property("batch-size",number_sources)
    tiler_rows=int(math.sqrt(number_sources))
    tiler_columns=int(math.ceil((1.0*number_sources)/tiler_rows))
    tiler.set_property("rows",tiler_rows)
    tiler.set_property("columns",tiler_columns)
    tiler.set_property("width", TILED_OUTPUT_WIDTH)
    tiler.set_property("height", TILED_OUTPUT_HEIGHT)

    print("Adding elements to Pipeline \n")
    pipeline.add(pgie)
    pipeline.add(pgie_2)
    if nvdslogger:
        pipeline.add(nvdslogger)
    pipeline.add(tiler)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    if transform:
        pipeline.add(transform)
    pipeline.add(sink)


    print("Linking elements in the Pipeline \n")
    streammux_main.link(queue1)
    queue1.link(pgie_2)
    pgie_2.link(tiler)
    # if nvdslogger:
    #     queue2.link(nvdslogger)
    #     nvdslogger.link(tiler)
    # else:
    #     queue2.link(tiler)
    tiler.link(queue3)
    queue3.link(nvvidconv)
    nvvidconv.link(queue4)
    queue4.link(nvosd)
    nvosd.link(sink)


    # create an event loop and feed gstreamer bus mesages to it
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)

    pgie_src_pad=pgie.get_static_pad("src")
    pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe, 0)
    GLib.timeout_add(5000, perf_data.perf_print_callback)

    pgie_2_src_pad=pgie_2.get_static_pad("src")
    pgie_2_src_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_src_pad_buffer_probe_2, 0)
    GLib.timeout_add(5000, perf_data_2.perf_print_callback)

    import os
    dst_folder = os.path.abspath(os.environ.get("GST_DEBUG_DUMP_DOT_DIR", ""))
    os.makedirs(dst_folder, exist_ok=True)
    graph_filename = "pipeline"
    graph_filepath = os.path.join(dst_folder, graph_filename)
    print(f"Saving pipeline in folder {dst_folder}")
    Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, graph_filename)
    print("Files in dst folder:", os.listdir(dst_folder))
    Gst.debug_bin_to_dot_file_with_ts(pipeline, Gst.DebugGraphDetails.ALL, graph_filename)
    print("Files in dst folder:", os.listdir(dst_folder))
    os.system(f"dot -Tpng -o {graph_filepath}.png {graph_filepath}.dot")


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



def pgie_src_pad_buffer_probe(pad,info,u_data):
    """
    Probe to extract facial info from metadata and add them to Face pool. 
    
    Should be after retinaface.
    """
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        stream_index = "stream{0}".format(frame_meta.pad_index)
        global perf_data
        perf_data.update_fps(stream_index)
        try:
            l_frame=l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK

def pgie_src_pad_buffer_probe_2(pad,info,u_data):
    """
    Probe to extract facial info from metadata and add them to Face pool. 
    
    Should be after retinaface.
    """
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        stream_index = "stream{0}".format(frame_meta.pad_index)
        global perf_data_2
        perf_data_2.update_fps(stream_index)
        try:
            l_frame=l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK

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

