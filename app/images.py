import asyncio
import logging
import urllib3
import requests
import re
from dataclasses import dataclass
from typing import Iterable, Optional
from app.config import PEXELS_API_KEY, PIXABAY_API_KEY

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
_GENERIC_QUERIES = {"ai", "robot", "technology", "future", "startup"}


@dataclass(frozen=True)
class ImageCandidate:
    source: str
    url: str
    width: int
    height: int
    description: str = ""


@dataclass(frozen=True)
class ImageResult:
    bytes: bytes
    source: str
    url: str
    query: str

_TOPIC_QUERY_RULES = [
    (("gps", "навигац", "спутник"), "GPS satellite navigation technology map"),
    (("голубое", "небо"), "blue sky atmospheric scattering sunlight"),
    (("чёрные дыры", "черные дыры", "черная дыр", "чёрная дыр"), "black hole space astronomy accretion disk"),
    (("квант", "запутан", "суперпозиция"), "quantum physics particles abstract science"),
    (("мозг", "воспомин", "память", "нейрон", "мозжечок"), "human brain neurons neuroscience"),
    (("сон", "сны"), "sleep dream brain night"),
    (("иммун", "вакцин", "антибиот"), "immune system medicine laboratory"),
    (("тёмная материя", "темная материя"), "dark matter galaxy astronomy"),
    (("жизнь на земле", "синтетическая биология"), "origin of life biology cells laboratory"),
    (("динозавр",), "dinosaur fossil paleontology museum"),
    (("интернет",), "internet network data cables servers"),
    (("нейронные сети", "искусственный интеллект", "нейросет"), "artificial intelligence neural network technology"),
    (("старе",), "human aging biology science"),
    (("атом",), "atom molecule science laboratory"),
    (("антиматер",), "particle physics collider science"),
    (("океан", "цунами"), "ocean waves sea science"),
    (("луна",), "moon lunar surface space"),
    (("crispr", "ген", "днк"), "DNA gene editing biotechnology laboratory"),
    (("земля круглая", "атмосфера земли"), "planet earth from space"),
    (("торнадо",), "tornado storm weather"),
    (("квазар",), "quasar deep space galaxy"),
    (("глаз",), "human eye close up science"),
    (("зева",), "tired person yawning sleep"),
    (("нейтронные звёзды", "нейтронные звезды"), "neutron star space astronomy"),
    (("фотосинтез", "листья", "растени"), "green leaves sunlight photosynthesis"),
    (("алмаз",), "diamond crystal geology"),
    (("мрт",), "MRI scanner medical technology"),
    (("сатурн",), "Saturn rings planet space"),
    (("мигрируют",), "bird migration sky"),
    (("cern", "коллайдер"), "particle accelerator collider CERN"),
    (("боль",), "medical pain nervous system"),
    (("солнечная система",), "solar system planets space"),
    (("энтропия",), "thermodynamics physics science"),
    (("эхолокация",), "sonar sound waves science"),
    (("светятся", "биолюминесцен"), "bioluminescence ocean glowing plankton"),
    (("электричество",), "electricity lightning power grid"),
    (("относительности",), "relativity spacetime physics"),
    (("слух",), "human ear sound waves"),
    (("замерзании", "снежинки"), "ice crystals snowflake macro"),
    (("обоняние", "нюх", "запах"), "smell nose aroma science"),
    (("плазма",), "plasma physics glowing science"),
    (("смеёмся", "смеемся"), "people laughing psychology"),
    (("нервная система", "рефлекторная дуга"), "nervous system anatomy neuroscience"),
    (("когнитивные искажения", "интуиция"), "human thinking psychology brain"),
    (("сердце", "кровообращения"), "human heart medical anatomy"),
    (("горы",), "mountain formation geology"),
    (("микробиом",), "microbiome bacteria microscope"),
    (("высоты",), "fear of heights cliff"),
    (("вирус",), "virus microscope medical science"),
    (("фотоэлектрический",), "solar panel light physics"),
    (("земная кора",), "tectonic plates geology"),
    (("теория игр",), "game theory strategy chess"),
    (("ракета",), "rocket launch space"),
    (("экзопланет",), "exoplanet space astronomy"),
    (("фотография",), "camera lens photography"),
    (("ржавеют",), "rusty metal corrosion"),
    (("облака",), "clouds sky weather"),
    (("компьютерный чип", "чип"), "computer chip microprocessor macro"),
    (("гравитационные волны",), "gravitational waves astronomy"),
    (("лазер",), "laser beam optics laboratory"),
    (("регенерировать",), "regeneration biology laboratory"),
    (("нейроморфные",), "neuromorphic computer chip AI"),
    (("музыку",), "music sound waves headphones"),
    (("желудок",), "human digestive system anatomy"),
    (("термоядер",), "fusion reactor plasma science"),
    (("3d-печати", "3d печати", "3д"), "3D printer printing object"),
    (("метеорит",), "meteorite space rock"),
    (("самозванца",), "impostor syndrome psychology work"),
    (("марсе",), "Mars red sky rover"),
    (("пчелин",), "bee colony honeycomb"),
    (("сверхпровод",), "superconductor physics laboratory"),
    (("ядерный реактор",), "nuclear reactor power plant"),
    (("времена года",), "four seasons nature collage"),
    (("международная космическая станция", "мкс"), "International Space Station orbit earth"),
]


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _context_text(topic: str, category: str | None, angle: str | None, keywords: Iterable[str] | None) -> str:
    parts = [topic, category or "", angle or "", " ".join(keywords or ())]
    return " ".join(parts).lower().replace("ё", "е")


def generate_image_query(
    topic: str,
    category: str | None = None,
    angle: str | None = None,
    keywords: Iterable[str] | None = None,
) -> str:
    t = topic.lower()
    normalized = _context_text(topic, category, angle, keywords)

    if _contains_any(normalized, ("выгоран", "стресс", "нагруз", "wellbeing")):
        return "employee wellbeing workload analytics AI office team"
    if _contains_any(normalized, ("фермер", "урож", "поле", "agriculture")):
        return "smart farming AI agriculture drone crop analytics"
    if _contains_any(normalized, ("фейк", "дезинформац", "новост", "fake")):
        return "fact checking newsroom misinformation digital media AI"
    if _contains_any(normalized, ("тренд", "общественное мнение", "социальн")):
        return "social media trend analytics dashboard AI marketing team"
    if _contains_any(normalized, ("поддержк", "оператор", "колл-центр", "call", "чат", "клиент")):
        return "customer support center AI chatbot operator dashboard"
    if _contains_any(normalized, ("ии-агент", "ai-агент", "агент", "личн")):
        return "personal AI assistant productivity dashboard human worker"
    if _contains_any(normalized, ("склад", "логист", "доставк", "посыл")):
        return "warehouse robots packages logistics automation"
    if _contains_any(normalized, ("стартап", "малый бизнес", "магазин", "продаж")):
        return "small business owner laptop AI tools shop customer service"
    if _contains_any(normalized, ("робот", "роботы")):
        return "collaborative robot modern robotics lab people"
    if _contains_any(normalized, ("автоматизац", "офис", "отчет", "письм", "расписан")):
        return "office worker automation dashboard productivity software"
    if _contains_any(normalized, ("цифров", "сервис", "платформ", "приложен")):
        return "digital service platform app interface people"
    if _contains_any(normalized, ("нейросет", "искусственный интеллект", " ии", "ai", "алгоритм")):
        return "artificial intelligence data analytics dashboard human team"

    for keywords, query in _TOPIC_QUERY_RULES:
        if any(kw in t for kw in keywords):
            return query

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

    cleaned_topic = " ".join(
        word for word in topic.replace("ё", "е").split()
        if word.lower().strip(".,:;!?") not in _BANNED_WORDS
    )
    return f"{cleaned_topic} modern science technology cover, people, clear subject, bright editorial photo"

_HEADERS = {"User-Agent": "HochuVseZnatBot/1.0"}
_MAX_PIXABAY_QUERY_CHARS = 95


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4 and token not in _GENERIC_QUERIES
    }


def _score_candidate(candidate: ImageCandidate, query: str) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    description = candidate.description.lower()
    query_tokens = _tokens(query)
    description_tokens = _tokens(description)
    overlap = len(query_tokens & description_tokens)

    if candidate.width >= 1200 and candidate.height >= 700:
        score += 25
        reasons.append("good resolution")
    elif candidate.width >= 1000 and candidate.height >= 600:
        score += 15
        reasons.append("acceptable resolution")
    else:
        score -= 25
        reasons.append("low resolution")

    ratio = candidate.width / candidate.height if candidate.height else 0
    if 1.45 <= ratio <= 2.2:
        score += 20
        reasons.append("landscape cover format")
    elif ratio < 1.2:
        score -= 15
        reasons.append("not cover-friendly")

    if overlap:
        score += min(overlap * 8, 32)
        reasons.append("matches query keywords")

    if any(word in description for word in ("person", "people", "human", "worker", "team", "office")):
        score += 12
        reasons.append("people or workplace")
    if any(word in description for word in ("robot", "automation", "artificial intelligence", "digital", "interface", "technology")):
        score += 14
        reasons.append("technology scene")
    if any(word in description for word in ("dark", "black background", "abstract", "texture", "text", "word", "laptop on desk")):
        score -= 14
        reasons.append("generic or text-heavy risk")
    if description and not overlap:
        score -= 10
        reasons.append("weak metadata match")

    return score, reasons or ["best available candidate"]


def _pick_best(
    candidates: list[ImageCandidate],
    query: str,
    used_urls: Iterable[str] | None = None,
) -> tuple[ImageCandidate | None, str]:
    used = set(used_urls or ())
    fresh_candidates = [candidate for candidate in candidates if candidate.url not in used]
    if not fresh_candidates and candidates:
        return None, "all candidates were recently used"
    if not fresh_candidates:
        return None, "no candidates"
    scored = [(_score_candidate(candidate, query), candidate) for candidate in fresh_candidates]
    scored.sort(key=lambda item: item[0][0], reverse=True)
    (score, reasons), candidate = scored[0]
    return candidate, f"score={score}; {', '.join(reasons[:4])}"


def _ensure_json_response(resp: requests.Response, source: str) -> None:
    content_type_header = resp.headers.get("Content-Type", "")
    content_type = content_type_header.lower() if isinstance(content_type_header, str) else ""
    if "json" not in content_type:
        raise ValueError(f"{source} returned non-JSON response: {content_type or 'unknown content type'}")


def _compact_search_query(query: str, max_chars: int = _MAX_PIXABAY_QUERY_CHARS) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", query)
    words = []
    for word in cleaned.split():
        if len(word) < 3:
            continue
        lowered = word.lower()
        if lowered in {"with", "using", "modern", "bright", "scene", "clear", "cover"}:
            continue
        candidate = " ".join([*words, word])
        if len(candidate) > max_chars:
            break
        words.append(word)
    return " ".join(words) or query[:max_chars]


def _query_variants(query: str) -> list[str]:
    compact = _compact_search_query(query)
    variants = [compact]
    broad = " ".join(compact.split()[:4])
    if broad and broad != compact:
        variants.append(broad)
    if "AI" in query or "artificial intelligence" in query.lower():
        variants.append("artificial intelligence office team")
    return list(dict.fromkeys(variants))


def _pexels(query: str) -> list[ImageCandidate]:
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 15, "orientation": "landscape"},
            headers={**_HEADERS, "Authorization": PEXELS_API_KEY},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        _ensure_json_response(resp, "Pexels")
        photos = resp.json().get("photos", [])
        return [
            ImageCandidate(
                source="Pexels",
                url=item["src"].get("large2x") or item["src"].get("large"),
                width=int(item.get("width") or 0),
                height=int(item.get("height") or 0),
                description=str(item.get("alt") or ""),
            )
            for item in photos
            if item.get("src", {}).get("large") or item.get("src", {}).get("large2x")
        ]
    except Exception as e:
        logger.warning("Pexels error: %s", e)
    return []


def _pixabay(query: str) -> list[ImageCandidate]:
    if not PIXABAY_API_KEY:
        return []
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_API_KEY,
                "q": _compact_search_query(query),
                "image_type": "photo",
                "orientation": "horizontal",
                "safesearch": "true",
                "per_page": 20,
                "min_width": 1000,
                "min_height": 600,
            },
            headers=_HEADERS,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        _ensure_json_response(resp, "Pixabay")
        hits = resp.json().get("hits", [])
        return [
            ImageCandidate(
                source="Pixabay",
                url=item.get("largeImageURL") or item.get("webformatURL"),
                width=int(item.get("imageWidth") or item.get("webformatWidth") or 0),
                height=int(item.get("imageHeight") or item.get("webformatHeight") or 0),
                description=str(item.get("tags") or ""),
            )
            for item in hits
            if item.get("largeImageURL") or item.get("webformatURL")
        ]
    except Exception as e:
        logger.warning("Pixabay error: %s", e)
    return []


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=_HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "").lower()
    if "image" not in content_type:
        raise ValueError(f"Downloaded file is not an image: {content_type or 'unknown content type'}")
    if len(resp.content) < 20_000:
        raise ValueError("Downloaded image is unexpectedly small")
    return resp.content


async def fetch_image_result(query: str, used_urls: Iterable[str] | None = None) -> Optional[ImageResult]:
    logger.info("Image search query: %s", query)
    last_reason = "no candidates"
    for search_query in _query_variants(query):
        pexels_candidates, pixabay_candidates = await asyncio.gather(
            asyncio.to_thread(_pexels, search_query),
            asyncio.to_thread(_pixabay, search_query),
        )
        candidate, reason = _pick_best([*pexels_candidates, *pixabay_candidates], search_query, used_urls)
        last_reason = reason
        if not candidate:
            logger.warning("No image found for query variant '%s': %s", search_query, reason)
            continue
        logger.info(
            "Selected image: source=%s url=%s query=%s reason=%s",
            candidate.source,
            candidate.url,
            search_query,
            reason,
        )
        try:
            image_bytes = await asyncio.to_thread(_download, candidate.url)
            return ImageResult(
                bytes=image_bytes,
                source=candidate.source,
                url=candidate.url,
                query=search_query,
            )
        except Exception as e:
            logger.warning("Image download failed: %s", e)

    logger.warning("No image found for query: %s (%s)", query, last_reason)
    return None


async def fetch_image(query: str) -> Optional[bytes]:
    result = await fetch_image_result(query)
    return result.bytes if result else None
