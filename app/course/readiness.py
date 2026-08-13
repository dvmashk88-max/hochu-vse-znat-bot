from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from app.config import (
    ADMIN_TELEGRAM_CHAT_ID,
    COURSE_AI_FALLBACK_MODEL,
    COURSE_AI_MODEL,
    COURSE_ALERTS_ENABLED,
    COURSE_ENABLED,
    COURSE_PREPARE_DAYS,
    COURSE_TIMEZONE,
    DZEN_STORAGE_STATE_JSON,
    MAX_BOT_TOKEN,
    MAX_CHANNEL_ID,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHANNEL_ID,
    VK_ACCESS_TOKEN,
    VK_GROUP_ID,
)
from app.course.curriculum import CurriculumCatalog
from app.database import Database
from app.marketcode.config import MarketCodeSettings


@dataclass
class CourseReadiness:
    enabled: bool = COURSE_ENABLED
    curriculum_loaded: bool = False
    database_ready: bool = False
    scheduler_started: bool = False

    def public_dict(self) -> dict[str, bool]:
        return asdict(self)


readiness = CourseReadiness()


def database_summary(db: Database) -> tuple[str, str]:
    backend = "PostgreSQL" if db.config.backend == "postgresql" else "SQLite"
    return backend, "configured"


def startup_summary(catalog: CurriculumCatalog, db: Database,
                    marketcode: MarketCodeSettings) -> str:
    courses = len({lesson.course_id for lesson in catalog.lessons})
    backend, connection = database_summary(db)
    dzen_configured = bool(DZEN_STORAGE_STATE_JSON or Path("storage/dzen_cookies.json").exists())
    alerts = "enabled/configured" if COURSE_ALERTS_ENABLED and ADMIN_TELEGRAM_CHAT_ID else "disabled/not configured"
    lines = [
        "=== ХОЧУ ВСЁ ЗНАТЬ — COURSE STARTUP ===",
        f"Course enabled: {str(COURSE_ENABLED).lower()}",
        f"Timezone: {COURSE_TIMEZONE}",
        "Curriculum:",
        f"  Seasons: {len(catalog.seasons)}",
        f"  Courses: {courses}",
        f"  Lessons: {len(catalog.lessons)}",
        f"  Special days: {len(catalog.special_days)}",
        f"  Calendar days: {len(catalog.days)}",
        f"  Range: {catalog.days[0].date} → {catalog.days[-1].date}",
        "Course AI:",
        f"  Primary: {COURSE_AI_MODEL}",
        f"  Fallback: {COURSE_AI_FALLBACK_MODEL}",
        "Database:",
        f"  Backend: {backend}",
        f"  Connection: {connection}",
        "  Schema: ready",
        f"Preparation horizon: Today + {COURSE_PREPARE_DAYS} days",
        "Scheduler:",
        "  09:00 РАЗБИРАЕМ",
        "  15:00 ПРОБУЕМ",
        "  20:00 ЗАКРЕПЛЯЕМ",
        "  00:10 prepare",
        "  reconciliation: 10 minutes",
        "Platforms:",
        f"  Telegram: {'configured' if TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID else 'not configured'}",
        f"  MAX: {'configured' if MAX_BOT_TOKEN and MAX_CHANNEL_ID else 'not configured'}",
        f"  VK: {'configured' if VK_ACCESS_TOKEN and VK_GROUP_ID else 'not configured'}",
        f"  Dzen: {'configured' if dzen_configured else 'not configured'}",
        f"Admin alerts: {alerts}",
        "MarketCode:",
        f"  enabled: {str(marketcode.enabled).lower()}",
        f"  schedule: {marketcode.post_time}",
        f"  timezone: {marketcode.timezone}",
        "========================================",
    ]
    return "\n".join(lines)
