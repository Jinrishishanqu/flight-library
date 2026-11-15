-- 书库数据库 schema
-- 目标：作品级元数据 + 章节全文 + 中文检索 + 未来补章匹配
-- SQLite 3.53.1，FTS5 bigram 方案（trigram 查不了 2 字词，实测 薰儿 MATCH 返回 0）

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- ========== 作品 ==========
CREATE TABLE IF NOT EXISTS works (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE,          -- 稳定标识，由文件名派生
    title         TEXT NOT NULL,        -- 书名（去除《》）
    subtitle      TEXT,                 -- 副标题 / 括号内补充
    author        TEXT,                 -- 作者；未知填 NULL
    author_note   TEXT,                 -- 「佚名」「作者自述」等说明
    genre         TEXT,                 -- 同人 / 原创 / 短篇集 / 未知
    source_work   TEXT,                 -- 原作：斗破苍穹 / 斗罗大陆 / ...
    series        TEXT,                 -- 系列名（同名多篇归组）
    pairing       TEXT,                 -- CP 关系
    tags          TEXT,                 -- JSON 数组，题材与玩法标签
    keywords      TEXT,                 -- JSON 数组，高频词
    theme         TEXT,                 -- 主题一句话
    summary       TEXT,                 -- 摘要（自动生成，可人工覆盖）
    description   TEXT,                 -- 简介/卷首作者语
    notes         TEXT,                 -- 人工备注（异常、残缺、分卷关系）
    rating        TEXT,                 -- 分级：成人向
    status        TEXT,                 -- 完 / 未完 / 合集
    char_count    INTEGER DEFAULT 0,
    chapter_count INTEGER DEFAULT 0,
    reading_minutes INTEGER DEFAULT 0,
    path_canon    TEXT,                 -- 校勘版路径（相对项目根）
    path_proof    TEXT,                 -- 校对后路径
    path_source   TEXT,                 -- 原文路径
    sha256        TEXT,
    lang          TEXT DEFAULT 'zh',
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now')),
    imported_from TEXT
);

CREATE INDEX IF NOT EXISTS idx_works_source ON works(source_work);
CREATE INDEX IF NOT EXISTS idx_works_genre  ON works(genre);
CREATE INDEX IF NOT EXISTS idx_works_series ON works(series);
CREATE INDEX IF NOT EXISTS idx_works_chars  ON works(char_count DESC);

-- ========== 章节 / 阅读单元 ==========
CREATE TABLE IF NOT EXISTS chapters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id     INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,       -- 从 1 开始
    title       TEXT,                   -- 真实章标题，或「第N节」
    is_real_title INTEGER DEFAULT 0,    -- 1=原文有章标题
    content     TEXT NOT NULL,
    body_bi     TEXT NOT NULL,          -- bigram 分词文本，供 FTS 使用
    char_count  INTEGER DEFAULT 0,
    UNIQUE(work_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_ch_work ON chapters(work_id, idx);

-- ========== 全文检索（bigram + unicode61）==========
CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
    title,
    body_bi,
    work_title,
    content='',
    tokenize='unicode61 remove_diacritics 0'
);

-- ========== 角色 ==========
CREATE TABLE IF NOT EXISTS characters (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id   INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    aliases   TEXT,                     -- JSON 数组
    role      TEXT,                     -- 主角 / 配角 / 提及
    gender    TEXT,
    mentions  INTEGER DEFAULT 0,
    title     TEXT,                     -- 身份/称号（女王、宗主、仙子…）
    intro     TEXT,                     -- 一句话介绍（取自正文原句）
    first_chapter INTEGER,              -- 首次出场的节号
    hue       INTEGER DEFAULT 0,        -- 角色卡底色序号 0-5
    looks     TEXT,                     -- 外貌描写（正文原句）
    figure    TEXT,                     -- 身体/身段描写
    personality TEXT,                   -- 性格
    relations TEXT,                     -- 关系（妻子/师父/师姐…，取自正文原句）
    sexual    TEXT,                     -- 性方面描写，多条用换行分隔
    sex_tags  TEXT,                     -- JSON 数组：性相关关键词标签
    UNIQUE(work_id, name)
);

CREATE INDEX IF NOT EXISTS idx_char_name ON characters(name);

-- ========== 标签规范化 ==========
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL,
    kind  TEXT,                         -- source(原作) / trope(玩法) / mood(情感) / char(角色) / meta
    count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_tags (
    work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    weight  REAL DEFAULT 1.0,
    PRIMARY KEY (work_id, tag_id)
);

-- ========== 指纹：未来新章节归入判断 ==========
CREATE TABLE IF NOT EXISTS fingerprints (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,              -- title / opening / ngram / filename
    value   TEXT NOT NULL,
    extra   TEXT,
    UNIQUE(kind, value)
);

CREATE INDEX IF NOT EXISTS idx_fp_value ON fingerprints(value);
CREATE INDEX IF NOT EXISTS idx_fp_work  ON fingerprints(work_id);

-- ========== 导入台账 ==========
CREATE TABLE IF NOT EXISTS import_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT DEFAULT (datetime('now')),
    action     TEXT,
    path       TEXT,
    work_id    INTEGER,
    detail     TEXT
);

-- ========== 视图：作品卡片 ==========
CREATE VIEW IF NOT EXISTS v_works AS
SELECT w.id, w.slug, w.title, w.author, w.genre, w.source_work, w.series,
       w.char_count, w.chapter_count, w.reading_minutes, w.summary,
       w.tags, w.keywords, w.status, w.path_canon,
       (SELECT COUNT(*) FROM characters c WHERE c.work_id = w.id) AS char_roles
FROM works w;
