# -*- coding: utf-8 -*-
"""探查校勘版文本结构：分章情况、文件名模式、目录分布。为建库做准备。"""
import re
import sys
from collections import Counter
from pathlib import Path

BASE = Path(r"F:\新建文件夹\read - 副本\校勘版")
sys.stdout.reconfigure(encoding="utf-8")

CHAPTER = re.compile(
    r"(?m)^[ \t]*(第[0-9零一二三四五六七八九十百千两]+[章节回卷]|序章|楔子|序言|前言|后记|尾声|终章|番外)"
    r"[^\r\n]{0,40}$"
)
PART = re.compile(r"(?m)^[ \t]*(第[0-9零一二三四五六七八九十百千两]+[卷部篇])[^\r\n]{0,40}$")


def load(p: Path) -> str:
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gb18030", "replace")


files = sorted(BASE.rglob("*.txt"))
print(f"总文件 {len(files)}")

stats = Counter()
nochap = []
chap_counts = []
samples = []
for p in files:
    t = load(p)
    ch = CHAPTER.findall(t)
    n = len(ch)
    stats["with_chapter" if n else "no_chapter"] += 1
    chap_counts.append(n)
    if n == 0:
        nochap.append((p.relative_to(BASE), len(t)))
    elif len(samples) < 12:
        m = CHAPTER.search(t)
        samples.append((p.name[:40], m.group(0).strip()[:50] if m else ""))

print(f"有章标题 {stats['with_chapter']}  无章标题 {stats['no_chapter']}")
print(f"章数合计 {sum(chap_counts)}  中位 {sorted(chap_counts)[len(chap_counts)//2]}")
print(f"章数分布: 0章={sum(1 for c in chap_counts if c==0)} "
      f"1-9={sum(1 for c in chap_counts if 1<=c<10)} "
      f"10-49={sum(1 for c in chap_counts if 10<=c<50)} "
      f"50-199={sum(1 for c in chap_counts if 50<=c<200)} "
      f"200+={sum(1 for c in chap_counts if c>=200)}")

print("\n--- 章标题样本 ---")
for name, s in samples:
    print(f"  {name:<42} | {s}")

print("\n--- 无章标题文件（前 25）---")
for rel, ln in nochap[:25]:
    print(f"  {str(rel)[:60]:<62} {ln:>8}")

print("\n--- 目录分布 ---")
for d, c in Counter(p.relative_to(BASE).parts[0] for p in files).most_common():
    print(f"  {d:<20} {c}")

print("\n--- 文件名后缀模式 ---")
suf = Counter()
for p in files:
    stem = p.stem
    m = re.search(r"-(全篇|合集|\d+~\d+|[0-9.]+w|[0-9]+\u5b57)[^-]*$", stem)
    suf[m.group(1) if m else "其他"] += 1
for k, v in suf.most_common(10):
    print(f"  {k:<12} {v}")

print("\n--- 文件名样本（20）---")
for p in files[:20]:
    print(f"  {str(p.relative_to(BASE))[:90]}")
