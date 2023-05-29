import time
from base.pipeline import *
from base.source import *
from app.pv_behavior.general_camera import *

uri = ["file:///media/test_out.mp4", "file:///media/3market_11.mp4", "file:///media/3market_22.mp4"] 
rtsp_uri = ['rtsp://admin:12345@192.168.88.99:554/Streaming/Channels/101', \
            'rtsp://admin:sh123456@192.168.1.240:554/h264/ch1/main/av_stream', \
                'rtsp://admin:sh123456@192.168.1.234:554/h264/ch1/main/av_stream', \
                    'rtsp://admin:sh123456@192.168.1.237:554/h264/ch1/main/av_stream']
app = DSPipeline()

p1 = dict()
park1 = {'ptz1': '0.1;0.1;0.9;0.1;0.9;0.9886;0.2;0.9829;0.1;0.1714'}
p1['ptz_id'] = '1'
p1['ptz'] = ''
p1['coordinate'] = park1


itime = 0.5

print(app.start())
id = 0
while True:
    if id == 0:
        ptz_params = [p1]
        src = GeneralCamera(id='test-{}'.format(id), uri=rtsp_uri[1], apps=[1], linger_time_thresh=itime, ptz_params=ptz_params)
        app.add_src(src=src)
        src.thread_start()
        # file_name = src.update_ptz_params(ptz_params=ptz_params)
        # print("file name:  ", file_name)
        app.set_analytics(appid=1, id='test-0', type=2, data=ptz_params[0]['coordinate'])


    # if id == 10:
    #     src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[2], apps=[0])
    #     app.add_src(src=src)


    # if id == 15:
    #     src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[3], apps=[0])
    #     app.add_src(src=src)

    # if id == 20:
    #     ptz_params = [p1]
    #     src = GeneralCamera(id='test-{}'.format(id), uri=rtsp_uri[0], apps=[1], linger_time_thresh=itime, ptz_params=ptz_params)
    #     app.add_src(src=src)
    #     src.thread_start()
    #     # file_name = src.update_ptz_params(ptz_params=ptz_params)
    #     # print("file name:  ", file_name)
    #     app.set_analytics(appid=1, id='test-20', type=2, data=ptz_params[0]['coordinate'])

    # if id == 20:
    #     app.del_src(id="test-0")

    # if id == 25:
    #     src = ParaInferStream(id='test-{}'.format(id), uri=rtsp_uri[0], apps=[1])
    #     app.add_src(src=src)
    #     time.sleep(4)
    #     app.play_src(id="test-25")
        


    time.sleep(1)
    id += 1