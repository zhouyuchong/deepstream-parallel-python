"""
通用摄像头，source

GeneralCamera |- CameraController(PTZ轮巡控制)
              |- EventManager（事件分析）  |- LingerEvent（逗留） ~ LingerData（逗留最小单位数据）
                                        |- SpeedEvent
                                        |- ...

GeneralCamera绑定唯一的控制器、事件管理器
主要功能：
    1、接收pipeline处理的基础数据，吐出事件消息
    2、启停控制
    3、更新analytic配置信息
"""
import re

from loguru import logger

from kbds.core.source import Stream
from kbds.app.pedestrian_vehicle.utils import modify_analytics_roi, modify_analytics_dir
from kbds.app.pedestrian_vehicle.camera_controller import CameraController
from kbds.app.pedestrian_vehicle.event_manager import EventManager, LingerEvent
from kbds.app.pedestrian_vehicle import config


class GeneralCamera(Stream):
    def __init__(self, id, uri, **kwargs) -> None:
        """
        :param id: str, source id
        :param uri: str, stream uri
        :param kwargs:
            username: str, camera username
            password: str, camera password
        """
        super().__init__(id, uri, **kwargs)
        
        reg = re.compile('^(?P<uri_mode>[^ ]*)://(?P<user>[^ ]*):(?P<passwd>[^"]*)@'
                         '(?P<ip>[^ ]*):(?P<port>[^ ]*)/(?P<uri_head>[^"]*)')
        match_info = reg.match(uri)
        self.ip = match_info['ip'] if match_info else None
        self.user = match_info['user'] if match_info else None
        self.passwd = match_info['passwd'] if match_info else None
        self.ptz_params = kwargs['ptz_params']

        # ptz控制器
        self._controller = CameraController(self.ip, self.user, self.passwd, self.ptz_params)
        # 事件管理器
        self._manager = EventManager(**kwargs)
        logger.debug("GeneralCamera | inited.")

    def get_current_state(self):
        return self._controller.get_current_state()

    def thread_start(self):
        self._controller.start()
        self._manager.start()
        logger.debug("GeneralCamera id:{} | controller&manager start.".format(self.id))

    def thread_stop(self):
        self._controller.stop()
        self._manager.stop()
        logger.debug("GeneralCamera id:{} | controller&manager stop.".format(self.id))

    def thread_restart(self):
        self._controller.restart()
        self._manager.restart()
        logger.debug("GeneralCamera id:{} | controller&manager start.".format(self.id))

    def feed_data(self, data):
        self._manager.feed_data(data)
        # logger.debug("GeneralCamera id:{} eat data from ptz:{}.".format(self.id, data.ptz_id))

    def pop_events(self):
        # logger.debug("GeneralCamera id:{} pop events.".format(self.id))
        return self._manager.pop_events()

    def update_ptz_params(self, ptz_params):
        if [True for i in ptz_params if 'coordinate' in i]:
            modify_analytics_roi(config.ANALYTICS_CONFIG_FILE, config.MAX_NUM_SOURCES,
                                 self.idx, 1, ptz_params, 0)
            logger.debug("GeneralCamera id:{} modify_analytics_roi done.".format(self.id))
        if [True for i in ptz_params if 'direction' in i]:
            modify_analytics_dir(config.ANALYTICS_CONFIG_FILE, config.MAX_NUM_SOURCES,
                                 self.idx, 1, ptz_params)
            logger.debug("GeneralCamera id:{} modify_analytics_dir done.".format(self.id))
        return config.ANALYTICS_CONFIG_FILE


