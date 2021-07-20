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
</p>

# MulimgViewer
[**English page (Thanks @Faberman for the translation and polishing.)**](https://github.com/nachifur/MulimgViewer/wiki)
## 1. 介绍

MulimgViewer**多图像浏览器**，在一个界面显示多个图像，方便图像的比较、筛选。 

**功能**
* 多路径并行显示
* 多框并行放大
* 点按旋转
* 支持远程目录
* 批量化resize图片

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f6.gif)

下载地址：https://github.com/nachifur/MulimgViewer/releases

测试图像地址：https://github.com/nachifur/MulimgViewer/blob/master/img/test_img.zip

您的star是我开发完善该项目最大的支持！
qq交流群：945669929

## 2. python源码运行
v3.9.1以后仅提供`Windows 10`的包（`amd64`）。其他环境可以使用源码运行。建议使用Python3.6以上。

pip安装：
```bash
pip install wxpython pillow pytest-shutil
```
运行：
```python
python3 main.py
```

## 3. Windows-10
直接运行exe文件。也可以下载源码运行`main.py`。

v3.9.3以后，`Windows 10`提供安装版`_Setup.exe`和便携版`_Portable.exe`（安装版`_Setup.exe`启动速度更快）。

## 4. 应用场景
### 例1：并行浏览、挑选、保存

**以前**你可能需要打开多个图像，逐个对比，再到文件夹找到图像，复制到别的地方。

**现在**只需使用MulimgViewer多图像浏览器，输入各个需要对比的目录，**一键保存对比图像对到本地**！

图片挑选（默认使用复制，选中`Move file`为剪切）：`Parallel auto` or `Parallel manual`，关闭`Parallel+Sequential`。

### 例2：并行放大

MulimgViewer可以轻松的完成纵向与横向的拼接，**支持自动拼接保存，支持并行放大**！

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f7.jpg)

同时支持**任意位置**划框（鼠标左键按住移动），**多框**并行放大（鼠标右键点击，生成新的框）。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f11.gif)

微调box:（注意：开启`Select box`后，使用鼠标左键不能划框）
1. 选中`Select box`
2. 鼠标左键单击，选中已有的放大框
3. 然后使用键盘上下左右，微调放大框
4. 关闭`Select box`。

清除放大框：

方法1：
1. 选中`Select box`，键盘`Del`，删除特定`box`
2. 关闭`Select box`，键盘`Del`，删除所有`box`

方法2：
1. 关闭`Select box`
2. 鼠标左键双击图片
3. `Ctrl+R`刷新显示。

### 例3：数据库浏览、成对数据
浏览一个1000张图片的数据库，需要多长时间？一次显示100张，只需点击10次即可完成！MulimgViewer可以方便的进行成对的数据的浏览、比较。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f8.jpg)

### 例4：支持远程挂载目录图片浏览
将远程服务器的目录挂载后，在MulimgViewer中选择目录即可，完成图片浏览。
例如：使用ubuntu的文件管理器`nautilus`，stfp://10.8.0.4连接到服务器。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f9.jpg)

### 例5：支持点按旋转

显示多张图片的同时，鼠标左键点击即可完成图片旋转。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f10.gif)

### 例6：批量化resize图片
利用自动保存功能，可以实现批量化resize图片。
操作：
1. 输入模式选择：Sequential，选择输入文件夹
2. 选择保存文件的输出目录
3. 勾选自动保存`Auto save all`
4. 设置`Truth resolution`为固定的大小，例如：`256,256`
5. 点击保存💾️

<img width="512" height="512" src="https://github.com/nachifur/MulimgViewer/blob/master/img/f14.jpg"/>

## 5. 使用说明

## 5.1 操作流程
1. 在**Setting中填写布局参数**：row（一行有几张图片）, num per img（一个图片由几个子图片组成）, col（一列有几个图片）
2. File->Input path，选择**输入模式**

    2.1. Sequential: 一个文件夹多张图片。

    2.2. Parallel auto: 一个文件夹多个子文件夹。一个文件夹下有n个子文件夹，子文件夹中为图片。

    2.3. Parallel manual: 手动选择多个子文件夹。

    2.4. Image file list： 从文件导入图片列表文件

3. 这时图片显示在面板，可以使用**next、last**查看下一张，上一张图片
4. File->Out path, **选择输出的路径**。

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

`Sequential`是**串行浏览**模式，一个文件夹下有不同的图片，命名不同，用于图片的拼接。

`Parallel auto`和`Parallel manual`是**并行浏览**模式（子文件夹的名称不一样），需要确保各子文件夹下面的图片命名相同，用于不同图片的对比。

`Image File List`是**自定义模式**，从txt, csv文件导入图片列表。支持csv文件多行多列显示。

如果需要自动排布，`Num per img`设为-1。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f1.jpg)

### 5.3.2  输出模式：

Stitch: 将拼接的图像保存到*stitch_images*目录下

Select: 分别保存当前浏览的图像到不同的文件夹，默认为copy模式，选中`Move file`为剪切模式。（推荐的输入模式为`Parallel auto`或`Parallel manual`，关闭`Parallel+Sequential`）

Magnifer: 单独保存放大图像，方便用户的后期处理。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f2.jpg)

### 5.3.3 图像排列自动化

默认：`Num per img` = -1，这时为程序**自动布局模式**。`Num per img` 的意思是几张图像合成一个图像。

### 5.3.4 取消图像排列自动化

当`num per img` = 1或者>1，图像布局为**手动模式**，这时可以调整 `row` 和 `col`。

### 5.3.5. 并行模式下的串行显示

此时需要选中`Parallel+Sequential`，可以同时显示文件夹1-12的前n张图片，n可由`Num per img`设定。
例如：`row=5` ,`Num per img=4`, `col=1`, 一次分别读取5个并行目录的4张图片，共20张。
`Vertical`可以调整串行方向。`row=5` , `col=1`, 可以控制并行的二维排布。

### 5.3.6 自动保存

勾选自动保存`Auto save all`，点击保存💾️

### 5.3.7 图像尺寸归一化

Fill: 图像尺寸为一组图像中的最大尺寸，填充模式(保持原始像素分辨率)

Crop: 图像尺寸为一组图像中的最小尺寸，裁剪模式(保持原始像素分辨率)

Resize: 图像尺寸为一组图像中的平均尺寸，缩放模式(不保持原始像素分辨率)

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f3.jpg)

### 5.3.8 图像间隔

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f12.jpg)

### 5.3.9 图像填充

支持多种颜色填充。支持背景填充**透明**。**同时支持前景透明度调节**。

### 5.3.10 并行手动模式支持路径导入保存

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f4.jpg)

### 5.3.11 显示、输出尺寸独立

此功能可以保证显示的scale与输出独立。

**应用场景**：
1. 同时浏览显示100张图像，屏幕放不下，使用`Show scale`缩放即可
2. 100张拼接造成的保存图片很大，使用`Output scale`可以方便控制文件大小

### 5.3.12 并行放大
**操作**:

1. 点击放大按钮

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f5.jpg)

2. 鼠标变为十字光标，在任意图片位置划框
3. 选择放大区域：按住鼠标左键，移动鼠标，释放鼠标左键，显示放大结果
4. 新增放大框：鼠标右键，实现多框放大

**Tip**:

1. 开启`🔍️Keep size`，即可获得与原始图片长宽比一样的放大结果。
2. `🔍️Scale`，默认为`-1,1`，自动设置scale。
3. 可以选中`Vertical`,`Crtl+R`刷新显示，放大图像放置在原图的左侧。
4. `🔍️Scale`，支持自定义倍数放大，最大不超过原图尺寸。例如：`3,3`，长宽3倍的放大。
5. `Draw line width`设为0，即可隐藏框。
6. `Draw line width`单位为pixel，在所有缩放下线宽保持不变。如果在`Show scale`为`0.1,0.1`，`Output scale`为`1,1`时，显示的框的宽度合适，那么输出框的宽度可能相比图片尺寸偏小。

### 5.3.13 窗口大小自动化调节

开启`Auto layout`，即可实现窗口自动大小调节。

### 5.3.14 浏览图片，精确定位
移动slider，可实现粗定位。
1. `Help`->`Index table`
2. 查看图片显示序号
3. 输入序号，回车

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f13.jpg)

## 6. 注意事项以及使用技巧

### 6.1 并行模式

1. 使用多图浏览模式（Parallel manual和Parallel auto），对比的文件夹里面的图像命名需要一样！
2. 子文件夹的命名。如果是0,1,2...10,11，需要改为00,01,02,...10,11。因为排序时会变为：0,1,10,11,2...

### 6.2 多图拼接，超大像素图片，窗口大小问题

1. 关闭`Auto layout`，最大化窗口
2. 调节`Show scale`，`0.2,0.2`缩小，`2,2`放大
3. 更改`Truth resolution`,将所有照片resize到同一尺寸，**对于浏览及其友好**

## 7. 未来增强功能
感谢各位提供意见！大家可以在issues中发表意见，采用的会致谢大家！如果大家希望可以和我一起合作开发，请联系我！
- [x] 增加精确定位（目前已经有slider）
- [x] 增加图片索引查看，方便进行精确定位
- [x] 并行的局部放大功能（用于论文中的对比实验图片**急需！**）
- [x] 输入方式，新增：路径文件的导入和存储（@nothingeasy提供改进意见）
- [x] 增加删除功能（完善筛选功能）
- [x] 保存带框的原始图像（@JuZiSYJ提供改进意见）
- [x] 拼图过程中，点击可旋转图片
- [x] 多框放大功能（@JuZiSYJ提供改进意见）
- [ ] 为图像添加titile（@Faberman提供改进意见）
- [ ] 高清图像的对比，放大图像1:1输出（@Faberman提供改进意见）

## 8. 致谢
* nothingeasy:改进意见-(输入方式，新增：路径文件的导入和存储)
* JuZiSYJ:改进意见-(保存带框的原始图像+并行放大)
* Faberman:改进意见-(为图像添加titile+放大图像1:1输出)


## 9. 引用
如果您在研究中使用此项目，请使用以下BibTeX条目。
```
@misc{MulimgViewer2020,
  author =       {Jiawei Liu},
  title =        {{MulimgViewer: A multi-image viewer for image comparison and image stitching}},
  howpublished = {\url{https://github.com/nachifur/MulimgViewer}},
  year =         {2020}
}
```

## 10. 使用条款
### 10.1 许可证
GPL-3.0 License：https://www.gnu.org/licenses/gpl-3.0.en.html

### 10.2 额外条款
- 允许个人使用
- 商业使用请联系 - liujiawei18@mails.ucas.ac.cn.
