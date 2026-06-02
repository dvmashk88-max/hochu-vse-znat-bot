import asyncio
import logging
import urllib3
import requests
from typing import Optional
from app.config import UNSPLASH_ACCESS_KEY, PEXELS_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_SPACE_KEYWORDS = [
    "космос", "ракет", "планет", "вселенн", "астроном", "спутник",
    "луна", "марс", "юпитер", "сатурн", "галактик", "звезд", "орбит",
    "мкс", "nasa", "нло", "метеор", "комет", "черная дыр", "чёрная дыр",
]
_TECH_KEYWORDS = [
    "технолог", "компьютер", "программ", "цифров", "интернет", "смартфон",
    "робот", "автоматизац", "искусственный интеллект", "нейросет", "алгоритм",
    "процессор", "гаджет", "электроник",
]
_HEALTH_KEYWORDS = [
    "здоровь", "медицин", "врач", "болезн", "лечени", "спорт", "питани",
    "диет", "витамин", "иммунитет", "мозг", "нейрон", "ген", "биолог",
    "анатоми", "физиолог",
]
_BUSINESS_KEYWORDS = [
    "деньг", "бизнес", "финанс", "экономик", "инвестиц", "банк", "акци",
    "доход", "зарплат", "налог", "предпринимател", "стартап", "маркетинг",
    "менеджмент", "продаж",
]
_PSYCHOLOGY_KEYWORDS = [
    "психолог", "эмоц", "стресс", "тревог", "депресс", "память", "сознани",
    "поведени", "личност", "характер", "мотивац", "интеллект", "восприяти",
]

_SAFE_QUERIES = {
    "space": "space exploration NASA spacecraft rocket launch astronomy galaxy",
    "tech": "modern technology digital innovation computer science AI laptop workspace",
    "health": "healthcare medicine doctor wellness healthy lifestyle",
    "business": "business finance startup office analytics",
    "psychology": "psychology mindfulness human brain mental health",
    "default": "knowledge education science learning",
}

_BANNED_WORDS = {"weapon", "war", "missile", "military", "gun", "army", "tank"}


def generate_image_query(topic: str) -> str:
    t = topic.lower()

    if any(kw in t for kw in _SPACE_KEYWORDS):
        return _SAFE_QUERIES["space"]
    if any(kw in t for kw in _TECH_KEYWORDS):
        return _SAFE_QUERIES["tech"]
    if any(kw in t for kw in _HEALTH_KEYWORDS):
        return _SAFE_QUERIES["health"]
    if any(kw in t for kw in _BUSINESS_KEYWORDS):
        return _SAFE_QUERIES["business"]
    if any(kw in t for kw in _PSYCHOLOGY_KEYWORDS):
        return _SAFE_QUERIES["psychology"]

    return _SAFE_QUERIES["default"]

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
