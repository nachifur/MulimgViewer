from PIL import ImageFilter

THREAD_SAFE = True


def process_image(image, *, context):
    """One full-resolution Pillow input; saving is owned by the framework."""
    return image.filter(ImageFilter.GaussianBlur(radius=2))
