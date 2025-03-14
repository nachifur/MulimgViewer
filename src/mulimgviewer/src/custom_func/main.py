'''
https://github.com/nachifur/MulimgViewer/issues/74
'''
from PIL import ImageEnhance,Image
from pathlib import Path
import os
'''
修改备用，此文件也有一个save，考虑在此定义类
class Save():
    def __init__(self):
        self.selected_save_format=None
    def save_convert_image(self,png_path):
            self.save_format=None
            self.selected_save_format=self.save_format.GetSelection()
            self.save_format=self.selected_save_format
            with Image.open(png_path) as img:
                # 根据目标格式保存图像
                if save_format == 'png':
                    img.save(png_path, 'PNG')
                elif save_format == 'jpg':
                    rgb_img = img.convert('RGB')
                    new_path = os.path.splitext(png_path)[0] + '.jpg'
                    rgb_img.save(new_path, 'JPEG')
                elif save_format == 'pdf':
                    new_path = os.path.splitext(png_path)[0] + '.pdf'
                    img.save(new_path, 'PDF')
            # 删除原始 PNG 文件
            if save_format != 'png':
                os.remove(png_path)
                '''
def custom_process_img(img):
    # Users can modify this function for custom image processing.
    # input: image(pillow)
    # output: image(pillow)
    enh = ImageEnhance.Contrast(img)
    img = enh.enhance(2)
    return img

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
        img = custom_process_img(img)

        out_img_list.append(img)
        if flag_save:
            if isinstance(name_list, list):
                img_path = save_path/name_list[i]
            else:
                img_path = save_path/(str(i)+".png")
            img.save(str(img_path))
        i += 1
    return out_img_list
