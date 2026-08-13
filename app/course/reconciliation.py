from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import COURSE_CATCHUP_MINUTES, COURSE_TIMEZONE
from app.course.models import PartType
from app.course.repository import recover_stale_work
from app.course.service import curriculum, mark_part_missed, publish_lesson_part

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationDecision:
    publish: PartType | None
    missed: tuple[PartType, ...]
    reason: str


def decide_reconciliation(now: datetime, catchup_minutes: int = COURSE_CATCHUP_MINUTES) -> ReconciliationDecision:
    due = [part for part in PartType if part.scheduled_time <= now.timetz().replace(tzinfo=None)]
    if not due:
        return ReconciliationDecision(None, (), "no part is due yet")
    latest = due[-1]
    scheduled = datetime.combine(now.date(), latest.scheduled_time, now.tzinfo)
    delay_minutes = int((now - scheduled).total_seconds() // 60)
    if delay_minutes <= catchup_minutes:
        return ReconciliationDecision(latest, tuple(due[:-1]), f"catch-up after {delay_minutes} minutes")
    return ReconciliationDecision(None, tuple(due), f"latest part is {delay_minutes} minutes late")


async def reconcile_course_publications(now: datetime | None = None) -> None:
    recovered_publications, recovered_generations = recover_stale_work()
    if recovered_publications or recovered_generations:
        logger.warning(
            "Recovered stale course work: publications=%d generations=%d",
            recovered_publications,
            recovered_generations,
        )
    current = now or datetime.now(ZoneInfo(COURSE_TIMEZONE))
    plan = curriculum()
    lesson = plan.day_for_date(current.date())
    if not lesson:
        return
    decision = decide_reconciliation(current)
    for part_type in decision.missed:
        mark_part_missed(lesson, part_type, decision.reason)
        logger.info("Course part marked missed: lesson=%s part=%s reason=%s",
                    lesson.lesson_id, part_type.value, decision.reason)
    if decision.publish:
        await publish_lesson_part(decision.publish, target_date=current.date())
