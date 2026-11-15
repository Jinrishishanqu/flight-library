# -*- coding: utf-8 -*-
import json, io
OUT = r"F:\新建文件夹\read - 副本\采集工具\书库\data\bio_out\fill_b1_10.json"
with io.open(OUT, "r", encoding="utf-8") as f:
    d = json.load(f)
print("json ok, top-level entries:", len(d))
for e in d:
    names = "、".join(c["name"] + "/" + c["gender"] for c in e["characters"])
    print(e["work_id"], "->", names)
mine = [e for e in d if e["work_id"] in (22, 444, 340)]
print("mine works:", len(mine), "mine chars:", sum(len(e["characters"]) for e in mine))
print("has summary key:", any("summary" in e for e in d))
