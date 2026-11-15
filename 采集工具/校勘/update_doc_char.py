import io
import re

P = r"F:\新建文件夹\read - 副本\文档\阅读站说明.md"
s = io.open(P, encoding="utf-8").read()

NEW = """## 角色档案（角色卡）

每部作品在详情页「主要角色」区展示 1–8 张角色卡，位置在目录之前。数据全部由脚本从正文抽取，再交给模型写成自然段描述。

### 表结构

`characters` 表关键列：

| 列 | 含义 |
|---|---|
| `name` | 角色名 |
| `role` | 主角 / 配角（提及级角色不入库） |
| `origin` | **原作**（命中 `词库\guard.txt`）/ **原创**（作者自创，靠 `discover_names.py` 发现） |
| `gender` | 男 / 女 / 不明 |
| `mentions` | 全书出现次数 |
| `first_chapter` | 首次出场的节号 |
| `title` | 身份（女王、宗主、封号斗罗…，需同作共现 ≥2 次才认） |
| `intro` | 首现节的一句原文（供生成时参考，前端不再展示） |
| `bio` | **模型写成的 1–4 自然段角色描述**（前端展示的就是它） |
| `bio_at` | bio 生成时间 |
| `story` / `looks` / `figure` / `personality` / `relations` / `sexual` | 旧的结构化字段，bio 缺失时前端回落使用 |

`works` 表有 `summary_ai` / `summary_at`：AI 写成的作品简介，优先于原始的 `summary`。

### 原作角色 vs 原创角色

- **原作角色**：名字在 `采集工具\词库\guard.txt`（104 个斗破/斗罗/诛仙/凡人/大主宰/武动/元尊/遮天/神印人物）里，`origin='原作'`。
- **原创角色**：`采集工具\书库\discover_names.py` 从正文里独立发现的姓名，不在 guard 里，`origin='原创'`，前端卡片上带一枚「原创」小标签。

`discover_names.py` 的判据（缺一不可）：

1. 姓氏法（百家姓单姓 + 复姓表 × 1~2 字）或称谓法（`X大人 / X娘娘 / X公子 / X姑娘 …`）
2. 全书出现 ≥ 6 次
3. `person_score ≥ 0.5` —— 名字前后要跟动作/标点，不是被量词修饰的普通词
4. **末字必须属于 `NAME_CHAR`** —— 挡掉「金币」「毕竟」「屈辱」「冷汗瞬」这类切坏的词
5. 首字不在 `BAD_NAME_HEAD`（后前中上下里外内这那何每某各该本原来去到从向对把被让使给和与同跟及并或而则就都也又还且但却是在），末字不在 `BAD_TAIL`（地得着的然着了过著们么呢吧啊呀）
6. 三字候选若前两字单独高频（`full.count(w[:2]) >= n * 3`）则判为切坏并丢弃（「冉绝刚」12 次 vs「冉绝」3698 次）
7. 不在 `STOP_WORDS`（温柔、安静、明白、江湖、江山…）

### 生成管线

```
build_characters.py      抽角色骨架（guard + discover_names），保留已有 bio 按 name 回填
        ↓
prep_bio_input.py        每部写 data\\bio_in\\<work_id>.txt：书名/原作/字数/节数/标签
                         + 开头 1200 字 + 每角色 8 条性相关句 + 10 条其他句
        ↓
（模型生成）               agent 直接把结果写进 data\\bio_out\\<tag>_<nn>_<a>-<b>.json
        ↓
apply_bio.py             读 JSON，写 works.summary_ai 与 characters.bio
```

命令：

```powershell
$py = "..\\..\\.venv\\Scripts\\python.exe"
& $py build_characters.py --limit 10            # 全库重建（约 450 秒）
& $py prep_bio_input.py --max 600               # 或有角色作品；加 --all 连无角色作品也出素材
& $py apply_bio.py data\\bio_out\\d1_*.json      # 可一次传多个文件
```

生成端的 prompt 要点：简介 140–240 字一到两自然段、不用「本文讲述了」开头；bio 1–4 个自然段连贯散文、不分条不用字段名、写身份/做过的事/性格与说话方式/关系/性经历与偏好、允许合理发散、性别判不出填「不明」、不抄原句。

当前覆盖：**486/486 部有 AI 简介，1118/1118 条角色有 bio**。

### 前端渲染

`app.js` 的 `castCard(c)`：有 `bio` 时只渲染 名字 + 称号 / 角色 + 「原创」徽标 + 性别 + 次数 / `div.cast-bio` 逐段 `<p>` / 「全文检索 →」；没有 `bio` 时回落到旧的 `cast-dl`（外貌·身体·性格·关系）与「性」标签块。

`components.css` 对应 `.cast`（`minmax(300px,1fr)` 网格）、`.cast-card`、`.cast-origin`（accent 描边小标签）、`.cast-bio p`（.84rem / 行高 1.85 / 2em 缩进）。

"""

start = s.index("## 角色档案（角色卡）")
end = s.index("## 未来：新章节归户")
s = s[:start] + NEW + s[end:]
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok", len(s))
