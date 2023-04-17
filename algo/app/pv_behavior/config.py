"""
当前应用所需的所有通用配置
"""
import os

GPU_ID = 0
MAX_NUM_SOURCES = 16
MUXER_OUTPUT_WIDTH = 1920
MUXER_OUTPUT_HEIGHT = 1080
TILED_OUTPUT_WIDTH = 1920
TILED_OUTPUT_HEIGHT = 1080
MAX_TIME_STAMP_LEN = 32

DETECT_OBJECTS = [0, 2]

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ANALYTICS_CONFIG_FILE = os.path.join(ROOT_DIR, '../configs/pedestrian_vehicle/config_nvdsanalytics.txt')
ANALYTICS_CONFIG_FILE = "/opt/nvidia/deepstream/deepstream-6.1/samples/configs/deepstream-app/config_nvanalytics.txt"
KAFKA_LIB = "/opt/nvidia/deepstream/deepstream-6.1/lib/libnvds_kafka_proto.so"
YOLO_PLUGIN_LIB = "/opt/models/yolov7/libmyplugins.so"
