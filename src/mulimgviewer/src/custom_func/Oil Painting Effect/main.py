from PIL import Image
from pathlib import Path
import os
import numpy as np

def custom_process_img(img):
    """油画效果"""
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    img_array = np.array(img)
    height, width = img_array.shape[:2]
    
    # 油画效果参数
    radius = 5  # 领域半径
    intensity_levels = 20  # 强度等级
    
    result = np.zeros_like(img_array)
    
    for y in range(height):
        for x in range(width):
            # 定义领域
            y1 = max(0, y - radius)
            y2 = min(height, y + radius + 1)
            x1 = max(0, x - radius)
            x2 = min(width, x + radius + 1)
            
            region = img_array[y1:y2, x1:x2]
            
            # 计算强度直方图
            intensities = np.mean(region, axis=2).astype(int)
            intensity_count = np.bincount(intensities.flatten(), minlength=256)
            
            # 找到最常见的强度
            most_common_intensity = np.argmax(intensity_count)
            
            # 计算该强度对应的平均颜色
            mask = (np.abs(intensities - most_common_intensity) < intensity_levels)
            if mask.sum() > 0:
                avg_color = region[mask].mean(axis=0).astype(int)
                result[y, x] = avg_color
            else:
                result[y, x] = img_array[y, x]
    
    return Image.fromarray(result.astype('uint8'))

def main(img_list, save_path, name_list=None, algorithm_name="Oil Painting Effect"):
    i = 0
    out_img_list = []
    if save_path != "":
        flag_save = True
        save_path = Path(save_path) / "custom_func_output" / algorithm_name / "processed_img"
        if not save_path.exists():
            os.makedirs(str(save_path))
    else:
        flag_save = False

    for img in img_list:
        # 油画效果计算量大，缩小图片加速
        small_img = img.resize((img.width // 2, img.height // 2), Image.BICUBIC)
        processed = custom_process_img(small_img)
        img = processed.resize(img.size, Image.BICUBIC)
        
        out_img_list.append(img)
        
        if flag_save:
            if isinstance(name_list, list):
                img_path = save_path / name_list[i]
            else:
                img_path = save_path / (str(i) + ".png")
            img.save(str(img_path))
        i += 1
    
    return out_img_list