import numpy as np


def layout_advice(num_all):
    list_factor = solve_factor(num_all)
    list_factor = list(set(list_factor))
    list_factor = np.sort(list_factor)
    if len(list_factor)==0:
        return [num_all, 1]
    else:
        if len(list_factor)<=2:
            row = list_factor[0]
        else:
            row = list_factor[int(len(list_factor)/2)-1]
        row = int(row)
        col=int(num_all/row)
        if row<col:
            return [col,row] 
        else:
            return [row,col] 



def solve_factor(num):
    list_factor = []
    i = 1
    if num >= 2:
        while i <= num:
            i += 1
            if num % i == 0:
                list_factor.append(i)
            else:
                pass
        return list_factor
    else:
        return []


print(layout_advice(12))
