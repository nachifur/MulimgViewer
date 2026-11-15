"""Reusable batching, conversion and fallback helpers for the GPU example."""
import warnings
import numpy as np
from PIL import Image

def _cpu_context(reason):
    warnings.warn('GPU Sharpen: ' + reason + '; using CPU fallback.', RuntimeWarning, stacklevel=2)
    return dict(backend='cpu', oom_warned=False)


def create_context(build_model):
    """Called once per algorithm session, never once per image."""
    try:
        import torch
    except (ImportError, OSError) as error:
        return _cpu_context('CUDA PyTorch is unavailable (' + str(error) + ')')
    if not torch.cuda.is_available():
        return _cpu_context('CUDA is unavailable')
    device = torch.device('cuda:0')
    model = build_model(torch)
    model.requires_grad_(False).eval().to(device)
    return dict(backend='cuda', torch=torch, device=device, model=model, oom_warned=False)


def _rgb_array(image):
    rgb = image.convert('RGB')
    try:
        return np.array(rgb, dtype=np.uint8, copy=True)
    finally:
        rgb.close()


def cpu_sharpen(image):
    pixels = _rgb_array(image).astype(np.int16)
    edge = np.pad(pixels, ((1, 1), (1, 1), (0, 0)), mode='edge')
    result = 5*pixels-edge[:-2, 1:-1]-edge[2:, 1:-1]-edge[1:-1, :-2]-edge[1:-1, 2:]
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def images_to_tensor(images, context):
    """RGB Pillow inputs -> float32 NCHW tensor on the configured device."""
    torch = context['torch']
    arrays = np.stack([_rgb_array(image) for image in images])
    tensor = torch.from_numpy(arrays).to(context['device'], dtype=torch.float32)
    return tensor.permute(0, 3, 1, 2).contiguous()


def tensor_to_images(tensor):
    """NCHW RGB tensor in [0,255] -> independent CPU Pillow outputs."""
    import torch
    torch_tensor = tensor.clamp(0, 255).round().to(dtype=torch.uint8)
    arrays = torch_tensor.permute(0, 2, 3, 1).contiguous().cpu().numpy()
    return [Image.fromarray(array.copy()) for array in arrays]


def process_images(images, *, context, run_gpu, run_cpu, max_batch_images=8, max_batch_pixels=2_000_000):
    """Preserve source sizes/order; return one RGB Pillow result per input."""
    if context['backend'] == 'cpu':
        # Yielding also lets the framework close prior outputs on a later error.
        for image in images:
            if run_cpu is None:
                raise RuntimeError('CUDA is unavailable and no CPU implementation was provided')
            yield run_cpu(image)
        return
    groups = {}
    for index, image in enumerate(images):
        groups.setdefault(image.size, []).append(index)
    outputs = [None]*len(images)
    try:
        for (width, height), indices in groups.items():
            size = max(1, min(max_batch_images, max_batch_pixels//max(1, width*height)))
            for start in range(0, len(indices), size):
                selected = indices[start:start+size]
                batch = [images[index] for index in selected]
                try:
                    processed = run_gpu(batch, context)
                except context['torch'].cuda.OutOfMemoryError:
                    # A single 4K input may exceed a small device's free memory.
                    # Handle only CUDA OOM; other user-code errors stay visible.
                    if run_cpu is None:raise
                    context['torch'].cuda.empty_cache()
                    if not context['oom_warned']:
                        warnings.warn('GPU Sharpen: CUDA memory exhausted; this microbatch uses CPU.', RuntimeWarning)
                        context['oom_warned'] = True
                    processed = [run_cpu(image) for image in batch]
                for index, image in zip(selected, processed):
                    outputs[index] = image
        for index in range(len(outputs)):
            output = outputs[index]
            outputs[index] = None  # Ownership transfers to the framework.
            yield output
    finally:
        for output in outputs:
            if output is not None:
                output.close()


def release_context(context):
    """The framework calls this hook when evicting this device model."""
    if context.get('backend') == 'cuda':
        torch = context['torch']
        context.pop('model', None)
        with torch.cuda.device(context['device']):
            torch.cuda.empty_cache()
    context.clear()
