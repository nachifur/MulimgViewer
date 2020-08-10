# 一、介绍

Mulimg_viewer是多图像浏览器，在一个界面打开**多个**图像，方便图像的比较，方便的选出对比明显的**图像对**，同时可以方便的进行图像的拼接。

**输入路径**有两种模式
1. 一个文件夹下有n个子文件夹，子文件夹中为png图片
2. 单独选择每个子文件夹（名字相同时，变为名称+数字）

选择**输出的路径**，输出的文夹名称为**输入的子文件夹名称**

# 二、安装与运行
目前仅在Ubuntu18.04测试，其他版本的linux系统理论上有python3和wxpython即可运行。

安装：(python3)
推荐使用conda安装，pip安装wxpython可能会失败。
pip：
```bash
sudo apt-get install build-essential libgtk-3-dev
/usr/bin/pip3 install wxpython
```
运行：
```python
python3 main.py
```
注：
错误 Failed to open file “/home/liu/.local/share/recently-used.xbel”: 权限不够

解决：
```bash
sudo chmod 777 * -R /home/liu/.local/share
```

# 三、应用场景
例1：

在深度学习中，你可能遇到以下问题：

一个模型或者多个模型对比时，产生多个输出文件夹。你已经通过指标判断出哪个模型是最优的，这时你需要你选出相应的图像对**用于实验结果的对比**。

以前你可能需要打开多个图像，逐个对比，再到文件夹找到图像，复制到别的地方。

现在只需使用Mulimg_viewer多图像浏览器，输入各个需要对比的目录，一键保存对比图像对到本地！![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f0.png)

例2：

Mulimg_viewer可以轻松的完成纵向与横向的拼接，支持自动一键保存！
# 四、快捷键操作

下一张：Ctrl+N

上一张Ctrl+L

保存：Ctrl+S

# 五、注意事项

1. 对比的文件夹的图像命名需要一样
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

