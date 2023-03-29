# Deepstream parallel DEMO
## Reference 
+ [deepstream parallel inference](https://github.com/NVIDIA-AI-IOT/deepstream_parallel_inference_app)
+ [deepstream demux](https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/tree/master/apps/deepstream-demux-multi-in-multi-out)

## TODO
暂时未解决多个streamdemux连同一个tee后，除了第一个demuxer，其他demuxer都没有视频流。
新的解决办法：使用一个demuxer，在demuxer后面每一路都接tee，streammux再和tee进行连接。

## Demo
单pipelin单模型(yolov5)
```
python3 single_gie.py -i file:///path/to/file file:///path/to/file ...
```
单pipeline并行模型(yolov5和retinaface)
```
python3 deepstream_parallel.py -i file:///path/to/file file:///path/to/file ...
```