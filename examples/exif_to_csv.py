import os
import pandas as pd
from PIL.ExifTags import TAGS, GPSTAGS
from PIL import Image
from pathlib import Path
import sys

def safe_decode(value):
    if isinstance(value, bytes):
        for enc in ('utf-8', 'latin1', 'gbk'):
            try:
                return value.decode(enc)
            except Exception:
                continue
    return str(value) if value is not None else "N/A"

def find_config_path():
    return Path(__file__).parent.parent / 'src' / 'mulimgviewer' / 'configs' / 'output.json'

TAGS_TO_EXTRACT = {
    "Make": ["Make"],
    "Model": ["Model", "Camera Model Name", "Image Model"],
    "FNum": ["FNumber", "F Number", "EXIF FNumber"],
    "ExpTime": ["ExposureTime", "Exposure Time", "EXIF ExposureTime"],
    "ISO": ["ISOSpeedRatings", "ISO", "EXIF ISOSpeedRatings"],
    "ExpComp": ["ExposureCompensation", "Exposure Compensation", "EXIF ExposureCompensation" ,"ExposureCompensation" ,"ExposureBiasValue"],
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
        return "N/A"

def format_gps(d, m, s, ref):
    try:
        deg = int(d)
        min_ = int(m)
        sec = round(s, 2)
        ref = ref.decode() if isinstance(ref, bytes) else ref
        return f"{deg}°{min_}'{sec:.2f}\"{ref}"
    except Exception as e:
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
                if chn_tag in ["Make", "Model"]:
                    if isinstance(value, bytes):
                        try:
                            value = value.decode('utf-8', errors='ignore')
                        except Exception:
                            value = "N/A"
                    if isinstance(value, str):
                        value = value.replace('\x00', '').strip()

                if chn_tag == "EXIFVer" and isinstance(value, bytes):
                    try:
                        decoded = value.decode('ascii').strip('\x00')
                        if len(decoded) == 4 and decoded.isdigit():
                            value = f"{int(decoded[:2])}.{int(decoded[2:])}"
                        else:
                            value = decoded
                    except:
                        value = "N/A"

                if chn_tag == "FNum" and value != "N/A":
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

                if chn_tag == "ExpTime" and value != "N/A":
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

                if any('zoom' in t.lower() for t in eng_tags):
                    if hasattr(value, 'num') and hasattr(value, 'den'):
                        try:
                            value = float(value.num) / float(value.den) if value.den != 0 else 0.0
                        except Exception:
                            value = str(value)
                record[chn_tag] = safe_decode(value)
            all_data.append(record)

    df = pd.DataFrame(all_data)
    df.to_csv(output_csv, index=False, encoding='utf-8')

if __name__ == "__main__":
    if len(sys.argv) > 1:
        image_folder = Path(sys.argv[1])
        print(f"Processing images in: {image_folder}")
    else:
        pass
        sys.exit(1)

    script_dir = Path(__file__).parent.resolve()
    out_csv = script_dir / "output_exif_data.csv"
    extract_to_csv(image_folder, out_csv)
