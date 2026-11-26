"""Create ten aligned comparison images from one large reference photograph."""
import argparse
from pathlib import Path

from PIL import Image, ImageOps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    parser.add_argument("output", type=Path, help="New directory for the ten sources")
    args = parser.parse_args()
    size = (4608, 2592)
    with Image.open(args.photo) as image:
        photo = ImageOps.exif_transpose(image)
        if photo.width < size[0] or photo.height < size[1]:
            parser.error("Use a landscape reference image of at least 4608 x 2592 pixels.")
        x = (photo.width - size[0]) // 2
        y = (photo.height - size[1]) // 2
        reference = photo.crop((x, y, x + size[0], y + size[1])).convert("RGB")

    args.output.mkdir(parents=True, exist_ok=False)

    def save(image, name):
        folder = args.output / name
        folder.mkdir()
        image.save(folder / "bird.png", compress_level=1)

    save(reference, "01-Reference")
    index = 2
    for factor in (2, 3, 4):
        small = reference.resize((size[0] // factor, size[1] // factor), Image.Resampling.LANCZOS)
        for method in ("Nearest", "Bicubic", "Lanczos"):
            with small.resize(size, Image.Resampling[method.upper()]) as result:
                save(result, f"{index:02d}-{factor}x-{method}")
            index += 1


if __name__ == "__main__":
    main()
