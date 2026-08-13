from __future__ import annotations

import logging
from dataclasses import dataclass

from app.bot import send_text
from app.config import ADMIN_TELEGRAM_CHAT_ID, COURSE_ALERTS_ENABLED
from app.course.models import CourseDay, PartType
from app.course.repository import claim_admin_alert, finish_admin_alert

logger = logging.getLogger(__name__)
_process_claims: set[str] = set()
_configuration_warning_logged = False


@dataclass(frozen=True)
class AdminAlert:
    key: str
    alert_type: str
    message: str


def lesson_alert(alert_type: str, day: CourseDay, status: str, error: str,
                 part_type: PartType | None = None) -> AdminAlert:
    part = f":{part_type.value}" if part_type else ""
    key = f"{alert_type}:{day.date.isoformat()}:{day.lesson_id}{part}"
    course = day.course_title if day.day_type == "lesson" else day.cover_label
    lesson = (
        f"{day.lesson_number} из {day.lesson_count}"
        if day.day_type == "lesson" else day.lesson_id
    )
    part_line = f"\nЧасть: {part_type.public_name}" if part_type else ""
    heading = "ошибка публикации части" if alert_type == "all_platforms_failed" else "ошибка подготовки урока"
    message = (
        f"⚠️ Хочу всё знать — {heading}\n"
        f"Дата: {day.date.isoformat()}\n"
        f"Сезон: {day.season_number}\n"
        f"Курс: {course}\n"
        f"Урок: {lesson}\n"
        f"Тема: {day.topic}{part_line}\n"
        f"Статус: {status}\n"
        f"Краткая ошибка: {error[:700]}"
    )
    return AdminAlert(key, alert_type, message)


def system_alert(alert_type: str, key_suffix: str, title: str, error: str) -> AdminAlert:
    return AdminAlert(
        f"{alert_type}:{key_suffix}",
        alert_type,
        f"⚠️ Хочу всё знать — {title}\nСтатус: failed\nКраткая ошибка: {error[:700]}",
    )


async def send_admin_alert(alert: AdminAlert, *, persistent_dedupe: bool = True) -> bool:
    global _configuration_warning_logged
    if not COURSE_ALERTS_ENABLED or not ADMIN_TELEGRAM_CHAT_ID:
        if not _configuration_warning_logged:
            logger.warning(
                "Course admin alerts are disabled or ADMIN_TELEGRAM_CHAT_ID is not configured"
            )
            _configuration_warning_logged = True
        return False
    if alert.key in _process_claims:
        return False
    _process_claims.add(alert.key)
    if persistent_dedupe:
        try:
            if not claim_admin_alert(alert.key, alert.alert_type):
                return False
        except Exception as exc:
            logger.error("Admin alert persistent dedupe unavailable: %s", exc)
    try:
        message_id = await send_text(ADMIN_TELEGRAM_CHAT_ID, alert.message)
    except Exception as exc:
        logger.error("Admin alert delivery failed: type=%s error=%s", alert.alert_type, exc)
        if persistent_dedupe:
            try:
                finish_admin_alert(alert.key, error=str(exc))
            except Exception:
                logger.exception("Cannot persist failed admin alert status")
        return False
    if persistent_dedupe:
        try:
            finish_admin_alert(alert.key, message_id=message_id)
        except Exception:
            logger.exception("Cannot persist sent admin alert status")
    logger.info("Admin alert sent: type=%s key=%s", alert.alert_type, alert.key)
    return True
