import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import COURSE_CURRICULUM_PATH, COURSE_ENABLED, COURSE_PREPARE_DAYS, COURSE_TIMEZONE
from app.course.curriculum import load_curriculum_catalog
from app.course.models import PartType
from app.course.reconciliation import reconcile_course_publications
from app.course.service import prepare_course_days, publish_lesson_part
from app.marketcode.config import load_settings, parse_post_time
from app.marketcode.publisher import publish_marketcode_article

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=COURSE_TIMEZONE)


async def publish_course_explain() -> None:
    await publish_lesson_part(PartType.EXPLAIN)


async def publish_course_try() -> None:
    await publish_lesson_part(PartType.TRY)


async def publish_course_reinforce() -> None:
    await publish_lesson_part(PartType.REINFORCE)


def configure_scheduler(target: AsyncIOScheduler = scheduler) -> None:
    if COURSE_ENABLED:
        if not 0 <= COURSE_PREPARE_DAYS <= 14:
            raise ValueError("COURSE_PREPARE_DAYS must be between 0 and 14")
        plan = load_curriculum_catalog(COURSE_CURRICULUM_PATH)
        if plan.timezone != COURSE_TIMEZONE:
            raise ValueError(
                f"Curriculum timezone {plan.timezone} does not match COURSE_TIMEZONE {COURSE_TIMEZONE}"
            )
        for job_id, operation, hour in (
            ("publish_course_explain", publish_course_explain, 9),
            ("publish_course_try", publish_course_try, 15),
            ("publish_course_reinforce", publish_course_reinforce, 20),
        ):
            target.add_job(
                operation,
                trigger="cron",
                hour=hour,
                minute=0,
                timezone=COURSE_TIMEZONE,
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
        target.add_job(
            prepare_course_days,
            trigger="cron",
            hour=0,
            minute=10,
            timezone=COURSE_TIMEZONE,
            id="prepare_course_days",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        target.add_job(
            reconcile_course_publications,
            trigger="interval",
            minutes=10,
            id="reconcile_course_publications",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        target.add_job(
            prepare_course_days,
            trigger="date",
            id="prepare_course_on_startup",
            replace_existing=True,
        )
        target.add_job(
            reconcile_course_publications,
            trigger="date",
            id="reconcile_course_on_startup",
            replace_existing=True,
        )
        logger.info("Course scheduler configured: 09:00, 15:00, 20:00 (%s)", COURSE_TIMEZONE)
    else:
        logger.info("Course scheduler is disabled")

    marketcode = load_settings()
    if marketcode.enabled:
        hour, minute = parse_post_time(marketcode.post_time)
        target.add_job(
            publish_marketcode_article,
            trigger="cron",
            hour=hour,
            minute=minute,
            timezone=marketcode.timezone,
            id="publish_marketcode_article",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("MarketCode scheduler started — daily at %s (%s)",
                    marketcode.post_time, marketcode.timezone)
    else:
        logger.info("MarketCode scheduler is disabled")


def start_scheduler() -> None:
    configure_scheduler(scheduler)
    scheduler.start()
    logger.info("Scheduler started")
