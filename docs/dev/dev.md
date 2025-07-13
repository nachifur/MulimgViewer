# MulimgViewer开发指南

## 加入我们吧！
**初衷**：目前的市面上的图像浏览器不能同时显示多张图像。2020.8.10诞生的MulimgViewer，希望可以让大家方便地进行多张图像的显示和比较。恍惚一世，希望能在这个世界留下痕迹。

**定位**：MulimgViewer，即multi-image viewer。该软件**核心功能**是：多张图像并行显示、比较。

**目标**：期待MulimgViewer走向世界的每一个角落。

**开发**：每个人都希望定制自己的MulimgViewer，但一个包含各种各样功能的软件也许不是大家喜欢的。开发一些受众较广的功能，这会帮助到更多的人，这是我们期望的。另外，进一步完善扩展核心功能也是需要的。

**如何参与开发？**
我们真诚地感谢您加入MulimgViewer的开发。

参与做出贡献的途径：（由易到难）
1. 项目的宣传。如：QQ、微信、知乎文章、CSDN博客、公众号等。
2. readme的优化。如：提升readme的易读性、完善某一功能的介绍。
3. ubuntu和ios等平台的打包。（该功能目前由@wzy负责）
4. pip安装途径的支持和维护。（该功能目前由@wzy负责）
5. 通过issue反馈bug，并提交commit解决这个bug。
6. 已有功能的改进。如：运行速度的优化、版本更新提示。
7. 新功能的开发。
8. 架构的优化。
9. 我们期待每个用户任意的改进意见！

新功能的开发：
1. 假如您有任何好的idea，在github上提一个issue。
2. 在这个issue中，我们可以讨论具体功能的实现细节。也可以在qq上交流，最后把讨论的结果记录到issue中。
3. 正常的开发流程：fork到自己本地->新建一个分支->实现功能->自行调试成功->合并到主分支。
4. 如果您希望深度地、持续地参与到项目的开发中，可以邮件(liujiawei18@mails.ucas.ac.cn)联系我。我会邀请您开发此软件，您可以获得直接访问该项目的权限，这有利于快速及时地更新主分支。

## 文件说明
项目框架：
```
MulimgViewer/src/mulimgviewer/
    * font/using                    # 7. Store preset fonts for use in displaying titles.
    * gui
        - about_gui.fbp
        - about_gui.py
        - index_table_gui.fbp
        - index_table_gui.py
        - main_gui.fbp              # 4. Using wxFormBuilder can modify the GUI interface and generate the corresponding main_gui.py file.
        - main_gui.py               # 3. The GUI of main.py
        - path_select_gui.fbp
        - path_select_gui.py
    * images
    * src
        * custom_func
            - main.py               # 11. Interface for User-customized Image Processing Functions.
        - main.py                   # 2. Main file, implementing the main logic functionality (callback functions).
        - data.py                   # 5. Load data.
        - utils_img.py              # 6. Image processing functions.
        - path_select.py            # 8. Choose the path in "Parallel manual" mode.
        - about.py                  # 9. Help.
        - index_table.py            # 10. Text List of images
        - utils.py                  # 11. Other Functions
    - __main__.py.py                # 1. Start

```
## 开发流程
### GUI的创建
GUI使用[wxFormBuilder](https://github.com/wxFormBuilder/wxFormBuilder)创建。wxFormBuilder的安装：
1. window平台可以直接下载[exe](https://github.com/wxFormBuilder/wxFormBuilder/releases)。
2. linux平台可以下载`.deb`，或者使用`.flatpak`。
3. ubuntu18.04下的安装，可以见[参考](https://nachifur.blog.csdn.net/article/details/107702485).
4. 目前MulimgViewer使用的wxFormBuilder版本为：v3.10.1。大家也可以使用最新的版本。

### 编写实现GUI的回调函数
为了分离GUI和功能实现，对于`MulimgViewer/src/mulimgviewer/gui`路径下的文件，不建议手动直接修改。具体的操作如下：
1. wxFormBuilder创建GUI文件`MulimgViewer/src/mulimgviewer/gui/main.fbp`。
2. 使用自动生成代码，生成`MulimgViewer/src/mulimgviewer/gui/main_gui.py`。只需在wxFormBuilder的GUI中，点击代码生成按钮即可生成`.py`。

![f19](https://user-images.githubusercontent.com/32936898/224470780-2f663d08-5a64-4f56-9d86-a350fbe90f81.jpg)

3. 修改`MulimgViewer/src/mulimgviewer/src/main.py`实现回调函数。

事实上，wxFormBuilder生成的python的GUI代码是wxpython。更多关于回调函数、事件等可见:
* [wxpython doc](https://docs.wxpython.org/index.html)
* [wxpython 自定义事件、线程安全、多线程交互、版本更新](https://nachifur.blog.csdn.net/article/details/124809333)

### 跨平台的支持
MulimgViewer的所有功能均采用python编写，这保证了跨平台的使用。但是windows和linux的路径是有区别的。**直接使用`D:\ncfey\Desktop\`，是非常糟糕的**，这会破坏跨平台。因为我们**强烈建议**使用：
```
from pathlib import Path
```
[pathlib使用说明](https://zhuanlan.zhihu.com/p/13978333)

### Readme | Translation
* 当您提出一个issue，或者决定参与该项目的开发，可以添加到[todo.md](https://github.com/nachifur/MulimgViewer/blob/master/docs/misc/todo.md).
* 当您完成一个功能的时候，可以在issue中添加该功能的`md`说明。在下一个版本release的时候，我们会更新`docs`（仅包含最新release版本的功能介绍）。
* 当您完成一个功能的时候，可以添加到[acknowledgements.md](https://github.com/nachifur/MulimgViewer/blob/master/docs/misc/acknowledgements.md).

**翻译**：(Refer [sphinx-intl](https://sphinx-intl.readthedocs.io).)

```sh
# 1. edit .md
vim docs/*md.
# 2. generate .po
pip install sphinx sphinx-intl myst-parser sphinxcontrib-eval
cd docs
sphinx-build -b gettext ./ build/gettext
sphinx-intl update -p ./build/gettext -l en
# 3. edit translations
vim locale/en/LC_MESSAGES/*.po
# 4. commit
git add -A
git commit
git push
```


**error**: ModuleNotFoundError: No module named 'mulimgviewer'

**fix error**: set pythonpath `windows powershell`:
```
$env:PYTHONPATH = "path_to_directory_1;path_to_directory_2"
echo $env:PYTHONPATH
```

## Release
我们的下一个release版本的计划可见[projects](https://github.com/nachifur/MulimgViewer/projects)。

### window的打包
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
pyinstaller -F -w -i ./src/mulimgviewer/mulimgviewer.png --add-data "./src/mulimgviewer/mulimgviewer.png;./src/mulimgviewer/" --add-data "./src/mulimgviewer/font/using;./src/mulimgviewer/font/using" --add-data "./src/mulimgviewer/images/flip_cursor.png;./src/mulimgviewer/images/" MulimgViewer.py
```
安装版：
* 打包成一个文件夹：
```
pyinstaller -D -w -i ./src/mulimgviewer/mulimgviewer.png --add-data "./src/mulimgviewer/mulimgviewer.png;./src/mulimgviewer/" --add-data "./src/mulimgviewer/font/using;./src/mulimgviewer/font/using" --add-data "./src/mulimgviewer/images/flip_cursor.png;./src/mulimgviewer/images/" MulimgViewer.py
```
* 使用createinstall打包成可安装的`.exe`。[createinstall使用](https://blog.csdn.net/qq_41811438/article/details/103092610)


### linux/ios/arm等平台的打包
感谢@wzy。打包目前由@wzy主要负责。

### 命名
```
MulimgViewer_3.9.3_win10_amd64_Portable.exe
MulimgViewer_3.9.3_win10_amd64_Setup.exe
MulimgViewer_3.9.3_ubuntu_amd64.deb
MulimgViewer_3.9.3_ios_amd64.ipa
```

### 镜像维护
我们目前支持以下两个镜像，release版本需要推送到这两个站点：
* [**国内gitee镜像项目**](https://gitee.com/nachifur/MulimgViewer)
* [**果壳OpenCas镜像项目**](https://github.com/opencas/MulimgViewer)
