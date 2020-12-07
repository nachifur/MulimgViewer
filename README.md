# Mulimg viewer
## 1. 介绍

Mulimg_viewer是**多图像**浏览器，在一个界面查看多个图像，方便图像的比较，方便的选出对比明显的**图像对**，同时可以方便的进行**图像的拼接**。

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f6.gif)

下载地址：https://github.com/nachifur/Mulimg_viewer/releases

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
### 例1：并行浏览、挑选、保存

**以前**你可能需要打开多个图像，逐个对比，再到文件夹找到图像，复制到别的地方。

**现在**只需使用Mulimg_viewer多图像浏览器，输入各个需要对比的目录，**一键保存对比图像对到本地**！


### 例2：并行放大

Mulimg_viewer可以轻松的完成纵向与横向的拼接，**支持自动拼接保存，支持并行放大**！

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f0.jpg)

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f7.jpg)

### 例3：数据库浏览、成对数据
浏览一个1000张图片的数据库，需要多长时间？一次显示100张，只需点击10次即可完成！同样Mulimg_viewer可以方便的进行成对的数据的浏览、比较。

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f8.jpg)



## 5. 使用说明

## 5.1 操作流程
1. 在**Setting中填写布局参数**：row（一行有几张图片）, num per img（一个图片由几个子图片组成）, col（一列有几个图片）
2. File->Input path，选择**输入模式**

    2.1. Sequential: 一个文件夹多张图片。

    2.2. Parallel auto: 一个文件夹多个子文件夹。一个文件夹下有n个子文件夹，子文件夹中为图片。

    2.3. Parallel manual: 手动选择多个子文件夹。

    2.4. Image file list： 从文件导入图片列表文件

3. 这时图片显示在面板，可以使用**next、last**查看下一张，上一张图片
4. File->Out path, **选择输出的路径**。输出的文夹名称为输入的子文件夹名称。子文件夹名字相同时，保存时变为名称+数字。

## 5.2 快捷键
输入路径：

    Sequential: Ctrl+E

    Parallel auto: Ctrl+A

    Parallel manual: Ctrl+M

    Image file list: Ctrl+F


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

4是**自定义模式**，从txt, csv文件导入图片列表。支持csv文件多行多列显示。需要自动排布，`Num per img`设为-1。

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f1.jpg)

### 5.3.2  输出模式：

Stitch: 将拼接的图像保存到*stitch_images*目录下

Select: 分别保存当前浏览的图像到不同的文件夹，默认为copy模式，选中`Move file`为剪切模式。

Magnifer: 单独保存放大图像，方便用户的后期处理。

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f2.jpg)

### 5.3.3 图像排列自动化

默认：`Num per img` = -1，这时为程序**自动布局模式**。`Num per img` 的意思是几张图像合成一个图像。

### 5.3.4 取消图像排列自动化

当`num per img` = 1或者>1，图像布局为**手动模式**，这时可以调整 `row` 和 `col`。

### 5.3.5. 并行模式下的串行显示

此时需要选中`Parallel+Sequential`，可以同时显示文件夹1-12的前n张图片，n可由`Num per img`设定。


### 5.3.6 自动保存

勾选自动保存，点击保存💾️

### 5.3.7 图像尺寸归一化

Fill: 图像尺寸为一组图像中的最大尺寸，填充模式(保持原始像素分辨率)

Crop: 图像尺寸为一组图像中的最小尺寸，裁剪模式(保持原始像素分辨率)

Resize: 图像尺寸为一组图像中的平均尺寸，缩放模式(不保持原始像素分辨率)

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f3.jpg)

### 5.3.8 图像间隔

`gap`值可以控制间距x,y方向的间距。可以使用**负数**，这时可以达到**覆盖重叠**的效果。

### 5.3.9 图像填充

支持多种颜色填充。支持背景填充**透明**。**同时支持前景透明度调节**。

### 5.3.10 并行手动模式支持路径导入保存

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f4.jpg)

### 5.3.11 显示、输出尺寸独立

此功能可以保证显示的scale与输出独立。

**应用场景**：
1. 同时浏览显示100张图像，屏幕放不下，使用`Show scale`缩放即可
2. 100张拼接造成的保存图片很大，使用`Output scale`可以方便控制文件大小

### 5.3.12 并行放大
**操作**:

1. 点击放大按钮

![image](https://github.com/nachifur/Mulimg_viewer/blob/master/img/f5.jpg)

2. 鼠标变为十字光标，在左上角第一张图片划框
3. 按住鼠标左键，选择放大区域，释放鼠标左键，显示放大结果

**Tip**:

1. **鼠标右键可以移动框的位置**
2. 默认放大结果的尺寸与原始图片一样，关闭`Keep size`，即可获得**任意长宽比**的放大结果
3. 放大`Scale`，默认为`-1,1`，即自动设置，默认放大图像放置原图下方。如果放大框的高度大于宽度，放大倍数为：原图高度/放大框的高度。此时可以选中`Vertical`,`Crtl+R`刷新显示，放大图像放置在原图的左侧
4. 放大`Scale`，支持自定义倍数放大，最大不超过原图尺寸。例如：`3,3`，长宽3倍的放大。
5. `Draw line width`设为0，即可隐藏框
6. `Draw line width`单位为pixel，在所有缩放下保持不变。注意：如果在`Show scale`为`0.1,0.1`，`Output scale`为`1,1`时，显示的框的宽度合适，那么输出框的宽度可能相比图片尺寸偏小

### 5.3.13 窗口大小自动化调节

关闭`Auto layout`即可。

## 6. 注意事项以及使用技巧

### 6.1 并行模式

1. 使用多图浏览模式（Parallel manual和Parallel auto），对比的文件夹里面的图像命名需要一样！
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

### 6.2 多图拼接，超大像素，窗口大小问题

1. 可以最大化窗口，或者关闭`Auto layout`
2. 调节`Show scale`，`0.2,0.2`缩小，`2,2`放大
3. 更改`Truth resolution`,将所有照片resize到同一尺寸，**对于浏览及其友好**

## 7. 许可证
https://www.gnu.org/licenses/gpl-3.0.en.html

## 8. 未来增强功能
感谢各位提供意见！大家可以在issues中发表意见，采用的会致谢大家！如果大家希望可以和我一起合作开发，请联系我！
- [x] 增加精确定位（目前已经有slider）
- [x] 增加图片索引查看，方便进行精确定位
- [x] 并行的局部放大功能（用于论文中的对比实验图片**急需！**）
- [x] 输入方式，新增：路径文件的导入和存储（@nothingeasy提供改进意见）
- [x] 增加删除功能（完善筛选功能）
- [ ] 任意图像数量的多模板拼图，每个图点击后可旋转，平移
- [ ] 用于图像分类标注？
- [ ] 多框放大功能（@JuZiSYJ提供改进意见）
- [ ] 保存带框的原始图像（@JuZiSYJ提供改进意见）
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
```

[![HitCount](http://hits.dwyl.com/nachifur/Mulimg_viewer.svg)](http://hits.dwyl.com/nachifur/Mulimg_viewer)
