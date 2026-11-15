# -*- coding: utf-8 -*-
"""词库统一加载器。校勘脚本、数据库构建、网站后端共用这一份真相源。

用法：
    from lib import Lexicon
    lx = Lexicon()                    # 默认读本目录
    lx.guard                          # ['萧炎', '薰儿', ...]
    lx.confusion                      # {'熏儿': '薰儿', ...}
    lx.sex_terms                      # {'肉棒': 'male', ...}
    lx.build_gap_regex('肉棒')        # 编译「肉[^汉字]{1,3}棒」的正则
    lx.split_candidates('私，处')      # 判断一个 X，Y 是否命中词表断词
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _read_lines(name: str) -> list[str]:
    p = HERE / name
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _read_tsv(name: str, min_cols: int = 2) -> list[list[str]]:
    rows = []
    for line in _read_lines(name):
        cols = line.split("\t")
        if len(cols) >= min_cols:
            rows.append(cols)
    return rows


class Lexicon:
    """词库只读视图。所有数据文件均为纯文本，可直接手工编辑扩容。"""

    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else HERE
        self._cache: dict[str, object] = {}

    # ---------- 专名 ----------
    @property
    def guard(self) -> list[str]:
        if "guard" not in self._cache:
            self._cache["guard"] = _read_lines("guard.txt")
        return self._cache["guard"]  # type: ignore[return-value]

    @property
    def confusion(self) -> dict[str, str]:
        """错写 → 正写。带作用域的行第二列是正写，第三列是作用域。"""
        if "confusion" not in self._cache:
            m: dict[str, str] = {}
            for cols in _read_tsv("confusion.txt"):
                # 去掉备注列可能带的括号说明
                wrong = cols[0].strip()
                right = cols[1].split("（")[0].strip()
                if wrong and right and not wrong.startswith("#"):
                    m[wrong] = right
            self._cache["confusion"] = m
        return self._cache["confusion"]  # type: ignore[return-value]

    @property
    def confusion_scoped(self) -> list[tuple[str, str, str]]:
        """(错写, 正写, 作用域) —— 作用域为 global 或作品目录名。"""
        out = []
        for cols in _read_tsv("confusion.txt"):
            wrong = cols[0].strip()
            right = cols[1].split("（")[0].strip()
            scope = cols[2].strip() if len(cols) > 2 else "global"
            if wrong and right:
                out.append((wrong, right, scope))
        return out

    # ---------- 情色词表 ----------
    @property
    def sex_terms(self) -> dict[str, str]:
        """词 → 类别。"""
        if "sex" not in self._cache:
            m: dict[str, str] = {}
            for cols in _read_tsv("sex_terms.txt"):
                m[cols[0].strip()] = cols[1].strip()
            self._cache["sex"] = m
        return self._cache["sex"]  # type: ignore[return-value]

    @property
    def sex_words(self) -> list[str]:
        """按长度倒序，长词优先匹配。"""
        return sorted(self.sex_terms, key=len, reverse=True)

    def terms_by_kind(self, kind: str) -> list[str]:
        return [w for w, k in self.sex_terms.items() if k == kind]

    # ---------- 错别字 ----------
    @property
    def typos(self) -> dict[str, str]:
        if "typos" not in self._cache:
            m: dict[str, str] = {}
            for cols in _read_tsv("typos.txt"):
                m[cols[0].strip()] = cols[1].strip()
            self._cache["typos"] = m
        return self._cache["typos"]  # type: ignore[return-value]

    @property
    def typo_counts(self) -> dict[str, int]:
        out = {}
        for cols in _read_tsv("typos.txt"):
            if len(cols) > 2:
                try:
                    out[cols[0].strip()] = int(cols[2])
                except ValueError:
                    pass
        return out

    # ---------- 异体字 / 水印 ----------
    @property
    def char_variants(self) -> dict[str, str]:
        if "cv" not in self._cache:
            self._cache["cv"] = {c[0].strip(): c[1].strip() for c in _read_tsv("char_variants.txt")}
        return self._cache["cv"]  # type: ignore[return-value]

    @property
    def watermark(self) -> list[str]:
        if "wm" not in self._cache:
            self._cache["wm"] = sorted(_read_lines("watermark.txt"), key=len, reverse=True)
        return self._cache["wm"]  # type: ignore[return-value]

    # ---------- 机器可读模式 ----------
    @property
    def variants(self) -> dict:
        if "var" not in self._cache:
            p = self.root / "variants.json"
            self._cache["var"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return self._cache["var"]  # type: ignore[return-value]

    @property
    def symbols(self) -> dict:
        if "sym" not in self._cache:
            p = self.root / "symbols.json"
            self._cache["sym"] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        return self._cache["sym"]  # type: ignore[return-value]

    # ---------- 工具方法 ----------
    @staticmethod
    def build_gap_regex(word: str, gap: str = r"[^\u4e00-\u9fff\r\n]{1,3}") -> re.Pattern:
        """生成「词内允许插入 gap」的正则，用于识别 肉…棒 / 乳#头 / 高k潮。"""
        body = gap.join(map(re.escape, list(word)))
        return re.compile(body)

    def split_words(self, x: str, y: str) -> bool:
        """判断 X，Y 是否是被标点切开的词（XY 在词表内）。"""
        return (x + y) in self.sex_terms

    def compile_all_gap(self, words: list[str] | None = None) -> list[tuple[str, re.Pattern]]:
        """一批词的 gap 正则，按词长倒序。"""
        ws = words or self.sex_words
        return [(w, self.build_gap_regex(w)) for w in sorted(ws, key=len, reverse=True)]

    def stats(self) -> dict:
        return {
            "guard": len(self.guard),
            "confusion": len(self.confusion),
            "sex_terms": len(self.sex_terms),
            "typos": len(self.typos),
            "char_variants": len(self.char_variants),
            "watermark": len(self.watermark),
        }


if __name__ == "__main__":
    lx = Lexicon()
    for k, v in lx.stats().items():
        print(f"{k:>14}: {v}")
    print("\n分类计数：")
    from collections import Counter

    for k, n in Counter(lx.sex_terms.values()).most_common():
        print(f"  {k:>8}: {n}")
