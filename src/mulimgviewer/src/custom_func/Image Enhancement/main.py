from PIL import ImageEnhance

THREAD_SAFE = True


def process_image(image, *, context):
    """Independent CPU kernel; the framework schedules images in parallel."""
    return ImageEnhance.Contrast(image).enhance(2)
