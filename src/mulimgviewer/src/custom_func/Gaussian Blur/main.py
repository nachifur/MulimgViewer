"""
Gaussian Blur Image Processing Module
"""
from PIL import ImageFilter
from pathlib import Path
import os

def custom_process_img(img):
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    return img

def main(img_list, save_path, name_list=None, algorithm_name="Gaussian Blur"):
    i = 0
    out_img_list = []
    if save_path != "":
        flag_save = True
        base_save_path = Path(save_path) / "processing_function" / algorithm_name / "processed_img"
        if not base_save_path.exists():
            os.makedirs(str(base_save_path))
    else:
        flag_save = False
        base_save_path = None

    for img in img_list:
        img = custom_process_img(img)
        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list) and i < len(name_list):
                name = name_list[i]
                name_path = Path(name)
                if len(name_path.parts) > 1:
                    sub_folder = name_path.parent
                    file_name = name_path.name
                    final_save_path = base_save_path / sub_folder
                else:
                    final_save_path = base_save_path
                    file_name = name

                if not final_save_path.exists():
                    os.makedirs(str(final_save_path))
                img_path = final_save_path / file_name
            else:
                img_path = base_save_path / (str(i) + ".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
