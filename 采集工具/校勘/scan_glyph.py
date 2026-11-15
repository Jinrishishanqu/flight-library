# -*- coding: utf-8 -*-
"""形近错字普查（作用于 校勘版）"""
import re, sys, csv
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本\校勘版")

# 每条: (名称, 正则, 建议, 说明)
PATS = [
    ("白勺", r"白勺", "的", "「的」被拆成白+勺"),
    ("日作曰", r"(?<![子])曰(?=后|出|落|前|子|常|记|本|光)", "日", "曰/日形近"),
    ("数曰", r"数曰", "数日", "曰/日"),
    ("今曰", r"今曰", "今日", "曰/日"),
    ("昨曰", r"昨曰", "昨日", "曰/日"),
    ("明曰", r"明曰", "明日", "曰/日"),
    ("次曰", r"次曰", "次日", "曰/日"),
    ("当曰", r"当曰", "当日", "曰/日"),
    ("干作千", r"[一二三四五六七八九十几数]干(?=[年月日里万次])", "千", "干/千形近"),
    ("三干", r"三干", "三千", "干/千"),
    ("闻然", r"闻然", "闻言", "然/言"),
    ("猛得", r"猛得(?=[起来了下着])", "猛地", "得/地"),
    ("猛得", r"猛得", "猛地", "得/地"),
    ("他她混", r"(?<=她)[^\u4e00-\u9fff]{0,2}(?=他)", "", "占位"),
    ("全角数字", r"[０-９]", "", "全角数字残留"),
    ("的的", r"的的", "的", "重复"),
    ("了了", r"了了", "了", "重复"),
    ("，，", r"[，、]{2,}", "，", "重复标点"),
    ("。。", r"。{2,}", "。", "重复句号"),
    ("她他", r"她他|他她", "", "人称混用"),
]
PATS = [p for p in PATS if p[0] != "他她混"]

def main():
    rows = []
    stat = {}
    files = sorted(ROOT.rglob("*.txt"))
    for fp in files:
        try:
            t = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print("ERR", fp, e, file=sys.stderr)
            continue
        for name, pat, fix, note in PATS:
            for m in re.finditer(pat, t):
                a = max(0, m.start() - 16)
                b = min(len(t), m.end() + 16)
                ctx = t[a:b].replace("\n", "⏎").replace("\r", "")
                rows.append([name, str(fp.relative_to(ROOT)), m.start(), m.group(0), fix, ctx])
                stat[name] = stat.get(name, 0) + 1

    out = Path(r"F:\新建文件夹\read - 副本\采集工具\记录\形近错字普查.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "file", "offset", "hit", "suggest", "context"])
        w.writerows(rows)

    print(f"files={len(files)} rows={len(rows)}")
    for k, v in sorted(stat.items(), key=lambda x: -x[1]):
        print(f"  {k}\t{v}")
    print("out:", out)

if __name__ == "__main__":
    main()
