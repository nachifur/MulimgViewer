r"""`<https://github.com/nachifur/MulimgViewer/issues/57#issuecomment-1431032894>_`"""
import piexif
from PIL import Image
import json
import csv
import chardet
from pathlib import Path
import sys


def get_encoding(file):
    with open(file, 'rb') as f:
        tmp = chardet.detect(f.read())
        return tmp['encoding']

def check_type(obj):
    if isinstance(obj, bytes):
        return str(obj, encoding='utf-8')
    else:
        return obj

def get_image_folder():
    if len(sys.argv) >1:
        folder_path = Path(sys.argv[1]).resolve()
        print(f"the path of input:{folder_path}")
        return folder_path
    else:
        return None

def fill_dict_to_img(key_list, exif_list , folder_path):
    img_name = exif_list[0]
    img_path = folder_path / img_name
    img = Image.open(img_path)
    # json.loads(exif_dict["0th"][270])
    if 'exif' not in img.info:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    else:
        exif_dict = piexif.load(img.info['exif'])

    add_new_dict = {}
    sub_dict = {}
    add_new_dict["MulimgViewer"] = sub_dict
    for i in range(len(exif_list)):
        if i == 0:
            # sub_dict[key_list[i]] = check_type(exif_dict["0th"][270]) # ImageDescription
            sub_dict[key_list[i]] = img_name
        else:
            sub_dict[key_list[i]] = check_type(exif_list[i])
    exif_dict["0th"][270] = json.dumps(add_new_dict).encode('utf-8')
    exif_bytes = piexif.dump(exif_dict)
    img.save(img_path, exif=exif_bytes)
    print("Modified EXIF - ImageDescription:", img_path)
    print(exif_dict["0th"][270])

image_folder = get_image_folder()
# load csv
csv_file = Path(__file__).parent.resolve() / "output_exif_data.csv"

#input_path = Path(csv_file)
encoding = get_encoding(csv_file)

with open(csv_file, 'r', newline='', encoding=encoding) as csvfile:
    dataset = list(csv.reader(csvfile))
    row = len(dataset)
    if row > 1:
        key_list = dataset[0]
        for r in range(1, row):
            try:
                fill_dict_to_img(key_list, dataset[r], image_folder)
            except:
                pass
