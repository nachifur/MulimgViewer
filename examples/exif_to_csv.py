import os
import pandas as pd
from PIL.ExifTags import TAGS, GPSTAGS
from PIL import Image
import piexif
import json
from pathlib import Path
import exifread

def safe_decode(value):
    if isinstance(value, bytes):
        for enc in ('utf-8', 'latin1', 'gbk'):
            try:
                return value.decode(enc)
            except Exception:
                continue
        return value.hex()  # 实在不行就转16进制字符串
    return str(value) if value is not None else "N/A"

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

# 删除这部分重复的配置读取代码（第26-47行）
# script_dir = os.path.dirname(os.path.abspath(__file__))
# config_path = find_config_path()
# ... 等等

TAGS_TO_EXTRACT = {
    "Make": ["Make"],
    "Model": ["Model", "Camera Model Name", "Image Model"],
    "FNum": ["FNumber", "F Number", "EXIF FNumber"],
    "ExpTime": ["ExposureTime", "Exposure Time", "EXIF ExposureTime"],
    "ISO": ["ISOSpeedRatings", "ISO", "EXIF ISOSpeedRatings"],
    "ExpComp": ["ExposureCompensation", "Exposure Compensation", "EXIF ExposureCompensation"],
    "FocalLen": ["FocalLength", "Focal Length", "EXIF FocalLength"],
    "MaxAperture": ["MaxApertureValue", "Max Aperture Value", "EXIF MaxApertureValue"],
    "MeterMode": ["MeteringMode", "Metering Mode", "EXIF MeteringMode"],
    "SubjDist": ["SubjectDistance", "Subject Distance", "EXIF SubjectDistance"],
    "Flash": ["Flash", "EXIF Flash"],
    "Focal35mm": ["FocalLengthIn35mmFilm", "Focal Length In35mm Format", "EXIF FocalLengthIn35mmFilm"],
    "Contrast": ["Contrast", "EXIF Contrast"],
    "LightSource": ["LightSource", "Light Source", "EXIF LightSource"],
    "ExpProgram": ["ExposureProgram", "Exposure Program", "EXIF ExposureProgram"],
    "Saturation": ["Saturation", "EXIF Saturation"],
    "Sharpness": ["Sharpness", "EXIF Sharpness"],
    "WB": ["WhiteBalance", "White Balance", "EXIF WhiteBalance"],
    "DigitalZoom": ["DigitalZoom Ratio", "Digital ZoomRatio", "EXIF DigitalZoomRatio","DigitalZoomRatio"],
    "EXIFVer": ["ExifVersion", "Exif Version ", "EXIF ExifVersion"],
    "GPSLatitude": ["GPSLatitude", "GPS Latitude", "EXIF GPSLatitude"],
    "GPSLongitude": ["GPSLongitude", "GPS Longitude", "EXIF GPSLongitude"]
}

def convert_to_degrees(value):
    try:
        d = float(value[0][0]) / float(value[0][1])
        m = float(value[1][0]) / float(value[1][1])
        s = float(value[2][0]) / float(value[2][1])
        return d, m, s
    except Exception as e:
        print(f"convert_to_degrees解析失败: {value} 错误: {e}")
        return None

def format_gps(d, m, s, ref):
    try:
        deg = int(d)
        min_ = int(m)
        sec = round(s, 2)
        ref = ref.decode() if isinstance(ref, bytes) else ref
        return f"{deg}°{min_}'{sec:.2f}\"{ref}"
    except Exception as e:
        print(f"format_gps解析失败: {d},{m},{s},{ref} 错误: {e}")
        return "N/A"

def get_exif_data(image_path):
    try:
        image = Image.open(image_path)
        try:
            exif_dict = piexif.load(image.info.get('exif', b''))
        except Exception:
            exif_dict = None
        exif_data_raw = image._getexif() or {}
        image.close()  # 添加关闭图片
    except Exception as e:
        print(f"错误处理图像 {image_path}: {e}")
        return {}

    exif_data = {}
    for tag_id, value in exif_data_raw.items():
        tag_name = TAGS.get(tag_id, tag_id)
        if tag_name in TAGS_TO_EXTRACT:
            exif_data[tag_name] = value

    # GPS处理逻辑保持不变...
    gps_info = None
    if exif_dict and "GPS" in exif_dict and exif_dict["GPS"]:
        gps_info = exif_dict["GPS"]
        gps_data = {}
        for key in gps_info.keys():
            tag_name = GPSTAGS.get(key, key)
            gps_data[tag_name] = gps_info[key]
        lat_raw = gps_data.get("GPSLatitude")
        lon_raw = gps_data.get("GPSLongitude")
        lat_ref = gps_data.get("GPSLatitudeRef", b"N")
        lon_ref = gps_data.get("GPSLongitudeRef", b"E")
        if lat_raw and lon_raw:
            try:
                def rational_to_tuple(r):
                    if hasattr(r, 'numerator') and hasattr(r, 'denominator'):
                        return (r.numerator, r.denominator)
                    elif isinstance(r, (tuple, list)):
                        return (r[0], r[1])
                    else:
                        return (int(r), 1)
                lat_tuple = tuple([rational_to_tuple(x) for x in lat_raw])
                lon_tuple = tuple([rational_to_tuple(x) for x in lon_raw])
                lat_dms = convert_to_degrees(lat_tuple)
                lon_dms = convert_to_degrees(lon_tuple)
                if lat_dms and lon_dms:
                    lat_str = format_gps(*lat_dms, lat_ref)
                    lon_str = format_gps(*lon_dms, lon_ref)
                    exif_data["GPSLatitude"] = lat_str
                    exif_data["GPSLongitude"] = lon_str
                else:
                    exif_data["GPSLatitude"] = "N/A"
                    exif_data["GPSLongitude"] = "N/A"
            except Exception as e:
                print(f"GPS解析失败: {e}")
                exif_data["GPSLatitude"] = "N/A"
                exif_data["GPSLongitude"] = "N/A"
        else:
            exif_data["GPSLatitude"] = "N/A"
            exif_data["GPSLongitude"] = "N/A"
    else:
        if 34853 in exif_data_raw:
            gps_info = exif_data_raw[34853]
            gps_data = {}
            for key in gps_info.keys():
                tag_name = GPSTAGS.get(key, key)
                gps_data[tag_name] = gps_info[key]
            lat_raw = gps_data.get("GPSLatitude")
            lon_raw = gps_data.get("GPSLongitude")
            lat_ref = gps_data.get("GPSLatitudeRef", "N")
            lon_ref = gps_data.get("GPSLongitudeRef", "E")
            if lat_raw and lon_raw:
                try:
                    lat_tuple = tuple(lat_raw)
                    lon_tuple = tuple(lon_raw)
                    lat_dms = convert_to_degrees(lat_tuple)
                    lon_dms = convert_to_degrees(lon_tuple)
                    if lat_dms and lon_dms:
                        lat_str = format_gps(*lat_dms, lat_ref)
                        lon_str = format_gps(*lon_dms, lon_ref)
                        exif_data["GPSLatitude"] = lat_str
                        exif_data["GPSLongitude"] = lon_str
                    else:
                        exif_data["GPSLatitude"] = "N/A"
                        exif_data["GPSLongitude"] = "N/A"
                except Exception as e:
                    print(f"GPS解析失败: {e}")
                    exif_data["GPSLatitude"] = "N/A"
                    exif_data["GPSLongitude"] = "N/A"
            else:
                exif_data["GPSLatitude"] = "N/A"
                exif_data["GPSLongitude"] = "N/A"
        else:
            exif_data["GPSLatitude"] = "N/A"
            exif_data["GPSLongitude"] = "N/A"
    return exif_data

def get_exif_data_exifread(image_path):
    exif_data = {}
    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)

        for tag, val in tags.items():
            # DigitalZoomRatio等Ratio类型特殊处理
            if hasattr(val, 'num') and hasattr(val, 'den'):
                try:
                    val = float(val.num) / float(val.den) if val.den != 0 else 0.0
                except Exception:
                    val = str(val)
            exif_data[tag] = safe_decode(val)
    except Exception as e:
        print(f"[exifread错误] 处理 {image_path} 失败: {e}")
    return exif_data

def extract_to_csv(folder, output_csv):
    supported = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
    all_data = []
    folder_path = Path(folder).absolute()
    print(f"[*] 扫描目录: {folder_path}")

    if not folder_path.exists() or not folder_path.is_dir():
        print(f"[错误] 图像文件夹不存在: {folder_path}")
        return

    found = False
    for fname in os.listdir(folder_path):
        if fname.lower().endswith(supported):
            found = True
            fpath = folder_path / fname
            print(f"处理: {fpath}")
            exif = get_exif_data(str(fpath))
            exifread_data = get_exif_data_exifread(str(fpath))
            if exifread_data is None:
                exifread_data = {}
            record = {"Name": fpath.name}
            for chn_tag, eng_tags in TAGS_TO_EXTRACT.items():
                value = "N/A"
                for eng_tag in eng_tags:
                    if eng_tag in exif:
                        value = exif[eng_tag]
                        break
                    elif eng_tag in exifread_data:
                        value = exifread_data[eng_tag]
                        break
                # 特殊处理
                if ("Make" in eng_tags or "Model" in eng_tags):
                    if isinstance(value, bytes):
                        try:
                            value = value.decode('utf-8', errors='ignore')
                        except Exception:
                            value = "N/A"
                    if isinstance(value, str):
                        value = value.replace('\x00', '').strip()
                elif "EXIFVer" in eng_tags and isinstance(value, bytes):
                    try:
                        decoded = value.decode('ascii').strip('\x00')
                        if len(decoded) == 4 and decoded.isdigit():
                            value = f"{int(decoded[:2])}.{int(decoded[2:])}"
                        else:
                            value = decoded
                    except:
                        value = "N/A"
                elif "FNum" in eng_tags and isinstance(value, tuple) and value != "N/A":
                    try:
                        f_number = value[0] / value[1]
                        value = f"ƒ/{f_number:.1f}"
                    except (TypeError, ZeroDivisionError, IndexError):
                        value = "N/A"
                elif "ExpTime" in eng_tags and isinstance(value, tuple) and value != "N/A":
                    try:
                        exposure = value[0] / value[1]
                        if exposure < 1:
                            value = f"1/{int(1/exposure)}"
                        else:
                            value = f"{exposure:.1f}秒"
                    except (TypeError, ZeroDivisionError, IndexError):
                        value = "N/A"
                # DigitalZoom字段特殊处理
                if any('zoom' in t.lower() for t in eng_tags):
                    if hasattr(value, 'num') and hasattr(value, 'den'):
                        try:
                            value = float(value.num) / float(value.den) if value.den != 0 else 0.0
                        except Exception:
                            value = str(value)
                record[chn_tag] = safe_decode(value)
            print(f"[调试] {record['Name']} 的EXIF信息: {record}")
            all_data.append(record)

    if not found or not all_data:
        print(f"[警告] 未找到任何支持的图片文件: {folder_path}")
        return

    # 统一做safe_decode
    for record in all_data:
        for k, v in record.items():
            record[k] = safe_decode(v)

    try:
        df = pd.DataFrame(all_data)
        df.to_csv(output_csv, index=False, encoding='utf-8')
        print(f"提取完成：{output_csv}")
        print(f"处理了 {len(all_data)} 张图像")
    except Exception as e:
        print(f"[错误] 写入CSV失败: {e}")
        return

    # 去除BOM
    try:
        with open(output_csv, 'rb') as f:
            content = f.read()
        BOM = b'\xef\xbb\xbf'
        if content.startswith(BOM):
            print("[去除BOM] 检测到BOM，正在去除...")
            content = content[len(BOM):]
            with open(output_csv, 'wb') as f:
                f.write(content)
            print("[去除BOM] 已去除BOM。")
    except Exception as e:
        print(f"[错误] 去除BOM失败: {e}")

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
                config_text = f.read().strip()
                config = json.loads(config_text)
                print("[调试] 配置文件内容：", json.dumps(config, indent=2, ensure_ascii=False))

            raw_path = config.get("image_folder", "")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f"[配置错误] 配置文件 {config_path} 中 image_folder 字段缺失或无效，内容为: {raw_path}")

            image_folder = Path(raw_path).expanduser()
            if not image_folder.is_absolute():
                config_dir = config_path.parent
                image_folder = config_dir / image_folder
            image_folder = image_folder.resolve()
            print(f"[配置] 使用配置文件中的图片文件夹: {image_folder}")
        except Exception as e:
            print(f"[错误] 无法从配置文件获取图片文件夹路径: {e}")
            sys.exit(1)

    script_dir = Path(__file__).parent.resolve()
    out_csv = script_dir / "output_exif_data.csv"
    extract_to_csv(image_folder, out_csv)
