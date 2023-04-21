import re
import json
import time
from loguru import logger


def error_parse_call(message, srcm, producer):
    err, debug = message.parse_error()
    # logger.debug("error: {}: {}".format(err, debug))
    
    if 'Option not supported (551)' in str(debug):
        logger.error("\n该设备不支持暂停操作, 可能是海康摄像头?\nPAUSE signal is not supported on this camera, maybe hikvision?")
        return True, None
    # This error no effect
    elif 'Could not send message. (Generic error)' in str(debug):
        return True, None
    elif 'Failed to connect. (Generic error)' in str(debug):
        logger.warning("Uridecodebin failed to connect to server. Could be ignored?")
        return True, None
    else:
        logger.error("Unknown error, will delete and send message.")

        struct = str(message.get_structure())
        search_index = re.search("source-bin-[0-9]{0,1}/", struct)
        search_index = int(search_index[0].split('-')[2][:-1])

        try:
            err_id = srcm.get_id_by_idx(search_index)
            # err_url = self.srcm.get_url_by_idx(search_index)
            logger.warning("id: {} | encounters error: {}.".format(err_id, err))
        except Exception as e:
            logger.warning("source: {} didn't exist: {}".format(search_index, e))
            return
        
        time_local = time.localtime(int(time.time()))
        dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
        msg = {"time": dt, "type": "normal", "id": str(err_id), "error":str(err), "debug": debug}
        msg = json.dumps(msg).encode('utf-8')
        producer.send('errsor', msg)
        return True, err_id

        # if str(err).startswith("gst-resource-error-quark") or str(err).startswith("gst-stream-error-quark"):
        #     # resource errors from 1 to 16
        #     if str(err).endswith("(9)"):
        #         # handle_read_error()
        #         logger.warning("source: {} | error: {}".format(search_index, err))
        #     else:
        #         producer.send('errsor', msg)
        #         logger.warning("id: {} will be deleted.".format(err_id))
                # try:
                #     del_src(id=err_id)
                # except Exception:
                #     logger.error("消息总线中: 删除资源时发生错误. id: {} | encounters error: {} while delete.".format(err_id, err))


def eos_parse_call(message, srcm, producer):
    struct = message.get_structure()
    # Check for stream-eos message
    if struct is not None and struct.has_name("stream-eos"):
        parsed, stream_id = struct.get_uint("stream-id")
        if parsed:
            # Set eos status of stream to True, to be deleted in delete-sources
            logger.info("Got EOS from stream-{}".format(stream_id))
            eos_id = srcm.get_id_by_idx(stream_id)
            if eos_id:
                time_local = time.localtime(int(time.time()))
                dt = time.strftime("%Y-%m-%d %H:%M:%S",time_local)
                msg = {"time": dt, "type": "normal", "id": str(eos_id), "error":"EOS", "debug": ""}
                msg = json.dumps(msg).encode('utf-8')
                producer.send('error', msg)
                return True, eos_id
                # try:
                #     self.del_src(id=eos_id)
                # except Exception:
                #     logger.error("消息总线中: 删除资源时发生错误. id: {} encounters e while delete.".format(eos_id))
    else:
        return True, None