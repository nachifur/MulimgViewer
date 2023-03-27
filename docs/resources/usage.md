# 使用说明

## 快捷栏

![Shortcut_bar](https://user-images.githubusercontent.com/32936898/224470802-9336ba25-2cc6-49f5-9468-058281b02ff4.jpg)

## 操作流程

测试图像下载地址：
[test_img.zip](https://github.com/nachifur/MulimgViewer/files/10948418/test_img.zip)

**注意：本软件不支持自动刷新，修改布局参数之后，需要手动刷新（`Ctrl+R`）。**

![Quick_start](https://user-images.githubusercontent.com/32936898/224470801-9bc4c1eb-1e9c-40bd-9382-313916331e5e.jpg)

1. 在`Layout`中**填写布局参数**：`Row`（一行有几张图片）, `NumPerImg`（一个图片由几个子图片组成）, `Col`（一列有几个图片）。
2. 选择**输入模式**

    2.1. Sequential: 一个文件夹多张图片。(`test_input/01`)

    2.2. Parallel auto: 一个文件夹多个子文件夹。一个文件夹下有n个子文件夹，子文件夹中为图片。 (`test_input/`)

    2.3. Parallel manual: 手动选择多个子文件夹。(`test_input//01`+`test_input//02`)

    2.4. Image file list： 从文件导入图片列表文件。([Examples file](https://github.com/nachifur/MulimgViewer/tree/master/examples/input))

3. 打开文件夹，导入路径
4. 这时图片显示在面板，可以使用`>`查看下一张，`<`查看上一张图片
5. `Input/OutPut`->OutputMode, 选择输出模式
6. `File->Select output path`, **选择输出的路径**。
7. 点击保存💾️


## 快捷键
1. 输入路径：

    Sequential: Ctrl+E

    Parallel auto: Ctrl+A

    Parallel manual: Ctrl+M

    Image file list: Ctrl+F

2. 输出路径：Ctrl+O
3. 下一张：Ctrl+N
4. 上一张Ctrl+L
5. 保存：Ctrl+S
6. 刷新：Ctrl+R (或者鼠标右键。ps：鼠标右键具有功能复用：默认是：刷新；放大模式：新增框；选中Box:SelectBox：移动框)
7. 隐藏工具栏：Ctrl+H
8. 使用键盘的上下左右，可以移动图像面板里的图像。

## 功能介绍

### 输入模式

`Sequential`是**串行浏览**模式，一个文件夹下有不同的图片，命名不同，用于图片的拼接。

`Parallel auto`和`Parallel manual`是**并行浏览**模式（子文件夹的名称不一样），需要确保各子文件夹下面的图片命名相同，用于不同图片的对比。

`Image File List`是**自定义模式**，从txt, csv文件导入图片列表。支持csv文件多行多列显示。

如果需要自动排布，`NumPerImg`设为-1。

<img width="250" height="150" src="https://user-images.githubusercontent.com/32936898/224470713-cf8d136d-f36c-4b57-8e0e-cc3545bd6650.jpg"/>

###  输出模式

Stitch: 将拼接的图像保存到*stitch_images*目录下

Select: 分别保存当前浏览的图像到不同的文件夹，默认为copy模式，选中`MoveFile`为剪切模式。（推荐的输入模式为`Parallel auto`或`Parallel manual`，关闭`Parallel+Sequential`和`Parallel->Sequential`）

Magnifer: 单独保存放大图像，方便用户的后期处理。

<img width="250" height="200" src="https://user-images.githubusercontent.com/32936898/224470715-7e22c443-210c-4e6f-9e77-dd10bd573f24.jpg"/>

### 图像排列自动化

默认：`NumPerImg` = -1，这时为程序**自动布局模式**。`NumPerImg` 的意思是几张图像合成一个图像。

当`NumPerImg` = 1或者>1，图像布局为**手动模式**，这时可以调整 `Row` 和 `Col`。

### 并行模式下的串行显示

在`Parallel auto`和`Parallel manual`模式下，可以并行显示多个文件夹。

**Parallel+Sequential：**

选中`Parallel+Sequential`，在并行显示的同时，可以串行浏览每个文件夹中的前n张图片，n可由`NumPerImg`设定。例如：`Row=5` ,`NumPerImg=4`, `Col=1`, 一次分别读取5个并行目录的4张图片，共20张。`Vertical`可以调整串行方向。修改`Row`和`Col`, 可以控制并行文件夹的二维排布。

![Parallel_Sequential](https://user-images.githubusercontent.com/32936898/224482764-d5e1335d-647d-480b-ae69-2596eeff3941.jpg)

**Parallel->Sequential：** 将多个文件夹的所有图片，拼接成一个图片列表进行串行显示。

在`Parallel+Sequential`模式下，各个子文件夹下的文件名称需要一样。在`Parallel->Sequential`模式下，则不需要。

### 自动保存

勾选自动保存`AutoSaveAll`，点击保存💾️，实现批量化操作。

### 图像尺寸归一化

Fill: 图像尺寸为一组图像中的最大尺寸，填充模式(保持原始像素分辨率)

Crop: 图像尺寸为一组图像中的最小尺寸，裁剪模式(保持原始像素分辨率)

Resize: 图像尺寸为一组图像中的平均尺寸，缩放模式(不保持原始像素分辨率)

<img width="250" height="150" src="https://user-images.githubusercontent.com/32936898/224470716-6bd324c8-5aea-4019-812e-99b8d920be88.jpg"/>

### 图像间隔

![f12](https://user-images.githubusercontent.com/32936898/224470762-099c5217-8e8a-4f08-8257-e9b9f8d0a70c.jpg)

### 图像填充

支持多种颜色填充。支持背景填充**透明**。**同时支持前景透明度调节**。

### 并行手动模式支持路径导入保存

<img width="250" height="200" src="https://user-images.githubusercontent.com/32936898/224470718-ded4393f-1910-49eb-9431-cc78a32f88ef.jpg"/>

### 显示、输出尺寸独立

此功能可以保证显示的scale与输出独立。

**应用场景**：
1. 同时浏览显示100张图像，屏幕放不下，使用`Scale:Show`缩放即可
2. 100张拼接造成的保存图片很大，使用`Scale:Out`可以方便控制文件大小

### 并行放大
**操作**:

1. 点击放大按钮`🔍️`

<img width="50" height="50" src="https://user-images.githubusercontent.com/32936898/224470719-89b1607c-c8be-424b-8e14-649db8260960.jpg"/>

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

### 窗口大小自动化调节

开启`AutoWinSize`，即可实现窗口自动大小调节。

### 浏览图片，精确定位
**粗定位：** 移动slider。

**精确定位：**

<img width="100" height="50" src="https://user-images.githubusercontent.com/32936898/224470766-74505f1c-ed5c-4b37-913e-87a682f965b2.jpg"/>

1. `Help`->`Index table`
2. 查看图片显示序号
3. 输入序号，回车

### 标题
**标题**

1. 关闭`Title:Auto`之后，可以进行自定义显示标题
2. 在`Sequential`输入模式下，文件名为`01_DSC.jpg`，不选中`Prefix`和`Suffix`，文件显示为`DSC`。使用数字可以对图片文件进行排序。

**字体**

1. 建议使用安装版`_Setup.exe`
2. 将字体`1_Calibri-Light.ttf`复制到安装目录`C:\Program Files (x86)\MulimgViewer\font\using`下
3. `1_Calibri-Light.ttf`中的数字越小，GUI中的字体排序靠前

## 注意事项以及使用技巧

### 并行模式

1. 使用多图浏览模式（Parallel manual和Parallel auto），对比的文件夹里面的图像命名需要一样！
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

文件重命名工具推荐：

win10: [uTools](https://u.tools/)

Ubuntu:

1. purrr.

`sudo apt install purrr`

2. Thunar - Bulk Rename Files.

`sudo apt install thunar`

3. 懂正则表达式的用户可以试试
[perl-rename](https://unix.stackexchange.com/questions/730894/what-are-the-different-versions-of-the-rename-command-how-do-i-use-the-perl-ver)。

4. find

```
find /path/to/folder -type f > ./filelist.txt
```



### 多图拼接，超大像素图片，窗口大小问题

1. 关闭`AutoWinSize`，最大化窗口
2. 调节`Scale:Show`，`0.2,0.2`缩小，`2,2`放大
3. 更改`TruthResolution`,将所有照片resize到同一尺寸，**对于浏览及其友好**
