# -*- coding: utf-8 -*-
"""hanlp 人名识别（PER）封装：全库建缓存 + 读取。

用法：
    python ner_hanlp.py --build            # 全库跑一遍，写 data/ner/<work_id>.json
    python ner_hanlp.py --build --ids 1,2  # 只跑指定作品
    python ner_hanlp.py --probe 185        # 打印某一部的结果

设计：
- 模型懒加载 + 单例；pipeline 必须先分词再 NER（直接喂字符串会按字符序列处理）
- 结果按 work_id 缓存成 JSON，重建角色时直接读，不重复跑模型
- 后处理四步：去单字 / 剥引号 / 前缀归并 / （可选）jieba 常用词过滤
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "采集工具" / "书库" / "data" / "library.db"
NER_DIR = ROOT / "采集工具" / "书库" / "data" / "ner"

QUOTE_HEAD = "「」『』“”‘’\"'（）()【】[]《》〈〉 \t\r\n"
_PIPE = None
_FREQ: dict | None = None
_JIEBA_OK: bool | None = None


def get_pipe():
    global _PIPE
    if _PIPE is None:
        import hanlp

        tok = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
        ner = hanlp.load(hanlp.pretrained.ner.MSRA_NER_ELECTRA_SMALL_ZH)
        _PIPE = (
            hanlp.pipeline()
            .append(tok, output_key="tok")
            .append(ner, input_key="tok", output_key="ner")
        )
    return _PIPE


def get_freq() -> dict | None:
    global _FREQ, _JIEBA_OK
    if _JIEBA_OK is None:
        try:
            import jieba

            jieba.initialize()
            _FREQ = jieba.dt.FREQ
            _JIEBA_OK = True
        except Exception:
            _FREQ = None
            _JIEBA_OK = False
    return _FREQ


def raw_persons(text: str, chunk: int = 500, batch: int = 8) -> Counter:
    """跑 hanlp，返回原始 PERSON 计数（未后处理）。"""
    pipe = get_pipe()
    if not text.strip():
        return Counter()
    chunks = [text[i : i + chunk] for i in range(0, len(text), chunk)]
    docs = pipe(chunks, batch_size=batch)
    if isinstance(docs, dict):
        ner_list = docs["ner"]
    else:
        ner_list = [d["ner"] if isinstance(d, dict) else d for d in docs]
    cnt: Counter[str] = Counter()
    for ner in ner_list:
        for item in ner:
            if item[1] == "PERSON":
                cnt[item[0]] += 1
    return cnt


def postprocess(cnt: Counter, use_jieba: bool = True, min_len: int = 2) -> Counter:
    """去单字 → 剥引号 → 前缀归并 → 常用词过滤。"""
    c: Counter[str] = Counter()
    for w, n in cnt.items():
        w2 = w.strip(QUOTE_HEAD)
        if len(w2) < min_len:
            continue
        if not re.fullmatch(r"[\u4e00-\u9fff·]+", w2):
            continue
        c[w2] += n

    # 前缀归并：`萧炎成`(1) 与 `萧炎`(18) 同时出现 → 低频并进高频
    items = sorted(c.items(), key=lambda x: -x[1])
    keep: dict[str, int] = {}
    for w, n in items:
        merged = False
        for k, kn in keep.items():
            if w != k and w.startswith(k) and kn >= n * 3:
                keep[k] = kn + n
                merged = True
                break
        if not merged:
            keep[w] = n
    out = Counter(keep)

    if use_jieba:
        freq = get_freq()
        if freq:
            # 只砍「明确的常用词」，阈值取 50 避免误杀「梅子」这类人名
            for w in list(out):
                if freq.get(w, 0) >= 50:
                    del out[w]
    return out


def cache_path(wid: int) -> Path:
    return NER_DIR / f"{wid}.json"


def persons_of(wid: int, text: str | None = None, use_jieba: bool = True) -> Counter:
    """优先读缓存；无缓存且有 text 时现算并写缓存。"""
    fp = cache_path(wid)
    if fp.exists():
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
            return Counter(d.get("persons") or {})
        except Exception:
            pass
    if text is None:
        return Counter()
    raw = raw_persons(text)
    clean = postprocess(raw, use_jieba=use_jieba)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(
            {"raw": dict(raw), "persons": dict(clean), "chars": len(text)},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return clean


def work_text(con: sqlite3.Connection, wid: int) -> str:
    rows = con.execute(
        "SELECT content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
    ).fetchall()
    return "\n".join(r[0] or "" for r in rows)


def build(ids: list[int] | None, use_jieba: bool) -> int:
    con = sqlite3.connect(DB)
    if ids:
        q = "SELECT id,title FROM works WHERE id IN (%s)" % ",".join("?" * len(ids))
        works = con.execute(q, ids).fetchall()
    else:
        works = con.execute(
            "SELECT id,title FROM works WHERE merged_into IS NULL ORDER BY char_count DESC"
        ).fetchall()
    print(f"共 {len(works)} 部待处理", flush=True)
    t0 = time.time()
    total = 0
    for i, (wid, title) in enumerate(works, 1):
        if cache_path(wid).exists():
            continue
        text = work_text(con, wid)
        if not text:
            continue
        raw = raw_persons(text)
        clean = postprocess(raw, use_jieba=use_jieba)
        fp = cache_path(wid)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(
            json.dumps(
                {"raw": dict(raw), "persons": dict(clean), "chars": len(text)},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        total += len(text)
        if i % 10 == 0 or i == len(works):
            el = time.time() - t0
            print(
                f"[{i}/{len(works)}] {total} 字 / {el:.0f}s "
                f"→ {total / max(el, 1e-6):.0f} 字/秒 | {title[:28]}",
                flush=True,
            )
    con.close()
    print(f"完成：{len(works)} 部，{total} 字，{time.time() - t0:.0f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--ids", default="")
    ap.add_argument("--probe", type=int, default=0)
    ap.add_argument("--no-jieba", action="store_true")
    a = ap.parse_args()

    if a.probe:
        con = sqlite3.connect(DB)
        title = con.execute("SELECT title FROM works WHERE id=?", (a.probe,)).fetchone()
        text = work_text(con, a.probe)
        con.close()
        raw = raw_persons(text)
        clean = postprocess(raw, use_jieba=not a.no_jieba)
        print(f"#{a.probe} {title[0] if title else '?'} / {len(text)} 字")
        print(f"原始 PERSON 去重 {len(raw)} → 后处理 {len(clean)}")
        for w, n in clean.most_common(40):
            print(f"  {w}\t{n}")
        print("\n被过滤掉的高频词：")
        for w, n in raw.most_common(40):
            if w not in clean:
                print(f"  {w}\t{n}")
        return 0

    if a.build:
        ids = [int(x) for x in a.ids.split(",") if x.strip()] if a.ids else None
        return build(ids, use_jieba=not a.no_jieba)

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
