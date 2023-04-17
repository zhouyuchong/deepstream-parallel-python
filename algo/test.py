import time
from base.pipeline import *
from base.source import *

uri = "file:///media/test_out.mp4"
uri = "file:///media/3market_11.mp4"
rtsp_uri = ['rtsp://admin:12345@192.168.88.99:554/Streaming/Channels/101']
app = DSPipeline()


print(app.start())
id = 0
while True:
    if id == 0:

        src = ParaInferStream(id='test-{}'.format(id), uri=uri, apps=[1])
    
        app.add_src(src=src)

    # if id == 10:
    #     app.del_src('test-0')

    # if id == 20:

    #     src = ParaInferStream(id='test-{}'.format(id), uri=uri, apps=[1])
    
    #     app.add_src(src=src)
    #     time.sleep(5)
    #     app.play_src(id='test-20')

    time.sleep(1)
    id += 1