from PIL import ImageEnhance
from pathlib import Path
import os

def custom_process_img(img):
    enh = ImageEnhance.Brightness(img)
    img = enh.enhance(0.5)
    return img

def main(img_list, save_path, name_list=None, algorithm_name="Image Darkening"):
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
            # 保存 PNG，并额外保存同名 PDF 方便用户选择 PDF 输出
            img.save(str(img_path))
            pdf_path = img_path.with_suffix(".pdf")
            try:
                img.convert("RGB").save(str(pdf_path), "PDF")
            except Exception:
                pass
        i += 1
    return out_img_list
