<p align="center">
<a href="https://github.com/nachifur/MulimgViewer" target="_blank">
<img align="center" alt="multiple images viewer" src="https://github.com/nachifur/MulimgViewer/blob/master/mulimgviewer.ico" />
</a>
</p>

<p align="center">
<a href="https://github.com/nachifur/MulimgViewer/stargazers" target="_blank">
 <img alt="GitHub stars" src="https://img.shields.io/github/stars/nachifur/MulimgViewer.svg" />
</a>
<a href="https://github.com/nachifur/MulimgViewer/releases" target="_blank">
 <img alt="All releases" src="https://img.shields.io/github/downloads/nachifur/MulimgViewer/total.svg" />
</a>
<a href="https://www.oscs1024.com/project/oscs/nachifur/MulimgViewer?ref=badge_small" alt="OSCS Status"><img src="https://www.oscs1024.com/platform/badge/nachifur/MulimgViewer.svg?size=small"/></a>
</p>

# MulimgViewer
[**English readme (Thanks @Faberman for the translation and polishing.)**](https://github.com/nachifur/MulimgViewer/wiki)

[**国内gitee镜像项目**](https://gitee.com/nachifur/MulimgViewer) | [**果壳OpenCas镜像项目**](https://github.com/opencas/MulimgViewer)

[**下载**](https://github.com/nachifur/MulimgViewer/releases) | [**快速上手**](#5.2) | [**开发者指南**](https://github.com/nachifur/MulimgViewer/blob/master/DEV_README.md)

<!-- https://github.com/nachifur/MulimgViewer/blob/->https://gitee.com/nachifur/MulimgViewer/raw/ -->
<!-- https://github.com/nachifur/MulimgViewer/releases->https://gitee.com/nachifur/MulimgViewer/releases -->

## 1. 介绍

MulimgViewer**多图像浏览器**，在一个界面显示多个图像，方便图像的比较、筛选。 

**软件功能**: 多路径并行显示、多框并行放大 ([more](#4.0))。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f6.gif)

您的star是我开发完善该项目最大的支持！
qq交流群：945669929

<img width="250" height="355" src="https://github.com/nachifur/MulimgViewer/blob/master/img/qrcode.jpg"/>

## 2. Windows-10
* 直接下载并运行[exe文件]((https://github.com/nachifur/MulimgViewer/releases))；或者下载源码运行`MulimgViewer.py`->[**源码运行**](#3.0)
* v3.9.3以后，`Windows 10`提供安装版`_Setup.exe`和便携版`_Portable.exe`（安装版`_Setup.exe`启动速度更快）

## 3. python源码运行(windows\linux\ios)<a name="3.0"></a> 

* 目前仅提供`Windows 10`的安装包（`amd64`）
* **其他环境**可以使用源码运行，安装环境使用以下两种方式都行（pip or conda）
* 建议使用Python3.6以上
* [最新源码下载](https://codeload.github.com/nachifur/MulimgViewer/zip/refs/heads/master)

## 3.1 pip 安装
pip安装：（如果安装过程出错，可以使用conda安装）
```bash
pip install wxpython pillow pytest-shutil numpy requests piexif
```
运行：
```python
python3 MulimgViewer.py
```
## 3.2 conda 安装
或者安装conda环境：
```bash
conda env create -f install.yaml
```
运行：
```python
conda activate mulimgviewer
python MulimgViewer.py
```

## 4. 应用场景 <a name="4.0"></a> 
### 例1：多图像浏览
浏览202,599张图片的数据库CelebA，需要多长时间？一次显示1000张，只需点击200多次即可完成！
![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f15.jpg)

### 例2：并行挑选

**以前**你可能需要在多个窗口打开多个图像，逐个对比，再到文件夹找到对应的图像，复制到别的地方。

**现在**使用MulimgViewer多图像浏览器，输入各个需要对比的目录，**一键保存需要对比的多张图像到本地**！

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/Parallel_select.jpg)

图片并行挑选：`Parallel auto` or `Parallel manual`，关闭`Parallel+Sequential`（默认使用复制，选中`MoveFile`为剪切）。

### 例3：并行放大 

MulimgViewer可以轻松的完成纵向与横向的拼接，**支持自动拼接保存，支持并行放大**！

<img src="https://github.com/nachifur/MulimgViewer/blob/master/img/f7.jpg"/>

同时支持**任意位置**划框（鼠标左键按住移动），**多框**并行放大（鼠标右键点击，生成新的框）。[详细见](#5.4.11)

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f11.gif)

### 例4：成对数据浏览
MulimgViewer可以方便的进行成对的数据的浏览、比较。[详细见](#5.4.4)

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f8.jpg)

### 例5：一键生成论文对比图
支持显示标题，调整放大框的位置。放大框的位置选择`middle bottom`，建议`🔍️Scale=-1,-1`;如果选择其他位置，自行调节放大倍数，例如：`🔍️Scale=1.5,1.5`。[详细见](#5.4.14)

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f17.jpg)

显示半张图像。勾选`OneImg`，使用`NumPerimg`控制几张图像合成一张图像。`Gap(x,y)=*,*,0,*,*`消除间距。
![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f18.jpg)

### 例6：支持远程挂载目录图片浏览
将远程服务器的目录挂载后，在MulimgViewer中选择目录即可，完成图片浏览。
1. Ubuntu: 使用ubuntu的文件管理器`nautilus`，stfp://10.8.0.4连接到服务器。

<img width="500" height="200" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f9.jpg"/>

2. win10: 安装WinFsp和[SSHFS-Win](https://github.com/billziss-gh/sshfs-win)之后，文件资源管理器中填写远程服务器ip，例如：`\\sshfs\user@ip!port`

<img width="500" height="200" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f16.jpg"/>

### 例7：支持点按旋转

显示多张图片的同时，鼠标左键点击即可完成图片旋转。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f10.gif)

### 例8：批量化resize图片
利用自动保存功能，可以实现批量化resize图片。
操作：
1. 输入模式选择：Sequential，选择输入文件夹
2. 选择保存文件的输出目录
3. 勾选自动保存`AutoSaveAll`
4. 设置`TruthResolution`为固定的大小，例如：`256,256`
5. 点击保存💾️

## 5. 使用说明

## 5.1 快捷栏

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/Shortcut_bar.jpg)

## 5.2 操作流程 <a name="5.2"></a> 
测试图像下载地址：https://raw.githubusercontent.com/nachifur/MulimgViewer/master/img/test_img.zip

**注意：本软件不支持自动刷新，修改布局参数之后，需要手动刷新（`Ctrl+R`）。**

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/Quick_start.jpg)


1. 在`Layout`中**填写布局参数**：`Row`（一行有几张图片）, `NumPerImg`（一个图片由几个子图片组成）, `Col`（一列有几个图片）。
2. 选择**输入模式**

    2.1. Sequential: 一个文件夹多张图片。(`test_input/01`)

    2.2. Parallel auto: 一个文件夹多个子文件夹。一个文件夹下有n个子文件夹，子文件夹中为图片。 (`test_input/`)

    2.3. Parallel manual: 手动选择多个子文件夹。(`test_input//01`+`test_input//02`)

    2.4. Image file list： 从文件导入图片列表文件。([Demo file](https://github.com/nachifur/MulimgViewer/tree/master/demo_input_from_file))

3. 打开文件夹，导入路径
4. 这时图片显示在面板，可以使用`>`查看下一张，`<`查看上一张图片
5. `Input/OutPut`->OutputMode, 选择输出模式
6. `File->Select output path`, **选择输出的路径**。
7. 点击保存💾️


## 5.3 快捷键
1. 输入路径：

    Sequential: Ctrl+E

    Parallel auto: Ctrl+A

    Parallel manual: Ctrl+M

    Image file list: Ctrl+F

2. 输出路径：Ctrl+O
3. 下一张：Ctrl+N
4. 上一张Ctrl+L
5. 保存：Ctrl+S
6. 刷新：Ctrl+R (或者鼠标右键)
7. 隐藏工具栏：Ctrl+H
8. 使用键盘的上下左右，可以移动图像面板里的图像。

## 5.4 功能介绍

### 5.4.1 输入模式

`Sequential`是**串行浏览**模式，一个文件夹下有不同的图片，命名不同，用于图片的拼接。

`Parallel auto`和`Parallel manual`是**并行浏览**模式（子文件夹的名称不一样），需要确保各子文件夹下面的图片命名相同，用于不同图片的对比。

`Image File List`是**自定义模式**，从txt, csv文件导入图片列表。支持csv文件多行多列显示。

如果需要自动排布，`NumPerImg`设为-1。

<img width="250" height="150" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f1.jpg"/>

### 5.4.2  输出模式

Stitch: 将拼接的图像保存到*stitch_images*目录下

Select: 分别保存当前浏览的图像到不同的文件夹，默认为copy模式，选中`MoveFile`为剪切模式。（推荐的输入模式为`Parallel auto`或`Parallel manual`，关闭`Parallel+Sequential`和`Parallel->Sequential`）

Magnifer: 单独保存放大图像，方便用户的后期处理。

<img width="250" height="200" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f2.jpg"/>

### 5.4.3 图像排列自动化

默认：`NumPerImg` = -1，这时为程序**自动布局模式**。`NumPerImg` 的意思是几张图像合成一个图像。

当`NumPerImg` = 1或者>1，图像布局为**手动模式**，这时可以调整 `Row` 和 `Col`。

### 5.4.4. 并行模式下的串行显示  <a name="5.4.4"></a> 

在`Parallel auto`和`Parallel manual`模式下，可以并行显示多个文件夹。

**Parallel+Sequential：**

选中`Parallel+Sequential`，在并行显示的同时，可以串行浏览每个文件夹中的前n张图片，n可由`NumPerImg`设定。例如：`Row=5` ,`NumPerImg=4`, `Col=1`, 一次分别读取5个并行目录的4张图片，共20张。`Vertical`可以调整串行方向。修改`Row`和`Col`, 可以控制并行文件夹的二维排布。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/Parallel_Sequential.jpg)

**Parallel->Sequential：** 将多个文件夹的所有图片，拼接成一个图片列表进行串行显示。

在`Parallel+Sequential`模式下，各个子文件夹下的文件名称需要一样。在`Parallel->Sequential`模式下，则不需要。

### 5.4.5 自动保存

勾选自动保存`AutoSaveAll`，点击保存💾️，实现批量化操作。

### 5.4.6 图像尺寸归一化

Fill: 图像尺寸为一组图像中的最大尺寸，填充模式(保持原始像素分辨率)

Crop: 图像尺寸为一组图像中的最小尺寸，裁剪模式(保持原始像素分辨率)

Resize: 图像尺寸为一组图像中的平均尺寸，缩放模式(不保持原始像素分辨率)

<img width="250" height="150" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f3.jpg"/>

### 5.4.7 图像间隔

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f12.jpg)

### 5.4.8 图像填充

支持多种颜色填充。支持背景填充**透明**。**同时支持前景透明度调节**。

### 5.4.9 并行手动模式支持路径导入保存

<img width="250" height="200" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f4.jpg"/>

### 5.4.10 显示、输出尺寸独立

此功能可以保证显示的scale与输出独立。

**应用场景**：
1. 同时浏览显示100张图像，屏幕放不下，使用`Scale:Show`缩放即可
2. 100张拼接造成的保存图片很大，使用`Scale:Out`可以方便控制文件大小

### 5.4.11 并行放大 <a name="5.4.11"></a> 
**操作**:

1. 点击放大按钮`🔍️`

<img width="50" height="50" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f5.jpg"/>

2. 鼠标变为十字光标，在任意图片位置划框
3. 选择放大区域：按住鼠标左键，移动鼠标，释放鼠标左键，显示放大结果
4. 新增放大框：鼠标右键，实现多框放大

**Tip**:

1. 开启`🔍️KeepSize`，即可获得与原始图片长宽比一样的放大结果。
2. `🔍️Scale`，默认为`-1,1`，自动设置scale。
3. 可以选中`Vertical`,`Crtl+R`刷新显示，放大图像放置在原图的右侧。
4. `🔍️Scale`，支持自定义倍数放大，最大不超过原图尺寸。例如：`3,3`，长宽3倍的放大。
5. `Box:Width`设为`2,3`。原图中的线宽是2，放大图中的线宽是3。
6. `Box:Width`设为`0,0`，即可隐藏框。
7. `Box:Width`单位为pixel，在所有缩放下线宽保持不变。如果在`Scale:Show`为`0.1,0.1`，`Scale:Out`为`1,1`时，显示的框的宽度合适，那么输出框的宽度可能相比图片尺寸偏小。
8. 点击放大按钮`🔍️`之后，鼠标单击图片选中，然后使用`ctrl`+鼠标滚轮全局缩放图像。
9. 鼠标滚轮缩放功能，使用缩放因子控制。每次手动设置`Scale:Show`为`1,1`，缩放因子清零，界面刷新。

**移动box**:

（注意：开启`Box:SelectBox`后，使用鼠标左键不能划框）
1. 选中`Box:SelectBox`
2. 鼠标左键单击，选中已有的放大框
3. 然后使用键盘上下左右(或者鼠标滚轮)，微调放大框(按`shift`键可以改变速度)。使用鼠标右键，快速移动放大框。
4. 关闭`Box:SelectBox`。

**清除放大框**：

方法1：
1. 选中`Box:SelectBox`，键盘`Del`，删除特定`box`
2. 关闭`Box:SelectBox`，键盘`Del`，删除所有`box`

方法2：
1. 关闭`Box:SelectBox`
2. 鼠标左键双击图片
3. `Ctrl+R`刷新显示。
   
**手动修改放大框的颜色**：

1. 选中`Box:SelectBox`
2. 在原图片上，鼠标左键选中某个框
3. 鼠标左键单击`Color/transparency:Draw`，选择颜色

**不显示box/框**：

1. 不选中`Box:InBox`，去掉原始图片上的框
2. 不选中`Box:In🔍️`，去掉放大图片上的框
3. 不选中`ShowImg`，不显示原始图片
4. 不选中`Show🔍️`，不显示放大图片

### 5.4.12 窗口大小自动化调节

开启`AutoWinSize`，即可实现窗口自动大小调节。

### 5.4.13 浏览图片，精确定位
**粗定位：** 移动slider。

**精确定位：**

<img width="100" height="50" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f13.jpg"/>

1. `Help`->`Index table`
2. 查看图片显示序号
3. 输入序号，回车

### 5.4.14 标题 <a name="5.4.14"></a> 
**标题**

1. 关闭`Title:Auto`之后，可以进行自定义显示标题
2. 在`Sequential`输入模式下，文件名为`01_DSC.jpg`，不选中`Prefix`和`Suffix`，文件显示为`DSC`。使用数字可以对图片文件进行排序。

**字体**

1. 建议使用安装版`_Setup.exe`
2. 将字体`1_Calibri-Light.ttf`复制到安装目录`C:\Program Files (x86)\MulimgViewer\font\using`下
3. `1_Calibri-Light.ttf`中的数字越小，GUI中的字体排序靠前

## 6. 注意事项以及使用技巧

### 6.1 并行模式

1. 使用多图浏览模式（Parallel manual和Parallel auto），对比的文件夹里面的图像命名需要一样！
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

> 文件重命名工具推荐：
> 
> win10: [uTools](https://u.tools/)
> 
> Ubuntu: 
> 1. purrr.
> `sudo apt install purrr`
> 2. Thunar - Bulk Rename Files.
> `sudo apt install thunar`

### 6.2 多图拼接，超大像素图片，窗口大小问题

1. 关闭`AutoWinSize`，最大化窗口
2. 调节`Scale:Show`，`0.2,0.2`缩小，`2,2`放大
3. 更改`TruthResolution`,将所有照片resize到同一尺寸，**对于浏览及其友好**

## 7. 未来增强功能 <a name="7.0"></a> 
感谢各位提供意见！大家可以在issues中发表意见，采用的会致谢大家！如果大家希望可以和我一起合作开发，请联系我！
- [x] 增加精确定位（目前已经有slider）
- [x] 增加图片索引查看，方便进行精确定位
- [x] 并行的局部放大功能（用于论文中的对比实验图片**急需！**）
- [x] 输入方式，新增：路径文件的导入和存储（@nothingeasy提供改进意见）
- [x] 增加删除功能（完善筛选功能）
- [x] 保存带框的原始图像（@JuZiSYJ提供改进意见）
- [x] 拼图过程中，点击可旋转图片
- [x] 多框放大功能（@JuZiSYJ提供改进意见）
- [x] 去除放大图像的box（@stefanklut提供改进意见）
- [x] 高清图像的对比，放大图像1:1输出（@Faberman提供改进意见）
- [X] 为图像添加titile（@Faberman提供改进意见）

## 8. 致谢 <a name="8.0"></a> 
* Everyone in the QQ group;
* nothingeasy:改进意见-(输入方式，新增：路径文件的导入和存储);
* JuZiSYJ:改进意见-(保存带框的原始图像+并行放大);
* Faberman:改进意见-(为图像添加titile+放大图像1:1输出);
* stefanklut:改进意见-(不显示放大图像的边界框);
* FunkyKoki:改进意见-(显示一半的图像+新增放大图像排布方式).

## 9. 引用
如果您在研究中使用此项目，请使用以下BibTeX条目。
```
@software{MulimgViewer,
  author  = {Liu, Jiawei},
  license = {GPL-3},
  title   = {{MulimgViewer: A multi-image viewer for image comparison and image stitching}},
  url     = {https://github.com/nachifur/MulimgViewer}
}
```

## 10. 使用条款
**许可证**

GPL-3.0 License：https://www.gnu.org/licenses/gpl-3.0.en.html

**额外条款**

- 允许个人使用
- 商业使用请联系 - liujiawei18@mails.ucas.ac.cn.
