'''
Image Enhancement Algorithm - Boosting Image Contrast
'''
from PIL import ImageEnhance
from pathlib import Path
import os

def custom_process_img(img):
    """
    Image Enhancement Processing Function
    input: image(pillow)
    output: image(pillow)
    """
    enh = ImageEnhance.Contrast(img)
    img = enh.enhance(2)
    return img

def main(img_list, save_path, name_list=None, algorithm_name="Image Enhancement"):
    """
    Batch process image list
    """
    i = 0
    out_img_list = []
    if save_path != "":
        flag_save = True
        save_path = Path(save_path) / "processing_function" / algorithm_name / "processed_img"
        if not save_path.exists():
            os.makedirs(str(save_path))
    else:
        flag_save = False

    for img in img_list:
        img = custom_process_img(img)
        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list) and i < len(name_list):
                img_path = save_path / name_list[i]
            else:
                img_path = save_path / (str(i) + ".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
