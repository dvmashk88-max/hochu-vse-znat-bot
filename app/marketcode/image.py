import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_MIN_IMAGE_BYTES = 10_000


def _download_image(url: str) -> bytes | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        path = Path(url)
        content = path.read_bytes()
        if len(content) < _MIN_IMAGE_BYTES:
            raise ValueError("MARKETCODE_IMAGE_URL local image is unexpectedly small")
        return content

    response = requests.get(url, timeout=45)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if not content_type.startswith("image/"):
        raise ValueError(f"MARKETCODE_IMAGE_URL returned {content_type or 'unknown content type'}")
    if len(response.content) < _MIN_IMAGE_BYTES:
        raise ValueError("MARKETCODE_IMAGE_URL returned an unexpectedly small image")
    return response.content


async def fetch_brand_cover(url: str) -> bytes | None:
    try:
        return await asyncio.to_thread(_download_image, url)
    except Exception as exc:
        logger.warning("MarketCode cover is unavailable: %s", exc)
        return None
