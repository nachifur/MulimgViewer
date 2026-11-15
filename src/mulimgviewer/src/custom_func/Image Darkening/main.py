from PIL import ImageEnhance

THREAD_SAFE = True


def process_image(image, *, context):
    return ImageEnhance.Brightness(image).enhance(0.5)
