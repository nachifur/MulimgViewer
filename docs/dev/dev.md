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

### 跨平台运行环境与视频依赖

推荐使用项目根目录的 `environment.yml` 创建环境。Windows、Linux 和 macOS 共用此文件；Conda 从 conda-forge 安装对应平台的 FFmpeg、wxPython 和其他原生依赖，pip 复用项目的 `requirements.txt` 安装 Python 依赖。环境文件不包含个人绝对路径或某个平台的构建编号。

在项目根目录执行以下命令。若已有同名环境，可用 `conda env create -n mulimgviewer-new -f environment.yml` 创建新环境；不要为了安装视频工具而覆盖已有环境。

```sh
conda env create -f environment.yml
conda activate mulimgviewer
python tools/check_video_tools.py
python MulimgViewer.py
```

macOS 的 Conda wxPython 可能需要框架启动器：在该环境安装 `conda install -c conda-forge python.app`，然后使用 `pythonw MulimgViewer.py` 启动 GUI。工具检测脚本仍使用 `python`。参见 [wxPython 官方说明](https://www.wxpython.org/pages/downloads/)。

只需为已有环境补装视频工具时，执行 `conda install -n mulimgviewer -c conda-forge ffmpeg`，并使用该环境的 Python 运行 `tools/check_video_tools.py`。此脚本会输出实际解释器和两个工具的路径、执行版本检查，失败时以非零状态退出；`ffmpeg-python` 是调用封装，不能代替 FFmpeg 和 FFprobe 可执行程序。

工具查找顺序为：`FFMPEG_BINARY` / `FFPROBE_BINARY` 显式设置、当前 Python 环境、系统 PATH、平台常见目录、可选的 `tools/ffmpeg/bin`、当前环境登记的同版本 Conda 包缓存。Windows 使用 `.exe` 与 `Library/bin`；Linux/macOS 使用无扩展名程序与 `bin`。过期的 `CONDA_PREFIX` 不会覆盖实际运行的解释器。程序只为子进程构造依赖搜索路径，不修改系统 PATH，不自动安装或下载软件。

`tools/ffmpeg/bin` 只是便携部署的可选兜底，不是运行所必需的目录，也不能把 Windows 的 `.exe` 分发给 Linux/macOS 使用。该目录中的本机二进制已加入 Git 忽略规则。Conda 安装和环境管理方式参见 [conda-forge FFmpeg](https://anaconda.org/channels/conda-forge/packages/ffmpeg) 和 [Conda 环境文档](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html)。

如果包记录显示 FFmpeg 已安装，但文件缺失，可执行 `conda install -n mulimgviewer -c conda-forge --force-reinstall ffmpeg` 后重新检测。若文件再次消失或启动被拒绝，需要检查本机的文件删除、隔离或权限原因；仅重新配置 PATH 无法修复缺失的程序。

`.github/workflows/video-environment.yml` 在 Windows、Linux、macOS 上从该环境文件安装依赖，检查 FFmpeg/FFprobe 能否启动、原生 Python 依赖能否导入，并执行不依赖 GUI 的工具查找测试。这些检查不等同于三平台完整 GUI 回归；完整功能回归仍使用下面的入口执行。

### 开发回归测试与 PR 审查

开发新功能或修复问题时，请按下面的顺序检查已有功能，并把对应的测试报告附在 PR 中，方便维护者审查。

#### 第 1 步：进入项目并确认 Python 环境

在项目根目录打开终端，此目录应包含 `MulimgViewer.py`、`src` 和 `auto_test_scripts`。使用能够正常启动软件的 Python 环境；如果使用 Conda，将下面的环境名称替换为自己的名称。

```sh
conda activate mulimgviewer
python -c "import sys; from pathlib import Path; print(sys.executable); print(Path.cwd()); assert Path('MulimgViewer.py').is_file()"
```

下面的测试命令均从项目根目录执行。测试使用独立进程和临时目录，不需要开发者提供自己的图片、视频或个人配置。

#### 第 2 步：安装依赖并准备视频工具

```sh
python -m pip install -r auto_test_scripts/requirements.txt
```

视频测试还需要 FFmpeg 和 FFprobe。如果当前环境没有这两个工具，使用 Conda 的开发者可以执行：

```sh
conda install -c conda-forge ffmpeg
```

测试入口会使用软件的视频工具定位机制检查依赖。依赖缺失时会生成失败报告，不能视为测试通过。

Windows 也可以在已激活的环境中双击 `auto_test_scripts/run_tests.cmd`。如果双击时使用了错误的 Python，可在 PowerShell 中指定解释器；把示例路径替换为自己的路径。

```powershell
$env:MULIMGVIEWER_PYTHON = 'C:\path\to\environment\python.exe'
& .\auto_test_scripts\run_tests.cmd --strict-skips
```

Linux 和 macOS 可使用同一个 Python 入口，或执行 `sh auto_test_scripts/run_tests.sh`。GUI 测试需要图形会话；无显示器的 Linux 环境在安装 Xvfb 后使用：

```sh
xvfb-run -a python auto_test_scripts/run_tests.py --strict-skips
```

#### 第 3 步：执行完整回归测试

```sh
python auto_test_scripts/run_tests.py --strict-skips
```

等待所有模块结束，确认最终状态为 `PASSED`，且命令退出码为 0。执行通常需要几分钟。`--strict-skips` 要求没有跳过的案例；失败、异常、缺少依赖、超时或跳过都会使本次严格检查不通过。

执行期间不要修改源码、测试脚本和固定素材，也不要在同一份工作目录同时启动多次全量测试。报告记录提交 SHA、未提交改动，以及源码、测试和素材的指纹；运行期间发生变化时，需要重新执行。

回归范围包括图像和视频播放、四种输入模式、并行与顺序组合、布局与标题、自定义算法、两层缓存、索引与状态栏、配置恢复，以及七种输出组合、三种保存格式、后台保存和暂停续存。固定 PNG、自定义处理和拼接结果使用像素比较，视频解码结果使用已知帧校验。

固定素材位于 `auto_test_scripts/assets`，包含小型图像、视频、相对路径列表和期望结果，合计约 38 KB。测试不会在正常执行时自动重建期望结果。既有 Windows 验证记录位于 `auto_test_scripts/baseline/verified.json`；实际案例数量以本次报告为准。

#### 第 4 步：打开报告并确认结果

每次执行生成 `auto_test_scripts/reports/<UTC时间>/`。读取 `auto_test_scripts/reports/latest.json` 的 `directory` 字段，即可找到最近一次执行的目录。Windows PowerShell 可执行：

```powershell
$reportInfo = Get-Content -Raw auto_test_scripts/reports/latest.json | ConvertFrom-Json
$reportPath = Join-Path auto_test_scripts/reports $reportInfo.directory
Invoke-Item (Join-Path $reportPath 'report.html')
```

| 文件 | 用途 |
| --- | --- |
| `report.html` | 查看功能分组、案例状态、参数子案例和错误堆栈。 |
| `report.json` | 核对提交、源码指纹、测试环境和完整结果。 |
| `junit.xml` | 供 CI 和 JUnit 工具解析结果。 |
| `summary.md` | 查看失败、跳过和环境错误摘要。 |
| `test_*.log` | 查看对应测试模块的执行日志。 |

`PASSED` 表示本次选择的案例全部通过，`PASSED_WITH_SKIPS` 表示存在跳过，`FAILED` 表示检查未通过。审查完整回归时，还要确认没有未执行的模块、功能分组均完成验证。仅运行部分案例得到的通过结果，不能代替全量报告。

#### 第 5 步：定位失败并重新验证

先在 HTML 报告中找到失败案例及其输入模式、输出组合、布局和格式，再查看同名模块的日志。可用下面的命令缩小范围：

```sh
python auto_test_scripts/run_tests.py --list
python auto_test_scripts/run_tests.py --module test_export_modes --module test_reference_workflows
python auto_test_scripts/run_tests.py --module test_video_gui_async --case '*background_save*'
```

也可以重跑某份报告中的失败案例。在已经执行第 4 步的 PowerShell 终端中运行：

```powershell
python auto_test_scripts/run_tests.py --failed "$reportPath/report.json"
```

先区分产品错误、过期的测试假设和环境问题，再处理失败。不要通过删除断言、把失败改成跳过或自动覆盖期望图片来获得通过结果。修复后必须再次执行第 3 步的全量严格检查。

#### 第 6 步：为代码修改补充测试

新增案例放在 `auto_test_scripts/cases/test_*.py`，使用 unittest；入口会自动发现。多个输入、布局和输出组合应使用带明确参数的 `subTest`，使失败报告能够定位具体组合。同步更新 `auto_test_scripts/coverage.json` 中的功能映射。

测试应使用固定素材或私有临时副本，避免依赖个人绝对路径、网络和用户文件。新增异步功能应检查任务依赖、内存准入、暂停、取消和关闭清理；新增保存功能应检查文件内容、实际格式和目录结构。

只有在明确修改了素材规范时，才运行 `python auto_test_scripts/generate_assets.py`。同时审查素材生成规则、输入、期望结果和 `manifest.json` 的变化，避免把错误输出当作新的正确答案。

#### 第 7 步：提交 PR 并附上测试报告

提交前确认代码和测试已经完成修改，再执行全量严格检查。PR 中说明修改目的、受影响功能、新增案例及仍需人工检查的项目，并填写 PR 模板中的回归验证部分。

提交 PR 后，在 GitHub Actions 中打开 **Functional regression report** 工作流，确认 `windows-regression` 任务通过，并下载对应提交的报告产物。把该次 CI 执行或产物的链接附在 PR 中；如果提供本地报告，应将 HTML、JSON、JUnit 和模块日志打包附上。

自动生成的 `auto_test_scripts/reports` 已被 Git 忽略，不需要把每次日志提交到仓库。`baseline/verified.json` 是既有基线，不能替代本次 PR 的报告。代码再次修改后，需要重新运行测试并更新报告链接。

维护者审查时，依次核对报告是否对应 PR 的最新提交、是否完成全量检查、失败和跳过是否得到解释，以及本次修改是否补充了相关案例。仓库管理员可在分支保护或仓库规则中，将 `windows-regression` 设为必需检查，从而阻止测试失败的 PR 合并。

目前 CI 工作流配置为 Windows。Linux/macOS、实际 GPU 驱动与硬件、系统对话框外观及长时间运行仍应根据修改范围补充验证。详细案例和维护规则见 `auto_test_scripts/README.md`。

### Readme | Translation
* 当您提出一个issue，或者决定参与该项目的开发，可以添加到[todo.md](https://github.com/nachifur/MulimgViewer/blob/master/docs/misc/todo.md).
* 当您完成一个功能的时候，可以在issue中添加该功能的`md`说明。在下一个版本release的时候，我们会更新`docs`（仅包含最新release版本的功能介绍）。
* 当您完成一个功能的时候，可以添加到[acknowledgements.md](https://github.com/nachifur/MulimgViewer/blob/master/docs/misc/acknowledgements.md).

#### 第 1 步：修改中文源文档

从项目根目录编辑需要更新的 Markdown 文件，例如 `docs/dev/dev.md`。中文源文档是维护入口；英文版本通过 Sphinx 的语言目录生成，不需要再维护一份独立的英文 Markdown 副本。

```sh
vim docs/dev/dev.md
```

#### 第 2 步：生成并更新英文 PO 词条

在项目根目录执行以下命令。先确认 Sphinx 成功生成 `docs/_build/gettext/dev/dev.pot`，再更新 PO。

```sh
python -m pip install sphinx sphinx-intl myst-parser sphinxcontrib-eval
python -m sphinx -b gettext docs docs/_build/gettext
python -m sphinx_intl update -p docs/_build/gettext -d docs/locale -l en
```

这些命令会自动提取中文并更新 PO 词条，不会自动完成英文翻译。开发指南对应的文件是 `docs/locale/en/LC_MESSAGES/dev/dev.po`。已有翻译会保留，新增或修改的内容需要补充或核对英文。

如果提示 `Invalid value for pot_dir`，先检查当前目录和上一步的 `gettext` 构建日志。`-p` 必须指向实际生成 `.pot` 的目录。如果上一步生成到了 `docs/build/gettext`，请把 `-p` 改为 `docs/build/gettext`，或者按上面的命令重新生成。

#### 第 3 步：填写对应的英文翻译

在项目根目录编辑对应的 PO 文件。

```sh
vim docs/locale/en/LC_MESSAGES/dev/dev.po
```

保留 `msgid` 中的中文原文，在 `msgstr` 中填写英文。保留命令、文件路径、格式名称和参数名称；检查 Markdown 链接和代码标记。带 `fuzzy` 标记的词条需要人工确认，确认后移除该标记，否则构建时可能继续显示中文。

```po
msgid "开发回归测试与 PR 审查"
msgstr "Development regression testing and PR review"
```

#### 第 4 步：构建并检查英文页面

```sh
python -m sphinx_intl build -d docs/locale -l en
python -m sphinx -b html -D language=en docs docs/_build/html/en
```

打开 `docs/_build/html/en/dev/dev.html`，确认新增章节显示英文，操作步骤、命令和表格完整。检查构建日志中的错误及与本次修改相关的警告；生成 PO 成功不代表翻译已经完成。

如果出现 `ModuleNotFoundError: No module named 'mulimgviewer'`，在项目根目录执行 `python -m pip install -e .`，然后重新构建。

#### 第 5 步：提交文档和对应翻译

把修改后的 Markdown 与对应 PO 文件一起提交，例如 `docs/dev/dev.md` 和 `docs/locale/en/LC_MESSAGES/dev/dev.po`。检查暂存差异，保留无关文档的既有翻译；不要提交 `_build`、生成的 MO 文件或本地测试日志。


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
