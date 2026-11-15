# -*- coding: utf-8 -*-
import json, io, os, shutil

OUT = r"F:\新建文件夹\read - 副本\采集工具\书库\data\bio_out\fill_b1_10.json"
NEW = r"F:\新建文件夹\read - 副本\采集工具\_tmp_new.json"
BAK = r"F:\新建文件夹\read - 副本\采集工具\书库\data\bio_out\fill_b1_10.bak_before_22_444_340.json"

if os.path.exists(OUT) and not os.path.exists(BAK):
    shutil.copy2(OUT, BAK)

with io.open(NEW, "r", encoding="utf-8") as f:
    new = json.load(f)
mine = {d["work_id"] for d in new}

old = []
if os.path.exists(OUT):
    with io.open(OUT, "r", encoding="utf-8") as f:
        old = json.load(f)
old = [d for d in old if d.get("work_id") not in mine]
data = old + new
data.sort(key=lambda d: d["work_id"])

with io.open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

n = sum(len(d["characters"]) for d in new)
print("file:", OUT)
print("works:", len(new))
print("characters:", n)
print("entries in file:", [d["work_id"] for d in data])
for d in new:
    for c in d["characters"]:
        print(d["work_id"], c["name"], c["gender"], len(c["bio"]))
