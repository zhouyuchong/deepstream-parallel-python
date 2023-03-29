# Deepstream parallel DEMO
## Reference 
+ [deepstream parallel inference](https://github.com/NVIDIA-AI-IOT/deepstream_parallel_inference_app)
+ [deepstream demux](https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/tree/master/apps/deepstream-demux-multi-in-multi-out)

## TODO
Fail to use multi `streamdemux`. Only the first branch could recieve and infer data. Reason Unknow. Maybe some configs are wrong with other `streamdemux` or `streammux`.

## Solution
Instead of **multi streamdemux**, try to use **multi tee**. Link a tee to `streamdemux` for every `src pad`. 

## Usage
```
python3 deepstream_parallel.py -i file:///path/to/file file:///path/to/file ...
```