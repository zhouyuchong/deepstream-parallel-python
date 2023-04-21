import time
from base.pipeline import *
from base.source import *

uri = ["file:///media/test_out.mp4", "file:///media/3market_11.mp4", "file:///media/3market_22.mp4"] 
rtsp_uri = ['rtsp://admin:12345@192.168.88.99:554/Streaming/Channels/101', 'rtsp://admin:sh240@192.168.1.240:554/h264/ch1/main/av_stream', 'rtsp://admin:sh123456@192.168.1.234:554/h264/ch1/main/av_stream']
app = DSPipeline()


print(app.start())
id = 0
while True:
    if id == 0:
        src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[0], apps=[1])
        app.add_src(src=src)

    if id == 10:
        src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[1], apps=[0, 1])
        app.add_src(src=src)


    if id == 15:
        src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[2], apps=[0])
        app.add_src(src=src)

    if id == 20:
        app.del_src(id="test-0")

    if id == 25:
        src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[0], apps=[1])
        app.add_src(src=src)
        time.sleep(4)
        app.play_src(id="test-25")
        


    time.sleep(1)
    id += 1