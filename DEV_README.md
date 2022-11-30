# MulimgViewer开发指南
# 0. 加入我们吧！
**初衷**：目前的市面上的图像浏览器不能同时显示多张图像。2020.8.10诞生的MulimgViewer，希望可以让大家方便地进行多张图像的显示和比较。恍惚一世，希望能在这个世界留下痕迹。

**定位**：MulimgViewer，即multi-image viewer。该软件**核心功能**是：多张图像并行显示、比较。

**目标**：期待MulimgViewer走向世界的每一个角落。

**开发**：每个人都希望定制自己的MulimgViewer，但一个包含各种各样功能的软件也许不是大家喜欢的。开发一些受众较广的功能，这会帮助到更多的人，这是我们期望的。另外，进一步完善扩展核心功能也是需要的。

**如何参与开发？** 
我们真诚地感谢您加入MulimgViewer的开发。

参与做出贡献的途径：（由易到难）
1. 项目的宣传。如：QQ、微信、知乎文章、CSDN博客、公众号等。
2. readme的优化。如：提升readme的易读性、完善某一功能的介绍。
3. ubuntu和ios等平台的打包。
4. pip安装途径的支持和维护。
5. bug提交并修复。
6. 已有功能的改进。如：运行速度的优化、版本更新提示。
7. 新功能的开发。
8. 架构的优化。
9. 我们期待每个用户任意的改进意见！

新功能的开发：
1. 假如您有任何好的idea，在github上提一个issue。
2. 在这个issue中，我们可以讨论具体功能的实现细节。也可以在qq上交流，最后把讨论的结果写到issue中。
3. 正常的开发流程：fork到自己本地->新建一个分支->实现功能->自行调试成功->合并到主分支。
4. 如果您希望深度地、持续地参与到项目的开发中，可以邮件(liujiawei18@mails.ucas.ac.cn)联系我。我会邀请您开发此软件，您可以获得直接访问该项目的权限，这有利于快速及时地更新主分支。

# 1. 文件说明
项目框架：
```
MulimgViewer
    * demo_input_from_file
    * font/using                    # 7. 存放预置的字体，用于title的显示
    * gui
        - about_gui.fbp
        - about_gui.py
        - index_table_gui.fbp
        - index_table_gui.py
        - main_gui.fbp              # 4. 使用wxfrombuilder可以更改GUI界面，生成对应的_gui.py
        - main_gui.py               # 3. 主文件对应的GUI
        - path_select_gui.fbp       
        - path_select_gui.py
    * img
    * src
        - main.py                   # 2. 主文件，实现主要的逻辑功能（回调函数）
        - data.py                   # 5. 数据加载
        - utils_img.py              # 6. 图像拼接、放大等操作
        - path_select.py            # 8. 在Parallel manual模式下，选择路径的窗口文件
        - about.py                  # 9. help 窗口文件
        - index_table.py            # 10. index table 窗口文件，可显示图片文件列表
        - utils.py                  # 11. 其他功能函数
    - MulimgViewer.py                 # 1. 入口文件
    - README.md                       # 12. 用户readme
    - DEV_README.md                   # 13. 开发readme
```
# 2. 开发流程
## 2.1 GUI的创建
GUI使用[wxFormBuilder](https://github.com/wxFormBuilder/wxFormBuilder)创建。wxFormBuilder的安装：
1. window平台可以直接下载[exe](https://github.com/wxFormBuilder/wxFormBuilder/releases)。
2. linux平台可以下载`.deb`，或者使用`.flatpak`。
3. ubuntu18.04下的安装，可以见[参考](https://nachifur.blog.csdn.net/article/details/107702485).
4. 目前MulimgViewer使用的wxFormBuilder版本为：v3.10.1。大家也可以使用最新的版本。

## 2.2 编写实现GUI的回调函数
为了分离GUI和功能实现，对于`MulimgViewer/gui`路径下的文件，不建议手动直接修改。具体的操作如下：
1. wxFormBuilder创建GUI文件`MulimgViewer/gui/main.fbp`。
2. 使用自动生成代码，生成`MulimgViewer/gui/main_gui.py`。只需在wxFormBuilder的GUI中，点击代码生成按钮即可生成`.py`。

![image](https://github.com/nachifur/MulimgViewer/blob/master/img/f19.jpg)

3. 修改`MulimgViewer/src/main.py`实现回调函数。

事实上，wxFormBuilder生成的python的GUI代码是wxpython。更多关于回调函数、事件等可见:
* [wxpython doc](https://docs.wxpython.org/index.html)
* [wxpython 自定义事件、线程安全、多线程交互、版本更新](https://nachifur.blog.csdn.net/article/details/124809333)

## 2.3 跨平台的支持
MulimgViewer的所有功能均采用python编写，这保证了跨平台的使用。但是windows和linux的路径是有区别的。**直接使用`D:\ncfey\Desktop\`，是非常糟糕的**，这会破坏跨平台。因为我们**强烈建议**使用：
```
from pathlib import Path
```
[pathlib使用说明](https://zhuanlan.zhihu.com/p/13978333) 

## 2.4 readme的维护
* 当您提出一个issue，或者决定参与该项目的开发，可以添加到[README.md-7. 未来增强功能](https://github.com/nachifur/MulimgViewer#7.0)以及[wiki-7. Future enhancements](https://github.com/nachifur/MulimgViewer/wiki#7.0)。
* 当您完成一个功能的时候，可以在issue中添加该功能的`md`说明。在下一个版本release的时候，我们会更新`README.md`（仅包含最新release版本的功能介绍）。
* 当您完成一个功能的时候，可以添加到[README.md-8. 致谢](https://github.com/nachifur/MulimgViewer#7.0)以及[wiki-8. Acknowledgements](https://github.com/nachifur/MulimgViewer/wiki#8.0)。

# 3. Release
我们的下一个release版本的计划可见[projects](https://github.com/nachifur/MulimgViewer/projects?type=classic)。

## 3.1 window的打包
1. 安装：
```
pip install wxpython pillow pytest-shutil numpy requests
```
2. Windows打包
```
cd MulimgViewer
```
便携版：
```
pyinstaller -F -w -i mulimgviewer.ico --add-data "mulimgviewer.ico;." --add-data "font/using;font/using" --add-data "img/flip_cursor.png;img" MulimgViewer.py
```
安装版：
* 打包成一个文件夹：
```
pyinstaller -D -w -i mulimgviewer.ico --add-data "mulimgviewer.ico;." --add-data "font/using;font/using" --add-data "img/flip_cursor.png;img" MulimgViewer.py
```
* 使用createinstall打包成可安装的`.exe`。[createinstall使用](https://blog.csdn.net/qq_41811438/article/details/103092610)

## 3.2 linux/ios/arm等平台的打包
ubuntu的打包可以使用`dpkg`。个人目前不了解其他平台的打包，期待大家可以帮助打包MulimgViewer！献上最真诚的感谢！

## 3.3 命名
```
MulimgViewer_3.9.3_win10_amd64_Portable.exe
MulimgViewer_3.9.3_win10_amd64_Setup.exe
MulimgViewer_3.9.3_ubuntu_amd64.deb
MulimgViewer_3.9.3_ios_amd64.ipa
```

## 3.4 镜像维护
我们目前支持以下两个镜像，release版本需要推送到这两个站点：
* [**国内gitee镜像项目**](https://gitee.com/nachifur/MulimgViewer)
* [**果壳OpenCas镜像项目**](https://github.com/opencas/MulimgViewer)