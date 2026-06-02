import sqlite3
import re
from app.config import DATABASE_URL


def _db_path() -> str:
    match = re.match(r"sqlite:///(.+)", DATABASE_URL)
    return match.group(1) if match else "bot.db"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_db_path())


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS published_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL UNIQUE,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_published_topic(topic: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO published_topics (topic) VALUES (?)", (topic,))
        conn.commit()


def get_published_topics() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT topic FROM published_topics").fetchall()
    return [row[0] for row in rows]
