from collections.abc import Iterable

from app.database import database


def _ensure_legacy_columns(conn) -> None:
    definitions = {"category": "TEXT", "angle": "TEXT", "keywords": "TEXT"}
    if database.config.backend == "sqlite":
        existing = {row[1] for row in conn.execute("PRAGMA table_info(published_topics)").fetchall()}
        for column, definition in definitions.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE published_topics ADD COLUMN {column} {definition}")
    else:
        for column, definition in definitions.items():
            conn.execute(f"ALTER TABLE published_topics ADD COLUMN IF NOT EXISTS {column} {definition}")


def init_db() -> None:
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if database.config.backend == "sqlite" else "BIGSERIAL PRIMARY KEY"
    timestamp = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    with database.connect() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS published_topics (
            id {pk}, topic TEXT NOT NULL UNIQUE, published_at {timestamp},
            category TEXT, angle TEXT, keywords TEXT)""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS dzen_publications (
            id {pk}, topic TEXT NOT NULL, status TEXT NOT NULL, error TEXT, created_at {timestamp})""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS max_publications (
            id {pk}, topic TEXT NOT NULL, status TEXT NOT NULL, message_id TEXT,
            error TEXT, created_at {timestamp})""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS vk_publications (
            id {pk}, topic TEXT NOT NULL, status TEXT NOT NULL, post_id TEXT,
            error TEXT, created_at {timestamp})""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS image_publications (
            id {pk}, topic TEXT NOT NULL, query TEXT NOT NULL, source TEXT NOT NULL,
            url TEXT NOT NULL, created_at {timestamp})""")
        _ensure_legacy_columns(conn)


def _serialize_keywords(keywords: Iterable[str] | None) -> str | None:
    if not keywords:
        return None
    return ", ".join(str(item).strip() for item in keywords if str(item).strip())


def save_published_topic(topic: str, category: str | None = None, angle: str | None = None,
                         keywords: Iterable[str] | None = None) -> None:
    with database.connect() as conn:
        if database.config.backend == "sqlite":
            sql = "INSERT OR IGNORE INTO published_topics (topic, category, angle, keywords) VALUES (?, ?, ?, ?)"
        else:
            sql = "INSERT INTO published_topics (topic, category, angle, keywords) VALUES (?, ?, ?, ?) ON CONFLICT(topic) DO NOTHING"
        conn.execute(sql, (topic, category, angle, _serialize_keywords(keywords)))


def get_published_topics() -> list[str]:
    with database.connect() as conn:
        rows = conn.execute("SELECT topic FROM published_topics").fetchall()
    return [row[0] for row in rows]


def get_recent_published_topics(limit: int = 50, days: int | None = None) -> list[str]:
    with database.connect() as conn:
        if days and database.config.backend == "sqlite":
            rows = conn.execute("SELECT topic FROM published_topics WHERE published_at >= datetime('now', ?) ORDER BY published_at DESC, id DESC LIMIT ?", (f"-{days} days", limit)).fetchall()
        elif days:
            rows = conn.execute("SELECT topic FROM published_topics WHERE published_at >= CURRENT_TIMESTAMP - (? * INTERVAL '1 day') ORDER BY published_at DESC, id DESC LIMIT ?", (days, limit)).fetchall()
        else:
            rows = conn.execute("SELECT topic FROM published_topics ORDER BY published_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [row[0] for row in rows]


def _save_status(table: str, columns: tuple[str, ...], values: tuple) -> None:
    placeholders = ", ".join("?" for _ in columns)
    with database.connect() as conn:
        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", values)


def save_dzen_publication_status(topic: str, status: str, error: str | None = None) -> None:
    _save_status("dzen_publications", ("topic", "status", "error"), (topic, status, error))


def save_max_publication_status(topic: str, status: str, message_id: str | None = None,
                                error: str | None = None) -> None:
    _save_status("max_publications", ("topic", "status", "message_id", "error"), (topic, status, message_id, error))


def save_vk_publication_status(topic: str, status: str, post_id: str | None = None,
                               error: str | None = None) -> None:
    _save_status("vk_publications", ("topic", "status", "post_id", "error"), (topic, status, post_id, error))


def save_published_image(topic: str, query: str, source: str, url: str) -> None:
    _save_status("image_publications", ("topic", "query", "source", "url"), (topic, query, source, url))


def get_recent_image_urls(limit: int = 50) -> list[str]:
    with database.connect() as conn:
        rows = conn.execute("SELECT url FROM image_publications ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [row[0] for row in rows]
