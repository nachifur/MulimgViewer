# Mulimg viewer
## 1. 介绍

Mulimg_viewer是**多图像**浏览器，在一个界面查看多个图像，方便图像的比较，方便的选出对比明显的**图像对**，同时可以方便的进行**图像的拼接**。

下载地址：https://github.com/nachifur/Mulimg_viewer/releases/tag/v2.1

测试图像地址：https://github.com/nachifur/Mulimg_viewer/blob/master/img/test_img.zip

目前处于测试阶段，需要改进的部分或者bug可以告诉我。邮箱：nachifur@mail.ustc.edu.cn

## 2. ubuntu
提供Ubuntu和Windows的包（amd64）。其他环境可以使用源码运行。建议使用Python3.6以上。
### 2.1
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
### 2.2
目前已经发布一个deb包（release中可以找到），在Ubuntu18.04(amd64)测试可用，安装之后运行：
```bash
/etc/Mulimg_viewer/main
```
这个不含测试图像，可以从code中直接下载。

## 3. Windows
目前已经打包一个exe，已经在win10下测试。也可以下载源码运行`main.py`。

## 4. 应用场景
### 例1：

在深度学习中，你可能遇到以下问题：一个模型或者多个模型对比时，产生多个输出文件夹。如果你已经通过指标判断出哪个模型是最优的，你需要你选出相应的*图像对***用于实验结果的对比**。

**以前**你可能需要打开多个图像，逐个对比，再到文件夹找到图像，复制到别的地方。

**现在**只需使用Mulimg_viewer多图像浏览器，输入各个需要对比的目录，**一键保存对比图像对到本地**！


### 例2：

Mulimg_viewer可以轻松的完成纵向与横向的拼接，**支持自动拼接保存**！![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f0.jpg)
## 5. 使用说明

## 5.1 操作流程
1. 在**Setting中填写布局参数**：row（一行有几张图片）, num per img（一个图片由几个子图片组成）, col（一列有几个图片）
2. File->Input path，选择**输入模式**（3种）

    2.1. Sequential: 一个文件夹多张图片。

    2.2. Parallel auto: 一个文件夹多个子文件夹。一个文件夹下有n个子文件夹，子文件夹中为图片。

    2.3. Parallel manual: 手动选择多个子文件夹。

3. 这时图片显示在面板，可以使用**next、last**查看下一张，上一张图片
4. File->Out path, **选择输出的路径**。输出的文夹名称为输入的子文件夹名称。子文件夹名字相同时，保存时变为名称+数字。

## 5.2 快捷键
输入路径：

    Sequential: Ctrl+E

    Parallel auto: Ctrl+A

    Parallel manual: Ctrl+M

输出路径：Ctrl+O

下一张：Ctrl+N

上一张Ctrl+L

保存：Ctrl+S

刷新：Ctrl+R

使用键盘的上下左右，可以移动图像面板里的图像。

## 5.3 功能介绍

### 5.3.1 输入模式

1是**串行浏览**模式，一个文件夹下有不同的图片，命名不同，用于这些图片的拼接。

2和3是**并行浏览**模式，需要确保各子文件夹下面的图片命名相同，用于不同图片的对比。

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f1.jpg)

### 5.3.2  输出模式：

Stitch: 在**图像拼接**时使用，将拼接的图像保存到*stitch_images*目录下

select: 在**图像挑选**时使用，分别保存当前浏览的图像到不同的文件夹

Both: 同时保存

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f2.jpg)

### 5.3.3 图像排列自动化

默认：num per img = -1，这时为程序**自动布局模式**。num per img 的意思是几张图像合成一个图像。

### 5.3.4 取消图像排列自动化
当num per img = 1或者>1，图像布局为**手动模式**，这时可以调整 row 和 col。

### 5.3.5 自动保存

勾选自动保存，点击保存💾️

### 5.3.6 图像尺寸归一化

Fill: 图像尺寸为一组图像中的最大尺寸，填充模式(保持原始像素分辨率)

Crop: 图像尺寸为一组图像中的最小尺寸，裁剪模式(保持原始像素分辨率)

Resize: 图像尺寸为一组图像中的平均尺寸，缩放模式(不保持原始像素分辨率)

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f3.jpg)

### 5.3.7 图像间隔

gap值可以控制间距x,y方向的间距。可以使用**负数**，这时可以达到**覆盖重叠**的效果。

### 5.3.8 图像填充

支持多种颜色填充。支持背景填充**透明**。**同时支持前景透明度调节**。

## 6. 注意事项

1. 使用多图浏览模式（输入路径为模式1和2），对比的文件夹里面的图像命名需要一样！
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

## 7. 许可证
https://www.gnu.org/licenses/gpl-3.0.en.html

## 8. 未来增强功能
感谢各位提供意见！大家可以在issues中发表意见，采用的会致谢大家！如果大家希望可以和我一起合作开发，请联系我！
- [x] 增加精确定位（目前已经有slider）
- [x] 增加图片索引查看，方便进行精确定位
- [ ] 并行的局部放大功能（用于论文中的对比实验图片**急需！**）
- [ ] 输入方式，新增：路径文件的导入和存储（@nothingeasy提供改进意见）
- [ ] 增加删除功能（完善筛选功能）
- [ ] 任意图像数量的多模板拼图，每个图点击后可旋转，平移
- [ ] 用于图像分类标注？
## 9. 致谢
nothingeasy:改进意见-(输入方式，新增：路径文件的导入和存储)
## 10. 引用
如果您在研究中使用此项目，请使用以下BibTeX条目。
```
@misc{Mulimgviewer2020,
  author =       {Jiawei Liu},
  title =        {{Mulimg viewer: A multi-image viewer for image comparison and image stitching}},
  howpublished = {\url{https://github.com/nachifur/Mulimg_viewer}},
  year =         {2020}
}
