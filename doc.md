视频分析平台-并行版

多路视频
模型并行推理
配置文件调用

配置文件应该在最外层，方便修改

接口调用
新的接口应该长这个样子：
url, params, 需要推理的模型[0, 1, 2, 3, ...]

base:
pipeline，现在只有一条pipeline，所以不再需要虚函数来每个app继承

每个app特有的只有parallel infer bin里面的东西