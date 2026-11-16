# -*- coding: utf-8 -*-
"""Stage：一个处理环节的声明与执行契约。

三种 kind：
  script  规则能可靠覆盖 → 调现有 CLI，产出直接落库/落盘
  ai      必须读上下文才能判 → 走 API，产物先落 artifacts 再 apply
  hybrid  脚本先跑，AI 只处理脚本判不了的疑难样本

每个 Stage 自己负责：
  - fingerprint()  给出输入指纹（参与幂等 key）
  - run(ctx)       真正干活，返回一段人类可读的 detail
  - check(ctx)     质量门禁，返回 (ok, message)；不 ok 时 runner 把整步标 failed
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
    """跑一个 stage 时能用到的一切。"""
    cfg: object                       # core.config.Config
    ledger: object                    # core.ledger.Ledger
    run_id: int
    stage: str
    force: bool = False
    log: Callable[[str], None] = print

    @property
    def root(self) -> Path:
        return self.cfg.paths.root

    @property
    def tool_dir(self) -> Path:
        return self.root / "采集工具" / "书库"

    @property
    def canon_dir(self) -> Path:
        return self.root / "采集工具" / "校勘"

    @property
    def py_dir(self) -> Path:
        return self.root / "采集工具" / "py"

    def py(self) -> str:
        return str(Path(sys.executable))

    def script(self, name: str, *args: str, cwd: Path | None = None,
               timeout: int = 7200) -> tuple[int, str]:
        """跑现有 Python 脚本，返回 (returncode, 输出尾部)。

        name 相对 cwd 解析（默认 采集工具\\书库），所以跨目录调用写
        `ctx.script("clean1.py", cwd=ctx.canon_dir)` 即可。
        """
        base = Path(cwd) if cwd else self.tool_dir
        p = Path(name)
        cmd = [self.py(), str(p if p.is_absolute() else base / p), *args]
        self.log(f"    $ {' '.join(cmd[1:])}")
        r = subprocess.run(cmd, cwd=str(base), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0:
            raise RuntimeError(f"{name} 退出码 {r.returncode}\n{out[-2000:]}")
        return r.returncode, out


@dataclass
class Stage:
    name: str
    kind: str                                   # script / ai / hybrid
    run: Callable[[Ctx], str]
    needs: list[str] = field(default_factory=list)
    fingerprint: Callable[[Ctx], str] | None = None
    check: Callable[[Ctx], tuple[bool, str]] | None = None
    description: str = ""

    def dedupe_key(self, ctx: Ctx) -> str:
        """幂等 key = stage 名 + 输入指纹 + 本模块源码版本 + 模型名。"""
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
    """大文件只取头尾，避免每次全量哈希几十 MB。"""
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
    """目录树指纹：文件名 + 大小 + mtime（不读内容，够用且快）。"""
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
