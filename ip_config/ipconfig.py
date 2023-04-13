import os

# 卡夫卡相关配置
KAFKA_HOST = '192.168.100.203'
KAFKA_PORT = 9092
KAFKA_TOPIC_ALGORITHM = 'deepstream'

# FastDFS相关配置
# CLIENT_PATH = '/opt/nvidia/deepstream/deepstream-6.1/sources/video_analysis_platform/common/'
CLIENT_PATH =os.path.dirname(__file__)