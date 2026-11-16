# agent/ — 文库整理流水线

把「采集 → 校勘 → 入库 → 角色与索引 → AI 补全」这一串环节收进一个可重跑、
可记账、能断点续跑的执行器。**不替代** `采集工具\` 里的脚本，而是给它们一个
统一的调度层：每个环节知道自己依赖谁、跳过条件是什么、产出必须满足什么。

```
python -m agent run lib      # 重建数据库 → 章节 → 角色 → 索引 → 自检
python -m agent run canon    # 校对后文章 → 校勘版（字符级清洗）
python -m agent run ai       # 只跑需要模型的部分
python -m agent status       # 最近运行
python -m agent report 12    # 某次运行逐环节明细
python -m agent list         # 所有环节与依赖
```

---

## 为什么自己写，不用 Prefect / Dagster / LangGraph

调研过（2026-11，实查 PyPI 与仓库状态）：Prefect 3.9.3、Dagster 1.13.30、
LangGraph 1.2.22、Temporal、Luigi 都能跑这套流程，但**它们解决的都不是这里的瓶颈**。

| 需求 | 框架能给什么 | 结论 |
|---|---|---|
| 编排顺序 | DAG，声明式 | 我们只需要「按声明顺序 + needs 排序」，300 行够了 |
| 断点续跑 | 靠 task 结果缓存 | 真正的幂等 key 要业务定义（见下），框架给不了 |
| 重试 | 有 | 已有；LLM 层单独做退避更细 |
| 可观测 | UI / 事件流 | 我们只问「哪部作品花了多少钱、哪步失败了」，一张 SQLite 表更直接 |
| 状态搬运 | TypedDict / asset / IO manager | 本项目流动的是**磁盘文件路径 + 库里的一行**，让它们进内存纯属搬运 |

代价：引入 Prefect 要多 30 个传递依赖（fastapi/uvicorn/sqlalchemy/alembic/docker/orjson…），
而它最贵的部分（持久化调度、分布式执行）在这里一次都用不上。

LLM 层只用官方 `openai` 3.51（wheel 2.3MB，6 个直接依赖）。不引 LiteLLM（38MB）也不用
Instructor（为几千次一次性补全引入一层 DSL 不值；等 JSON 不合规率超过 2–3% 再考虑）。

---

## 目录

```
agent/
  config.toml          路径 / 模型 / 预算 / 幂等开关
  core/
    config.py          读配置，路径一律绝对化
    ledger.py          SQLite 台账：runs / steps / ai_calls / artifacts
    llm.py             OpenAI 兼容端点 + json_schema + 并发 + 记账 + 熔断
    stage.py           Stage 声明、Ctx（调脚本 / 访问库）、指纹函数
    runner.py          拓扑排序、幂等跳过、门禁、日志
    apply.py           AI 产物入库（与生成分离）
  stages/
    library.py         采集与文库（script）
    canon.py           校勘（script + 1 个 hybrid）
    ai.py              bio / summary / text_proof（ai + hybrid）
  pipelines/
    lib.toml           只跑库
    canon.toml         只跑清洗
    ai.toml            只跑 AI
    full.toml          全量
  state/               运行时产物（已 gitignore）
    ledger.db          台账
    logs/run_<id>.log  每次运行的完整日志
    out/<stage>/*.json AI 原始产物
    reports/           复核报告
```

---

## 三种环节，怎么定

这是整个设计里最要紧的一条判据（用户 m10197 / m10198）：

> 能用脚本可靠判定的绝不花 token；脚本结果不达标的才交给模型。

| kind | 判据 | 例子 |
|---|---|---|
| `script` | 同一批输入重跑结果确定，且能用**不变量**验收（字数、文件数、字符集、依赖关系） | 全角转半角（字数不变）、章节切分（拼接后与原文差 <0.3%）、FTS 重灌（FTS 行数 = 可见章节数） |
| `ai` | 判断需要读语义：这个角色是谁、这本书讲什么、这处是不是错字 | bio、summary、text_proof |
| `hybrid` | 脚本能筛出「可疑」，但裁定要人/模型 | 字符体检（脚本报可疑字符，AI 判是不是错字） |

`check()` 就是这条判据的落地点。**门禁不过就 failed，不带病往下走** ——
这是把「脚本结果不完美」变成「看得见的失败」，而不是继续产出脏数据。

---

## AI API 怎么配

只有 `config.toml` 的 `[llm]` 一段与一个环境变量，改完立即生效，不用重启任何服务。

**A. OpenAI 官方（最短路径）**

```powershell
setx OPENAI_API_KEY "sk-..."        # 设完要开新终端
.\.venv\Scripts\python.exe -m agent run ai bio --dry     # 能打印环节 = 配好了
```

`base_url` / `model` 保持默认（`https://api.openai.com/v1` / `gpt-4o-mini`）。

**B. 任何 OpenAI 兼容服务**（DeepSeek / 硅基流动 / 智谱 / 本地 vLLM / one-api）

只改 `config.toml` 这四行：

```toml
base_url = "https://api.deepseek.com/v1"
model    = "deepseek-chat"
price_in_per_mtok  = 0.14      # 换成对方的实际价格，否则记账是错的
price_out_per_mtok = 0.28
```

`api_key_env` 指向你设的环境变量名即可；也可以直接把 key 写进 `api_key`。
**唯一的硬要求：对方必须支持 `response_format={"type":"json_schema"}`。**
只支持 `json_object` 的服务会在 `chat_json()` 处报 400。

**C. 本地模型**

```toml
base_url = "http://127.0.0.1:8000/v1"
model    = "你的模型名"
api_key  = "none"              # vLLM / llama.cpp 不校验 key，但不能留空
price_in_per_mtok  = 0
price_out_per_mtok = 0         # 本地不花钱，记 0
```

**花费与熔断**

- 每笔调用写 `agent/state/ledger.db` 的 `ai_calls`（`tokens_in / tokens_out / cost_usd / ok / attempts / tag`）
- `python -m agent cost 10` 看最近十次运行各花了多少
- 按作品归集：`sqlite3 agent/state/ledger.db "SELECT tag,SUM(cost_usd) FROM ai_calls GROUP BY tag ORDER BY 2 DESC LIMIT 20"`
- 单次运行超过 `max_usd_per_run`（默认 $5）立刻抛 `BudgetExceeded` 停下 ——
  超支那一笔也会记账（熔断在「记完账之后」），不会出现「钱花了账上没有」

**没配 key 时的行为**

AI 环节会明确报「没有可用的 API key」并失败，不会静默跳过；
脚本环节完全不受影响，`apply` 也能把已有产物入进库。

## 幂等：key 由业务定义

```python
key = sha256(
    stage 名
  + 输入指纹            # 文件大小+mtime 或 SQL 计数（见各 stage 的 fingerprint）
  + 该 stage 模块源码 sha256 前 16 位
  + 模型名（仅 ai / hybrid）
)[:32]
```

- 改了 `stages/ai.py` 的提示词 → 源码 hash 变 → key 变 → 自动重跑，不用手动清缓存
- 换模型 → key 变
- 数据没动 → 直接 `skipped`，零成本
- `--force` 无视 key 强制重跑

## 成本

每次调用都写 `ai_calls`（`tokens_in / tokens_out / cost_usd / ok / attempts`），
`report` 与 `cost` 两个命令能按运行、按环节、按作品看钱。
`config.toml` 的 `max_usd_per_run` 是硬熔断：一次运行超了直接 `BudgetExceeded` 停下，
不会「跑一夜醒来发现烧了几十刀」。

## 生成与入库分离

AI 环节只往 `state/out/<stage>/` 写 JSON，`python -m agent apply bio` 才入库。好处：

1. 同一次生成可以反复 apply（改字段、补格式、只入一部分）
2. 出问题能分清是模型写错还是入库写错
3. 没配 key 时也能把历史产物入进去
4. 产物是纯数据，可以直接 diff

---

## 加一个环节

```python
# agent/stages/library.py 末尾
def _run_my_thing(ctx: Ctx) -> str:
    ctx.script("my_script.py", "--apply")      # 相对 采集工具\书库
    return "完成"

my_thing = Stage(
    name="my_thing",
    kind="script",
    run=_run_my_thing,
    needs=["build_db"],                        # 只写「必须先完成」的
    check=lambda ctx: (True, "ok"),            # 有可验的不变量就写，别留空
    description="一句话说明这条在干什么",
)
```
再把它加进 `agent/stages/__init__.py` 的 `ALL`（位置即默认顺序）。

跨目录调脚本：`ctx.script("clean1.py", cwd=ctx.canon_dir)`。

---

## 当前覆盖

| 段 | 环节 | kind |
|---|---|---|
| 采集 | collect, dedupe_source | script |
| 校勘 | clean, reflow, fix_glyph, fix_punct, restore_titles | script |
| 校勘 | audit_chars | hybrid |
| 文库 | build_db, chapters, dedupe_chapters, merge_works, classify_source, meta, characters, fts, check | script |
| AI | bio, summary | ai |
| AI | text_proof | hybrid |

已实测（真实执行，非 dry-run）：

| 命令 | 结果 |
|---|---|
| `run lib check` | 1.2s，`works 486（可见 464）/ chapters 3499 / FTS 3403 / characters 2759 缺 bio 0` |
| 同上二次运行 | 同指纹正确 `skipped`，零成本 |
| `run lib fts --force` | 47.1s，门禁 `FTS 3403 / 可见章节 3403` |
| `run lib collect` | 0.6s，`原文 748 个 txt / 已入库 589 / 待入库 313` |
| `run lib dedupe_source` | 125s，`扫描 748 个文件 → 152 组疑似重复` |
| `run ai` | 无 API key 时给出明确提示，不抛堆栈 |

> `collect` 的「待入库」是文件级清点：一部作品常有多个分卷文件，`path_source`
> 把它们用 `|` 拼成一行，所以「文件数 − 已登记路径数」不等于「未入库作品数」。
> 它只用于发现**新掉进来的文件**，不做入库判断。

## 待补

- `text_proof` 只产报告不回改正文 —— 改正文要人看一眼，这是有意的
- `summary` 会覆盖 `works.tags`：现有标签是脚本 + 人工整理的成果，正式跑之前
  应改成「只在 tags 为空时写」
- 章节目录里「卷名行落在该卷第一章之后」的少数章节没有卷名前缀，属已知保守处理
