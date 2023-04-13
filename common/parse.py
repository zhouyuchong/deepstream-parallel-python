import configparser
import json
from loguru import logger
import sys
sys.path.append('../')


APP_LIST = {0:"face", 1:"behavior"}



def parse_config_pipeline(config_path):   
    if not config_path:
        logger.error("请指定配置文件路径.")
        return False, "No config specify."
    config = configparser.ConfigParser()
    config.read(config_path)
    config.sections()
    for key in config['inference']:
        if key == 'app-activated' :
            activated_apps = json.loads(config.get("inference", key))
            if not activated_apps:
                logger.error("需要指明激活的应用.")
                return False, None, None

            logger.info("Activated Apps: {}".format(activated_apps))
    
    for key in config['kafka-pipeline']:
        if key == 'ip':
            kafka_ip = config.get("kafka-pipeline", key)
            if not kafka_ip:
                logger.error("未设置kafka 参数.")
                return False, None, None
        if key == 'port':
            kafka_port = config.get("kafka-pipeline", key)
            if not kafka_port:
                logger.error("未设置kafka 参数.")
                return False, None, None
            
    kafka_conn_str = ":".join([kafka_ip, kafka_port])
    logger.info("Kafka of Pipeline message bus: {}".format(kafka_conn_str))

    return True, activated_apps, kafka_conn_str

def set_property_pipeline(config_path, streammux):
    if not config_path:
        logger.error("请指定配置文件路径.")
        return False, "No config specify."
    config = configparser.ConfigParser()
    config.read(config_path)
    config.sections()

    for key in config['streammux']:
        if key == 'batch-push-timeout':
            batch_push_timeout = config.getint('streammux', key)
            streammux.set_property("batched_push_timeout", batch_push_timeout)
        if key == 'batch-size':
            batch_size = config.getint('streammux', key)
            streammux.set_property("batch_size", batch_size)
        # if key == 'nvbuf-memory-type':
        #     mem_type = config.getint('streammux', key)
        #     streammux.set_property("nvbuf-memory-type", mem_type)
        if key == 'width':
            streammux_width = config.getint('streammux', key)
            streammux.set_property("width", streammux_width)
        if key == 'height':
            streammux_height = config.getint('streammux', key)
            streammux.set_property("height", streammux_height)
        if key == 'gpu-id':
            gpu_id = config.getint('streammux', key)
            streammux.set_property("gpu_id", gpu_id)
            streammux.set_property("live-source", 1)

    return batch_size, gpu_id


    
