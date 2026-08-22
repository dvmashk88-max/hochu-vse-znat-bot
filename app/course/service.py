from __future__ import annotations

import logging
import hashlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.bot import send_photo_with_caption
from app.config import (
    COURSE_CURRICULUM_PATH,
    COURSE_PREPARE_DAYS,
    COURSE_SOURCE_TIMEOUT,
    COURSE_TIMEZONE,
    TELEGRAM_CHANNEL_ID,
)
from app.course.alerts import lesson_alert, send_admin_alert, system_alert
from app.course.covers import COVER_RENDERER_VERSION, render_cover
from app.course.curriculum import CurriculumCatalog, load_curriculum_catalog
from app.course.generator import CourseGenerationError, generate_lesson
from app.course.models import CourseDay, PartType
from app.course.quality import LessonQualityError, validate_parts
from app.course.repository import (
    claim_generation,
    claim_publication,
    finish_publication,
    generation_status,
    load_part,
    mark_missed,
    publication_statuses,
    recent_reinforce_texts,
    replace_prepared_lesson_covers,
    retry_needs_review_generation,
    save_generated_lesson,
    save_generation_failure,
)
from app.course.sources import SourceRetrievalError, SourceRetriever
from app.dzen_publisher import DzenPublishAmbiguousError, publish_draft
from app.max_publisher import publish_to_max
from app.vk_publisher import publish_to_vk

logger = logging.getLogger(__name__)
PLATFORMS = ("telegram", "max", "vk", "dzen")


def curriculum() -> CurriculumCatalog:
    return load_curriculum_catalog(COURSE_CURRICULUM_PATH)


def _cover_artifacts(
    lesson: CourseDay,
    part_types: tuple[PartType, ...] = tuple(PartType),
) -> dict[PartType, tuple[str, str, bytes]]:
    artifacts = {}
    for part_type in part_types:
        image_bytes, image_hash = render_cover(lesson, part_type)
        artifacts[part_type] = (
            f"course-cover://{lesson.season_id}/{lesson.course_id}/{lesson.lesson_id}/"
            f"{part_type.value}?renderer={COVER_RENDERER_VERSION}",
            image_hash,
            image_bytes,
        )
    return artifacts


def rebuild_prepared_lesson_covers(
    lesson: CourseDay,
    part_types: tuple[PartType, ...] = tuple(PartType),
) -> None:
    """Re-render stored images without regenerating or rewriting lesson text."""
    replace_prepared_lesson_covers(lesson, _cover_artifacts(lesson, part_types))


async def prepare_lesson(
    lesson: CourseDay,
    retriever: SourceRetriever | None = None,
    *,
    retry_needs_review: bool = False,
) -> bool:
    try:
        status = generation_status(lesson)
    except Exception as exc:
        logger.error("Course state read failed: lesson=%s error=%s", lesson.lesson_id, exc)
        await send_admin_alert(system_alert(
            "database_error", f"{lesson.date}:{lesson.lesson_id}:generation-read",
            "критическая ошибка базы course state", str(exc),
        ), persistent_dedupe=False)
        return False
    if status == "needs_review":
        if not retry_needs_review:
            logger.info(
                "Course generation awaits scheduled retry: lesson=%s status=%s",
                lesson.lesson_id,
                status,
            )
            return False
        try:
            retryable = retry_needs_review_generation(lesson)
        except Exception as exc:
            logger.error("Course needs-review retry failed: lesson=%s error=%s", lesson.lesson_id, exc)
            return False
        if not retryable:
            logger.warning(
                "Course needs-review lesson cannot be retried safely: lesson=%s",
                lesson.lesson_id,
            )
            return False
        logger.info("Course needs-review lesson scheduled for one retry: lesson=%s", lesson.lesson_id)
        status = "failed"
    if status == "generated":
        try:
            stored_parts = tuple(load_part(lesson, part_type) for part_type in PartType)
            if any(part is None for part in stored_parts):
                raise LessonQualityError(["stored lesson is missing one or more parts"])
            validate_parts(stored_parts, recent_reinforce_texts(lesson))
        except LessonQualityError as exc:
            try:
                already_started = any(
                    publication_statuses(lesson, part_type) for part_type in PartType
                )
            except Exception as state_exc:
                logger.error(
                    "Course legacy publication state read failed: lesson=%s error=%s",
                    lesson.lesson_id, state_exc,
                )
                return False
            if already_started:
                logger.warning(
                    "Course lesson keeps legacy generated text because publication already started: "
                    "lesson=%s error=%s",
                    lesson.lesson_id, exc,
                )
                return True
            logger.info(
                "Course lesson will be regenerated under current quality rules: lesson=%s error=%s",
                lesson.lesson_id, exc,
            )
            save_generation_failure(lesson, f"Stale generated lesson: {exc}", "failed")
            status = "failed"
        except Exception as exc:
            logger.error(
                "Course generated lesson quality read failed: lesson=%s error=%s",
                lesson.lesson_id, exc,
            )
            return False
        else:
            return True
    try:
        claimed = claim_generation(lesson)
    except Exception as exc:
        logger.error("Course generation claim failed: lesson=%s error=%s", lesson.lesson_id, exc)
        await send_admin_alert(system_alert(
            "database_error", f"{lesson.date}:{lesson.lesson_id}:generation-claim",
            "критическая ошибка базы course state", str(exc),
        ), persistent_dedupe=False)
        return False
    if not claimed:
        logger.info("Course generation already claimed: lesson=%s status=%s", lesson.lesson_id, status)
        return status == "generated"
    logger.info(
        "Course generation started: season=%s course=%s lesson=%s date=%s",
        lesson.season_id, lesson.course_id, lesson.lesson_id, lesson.date,
    )
    try:
        sources = await (retriever or SourceRetriever(COURSE_SOURCE_TIMEOUT)).retrieve(lesson)
        generated = await generate_lesson(
            lesson,
            sources,
            previous_reinforce_texts=recent_reinforce_texts(lesson),
        )
        artifacts = _cover_artifacts(lesson)
        save_generated_lesson(generated, sources, artifacts)
    except SourceRetrievalError as exc:
        try:
            save_generation_failure(lesson, str(exc), "failed")
        except Exception:
            logger.exception("Cannot persist source failure: lesson=%s", lesson.lesson_id)
        await send_admin_alert(lesson_alert(
            "mandatory_sources_unavailable", lesson, "failed", str(exc)
        ))
        logger.error("Course required sources unavailable: lesson=%s error=%s", lesson.lesson_id, exc)
        return False
    except CourseGenerationError as exc:
        try:
            save_generation_failure(lesson, str(exc), "needs_review")
        except Exception:
            logger.exception("Cannot persist needs_review: lesson=%s", lesson.lesson_id)
        await send_admin_alert(lesson_alert(
            "lesson_needs_review", lesson, "needs_review", str(exc)
        ))
        logger.error("Course generation needs review: lesson=%s error=%s", lesson.lesson_id, exc)
        return False
    except Exception as exc:
        try:
            save_generation_failure(lesson, str(exc), "failed")
        except Exception:
            logger.exception("Cannot persist generation failure: lesson=%s", lesson.lesson_id)
        await send_admin_alert(lesson_alert(
            "lesson_generation_failed", lesson, "failed", str(exc)
        ))
        logger.error("Course preparation failed: lesson=%s error=%s", lesson.lesson_id, exc)
        return False
    logger.info("Course generation completed: lesson=%s model=%s", lesson.lesson_id, generated.model)
    return True


async def prepare_course_days(reference_date: date | None = None) -> None:
    plan = curriculum()
    today = reference_date or datetime.now(ZoneInfo(COURSE_TIMEZONE)).date()
    for offset in range(COURSE_PREPARE_DAYS + 1):
        target = today + timedelta(days=offset)
        day = plan.day_for_date(target)
        if day:
            await prepare_lesson(day, retry_needs_review=True)


async def _telegram(text: str, image: bytes) -> str:
    message_id = await send_photo_with_caption(TELEGRAM_CHANNEL_ID, image, text)
    return str(message_id)


async def _publish_platform(platform: str, lesson: CourseDay, part_type: PartType,
                            title: str, text: str, image: bytes) -> str:
    if platform == "telegram":
        return await _telegram(text, image)
    if platform == "max":
        return await publish_to_max(text=text, image_bytes=image)
    if platform == "vk":
        return await publish_to_vk(text=text, image_bytes=None)
    if platform == "dzen":
        return await publish_draft(title=f"{part_type.public_name}: {lesson.topic}", text=text, image_bytes=image)
    raise ValueError(f"Unknown platform: {platform}")


async def publish_lesson_part(part_type: PartType, *, target_date: date | None = None) -> None:
    now = datetime.now(ZoneInfo(COURSE_TIMEZONE))
    plan = curriculum()
    lesson = plan.day_for_date(target_date or now.date())
    if not lesson:
        logger.info("No curriculum day today: date=%s", target_date or now.date())
        return
    if not await prepare_lesson(lesson):
        logger.error("Course publication cancelled: lesson=%s generation is not ready", lesson.lesson_id)
        return
    try:
        part = load_part(lesson, part_type)
    except Exception as exc:
        logger.error("Course part state read failed: lesson=%s error=%s", lesson.lesson_id, exc)
        await send_admin_alert(system_alert(
            "database_error", f"{lesson.date}:{lesson.lesson_id}:{part_type.value}:part-read",
            "критическая ошибка базы course state", str(exc),
        ), persistent_dedupe=False)
        return
    if not part:
        logger.error("Course publication cancelled: lesson=%s part=%s is absent", lesson.lesson_id, part_type.value)
        return
    image = part.image_bytes
    if hashlib.sha256(image).hexdigest() != part.image_hash:
        logger.error("Course cover hash mismatch: lesson=%s part=%s", lesson.lesson_id, part_type.value)
        return
    scheduled = datetime.combine(lesson.date, part_type.scheduled_time, ZoneInfo(COURSE_TIMEZONE)).isoformat()
    for platform in PLATFORMS:
        try:
            attempt = claim_publication(lesson, part_type, platform, scheduled)
        except Exception as exc:
            logger.error("Course publication claim failed: platform=%s error=%s", platform, exc)
            await send_admin_alert(system_alert(
                "database_error", f"{lesson.date}:{lesson.lesson_id}:{part_type.value}:claim",
                "критическая ошибка базы course state", str(exc),
            ), persistent_dedupe=False)
            continue
        if not attempt:
            logger.info(
                "Course platform skipped by idempotency: lesson=%s part=%s platform=%s",
                lesson.lesson_id, part_type.value, platform,
            )
            continue
        logger.info(
            "Course platform attempt: season=%s course=%s lesson=%s part=%s scheduled=%s "
            "platform=%s attempt=%d retry=%s",
            lesson.season_id, lesson.course_id, lesson.lesson_id, part_type.value, scheduled,
            platform, attempt, attempt > 1,
        )
        try:
            result = await _publish_platform(platform, lesson, part_type, part.title, part.text, image)
        except DzenPublishAmbiguousError as exc:
            try:
                finish_publication(lesson, part_type, platform, status="ambiguous", error=str(exc))
            except Exception:
                logger.exception("Cannot persist ambiguous Dzen result")
            logger.error(
                "Course Dzen result is ambiguous and will not be retried automatically: "
                "lesson=%s part=%s error=%s",
                lesson.lesson_id, part_type.value, exc,
            )
            await send_admin_alert(lesson_alert(
                "dzen_publication_ambiguous",
                lesson,
                "ambiguous",
                str(exc),
                part_type,
                platform="dzen",
            ))
        except Exception as exc:
            try:
                finish_publication(lesson, part_type, platform, status="failed", error=str(exc))
            except Exception:
                logger.exception("Cannot persist platform failure: platform=%s", platform)
            logger.error("Course platform failed: lesson=%s part=%s platform=%s error=%s",
                         lesson.lesson_id, part_type.value, platform, exc)
        else:
            status = "draft" if platform == "dzen" and result == "draft" else "published"
            try:
                finish_publication(lesson, part_type, platform, status=status, external_id=str(result))
            except Exception as exc:
                logger.error("Cannot persist platform success: platform=%s error=%s", platform, exc)
                await send_admin_alert(system_alert(
                    "database_error", f"{lesson.date}:{lesson.lesson_id}:{part_type.value}:finish",
                    "результат публикации не сохранён в course state", str(exc),
                ), persistent_dedupe=False)
            logger.info("Course platform finished: lesson=%s part=%s platform=%s status=%s",
                        lesson.lesson_id, part_type.value, platform, status)
    try:
        statuses = publication_statuses(lesson, part_type)
    except Exception as exc:
        logger.error("Cannot evaluate aggregate platform status: %s", exc)
        return
    if set(statuses) == set(PLATFORMS) and all(value == "failed" for value in statuses.values()):
        await send_admin_alert(lesson_alert(
            "all_platforms_failed", lesson, "failed",
            "Ни одна платформа не опубликовала эту часть", part_type,
        ))


def mark_part_missed(lesson: CourseDay, part_type: PartType, reason: str) -> None:
    scheduled = datetime.combine(lesson.date, part_type.scheduled_time, ZoneInfo(COURSE_TIMEZONE)).isoformat()
    statuses = publication_statuses(lesson, part_type)
    for platform in PLATFORMS:
        if platform not in statuses:
            mark_missed(lesson, part_type, platform, scheduled, reason)
