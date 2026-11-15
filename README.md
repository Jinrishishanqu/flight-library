# 飞行图书馆

中文同人 / 长篇小说的采集、排版校对、综合校勘与本地阅读站项目。

**当前交付层是 `校勘版\`**（471 篇 / 1,882 万字），在排版稿之上叠加了水印净化、打码还原、专名统一、标点体例与成人语汇还原。
**阅读站**把这一层装进 SQLite 库，提供书架、分类、标签、全文检索与正文阅读。

## 快速开始

```
双击 启动飞行图书馆.cmd        # 起本地服务并打开浏览器（默认 127.0.0.1:8770）
```

或手动：

```powershell
采集工具\书库\启动.cmd
```

## 目录

```
飞行图书馆\
├─ 原文\              源库，字节不动。按原作分子目录（斗破 / 斗罗 / 大主宰 / 武动乾坤 / 神印王座 / 凡人修仙传 / 诛仙 / 元尊 / 仙逆 / 遮天 / 完美世界 / 神墓 / 不死不灭），判不出原作的进「待归类」。不再有「辰东」这种作者合集目录
├─ 校对后文章\        排版层（S1）：只动换行、分段、编码，一个字不改
├─ 校勘版\            成品层（S2+S3）：净化 + 专名 + 标点体例 + 语汇还原  ← 交付用
├─ 采集工具\          抓取 / 入库 / 校对 / 校验 / 去重 / 合并 / OCR / 截图 / 校勘 全套脚本
│  ├─ 词库\           词典知识库：专名、异写、成人语汇、错别字、水印、符号规范
│  ├─ 校勘\           校勘层脚本（重排、形近字、数字、符号、专名、归户）
│  └─ 书库\           SQLite 库 + 本地阅读站
├─ 文档\              规则、报告、索引、结构说明
├─ 站点\              本地静态记录站（双击 index.html）
├─ 归档\              备份 / 重复件 / 旧成品 / 参考源码（可整体删除，不影响主链）
├─ .venv\             Python 3.12 运行环境
├─ .dsh\skills\       chinese-erotic-fiction-writing 写作技能
├─ 启动飞行图书馆.cmd  网站入口
└─ README.md
```

## 工作流

```
原文\  ──①搜集 入库──┐
                      ├─②校对.ps1 / py\build.py──→ 校对后文章\  (S1 排版，零字变)
   采集工具\raw\ ─────┘                                  │
                                                          ├─③校勘流水线──→ 校勘版\  (S2+S3)
                                                          │
                                                          └─④校验.ps1 / py\verify.py
                                                                  │
                                                        ⑤build_db.py──→ 阅读站
```

三层职责严格分离，越往下改动越大：

| 层 | 目录 | 允许改动 | 校验方式 |
|---|---|---|---|
| S0 源 | `原文\` | 不改（采集后即冻结） | 只有新增 |
| S1 排版 | `校对后文章\` | 换行、空行、段落、编码 | 忽略空白后字符序列必须与原文一致 |
| S2 净化 | `校勘版\` | 水印、打码、专名、错别字 | 逐层计数 + 抽样上下文核验 |
| S3 体例 | `校勘版\` | 引号、破折号、省略号、语汇 | 全库符号普查 |

## 常用命令

```powershell
# 抓取 → 入库 → 校对 → 校验 一条龙
pwsh -File 采集工具\run-all.ps1 -Tags 斗破苍穹,斗罗大陆 -Pages 2

# 只重跑排版层
pwsh -File 采集工具\校对.ps1 -Force
pwsh -File 采集工具\校验.ps1

# 重建书目索引 → 文档\书目索引.csv
pwsh -File 采集工具\索引.ps1

# 去重（5-gram Jaccard），重复件移入 归档\重复_根级\
pwsh -File 采集工具\查重.ps1 -Apply

# 校勘流水线（在远端 10.26.56.12 的 D:\article_tools 跑，见 文档\校勘报告.md）
ssh dsh "D:\article_tools\.venv-csc\Scripts\python.exe D:\article_tools\work\normalize_sex_style.py"

# 章结构（标题粘连 / 重复章）
.venv\Scripts\python.exe 采集工具\校勘\diagnose_structure.py
.venv\Scripts\python.exe 采集工具\校勘\restore_chapter_titles.py --dry
.venv\Scripts\python.exe 采集工具\校勘\report_structure_issues.py

# 阅读站（471 部 / 3,508 节，含全文检索与角色卡）
启动飞行图书馆.cmd
& .venv\Scripts\python.exe 采集工具\书库\build_db.py --rebuild          # 内容变动后重建库
& .venv\Scripts\python.exe 采集工具\书库\build_characters.py --limit 8   # 重建角色档案

# 新章节归户：先诊断，确认后 --apply 追加
& .venv\Scripts\python.exe 采集工具\书库\import_chapter.py 新章.txt
& .venv\Scripts\python.exe 采集工具\书库\import_chapter.py 新章.txt --apply

# 书目整理（改名 / 同作合并 / 目录归类 / 章节按原文重切）
& .venv\Scripts\python.exe 采集工具\书库\fix_titles.py --dry        # 书名去序号、去合集标记
& .venv\Scripts\python.exe 采集工具\书库\scan_similar.py             # 找同作异名候选
& .venv\Scripts\python.exe 采集工具\书库\compare_pair.py 367 388     # 并排读原文确认
& .venv\Scripts\python.exe 采集工具\书库\merge_works2.py --apply     # 按章号排序合并
& .venv\Scripts\python.exe 采集工具\书库\classify_source.py --apply  # 辰东/待归类 → 具体作品
& .venv\Scripts\python.exe 采集工具\书库\update_source_works.py --apply
& .venv\Scripts\python.exe 采集工具\书库\rebuild_chapters.py --dry   # 章节按原文「第N章」重切
& .venv\Scripts\python.exe 采集工具\书库\refresh_fts.py              # 改库后重灌检索索引
```

## 阅读站

- 作品详情页展示 **AI 写成的作品简介** 与 **主要角色卡**（1–4 个自然段的角色描述，原作角色与作者原创角色用「原创」徽标区分）

`采集工具\书库\` 是独立于 `站点\` 的本地文库站：SQLite 库 + 零依赖 HTTP 服务 + 原生 JS 前端。
书架 / 分类浏览 / 标签 / 全文检索（bm25）/ 作品详情（含角色卡）/ 正文阅读（字号行高主题、进度记忆、目录抽屉）。
新到的章节可用 `import_chapter.py` 按 sha256 / 开篇指纹 / 书名 / 角色共现自动归户并追加，不覆盖已有章节。
细节见 `文档\阅读站说明.md`。

## 版本库

远端：<https://github.com/Jinrishishanqu/flight-library.git>

仓库只跟踪**代码、脚本、文档、词库**；语料（`原文\` / `校对后文章\` / `校勘版\`）、数据库（`library.db`）、`归档\`、`.venv\` 都在 `.gitignore` 里，靠本地文件与备份维持。

## 文档

| 文件 | 内容 |
|---|---|
| `文档\校对规则.md` | S1 排版规则全文（`校对.ps1` / `py\normalize.py` 的实现依据） |
| `文档\校勘报告.md` | S2+S3 校勘：逐层数字、校验方法、保留项、回滚路径 |
| `文档\目录结构说明.md` | 每个目录与 `归档\` 子目录的用途、可否删除 |
| `文档\阅读站说明.md` | 书库 schema、API、前端结构、阅读排版参数、角色卡、新章节归户流程 |
| `文档\阅读站-设计规范.md` | 配色 / 排版 / 字体 / 交互的设计依据与实测数据 |
| `文档\整合报告.md` | 同书散件的整合过程与结论 |
| `文档\资源包清单.md` | 外部资源站清单（可用性、门槛、抓法） |
| `文档\男同审计.md` | BL 内容审计结论 |
| `文档\书目索引.csv` | `原文\` 全量索引（Group / File / Chars / KB / Enc） |
| `采集工具\README.md` | 抓取工具链操作手册（检索词打法、H 度判定、各源状态） |

## 回滚

- 校勘层：删除 `校勘版\` 即回到排版层，`校对后文章\` 不受影响。
- 排版层：`校对后文章\` 可整体由 `原文\` 重跑 `py\build.py` 再生。
- 旧成品：`归档\旧版成品\` 下有 final7、弯引号前、形近字前、重排前、数字前、reflow 各版快照。
- 合并 / 去重的原件：`归档\备份_整合前\`、`归档\备份_校对后\`、`归档\重复_根级\`、`归档\重复_校对后\`。
