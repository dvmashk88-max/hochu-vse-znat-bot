from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.database import Database
from app.marketcode.repository import init_marketcode_storage


@dataclass(frozen=True)
class MigrationResult:
    source_rows: int
    target_existing: int
    would_insert: int
    inserted: int
    skipped: int
    dry_run: bool


def read_marketcode_rows(source_path: str | Path) -> list[tuple]:
    path = Path(source_path).resolve()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='marketcode_publications'"
        ).fetchone()
        if not exists:
            return []
        rows = connection.execute(
            """SELECT plan_day, topic, category, word_count, model, status,
            channel_statuses, created_at FROM marketcode_publications ORDER BY plan_day"""
        ).fetchall()
    finally:
        connection.close()
    for row in rows:
        statuses = json.loads(row[6])
        if not isinstance(statuses, dict):
            raise ValueError(f"MarketCode plan day {row[0]} has invalid channel_statuses JSON")
    return rows


def migrate_marketcode(source_path: str | Path, target: Database | None, *,
                       dry_run: bool, require_postgresql: bool = True) -> MigrationResult:
    rows = read_marketcode_rows(source_path)
    if target is None:
        if not dry_run:
            raise ValueError("Actual migration requires a target DATABASE_URL")
        return MigrationResult(len(rows), 0, len(rows), 0, 0, True)
    if require_postgresql and target.config.backend != "postgresql":
        raise ValueError("SQLite → PostgreSQL migration target must use a PostgreSQL URL")
    days = [int(row[0]) for row in rows]
    try:
        with target.connect() as conn:
            existing = {
                int(row[0]) for row in conn.execute(
                    "SELECT plan_day FROM marketcode_publications"
                ).fetchall()
            }
    except Exception as exc:
        message = str(exc).lower()
        if "does not exist" not in message and "no such table" not in message:
            raise
        if not dry_run:
            existing = set()
        else:
            return MigrationResult(len(rows), 0, len(rows), 0, 0, True)
    would_insert = sum(day not in existing for day in days)
    if dry_run:
        return MigrationResult(len(rows), len(existing), would_insert, 0, len(rows) - would_insert, True)
    init_marketcode_storage(target)
    inserted = 0
    with target.connect(immediate=True) as conn:
        for row in rows:
            target_row = row
            if target.config.backend == "postgresql" and isinstance(row[7], str):
                target_row = (*row[:7], datetime.fromisoformat(row[7]))
            cursor = conn.execute(
                """INSERT INTO marketcode_publications
                (plan_day, topic, category, word_count, model, status, channel_statuses, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_day) DO NOTHING""",
                target_row,
            )
            inserted += cursor.rowcount
    return MigrationResult(len(rows), len(existing), would_insert, inserted, len(rows) - inserted, False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely import MarketCode progress from legacy SQLite into PostgreSQL."
    )
    parser.add_argument("--source", default="bot.db", help="Path to source SQLite bot.db")
    parser.add_argument("--target-url", default=os.getenv("DATABASE_URL", ""),
                        help="PostgreSQL DATABASE_URL; never printed")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read/count only; no target rows written")
    mode.add_argument("--execute", action="store_true", help="Explicitly perform idempotent inserts")
    return parser


def main() -> None:
    args = _parser().parse_args()
    target = Database(args.target_url) if args.target_url else None
    result = migrate_marketcode(args.source, target, dry_run=args.dry_run)
    mode = "DRY RUN" if result.dry_run else "EXECUTED"
    print(f"Mode: {mode}")
    print(f"Source MarketCode rows: {result.source_rows}")
    print(f"Target rows before migration: {result.target_existing}")
    print(f"Would insert: {result.would_insert}")
    print(f"Inserted: {result.inserted}")
    print(f"Skipped/preserved: {result.skipped}")
    print("Source SQLite was opened read-only and was not changed.")
    print("Legacy random-channel history and course state were not migrated.")


if __name__ == "__main__":
    main()
