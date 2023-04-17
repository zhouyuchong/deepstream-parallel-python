import math
from sensecam_control import onvif_control


class PTZController:
    def __init__(self, ip, user, password):
        self.__camera1_ctl__ = onvif_control.CameraControl(ip, user, password)

        self.__camera1_ctl__.camera_start()
        self.__home__ = self.__camera1_ctl__.get_ptz()

    def __relative__(self, p, t, z):
        self.__camera1_ctl__.relative_move(p, t, z)

    def __absolute__(self, p, t, z):
        self.__camera1_ctl__.absolute_move(p, t, z)

    # 移动到指定PTZ
    def set_ptz(self, p, t, z):
        self.__camera1_ctl__.absolute_move(p, t, z)

    # 获取当前PTZ
    def get_ptz(self):
        return self.__camera1_ctl__.get_ptz()

    # 停止移动
    def stop_move(self):
        return self.__camera1_ctl__.stop_move()

    # 移动到初始PTZ
    def go_home(self):
        self.__absolute__(self.__home__[0], self.__home__[1], self.__home__[2])

    # 获取初始PTZ
    def get_home(self):
        return self.__home__

    @staticmethod
    def delta_cal(frame_w, frame_h, x1, y1, x2, y2, max_zoom, pre_zoom_rate, rate):
        target_x = (x1+x2)/2.0
        target_y = (y1+y2)/2.0
        pre_zoom_rate = 1/max_zoom if pre_zoom_rate == 0 else pre_zoom_rate
        ab_pre_zoom = pre_zoom_rate*max_zoom
        box_w = x2 - x1
        absolute_zoom = frame_w/box_w/rate
        delta_z = (absolute_zoom * (pre_zoom_rate * max_zoom)+1) / max_zoom
        delta_z = 1 if delta_z > 1 else delta_z

        y_degree = math.atan((target_y - frame_h / 2.0) / (frame_h / 2.0) *
                             math.tan(21.8 / 180 * math.pi)) * 180 / math.pi / 45 / ab_pre_zoom
        z_degree = math.atan((target_x - frame_w / 2.0) / (frame_w / 2.0)
                             * math.tan(29.15 / 180 * math.pi)) / math.pi/ab_pre_zoom
        return z_degree, y_degree, delta_z

    def go_to(self, frame_w, frame_h, x1, y1, x2, y2, max_zoom, present_p, present_t, present_z, rate, mark):
        delta_p, delta_t, delta_z = self.delta_cal(
            frame_w, frame_h, x1, y1, x2, y2, max_zoom, present_z, rate)
        p = present_p + delta_p
        t = present_t + delta_t
        if p < -1:
            p += 2
        if p > 1:
            p -= 2
        if t < -1:
            t = -1
        if t > 1:
            t = 1
        z = delta_z

        if (present_p, present_t, present_z) == (p, t, z):
            return
        if mark:
            self.__absolute__(p, t, z)
        else:
            self.__absolute__(p, t, present_z)
