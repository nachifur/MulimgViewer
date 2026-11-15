"""GPU 自定义函数模板：通常只需修改 build_model 和 process_gpu_batch。

框架自动调用 setup（同一会话初始化一次）、process_batch（每批调用）、
teardown（设备模型卸载时调用）。不要在这里保存文件或操作 GUI。
"""
from mulimgviewer.src.custom_func.gpu_support import (
    create_context, process_images, release_context,
    images_to_tensor, tensor_to_images, cpu_sharpen,
)

# 【可选调整】限制单个 GPU 小批次；不同尺寸的图片自动分组。
MAX_BATCH_IMAGES = 8
MAX_BATCH_PIXELS = 2_000_000


# 【需要修改 1】创建自己的模型、加载权重；框架负责移到 GPU 并设为推理模式。
def build_model(torch):
    # 示例：固定锐化卷积，无需下载权重。替换为自己的模型即可。
    convolution = torch.nn.Conv2d(3, 3, 3, groups=3, bias=False)
    with torch.no_grad():
        kernel = torch.tensor([[0., -1., 0.], [-1., 5., -1.], [0., -1., 0.]])
        convolution.weight.copy_(kernel.reshape(1, 1, 3, 3).repeat(3, 1, 1, 1))
    return torch.nn.Sequential(torch.nn.ReplicationPad2d(1), convolution)


# 【需要修改 2】自己的预处理 → GPU 推理 → 绘制/后处理。
def process_gpu_batch(images, context):
    # images：同尺寸的 Pillow 图片列表；context['model']：复用的 GPU 模型。
    # 必须返回同数量、同顺序的 Pillow 图片；检测/分割结果也要先绘制成图片。
    torch = context['torch']
    with torch.inference_mode():
        tensor = images_to_tensor(images, context)  # RGB，NCHW，float32，范围 0~255
        result = context['model'](tensor)
        return tensor_to_images(result)  # 示例输出也是 NCHW、RGB、范围 0~255


# 【通常不用修改】以下是框架的三个固定接口，请保留函数名和参数。
def setup():
    return create_context(build_model)


def process_batch(images, *, context):
    return process_images(
        images, context=context, run_gpu=process_gpu_batch,
        # 【更换算法时检查】换成自己的 CPU 实现；不支持 CPU 时设为 None。
        run_cpu=cpu_sharpen,
        max_batch_images=MAX_BATCH_IMAGES, max_batch_pixels=MAX_BATCH_PIXELS,
    )


def teardown(context):
    release_context(context)
