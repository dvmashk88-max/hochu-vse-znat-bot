import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.publisher import publish_next_post
from app.config import POST_INTERVAL_HOURS

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
    scheduler.start()
    logger.info("Scheduler started — interval: %d h", POST_INTERVAL_HOURS)
