# 提示词

所有会发给模型的文本都在这里，`stages/ai.py` 只负责取用与传参，不再内嵌字符串。

## 文件

| 文件 | 用途 | 占位符 |
|---|---|---|
| `bio.system.txt` | 角色小传的 system | 无 |
| `bio.user.txt` | 角色小传的 user | `{title}` `{blocks}` |
| `bio.block.txt` | 单个角色的素材块（拼进 `{blocks}`） | `{name}` `{role}` `{gender}` `{mentions}` `{paras}` |
| `summary.system.txt` | 书籍简介的 system | 无 |
| `summary.user.txt` | 书籍简介的 user | `{title}` `{source_work}` `{chars}` `{head}` |
| `proof.system.txt` | 文字复核的 system | 无 |
| `proof.user.txt` | 文字复核的 user | `{work_title}` `{title}` `{body}` |

## 改提示词

直接编辑对应的 `.txt`，不用动 Python，也不用重启任何东西。

**版本自动生效**：`core/prompts.py` 的 `version()` 把目录内全部 `.txt` 的内容哈希取前 12 位，
它进 `ai_calls.prompt_ver`（记账）与各 AI 环节的输入指纹（幂等 key）。
所以改完提示词后下一次 `run` 会自动重跑，不会出现「改了却没生效」。
（以前的 `PROMPT_VER = "v1"` 常量已废弃 —— 忘了手动 bump 正是最容易踩的坑。）

## 占位符

用 Python 的 `{}` 语法，由 `Prompts.render(name, **kw)` 填充。
缺参数会立刻抛 `KeyError`，不会静默发出残缺的提示词。
模板里若要字面量花括号，写成 `{{ }}`（目前所有模板都不需要）。

## 加一个提示词

1. 在这里建 `<环节>.<用途>.txt`
2. 在 `stages/ai.py` 里 `from ..core.prompts import P`，用 `P.text("x.system")` 或 `P.render("x.user", **kw)`
3. 不用注册、不用改版本号 —— 目录哈希会自动变
