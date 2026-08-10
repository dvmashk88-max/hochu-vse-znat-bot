import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.publisher import publish_next_post
from app.config import POST_INTERVAL_HOURS
from app.marketcode.config import load_settings, parse_post_time
from app.marketcode.publisher import publish_marketcode_article

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(
        publish_next_post,
        trigger="interval",
        hours=POST_INTERVAL_HOURS,
        id="publish_post",
        replace_existing=True,
    )

    marketcode = load_settings()
    if marketcode.enabled:
        hour, minute = parse_post_time(marketcode.post_time)
        scheduler.add_job(
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
        logger.info(
            "MarketCode scheduler started — daily at %s (%s)",
            marketcode.post_time,
            marketcode.timezone,
        )
    else:
        logger.info("MarketCode scheduler is disabled")

    scheduler.start()
    logger.info("Scheduler started — interval: %d h", POST_INTERVAL_HOURS)
