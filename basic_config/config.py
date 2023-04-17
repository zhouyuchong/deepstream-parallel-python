import os

# 卡夫卡（connxtion）相关配置
# kafka ip & port & topic for connextion
KAFKA_HOST = '192.168.100.203'
KAFKA_PORT = 9092
KAFKA_TOPIC_ALGORITHM = 'deepstream'

# FastDFS 配置文件路径
# FastDFS client file path for import
FastDFS_CLIENT_PATH =os.path.dirname(__file__)

PIPELINE_CLIENT_PATH =os.path.dirname(__file__)

