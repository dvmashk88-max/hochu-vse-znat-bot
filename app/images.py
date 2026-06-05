import asyncio
import logging
import urllib3
import requests
import random
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


def generate_image_query(topic: str) -> str:
    t = topic.lower()

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
    return f"{cleaned_topic} science educational illustration"

_HEADERS = {"User-Agent": "HochuVseZnatBot/1.0"}


def _pick_url(urls: list[str]) -> Optional[str]:
    if not urls:
        return None
    return random.choice(urls)


def _unsplash(query: str) -> Optional[str]:
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 10, "orientation": "landscape"},
            headers={**_HEADERS, "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        urls = [item["urls"]["regular"] for item in results if item.get("urls", {}).get("regular")]
        return _pick_url(urls)
    except Exception as e:
        logger.warning("Unsplash error: %s", e)
    return None


def _pexels(query: str) -> Optional[str]:
    if not PEXELS_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 10, "orientation": "landscape"},
            headers={**_HEADERS, "Authorization": PEXELS_API_KEY},
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        urls = [item["src"]["large"] for item in photos if item.get("src", {}).get("large")]
        return _pick_url(urls)
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
