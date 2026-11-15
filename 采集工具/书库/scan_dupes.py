# -*- coding: utf-8 -*-
"""查重普查：找出同一作品的不同版本 / 分卷与合集 / 重复下载。

不直接改库，输出报告供人工确认。

用法：python scan_dupes.py
"""
import hashlib
import io
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
ROOT = HERE.parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 书名里不影响同一性的词
NOISE = re.compile(
    r"《|》|（|）|\(|\)|【|】|\[|\]|·|—|－|-|_|～|~|\s|"
    r"全篇|全集|全本|完结|精校|校对版|加料|无删|完整版|修订版|最终版|合集|合订|"
    r"第[0-9一二三四五六七八九十百]+[章节回卷]|"
    r"[0-9]+(\.[0-9]+)?[wW万]字?"
)


def norm_title(t: str) -> str:
    s = NOISE.sub("", t or "")
    return s.lower()


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()[:16]


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    works = con.execute(
        "SELECT id,title,char_count,chapter_count,path_canon,source_work FROM works ORDER BY id"
    ).fetchall()

    texts = {}
    for w in works:
        p = Path(w["path_canon"])
        if not p.is_absolute():
            p = ROOT / "校勘版" / p
        if not p.exists():
            continue
        raw = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        texts[w["id"]] = raw

    # ---- 1) 内容指纹 ----
    by_full = defaultdict(list)
    by_edge = defaultdict(list)
    for wid, t in texts.items():
        flat = re.sub(r"\s+", "", t)
        by_full[sha1(flat.encode())].append(wid)
        edge = flat[:1500] + "|" + flat[-1500:]
        by_edge[sha1(edge.encode())].append(wid)

    dup_full = [v for v in by_full.values() if len(v) > 1]
    dup_edge = [v for v in by_edge.values() if len(v) > 1]

    # ---- 2) 标题键 ----
    by_key = defaultdict(list)
    for w in works:
        by_key[norm_title(w["title"])].append(w["id"])

    # 标题互相包含（去掉噪声后）
    keys = [(k, v) for k, v in by_key.items() if k]
    keys.sort()
    contain = []
    for i, (k1, v1) in enumerate(keys):
        for k2, v2 in keys[i + 1:]:
            if k1 == k2:
                continue
            if len(k1) >= 4 and k1 in k2:
                contain.append((k1, v1, k2, v2))
            elif len(k2) >= 4 and k2 in k1:
                contain.append((k2, v2, k1, v1))

    title_of = {w["id"]: w["title"] for w in works}
    size_of = {w["id"]: w["char_count"] for w in works}

    def show(ids):
        return " | ".join(f"{i}:{title_of[i][:26]}({size_of[i]//1000}k)" for i in ids)

    print(f"作品 {len(works)}，可读文件 {len(texts)}")
    print(f"\n=== A. 全文完全一致（去空白后 sha 相同）：{len(dup_full)} 组 ===")
    for g in dup_full:
        print("  " + show(g))

    print(f"\n=== B. 首尾各 1500 字一致（疑同一作品不同版本）：{len(dup_edge)} 组 ===")
    for g in dup_edge:
        if g in dup_full:
            continue
        print("  " + show(g))

    print(f"\n=== C. 标题归一化后同名：{sum(1 for v in by_key.values() if len(v) > 1)} 组 ===")
    for k, v in sorted(by_key.items(), key=lambda x: -len(x[1])):
        if len(v) > 1:
            print(f"  [{k}] {show(v)}")

    print(f"\n=== D. 标题互相包含：{len(contain)} 对 ===")
    seen = set()
    for k1, v1, k2, v2 in contain:
        sig = (k1, k2)
        if sig in seen:
            continue
        seen.add(sig)
        print(f"  「{k1}」⊂「{k2}」  {show(v1)}  ->  {show(v2)}")

    out = HERE / "data" / "dupes_report.json"
    out.write_text(json.dumps({
        "full": dup_full, "edge": dup_edge,
        "same_title": {k: v for k, v in by_key.items() if len(v) > 1},
        "contain": [[k1, v1, k2, v2] for k1, v1, k2, v2 in contain],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n报告 -> {out}")
    con.close()


if __name__ == "__main__":
    main()
