import os
import sys

sys.path.append('../../')
import config
from common.link_func import *
from common.FPS_NEW import *
from .probe import *
from ..ParaInferBin import *

import ctypes
ctypes.cdll.LoadLibrary(YOLO_PLUGIN_LIB)


class PVBehavior(InferBin):
    def __init__(self, pipeline, srcm, perf) -> None:
        self.app_name = 'PVBehavior'
        self.config_path = os.path.join(config.__path__[0], 'config_app_pvbehavior.txt')
        self.pgie_config_path = os.path.join(config.__path__[0], 'config_trt_yolov7.txt')
        self.msgbroker_path = os.path.join(config.__path__[0], 'config_gst_kafka.txt')
        self.msgconv_path = os.path.join(config.__path__[0], 'config_gst_msgconv.txt')

        self.pipeline = pipeline
        self.srcm =srcm
        
        self.main_bin = "nvstreammux-streammux|nvinfer-pgie|nvtracker-tracker|nvvideoconvert-videoconvert|capsfilter|tee"
        # self.main_bin = "nvstreammux-streammux|nvinfer-pgie|nvtracker-tracker|nvvideoconvert-videoconvert|capsfilter|nvdsosd-osd|nvmultistreamtiler-tiler|tee"
        ## sink_bin 暂时是写死的
        self.sink_bin = "nvmsgconv-msgconv|nvmsgbroker-msgbroker|fakevideosink-sink"
        # self.sink_bin = "nvmsgconv-msgconv|nvmsgbroker-msgbroker|nveglglessink-sink"
        
        self.main_bin_elements = []
        self.sink_elements = []
        self.activated_pads_streammux = []

        # perf[self.app_name]= PERF_DATA_SINGLE(num_streams=16, app_name=self.app_name)
        # self.perf_data = perf[self.app_name]
        self.make_elements()
        self.link_elements()
        # self.set_streammux_null()
        # self.add_probes()


        


    def make_elements(self):
        '''
        Make Gstreamer plugins and set properties.

        some plugin path can't be auto read from config files.
        '''
        for element in self.main_bin.split("|"):
            if '-' in element:
                detail = element.split("-")
                ret, gst_element = create_element(self.app_name, detail[0], detail[1])
                ## Temporary we should specify the config path of gies, msgconv and msgbroker by addition path
                if detail[1] == 'pgie':
                    gie_path = self.pgie_config_path
                elif detail[1] == 'sgie':
                    gie_path = self.sgie_config_path
                else:
                    gie_path = None

                if ret:
                    set_element_property(config_path=self.config_path, element=gst_element, element_name=detail[1], addition_path=gie_path)
            else:
                ret, gst_element = create_element(self.app_name, element)

            self.pipeline.add(gst_element)
            self.main_bin_elements.append(gst_element)

        for element in self.sink_bin.split("|"):
            if '-' in element:
                detail = element.split("-")
                ret, gst_element = create_element(self.app_name, detail[0], detail[1])
                if detail[1] == 'msgbroker':
                    add_path = self.msgbroker_path
                elif detail[1] == 'msgconv':
                    add_path = self.msgconv_path
                if ret:
                    set_element_property(config_path=self.config_path, element=gst_element, element_name=detail[1], addition_path=add_path)
            else:
                ret, gst_element = create_element(self.app_name, element)

            self.pipeline.add(gst_element)
            self.sink_elements.append(gst_element)

    def link_elements(self):
        '''
        Link all elements
        
        Temporary only support static sink pad: tee-->msgconv-->msgbroker
                                                   -->sink
        '''
        for i in range(len(self.main_bin_elements)-1):
            ret, queue = create_element(self.app_name, "queue", str(i))  
            self.pipeline.add(queue)            
            self.main_bin_elements[i].link(queue)
            queue.link(self.main_bin_elements[i+1])  

        if self.main_bin.split("|")[-1] == 'tee':
            ret, queue_tee_1 = create_element(self.app_name, "queue", 'tee-1')  
            ret, queue_tee_2 = create_element(self.app_name, "queue", 'tee-2')  
            self.pipeline.add(queue_tee_1) 
            self.pipeline.add(queue_tee_2)  

            msg_sink_pad = queue_tee_1.get_static_pad("sink")
            sink_pad = queue_tee_2.get_static_pad("sink")

            tee_msg_pad = self.main_bin_elements[len(self.main_bin_elements)-1].get_request_pad('src_%u')
            tee_sink_pad = self.main_bin_elements[len(self.main_bin_elements)-1].get_request_pad("src_%u")

            tee_msg_pad.link(msg_sink_pad)
            tee_sink_pad.link(sink_pad)

            queue_tee_1.link(self.sink_elements[0])
            self.sink_elements[0].link(self.sink_elements[1])
            queue_tee_2.link(self.sink_elements[2])

    def set_streammux_null(self):
        self.main_bin_elements[0].set_state(Gst.State.NULL)


    # def add_probes(self):
    #     user_data = [self.face_pool, self.t_pool, self.srcm, self.perf_data]
    #     self.pgie_src_pad=self.main_bin_elements[4].get_static_pad("src")
    #     if not self.pgie_src_pad:
    #         sys.stderr.write(" Unable to get src pad \n")
    #     else:
    #         self.pgie_src_pad.add_probe(Gst.PadProbeType.BUFFER, pgie_sink_pad_buffer_probe, user_data)
    #         GLib.timeout_add(5000, self.perf_data.perf_print_callback)

    #     self.sgie_sink_pad = self.main_bin_elements[5].get_static_pad("src")
    #     if not self.sgie_sink_pad:
    #         return False, "fail"
    #     else:
    #         self.sgie_sink_pad.add_probe(Gst.PadProbeType.BUFFER, sgie_sink_pad_buffer_probe, user_data)


    #     self.msg_sink_pad = self.main_bin_elements[6].get_static_pad("sink")
    #     if not self.msg_sink_pad:
    #         return False, "fail"
    #     else:
    #         self.msg_sink_pad.add_probe(Gst.PadProbeType.BUFFER, msg_sink_pad_buffer_probe, user_data)


        

    def add_new_source(self, padname, srcpad):
        if padname not in self.activated_pads_streammux:
            self.activated_pads_streammux.append(padname)
            streammux_sink_pad = self.main_bin_elements[0].get_request_pad(padname)
            srcpad.link(streammux_sink_pad)
        else:
            streammux_sink_pad = self.main_bin_elements[0].get_static_pad(padname)
            streammux_sink_pad.send_event(Gst.Event.new_flush_start())
    
    def release_streammux(self, pad_name):
        sinkpad = self.main_bin_elements[0].get_static_pad(pad_name)
        if sinkpad is not None:
            sinkpad.send_event(Gst.Event.new_flush_stop(False))
            # self.main_bin_elements[0].release_request_pad(sinkpad)
        logger.info("Branch {} streammux release finished.".format(self.app_name))
        # return sinkpad
    


        
