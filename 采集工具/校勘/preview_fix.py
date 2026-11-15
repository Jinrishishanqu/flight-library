# -*- coding: utf-8 -*-
"""为「混用」文件生成修正预览（不写回原库）

输出:
  D:\\article_tools\\out\\preview\\<原名>.txt   修正后全文
  D:\\article_tools\\out\\preview\\patch.csv    逐处台账(含行号/上下文/diff校验)
  D:\\article_tools\\out\\preview\\preview_report.txt
"""
import csv, os, sys, collections
from diff_match_patch import diff_match_patch

HITS = r"D:\article_tools\work\hits.csv"
LEX = r"D:\article_tools\lexicon"
OUT = r"D:\article_tools\out\preview"
EXCLUDE_DIRS = {"归档", "_校勘版", "_legacy"}

os.makedirs(OUT, exist_ok=True)

conf = {}
with open(os.path.join(LEX, "confusion.txt"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.replace("\t", " ").split()
        if len(p) >= 2:
            conf[p[0]] = p[1]

def is_excluded(path):
    return any(p in EXCLUDE_DIRS for p in path.replace("\\", "/").split("/"))

rows = [r for r in csv.DictReader(open(HITS, encoding="utf-8-sig")) if not is_excluded(r["file"])]
by_file = collections.defaultdict(list)
for r in rows:
    by_file[r["file"]].append(r)

dmp = diff_match_patch()
patch_rows = []
report = []
n_changed = 0

for fp, rs in sorted(by_file.items()):
    with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
        text = fh.read()

    # 只处理混用文件（同一文件里既有异写又有正写）
    groups = {}
    for r in rs:
        groups.setdefault((r["variant"], r["canon"]), []).append(int(r["offset"]))
    to_fix = []
    for (bad, good), offs in groups.items():
        if text.count(good) > 0:          # mixed
            to_fix.extend((o, bad, good) for o in offs)
    if not to_fix:
        continue

    to_fix.sort(key=lambda x: -x[0])
    out = text
    for off, bad, good in to_fix:
        if out[off:off + len(bad)] != bad:
            continue
        out = out[:off] + good + out[off + len(bad):]

    # diff 校验：只有 replace 且 old==bad new==good
    diffs = dmp.diff_main(text, out)
    ops = collections.Counter(op for op, _ in diffs)

    name = os.path.basename(fp)
    stem = os.path.splitext(name)[0]
    dest = os.path.join(OUT, stem + ".fixed.txt")
    with open(dest, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)

    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    import bisect
    lineno = lambda off: bisect.bisect_right(starts, off)

    for off, bad, good in sorted(to_fix):
        ctx = text[max(0, off - 25):off + len(bad) + 25].replace("\r", "").replace("\n", "\u23ce")
        patch_rows.append([name, lineno(off), off, bad, good, ctx])

    n_changed += len(to_fix)
    report.append(f"{name}\tfix={len(to_fix)}\tchars {len(text)}->{len(out)}\tdiff_ops={dict(ops)}")

with open(os.path.join(OUT, "patch.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["file", "line", "offset", "old", "new", "context"])
    w.writerows(patch_rows)

with open(os.path.join(OUT, "preview_report.txt"), "w", encoding="utf-8") as f:
    f.write(f"files_changed={len(report)} total_fixes={n_changed}\n\n")
    f.write("\n".join(report))

print(f"files_changed={len(report)} total_fixes={n_changed}")
print("\n".join(report[:15]))
print("...")
