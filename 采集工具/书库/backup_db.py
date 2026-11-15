# -*- coding: utf-8 -*-
"""给 library.db 做一份带时间戳的 VACUUM INTO 备份。"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "bak"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = DB.parent / f"library_{tag}_{stamp}.db"
    con = sqlite3.connect(DB)
    con.execute("VACUUM INTO ?", (str(dest),))
    con.close()
    print(f"备份 -> {dest}  {dest.stat().st_size / 1048576:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
