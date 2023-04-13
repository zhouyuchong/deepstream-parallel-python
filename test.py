import time
from base.pipeline import *
from base.source import *

uri = "file:///media//test_out.mp4"
rtsp_uri = ['rtsp://admin:12345@192.168.88.99:554/Streaming/Channels/101']
app = DSPipeline()


print(app.start())
id = 0
while True:
    if id == 0:
        src = ParaInferStream(id='test', uri=rtsp_uri[0], apps=[0, 1])
        # src = ParaInferStream(id='test', uri=uri, apps=[0])
        app.add_src(src=src)
        # time.sleep(10)
        # app.play_src('test')

    # if id == 10:
    #     app.play_src('test')

    if id == 10:
        src = ParaInferStream(id='test-1', uri=rtsp_uri[0], apps=[1])
        app.add_src(src=src)
        time.sleep(5)
        app.play_src('test-1')
    # if id == 20:
    #     print("================adddd")
    #     src = ParaInferStream(id='test-3', uri=uri, apps=[0])
    #     app.add_src(src=src)
    
    
    id += 1
    time.sleep(1)