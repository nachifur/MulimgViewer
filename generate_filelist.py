import numpy as np
#import math
#from time import time
from pathlib import Path
def filelist(path):
    #dataset=[]
    if not Path(path).exists():
        return
    if Path(path).is_dir():
        dataset1=([f.resolve() for f in Path(path).iterdir() if f.is_file()])
        if len(dataset1)>0:
            ret = dataset1
        dataset2=[filelist(f.resolve()) for f in Path(path).iterdir() if f.is_dir()]
        if len(dataset2)>0:
            if 'ret' in locals() :# or 'ret' in globals()
                ret.append(dataset2)
            else:
                ret= dataset2
        return np.array(ret).ravel().tolist()
if __name__ == "__main__":
    path="D:\\Repos\\Mulimg_viewer\\test_input"
    dataset=filelist(path)
    #print(dataset)
    if dataset is not None:
        f = open("D:\\Repos\\Mulimg_viewer\\filelist.txt", "a")
        
        
        for data in dataset:
            f.write(str(data)+'\n')
            print(data) 
        f.close()
    else:
        print('dataset is None\n')
    