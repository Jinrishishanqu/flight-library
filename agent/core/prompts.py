# -*- coding: utf-8 -*-
"""提示词仓库：所有 system / user 模板放在 agent/prompts/*.txt，代码里不再写死。

为什么单独抽出来：
  1. 提示词是「内容」，不是「逻辑」—— 改一句话不该动 Python 文件、更不该担心
     缩进或转义（角色素材里常有多段正文，嵌在字符串里很难读）
  2. 版本自动化。`version()` 拿整个目录的哈希当前 12 位，它进幂等 key，
     于是「改了任何一个 .txt → key 变 → 下次运行自动重跑」，
     不再需要手动 bump PROMPT_VER（忘了 bump 就会「改了提示词却被幂等跳过」）
  3. 每个提示词都是独立文件，能直接 diff、能被别的工具读

文件命名约定：
  <环节>.<用途>.txt     例：bio.system.txt / bio.user.txt / bio.block.txt
  占位符用 Python 的 {} 语法，由 render() 填充；正文里的半角花括号需写成 {{ }}
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class Prompts:
    """读取与渲染 agent/prompts 下的模板。"""

    def __init__(self, root: Path | None = None):
        # 默认就是 agent/prompts（本文件在 agent/core/ 下，上两级是 agent/）
        self.dir = Path(root) if root else Path(__file__).resolve().parent.parent / "prompts"
        self._ver: str | None = None

    # ---------- 读 ----------
    def text(self, name: str) -> str:
        """取模板原文（不去首尾空行之外的任何空白）。name 不带 .txt。"""
        p = self.dir / f"{name}.txt"
        if not p.exists():
            raise FileNotFoundError(f"缺提示词文件：{p}")
        return p.read_text(encoding="utf-8").strip()

    def render(self, name: str, **kw) -> str:
        """填占位符。用 format 而不是 replace，缺参数会立刻 KeyError 暴露出来。"""
        return self.text(name).format(**kw)

    # ---------- 版本 ----------
    def version(self) -> str:
        """整个提示词目录的内容哈希（前 12 位）。

        只算 .txt：README 改了不该让全部 AI 环节重跑。
        结果缓存，一次进程内只算一次。
        """
        if self._ver is None:
            h = hashlib.sha256()
            for p in sorted(self.dir.glob("*.txt")):
                h.update(p.name.encode("utf-8"))
                h.update(p.read_bytes())
            self._ver = h.hexdigest()[:12]
        return self._ver


# 进程级单例：stages/ai.py 直接 import 用
P = Prompts()
