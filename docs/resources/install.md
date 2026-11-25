# 安装与自检

## 运行当前源码版

以下命令适用于 Windows、Linux 和 macOS。先安装 Git 和 Conda，在终端（Windows 可用 Anaconda Prompt）执行：

```sh
git clone https://github.com/nachifur/MulimgViewer.git
cd MulimgViewer
conda env create -f environment.yml
conda activate mulimgviewer
python tools/check_video_tools.py
python MulimgViewer.py
```

已有仓库时，从项目根目录的第三条命令开始；已有可用环境时，从激活环境开始。`environment.yml` 指定 Python 3.11，由 conda-forge 安装 wxPython、FFmpeg 和 PyAV。以后启动只需激活同一环境，在仓库根目录执行最后一条命令。

**Windows 安装包**可在 [GitHub Releases](https://github.com/nachifur/MulimgViewer/releases) 按版本下载。如果要使用本手册演示的并行视频、自定义算法和后台导出，请先核对安装包版本。使用源码可与当前手册保持一致。

## 验证安装

| 检查 | 怎么做 | 应该看到什么 |
| --- | --- | --- |
| 图形界面 | 启动程序，选择 Sequential，打开 `auto_test_scripts/assets/images/source_001` | 能显示图像并翻页 |
| 视频工具 | 运行 `python tools/check_video_tools.py` | 列出当前解释器、FFmpeg 和 FFprobe 的路径，两个程序均可执行 |
| 多视频播放 | 勾选 Video mode，用 Parallel auto 打开 `docs/media/example-videos`，页面网格设为 `1,2` 后刷新 | 两个视频来源并排显示，播放时一起更新 |

如果提示找不到 FFmpeg 或 FFprobe，在当前环境执行 `conda install -c conda-forge ffmpeg`，再运行检测脚本。在 IDE 中调试时，选择检测脚本输出的同一个 Python 解释器。使用自行安装的工具时，可用环境变量 `FFMPEG_BINARY`、`FFPROBE_BINARY` 分别指定两个可执行文件的完整路径。

如果 Linux 上安装 wxPython 时提示缺少 GTK，先确认已用仓库的 Conda 环境安装原生依赖。macOS 如提示 wxPython 需要框架启动器，可在该环境安装 `conda install -c conda-forge python.app`，然后用 `pythonw MulimgViewer.py` 启动。
