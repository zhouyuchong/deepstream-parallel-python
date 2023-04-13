import abc
import functools
from threading import RLock, Thread, Lock
import json
from kafka import KafkaProducer, KafkaConsumer
import re
import time
from loguru import logger

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

from .srcm import SRCM
import sys
sys.path.append('../')
import config
from common.parse import *
from app import *


__all__ = ['DSPipeline']




Gst.init(None)

Gst.debug_set_active(True)
Gst.debug_set_default_threshold(1)

class DSPD:
    """
    deepstream pipeline decorator
    """
    lock = RLock()

    @staticmethod
    def d_acquire_lock(func):
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with DSPD.lock:
                res = func(*args, **kwargs)
            return res
        
        return wrapper


class DSPipeline(abc.ABC):
    def __init__(self) -> None:
        """
        deepstream pipeline
        :param gpu_id: int, stream-mux gup_id
        :param batch_size: int, stream-mux batch_size
        :param batch_push_timeout: int, stream-mux batch_push_timeout
        :param max_source_num: int, pipeline supported max source num
        """
        super().__init__()
        # self.srcm = SRCM(max_src_num=max_source_num)
        self.is_first_src = True

        self.branch_manager = dict()

        self.loop = GLib.MainLoop()
        self.pipeline_config = os.path.join(config.__path__[0], 'config_gst_pipeline.txt')

        self.tee = dict()
        self.srcm = None
        self.producer = None
        self.perf = dict()

        self.activated_pads_streammux = []
        self.demux_pad_list = dict()


        # if self._init:
        #     return True, "system already init"

        # self.build_pipeline()

        
        

    def update_src_abs(self, src, data):
        """
        if ur pipeline support update source config, re-implement this function, default not

        :raise NotImplementedError
        :param src:
        :param data:
        :return:
        """
        # TODO log here
        print("source %s(id) update infrmation:\n" % src.id, data)
        raise NotImplementedError("current app does not support update source information")

    def bus_call_abs(self, bus, message):
        t = message.type
        # TODO log here
        if t == Gst.MessageType.EOS:
            logger.error("收到流播放结束信号. end of stream")

        elif t==Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            print("Warning: %s: %s\n" % (err, debug))
        elif t == Gst.MessageType.ERROR:
            
            err, debug = message.parse_error()
            logger.error("播放时发生错误. error: {}: {}".format(err, debug))
            struct = str(message.get_structure())
            search_index = re.search("source-bin-[0-9]{0,1}/", struct)
            search_index = int(search_index[0].split('-')[2][:-1])

            try:
                err_id = self.srcm.get_id_by_idx(search_index)
                # err_url = self.srcm.get_url_by_idx(search_index)
                logger.warning("id: {} | encounters error: {}.".format(err_id, err))
            except Exception as e:
                logger.warning("source: {} didn't exist: {}".format(search_index, e))
                return
            
            # logger.warning("id: {} | {} reach max reconnect retry. sending message...".format(err_id, err_url))
            time_local = time.localtime(int(time.time()))
            dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
            msg = {"time": dt, "type": "normal", "id": str(err_id), "error":str(err), "debug": debug}
            msg = json.dumps(msg).encode('utf-8')

            if str(err).startswith("gst-resource-error-quark") or str(err).startswith("gst-stream-error-quark"):
                # resource errors from 1 to 16
                if str(err).endswith("(9)"):
                    # handle_read_error()
                    logger.warning("source: {} | error: {}".format(search_index, err))
                else:
                    self.producer.send('error', msg)
                    logger.warning("id: {} will be deleted.".format(err_id))
                    try:
                        self.del_src(id=err_id)
                    except Exception:
                        logger.error("消息总线中: ERROR, 删除资源时发生错误. id: {} | encounters error: {} while delete.".format(err_id, err))

        elif t == Gst.MessageType.ELEMENT:
            struct = message.get_structure()
            # Check for stream-eos message
            if struct is not None and struct.has_name("stream-eos"):
                parsed, stream_id = struct.get_uint("stream-id")
                if parsed:
                    # Set eos status of stream to True, to be deleted in delete-sources
                    logger.info("Got EOS from stream-{}".format(stream_id))
                    eos_id = self.srcm.get_id_by_idx(stream_id)
                    if eos_id:
                        time_local = time.localtime(int(time.time()))
                        dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
                        msg = {"time": dt, "type": "normal", "id": str(eos_id), "error":"EOS", "debug": ""}
                        msg = json.dumps(msg).encode('utf-8')
                        self.producer.send('error', msg)
                        try:
                            self.del_src(id=eos_id)
                        except Exception:
                            logger.error("消息总线中: EOS, 删除资源时发生错误. id: {} encounters e while delete.".format(eos_id))
        return True 

    @DSPD.d_acquire_lock
    def init(self):
        self.pipeline = Gst.Pipeline()
        
        if not self.pipeline:
            logger.error("创建pipeline时失败.")
            return False, "unable to create pipeline"
        
        # parse pipeline config file
        ret, self.app_list, kafka_conn_str = parse_config_pipeline(self.pipeline_config)
        if not ret:
            return ret, "Fail to parse config_pipeline."
        
        self.producer = KafkaProducer(bootstrap_servers=kafka_conn_str, api_version=(2,10))
        
        self.streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
        if not self.streammux:
            logger.error("创建nvstreammux-main时失败.")
            return False, "unable to create nvstreammux"

        # set properties of streammux
        self.max_source_num, self.gpu_id = set_property_pipeline(self.pipeline_config, self.streammux)
        # init source manager
        self.srcm = SRCM(max_src_num=self.max_source_num, app_list=self.app_list)
        # init branches of different apps
        

        self.nvstreamdemux = Gst.ElementFactory.make("nvstreamdemux", "nvstreamdemuxer")

        self.pipeline.add(self.streammux)
        self.pipeline.add(self.nvstreamdemux)
        self.streammux.link(self.nvstreamdemux)

        for i in range(self.max_source_num):
            padname = "src_%u" % i
            # logger.info("Get {} of nvstreamdemux.".format(padname))
            demuxsrcpad = self.nvstreamdemux.get_request_pad(padname)
            if not demuxsrcpad:
                sys.stderr.write("Unable to create demux src pad \n")
            self.demux_pad_list[i] = demuxsrcpad
  
        # add and link a gst-tee to every src pad of nvstreamdemux
        # for i in range(self.max_source_num):
        #     tmp_tee = Gst.ElementFactory.make("tee", "demuxer-tee-{}".format(i))
        #     self.pipeline.add(tmp_tee)
        #     # add gst-tees to tee-list so we can control and reach them later
        #     self.tee.append(tmp_tee)

        #     padname = "src_%u" % i
        #     demuxsrcpad = self.nvstreamdemux.get_request_pad(padname)
        #     if not demuxsrcpad:
        #         sys.stderr.write("Unable to create demux src pad \n")

        #     sinkpad = tmp_tee.get_static_pad("sink")
        #     demuxsrcpad.link(sinkpad)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.bus_call_abs, )
        self._init = True

        return True, ""


    @DSPD.d_acquire_lock
    def start(self):
        """
        start the pipeline
        :return: (bool, str), result & message
        """
        ret, msg = self.init()
        if not ret:
            return ret, "pipeline init failed, %s" % msg

        _, s, ps = self.pipeline.get_state(0.0)
        if s == Gst.State.PLAYING or ps == Gst.State.PLAYING:
            return True, "pipeline is running, state %s, pending state %s" % (s, ps)

        # run message loop
        self.thread = Thread(target=self._msg_thread_func)
        self.thread.start()
        
        ret = self.pipeline.set_state(Gst.State.NULL)        
        # self.listener = HeartbeatListener(pipeline=self.pipeline, timethreshold=15, errorproducer=self.producer, 
        #                 app_name=self.app_name, srcm=self.srcm)
        # self.listener.start()

        # if self._init_signal:
        #     self._init_signal = False
        #     time_local = time.localtime(int(time.time()))
        #     dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
        #     msg = {"time": dt, "type": "update",  "id": self.app_name, "error":"get/recover src manager when init", "debug": ""}
        #     msg = json.dumps(msg).encode('utf-8')
        #     logger.info("Try to get/recover information of source manager at INIT stage.")
        #     self.producer.send('error', msg)

        if ret == Gst.StateChangeReturn.SUCCESS:
            return True, "success, state %s" % ret
        elif ret == Gst.StateChangeReturn.FAILURE:
            logger.error("改变pipeline状态为NULL时失败. Fail to change pipeline state to NULL")
            return False, "start pipeline failed"
        elif ret == Gst.StateChangeReturn.ASYNC:
            return True, "success, state %s" % ret

    @DSPD.d_acquire_lock
    def stop(self):
        """
        stop the pipeline
        :return: (bool, str), result & message
        """
        # ret, _, src_ls = self.srcm.get()
        # if not ret:
        #     return False, "get src info failed"
        # for src in src_ls:
        #     src.rt_ctx['bin'].set_state(Gst.State.NULL)
        #     src.rt_ctx['enable'] = False
        print("stop pipeline .")
        self.pipeline.set_state(Gst.State.NULL)
        print("stop hb listener...")
        self.listener.stop()
        # print("closing error kafka producer ..")
        # self.producer.close()
        print("exit gloop ...")
        if self.thread is not None and self.thread.is_alive():
            self.loop.quit()
            self.thread = None

        return True, "success"

    @DSPD.d_acquire_lock
    def reboot(self):
        self.stop()
        time.sleep(2)
        self.start()

    @DSPD.d_acquire_lock
    def get_src(self, id=None):
        """
        get source list or
        get source with index
        :param id: str, source id
        :return: (bool, str, Source or List), result & message & source or list-of-source
        """
        return self.srcm.get(id=id)

    @DSPD.d_acquire_lock
    def add_src(self, src):
        """
        :param src: Source
        :return: (bool, str)
        """
        logger.debug("Add source api called.")

        # make not exceed max source num
        if self.srcm.total >= self.max_source_num:
            logger.error("资源超过最大限制.")
            return False, "exceed max source num %d" % self.max_source_num

        if self.srcm.exist(src.id):
            logger.error("任务已经存在.")
            return False, "source id %s exist" % src.id
        
        # make sure the pipeline is start
        _, s, _ = self.pipeline.get_state(0.0)
        if s == Gst.State.NULL and self.is_first_src is not True:
            return False, "pipeline is stoped"
        
        self.srcm.alloc_index(src)

        # create source bin
        source_bin, msg = self._create_uridecode_bin(src.idx, src.uri)
        if not source_bin:
            return False, msg
        
        self.pipeline.add(source_bin)

        # 添加一个tee在对应的demux后面，然后可以用tee来连接多个推理分支
        tmp_tee = Gst.ElementFactory.make("tee", "demuxer-tee-{}".format(src.idx))
        self.pipeline.add(tmp_tee)
        # add gst-tees to tee-list so we can control and reach them later
        self.tee[src.idx] = tmp_tee

        padname = "src_%u" % src.idx
        logger.info("Get {} of nvstreamdemux.".format(padname))
        tmp_src_pad = self.demux_pad_list[src.idx]
        sinkpad = tmp_tee.get_static_pad("sink")
        tmp_src_pad.link(sinkpad)
        
        # 接下来用tee来连接多个分支
        infer_ids = src.get_infer_ids()
        logger.debug("{} infer ids = {}.".format(src.id, infer_ids))

        

        for i in infer_ids:
            if i not in self.app_list:
                logger.error("Unsupport App Type")
                return False, "wrong app type"
            
        for app_index in infer_ids:
            if app_index not in self.branch_manager.keys():
                if app_index == 0:
                    branch = Face(self.pipeline, self.srcm, self.perf)
                    self.branch_manager[0] = branch
                    logger.success("APP face-recognition ACTIVATED")
                if app_index == 1:
                    branch = PVBehavior(self.pipeline, self.srcm, self.perf)
                    self.branch_manager[1] = branch
                    logger.success("APP pv-behavior ACTIVATED")

        for i in infer_ids:
            tee_src_pad = self.tee[src.idx].get_request_pad('src_%u')
            padname="sink_%u" % src.idx
            logger.debug("Sinkpad padname: {}".format(padname))
            ret = self.branch_manager[i].add_new_source(padname, tee_src_pad)
            # tee_src_pad.link(sinkpad)

        print(self.pipeline)
        


        # add runtime infotmation
        src.rt_ctx = {'enable': True,
            'bin': source_bin,
            'bin_name': self._uridecode_bin_name(src.idx)}

        # playing source
        state_return = source_bin.set_state(Gst.State.PLAYING)
        # print("add set return :", state_return)
        if state_return == Gst.StateChangeReturn.SUCCESS:
            print("source state change  success")
        elif state_return == Gst.StateChangeReturn.FAILURE:
            print("error, source state change failure")

        # add src to source manager
        ret, msg = self.srcm.add(src)
        if not ret:
            raise Exception("add source to srm failed")
        
        
        
        if self.is_first_src:
            self.is_first_src = False
            logger.info("First source in pipeline, START whole pipeline")
            
            state_return  = self.pipeline.set_state(Gst.State.PLAYING)



        # if src.ptz_params:
        #     if src.get_cam_type():
        #         self.set_analytics(src.id, 2, src.get_multi_roi())
        #     else:
        #         if 'forward' in src.ptz_params[0]['coordinate']:
        #             logger.info("Set nvanalytics plugin, type: Line-Crossing")
        #             self.set_analytics(src.id, 1, src.ptz_params[0]['coordinate'])
        #         elif 'recog' in src.ptz_params[0]['coordinate']:
        #             logger.info("Set nvanalytics plugin, type: ROI")
        #             self.set_analytics(src.id, 2, src.ptz_params[0]['coordinate'])

        
                    
        return True, "success"

    @DSPD.d_acquire_lock
    def del_src(self, id):
        """
        :param id: str, source id
        :return: (bool, str, Source), result & message & deleted source
        """
        ret, msg, src = self.srcm.get(id)
        if not ret:
            logger.warning("source: {} not exist.")
            return ret, msg, None
        
        logger.info("will delete src:{} | {}".format(src.idx, src.uri))
        infer_ids = src.get_infer_ids()
       
        # 如果管道中已经没有其他正在播放的资源，设置管道为空
        if self.srcm.total == 1:
            self.streammux.set_state(Gst.State.NULL)
            state_return = self.pipeline.set_state(Gst.State.NULL)
            self.is_first_src = True

        source_bin = src.rt_ctx['bin']
        state_return = source_bin.set_state(Gst.State.NULL)

        if state_return == Gst.StateChangeReturn.FAILURE:
            return False, "source bin stop failed", src
        elif state_return == Gst.StateChangeReturn.ASYNC:
            state_return = source_bin.get_state(Gst.CLOCK_TIME_NONE)

        pad_name = "sink_%s" % src.idx
        logger.debug("Release pad name: {}".format(pad_name))
        logger.debug("First release branches.")
        for i in infer_ids:
            self.branch_manager[i].release_streammux(pad_name)
            # tee_src_pad = self.tee[src.idx].get_request_pad('src_%u')
            # tee_src_pad.unlink(sinkpad)
            
        logger.debug("Then release main streammux.")
        sinkpad = self.streammux.get_static_pad(pad_name)
        if sinkpad is not None:
            sinkpad.send_event(Gst.Event.new_flush_stop(False))
            # self.streammux.release_request_pad(sinkpad)

        logger.info("delete finished, source id: {} | padname: {}".format(id, pad_name))

        self.pipeline.remove(source_bin)

        src.rt_ctx = None
        self.srcm.clean_index(src)
        ret, msg, src = self.srcm.delete(id)    
        if not ret:
            raise Exception("srcm delete source failed")

        return ret, msg, src        

    @DSPD.d_acquire_lock
    def pause_src(self, id):
        """
        :param id: str, source id
        :return: (bool, str), result & message
        """ 
        raise NotImplementedError

        ret, msg, src = self.srcm.get(id)
        if not ret:
            return ret, msg

        source_bin = src.rt_ctx["bin"]
        state_return = source_bin.set_state(Gst.State.PAUSED)
        if state_return == Gst.StateChangeReturn.FAILURE:
            return False, "source %s change state failure %s" % (src.id, state_return)
        
        src.rt_ctx['enable'] = False
        return True, "success"

    @DSPD.d_acquire_lock
    def play_src(self, id):
        """

        :param id: str, source id
        :return: (bool, str), result & message
        """
        
        ret, msg, src = self.srcm.get(id=id)
        logger.debug("play source: {} | {}".format(id, ret))
        # print("src:", src)
        if not ret or isinstance(src, list):
            return ret, msg
        source_bin = src.rt_ctx["bin"]
        print("source_bin:",source_bin)
        state_return = source_bin.set_state(Gst.State.PLAYING)
        print(state_return)
        if state_return == Gst.StateChangeReturn.FAILURE:
            return False, "source %s change state failure %s" % (src.id, state_return)
        
        dst_folder = os.path.abspath(os.environ.get("GST_DEBUG_DUMP_DOT_DIR", ""))
        os.makedirs(dst_folder, exist_ok=True)
        graph_filename = "pipeline"
        graph_filepath = os.path.join(dst_folder, graph_filename)
        print(f"Saving pipeline in folder {dst_folder}")
        Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL, graph_filename)
        print("Files in dst folder:", os.listdir(dst_folder))
        Gst.debug_bin_to_dot_file_with_ts(self.pipeline, Gst.DebugGraphDetails.ALL, graph_filename)
        print("Files in dst folder:", os.listdir(dst_folder))
        os.system(f"dot -Tpng -o {graph_filepath}.png {graph_filepath}.dot")

        src.rt_ctx['enable'] = True
        return True, "success"

    @DSPD.d_acquire_lock
    def update_src(self, id, data):
        """

        :param id: str, source id
        :param data: any, source update information
        :return: (bool, str), result & message
        """
        ret, msg, src = self.srcm.get(id)
        if not ret:
            return ret, msg

        return self.update_src_abs(src, data)

    @DSPD.d_acquire_lock
    def verify_src(self, class_name, **data):
        # 检查id和uri是否存在
        if 'id' not in data or 'uri' not in data:
            logger.error("No id or url in params...")
            return False, "No id/url"
        elif class_name == 'GeneralCamera':
            print(class_name)
            print(data['id'])
            return True, "source correct"
        elif class_name == 'Stream':
            return True, "source correct"
        elif class_name == 'Camera':
            return True, "source correct"
        return False, "unknown source"

    @DSPD.d_acquire_lock
    def set_analytics(self, id=0, type=0, data=None, path=None):
        """
        :param id:str, source id
        :param type: enum, analytics type
        :param data: dict, line crossing data
        :return: (bool, str), result & path of analytics
        """
        if path:
            self.nvanalytics.set_property("config-file", path)
            return True, self.nvanalytics.get_property("config-file")
        ret, msg, src = self.srcm.get(id)
        if not ret:
            return ret, msg
        for key, value in data.items():
            coors = value.split(';')            
            for i in range(len(coors)):
                if i == 0:
                    coors[i] = int(float(coors[i]) * constant.MUXER_OUTPUT_WIDTH) 
                    continue
                elif i == 1:
                    coors[i] = int(float(coors[i]) * constant.MUXER_OUTPUT_HEIGHT) 
                    continue
                elif i%2 == 0:
                    coors[i] = int(float(coors[i]) * constant.MUXER_OUTPUT_WIDTH) 
                else:
                    coors[i] = int(float(coors[i]) * constant.MUXER_OUTPUT_HEIGHT) 
            coors = [str(coor) for coor in coors]
            semicolon = ';'
            coors = semicolon.join(coors)
            data[key] = coors
        idx = src.get_index()
        if type == 1:
            if modify_analytics_crossingline(constant.ANALYTICS_CONFIG_FILE, max_source_number=self.max_source_num, index=idx, enable=1, extended=0, mode='balanced', class_id=2, **data):
                self.nvanalytics.set_property("config-file", constant.ANALYTICS_CONFIG_FILE)      
            return True, self.nvanalytics.get_property("config-file")
        elif type == 2:
            # if self.is_ball:
            #     tmp_thread = self.thread_m.get_cam(source_id=idx)
            #     tmp_thread.set_analytics_dict(data)
            if modify_analytics_ROI(constant.ANALYTICS_CONFIG_FILE, max_source_number=self.max_source_num, index=idx, enable=1, inverse_roi=0, class_id=-1, **data):
                self.nvanalytics.set_property("config-file", constant.ANALYTICS_CONFIG_FILE)      
            return True, self.nvanalytics.get_property("config-file")
        else:
            return False, "None"
        
    def add_subthread(self, source):
        '''
        添加ptz管理子线程
        '''
        if source.get_cam_type():
            self.is_ball = True
            self.campoll.add_controller(source_id=source.idx, url=source.uri)
            if self.is_first_cam:
                self.is_first_cam = False
                logger.info("init thread manager...")
                self.thread_m = SuperiorPTZDataThread()
            logger.info("init ptz data thread for {}.... app type: {}".format(source.uri, self.app_name))
            ptz_thread = SinglePTZDataThread(source_id=source.idx, app_type=self.app_name)
            ptz_thread.set_ptz_patrol(source.get_patrol_list())
            self.thread_m.add_src(source_id=source.idx, sub=ptz_thread)
            logger.info("init cam controller for {}".format(source.uri))

    def cb_decodebin_newpad(self, bin, pad, data) -> None:
        """
        callback function
        decodebin pad_added signal
        :param bin:
        :param pad:
        :param data: str, source id
        :return:
        """
        # TODO log here
        caps = pad.get_current_caps()
        gststruct = caps.get_structure(0)
        gstname = gststruct.get_name()
        # print("gstname=",gstname)
        logger.info("gstname = {}".format(gstname))

        if gstname.find("video") != -1:
            pad_name = "sink_%s" % data
            # get a sink pad from the streammux, link to decodebin
            logger.info("pad name: {}".format(pad_name))
            try:
                if data in self.activated_pads_streammux:
                    sinkpad = self.streammux.get_static_pad(pad_name)
                else:
                    sinkpad = self.streammux.get_request_pad(pad_name)
                 # TODO log here
                if pad.link(sinkpad) == Gst.PadLinkReturn.OK:
                    # print("Decodebin linked to pipeline")
                    logger.info("Decodebin linked to pipeline successfully")
                    
                else:
                    print("Failed to link decodebin to pipeline\n")

                if data not in self.activated_pads_streammux:
                    self.activated_pads_streammux.append(data)
            except Exception as e:
                logger.error("连接资源时出错. fail to get request pad: {}".format(e))

    def cb_decodebin_child_added(self, child_proxy, obj, name, data) -> None:
        """
        :param child_proxy:
        :param obj:
        :param name:
        :param data:
        :return:
        """
        logger.info("Plugin {} created.".format(name))
        if name.find("source") != -1:
            obj_name = str(obj)
            if 'GstRTSPSrc' in obj_name:
                logger.info("Source type: RTSP")
                obj.set_property("latency", 10000)

            elif 'GstFileSrc' in obj_name:
                logger.info("Source type: File")

            else:
                logger.info("Unknown source type: {}".format(obj_name))

        if name.find("decodebin") != -1:
            obj.connect("child-added", self.cb_decodebin_child_added, data)

        if name.find("nvv4l2decoder") != -1:
            obj.set_property("gpu_id", self.gpu_id)

    def _uridecode_bin_name(self, bin_id):
        return "source-bin-%s" % bin_id

    def _create_uridecode_bin(self, bin_id, uri):
        bin_name = self._uridecode_bin_name(bin_id)
        bin = Gst.ElementFactory.make("uridecodebin", bin_name)
        if not bin:
            return None, "failed to create uridecodebin"

        bin.set_property("uri", uri)
        bin.connect("pad_added", self.cb_decodebin_newpad, bin_id)
        bin.connect("child-added", self.cb_decodebin_child_added, bin_id)

        return bin, "success"

    def _msg_thread_func(self):
        try:
            self.loop.run()
        except Exception as e:
            print(e)

