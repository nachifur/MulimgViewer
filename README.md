<p align="center">
<a href="https://github.com/nachifur/MulimgViewer" target="_blank">
<img width="251" height="251" img align="center" alt="multiple images viewer" src="https://user-images.githubusercontent.com/32936898/224470786-d7c590e6-8a0e-4d0e-b897-50906e5eb209.png" />
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

Doc: [**English Doc**](https://mulimgviewer.readthedocs.io/en/latest/) | [**完整官网文档**](https://mulimgviewer.readthedocs.io) | [**Wiki**](https://github.com/nachifur/MulimgViewer/wiki)



Mirror: [**国内gitee镜像项目**](https://gitee.com/nachifur/MulimgViewer) | [**果壳OpenCas镜像项目**](https://github.com/opencas/MulimgViewer)

Link: [**快速入门**](https://mulimgviewer.readthedocs.io/zh_CN/latest/resources/usage.html) | [**下载和安装**](https://mulimgviewer.readthedocs.io/zh_CN/latest/resources/install.html)

如果有一些超链接失效，请通过[issue](https://github.com/nachifur/MulimgViewer/issues/new/choose)反馈。

## 介绍

MulimgViewer**多图像浏览器**，在一个界面显示多个图像，方便图像的比较、筛选。
- 从多个文件夹加载图像并并排显示
- 同时放大多个区域

![f6](https://user-images.githubusercontent.com/32936898/224470721-c49f0269-70ad-419d-bbd0-f2a8eaa7a453.gif)

您的star是我开发完善该项目最大的支持！
qq交流群：945669929

<img width="250" height="355" src="https://user-images.githubusercontent.com/32936898/224470800-84969a8a-f98e-4150-aa05-6b174b404845.jpg"/>

## 应用场景
### 例1：多图像浏览
浏览202,599张图片的数据库CelebA，需要多长时间？一次显示1000张，只需点击200多次即可完成！
![f15](https://user-images.githubusercontent.com/32936898/224470768-96eb5aee-8ca0-4903-ab80-d624b7aee691.jpg)

### 例2：并行挑选

**以前**你可能需要在多个窗口打开多个图像，逐个对比，再到文件夹找到对应的图像，复制到别的地方。

**现在**使用MulimgViewer多图像浏览器，输入各个需要对比的目录，**一键保存需要对比的多张图像到本地**！

![Parallel_select](https://user-images.githubusercontent.com/32936898/224470788-799e5141-a8a0-4e4b-b58b-cd61f5446591.jpg)

图片并行挑选：`Parallel auto` or `Parallel manual`，关闭`Parallel+Sequential`（默认使用复制，选中`MoveFile`为剪切）。

### 例3：并行放大

MulimgViewer可以轻松的完成纵向与横向的拼接，**支持自动拼接保存，支持并行放大**！

![f7](https://user-images.githubusercontent.com/32936898/224470740-375f42ee-a9d3-4902-b9d4-9945bc84044c.jpg)

同时支持**任意位置**划框（鼠标左键按住移动），**多框**并行放大（鼠标右键点击，生成新的框）。[详细见](https://mulimgviewer.readthedocs.io/zh_CN/latest/resources/usage.html#id16)

![f11](https://user-images.githubusercontent.com/32936898/224470749-46b0507d-b1c8-4418-9429-6874579ffdca.gif)

### 例4：成对数据浏览
MulimgViewer可以方便的进行成对的数据的浏览、比较。[详细见](https://mulimgviewer.readthedocs.io/zh_CN/latest/resources/usage.html#id9)

![f8](https://user-images.githubusercontent.com/32936898/224470741-b6466206-6397-4383-a56c-92c601128170.jpg)

### 例5：一键生成论文对比图
支持显示标题，调整放大框的位置。放大框的位置选择`middle bottom`，建议`🔍️Scale=-1,-1`;如果选择其他位置，自行调节放大倍数，例如：`🔍️Scale=1.5,1.5`。[详细见](https://mulimgviewer.readthedocs.io/zh_CN/latest/resources/usage.html#id19)

![f17](https://user-images.githubusercontent.com/32936898/224470773-0917564d-e74c-4f3e-9434-f3cb7d7687de.jpg)

显示半张图像。勾选`OneImg`，使用`NumPerimg`控制几张图像合成一张图像。`Gap(x,y)=*,*,0,*,*`消除间距。

![f18](https://user-images.githubusercontent.com/32936898/224470775-aa84975a-29e4-4d6a-b826-7ffbb4cbbbc6.jpg)

### 例6：支持远程挂载目录图片浏览
将远程服务器的目录挂载后，在MulimgViewer中选择目录即可，完成图片浏览。
1. Ubuntu: 使用ubuntu的文件管理器`nautilus`，stfp://10.8.0.4连接到服务器。

<img width="500" height="200" src="https://user-images.githubusercontent.com/32936898/224470743-2c3b25e2-9835-4324-812d-17d6088abdc0.jpg"/>

2. win10: 安装WinFsp和[SSHFS-Win](https://github.com/billziss-gh/sshfs-win)之后，文件资源管理器中填写远程服务器ip，例如：`\\sshfs\user@ip!port`

<img width="500" height="200" src="https://user-images.githubusercontent.com/32936898/224470772-7282bfaf-702c-4f95-a388-8d9db4f51e39.jpg"/>

### 例7：支持点按旋转

显示多张图片的同时，鼠标左键点击即可完成图片旋转。

![f10](https://user-images.githubusercontent.com/32936898/224470746-39609e38-b610-4254-baf5-3ad4385f9171.gif)

### 例8：批量化resize图片
利用自动保存功能，可以实现批量化resize图片。
操作：
1. 输入模式选择：Sequential，选择输入文件夹
2. 选择保存文件的输出目录
3. 勾选自动保存`AutoSaveAll`
4. 设置`TruthResolution`为固定的大小，例如：`256,256`
5. 点击保存💾️

## 引用

如果您在研究中使用此项目，请使用以下BibTeX条目。

```bib
@software{MulimgViewer,
  author  = {Liu, Jiawei},
  license = {GPL-3},
  title   = {{MulimgViewer: A multi-image viewer for image comparison and image stitching}},
  url     = {https://github.com/nachifur/MulimgViewer}
}
```

## 使用条款
**许可证**

GPL-3.0 License：https://www.gnu.org/licenses/gpl-3.0.en.html

**额外条款**

- 允许个人使用
- 商业使用请联系 - liujiawei18@mails.ucas.ac.cn.
## Star 历史

[![Star History Chart](https://api.star-history.com/svg?repos=nachifur/MulimgViewer&type=Date)](https://star-history.com/#nachifur/MulimgViewer&Date)
