"""
事件管理器: 与GeneralCamera绑定，一个GeneralCamera（或者称为source）实例存在唯一的EventManager
事件：封装单个独立事件，负责实现以下三个接口
    1、启动 run()
    2、停止 exit()
    3、推送事件信息 pop_event()

事件管理器可以注册不同事件Event，例如人车聚集 GatherEvent，或者超速检测事件 SpeedEvent..
"""
import time
from threading import Thread
from collections import deque, namedtuple
from abc import ABC, abstractmethod

import cv2
from loguru import logger
import sys
sys.path.append('../')
from common.fdfs_util.fdfs_util import FastDfsUtil
from .pv_data import GatherData, IncreaseData, LingerData, RetrogradeData, SpeedingData, SpeedingNumData
from .utils import AnaInfo

MSG_INFO = namedtuple("MSG_INFO", ['catch_time', 'ptz_id', 'track_id', 'frame_num', 'event_label', 'process_data', 'process_func'])
count_id = 0


class Event(ABC, Thread):
    def __init__(self):
        super().__init__()
        self.buffer = deque(maxlen=5)
        self.save_fdfs = FastDfsUtil() 

    def feed_data(self, data):
        self.buffer.append(data)

    # @staticmethod
    def upload_img(self, img):
        global count_id
        frame_copy = img
        frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)

        img_name = 'pv-images/{}.png'.format(count_id)
        count_id += 1
        cv2.imwrite(img=frame_copy, filename=img_name)

        success, encoded_image = cv2.imencode(".png", frame_copy)
        #将数组转为bytes
        byte_data = encoded_image.tobytes()
        try:
            ret = self.save_fdfs.upload_by_buffer(byte_data, "png")
            link = ret["Remote file_id"].decode('utf-8')
            return link
        except Exception as e:
            logger.error("上传图片至Fastdfs时失败. fail to upload images to fastfdfs: {}".format(e))
            return False

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def exit(self):
        pass

    @abstractmethod
    def pop_event(self):
        pass


# 人或车聚集event_data
class GatherEvent(Event):
    def __init__(self, **kwargs):
        super().__init__()
        # 记录每个监测区域的事件信息
        self.event_dict = dict()
        for params in kwargs["ptz_params"]:
            for roi_label in params["coordinate"].keys():
                event_key = "{}-{}".format(params["ptz_id"], roi_label)
                self.event_dict[event_key] = GatherData(kwargs["number_thresh"])

        self.message_buffer = deque(maxlen=5)
        self._active = True
        logger.debug("GatherEvent | inited.")

    def run(self):
        logger.debug("GatherEvent | start.")
        while self._active:
            if not self.buffer:
                continue

            event_data = self.buffer.popleft()

            catch_time = event_data.time
            ptz_id = event_data.ptz_id
            for event_key, event_value in self.event_dict.items():
                num_person = 0
                num_car = 0
                for event in event_data.events:
                    track_id, class_id, detect_bbox, analytic_info, frame_num = event
                    event_label = event_key
                    if event_label not in analytic_info.roi:
                        continue
                    # 如果在区域内,统计人车数量
                    num_person += 1 if class_id == '0' else 0
                    num_car += 1 if class_id == '2' else 0
                # logger.debug("GatherEvent | {}-{} catch_time:{} num_person:{} num_car:{}"
                #              "".format(event_key, track_id, catch_time, num_person, num_car))
                event_value.add_data(catch_time, num_person, num_car)

                # 消息推送
                if event_value.event_trigger():
                    logger.info("GatherEvent ptz_id:{} | gather event triggered.".format(ptz_id))
                    process_data = event_data.events
                    self.message_buffer.append(MSG_INFO(catch_time=str(catch_time),
                                                        ptz_id=ptz_id,
                                                        track_id='',
                                                        frame_num=frame_num,
                                                        event_label='gather',
                                                        process_data=process_data,
                                                        process_func=self.process_func))

    def pop_event(self):
        res = []
        while self.message_buffer:
            res.append(self.message_buffer.pop())
        return res

    def exit(self):
        logger.debug("GatherEvent | stop.")
        self._active = False

    def process_func(self, image, process_data, frame_number):
        for data in process_data:
            track_id, class_id, detect_bbox, _, frame_num = data
            
            rect_color = (0, 200, 255) if class_id == 0 else (200, 0, 255)
            cv2.rectangle(image, (int(detect_bbox[0]), int(detect_bbox[1])),
                            (int(detect_bbox[2]), int(detect_bbox[3])), rect_color, 2)
        img_url = self.upload_img(image)
        logger.info("image saved, event belongs to: gather...")
        return img_url


# 单位时间内人或车数量剧增
class IncreaseEvent(Event):
    def __init__(self, **kwargs):
        super().__init__()
        # 记录每个监测区域的事件信息
        self.event_dict = dict()
        for params in kwargs["ptz_params"]:
            for roi_label in params["coordinate"].keys():
                event_key = "{}-{}".format(params["ptz_id"], roi_label)
                self.event_dict[event_key] = IncreaseData(kwargs["cycle_time"], kwargs["cycle_increase_thresh"])

        self.message_buffer = deque(maxlen=5)
        self._active = True
        logger.debug("IncreaseEvent | inited.")

    def run(self):
        logger.debug("IncreaseEvent | start.")
        while self._active:
            if not self.buffer:
                continue

            event_data = self.buffer.popleft()

            catch_time = event_data.time
            ptz_id = event_data.ptz_id
            for event_key, event_value in self.event_dict.items():
                num_person = 0
                num_car = 0
                for event in event_data.events:
                    track_id, class_id, detect_bbox, analytic_info, frame_num = event
                    event_label = event_key
                    if event_label not in analytic_info.roi:
                        continue
                    # 如果在区域内
                    num_person += 1 if class_id == '0' else 0
                    num_car += 1 if class_id == '2' else 0
                event_value.add_data(catch_time, num_person, num_car)
                # logger.debug("IncreaseEvent | {}-{} catch_time:{} num_person:{} num_car:{}"
                #              "".format(event_key, track_id, catch_time, num_person, num_car))

                # 消息推送
                if event_value.event_trigger():
                    logger.info("IncreaseEvent ptz_id:{} | increase event triggered. \n".format(ptz_id))
                    process_data = event_data.events
                    self.message_buffer.append(MSG_INFO(catch_time=str(catch_time),
                                                        ptz_id=ptz_id,
                                                        track_id='',
                                                        frame_num=frame_num,
                                                        event_label='increase',
                                                        process_data=process_data,
                                                        process_func=self.process_func))

    def pop_event(self):
        res = []
        while self.message_buffer:
            res.append(self.message_buffer.pop())
        return res

    def exit(self):
        logger.debug("IncreaseEvent | stop.")
        self._active = False

    def process_func(self, image, process_data, frame_number):
        for data in process_data:
            track_id, class_id, detect_bbox, analytic_info, frame_num = data
            cv2.rectangle(image, (int(detect_bbox[0]), int(detect_bbox[1])),
                          (int(detect_bbox[2]), int(detect_bbox[3])), (0, 200, 255), 2)
        img_url = self.upload_img(img=image)
        logger.info("image saved, event belongs to: increase...")
        return img_url


# 人或车逗留
class LingerEvent(Event):
    def __init__(self, **kwargs):
        super().__init__()
        # 记录每个监测区域的事件信息
        self.event_dict = dict()
        for params in kwargs["ptz_params"]:
            for roi_label, roi_polyline in params["coordinate"].items():
                event_key = "{}-{}".format(params["ptz_id"], roi_label)
                self.event_dict[event_key] = LingerData(kwargs["linger_time_thresh"], roi_polyline)

        self.message_buffer = deque(maxlen=5)
        self._active = True
        logger.debug("LingerEvent | inited.")

    def run(self):
        logger.debug("LingerEvent | start.")
        while self._active:
            if not self.buffer:
                # logger.info("LingerEvent | buffer empty.")
                continue

            event_data = self.buffer.popleft()
            # logger.info("LingerEvent | event_data num:{}".format(len(event_data.events)))

            catch_time = event_data.time
            ptz_id = event_data.ptz_id
            # print("***********", self.event_dict.keys())
            for event_key, event_value in self.event_dict.items():
                for event in event_data.events:
                    track_id, class_id, detect_bbox, analytic_info, frame_num = event
                    # logger.debug("LingerEvent event | track_id:{}, class_id:{}, detect_bbox:{}, analytic_info:{}.".
                    #              format(track_id, class_id, detect_bbox, analytic_info))

                    event_label = event_key
                    # print("*************", analytic_info.roi, "  ", event_label)
                    in_roi = event_label in analytic_info.roi
                    # logger.debug("LingerEvent | {}-{} catch_time:{} in_roi:{}.".format(event_key,
                    #                                                                    track_id, catch_time, in_roi))
                    event_value.add_data(track_id, detect_bbox, catch_time, in_roi)

                # 事件处理
                ids_triggered = event_value.event_trigger()

                if ids_triggered:
                    logger.info("LingerEvent ptz_id:{} | linger event triggered .\n"
                                "ids:[{}]".format(ptz_id, ids_triggered))
                    # process_data = event_data.events
                for trigger_id in ids_triggered:
                    for event in event_data.events:
                        track_id, class_id, detect_bbox, analytic_info, frame_num = event
                        if trigger_id == track_id:
                            self.message_buffer.append(MSG_INFO(catch_time=str(catch_time),
                                                                ptz_id=ptz_id,
                                                                track_id=track_id,
                                                                frame_num=frame_num,
                                                                event_label='linger',
                                                                process_data=[event],
                                                                process_func=self.process_func))

    def pop_event(self):
        res = []
        while self.message_buffer:
            res.append(self.message_buffer.pop())
        return res

    def exit(self):
        logger.debug("LingerEvent | stop.")
        self._active = False

    def process_func(self, image, process_data, frame_number):
        for data in process_data:
            track_id, class_id, detect_bbox, analytic_info, frame_num = data
            # print(int(detect_bbox[0]), int(detect_bbox[1]), int(detect_bbox[2]), int(detect_bbox[3]), class_id, track_id)
            # cv2.imwrite("test.png", image)
            cv2.rectangle(image, (int(detect_bbox[0]), int(detect_bbox[1])),
                          (int(detect_bbox[2]), int(detect_bbox[3])), (0, 0, 255), 2)
        logger.info("image saved, event belongs to: linger...")
        img_url = self.upload_img(img=image)
        return img_url


# 人和车逆行事件检测
class RetrogradeEvent(Event):
    def __init__(self, **kwargs):
        super().__init__()
        # 记录每个监测区域的事件信息
        self.event_dict = dict()
        for params in kwargs["ptz_params"]:
            for roi_label in  params["coordinate"].keys():
                event_key = "{}-{}".format(params["ptz_id"], roi_label)
                self.event_dict[event_key] = RetrogradeData()
        self.message_buffer = deque(maxlen=30)
        self._active = True
        logger.debug("RetrogradeEvent | inited.")

    def run(self):
        logger.debug("RetrogradeEvent | start.")
        while self._active:
            if not self.buffer:
                continue

            event_data = self.buffer.popleft()

            catch_time = event_data.time
            ptz_id = event_data.ptz_id
            for event_key, event_value in self.event_dict.items():
                for event in event_data.events:
                    track_id, class_id, detect_bbox, analytic_info, frame_num = event
                    event_label = event_key
                    if event_label in analytic_info.roi:
                        # logger.debug("RetrogradeEvent | {}-{} satisfy.".format(event_key, track_id))
                        is_retrograde = event_key in analytic_info.dir
                        event_value.add_data(track_id, catch_time, is_retrograde)

                # 事件处理
                ids_triggered = event_value.event_trigger()
                if ids_triggered:
                    logger.info("RetrogradeEvent ptz_id:{} | retrograde event event triggered .\n"
                                "ids:[{}]".format(ptz_id, ids_triggered))
                for trigger_id in ids_triggered:
                    for event in event_data.events:
                        track_id, class_id, detect_bbox, analytic_info, frame_num = event
                        if trigger_id == track_id:
                            self.message_buffer.append(MSG_INFO(catch_time=str(catch_time),
                                                                ptz_id=ptz_id,
                                                                track_id=track_id,
                                                                frame_num=frame_num,
                                                                event_label='retrograde',
                                                                process_data=[event],
                                                                process_func=self.process_func))

    def pop_event(self):
        res = []
        while self.message_buffer:
            res.append(self.message_buffer.pop())
        return res

    def exit(self):
        logger.debug("RetrogradeEvent | stop.")
        self._active = False

    def process_func(self, image, process_data, frame_number):
        for data in process_data:
            track_id, class_id, detect_bbox, analytic_info, frame_num = data
            cv2.rectangle(image, (int(detect_bbox[0]), int(detect_bbox[1])),
                          (int(detect_bbox[2]), int(detect_bbox[3])), (0, 200, 255), 2)
        img_url = self.upload_img(image)
        logger.info("image saved, event belongs to: retrograde...")
        return img_url


# 超速告警
class SpeedingEvent(Event):
    def __init__(self, **kwargs):
        super().__init__()
        # 记录每个监测区域的事件信息
        self.event_dict = dict()
        for params in kwargs["ptz_params"]:
            for roi_label in params["coordinate"].keys():
                event_key = "{}-{}".format(params["ptz_id"], roi_label)
                calibration_extra_data = params['calibration_extra'][roi_label] if params.get(
                    'calibration_extra', None) else None
                self.event_dict[event_key] = SpeedingData(kwargs['speed_thresh'],
                                                          params['calibration'][roi_label],
                                                          calibration_extra_data)
        self.message_buffer = deque(maxlen=30)
        self._active = True
        logger.debug("SpeedignEvent | inited.")

    def run(self):
        logger.debug("SpeedignEvent | start.")
        while self._active:
            if not self.buffer:
                continue

            event_data = self.buffer.popleft()

            catch_time = event_data.time
            ptz_id = event_data.ptz_id
            for event_key, event_value in self.event_dict.items():
                for event in event_data.events:
                    track_id, class_id, detect_bbox, analytic_info, frame_num = event
                    # logger.debug("track:{} {} {} {}".format(track_id, class_id, event_key, analytic_info.roi))
                    event_label = event_key
                    if event_label in analytic_info.roi:
                        # logger.debug("SpeedingEvent | {}-{} satisfy.".format(event_key, track_id))
                        event_value.add_data(track_id, catch_time, detect_bbox)

                # 事件处理
                ids_triggered = event_value.event_trigger(catch_time)
                if ids_triggered:
                    logger.info("SpeedingEvent ptz_id:{} | speeding event event triggered .\n"
                                "ids:[{}]".format(ptz_id, ids_triggered))
                for trigger_id in ids_triggered:
                    for event in event_data.events:
                        track_id, class_id, detect_bbox, analytic_info, frame_num = event
                        if trigger_id == track_id:
                            self.message_buffer.append(MSG_INFO(catch_time=str(catch_time),
                                                                ptz_id=ptz_id,
                                                                track_id=track_id,
                                                                frame_num=frame_num,
                                                                event_label='speed',
                                                                process_data=[event],
                                                                process_func=self.process_func))

    def pop_event(self):
        res = []
        while self.message_buffer:
            res.append(self.message_buffer.pop())
        return res

    def exit(self):
        logger.debug("SpeedignEvent | stop.")
        self._active = False

    def process_func(self, image, process_data, frame_number):
        for data in process_data:
            track_id, class_id, detect_bbox, analytic_info, frame_num = data
            if frame_num >= frame_number-1 and frame_num <= frame_number+1:
                cv2.rectangle(image, (int(detect_bbox[0]), int(detect_bbox[1])),
                            (int(detect_bbox[2]), int(detect_bbox[3])), (0, 255, 255), 2)
            # cv2.putText(image, str(track_id), int((detect_bbox[0])), int(detect_bbox[1] - 10),
            #             cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        img_url = self.upload_img(image)
        logger.info("image saved, event belongs to: speeding...")
        return img_url


# 超速数量超出限制
class SpeedingNumEvent(Event):
    def __init__(self, **kwargs):
        super().__init__()
        # 记录每个监测区域的事件信息
        self.event_dict = dict()
        for params in kwargs["ptz_params"]:
            for roi_label in params["coordinate"].keys():
                event_key = "{}-{}".format(params["ptz_id"], roi_label)
                calibration_extra_data = params['calibration_extra'][roi_label] if params.get('calibration_extra', None) else None
                self.event_dict[event_key] = SpeedingNumData(kwargs['speed_thresh'],
                                                          kwargs['overspeed_number_thresh'],
                                                          params['calibration'][roi_label],
                                                             calibration_extra_data)
        self.message_buffer = deque(maxlen=30)
        self._active = True
        logger.debug("SpeedignNumEvent | inited.")

    def run(self):
        logger.debug("SpeedignNumEvent | start.")
        while self._active:
            if not self.buffer:
                continue

            event_data = self.buffer.popleft()

            catch_time = event_data.time
            ptz_id = event_data.ptz_id
            for event_key, event_value in self.event_dict.items():
                for event in event_data.events:
                    track_id, class_id, detect_bbox, analytic_info, frame_num = event
                    event_label = event_key
                    if event_label in analytic_info.roi:
                        # logger.debug("SpeedingNumEvent | {}-{} satisfy.".format(event_key, track_id))
                        event_value.add_data(track_id, catch_time, detect_bbox)

                # 事件处理
                ids_triggered = event_value.event_trigger(catch_time)
                if ids_triggered:
                    logger.info("SpeedingNumEvent ptz_id:{} | speeding num event event triggered .\n"
                                "ids:[{}]".format(ptz_id, ids_triggered))
                # process_data = []
                for trigger_id in ids_triggered:
                    for event in event_data.events:
                        track_id, class_id, detect_bbox, analytic_info, frame_num = event
                        if trigger_id == track_id:
                            # process_data.append(event)

                            self.message_buffer.append(MSG_INFO(catch_time=str(catch_time),
                                                                ptz_id=ptz_id,
                                                                track_id=track_id,
                                                                frame_num=frame_num,
                                                                event_label='num',
                                                                process_data=[event],
                                                                process_func=self.process_func))

    def pop_event(self):
        res = []
        while self.message_buffer:
            res.append(self.message_buffer.pop())
        return res

    def exit(self):
        logger.debug("SpeedignNumEvent | stop.")
        self._active = False

    def process_func(self, image, process_data, frame_number):
        for data in process_data:
            track_id, class_id, detect_bbox, analytic_info, frame_num = data
            if frame_num >= frame_number-1 and frame_num <= frame_number+1:
                cv2.rectangle(image, (int(detect_bbox[0]), int(detect_bbox[1])),
                            (int(detect_bbox[2]), int(detect_bbox[3])), (0, 0, 255), 2)
            # cv2.putText(image, str(track_id), (detect_bbox[0], detect_bbox[1] - 10),
            #             cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
        img_url = self.upload_img(image)
        logger.info("image saved, event belongs to: speedingnum...")
        return img_url


class EventManager:
    def __init__(self, **kwargs):
        self.event_pool = dict()
        self.params = kwargs
        self.add_thread()
        
    def add_thread(self):
        if 'number_thresh' in self.params:
            self.register_event(GatherEvent(**self.params))
        if 'cycle_time' in self.params and 'cycle_increase_thresh' in self.params:
            self.register_event(IncreaseEvent(**self.params))
        if 'linger_time_thresh' in self.params:
            self.register_event(LingerEvent(**self.params))
        if [True for i in self.params['ptz_params'] if 'direction' in i]:
            self.register_event(RetrogradeEvent(**self.params))
        if 'speed_thresh' in self.params:
            if 'overspeed_number_thresh' in self.params:
                self.register_event(SpeedingNumEvent(**self.params))
            else:
                self.register_event(SpeedingEvent(**self.params))
        logger.debug("EventManager | inited.")

    def register_event(self, event):
        self.event_pool[event.__class__.__name__] = event

    def feed_data(self, data):
        # logger.info("EventManager feed data [time:{} , ptz_id:{}, events:{}]".format(data.time,
        #                                                                              data.ptz_id, data.track_ids))
        # logger.info("EventManager feed data [time:{} , ptz_id:{}]".format(data.time,
        #                                                                              data.ptz_id))
        for event in self.event_pool.values():
            event.feed_data(data)

    def pop_events(self):
        events = []
        # print("-----------",self.event_pool)
        for e in self.event_pool.values():
            events.extend(e.pop_event())
        return events            

    def start(self):
        logger.info("EventManager | thread start...")
        for event_name, event in self.event_pool.items():
            event.start()
            logger.info("EventManager | event_name:{} supported.".format(event_name))

    def stop(self):
        for event in self.event_pool.values():
            event.exit()  
        self.event_pool = None
        self.event_pool = dict()

    def restart(self):
        logger.info("EventManager | thread restart...")
        self.add_thread()
        for event_name, event in self.event_pool.items():
            event.start()
            logger.info("EventManager | event_name:{} supported.".format(event_name))

    def delete_event(self, event_name):
        self.event_pool[event_name].exit()
        del self.event_pool[event_name]

    def delete_all_event(self):
        for i in self.event_pool.values():
            i.exit()
        self.event_pool.clear()


