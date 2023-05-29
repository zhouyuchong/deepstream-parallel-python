"""
事件数据，配合event_manager下的Event使用
Event下基础数据以字典形式存储，
    key： ptz-coordinate_key形式存储，例如： 1&2&3-ptz1
    value: 事件相关的 **Data

主要接口：
    add_event: 负责接收单个事件的信息数据
    event_trigger： 当该接口被调用时返回事件触发的状态信息
                如：是否发生
                    哪些track_id触发的事件
"""
import time
import cv2
from collections import namedtuple, deque

import numpy as np
from loguru import logger

from .config import *


EVENT_INFO = namedtuple("EVENT_INFO", ['track_id', 'class_id', 'detect_bbox', 'analytic_info', 'frame_num'])

class EventFinished:
    def __init__(self, max_num):
        self.pool = deque(maxlen=max_num)

    def add(self, id, label):
        tmpdict = dict()
        tmpdict[id] = label
        self.pool.append(tmpdict)

    def check(self, id, label):
        for item in self.pool:
            if id in item.keys() and label in item.values():
                return False
        return True


class EventData:
    def __init__(self, sys_time, ptz_id, events=[]):
        self.time = sys_time
        self.ptz_id = ptz_id
        self.events = events

    def add_event(self, event_info):
        self.events.append(event_info)

    @property
    def track_ids(self):
        return [e.track_id for e in self.events]


# 1、人或车聚集
class GatherData:
    def __init__(self, number_thresh):
        self.number_thresh = number_thresh
        # 事件连续触发的帧数
        self.event_trigger_count = 0
        # 连续触发帧数超过该阈值则告警
        self.event_trigger_thresh = 5
        logger.info("GatherData Init: num_thresh:{}/ event_trigger_count:{}/ "
                    "event_trigger_thresh:{}".format(self.number_thresh,
                                                     self.event_trigger_count, self.event_trigger_thresh))

    def add_data(self, catch_time, num_person, num_car):
        logger.debug("catch : {}| {}".format(num_person, num_car))
        is_overcrowd = num_person > self.number_thresh or num_car > self.number_thresh
        self.event_trigger_count = self.event_trigger_count+1 if is_overcrowd else 0

    def event_trigger(self):
        # 当且仅当等于阈值时告警
        res = self.event_trigger_count == self.event_trigger_thresh
        return res


# 2、单位时间内人车剧增
class IncreaseData:
    def __init__(self, cycle_time, cycle_increase_thresh):
        self.cycle_time = cycle_time
        self.cycle_increase_thresh = cycle_increase_thresh
        logger.info("IncreaseData Init: cycle_time:{}/ cycle_increase_thresh:{}"
                    "".format(self.cycle_time, self.cycle_increase_thresh))

        self.last_push_time = 0

        self.last_num_person = 0
        self.last_num_car = 0
        self.num_person_increase = 0
        self.num_car_increase = 0

        self.trigger_mark = False

    def add_data(self, catch_time, num_person, num_car):
        if catch_time - self.last_push_time > self.cycle_increase_thresh:
            self.num_person_increase = num_person - self.last_num_person
            self.num_car_increase = num_car - self.last_num_car
            # logger.debug("IncreaseData info: {} -> {} | {} {}".format(self.last_push_time, catch_time, self.num_person_increase, self.num_car_increase))
            self.last_num_person = num_person
            self.last_num_car = num_car
            self.last_push_time = catch_time
            self.trigger_mark = True

    def event_trigger(self):
        res = max(self.num_person_increase, self.num_car_increase) >= self.cycle_increase_thresh if self.trigger_mark else False
        self.trigger_mark = False
        return res


# 3、人或车逗留
class LingerData:
    def __init__(self, linger_time_thresh, roi_polyline):
        self.linger_time_thresh = linger_time_thresh
        # self.inside_rad = self.get_inside_rad(roi_polyline)
        self.track_dict = dict()
        self.history = dict()  # 上一次巡检目标位置记录
        self.width_rate = 1.5
        logger.info("LingerData Init: linger_time_thresh:{}".format(self.linger_time_thresh))

    def clean(self):
        self.track_dict.clear()

    def add_data(self, track_id, detect_bbox, catch_time, is_in_roi):
        # logger.debug("add data: {} {} {}".format(track_id, detect_bbox, catch_time))
        x1, y1, x2, y2 = detect_bbox
        person_width = x2 - x1
        foot_loc = ((x1 + x2) / 2.0, y2)

        if (track_id not in self.track_dict) or (not is_in_roi):
            # logger.debug("track id: {} | {} | {}".format(track_id, self.track_dict, is_in_roi))
            # [开始时间、结束时间、初始位置、是否已推送、行人宽度]
            self.track_dict[track_id] = [catch_time, catch_time, foot_loc, False, person_width]

        # foot_loc与初始位置距离
        # 如果距离小于阈值更新捕获结束时间

        dist_with_origin = self.l2_distance(foot_loc, self.track_dict[track_id][2])
        # logger.debug("dist width: {} | {} | {} | {}".format(dist_with_origin, foot_loc, self.track_dict[track_id][2], track_id))
        if dist_with_origin < person_width*self.width_rate:
            self.track_dict[track_id][1] = catch_time

        # 历史数据清理
        if time.time() - self.track_dict[track_id][1] > 1*30*10:
            del self.track_dict[track_id]
        for mark_time in list(self.history.keys()):
            if time.time() - mark_time > 1*30*10:
                del self.history[mark_time]

    def event_trigger(self):
        ids_triggered = []
        for track_id, linger_data in self.track_dict.items():
            time_start, time_end, foot_loc, is_pushed, person_width = linger_data
            dist_history = self.min_distance_with_history(foot_loc)
            # logger.debug("trigger : {} {} {}".format(time_end, time_start, dist_history))
            if (time_end - time_start > self.linger_time_thresh) and (not is_pushed) and \
                    dist_history > person_width*self.width_rate:
                ids_triggered.append(track_id)
                linger_data[3] = True
                self.history[time.time()] = foot_loc
        return ids_triggered

    '''
    @staticmethod
    def get_inside_rad(polyline):
        """
        获取多边形最大内接圆半径
        注： 以内结圆半径，作为前后两次轮巡为同一目标判定依据
        @return:
        """
        region = np.reshape([float(i) for i in polyline.split(';')], (-1, 2))
        region = region*np.array([config.MUXER_OUTPUT_WIDTH, config.MUXER_OUTPUT_HEIGHT])
        logger.debug("region: {}".format(region))
        width_tmp, height_tmp = np.max(region, axis=0).astype(np.int32)
        width_tmp += 1
        height_tmp += 1

        raw_dist = np.zeros((height_tmp, width_tmp))
        contours = np.array(region, np.int32)
        for i in range(height_tmp):
            for j in range(width_tmp):
                raw_dist[i, j] = cv2.pointPolygonTest(contours, (j, i), True)
        _, max_val, _, max_dist_pt = cv2.minMaxLoc(raw_dist)
        return max_val
    '''

    def min_distance_with_history(self, foot_loc):
        dist_min = min([self.l2_distance(foot_loc, foot_mark) for mark_time, foot_mark in self.history.items()]) \
            if self.history else 9999.0
        return dist_min

    @staticmethod
    def l2_distance(p1, p2):
        return np.linalg.norm(np.subtract(p1, p2))


# 4、人或车逆行
class RetrogradeData:
    def __init__(self):
        self.retrograde_time_thresh = 2
        self.track_dict = dict()
        logger.info("RetrogradeData Init: retrograde_time_thresh:{}".format(self.retrograde_time_thresh))

    def add_data(self, track_id, catch_time, is_retrograde):
        if (track_id not in self.track_dict) or (not is_retrograde):
            # [开始时间、结束时间、是否已推送]
            self.track_dict[track_id] = [catch_time, catch_time, False]
        self.track_dict[track_id][1] = catch_time
        # 清理过期数据（半小时外）
        if time.time() - self.track_dict[track_id][1] > 30*60:
            del self.track_dict[track_id]

    def event_trigger(self):
        ids_triggered = []
        for track_id, linger_data in self.track_dict.items():
            time_start, time_end, is_pushed = linger_data
            if time_end - time_start > self.retrograde_time_thresh and (not is_pushed):
                ids_triggered.append(track_id)
                linger_data[2] = True
        return ids_triggered


# 5、超速检测
class SpeedingData:
    def __init__(self, speed_thresh, calibration, calibration_extra=None):
        self.speed_thresh = speed_thresh
        self.calibration = calibration
        self.calibration_extra = calibration_extra
        logger.info("SpeedingData Init: speed_thresh:{}/ "
                    "calibration:{} calibration_extra:{}".format(self.speed_thresh, self.calibration, self.calibration_extra))
        calibration_data = [float(i) for i in calibration.split(";")]
        calibration_extra_data = [float(i) for i in calibration_extra.split(";")] if calibration_extra else None

        self.target_height = 1.7
        self.trans_matrix = self.get_trans_matrix(self.calibration, self.calibration_extra)
        logger.info("SpeedingData Init: tran_matrix:{}".format(self.trans_matrix))

        self.history_len = 8
        self.trigger_number_thresh = 5
        self.track_dict = dict()

    def add_data(self, track_id, catch_time, detect_bbox):
        # logger.debug("Speeding trans: {} | {}".format(track_id, catch_time))
        if track_id not in self.track_dict:
            # 上次更新时间、历史数据、是否已推送
            self.track_dict[track_id] = [catch_time, deque(maxlen=self.history_len), False, 0]

        # 真实位置
        pix_loc = [(detect_bbox[0]+detect_bbox[1])/2.0, detect_bbox[3]]
        realword_loc = self.tran_location(pix_loc)
        # logger.debug("SpeedingData trans | {} -> {}".format(pix_loc, realword_loc))
        self.track_dict[track_id][0] = catch_time
        self.track_dict[track_id][1].append((catch_time, realword_loc))
        # 清理过期数据（半小时外）
        if time.time() - self.track_dict[track_id][0] > 30*60:
            del self.track_dict[track_id]

    def event_trigger(self, catch_time):
        ids_triggered = []
        for track_id, linger_data in self.track_dict.items():
            update_time, track_data, is_pushed, trigger_num = linger_data
            if len(track_data) != self.history_len or is_pushed:
                continue
            
            # 计算速度
            time_start, loc_start = track_data.popleft()
            time_end, loc_end = track_data.pop()
            current_speed = self.cal_distance(loc_end, loc_start) / (time_end - time_start + 1e-6)
            logger.debug("speed| id:{} | speed:{:.2f} | {} {} -> {} {}".format(track_id, current_speed, loc_start, time_start, loc_end, time_end))
            # print(loc_end, loc_start, self.cal_distance(loc_end, loc_start), time_start, time_end, current_speed, self.speed_thresh)
            if current_speed < self.speed_thresh:
                linger_data[3] = 0
                continue

            linger_data[3] += 1
            if linger_data[3]>self.trigger_number_thresh:
                ids_triggered.append(track_id)
                linger_data[2] = True
        return ids_triggered
    
    def get_trans_matrix(self, calibration, calibration_extra):
        use_3d = bool(calibration_extra)
        calibration_data = [float(i) for i in calibration.split(";")]
        calibration_extra_data = [float(i) for i in calibration_extra.split(
            ";")] if use_3d else None
        
        cali_bbox = None
        target_bbox = None

        if not use_3d:
            cali_bbox = np.array(calibration_data[:8]).reshape(
                (-1, 2)).astype(np.float32)

            L1, L2 = calibration_data[10:]
            target_bbox = np.array([[0.0, 0.0],
                                    [L1, 0.0],
                                    [L1, L2],
                                    [0.0, L2]]).astype(np.float32)
        else:
            tmp_pts = []
            calibration_extra_bbox = np.array(calibration_extra_data[:16]).reshape(
                (-1, 2)).astype(np.float32)
            L1, L2, H = calibration_extra_data[16:]
            height_ratio = 1.5/ H

            for i in range(4):
                p0 = calibration_extra_bbox[2*i]
                p1 = calibration_extra_bbox[2*i + 1]

                target_point = p0 + (p1 - p0)*height_ratio
                tmp_pts.append(target_point)
            cali_bbox = np.array(tmp_pts).astype(np.float32)
            target_bbox = np.array([[0.0, 0.0], [L1, 0.0], [L1, L2], [0.0, L2]]).astype(np.float32)

        logger.debug("SpeedingData cali_bbox:{} target_bbox:{}".format(cali_bbox, target_bbox))
        cali_bbox[:, 0] *= MUXER_OUTPUT_WIDTH
        cali_bbox[:, 1] *= MUXER_OUTPUT_HEIGHT
        trans_matrix = cv2.getPerspectiveTransform(cali_bbox, target_bbox)

        return trans_matrix


    def tran_location(self, point):
        u, v = point[0], point[1]
        x = (self.trans_matrix[0][0] * u + self.trans_matrix[0][1] * v + self.trans_matrix[0][2]) / (self.trans_matrix[2][0] * u + self.trans_matrix[2][1] * v + self.trans_matrix[2][2])
        y = (self.trans_matrix[1][0] * u + self.trans_matrix[1][1] * v + self.trans_matrix[1][2]) / (self.trans_matrix[2][0] * u + self.trans_matrix[2][1] * v + self.trans_matrix[2][2])
        return x, y

    @staticmethod
    def cal_distance(p1, p2):
        return np.linalg.norm([p1[0]-p2[0], p1[1]-p2[1]])


# 6、超速数量超额检测
class SpeedingNumData:
    def __init__(self, speed_thresh, overspeed_number_thresh, calibration, calibration_extra=None):
        self.speed_thresh = speed_thresh
        self.overspeed_number_thresh = overspeed_number_thresh
        self.calibration = calibration
        self.calibration_extra = calibration_extra
        logger.info("SpeedingNumData Init: speed_thresh:{}/ overspeed_number_thresh:{}/ "
                    "calibration:{} calibration_extra:{}".format(self.speed_thresh, self.overspeed_number_thresh, self.calibration, self.calibration_extra))

        self.trans_matrix = self.get_trans_matrix(
            self.calibration, self.calibration_extra)
        logger.info("SpeedingNumData Init: tran_matrix:{}".format(self.trans_matrix))

        self.target_height = 1.7
        self.history_len = 8
        self.trigger_number_thresh = 5
        self.track_dict = dict()

    def add_data(self, track_id, catch_time, detect_bbox):
        if track_id not in self.track_dict:
            # 上次更新时间、历史数据、是否超速
            self.track_dict[track_id] = [catch_time, deque(maxlen=self.history_len), False, 0]

        # 真实位置
        pix_loc = [(detect_bbox[0]+detect_bbox[1])/2.0, detect_bbox[3]]
        realword_loc = self.tran_location(pix_loc)
        # realword_loc = self.trans_matrix((detect_bbox[0]+detect_bbox[1])/2.0, detect_bbox[3])
        self.track_dict[track_id][0] = catch_time
        self.track_dict[track_id][1].append((catch_time, realword_loc))
        # 清理过期数据（半小时外）
        if time.time() - self.track_dict[track_id][0] > 30*60:
            del self.track_dict[track_id]

    def event_trigger(self, catch_time):
        ids_triggered = []
        # 在catch_time时间下事件个数
        current_num = sum(1 for i in self.track_dict.values() if i[0]==catch_time)
        for track_id, linger_data in self.track_dict.items():
            update_time, track_data, is_pushed, trigger_num = linger_data
            if len(track_data) != self.history_len or is_pushed:
                continue
            
            # 计算速度
            time_start, loc_start = track_data.popleft()
            time_end, loc_end = track_data.pop()
            current_speed = self.cal_distance(loc_end, loc_start) / (time_end - time_start + 1e-6)
            logger.debug("speednum| id:{} | speed:{:.2f} | {} {} -> {} {}".format(
                track_id, current_speed, loc_start, time_start, loc_end, time_end))
            if current_speed < self.speed_thresh:
                linger_data[3] = 0
                continue

            linger_data[3] += 1 
            if linger_data[0] == catch_time and linger_data[3]>self.trigger_number_thresh and current_num>self.overspeed_number_thresh:
                ids_triggered.append(track_id)
                linger_data[2] = True

        res = ids_triggered
        return res
    
    def get_trans_matrix(self, calibration, calibration_extra):
        use_3d = bool(calibration_extra)
        calibration_data = [float(i) for i in calibration.split(";")]
        calibration_extra_data = [float(i) for i in calibration_extra.split(
            ";")] if use_3d else None

        cali_bbox = None
        target_bbox = None

        if not use_3d:
            cali_bbox = np.array(calibration_data[:8]).reshape(
                (-1, 2)).astype(np.float32)

            L1, L2 = calibration_data[10:]
            target_bbox = np.array([[0.0, 0.0],
                                    [L1, 0.0],
                                    [L1, L2],
                                    [0.0, L2]]).astype(np.float32)
        else:
            tmp_pts = []
            calibration_extra_bbox = np.array(calibration_extra_data[:16]).reshape(
                (-1, 2)).astype(np.float32)
            L1, L2, H = calibration_extra_data[16:]
            height_ratio = 1.5/H

            for i in range(4):
                p0 = calibration_extra_bbox[2*i]
                p1 = calibration_extra_bbox[2*i + 1]

                target_point = p0 + (p1 - p0)*height_ratio
                tmp_pts.append(target_point)
            cali_bbox = np.array(tmp_pts).astype(np.float32)
            target_bbox = np.array(
                [[0.0, 0.0], [L1, 0.0], [L1, L2], [0.0, L2]]).astype(np.float32)
        logger.debug("SpeedingNumData cali_bbox:{} target_bbox:{}".format(
            cali_bbox, target_bbox))
        cali_bbox[:, 0] *= MUXER_OUTPUT_WIDTH
        cali_bbox[:, 1] *= MUXER_OUTPUT_HEIGHT
        trans_matrix = cv2.getPerspectiveTransform(cali_bbox, target_bbox)

        return trans_matrix

    def tran_location(self, point):
        u, v = point
        x = (self.trans_matrix[0][0] * u + self.trans_matrix[0][1] * v + self.trans_matrix[0][2]) / (self.trans_matrix[2][0] * u + self.trans_matrix[2][1] * v + self.trans_matrix[2][2])
        y = (self.trans_matrix[1][0] * u + self.trans_matrix[1][1] * v + self.trans_matrix[1][2]) / (self.trans_matrix[2][0] * u + self.trans_matrix[2][1] * v + self.trans_matrix[2][2])
        return x, y

    @staticmethod
    def cal_distance(p1, p2):
        return np.linalg.norm([p1[0]-p2[0], p1[1]-p2[1]])


class backImages:
    def __init__(self, max_len):
        self.table = dict()
        self.images = dict()
        for i in range(MAX_NUM_SOURCES):
            self.images[i] = deque(maxlen=max_len)
            self.table[i] = deque(maxlen=max_len)
        
    def check_exist(self, source_id, frame_num):
        if frame_num in self.table[source_id]:
            return True
        return False

    def add_image(self, source_id, frame_num, frame_copy):
        tmp_dict = dict()
        tmp_dict[frame_num] = frame_copy
        self.table[source_id].append(frame_num)
        self.images[source_id].append(tmp_dict)

    def get_frame(self, source_id, frame_num):
        tmp_deque = self.images[source_id]
        for item in tmp_deque:
            if frame_num in item:
                return item[frame_num]
        
