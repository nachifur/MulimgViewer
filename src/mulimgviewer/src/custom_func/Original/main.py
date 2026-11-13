"""Identity operation: the framework references inputs without copying pixels."""
THREAD_SAFE = True


def custom_process_img(img):
    return img


def main(img_list, save_path='', name_list=None, algorithm_name='Original'):
    return img_list
