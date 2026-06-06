import logging
from app.bot import send_text, send_photo_with_caption
from app.generator import generate_post
from app.images import fetch_image, generate_image_query
from app.topic_selector import pick_next_topic
from app.db import save_dzen_publication_status, save_published_topic
from app.config import TELEGRAM_CHANNEL_ID
from app.dzen_publisher import publish_draft

logger = logging.getLogger(__name__)


async def publish_next_post() -> None:
    topic = await pick_next_topic()
    logger.info("Selected topic: %s", topic)

    try:
        text = await generate_post(topic)
    except Exception as e:
        logger.error("Failed to generate post for '%s': %s", topic, e)
        return

    try:
        image_bytes = await fetch_image(generate_image_query(topic))
    except Exception as e:
        logger.warning("Failed to fetch image for '%s': %s", topic, e)
        image_bytes = None

    try:
        if image_bytes:
            await send_photo_with_caption(TELEGRAM_CHANNEL_ID, image_bytes, caption=text)
        else:
            await send_text(TELEGRAM_CHANNEL_ID, text)
    except Exception as e:
        logger.error("Failed to send post to Telegram: %s", e)
        return

    save_published_topic(topic)
    logger.info("Published topic: %s", topic)

    try:
        dzen_status = await publish_draft(title=topic, text=text, image_bytes=image_bytes)
    except Exception as e:
        save_dzen_publication_status(topic, "failed", str(e))
        logger.error("Failed to create Dzen draft: %s", e)
    else:
        save_dzen_publication_status(topic, dzen_status)
        logger.info("Dzen publication status for '%s': %s", topic, dzen_status)
