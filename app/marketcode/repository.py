from __future__ import annotations

import json
from app.database import database


def init_marketcode_storage(target_database=None) -> None:
    target = target_database or database
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if target.config.backend == "sqlite" else "BIGSERIAL PRIMARY KEY"
    with target.connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS marketcode_publications (
                id {pk},
                plan_day INTEGER NOT NULL UNIQUE,
                topic TEXT NOT NULL,
                category TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                channel_statuses TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def published_days() -> set[int]:
    init_marketcode_storage()
    with database.connect() as conn:
        rows = conn.execute(
            "SELECT plan_day FROM marketcode_publications WHERE status IN ('published', 'partial')"
        ).fetchall()
    return {int(row[0]) for row in rows}


def save_publication(
    *,
    plan_day: int,
    topic: str,
    category: str,
    word_count: int,
    model: str,
    channel_statuses: dict[str, str],
) -> None:
    init_marketcode_storage()
    successful = sum(value.startswith("published") for value in channel_statuses.values())
    status = "published" if successful == len(channel_statuses) else "partial" if successful else "failed"
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO marketcode_publications
                (plan_day, topic, category, word_count, model, status, channel_statuses)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_day) DO UPDATE SET
                topic = excluded.topic,
                category = excluded.category,
                word_count = excluded.word_count,
                model = excluded.model,
                status = excluded.status,
                channel_statuses = excluded.channel_statuses,
                created_at = CURRENT_TIMESTAMP
            """,
            (
                plan_day,
                topic,
                category,
                word_count,
                model,
                status,
                json.dumps(channel_statuses, ensure_ascii=False),
            ),
        )
