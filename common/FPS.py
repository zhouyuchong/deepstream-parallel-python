import time
from threading import Lock
import json
import threading
from loguru import logger
start_time=time.time()

fps_mutex = Lock()

class GETFPS:
    def __init__(self,stream_id):
        global start_time
        self.start_time=start_time
        self.is_first=True
        self.frame_count=0
        self.stream_id=stream_id

    def update_fps(self):
        end_time = time.time()
        if self.is_first:
            self.start_time = end_time
            self.is_first = False
        else:
            global fps_mutex
            with fps_mutex:
                self.frame_count = self.frame_count + 1

    def get_fps(self):
        end_time = time.time()
        with fps_mutex:
            stream_fps = float(self.frame_count/(end_time - self.start_time))
            self.frame_count = 0
        self.start_time = end_time
        return round(stream_fps, 2)

class PERF_DATA:
    def __init__(self, num_streams=1):
        self.perf_dict = {}
        self.all_stream_fps = {}
        # self.hbdata = HBdata()
        for i in range(num_streams):
            self.all_stream_fps["stream{0}".format(i)]=GETFPS(i)

    def perf_print_callback(self):
        self.perf_dict = {stream_index:stream.get_fps() for (stream_index, stream) in self.all_stream_fps.items()}
        # print ("\n**PERF: ", self.perf_dict, "\n")
        logger.trace("**PERF: \n {}".format(self.perf_dict))
        # self.update_heartbeat(self.perf_dict)
        return True
    
    def update_fps(self, stream_index):
        self.all_stream_fps[stream_index].update_fps()

    # def update_heartbeat(self, fpsdict):
    #     time_local = time.time()
    #     # dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
    #     msg = {"time": time_local, "fps": fpsdict, "status": 'running'}
    #     self.hbdata.update_hb_data(msg)
    #     return True