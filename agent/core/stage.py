# -*- coding: utf-8 -*-
"""Stage：一个处理环节的声明与执行契约。

三种 kind（判定依据是「换一批输入重跑，结果是否确定」）：
  script  规则能可靠覆盖 → 调现有 CLI 脚本，产出直接落库/落盘
          判据：结果确定、可用不变量回归（字数不变 / 文件数不变 / 无禁用字符）
  ai      必须读懂语义才能判 → 走 API，产物先落 state/out/ 再 apply
          判据：规则写不出、且错了人一眼能看出来（简介、角色小传）
  hybrid  脚本先跑筛出可疑样本，AI 只处理这些样本
          判据：规则能定位「哪里可能错」，但不能裁定「到底错没错」

每个 Stage 由四个可选部分构成：
  run(ctx)        干活，返回一段人类可读的 detail（会写进台账并打印）
  fingerprint(ctx) 输入指纹，参与幂等 key —— 输入没变就不重跑
  check(ctx)      质量门禁，返回 (ok, message)；不 ok 时 runner 把整步标 failed 并中断
  needs           依赖的环节名（仅用于文档与 --dry 的顺序展示；数据依赖靠库）

为什么幂等要自己算 key：
  框架（Prefect / Airflow）的缓存只认它自己定义的输入对象；
  而这里同样的「输入」是「某部作品的正文 + 某版提示词 + 某个模型」，
  只有业务自己知道该把它们拼在一起。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Ctx:
    """跑一个 stage 时能用到的一切。由 Runner 在每步开始时构造。"""

    cfg: object                       # core.config.Config
    ledger: object                    # core.ledger.Ledger
    run_id: int                       # 本次运行的 id（dry 时为 0）
    stage: str                        # 当前环节名
    force: bool = False               # --force：忽略幂等，强制重跑
    log: Callable[[str], None] = print

    @property
    def root(self) -> Path:
        return self.cfg.paths.root

    @property
    def tool_dir(self) -> Path:
        """阅读站与文库脚本所在目录（采集工具\\书库）。"""
        return self.root / "采集工具" / "书库"

    @property
    def canon_dir(self) -> Path:
        """校勘脚本所在目录（采集工具\\校勘）。"""
        return self.root / "采集工具" / "校勘"

    @property
    def py_dir(self) -> Path:
        """采集管线脚本所在目录（采集工具\\py）。"""
        return self.root / "采集工具" / "py"

    def py(self) -> str:
        """当前解释器（项目 .venv 里的 python），保证子脚本用同一套依赖。"""
        return str(Path(sys.executable))

    def script(self, name: str, *args: str, cwd: Path | None = None,
               timeout: int = 7200) -> tuple[int, str]:
        """跑现有 Python 脚本，返回 (returncode, stdout+stderr 尾部)。

        这是「脚本环节」唯一的执行方式 —— 不重写脚本，只负责按顺序调、
        接住输出、把非零退出码变成异常。

        name 相对 cwd 解析（默认 采集工具\\书库），所以跨目录调用写：
            ctx.script("clean1.py", cwd=ctx.canon_dir)
            ctx.script("dedupe.py", "--dir", str(...), cwd=ctx.py_dir)
        timeout 默认 2 小时：全库查重、hanlp 建卡这类长任务都在这个量级。

        坑：dedupe.py 之类脚本用相对 $_PSScriptRoot 找资源，--dir 必须传绝对路径。
        """
        base = Path(cwd) if cwd else self.tool_dir
        p = Path(name)
        cmd = [self.py(), str(p if p.is_absolute() else base / p), *args]
        self.log(f"    $ {' '.join(cmd[1:])}")
        r = subprocess.run(cmd, cwd=str(base), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            # 只带尾部 2000 字符：脚本报错信息通常就在最后几行，全文会淹没日志
            raise RuntimeError(f"{name} 退出码 {r.returncode}\n{out[-2000:]}")
        return r.returncode, out


@dataclass
class Stage:
    """环节声明。stages/*.py 里通过实例化它来注册环节。"""

    name: str
    kind: str                                   # script / ai / hybrid
    run: Callable[[Ctx], str]
    needs: list[str] = field(default_factory=list)
    fingerprint: Callable[[Ctx], str] | None = None
    check: Callable[[Ctx], tuple[bool, str]] | None = None
    description: str = ""

    def dedupe_key(self, ctx: Ctx) -> str:
        """幂等 key = 环节名 + 输入指纹 + 运行代码版本 + 模型名。

        四段的用意：
          环节名    —— 不同环节永不互相命中
          输入指纹  —— 语料/数据库变了就失效（由各 Stage 的 fingerprint() 给）
          代码版本  —— 改了 run()/check() 的实现，旧的成功记录不该再算数
          模型名    —— 换模型等于换输出，必须重跑
        提示词变化不在里面：改 prompt 时手动 bump stages/ai.py 的 PROMPT_VER，
        它会进入输入指纹（各 AI Stage 的 fingerprint 会带上）。⚠ 改提示词别忘了加版本号。
        """
        parts = [self.name, self.kind]
        if self.fingerprint:
            parts.append(self.fingerprint(ctx))
        src = Path(sys.modules[self.run.__module__].__file__)
        if src.exists():
            parts.append(hashlib.sha256(src.read_bytes()).hexdigest()[:16])
        if self.kind in ("ai", "hybrid"):
            parts.append(getattr(ctx.cfg.llm, "model", ""))
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def file_digest(path: Path, limit_mb: int = 8) -> str:
    """文件指纹：大小 + 头尾各 8MB 的哈希。

    为什么不整份哈希：library.db 有 200MB+，每次算全程要好几秒，
    而头尾各 8MB 已经足以识别「这个库被动过」。
    返回 "missing" 表示文件不存在（首次运行时指纹就该是它）。
    """
    if not path.exists():
        return "missing"
    size = path.stat().st_size
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(limit_mb * 1024 * 1024))
        if size > limit_mb * 2 * 1024 * 1024:
            f.seek(-limit_mb * 1024 * 1024, 2)
            h.update(f.read())
    return f"{size}:{h.hexdigest()[:24]}"


def tree_digest(paths: list[Path], glob: str = "*.txt", limit: int = 400) -> str:
    """目录树指纹：文件名 + 大小 + mtime，不读内容。

    只取前 limit 个文件（默认 400）—— 语料有 700+ 文件，
    而「有没有新增/改动」看前 400 个的元数据已经足够，且是毫秒级。
    """
    items = []
    for p in paths:
        if not p.exists():
            items.append(f"{p.name}:missing")
            continue
        files = sorted(p.rglob(glob))[:limit]
        for f in files:
            st = f.stat()
            items.append(f"{f.relative_to(p.parent)}:{st.st_size}:{int(st.st_mtime)}")
    return hashlib.sha256("|".join(items).encode("utf-8")).hexdigest()[:32]
