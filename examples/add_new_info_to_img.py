r"""`<https://github.com/nachifur/MulimgViewer/issues/57#issuecomment-1431032894>_`"""
import piexif
from PIL import Image
import json
import csv
import chardet
from pathlib import Path


def get_encoding(file):
    with open(file, 'rb') as f:
        tmp = chardet.detect(f.read())
        return tmp['encoding']


def check_type(obj):
    if isinstance(obj, bytes):
        return str(obj, encoding='utf-8')
    else:
        return obj


def fill_dict_to_img(key_list, exif_list):
    img_path = Path(exif_list[0])
    img = Image.open(img_path)
    exif_dict = piexif.load(img.info['exif'])
    # json.loads(exif_dict["0th"][270])

    add_new_dict = {}
    sub_dict = {}
    add_new_dict["MulimgViewer"] = sub_dict
    for i in range(len(exif_list)):
        if i == 0:
            # sub_dict[key_list[i]] = check_type(exif_dict["0th"][270]) # ImageDescription
            sub_dict[key_list[i]] = Path(exif_list[i]).name
        else:
            sub_dict[key_list[i]] = check_type(exif_list[i])
    exif_dict["0th"][270] = json.dumps(add_new_dict)
    exif_bytes = piexif.dump(exif_dict)
    img.save(img_path, exif=exif_bytes)
    print("Modified EXIF - ImageDescription:", img_path)
    print(exif_dict["0th"][270])


# load csv
csv_list = ["D:/ncfey/Desktop/Vaccher/test_show_exif/input_1_exif.csv",
            "D:/ncfey/Desktop/Vaccher/test_show_exif/input_2_exif.csv"]
for csv_file in csv_list:
    input_path = Path(csv_file)
    encoding = get_encoding(input_path)

    with open(input_path, 'r', newline='', encoding='ANSI') as csvfile:
        dataset = list(csv.reader(csvfile))
        row = len(dataset)
        first_row = True
        for r in range(row):
            if first_row:
                key_list = dataset[0]
                first_row = False
                continue
            fill_dict_to_img(key_list, dataset[r])
