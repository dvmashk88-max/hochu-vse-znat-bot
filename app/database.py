from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from app.config import DATABASE_URL


class UnsupportedDatabaseURL(ValueError):
    pass


@dataclass(frozen=True)
class DatabaseConfig:
    backend: str
    url: str
    sqlite_path: str | None = None


def parse_database_url(url: str) -> DatabaseConfig:
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        if not path:
            raise UnsupportedDatabaseURL("SQLite DATABASE_URL must contain a file path")
        return DatabaseConfig("sqlite", url, path)
    scheme = urlparse(url).scheme.lower().split("+", 1)[0]
    if scheme in {"postgres", "postgresql"}:
        normalized = re.sub(r"^postgresql\+[^:]+://", "postgresql://", url)
        normalized = re.sub(r"^postgres://", "postgresql://", normalized)
        return DatabaseConfig("postgresql", normalized)
    raise UnsupportedDatabaseURL(
        "Unsupported DATABASE_URL scheme. Use sqlite:///..., postgresql://..., or postgresql+..."
    )


class Connection:
    def __init__(self, raw: Any, backend: str):
        self.raw = raw
        self.backend = backend

    def _sql(self, statement: str) -> str:
        return statement if self.backend == "sqlite" else statement.replace("?", "%s")

    def execute(self, statement: str, params: tuple[Any, ...] = ()):
        return self.raw.execute(self._sql(statement), params)


class Database:
    def __init__(self, url: str = DATABASE_URL):
        self.config = parse_database_url(url)

    def _connect(self):
        if self.config.backend == "sqlite":
            path = self.config.sqlite_path or "bot.db"
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=30)
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL DATABASE_URL requires psycopg") from exc
        return psycopg.connect(self.config.url)

    @contextmanager
    def connect(self, *, immediate: bool = False) -> Iterator[Connection]:
        raw = self._connect()
        conn = Connection(raw, self.config.backend)
        try:
            if immediate and self.config.backend == "sqlite":
                raw.execute("BEGIN IMMEDIATE")
            yield conn
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()


database = Database()
