import asyncio
import logging
import urllib3
import requests
from typing import Optional
from app.config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "HochuVseZnatBot/1.0"}


def _unsplash(query: str) -> Optional[str]:
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={**_HEADERS, "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["urls"]["regular"]
    except Exception as e:
        logger.warning("Unsplash error: %s", e)
    return None


def _pexels(query: str) -> Optional[str]:
    if not PEXELS_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={**_HEADERS, "Authorization": PEXELS_API_KEY},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if photos:
            return photos[0]["src"]["large"]
    except Exception as e:
        logger.warning("Pexels error: %s", e)
    return None


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.content


async def fetch_image(query: str) -> Optional[bytes]:
    url = await asyncio.to_thread(_unsplash, query)
    if not url:
        logger.info("Unsplash returned nothing, trying Pexels")
        url = await asyncio.to_thread(_pexels, query)
    if not url:
        logger.warning("No image found for query: %s", query)
        return None
    try:
        return await asyncio.to_thread(_download, url)
    except Exception as e:
        logger.warning("Image download failed: %s", e)
        return None
