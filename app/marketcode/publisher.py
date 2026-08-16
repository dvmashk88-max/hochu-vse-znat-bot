from __future__ import annotations

import logging
from pathlib import Path

from app.bot import send_photo_with_caption, send_text
from app.config import TELEGRAM_CHANNEL_ID
from app.dzen_publisher import DzenPublishAmbiguousError, publish_draft
from app.marketcode.config import load_settings
from app.marketcode.content_plan import load_content_plan
from app.marketcode.generator import generate_article
from app.marketcode.image import fetch_brand_cover
from app.marketcode.repository import published_days, save_publication
from app.marketcode.vk import publish_marketcode_to_vk
from app.max_publisher import publish_to_max

logger = logging.getLogger(__name__)


def _next_entry(content_plan: str):
    completed = published_days()
    path = Path(content_plan)
    return next((entry for entry in load_content_plan(path) if entry.day not in completed), None)

async def _attempt(label: str, operation, statuses: dict[str, str]) -> None:
    try:
        result = await operation()
    except DzenPublishAmbiguousError as exc:
        statuses[label] = f"ambiguous: {exc}"
        logger.error("MarketCode %s publication requires manual verification: %s", label, exc)
    except Exception as exc:
        statuses[label] = f"failed: {exc}"
        logger.error("MarketCode %s publication failed: %s", label, exc)
    else:
        statuses[label] = f"published: {result or 'ok'}"


async def publish_marketcode_article() -> None:
    settings = load_settings()
    if not settings.enabled:
        logger.info("MarketCode stream is disabled")
        return

    entry = _next_entry(settings.content_plan)
    if entry is None:
        logger.warning("MarketCode content plan is exhausted")
        return

    try:
        article = await generate_article(entry, settings)
    except Exception as exc:
        logger.error("MarketCode generation failed for day %d: %s", entry.day, exc)
        return

    image_bytes = await fetch_brand_cover(settings.image_url)
    if not image_bytes:
        logger.error("MarketCode publication cancelled: the required brand cover is unavailable")
        return

    statuses: dict[str, str] = {}

    async def telegram_operation():
        await send_photo_with_caption(TELEGRAM_CHANNEL_ID, image_bytes, "")
        await send_text(TELEGRAM_CHANNEL_ID, article.full_text)
        return "sent as cover + 1 complete text message"

    await _attempt("telegram", telegram_operation, statuses)
    await _attempt(
        "max",
        lambda: publish_to_max(text=article.full_text, image_bytes=image_bytes),
        statuses,
    )
    await _attempt(
        "vk",
        lambda: publish_marketcode_to_vk(text=article.full_text),
        statuses,
    )
    await _attempt(
        "dzen",
        lambda: publish_draft(title=article.title, text=article.body, image_bytes=image_bytes),
        statuses,
    )

    save_publication(
        plan_day=entry.day,
        topic=entry.topic,
        category=entry.category,
        word_count=article.word_count,
        model=article.model,
        channel_statuses=statuses,
    )
    logger.info("MarketCode day %d finished: %s", entry.day, statuses)
