import os
import pandas as pd
from PIL.ExifTags import TAGS, GPSTAGS
from PIL import Image
from pathlib import Path
import sys
import re
import csv

def clean_string(text):
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    problem_chars = ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', '\x08']
    for char in problem_chars:
        text = text.replace(char, '')
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = ' '.join(text.split())
    return text

def safe_decode(value):
    if isinstance(value, bytes):
        for enc in ('utf-8', 'latin1', 'gbk','cp1252'):
            try:
                decoded = value.decode(enc, errors='ignore')
                return clean_string(decoded)
            except Exception:
                continue
    result = str(value) if value is not None else "N/A"
    return clean_string(result)

def validate_csv(csv_path):
    try:
        with open(csv_path, 'rb') as f:
            content = f.read()
        if b'\x00' in content:
            cleaned_content = content.replace(b'\x00', b'')
            with open(csv_path, 'wb') as f:
                f.write(cleaned_content)
            return True
        else:
            return True
    except:
        return False

TAGS_TO_EXTRACT = {
    # 基本相机信息
    "Make": ["Make", "Camera Make"],
    "Model": ["Model", "Camera Model Name", "Image Model"],

    # 曝光设置
    "FNum": ["FNumber", "F Number", "EXIF FNumber", "Aperture"],
    "ExpTime": ["ExposureTime", "Exposure Time", "EXIF ExposureTime", "Shutter Speed"],
    "ISO": ["ISOSpeedRatings", "ISO", "EXIF ISOSpeedRatings"],
    "ExpComp": ["ExposureCompensation", "Exposure Compensation", "EXIF ExposureCompensation", "ExposureBiasValue"],
    "ExpProgram": ["ExposureProgram", "Exposure Program", "EXIF ExposureProgram"],
    "ExpMode": ["ExposureMode", "Exposure Mode", "EXIF ExposureMode"],

    # 焦距信息
    "FocalLen": ["FocalLength", "Focal Length", "EXIF FocalLength"],
    "Focal35mm": ["FocalLengthIn35mmFilm", "Focal Length In 35mm Format", "EXIF FocalLengthIn35mmFilm"],
    "MaxAperture": ["MaxApertureValue", "Max Aperture Value", "EXIF MaxApertureValue"],
    "MinFocalLen": ["Min Focal Length", "MinFocalLength"],
    "MaxFocalLen": ["Max Focal Length", "MaxFocalLength"],
    "MaxApertureAtMinFocal": ["Max Aperture At Min Focal", "MaxApertureAtMinFocal"],
    "MaxApertureAtMaxFocal": ["Max Aperture At Max Focal", "MaxApertureAtMaxFocal"],

    # 测光和对焦
    "MeterMode": ["MeteringMode", "Metering Mode", "EXIF MeteringMode"],
    "SubjDist": ["SubjectDistance", "Subject Distance", "EXIF SubjectDistance", "Subject Distance Range"],
    "FocusMode": ["FocusMode", "Focus Mode", "AF Mode"],
    "AFMode": ["AF Mode", "AFMode", "Focus Mode 2"],
    "AFAreaMode": ["AF Area Mode", "AFAreaMode"],
    "SensingMethod": ["SensingMethod", "Sensing Method"],

    # 闪光灯
    "Flash": ["Flash", "EXIF Flash"],
    "FlashMode": ["Fuji Flash Mode", "Flash Mode"],
    "FlashExpComp": ["Flash Exposure Comp", "Flash Exposure Compensation"],

    # 图像质量设置
    "Contrast": ["Contrast", "EXIF Contrast"],
    "LightSource": ["LightSource", "Light Source", "EXIF LightSource"],
    "Saturation": ["Saturation", "EXIF Saturation"],
    "Sharpness": ["Sharpness", "EXIF Sharpness"],
    "WB": ["WhiteBalance", "White Balance", "EXIF WhiteBalance"],
    "WBFineTune": ["White Balance Fine Tune", "WhiteBalanceFineTune"],
    "NoiseReduction": ["Noise Reduction", "NoiseReduction"],

    # 数字处理
    "DigitalZoom": ["DigitalZoom Ratio", "Digital ZoomRatio", "EXIF DigitalZoomRatio", "DigitalZoomRatio"],
    "ColorSpace": ["ColorSpace", "Color Space", "EXIF ColorSpace"],
    "SceneCaptureType": ["SceneCaptureType", "Scene Capture Type"],
    "CustomRendered": ["CustomRendered", "Custom Rendered"],

    # 版本和技术信息
    "EXIFVer": ["ExifVersion", "Exif Version", "EXIF ExifVersion"],
    "FlashpixVer": ["FlashpixVersion", "Flashpix Version"],

    # GPS 信息
    "GPSLatitude": ["GPSLatitude", "GPS Latitude", "EXIF GPSLatitude"],
    "GPSLongitude": ["GPSLongitude", "GPS Longitude", "EXIF GPSLongitude"],
    "GPSLatitudeRef": ["GPSLatitudeRef", "GPS Latitude Ref"],
    "GPSLongitudeRef": ["GPSLongitudeRef", "GPS Longitude Ref"],
    "GPSAltitude": ["GPSAltitude", "GPS Altitude"],
    "GPSAltitudeRef": ["GPSAltitudeRef", "GPS Altitude Ref"],

    # 镜头信息
    "LensInfo": ["LensInfo", "Lens Info", "Lens"],
    "LensSerialNumber": ["LensSerialNumber", "Lens Serial Number"],
    "ImageStabilization": ["Image Stabilization", "ImageStabilization"],

    # 相机特定设置（富士相机）
    "Quality": ["Quality", "Image Quality"],
    "PictureMode": ["PictureMode", "Picture Mode"],
    "FilmMode": ["FilmMode", "Film Mode"],
    "DynamicRange": ["DynamicRange", "Dynamic Range", "Dynamic Range Setting"],
    "ShadowTone": ["ShadowTone", "Shadow Tone"],
    "HighlightTone": ["HighlightTone", "Highlight Tone"],
    "GrainEffect": ["Grain Effect Roughness", "GrainEffectRoughness"],
    "LensModulationOptimizer": ["Lens Modulation Optimizer", "LensModulationOptimizer"],

    # 拍摄信息
    "ShutterType": ["ShutterType", "Shutter Type"],
    "DriveMode": ["DriveMode", "Drive Mode"],
    "DriveSpeed": ["DriveSpeed", "Drive Speed"],
    "AutoBracketing": ["AutoBracketing", "Auto Bracketing"],
    "SequenceNumber": ["SequenceNumber", "Sequence Number"],
    "ExposureCount": ["ExposureCount", "Exposure Count"],
    "ImageCount": ["ImageCount", "Image Count"],

    # 图像尺寸和分辨率
    "ImageWidth": ["ImageWidth", "Image Width", "ExifImageWidth", "Exif Image Width"],
    "ImageHeight": ["ImageHeight", "Image Height", "ExifImageHeight", "Exif Image Height"],
    "XResolution": ["XResolution", "X Resolution"],
    "YResolution": ["YResolution", "Y Resolution"],
    "ResolutionUnit": ["ResolutionUnit", "Resolution Unit"],
    "FocalPlaneXResolution": ["FocalPlaneXResolution", "Focal Plane X Resolution"],
    "FocalPlaneYResolution": ["FocalPlaneYResolution", "Focal Plane Y Resolution"],
    "FocalPlaneResolutionUnit": ["FocalPlaneResolutionUnit", "Focal Plane Resolution Unit"],

    # 时间信息
    "DateTime": ["DateTime", "Date Time", "Modify Date"],
    "DateTimeOriginal": ["DateTimeOriginal", "Date/Time Original"],
    "CreateDate": ["CreateDate", "Create Date"],

    # 其他技术参数
    "Orientation": ["Orientation", "Image Orientation"],
    "BitsPerSample": ["BitsPerSample", "Bits Per Sample"],
    "Compression": ["Compression", "Image Compression"],
    "PhotometricInterpretation": ["PhotometricInterpretation", "Photometric Interpretation"],
    "YCbCrPositioning": ["YCbCrPositioning", "Y Cb Cr Positioning"],

    # 计算值
    "Aperture": ["Aperture", "F Number"],
    "ShutterSpeed": ["ShutterSpeed", "Shutter Speed", "Shutter Speed Value"],
    "LightValue": ["LightValue", "Light Value"],
    "HyperfocalDistance": ["HyperfocalDistance", "Hyperfocal Distance"],
    "FieldOfView": ["FieldOfView", "Field Of View"],
    "CircleOfConfusion": ["CircleOfConfusion", "Circle Of Confusion"],
    "ScaleFactor": ["Scale Factor To 35 mm Equivalent", "ScaleFactorTo35mmEquivalent"],
    "Megapixels": ["Megapixels", "Image Size"],

    # 评级和元数据
    "Rating": ["Rating", "Image Rating"],

    # 人脸检测
    "FacesDetected": ["FacesDetected", "Faces Detected"],
    "FacePositions": ["FacePositions", "Face Positions"],

    # 序列号和版本
    "SerialNumber": ["SerialNumber", "Serial Number"],
    "InternalSerialNumber": ["InternalSerialNumber", "Internal Serial Number"],
    "ImageGeneration": ["ImageGeneration", "Image Generation"],

    # 文件信息
    "FileName": ["FileName", "File Name"],
    "FileSize": ["FileSize", "File Size"],
    "FileType": ["FileType", "File Type"],
    "MIMEType": ["MIMEType", "MIME Type"],

    # 警告信息
    "BlurWarning": ["BlurWarning", "Blur Warning"],
    "FocusWarning": ["FocusWarning", "Focus Warning"],
    "ExposureWarning": ["ExposureWarning", "Exposure Warning"]
}

def convert_to_degrees(value):
    try:
        d = float(value[0][0]) / float(value[0][1])
        m = float(value[1][0]) / float(value[1][1])
        s = float(value[2][0]) / float(value[2][1])
        return d, m, s
    except:
        return "N/A"

def format_gps(d, m, s, ref):
    try:
        deg = int(d)
        min_ = int(m)
        sec = round(s, 2)
        ref = ref.decode() if isinstance(ref, bytes) else ref
        return f"{deg}°{min_}'{sec:.2f}\"{ref}"
    except:
        return "N/A"

def get_exif_data(image_path):

    image = Image.open(image_path)
    exif_data_raw = image._getexif() or {}
    image.close()

    exif_data = {}
    for tag_id, value in exif_data_raw.items():
        tag_name = TAGS.get(tag_id, str(tag_id))
        exif_data[tag_name] = value

    gps_raw = exif_data_raw.get(34853)

    if gps_raw is not None:
        try:
            gps_data = {}
            for key in gps_raw.keys():
                tag_name = GPSTAGS.get(key, key)
                gps_data[tag_name] = gps_raw[key]
            lat_raw = gps_data.get("GPSLatitude")
            lon_raw = gps_data.get("GPSLongitude")
            lat_ref = gps_data.get("GPSLatitudeRef", b"N")
            lon_ref = gps_data.get("GPSLongitudeRef", b"E")

            if lat_raw and lon_raw:
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

                if lat_dms !="N/A" and lon_dms !="N/A":
                    lat_str = format_gps(*lat_dms, lat_ref)
                    lon_str = format_gps(*lon_dms, lon_ref)
                    exif_data["GPSLatitude"] = lat_str
                    exif_data["GPSLongitude"] = lon_str
                else:
                    exif_data["GPSLatitude"] = "N/A"
                    exif_data["GPSLongitude"] = "N/A"
        except Exception as e:
            exif_data["GPSLatitude"] = "N/A"
            exif_data["GPSLongitude"] = "N/A"
    else:
        exif_data["GPSLatitude"] = "N/A"
        exif_data["GPSLongitude"] = "N/A"
    return exif_data

def process_time_value(value):
    if value == "N/A":
        return "N/A"
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8', errors='ignore')
        except:
            return "N/A"
    if isinstance(value, str):
        value = clean_string(value)
        if len(value) >= 19:
            time_pattern = r'^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}'
            if re.match(time_pattern, value[:19]):
                return value[:19]
            else:
                return "N/A"
        else:
            return "N/A"
    return "N/A"

def extract_to_csv(folder, output_csv):
    supported = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
    all_data = []
    folder_path = Path(folder).absolute()

    for fname in os.listdir(folder_path):
        if fname.lower().endswith(supported):
            fpath = folder_path / fname
            exif = get_exif_data(str(fpath))
            record = {"Name": fpath.name}
            for chn_tag, eng_tags in TAGS_TO_EXTRACT.items():
                value = "N/A"
                for eng_tag in eng_tags:
                    if eng_tag in exif:
                        value = exif[eng_tag]
                        break
                if chn_tag in ["DateTime", "DateTimeOriginal", "CreateDate"]:
                        value = process_time_value(value)
                elif chn_tag in ["Make", "Model"]:
                    if isinstance(value, bytes):
                        try:
                            value = value.decode('utf-8', errors='ignore')
                        except Exception:
                            value = "N/A"
                    if isinstance(value, str):
                        value = clean_string(value)

                elif chn_tag == "EXIFVer" and isinstance(value, bytes):
                    try:
                        decoded = value.decode('ascii', errors='ignore').strip('\x00')
                        decoded = clean_string(decoded)
                        if len(decoded) == 4 and decoded.isdigit():
                            value = f"{int(decoded[:2])}.{int(decoded[2:])}"
                        else:
                            value = decoded
                    except:
                        value = "N/A"

                elif chn_tag == "FNum" and value != "N/A":
                    try:
                        if isinstance(value, tuple):
                            f_number = value[0] / value[1]
                        elif hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                            f_number = float(value.numerator) / float(value.denominator)
                        else:
                            f_number = float(value)

                        value = f"ƒ/{f_number:.1f}"
                    except (TypeError, ZeroDivisionError, AttributeError) as e:
                        value = "N/A"

                elif chn_tag == "ExpTime" and value != "N/A":
                    try:
                        if isinstance(value, tuple):
                            exposure = value[0] / value[1]
                        elif hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                            exposure = float(value.numerator) / float(value.denominator)
                        else:
                            exposure = float(value)
                        if exposure < 1:
                            shutter_speed = round(1/exposure)
                            value = f"1/{shutter_speed}s"
                        else:
                            value = f"{exposure:.1f}s"
                    except (TypeError, ZeroDivisionError, AttributeError) as e:
                        value = "N/A"

                elif any('zoom' in t.lower() for t in eng_tags):
                    if hasattr(value, 'num') and hasattr(value, 'den'):
                        try:
                            value = float(value.num) / float(value.den) if value.den != 0 else 0.0
                        except Exception:
                            value = str(value)
                record[chn_tag] = safe_decode(value)
            all_data.append(record)

    df = pd.DataFrame(all_data)

    for col in df.columns:
        df[col] = df[col].astype(str).apply(clean_string)

    try:
        df.to_csv(output_csv, index=False, encoding='utf-8', escapechar='\\')
    except:
        try:
            with open(output_csv, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerow(df.columns.tolist())
                for _, row in df.iterrows():
                    cleaned_row = [clean_string(str(cell)) for cell in row]
                    writer.writerow(cleaned_row)
        except:
            return False

    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        image_folder = Path(sys.argv[1])
    else:
        sys.exit(1)
    script_dir = Path(__file__).parent.resolve()
    out_csv = script_dir / "output_exif_data.csv"

    success = extract_to_csv(image_folder, out_csv)
    if success:
        if validate_csv(out_csv):
            pass
        else:
            sys.exit(1)
    else:
        sys.exit(1)
