# -*- coding: utf-8 -*-
"""书库阅读站后端。零依赖（stdlib），单机自用。

启动：
    python server.py            # 默认 127.0.0.1:8770
    python server.py 0.0.0.0 8770

接口：
    GET /api/stats
    GET /api/works?q=&source=&genre=&tag=&sort=&page=&size=
    GET /api/works/{id}
    GET /api/works/{id}/chapters
    GET /api/chapters/{id}
    GET /api/search?q=&page=
    GET /api/tags
    GET /api/characters
    GET /api/sources
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "data" / "library.db"
WEB = HERE / "web"
sys.stdout.reconfigure(encoding="utf-8")


def to_fts_query(q: str) -> str:
    """中文查询 → bigram 短语。"""
    segs = re.findall(r"[\u4e00-\u9fff]+", q)
    phrases = []
    for s in segs:
        if len(s) < 2:
            continue
        bg = [s[i : i + 2] for i in range(len(s) - 1)]
        phrases.append('"' + " ".join(bg) + '"')
    return " AND ".join(phrases)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def snippet(text: str, q: str, width: int = 48) -> str:
    """在原文里定位关键词，取上下文。"""
    for kw in re.findall(r"[\u4e00-\u9fff]{2,}", q):
        i = text.find(kw)
        if i >= 0:
            a, b = max(0, i - width), min(len(text), i + len(kw) + width)
            pre = "…" if a > 0 else ""
            post = "…" if b < len(text) else ""
            frag = text[a:b].replace("\n", " ")
            return pre + frag.replace(kw, f"<mark>{kw}</mark>") + post
    return text[: width * 2].replace("\n", " ")


class Handler(BaseHTTPRequestHandler):
    server_version = "LibraryShelf/1.0"

    def log_message(self, fmt, *args):  # 静音
        pass

    # ---------- 基础 ----------
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    # ---------- 路由 ----------
    def do_GET(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if path.startswith("/api/"):
                return self._api(path[5:], qs)
            return self._static(path)
        except Exception as e:  # 开发期便于排查
            self._json({"error": str(e), "type": type(e).__name__}, 500)

    def _static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        fp = (WEB / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(WEB.resolve())) or not fp.is_file():
            return self._send(404, b"404", "text/plain; charset=utf-8")
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".woff2": "font/woff2",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }.get(fp.suffix, "application/octet-stream")
        self._send(200, fp.read_bytes(), ctype)

    # ---------- API ----------
    def _api(self, ep: str, q: dict):
        con = db()
        try:
            if ep == "stats":
                return self._json(self._stats(con))
            if ep == "works":
                return self._json(self._works(con, q))
            if ep.startswith("works/"):
                parts = ep.split("/")
                wid = int(parts[1])
                if len(parts) == 2:
                    return self._json(self._work_detail(con, wid))
                if parts[2] == "chapters":
                    return self._json(self._chapters(con, wid))
            if ep.startswith("chapters/"):
                return self._json(self._chapter(con, int(ep.split("/")[1])))
            if ep == "search":
                return self._json(self._search(con, q))
            if ep == "tags":
                return self._json(self._tags(con))
            if ep == "characters":
                return self._json(self._characters(con))
            if ep == "sources":
                return self._json(self._sources(con))
            return self._json({"error": "not found"}, 404)
        finally:
            con.close()

    def _stats(self, con):
        r = con.execute(
            "SELECT COUNT(*), SUM(char_count), SUM(chapter_count) FROM works"
        ).fetchone()
        return {
            "works": r[0], "chars": r[1] or 0, "chapters": r[2] or 0,
            "sources": len(self._sources(con)),
            "tags": con.execute("SELECT COUNT(*) FROM tags").fetchone()[0],
            "characters": con.execute("SELECT COUNT(DISTINCT name) FROM characters").fetchone()[0],
        }

    def _sources(self, con):
        return [
            {"name": r[0] or "未归类", "works": r[1], "chars": r[2] or 0}
            for r in con.execute(
                "SELECT source_work, COUNT(*), SUM(char_count) FROM works "
                "GROUP BY source_work ORDER BY 3 DESC"
            )
        ]

    def _works(self, con, q):
        where, args = ["1=1"], []
        kw = q.get("q", "").strip()
        if kw:
            where.append("(w.title LIKE ? OR w.author LIKE ? OR w.summary LIKE ?)")
            args += [f"%{kw}%"] * 3
        if q.get("source"):
            if q["source"] == "_none":
                where.append("w.source_work IS NULL")
            else:
                where.append("w.source_work = ?")
                args.append(q["source"])
        if q.get("genre"):
            where.append("w.genre = ?")
            args.append(q["genre"])
        if q.get("tag"):
            where.append(
                "EXISTS (SELECT 1 FROM work_tags wt JOIN tags t ON t.id=wt.tag_id "
                "WHERE wt.work_id=w.id AND t.name=?)"
            )
            args.append(q["tag"])
        if q.get("min"):
            where.append("w.char_count >= ?")
            args.append(int(q["min"]))
        if q.get("max"):
            where.append("w.char_count <= ?")
            args.append(int(q["max"]))
        if q.get("status"):
            where.append("w.status = ?")
            args.append(q["status"])

        order = {
            "chars": "w.char_count DESC",
            "chars_asc": "w.char_count ASC",
            "title": "w.title",
            "recent": "w.id DESC",
        }.get(q.get("sort", ""), "w.char_count DESC")

        page = max(1, int(q.get("page", 1)))
        size = min(120, max(1, int(q.get("size", 40))))
        wsql = " AND ".join(where)
        total = con.execute(f"SELECT COUNT(*) FROM works w WHERE {wsql}", args).fetchone()[0]
        rows = con.execute(
            f"""SELECT w.id,w.title,w.author,w.genre,w.source_work,w.char_count,
                       w.chapter_count,w.reading_minutes,w.summary,w.tags,w.status
                FROM works w WHERE {wsql} ORDER BY {order} LIMIT ? OFFSET ?""",
            args + [size, (page - 1) * size],
        ).fetchall()
        return {
            "total": total, "page": page, "size": size,
            "items": [dict(r) for r in rows],
        }

    def _work_detail(self, con, wid):
        r = con.execute("SELECT * FROM works WHERE id=?", (wid,)).fetchone()
        if not r:
            return {"error": "not found"}
        d = dict(r)
        d["characters"] = [
            dict(x) for x in con.execute(
                "SELECT name,role,gender,mentions,title,intro,first_chapter,hue,"
                "looks,figure,personality,relations,sexual,sex_tags,story"
                " FROM characters WHERE work_id=? "
                "ORDER BY mentions DESC LIMIT 20", (wid,)
            )
        ]
        d["chapter_total"] = con.execute(
            "SELECT COUNT(*) FROM chapters WHERE work_id=?", (wid,)
        ).fetchone()[0]
        return d

    def _chapters(self, con, wid):
        return [
            dict(r) for r in con.execute(
                "SELECT id,idx,title,is_real_title,char_count FROM chapters "
                "WHERE work_id=? ORDER BY idx", (wid,)
            )
        ]

    def _chapter(self, con, cid):
        r = con.execute(
            """SELECT c.id,c.work_id,c.idx,c.title,c.content,c.char_count,w.title AS work_title,
                      (SELECT title FROM chapters WHERE work_id=c.work_id AND idx=c.idx-1) AS prev,
                      (SELECT id FROM chapters WHERE work_id=c.work_id AND idx=c.idx-1) AS prev_id,
                      (SELECT title FROM chapters WHERE work_id=c.work_id AND idx=c.idx+1) AS next,
                      (SELECT id FROM chapters WHERE work_id=c.work_id AND idx=c.idx+1) AS next_id,
                      (SELECT COUNT(*) FROM chapters WHERE work_id=c.work_id) AS total
               FROM chapters c JOIN works w ON w.id=c.work_id WHERE c.id=?""",
            (cid,),
        ).fetchone()
        return dict(r) if r else {"error": "not found"}

    def _search(self, con, q):
        kw = q.get("q", "").strip()
        if len(kw) < 2:
            return {"total": 0, "items": [], "q": kw}
        fq = to_fts_query(kw)
        if not fq:
            return {"total": 0, "items": [], "q": kw}
        page = max(1, int(q.get("page", 1)))
        size = min(60, max(1, int(q.get("size", 20))))
        total = con.execute(
            "SELECT COUNT(*) FROM chapters_fts WHERE chapters_fts MATCH ?", (fq,)
        ).fetchone()[0]
        rows = con.execute(
            """SELECT c.id, c.work_id, c.idx, c.title, c.content, w.title AS work_title,
                      w.source_work, bm25(chapters_fts) AS score
               FROM chapters_fts JOIN chapters c ON c.id = chapters_fts.rowid
               JOIN works w ON w.id = c.work_id
               WHERE chapters_fts MATCH ? ORDER BY score LIMIT ? OFFSET ?""",
            (fq, size, (page - 1) * size),
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d.pop("content", None)
            d["snippet"] = snippet(r["content"], kw)
            items.append(d)
        return {"total": total, "page": page, "q": kw, "items": items}

    def _tags(self, con):
        return [
            dict(r) for r in con.execute(
                "SELECT name, kind, count FROM tags ORDER BY count DESC"
            )
        ]

    def _characters(self, con):
        return [
            dict(r) for r in con.execute(
                "SELECT name, SUM(mentions) AS m, COUNT(*) AS works FROM characters "
                "GROUP BY name ORDER BY m DESC LIMIT 80"
            )
        ]


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8770
    if not DB_PATH.exists():
        print(f"数据库不存在：{DB_PATH}\n先跑 build_db.py")
        return
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"书库站点：http://{host}:{port}")
    print(f"数据库：  {DB_PATH}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
