from PIL import ImageEnhance
from pathlib import Path
import os


def main(img_list, save_path, name_list=None):
    i = 0
    out_img_list = []
    if save_path!="":
        flag_save = True
        save_path = Path(save_path)/"custom_func_output"
        if not save_path.exists():
            os.makedirs(str(save_path))
    else:
        flag_save = False

    for img in img_list:
        # custom process img
        enh = ImageEnhance.Contrast(img)
        img = enh.enhance(2)
        ##########

        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list):
                img_path = save_path/name_list[i]
            else:
                img_path = save_path/(str(i)+".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
