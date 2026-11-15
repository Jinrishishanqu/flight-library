# -*- coding: utf-8 -*-
"""把「重复作品整合」小节写进 文档\\阅读站说明.md。"""
from __future__ import annotations

import io
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DOC = ROOT / "文档" / "阅读站说明.md"
DB = ROOT / "采集工具" / "书库" / "data" / "library.db"
ANCHOR = "## API"


def table() -> str:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.id, c.title, p.id, p.title FROM works c "
        "JOIN works p ON p.id = c.merged_into ORDER BY p.id, c.id"
    ).fetchall()
    con.close()
    lines = ["| 被并入 | 并入到 | 说明 |", "| --- | --- | --- |"]
    for cid, ct, pid, pt in rows:
        lines.append(f"| #{cid}《{ct}》 | #{pid}《{pt}》 | 内容被主本覆盖，仅保留索引 |")
    return "\n".join(lines)


BODY = """## 重复作品整合

同一部作品在采集阶段常被拆成多个文件（分卷、单章单发、短版与加长版、异名版），
入库后会变成多条「看起来不同」的记录。整合的目标是**每个作品只留一条可见记录**，
其余标 `merged_into` 指向主本，内容不重复保留。

### 判据

| 层级 | 手段 | 脚本 | 判定 |
| --- | --- | --- | --- |
| 一 | 全文 sha256（去空白后） | `scan_dupes.py` | 完全一致才合并 |
| 二 | 首尾各 1500 字 sha256 | `scan_dupes.py` | 首尾都相同 |
| 三 | 段级指纹 + MinHash/LSH | `dupe_content.py` | containment ≥ 0.85 |
| 四 | 同作异名候选 | `scan_similar.py` | 书名相似 + 内容重合 + 原创角色同名 |

**书名包含不能当依据**：全库有 103 对「书名互相包含」，其中绝大多数是不同作品
（如「斗破苍穹」⊂「斗破苍穹之始于云岚」）。

**续篇不算重复**：`21 南宫婉失身` 与 `22 续-`、`27 冰灵族银宴` 与 `97 续-`、
`338 唐舞麟与娜儿` 与 `320 新-`，互含都是 0.00 —— 是接续写的第二部，须各自独立。

**异本不合并**：`174 黑暗奴隶拍卖大会` 与 `210`（142k vs 148k）互含仅 0.27/0.28。

**人名不同也是异本**：`167 斗破苍穹 魔法学院`（萧薰儿）与 `175 斗破苍穹`（萧黛儿）
段级重合 0.88，但人名被整体替换，合并后目录里会出现大量近似重复章节 —— 保留双版本。

### 段级去重

`merge_works.py` / `merge_works2.py` 的 `unique_text()`：把子作品逐段切分，每段取
去空白后的**前 24 字**作指纹，若该指纹已存在于主本全文则视为重复段落丢弃。
剩余不足 200 字的子作品视为「无独有内容」，只标 `merged_into` 不追加章节。

### 章节排序

整合时不能简单地把子作品章节追加到末尾。规则：

1. 先按**原文件**排序（同一文件内的章节顺序不动，作者原本的顺序就是正确的）
2. 再按**章号**归并：`build_db.py` 的 `chap_no()` 解析「第十二章」这类中文数字，
   `order_by_chapter()` 只在章号序列非单调时才稳定排序
3. 子作品章节标题是「第1节」这种按字数切的编号时**不认**，改用子作品标题里的章号
   （`CHAP_ONLY` 只认「第N章」）
4. 同章号时主本在前、子本在后
5. 子章节标题统一加前缀 `另版 · 原节标题`（由 `fix_merge_prefix.py` 生成，
   不用子书名全名，避免把目录撑满）

### 短章节压缩

原文里章标题连续出现（目录页、卷首列表）会被 `CHAPTER_RE` 当成独立章节，
产生正文只有 20–60 字的「空章」。`build_db.py` 的 `compact_short()` 把正文
短于 `MIN_BODY = 200` 的真章并入下一节开头（最后一节则并入上一节末尾）。

### merged_into 语义

- `works.merged_into` 为 `NULL` 表示可见作品，否则是主本 id
- `/api/works`、`/api/stats`、`/api/sources`、FTS 重灌都默认排除 `merged_into IS NOT NULL`
- `?merged=1` 可查看全部记录（含已合并）
- 详情页访问被合并的作品时显示「已并入《主本》，不再单独展示」并给跳转按钮
- `import_chapter.py` 的候选匹配排除已合并作品，新章节只会追加到主本

### 与未来追加章节的兼容

合并后的主本章节是连续 `idx`，`import_chapter.py` 用
`SELECT MAX(idx) FROM chapters WHERE work_id=?` 定位追加点，实测对合并后的主本照常工作
（34 节的主本插入一节后变 35 节，`max(idx)` 同步变 35）。

### 撤销

```sql
UPDATE works SET merged_into = NULL WHERE id IN (...);
```
再用 `refresh_fts.py` 重灌搜索表。合并前的完整备份在
`采集工具\\书库\\data\\library_before_merge*.db`。

### 当前状态

%s

"""


def main() -> int:
    s = io.open(DOC, encoding="utf-8").read()
    body = BODY % table()
    if "## 重复作品整合" in s:
        i = s.index("## 重复作品整合")
        j = s.index(ANCHOR, i)
        s = s[:i] + body + s[j:]
    else:
        if ANCHOR not in s:
            print("找不到锚点", ANCHOR)
            return 1
        j = s.index(ANCHOR)
        s = s[:j] + body + s[j:]
    io.open(DOC, "w", encoding="utf-8", newline="").write(s)
    print("已写入", DOC, len(s), "字符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
