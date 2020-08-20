# 一、介绍

Mulimg_viewer是**多图像**浏览器，在一个界面查看多个图像，方便图像的比较，方便的选出对比明显的**图像对**，同时可以方便的进行**图像的拼接**。

下载地址：https://github.com/nachifur/Mulimg_viewer/releases/tag/v1.1

测试图像地址：https://github.com/nachifur/Mulimg_viewer/blob/master/img/test_img.zip

目前处于测试阶段，需要改进的部分或者bug可以告诉我。邮箱：nachifur@mail.ustc.edu.cn

# 二、安装与运行
提供Ubuntu和Windows的包（amd64）。其他环境可以使用源码运行。建议使用Python3.6以上。
## ubuntu
### 1
安装：
推荐使用conda安装，pip安装wxpython可能会失败。
pip：
```bash
sudo apt-get install build-essential libgtk-3-dev
/usr/bin/pip3 install wxpython pillow pytest-shutil
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
### 2
目前已经发布一个deb包（release中可以找到），在Ubuntu18.04(amd64)测试可用，安装之后运行：
```bash
/etc/Mulimg_viewer/main
```
这个不含测试图像，可以从code中直接下载。
## Windows
目前已经打包一个exe，已经在win10下测试。也可以下载源码运行`main.py`。
# 三、应用场景
## 例1：

在深度学习中，你可能遇到以下问题：一个模型或者多个模型对比时，产生多个输出文件夹。如果你已经通过指标判断出哪个模型是最优的，你需要你选出相应的*图像对***用于实验结果的对比**。

**以前**你可能需要打开多个图像，逐个对比，再到文件夹找到图像，复制到别的地方。

**现在**只需使用Mulimg_viewer多图像浏览器，输入各个需要对比的目录，**一键保存对比图像对到本地**！


## 例2：

Mulimg_viewer可以轻松的完成纵向与横向的拼接，**支持自动拼接保存**！![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f0.jpg)
# 四、操作流程与快捷键操作

## 1 操作流程
1. 在**Setting中填写布局参数**：num per row（一行有几张图片）, num per img（一个图片由几个子图片组成）, num per column（一列有几个图片）
2. File->Input path，选择**输入模式**（3种）

    2.1. Sequential: 一个文件夹多张图片。

    2.2. Parallel auto: 一个文件夹多个子文件夹。一个文件夹下有n个子文件夹，子文件夹中为图片。

    2.3. Parallel manual: 手动选择多个子文件夹。

3. 这时图片显示在面板，可以使用**next、last**查看下一张，上一张图片
4. File->Out path, **选择输出的路径**。输出的文夹名称为输入的子文件夹名称。子文件夹名字相同时，保存时变为名称+数字。

**输入模式**：

**1是多图拼接模式**，一个文件夹下有不同的图片，命名不同，用于这些图片的拼接。

**2和3是多图浏览模式**，需要确保各子文件夹下面的图片命名相同，用于不同图片的对比。

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f1.jpg)

**输出模式**：

Stitch: 在**图像拼接**时使用，将拼接的图像保存到*stitch_images*目录下

select: 在**图像挑选**时使用，分别保存当前浏览的图像到不同的文件夹

Both: 同时保存

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f2.jpg)

**图像尺寸归一化**

Fill: 图像尺寸为一组图像中的最大尺寸，填充模式

Crop: 图像尺寸为一组图像中的最小尺寸，裁剪模式

Resize: 图像尺寸为一组图像中的平均尺寸，缩放模式

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f3.jpg)

## 2 快捷键
下一张：Ctrl+N

上一张Ctrl+L

保存：Ctrl+S

使用键盘的上下左右，可以移动图像面板里的图像。

# 五、注意事项

1. 使用多图浏览模式（输入路径为模式1和2），对比的文件夹里面的图像命名需要一样！
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

# 六、许可证
https://www.gnu.org/licenses/gpl-3.0.en.html

