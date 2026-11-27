# 开发指南

从项目根目录按[下载与安装](../resources/install.md)创建环境。修改前先用仓库的微型素材跑通目标操作；修改后用相同输入比较显示、缓存和导出结果。

## 从功能找到入口

下表中的实现文件位于 `src/mulimgviewer/src/`，界面定义位于同级的 `gui/`。

| 要修改的行为 | 从这里读起 |
| --- | --- |
| 主窗口、打开来源、按钮和绘图交互 | `main.py`；图像来源与索引数据见 `data.py` |
| 拆帧、长视频寻帧、视频缓存调度 | `video_source.py`、`video_decoder.py`、`video_manager.py` |
| 图像异步显示、播放节奏、任务预算 | `image_pipeline.py`、`playback_controls.py`、`playback_policy.py`、`pipeline_executor.py` |
| 算法执行、布局、缓存路径 | `custom_pipeline.py`、`render_layout.py`、`cache_layout.py` |
| 后台保存与编码 | `export_controller.py`、`image_encoding.py` |
| 配置、右侧设置栏、状态栏和索引表 | `configuration.py`、`settings_panel.py`、`status_bar.py`、`index_table.py` |

### 修改 GUI

1. 用 wxFormBuilder 打开对应的 `.fbp`，例如 `src/mulimgviewer/gui/main_gui.fbp`，修改控件和事件绑定。
2. 运行 `python tools/generate_gui.py` 重新生成界面。若生成器不在 PATH，在命令末尾加 `--generator "可执行文件的完整路径"`。用 `--check` 检查生成文件与定义是否匹配。
3. 在实现层连接回调。布局参数沿用“修改多项后手动刷新”的交互；后台任务使用应用后的设置，保存使用点击时的参数。新增设置需检查加载、保存、重置和旧配置兼容。
4. 打开主窗口实际操作一次，覆盖图像和视频两条入口，再执行对应测试。

新增界面语言时，在 `src/mulimgviewer/src/languages.py` 登记稳定的语言代码、菜单名称和手册路径，在 `src/mulimgviewer/src/locales/<code>.json` 添加 UTF-8 译表。参考已有译表，保留英文键、格式占位符、快捷键和技术参数。运行配置回归测试，核对语言切换、设置保存与重置。

### 添加图像处理算法

在 `src/mulimgviewer/src/custom_func/<算法名>/main.py` 中实现单图核函数。例如内置的 Gaussian Blur：

```python
from PIL import ImageFilter

THREAD_SAFE = True

def process_image(image, *, context):
    return image.filter(ImageFilter.GaussianBlur(radius=2))
```

输入和返回值均为 Pillow 图像，缓存与导出由框架负责。只有可安全并发调用的算法才声明 `THREAD_SAFE = True`。需要复用模型时，用 `setup()` 返回上下文，处理函数从 `context` 取得模型；框架在算法会话内复用它。批处理实现 `process_batch(images, *, context)`，输出与输入数量、顺序一致。设备、批量和释放接口可参照仓库的 `examples/custom_func/GPU Sharpen/`。

调试时先用 **Selected** 验证单算法，再用 **All algorithms** 对照。源帧就绪后，后台可处理各算法，生成各自的拼接，再合成最终页面。检查布局变化、快速跳页和关闭窗口时过期结果的处理；只测单个函数的耗时不能说明整页播放性能。

## 性能与回归

做性能对比时固定来源、布局、显示比例、算法和缓存窗口，分别记录冷启动首屏、深处跳转首屏、稳定播放与供给 FPS、CPU 和内存。记录性能模式、操作系统和处理器，区分首次构建与已经命中缓存的结果。工具和用法可从 `python auto_test_scripts/performance/benchmark_video_playback.py --help` 开始。

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

(desktop-bundle)=
## 构建桌面离线包

**一次构建多个平台。** 在 GitHub 仓库进入 **Actions → Desktop packages → Run workflow**，选择分支并运行。矩阵分别在 Windows x64、Linux x64/ARM64、macOS Intel/Apple Silicon 上构建。每项通过解压自检后才上传自己的 artifact；在运行详情页下载，解开 GitHub 外层 ZIP 即可取得实际软件包。此操作只生成候选包，发布版本时再选择附件。

**本机打包。** 在目标系统的 Git 工作副本根目录运行以下命令。Linux 需要图形桌面；无显示器时安装 Xvfb 和 xauth，并将最后一行换成 `xvfb-run -a python tools/package_desktop.py --compact`。构建时需要联网获取依赖，并预留运行环境、压缩包和解压副本的空间。

```sh
conda create -y -n mulimg-builder -c conda-forge python=3.11
conda activate mulimg-builder
python tools/package_desktop.py --compact
```

三个平台都在 `dist/desktop/` 生成带有系统和架构名称的 `.tar.xz`。省略 `--compact` 时，Windows 使用 ZIP，Linux 和 macOS 使用 tar.gz。解压后按[下载与安装](../resources/install.md)启动。macOS 产物未经签名和公证，Linux 需要兼容的系统库和图形会话。

**构建与验收。** 脚本按照 `environment.yml` 创建临时 Conda 环境，禁用个人默认加装包，并在临时环境中安装 PyInstaller。PyInstaller 以目录模式收集依赖，脚本显式加入 FFmpeg、FFprobe、内置算法和资源，解压自检通过后才输出归档。

新增内置算法时，请将源文件和资源加入 Git。动态导入的算法依赖需加入构建环境并确认 PyInstaller 已收集。发布前请在干净的目标机器上打开两段视频、运行实际算法、导出并重新打开结果。

紧凑压缩保留相同的运行文件，以更多构建时间和临时磁盘空间换取更小的下载体积。

比较打包器时，在 **Actions → Compare desktop packages** 对同一提交运行对照。每个原生平台分别生成 Conda 与 PyInstaller 目录版的 `.tar.xz`，用解压后的程序检查窗口、视频、内置算法和导出。任务摘要记录通过验证的下载字节数。请在相同系统及处理器架构下比较，并用实际要分发的自定义算法再试一次。

## 构建文档与维护翻译

[多语言维护教程](localization.md)包括界面译表、完整手册、回归检查和 Read the Docs 发布流程。

## 准备发布版本

维护者请按[新版本构建与发布](release.md)准备发布提交、验证安装包并推送正式标签。
