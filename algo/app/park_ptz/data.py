import os
import threading
import time
from loguru import logger
from collections import deque

import numpy as np
from requests import patch
# from kbds.util.fdfs_util.fdfs_util import FastDfsUtil
import sys
sys.path.append('../../')
from common.fdfs_util.fdfs_util import FastDfsUtil

from .constant import *

class FaceFeature():
    '''
    人脸数据类
    '''
    def __init__(self):
        self.link = ""
        self.state = FaceState.INIT
        self.bbox = None

    def set_frame_num(self, frame_num):
        self.frame_num = frame_num

    def set_source_id(self, source_id):
        self.source_id = source_id

    def set_timestamp(self, ts):
        self.ts = ts

    def set_bbox(self, bbox):
        self.bbox = bbox

    def set_state(self, state):
        self.state =  state

    def set_bg_image(self, array):
        self.bg_image = array

    def set_face_feature(self, array):
        self.face_feature = array

    def set_image_name(self, name):
        self.image_name = name

    def set_face_image_link(self, link):
        self.face_link = link

    def set_ff_link(self, link):
        self.ff_link = link

#== get functions=============================================================================

    def get_state(self):
        return self.state

    def get_bg_image(self):
        return self.bg_image

    def get_source_id(self):
        return self.source_id

    def get_frame_num(self):
        return self.frame_num

    def get_bbox(self):
        return self.bbox

    def get_ts(self):
        return self.ts

    def get_face_feature(self):
        return self.face_feature

    def get_image_name(self):
        return self.image_name

    def get_face_image_link(self):
        return self.face_link

    def get_ff_link(self):
        return self.ff_link

class FacePool():
    '''
    人脸数据池
    '''
    _instance = None
    lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance:
            return cls._instance
        else:
            with cls.lock:
                cls._instance = super().__new__(cls)
                return cls._instance

    def __init__(self):
        self.uninfered_face_num = 0
        self.pool = dict()
        self.save_fdfs = FastDfsUtil()
        

    def add(self, id, face):
        self.pool[id] = face
        return True, "success"

    def id_exist(self, id):
        if id in self.pool:
            return True
        return False

    def counter(self, op):
        if op == CounterOp.UP:
            self.uninfered_face_num = self.uninfered_face_num + 1
        if op == CounterOp.DOWN:
            self.uninfered_face_num = self.uninfered_face_num - 1
            

    def check_full(self):
        if self.uninfered_face_num >= MAX_FACE_IN_POOL:
            return True
        else:
            return False
            
    def get_face_by_id(self, id):
        return self.pool[id]

    def pop_face_by_id(self, id):
        return self.pool.pop(id)

    def get_ids_in_pool(self):
        ids = self.pool.copy().keys()
        return ids

    def check_msg_status(self, id):
        if self.pool[id].get_state() == FaceState.TOSEND:
            self.pool[id].set_state(FaceState.FINISH)
            return self.pool[id].get_face_image_link(), self.pool[id].get_ff_link(), self.pool[id].get_image_name(), self.pool[id].get_ts(), self.pool[id].get_source_id()

    def check_and_save(self):
        tmp_pool = self.pool.copy()
        for id in tmp_pool:
            if tmp_pool[id].get_state() == FaceState.TOSAVE:
                ret2 = self.save_face_to_local(id=id, face=tmp_pool[id])
                if ret2:
                    ret3 = self.save_face_feature_to_local(id=id, face=tmp_pool[id])
                    if ret2 and ret3:
                        self.pool[id].set_state(FaceState.TOSEND)
                    elif not ret2:
                        logger.error("上传图片至Fastdfs时失败.fail to upload images to FastDFS!")

    def save_face_to_local(self, id, face):
        img_path = "images/before/origin-{}.png".format(id)
        if os.path.exists("images/before/origin-{}.png".format(id)):
            name = "before-{}.png".format(id)
            face.set_image_name(name)
                  
            ret = self.save_fdfs.upload_by_filename(img_path)
            save_p = ret["Remote file_id"].decode('utf-8')
            face.set_face_image_link(save_p)     
            logger.debug("face-{} image file save to {}".format(id, save_p))
            os.remove(path=img_path)
            return True

        else:
            return False

    def save_face_feature_to_local(self, id, face):   
        ff = face.get_face_feature()
        ff_path = "images/face_feature/face-{0}-{1}.npy".format(id, face.get_ts())
        path = 'images/face_feature'
        if not os.path.exists(path):
            os.makedirs(path)
        np.save(ff_path, ff)
        # print("ff of face-{} saved to {}".format(id, ff_path))

        ret = self.save_fdfs.upload_by_filename(ff_path)
        save_p = ret["Remote file_id"].decode('utf-8')
        
        face.set_ff_link(save_p)
        logger.debug("face-{} feature npy file save to {}".format(id, save_p))
        # os.remove(path=ff_path)        

        return True

 
class TerminatePool():
    '''
    用于存放已经上传过的id
    '''
    _instance = None
    lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance:
            return cls._instance
        else:
            with cls.lock:
                cls._instance = super().__new__(cls)
                return cls._instance

    def __init__(self):
        self.pool = deque(maxlen=MAX_FACE_IN_POOL*10)

    def add(self, id):
        self.pool.append(id)
    
    def id_exist(self, id):
        for item in self.pool:
            if item[0] == id:
                return True
        # if id in self.pool:
        #     return True
        return False

    def get_bbox_by_id(self, id):
        for item in self.pool:
            if item[0] == id:
                return item

    def pop(self, data):
        self.pool.remove(data)

class Facethread(threading.Thread):
    '''
    检查并存储数据的线程
    '''
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True
        self._lock = threading.Lock()
        self._timeout = 30
        self.num_in_pool = 0
        self.face_pool = FacePool()
        self.create_save_dir()
        
    def create_save_dir(self):
        path = "images/aligned"
        if not os.path.exists(path):
            os.makedirs(path)
          
    def run(self):
        while True:
            time.sleep(1)
            self.face_pool.check_and_save()


        
