# GPU Sharpen

演示 API v2 的 GPU 批处理接口，不需要模型权重，也不保存文件。

- 重新打开软件，在 GUI 算法列表选择 GPU Sharpen，勾选自定义算法显示，然后点击 Refresh。
- setup() 为当前算法会话创建一次固定锐化卷积模块；后续批次复用同一个模块。
- process_batch() 按输入尺寸分组，每批最多 8 张，目标总像素不超过 200 万；大图允许单张处理。输出保持原尺寸、原顺序，转换为 RGB。
- GPU 处理包含 CPU→GPU 上传、GPU→CPU 回传；小图未必比 CPU 快。
- 需要 NVIDIA CUDA 环境以及与驱动兼容的 CUDA 版 PyTorch。PyTorch 为可选依赖，不会自动安装或下载权重。
- 没有 PyTorch/CUDA 时，初始化提示后使用相同滤波的 CPU 实现，因此不影响 Show all functions。个别小批次显存不足时也提示并回退 CPU；其他错误正常报告。
- 主内存仍受应用的批处理预算约束。小批量限制减少显存峰值，但不是任意设备的显存硬隔离。
- teardown() 在设备模型被框架卸载时释放该模块；正常批次之间不反复加载或清空显存。

改成自己的检测／分割模型时，把权重加载放到 setup()，把预处理、推理、可视化放到 process_batch()，最终返回与输入数量及顺序一致的 Pillow 图像。修改算法后使用 Refresh 应用。


## 修改自己的算法时看哪里

main.py 中标有中文注释，通常只需修改两处：

| 位置 | 用途 | 是否需要修改 |
| --- | --- | --- |
| build_model(torch) | 创建自己的模型、加载权重 | 需要 |
| process_gpu_batch(images, context) | 自己的预处理、推理及可视化，返回 Pillow 图片列表 | 需要 |
| run_cpu=cpu_sharpen | 无 CUDA/显存不足时的 CPU 算法 | 更换算法时必须检查：改成自己的 CPU 函数，或设为 None 禁用回退 |
| MAX_BATCH_IMAGES / MAX_BATCH_PIXELS | GPU 小批次大小 | 可选调整 |
| setup / process_batch / teardown | 框架固定入口，连接初始化、调度、释放 | 通常不用改，请保留函数名和参数 |

图片读取、缓存、拼接、保存和线程管理由应用完成，不要复制到算法中。

无需修改的尺寸分组、顺序恢复、CPU 回退和资源管理已移到 `custom_func/gpu_support.py`。复制本示例创建新算法时，保留 plugin.json 的 API v2/batch/device 声明及 cache_dependencies；shared helper 属于软件的一部分。权重变化应更新 cache_version 或 cache_dependencies。

转换辅助函数只适用于本锐化示例的 RGB、float32、NCHW、0~255 数据。自己的模型若要求 0~1、归一化输入，或返回检测框/分割标签，需要在 process_gpu_batch 中自行调整预处理和后处理，不可直接套用转换函数。build_model 应返回 PyTorch 模型模块；辅助函数负责设为 eval、关闭梯度并移到 cuda:0。
