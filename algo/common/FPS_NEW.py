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
        # print(round(stream_fps, 2))
        return round(stream_fps, 2)
    

class PERF_DATA:
    def __init__(self) -> None:
        self.task = dict()

    

class PERF_DATA_SINGLE:
    def __init__(self, num_streams=1, app_name=None, srcm=None):
        self.perf_dict = {}
        self.all_stream_fps = {}
        self.app_name = app_name
        self.srcm = srcm
        # self.hbdata = HBdata()
        for i in range(num_streams):
            self.all_stream_fps[i]=GETFPS(i)

    def perf_print_callback(self):
        self.perf_dict = {stream_index:stream.get_fps() for (stream_index, stream) in self.all_stream_fps.items()}
        output_perf = dict()
        for key, value in self.perf_dict.items():
            task_id = self.srcm.get_id_by_idx(key)
            if task_id:
                if value:
                    task_id = self.srcm.get_id_by_idx(key)
                    if task_id:
                        output_perf[task_id] = value
        if not output_perf:
            output_perf = "No data updates"
        logger.warning("**PERF: \n {}: {}".format(self.app_name, output_perf))
        return True
    
    def update_fps(self, stream_index):
        self.all_stream_fps[stream_index].update_fps()

    # def update_heartbeat(self, fpsdict):
    #     time_local = time.time()
    #     # dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
    #     msg = {"time": time_local, "fps": fpsdict, "status": 'running'}
    #     self.hbdata.update_hb_data(msg)
    #     return True