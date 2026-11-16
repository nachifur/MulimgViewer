# 开发与 PR 回归测试

这里集中维护功能回归、固定输入、像素基准、性能工具和报告入口。测试不参与软件正常运行。

## 一键执行

使用**运行 MulimgViewer 的 Python 环境**（建议 Python 3.10+，CI 使用 3.11）：

```sh
python -m pip install -r auto_test_scripts/requirements.txt
python auto_test_scripts/run_tests.py
```

Windows 也可以在激活应用环境后双击 `run_tests.cmd`。如果双击时找不到正确环境，先设置环境变量 `MULIMGVIEWER_PYTHON` 为 Python 可执行文件的绝对路径。Linux/macOS 可执行 `sh auto_test_scripts/run_tests.sh`。

FFmpeg、FFprobe 必须可用。入口沿用应用的跨平台定位机制，把找到的工具加入子进程 PATH；依赖缺失会生成失败报告并返回非零退出码，不会把未执行的视频案例显示为通过。真实 wx GUI 测试需要图形会话；无显示器 Linux 使用：

```sh
xvfb-run -a python auto_test_scripts/run_tests.py
```

本地 Windows 完整运行通常需要几分钟。不要同时在同一 checkout 启动多份全量测试，也不要在执行期间修改被测代码或测试素材；入口会对提交、源码、测试和素材取指纹，运行中变更会使报告失败。

## 报告与 PR 审查

每次运行生成 `reports/<UTC时间>/`，`reports/latest.json` 指向最近一次运行：

| 文件 | 用途 |
|---|---|
| `report.html` | 开发者查阅：功能分组、成功/失败案例、子案例参数与错误堆栈 |
| `report.json` | 完整机器可读结果、提交 SHA、未提交改动、源码/测试/素材指纹、环境 |
| `junit.xml` | CI/JUnit 工具解析失败和跳过案例 |
| `summary.md` | PR/CI 摘要，列出失败和跳过项 |
| `test_*.log` | 每个模块的标准输出、异常和 unittest 日志 |
| `test_*.json` | 模块原始结果，便于定位崩溃前已经完成的案例 |
| `workspaces/` | 模块独立工作目录；不作为待提交文件 |

结果分为 `PASSED`、`PASSED_WITH_SKIPS`、`FAILED`。失败、环境错误、超时、进程崩溃、后台未捕获异常和空案例选择均不能得到通过报告。`--strict-skips` 要求零跳过，CI 默认启用。报告区分 unittest 方法数与方法内的参数子案例数；不能把它们相加宣称为独立端到端工作流数。

提交 PR 时，在最新代码上运行全量测试，附上 CI 的 **Functional regression report** 工作流/产物链接，或将 HTML、JSON、JUnit 和日志打包附上。`.github/PULL_REQUEST_TEMPLATE.md` 提供检查项。工作流会在 PR 自动运行，并在成功和失败时均上传报告；不会自动评论或向他人发送消息。需要管理员在仓库分支保护中将 `windows-regression` 设为必需检查，才能强制阻止失败 PR 合并；本次没有修改远程仓库设置。

审查时核对报告的提交 SHA/源码指纹、完整功能分组、失败/跳过和未执行项，不接受仅运行部分案例作为全量通过的证据。不要只看截图或一行“通过”。`baseline/verified.json` 是本次整理时的本地验证记录，不替代未来 PR 自己的报告。CI 工作流目前覆盖 Windows；Linux/macOS 可运行同一入口，但这里不宣称已在未实测的平台通过。

## 维护与复现失败

```sh
# 列出测试模块
python auto_test_scripts/run_tests.py --list

# 只检查保存和固定素材工作流
python auto_test_scripts/run_tests.py --module test_export_modes --module test_reference_workflows

# 在指定模块内定位单个案例；--case 也支持完整 id 或通配符
python auto_test_scripts/run_tests.py --module test_video_gui_async --case '*background_save*'

# 按失败报告重跑失败案例（属于局部验证，不替代全量运行）
python auto_test_scripts/run_tests.py --failed auto_test_scripts/reports/<时间>/report.json

# 提交前要求所有案例均执行，无跳过
python auto_test_scripts/run_tests.py --strict-skips
```

`--timeout` 默认每模块 600 秒，超时会终止该模块及其子进程，记录错误并继续其余模块。筛选案例时应同时限定模块；匹配不到案例是错误。多个模块顺序运行、每模块使用独立进程，以隔离 wx.App、后台线程、当前目录和测试替身，避免模块间污染。

新增测试放进 `cases/test_*.py`，采用 unittest；入口自动发现。多个模式使用带具体参数的 `subTest`，失败报告会指出输入、输出、布局和格式。新增功能同步更新 `coverage.json` 的功能映射。避免依赖开发者的个人文件、绝对路径、GPU 或网络。用临时目录和可控事件验证异步行为；不要仅靠短暂 sleep 或“CPU 必须超过某个百分比”判断成功。

修复失败应先分清产品错误、过期的测试假设和环境限制。不要删除失败断言、把错误改为 skip，或在正常运行时从当前程序自动更新期望图片。本轮旧测试明确指定 PNG 场景，并将过时的 JPEG getsize 拦截替换为实际后台维护入口，继续验证同样的缓存边界与 GUI 非阻塞要求。

## 目录

```text
auto_test_scripts/
  run_tests.py / run_tests.cmd / run_tests.sh
  requirements.txt
  coverage.json                  # 主要功能与测试模块对应关系
  cases/                         # 自动发现的回归案例
  support/                       # 执行子进程、结果格式、独立像素算法
  assets/                        # 约36 KB固定图像、视频、列表和期望结果
  generate_assets.py             # 显式重建素材；普通测试不调用
  performance/                   # FPS/CPU/100路4K等可选基准，不纳入功能通过门槛
  history/                       # 整理前的性能测试记录，仅供参考
  baseline/                      # 本次已验证的摘要
  reports/                       # 自动生成，git忽略
```

所有固定素材和测试源码都在本目录。会话配置、挑图、移动、旋转、EXIF 写入、缓存清理和后台导出使用私有临时副本或隔离资源路径；不把软件的真实配置和用户视频作为测试输入。临时大图/长视频场景按需生成，不提交 GitHub。

## 主要功能覆盖

| 功能 | 核心模块/检查 |
|---|---|
| 图像/视频 + Sequential、Parallel auto/manual、File List | `test_reference_workflows`：真实显示与后台保存，8种输入情形×7种输出×3种格式 |
| parallel_to_sequential、parallel_sequential、嵌套/稀疏布局、尾页 | `test_export_modes`、`test_browsing_index`、`test_video_gui_async` |
| 显示、连续/反向播放、跳转、1起始滑块、间隔与用户下限 | `test_video_gui_async`、`test_video_interval`、`test_playback_pacer` |
| 状态栏、来源路径/视频时间、索引定位/跳转、虚拟帧、Excel | `test_status_bar`、`test_browsing_index`、`test_index_excel` |
| 自定义算法单选/全选、原图显示、画布容量和空白色 | `test_custom_pipeline`、`test_video_gui_async`、`test_reference_assets` |
| 用户CPU核函数并行、GPU批接口一次setup、顺序/并发约束 | `test_custom_kernel`、`test_custom_functions`（GPU协议使用可控替身） |
| 原始帧/处理/小拼接/大合成，缓存租约与动态回收 | `test_cache_layout`、`test_custom_pipeline`、`test_video_cache`、`test_cache_shutdown` |
| JPG/PNG/auto、透明度、无损保存、高清缓存复用 | `test_cache_quality`、`test_reference_assets`、`test_video_gui_async` |
| 七种输出组合、带框图、放大图编号、并行挑图、移动保护 | `test_export_modes`、`test_reference_workflows` |
| 后台保存点击快照、批量多线程、Esc暂停、取消续存、关闭 | `test_export_modes`、`test_video_gui_async` |
| 配置补参/迁移、Load/Save/Reset、退出恢复、手动Refresh | `test_configuration`、`test_video_gui_async` |
| 缩放、标题/字体色、自动窗口、旋转/翻转、Unicode EXIF | `test_video_gui_async`、`test_reference_assets` |
| 精确解码、跳帧/VFR/倒放/视频旋转、有限内存4K布局 | `test_video_pipeline`、`test_video_conversion`、`test_reference_assets` |
| 四档预算、线程/内存准入、依赖调度、资源显示 | `test_thread_optimizer`、`test_stage_allocator`、`test_admission_optimizer`及调度/监测模块 |
| 报告自身不产生假通过 | `test_reporting`：故意失败的内层用例必须被正确记录、依赖错误返回非零 |

固定 PNG 与自定义算法图像使用逐像素比较；真实 MP4 分别通过常驻解码和 FFmpeg 分支与独立帧哈希核对。显示/保存工作流会验证实际格式、输出组合和可解码性；PDF 另检查无损嵌入与标题路径，不依赖每次变化的 PDF/JPEG 压缩字节。

这些检查针对已有主要功能和已知回归，不能证明任意用户插件、实际 CUDA 驱动/显卡、所有系统字体/native dialog 外观、远程版本检查或长时间真实设备运行都没有问题。手动路径选择测试使用受控输入而不操作系统对话框；真实处理、解码、事件循环和保存仍执行产品代码。Windows 账户若不能创建符号链接，缓存根保护案例明确记录为链接元数据模拟并断言删除函数从未调用；不会宣称测到了实际系统链接。

性能基准独立于功能门槛，因为 FPS/CPU 受硬件、磁盘与负载影响。按需使用：

```sh
python auto_test_scripts/performance/benchmark_video_playback.py --help
python auto_test_scripts/performance/benchmark_video_stress.py --help
```
