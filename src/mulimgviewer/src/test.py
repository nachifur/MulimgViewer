import re
from pathlib import Path

# ===== 配置 =====
LIST_FILE = r"D:\3D_Models\revise3\dianzi\electronic_components_3d_models_7267\electronic_components_3d_models_7267\miss_mtl_list.txt"   # 把你的清单粘贴进这个txt里
DRY_RUN   = False                                  # 先预览；改成 False 才会真正删除
# ===============

# 从清单里提取 Windows 路径（行里出现的 *.obj）
PATTERN = re.compile(r'([A-Za-z]:\\[^:*?"<>|]+?\.obj)\b', re.IGNORECASE)

def iter_obj_paths(list_file: str):
    with open(list_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            for m in PATTERN.finditer(line):
                yield Path(m.group(1))

def main():
    total = deleted = not_exist = errors = 0
    seen = set()

    for p in iter_obj_paths(LIST_FILE):
        if p in seen:
            continue
        seen.add(p)
        total += 1

        if p.suffix.lower() != ".obj":
            print(f"[SKIP] 非 .obj：{p}")
            continue

        if not p.exists():
            not_exist += 1
            print(f"[MISS] 文件不存在：{p}")
            continue

        if DRY_RUN:
            print(f"[DRY] 将删除：{p}")
        else:
            try:
                p.unlink()
                deleted += 1
                print(f"[DEL] 已删除：{p}")
            except Exception as e:
                errors += 1
                print(f"[ERR] 删除失败：{p} ({e})")

    print(f"\n统计：解析 {total} 个；删除 {deleted}；不存在 {not_exist}；错误 {errors}。")
    if DRY_RUN:
        print("提示：把 DRY_RUN=False 再运行一次即可执行删除。")

if __name__ == "__main__":
    main()
