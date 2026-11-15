# -*- coding: utf-8 -*-
"""编码判决 A/B：现有管线（utf-8 优先，失败 gb18030）vs chardet 7 vs charset-normalizer。
输出 CSV：path,size,mine,mine_ok,chardet,chardet_conf,cn,cn_conf,agree
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import chardet
from charset_normalizer import from_bytes

ROOT = Path(r"F:\新建文件夹\read - 副本")
OUT = ROOT / "采集工具" / "记录" / "编码判决对比.csv"


def mine(raw: bytes) -> tuple[str, bool]:
    try:
        raw.decode("utf-8")
        return "utf-8", True
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gb18030")
        return "gb18030", True
    except UnicodeDecodeError:
        return "gb18030", False


def main() -> int:
    trees = [ROOT / "原文", ROOT / "校勘版"]
    rows = []
    total = 0
    disagree = 0
    for tree in trees:
        for fp in sorted(tree.rglob("*.txt")):
            raw = fp.read_bytes()
            if len(raw) < 200:
                continue
            total += 1
            m, ok = mine(raw)
            det = chardet.detect(raw)
            cd = (det.get("encoding") or "").lower()
            cn_obj = from_bytes(raw).best()
            cn = (cn_obj.encoding if cn_obj else "") or ""
            agree = (cd.replace("_", "-") == m.replace("_", "-"))
            if not agree:
                disagree += 1
            rows.append({
                "path": str(fp.relative_to(ROOT)),
                "size": len(raw),
                "mine": m,
                "mine_ok": int(ok),
                "chardet": cd,
                "chardet_conf": round(float(det.get("confidence") or 0), 3),
                "cn": cn,
                "cn_conf": round(float(cn_obj.percent_chaos) if cn_obj else -1, 3),
                "agree": int(agree),
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"files={total} disagree={disagree}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
