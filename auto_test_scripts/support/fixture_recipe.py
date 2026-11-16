"""Independent, integer-only input and pixel oracle; no production imports."""
import hashlib
from PIL import Image

WIDTH, HEIGHT, FPS = 64, 48, 4


def frame(source, index):
    image=Image.new('RGB',(WIDTH,HEIGHT))
    image.putdata([((source*73+x*3+index*17)%256,
                    (y*5+index*29)%256,
                    ((x//8+y//8)%2*120+source*31+index*7)%256)
                   for y in range(HEIGHT) for x in range(WIDTH)])
    return image


def pixel_hash(image):
    with image.convert('RGB') as rgb:
        return hashlib.sha256(rgb.tobytes()).hexdigest()


def expected_pair(left_source=1, left_index=0, right_source=2, right_index=0):
    image=Image.new('RGB',(WIDTH*2,HEIGHT))
    with frame(left_source,left_index) as left, frame(right_source,right_index) as right:
        image.paste(left,(0,0));image.paste(right,(WIDTH,0))
    return image
