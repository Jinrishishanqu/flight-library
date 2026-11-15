# -*- coding: utf-8 -*-
"""重写《阅读站说明》的「角色档案（角色卡）」整节。"""
from __future__ import annotations

import sys
from pathlib import Path

DOC = Path(r"F:\新建文件夹\read - 副本\文档\阅读站说明.md")

NEW = """## 角色档案（角色卡）

### 数据表

`characters` 一行 = **一部作品里的一个角色**，`(work_id, name)` 唯一。同名角色出现在两部书里就是两行，
简介、性别、出场统计彼此独立 —— **不跨作品合并记录**。

| 列 | 含义 |
|---|---|
| `name` | 正名（别名已在统计阶段并入，见下） |
| `role` | 主角 / 配角（由 `score` 分档，不再有「提及」档） |
| `gender` | 男 / 女 / 不明 |
| `mentions` | 全书出现次数（含别名） |
| `coverage` | **出场范围**：把全文切成 100 块，命中的块数 / 100 |
| `spread` | **跨度**：(最后一次 - 第一次) / 全文字符数 |
| `score` | 综合分，决定 role 与排序 |
| `first_chapter` | 首次出场的节号 |
| `origin` | 原作 / 原创 |
| `bio` | AI 写的 1–4 自然段角色卡正文 |
| `title` `intro` `hue` `looks` `figure` `personality` `relations` `sexual` `sex_tags` `story` | 旧结构化字段，保留但前端已不再渲染 |

### 主角判定：看「铺得开」而不是「喊得多」

```python
K_BLOCKS = 100        # 全文切 100 块
MIN_COVERAGE = 0.04   # 出场范围不足 4% 的不要
ROLE_LEAD = 0.55      # score >= 0.55 → 主角
ROLE_SUB = 0.26       # score >= 0.26 → 配角；再低直接不建卡

score = 0.45 * coverage
      + 0.30 * log(1 + mentions) / log(1 + top_mentions)
      + 0.20 * spread
      + 0.05 * chapter_ratio
```

依据是 **Mendenhall 的 composition characteristic curve**（T. C. Mendenhall, *The Characteristic Curves
of Composition*, Science 1887）：把文本等长切段统计某词出现次数，主角的曲线**高而平**，配角**短而集中**。
只看总次数会把「反复被提一句的路人」判得比「贯穿全书但话不多的人」更重要，所以 `coverage` 权重最高。

`spread` 解决「只在开头出现、之后再没露面」的虚高；`chapter_ratio` 是出现过的节数占比。

**一部作品最多 50 张卡**（`--limit 50`，默认值），实际最多的作品 23 人。

### 人名识别：三道门

角色名候选来自两处：`采集工具\词库\guard.txt` 的专名（原作角色）与 `discover_names.py` 的通用人名发现（作者原创角色）。
后者用姓氏法（百家姓 + 复姓 + 1~2 字）与称谓法（`名字+大人/公子/姑娘/长老/宗主/陛下…`），并过三道门：

1. **`person_score >= 0.30`** —— 名字前后是否接动作词或标点
2. **`head >= MIN_HEAD (0.30)`** —— 名字前面不是汉字的比例。真名 ≥0.48，普通词 ≤0.40（`暴露` 0.17、`高贵` 0.09、`冷冰冰` 0.00）
3. **`strong >= MIN_STRONG (0.04)`** —— 前面是标点、后面紧跟说话/动作动词的比例

再加 `NOT_PERSON` 剔除等级与势力词（`斗者/斗师/斗帝/封号斗罗/魂环…`）与常被误判的叙述词（`闻言`/`少年`/`老者`…）。

### 原作信息表 `采集工具\词库\原作信息.tsv`

手工维护、可无限扩展的制表符文件，**性别等不会因作品而变的设定优先从这里读**：

```
原作	角色	性别	别名	身份	备注
斗破苍穹	萧薰儿	女	萧黛儿|薰儿|熏儿|萧熏儿	古族少女	别名含常见错写
```

- 别名用 `|` 分隔，统计时并入正名（`萧薰儿` 的 3 次字面 + `薰儿` 的 3010 次 → 3013 次）
- 别名同时继承正名的性别
- 目前 151 个角色 / 28 条别名，覆盖 15 部原作
- 旧文件 `采集工具\词库\genders.txt` 仍被读取，但新表优先（`dict.setdefault` 不覆盖）

性别判定的顺序：**原作信息表 → 称谓后缀（仙子/老/婆婆…）→ 名字用字（`FEM_CHAR`/`MALE_CHAR`）→
名字后 4 字内的称呼词 → 「X 的妻子 / X 的夫君」反指 → 不明**。裸代词统计已被证明不可靠（后宫文里
「韩立看着她」的「她」是她），`gender_consensus.py` 与 `gender_from_bio.py` 两个脚本因此作废，留在仓库里备查。

### 生成管线

```
build_characters.py  --limit 50       # 统计 + 定角色 + 写 characters 表
        ↓
prep_bio_input.py --only-missing      # 为缺 bio 的角色出素材包 data/bio_in/<work_id>.txt
        ↓
workflow（子 agent 分批）              # 每个 agent 写 data/bio_out/fill_<tag>_<nn>.json
        ↓
apply_bio.py data/bio_out/*.json      # 回写 characters.bio / bio_at
```

素材包含书名、原作、字数、节数、现有标签、开头 1200 字，以及每个角色 8 条性相关句 + 10 条其他句。
prompt 要求：1–4 自然段连贯散文、不分条不用字段名、写身份/做过的事/性格与说话方式/关系/性经历与偏好、
主动发散、不编造不抄原句、性别判不出填「不明」。

**当前覆盖**：1,647 条角色 / 460 部作品有角色 / 原作 1,450 原创 197 / **bio 100%**（1,647/1,647）。

### 前端渲染

`app.js` 的 `castCard(c)`：有 `bio` 时只渲染 名字+称号 / 角色+`原创`徽标+性别+次数 / `.cast-bio` 逐段 `<p>` /
「全文检索 →」；详情页按 `score DESC` 取前 50 人。

`#/cats` 页的「按角色」与筛选抽屉的「角色」字段用的是 `/api/characters` 的**跨作品导航聚合**
（`name, works, mentions, leads, original`），只回答「这个角色出现在哪几部书里」，
不参与角色卡内容 —— 卡片的 bio 永远只来自当前这部作品。

"""


def main() -> int:
    s = DOC.read_text(encoding="utf-8")
    a = s.index("## 角色档案（角色卡）")
    b = s.index("## 未来：新章节归户")
    out = s[:a] + NEW + s[b:]
    DOC.write_text(out, encoding="utf-8", newline="")
    print(f"写入 {DOC.name}，{len(s)} -> {len(out)} 字符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
