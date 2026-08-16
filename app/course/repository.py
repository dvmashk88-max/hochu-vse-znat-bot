from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.course.models import CourseDay, GeneratedLesson, PartType, RetrievedSource
from app.database import database


@dataclass(frozen=True)
class StoredPart:
    season_id: str
    course_id: str
    lesson_id: str
    lesson_date: date
    part_type: PartType
    title: str
    text: str
    image_reference: str
    image_hash: str
    image_bytes: bytes


class CoverRebuildError(RuntimeError):
    pass


def _date_value(value: date):
    return value.isoformat() if database.config.backend == "sqlite" else value


def _timestamp_value(value: str | datetime):
    if database.config.backend == "postgresql" and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def init_course_storage() -> None:
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if database.config.backend == "sqlite" else "BIGSERIAL PRIMARY KEY"
    blob = "BLOB" if database.config.backend == "sqlite" else "BYTEA"
    date_type = "TEXT" if database.config.backend == "sqlite" else "DATE"
    timestamp = "TIMESTAMP" if database.config.backend == "sqlite" else "TIMESTAMPTZ"
    with database.connect() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS course_lessons (
            id {pk}, season_id TEXT NOT NULL, course_id TEXT NOT NULL, lesson_id TEXT NOT NULL,
            lesson_date {date_type} NOT NULL, topic TEXT NOT NULL, learning_goal TEXT NOT NULL,
            generation_status TEXT NOT NULL DEFAULT 'pending', model TEXT, error TEXT,
            generated_at {timestamp}, updated_at {timestamp} DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (season_id, course_id, lesson_id))""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS lesson_parts (
            id {pk}, season_id TEXT NOT NULL, course_id TEXT NOT NULL, lesson_id TEXT NOT NULL,
            lesson_date {date_type} NOT NULL, part_type TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL,
            image_reference TEXT NOT NULL, image_hash TEXT NOT NULL, image_data {blob} NOT NULL,
            generation_status TEXT NOT NULL, generated_at {timestamp} DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (season_id, course_id, lesson_id, part_type))""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS platform_publications (
            id {pk}, publication_key TEXT NOT NULL UNIQUE, season_id TEXT NOT NULL,
            course_id TEXT NOT NULL, lesson_id TEXT NOT NULL, part_type TEXT NOT NULL,
            platform TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', external_id TEXT,
            error TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, scheduled_at {timestamp} NOT NULL,
            published_at {timestamp}, updated_at {timestamp} DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (season_id, course_id, lesson_id, part_type, platform))""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS source_snapshots (
            id {pk}, season_id TEXT NOT NULL, course_id TEXT NOT NULL, lesson_id TEXT NOT NULL,
            source_url TEXT NOT NULL, source_title TEXT NOT NULL, content_hash TEXT NOT NULL,
            content_text TEXT NOT NULL, used_for_generation INTEGER NOT NULL DEFAULT 1,
            fetched_at {timestamp} DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (season_id, course_id, lesson_id, source_url))""")
        conn.execute(f"""CREATE TABLE IF NOT EXISTS admin_alerts (
            id {pk}, alert_key TEXT NOT NULL UNIQUE, alert_type TEXT NOT NULL,
            status TEXT NOT NULL, telegram_message_id TEXT, error TEXT,
            created_at {timestamp} DEFAULT CURRENT_TIMESTAMP, sent_at {timestamp})""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_course_lessons_date_status
            ON course_lessons (lesson_date, generation_status)""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_lesson_parts_recent
            ON lesson_parts (season_id, course_id, lesson_date, part_type)""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_platform_publications_status
            ON platform_publications (lesson_id, part_type, status)""")


def _insert_lesson_if_needed(lesson: CourseDay, conn) -> None:
    conn.execute(
        """INSERT INTO course_lessons
        (season_id, course_id, lesson_id, lesson_date, topic, learning_goal, generation_status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending') ON CONFLICT(season_id, course_id, lesson_id) DO NOTHING""",
        (lesson.season_id, lesson.course_id, lesson.lesson_id, _date_value(lesson.date), lesson.topic, lesson.learning_goal),
    )


def claim_generation(lesson: CourseDay) -> bool:
    init_course_storage()
    with database.connect(immediate=True) as conn:
        _insert_lesson_if_needed(lesson, conn)
        cursor = conn.execute(
            """UPDATE course_lessons SET generation_status='generating', error=NULL,
            updated_at=CURRENT_TIMESTAMP WHERE season_id=? AND course_id=? AND lesson_id=?
            AND generation_status IN ('pending', 'failed')""",
            (lesson.season_id, lesson.course_id, lesson.lesson_id),
        )
        return cursor.rowcount == 1


def generation_status(lesson: CourseDay) -> str | None:
    init_course_storage()
    with database.connect() as conn:
        row = conn.execute(
            "SELECT generation_status FROM course_lessons WHERE season_id=? AND course_id=? AND lesson_id=?",
            (lesson.season_id, lesson.course_id, lesson.lesson_id),
        ).fetchone()
    return row[0] if row else None


def save_generation_failure(lesson: CourseDay, error: str, status: str = "failed") -> None:
    init_course_storage()
    with database.connect() as conn:
        _insert_lesson_if_needed(lesson, conn)
        conn.execute(
            """UPDATE course_lessons SET generation_status=?, error=?, updated_at=CURRENT_TIMESTAMP
            WHERE season_id=? AND course_id=? AND lesson_id=?""",
            (status, error[:2000], lesson.season_id, lesson.course_id, lesson.lesson_id),
        )


def save_generated_lesson(generated: GeneratedLesson, sources: tuple[RetrievedSource, ...],
                          image_artifacts: dict[PartType, tuple[str, str, bytes]]) -> None:
    lesson = generated.lesson
    init_course_storage()
    with database.connect(immediate=True) as conn:
        _insert_lesson_if_needed(lesson, conn)
        for source in sources:
            conn.execute(
                """INSERT INTO source_snapshots
                (season_id, course_id, lesson_id, source_url, source_title, content_hash, content_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(season_id, course_id, lesson_id, source_url) DO UPDATE SET
                source_title=excluded.source_title, content_hash=excluded.content_hash,
                content_text=excluded.content_text, fetched_at=CURRENT_TIMESTAMP""",
                (lesson.season_id, lesson.course_id, lesson.lesson_id, source.source.url,
                 source.source.title, source.content_hash, source.text),
            )
        for part in generated.parts:
            image_reference, image_hash, image_bytes = image_artifacts[part.part_type]
            conn.execute(
                """INSERT INTO lesson_parts
                (season_id, course_id, lesson_id, lesson_date, part_type, title, text,
                 image_reference, image_hash, image_data, generation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated')
                ON CONFLICT(season_id, course_id, lesson_id, part_type) DO UPDATE SET
                title=excluded.title, text=excluded.text, image_reference=excluded.image_reference,
                image_hash=excluded.image_hash, image_data=excluded.image_data,
                generation_status='generated', generated_at=CURRENT_TIMESTAMP""",
                (lesson.season_id, lesson.course_id, lesson.lesson_id, _date_value(lesson.date),
                 part.part_type.value, part.title, part.text, image_reference, image_hash, image_bytes),
            )
        conn.execute(
            """UPDATE course_lessons SET generation_status='generated', model=?, error=NULL,
            generated_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE season_id=? AND course_id=? AND lesson_id=?""",
            (generated.model, lesson.season_id, lesson.course_id, lesson.lesson_id),
        )


def load_part(lesson: CourseDay, part_type: PartType) -> StoredPart | None:
    init_course_storage()
    with database.connect() as conn:
        row = conn.execute(
            """SELECT season_id, course_id, lesson_id, lesson_date, part_type, title, text,
            image_reference, image_hash, image_data FROM lesson_parts
            WHERE season_id=? AND course_id=? AND lesson_id=? AND part_type=?
            AND generation_status='generated'""",
            (lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value),
        ).fetchone()
    if not row:
        return None
    lesson_date = row[3] if isinstance(row[3], date) else date.fromisoformat(row[3])
    return StoredPart(row[0], row[1], row[2], lesson_date, PartType(row[4]),
                      row[5], row[6], row[7], row[8], bytes(row[9]))


def replace_prepared_lesson_covers(
    lesson: CourseDay,
    image_artifacts: dict[PartType, tuple[str, str, bytes]],
) -> None:
    """Replace only image fields for an unstarted prepared lesson."""
    requested = set(image_artifacts)
    if not requested or not requested.issubset(set(PartType)):
        raise CoverRebuildError("Cover rebuild requires at least one valid course part")
    init_course_storage()
    with database.connect(immediate=True) as conn:
        rows = conn.execute(
            """SELECT part_type FROM lesson_parts
            WHERE season_id=? AND course_id=? AND lesson_id=?
            AND generation_status='generated'""",
            (lesson.season_id, lesson.course_id, lesson.lesson_id),
        ).fetchall()
        if not requested.issubset({PartType(row[0]) for row in rows}):
            raise CoverRebuildError("Lesson must be fully prepared before a cover-only rebuild")
        for part_type, (reference, digest, content) in image_artifacts.items():
            publications = conn.execute(
                """SELECT COUNT(*) FROM platform_publications
                WHERE season_id=? AND course_id=? AND lesson_id=? AND part_type=?""",
                (lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value),
            ).fetchone()[0]
            if publications:
                raise CoverRebuildError(
                    f"Cover-only rebuild is blocked after {part_type.value} publication has started"
                )
            conn.execute(
                """UPDATE lesson_parts SET image_reference=?, image_hash=?, image_data=?
                WHERE season_id=? AND course_id=?
                AND lesson_id=? AND part_type=? AND generation_status='generated'""",
                (reference, digest, content, lesson.season_id, lesson.course_id,
                 lesson.lesson_id, part_type.value),
            )


def recent_reinforce_texts(lesson: CourseDay, limit: int = 7) -> tuple[str, ...]:
    init_course_storage()
    with database.connect() as conn:
        rows = conn.execute(
            """SELECT text FROM lesson_parts WHERE season_id=? AND course_id=?
            AND lesson_date < ? AND part_type=? AND generation_status='generated'
            ORDER BY lesson_date DESC LIMIT ?""",
            (lesson.season_id, lesson.course_id, _date_value(lesson.date), PartType.REINFORCE.value, limit),
        ).fetchall()
    return tuple(row[0] for row in rows)


def publication_key(lesson: CourseDay, part_type: PartType, platform: str) -> str:
    return ":".join((lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value, platform))


def claim_publication(lesson: CourseDay, part_type: PartType, platform: str, scheduled_at: str) -> int:
    init_course_storage()
    key = publication_key(lesson, part_type, platform)
    with database.connect(immediate=True) as conn:
        conn.execute(
            """INSERT INTO platform_publications
            (publication_key, season_id, course_id, lesson_id, part_type, platform, status, scheduled_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            ON CONFLICT(publication_key) DO NOTHING""",
            (key, lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value,
             platform, _timestamp_value(scheduled_at)),
        )
        cursor = conn.execute(
            """UPDATE platform_publications SET status='publishing', attempt_count=attempt_count+1,
            error=NULL, updated_at=CURRENT_TIMESTAMP WHERE publication_key=?
            AND status IN ('pending', 'failed')""",
            (key,),
        )
        if cursor.rowcount != 1:
            return 0
        row = conn.execute(
            "SELECT attempt_count FROM platform_publications WHERE publication_key=?",
            (key,),
        ).fetchone()
        return int(row[0])


def finish_publication(lesson: CourseDay, part_type: PartType, platform: str, *,
                       status: str, external_id: str | None = None, error: str | None = None) -> None:
    key = publication_key(lesson, part_type, platform)
    published = "CURRENT_TIMESTAMP" if status == "published" else "NULL"
    with database.connect() as conn:
        conn.execute(
            f"""UPDATE platform_publications SET status=?, external_id=?, error=?,
            published_at={published}, updated_at=CURRENT_TIMESTAMP WHERE publication_key=?""",
            (status, external_id, (error or "")[:2000] or None, key),
        )


def mark_missed(lesson: CourseDay, part_type: PartType, platform: str, scheduled_at: str,
                reason: str) -> None:
    init_course_storage()
    key = publication_key(lesson, part_type, platform)
    with database.connect() as conn:
        conn.execute(
            """INSERT INTO platform_publications
            (publication_key, season_id, course_id, lesson_id, part_type, platform,
             status, error, scheduled_at) VALUES (?, ?, ?, ?, ?, ?, 'missed', ?, ?)
            ON CONFLICT(publication_key) DO NOTHING""",
            (key, lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value,
             platform, reason, _timestamp_value(scheduled_at)),
        )


def publication_statuses(lesson: CourseDay, part_type: PartType) -> dict[str, str]:
    init_course_storage()
    with database.connect() as conn:
        rows = conn.execute(
            """SELECT platform, status FROM platform_publications
            WHERE season_id=? AND course_id=? AND lesson_id=? AND part_type=?""",
            (lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value),
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def claim_admin_alert(alert_key: str, alert_type: str) -> bool:
    init_course_storage()
    with database.connect(immediate=True) as conn:
        cursor = conn.execute(
            """INSERT INTO admin_alerts (alert_key, alert_type, status)
            VALUES (?, ?, 'claimed') ON CONFLICT(alert_key) DO NOTHING""",
            (alert_key, alert_type),
        )
        return cursor.rowcount == 1


def finish_admin_alert(alert_key: str, *, message_id: str | None = None,
                       error: str | None = None) -> None:
    status = "sent" if message_id else "failed"
    sent_at = "CURRENT_TIMESTAMP" if message_id else "NULL"
    with database.connect() as conn:
        conn.execute(
            f"""UPDATE admin_alerts SET status=?, telegram_message_id=?, error=?,
            sent_at={sent_at} WHERE alert_key=?""",
            (status, message_id, (error or "")[:1000] or None, alert_key),
        )


def recover_stale_work(minutes: int = 30) -> tuple[int, int]:
    """Recover stale work without retrying an indeterminate external Dzen publish."""
    init_course_storage()
    with database.connect(immediate=True) as conn:
        if database.config.backend == "sqlite":
            threshold = f"-{minutes} minutes"
            retryable_publications = conn.execute(
                """UPDATE platform_publications SET status='failed',
                error='Recovered stale publishing claim', updated_at=CURRENT_TIMESTAMP
                WHERE status='publishing' AND platform<>'dzen'
                AND updated_at <= datetime('now', ?)""",
                (threshold,),
            ).rowcount
            ambiguous_dzen = conn.execute(
                """UPDATE platform_publications SET status='ambiguous',
                error='Stale Dzen claim requires manual verification', updated_at=CURRENT_TIMESTAMP
                WHERE status='publishing' AND platform='dzen'
                AND updated_at <= datetime('now', ?)""",
                (threshold,),
            ).rowcount
            generations = conn.execute(
                """UPDATE course_lessons SET generation_status='failed',
                error='Recovered stale generation claim', updated_at=CURRENT_TIMESTAMP
                WHERE generation_status='generating' AND updated_at <= datetime('now', ?)""",
                (threshold,),
            ).rowcount
        else:
            retryable_publications = conn.execute(
                """UPDATE platform_publications SET status='failed',
                error='Recovered stale publishing claim', updated_at=CURRENT_TIMESTAMP
                WHERE status='publishing' AND platform<>'dzen'
                AND updated_at <= CURRENT_TIMESTAMP - (? * INTERVAL '1 minute')""",
                (minutes,),
            ).rowcount
            ambiguous_dzen = conn.execute(
                """UPDATE platform_publications SET status='ambiguous',
                error='Stale Dzen claim requires manual verification', updated_at=CURRENT_TIMESTAMP
                WHERE status='publishing' AND platform='dzen'
                AND updated_at <= CURRENT_TIMESTAMP - (? * INTERVAL '1 minute')""",
                (minutes,),
            ).rowcount
            generations = conn.execute(
                """UPDATE course_lessons SET generation_status='failed',
                error='Recovered stale generation claim', updated_at=CURRENT_TIMESTAMP
                WHERE generation_status='generating' AND updated_at <= CURRENT_TIMESTAMP - (? * INTERVAL '1 minute')""",
                (minutes,),
            ).rowcount
    return retryable_publications + ambiguous_dzen, generations
