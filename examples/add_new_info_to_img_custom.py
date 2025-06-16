r"""`<https://github.com/nachifur/MulimgViewer/issues/57#issuecomment-1431032894>_`"""
import piexif
import csv
import json
import os
from pathlib import Path
from PIL import Image

def check_type(obj):
    if isinstance(obj, bytes):
        for enc in ('utf-8', 'gbk'):
            try:
                return obj.decode(enc)
            except Exception:
                continue
        return obj.hex()
    else:
        return obj

def find_config_path():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    candidates = [
        script_dir / "output.json",
        project_root / "src" / "mulimgviewer" / "configs" / "output.json",
        project_root / "configs" / "output.json",
        Path.home() / ".mulimgviewer" / "output.json",
    ]
    for path in candidates:
        if path.exists():
            print(f"[配置] 使用配置文件: {path}")
            return path
    raise FileNotFoundError(
        "[配置错误] 未找到有效的 output.json 配置文件，尝试过的路径如下：\n" +
        "\n".join(str(p) for p in candidates)
    )

def batch_write_exif(image_folder, key_list, exif_lists):
    """批量写入EXIF信息到图片"""
    print(f"[批量处理] 开始处理文件夹: {image_folder}")
    processed_count = 0

    for exif_list in exif_lists:
        if len(exif_list) != len(key_list):
            print(f"[警告] 跳过字段数不匹配的行: {exif_list}")
            continue

        img_name = exif_list[0]
        # 使用传入的 image_folder 构建完整路径
        img_path = Path(image_folder) / img_name

        # 如果找不到，尝试只用文件名再找一次
        if not img_path.exists():
            img_path = Path(image_folder) / Path(img_name).name

        if img_path.is_file() and img_path.suffix.lower() in [".jpg", ".jpeg"]:
            fill_dict_to_img(key_list, exif_list, image_folder)
            processed_count += 1
        else:
            print(f"[跳过] 非图片文件或不存在: {img_path}")

    print(f"[批量处理] 完成，共处理 {processed_count} 个文件")

def fill_dict_to_img(key_list, exif_list, image_folder=None):
    print("进入 fill_dict_to_img")
    img_name = exif_list[0]

    # 如果没有传入 image_folder，则从配置文件读取
    if image_folder is None:
        config_path = find_config_path()
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        raw_path = config.get("image_folder", "")
        if not isinstance(raw_path, str) or not raw_path.strip():
            print(f"[错误] 配置文件中 image_folder 字段无效: {raw_path}")
            return
        image_folder = Path(raw_path).expanduser()
        if not image_folder.is_absolute():
            config_dir = config_path.parent
            image_folder = config_dir / image_folder
        image_folder = image_folder.resolve()
    else:
        image_folder = Path(image_folder)

    print(f"[处理] 图片文件夹: {image_folder}")
    print(f"[处理] 图片文件名: {img_name}")

    img_path = image_folder / img_name

    # 如果找不到，尝试只用文件名再找一次
    if not img_path.exists():
        img_path2 = image_folder / Path(img_name).name
        if img_path2.exists():
            img_path = img_path2
            print(f"[路径修正] 使用文件名查找: {img_path}")
        else:
            print(f"[警告] 找不到图片文件: {img_path}，已跳过。")
            print(f"[调试] 也尝试了: {img_path2}")
            return

    if not os.access(img_path, os.W_OK):
        print(f"[权限错误] 文件不可写: {img_path}")
        return

    try:
        img = Image.open(img_path)
        try:
            exif_dict = piexif.load(img.info.get("exif", b""))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        add_new_dict = {}
        sub_dict = {}
        add_new_dict["MulimgViewer"] = sub_dict

        for i in range(len(exif_list)):
            if i == 0:
                sub_dict[key_list[i]] = Path(exif_list[i]).name
            else:
                sub_dict[key_list[i]] = check_type(exif_list[i])

        exif_dict["0th"][piexif.ImageIFD.ImageDescription] = json.dumps(add_new_dict, ensure_ascii=False).encode("utf-8")
        exif_bytes = piexif.dump(exif_dict)

        if img.mode != "RGB":
            img = img.convert("RGB")

        img.save(img_path, "JPEG", exif=exif_bytes)
        img.close()

        # 验证写入结果
        img_check = Image.open(img_path)
        try:
            exif_check = piexif.load(img_check.info.get("exif", b""))
            desc = exif_check["0th"].get(piexif.ImageIFD.ImageDescription, b"")
            if desc:
                try:
                    info = json.loads(desc.decode("utf-8"))
                    print(f"[写入成功] {img_path.name}")
                except Exception as e:
                    print(f"[写入验证失败] {img_path.name}: {e}")
            else:
                print(f"[写入验证失败] {img_path.name}: 没有ImageDescription字段")
        except Exception as e:
            print(f"[写入验证失败] {img_path.name}: {e}")
        finally:
            img_check.close()

    except Exception as e:
        print(f"[处理失败] {img_path}: {e}")

if __name__ == "__main__":
    import sys

    # 优先使用命令行参数
    if len(sys.argv) > 1:
        image_folder_arg = sys.argv[1]
        image_folder = Path(image_folder_arg)
        if not image_folder.exists():
            print(f"[错误] 命令行指定的文件夹不存在: {image_folder}")
            sys.exit(1)
        print(f"[配置] 使用命令行参数指定的图片文件夹: {image_folder}")
    else:
        # 回退到配置文件方式
        try:
            config_path = find_config_path()
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            raw_path = config.get("image_folder", "")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f"[配置错误] 配置文件 {config_path} 中 image_folder 字段缺失或无效: {raw_path}")

            image_folder = Path(raw_path).expanduser()
            if not image_folder.is_absolute():
                config_dir = config_path.parent
                image_folder = config_dir / image_folder
            image_folder = image_folder.resolve()
            print(f"[配置] 使用配置文件中的图片文件夹: {image_folder}")
        except Exception as e:
            print(f"[错误] 无法从配置文件获取图片文件夹路径: {e}")
            sys.exit(1)

    # 加载 CSV 文件并处理
    csv_path = Path(__file__).parent / "output_exif_data.csv"
    print(f"[调试] 尝试读取CSV文件: {csv_path}")
    print(f"[调试] 文件是否存在: {csv_path.exists()}")

    if not csv_path.exists():
        print(f"[错误] 找不到CSV文件: {csv_path}")
        sys.exit(1)

    try:
        with open(csv_path, 'r', encoding='utf-8', errors='replace') as csvfile:
            lines = (line for line in csvfile if '\x00' not in line)
            dataset = list(csv.reader(lines))
            if not dataset:
                print("[错误] CSV文件为空")
                sys.exit(1)

            key_list = dataset[0]
            exif_lists = dataset[1:]

            print(f"[调试] CSV包含 {len(key_list)} 个字段: {key_list}")
            print(f"[调试] CSV包含 {len(exif_lists)} 行数据")
            # 使用批量处理函数
            batch_write_exif(image_folder, key_list, exif_lists)

    except Exception as e:
        print(f"[错误] 处理CSV文件时出错: {e}")
        sys.exit(1)
