"""
camera_controller
控制器与GeneralCamera绑定，一个GeneralCamera（或者称为source）实例存在唯一的CameraController

控制器线程负责根据预设的凝视时间轮巡所有巡逻点
"""

import time
from threading import Thread
from collections import deque, namedtuple
from abc import ABC, abstractmethod

from loguru import logger

from .ptz_controller import PTZController


class MoveState:
    Ready = "READY"
    Stop = "STOP"
    Move = "MOVE"


PTZ_DATA = namedtuple("PTZ_DATA", ['ptz_id', 'ptz'])
CAM_STATE = namedtuple("CAM_STATE", ['state', 'ptz_data'])


class BaseController(ABC, Thread):
    def __init__(self):
        super(BaseController, self).__init__()
        self.patrollers = []

    def add_patrollers(self, ptz_params):
        """
        原有patrollers基础上添加巡逻点
        @param ptz_params:
        @return:
        """
        ptz_data = self.extract_params(ptz_params)
        self.patrollers.extend(ptz_data)

    def clean_patrollers(self):
        self.patrollers.clear()

    def update_patrollers(self, ptz_params):
        """
        替换原有patrollers
        @param ptz_params:
        @return:
        """
        self.clean_patrollers()
        self.add_patrollers(ptz_params)

    @staticmethod
    def extract_params(ptz_params):
        return [PTZ_DATA(i['ptz_id'], i['ptz']) for i in ptz_params]

    @abstractmethod
    def run(self):
        """
        控制器按巡逻点位轮巡
        @return:
        """
        pass

    @abstractmethod
    def stop_controller(self):
        """
        控制器停止巡逻点位轮巡
        @return:
        """
        pass

    @abstractmethod
    def get_current_state(self):
        """
        获取控制器当前状态
        @return: state， ptz_data
        """
        pass


class GunController(BaseController):
    def __init__(self):
        super(GunController, self).__init__()

    def run(self):
        pass

    def stop_controller(self):
        pass

    def get_current_state(self):
        if not self.patrollers:
            logger.error("GunController | patrollers empty")

        return CAM_STATE(MoveState.Stop, self.patrollers[0])


class BallController(BaseController):
    def __init__(self, ip, user, passwd):
        super(BallController, self).__init__()
        self.ptz_deque = deque(maxlen=30)
        # 每个点位凝视时间
        self.stare_time = 30

        self.moving_flag = MoveState.Ready
        self.ptz_data_now = None

        self._active = True
        self._controller = PTZController(ip, user, passwd)

    def run(self):
        while self._active:
            if not self.ptz_deque:
                self.ptz_deque.extend(self.patrollers)

            self.ptz_data_now = self.ptz_deque.pop()
            ptz_data = [float(i) for i in self.ptz_data_now.ptz.split(',')]

            self.moving_flag = MoveState.Move
            self._controller.set_ptz(*ptz_data)
            logger.debug("camera state id:{} | {} {}".format(self.ptz_data_now.ptz_id, self.moving_flag,
                                                             self.ptz_data_now.ptz))
            time.sleep(3)
            self.moving_flag = MoveState.Stop
            logger.debug("camera state id:{} | {} {}".format(self.ptz_data_now.ptz_id, self.moving_flag,
                                                             self.ptz_data_now.ptz))
            time.sleep(self.stare_time)

    def stop_controller(self):
        self._active = False

    def get_current_state(self):
        return CAM_STATE(self.moving_flag, self.ptz_data_now)


class CameraController:
    def __init__(self, ip, user, passwd, ptz_params):
        # 是否支持ptz控制
        self.ptz_params = ptz_params
        self.is_ptz_enabled = '' not in [i['ptz'] for i in ptz_params]
        self.ip = ip
        self.user = user
        self.passwd = passwd
        self.target_controller = BallController(ip, user, passwd) if self.is_ptz_enabled else GunController()
        self.target_controller.update_patrollers(ptz_params)
        logger.info("CameraController | inited.\nip: {} | user: {} | passwd: {} \nptz_params:\n{}.".format(ip, user, passwd, ptz_params))

    def start(self):
        """
        控制器开始轮巡
        @return:
        """
        logger.debug("CameraController |  controller start.")
        self.target_controller.start()

    def stop(self):
        """
        控制器结束
        @return:
        """
        logger.debug("CameraController |  controller stop.")
        if self.target_controller:
            try:
                self.target_controller.stop_controller()
                self.target_controller = None
            except Exception as e:
                logger.error(e)

    def restart(self):
        self.target_controller = BallController(self.ip, self.user, self.passwd) if self.is_ptz_enabled else GunController()
        self.target_controller.update_patrollers(self.ptz_params)
        
        self.target_controller.start()
        logger.debug("CameraController |  controller restart.")


    def add_patrollers(self, ptz_params):
        """
        在原有巡逻点基础上添加巡逻点位
        @param ptz_params:
        @return:
        """
        self.target_controller.add_patrollers(ptz_params)

    def update_patrollers(self, ptz_params):
        """
        更新巡逻点位（清理已有巡逻点）
        @param ptz_params:
        @return:
        """
        self.target_controller.update_patrollers(ptz_params)

    def get_current_state(self):
        """
        获取当前控制器状态
        @return: status， ptz_data
            示例：“MOVE”， PTZ_DATA('1&2&3', "0.8,0.9,0.12")
        """
        return self.target_controller.get_current_state()


if __name__ == "__main__":
    ptz_info = ['192.168.88.99', 'admin', '12345']
    ptz_params = [
        {
            'ptz_id': '1',
            'ptz': '-0.9,-0.7,0',
        },
        {
            'ptz_id': '2',
            'ptz': '-0.6,-0.6,0.1',
        }
    ]

    normal_info = ['192.168.1.240', 'admin', 'sh240']
    normal_params = [
        {
            'ptz_id': '1',
            'ptz': '',
        },
    ]
    camera = CameraController(*ptz_info, ptz_params)
    camera.start()
    logger.info("thread start.")
    for i in range(20):
        logger.info("current state: {}".format(camera.current_state))
        time.sleep(1)
    camera.stop()
    logger.info("thread stoped.")


