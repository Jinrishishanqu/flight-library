# -*- coding: utf-8 -*-
"""补齐 works 表里由现有数据可以推导出来的元数据。

补的字段：
- `path_source`  原文路径（从 `采集工具\记录\校对清单.csv` 的 Output→Sources 映射）
- `pairing`      主要角色性别组合（男男 / 女女 / 男女 / 混合 / 空）
- `theme`        主主题（从 tags 按优先级取一个）
- `series`       系列名（同原作 + 书名共有前缀的归为一组，取最长公共前缀）

`description` / `notes` 是人工字段，脚本不写。

用法：
    python fill_meta.py            # 只报告
    python fill_meta.py --apply
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = HERE / "data" / "library.db"
MANIFEST = ROOT / "采集工具" / "记录" / "校对清单.csv"

# 主题优先级：越靠前越像「这本的主打」
THEME_ORDER = [
    "NTR", "绿帽", "调教", "奴役", "催眠", "兽交", "触手", "轮奸", "群交",
    "双修", "春药", "恋足", "足交", "肛交", "口交", "丝袜", "制服", "淫纹",
    "母女", "兄妹", "姐弟", "师生", "后宫", "堕落", "契约", "女神", "女帝",
    "纯爱", "情色",
]


def norm_path(p: str) -> str:
    """把绝对路径统一成相对库根的 `原文\\...` 形式。"""
    p = (p or "").strip().replace("/", "\\")
    marker = "\\原文\\"
    i = p.find(marker)
    if i >= 0:
        return p[i + 1:]
    return p


def load_source_map() -> dict[str, str]:
    """校勘版文件名 -> 原文路径（多分卷用 | 连接）。"""
    out: dict[str, str] = {}
    if not MANIFEST.exists():
        return out
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out_name = (r.get("Output") or "").strip().replace("/", "\\")
            src = (r.get("Sources") or "").strip()
            if not out_name or not src:
                continue
            name = out_name.rsplit("\\", 1)[-1]
            parts = [norm_path(s) for s in src.split("|") if s.strip()]
            out[name] = "|".join(parts)
    return out


def pick_pairing(genders: list[str]) -> str:
    g = [x for x in genders if x in ("男", "女")]
    if len(g) < 2:
        return ""
    m, f = g.count("男"), g.count("女")
    if m and f:
        return "混合" if len(g) > 2 and min(m, f) > 1 else "男女"
    return "男男" if m else "女女"


def pick_theme(tags: list[str]) -> str:
    s = set(tags)
    for t in THEME_ORDER:
        if t in s:
            return t
    return tags[0] if tags else ""


def common_prefix(names: list[str]) -> str:
    if len(names) < 2:
        return ""
    pref = names[0]
    for n in names[1:]:
        while pref and not n.startswith(pref):
            pref = pref[:-1]
    return pref if len(pref) >= 3 else ""


def main() -> int:
    apply_ = "--apply" in sys.argv
    src_map = load_source_map()
    print(f"校对清单映射 {len(src_map)} 条原文路径")

    con = sqlite3.connect(DB, timeout=60)
    rows = con.execute(
        "SELECT id,title,path_canon,path_source,source_work,tags,pairing,theme,series "
        "FROM works WHERE merged_into IS NULL ORDER BY id"
    ).fetchall()
    print(f"可见作品 {len(rows)} 部")

    # 角色性别（每部按 score 取前 3）
    gmap: dict[int, list[str]] = defaultdict(list)
    for wid, g in con.execute(
        "SELECT work_id, gender FROM characters WHERE gender IN ('男','女') "
        "ORDER BY work_id, score DESC, mentions DESC"
    ):
        if len(gmap[wid]) < 3:
            gmap[wid].append(g)

    n_src = n_pair = n_theme = 0
    updates = []
    for wid, title, path_canon, path_source, src_work, tags_j, pairing, theme, series in rows:
        name = (path_canon or "").replace("/", "\\").rsplit("\\", 1)[-1]
        new_src = path_source or src_map.get(name, "")
        try:
            tags = json.loads(tags_j) if tags_j else []
        except Exception:
            tags = []
        new_pair = pairing or pick_pairing(gmap.get(wid, []))
        new_theme = theme or pick_theme(tags)
        if new_src:
            n_src += 1
        if new_pair:
            n_pair += 1
        if new_theme:
            n_theme += 1
        updates.append((new_src, new_pair, new_theme, wid))

    # 系列：同原作内，书名有 ≥3 字公共前缀的归为系列
    by_src: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for wid, title, *_rest in rows:
        s = _rest[1]  # source_work
        if s:
            by_src[s].append((wid, title))
    series_of: dict[int, str] = {}
    for s, items in by_src.items():
        if len(items) < 3:
            continue
        pref = common_prefix([t for _, t in items])
        if pref:
            for wid, _ in items:
                series_of[wid] = f"{s}·{pref.strip('·- ')}"

    print(f"可补 path_source {n_src} / pairing {n_pair} / theme {n_theme} / series {len(series_of)}")

    if apply_:
        con.executemany(
            "UPDATE works SET path_source=?, pairing=?, theme=? WHERE id=?", updates)
        if series_of:
            con.executemany(
                "UPDATE works SET series=? WHERE id=?",
                [(v, k) for k, v in series_of.items()])
        con.commit()
        print("已写库")
        for c in ("path_source", "pairing", "theme", "series"):
            n = con.execute(
                f"SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND {c} IS NOT NULL AND {c} <> ''"
            ).fetchone()[0]
            print(f"  {c:<12} {n} / {len(rows)}")
        samples = con.execute(
            "SELECT id,title,pairing,theme,series,path_source FROM works "
            "WHERE merged_into IS NULL AND pairing <> '' ORDER BY id LIMIT 6"
        ).fetchall()
        for s in samples:
            print("   ", s[0], s[1][:18], "|", s[2], "|", s[3], "|", s[4], "|", s[5][:46])

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
