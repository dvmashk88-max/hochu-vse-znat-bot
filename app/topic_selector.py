import logging
import random
import re
from dataclasses import dataclass
from app.db import get_published_topics, get_recent_published_topics
from app.generator import generate_topic_candidate

logger = logging.getLogger(__name__)

RECENT_TOPICS_LIMIT = 80
RECENT_TOPIC_DAYS = 30
GENERATED_TOPIC_ATTEMPTS = 6


@dataclass(frozen=True)
class TopicSelection:
    title: str
    category: str | None = None
    angle: str | None = None
    keywords: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.title


TOPICS = [
    "Почему небо голубое",
    "Как работают чёрные дыры",
    "Что такое квантовая запутанность",
    "Как мозг формирует воспоминания",
    "Почему мы видим сны",
    "Как работает иммунная система",
    "Что такое тёмная материя",
    "Как возникла жизнь на Земле",
    "Почему вымерли динозавры",
    "Как работает интернет",
    "Что такое нейронные сети",
    "Почему люди стареют",
    "Как устроен атом",
    "Что такое антиматерия",
    "Как работает GPS",
    "Почему океан солёный",
    "Как появилась Луна",
    "Что такое CRISPR и редактирование генов",
    "Как работает вакцина",
    "Почему земля круглая",
    "Как формируются торнадо",
    "Что такое квазары",
    "Как работает человеческий глаз",
    "Почему мы зеваем",
    "Как устроена ДНК",
    "Что такое нейтронные звёзды",
    "Как работает фотосинтез",
    "Почему листья меняют цвет осенью",
    "Как образуются алмазы",
    "Что такое суперпозиция в квантовой физике",
    "Как работает МРТ",
    "Почему Сатурн имеет кольца",
    "Как мигрируют птицы",
    "Что такое синаптическая пластичность",
    "Как работает CERN и коллайдер",
    "Почему мы чувствуем боль",
    "Как устроена Солнечная система",
    "Что такое энтропия",
    "Как работает эхолокация у летучих мышей",
    "Почему некоторые животные светятся",
    "Как работает электричество",
    "Что такое теория относительности",
    "Как устроен человеческий слух",
    "Почему вода расширяется при замерзании",
    "Как работает нюх у собак",
    "Что такое плазма",
    "Как возникают цунами",
    "Почему мы смеёмся",
    "Как устроена нервная система",
    "Что такое когнитивные искажения",
    "Как работает сердце",
    "Почему некоторые вещества светятся в темноте",
    "Как формируются горы",
    "Что такое микробиом кишечника",
    "Как работает человеческая память",
    "Почему мы боимся высоты",
    "Как устроен вирус",
    "Что такое фотоэлектрический эффект",
    "Как работают антибиотики",
    "Почему земная кора движется",
    "Как образуются снежинки",
    "Что такое теория игр",
    "Как работает обоняние",
    "Почему мы привыкаем к запахам",
    "Как устроена ракета",
    "Что такое экзопланеты",
    "Как работает фотография",
    "Почему некоторые металлы ржавеют",
    "Как формируются облака",
    "Что такое синтетическая биология",
    "Как работает мозжечок",
    "Почему мы дрожим от холода",
    "Как устроен компьютерный чип",
    "Что такое гравитационные волны",
    "Как работает лазер",
    "Почему некоторые животные умеют регенерировать",
    "Как устроена атмосфера Земли",
    "Что такое нейроморфные компьютеры",
    "Как работает слух у рыб",
    "Почему мы любим музыку",
    "Как устроен желудок",
    "Что такое термоядерная реакция",
    "Как работает принтер на 3D-печати",
    "Почему некоторые растения плотоядные",
    "Как образуются метеориты",
    "Что такое синдром самозванца",
    "Как работает рефлекторная дуга",
    "Почему мы зеваем когда другие зевают",
    "Как устроена чёрная дыра внутри",
    "Что такое фракталы в природе",
    "Как работает обезболивание в медицине",
    "Почему небо на Марсе красное",
    "Как устроена пчелиная колония",
    "Что такое сверхпроводимость",
    "Как работает система кровообращения",
    "Почему мы плачем",
    "Как устроен ядерный реактор",
    "Что такое биолюминесценция океана",
    "Как работает интуиция",
    "Почему существуют времена года",
    "Как устроена Международная космическая станция",
    "Почему старые книги пахнут ванилью",
    "Как древние люди делали клей из берёзовой коры",
    "Почему римский бетон крепнет в морской воде",
    "Как шум меняет вкус еды",
    "Почему стекло кажется жидким, хотя им не является",
    "Как муравьи находят короткие маршруты",
    "Зачем средневековые замки строили с винтовыми лестницами",
    "Почему самолёты оставляют белые следы в небе",
    "Как работают музыкальные шкатулки",
    "Почему осьминоги думают не только головой",
    "Как археологи читают древние надписи без словаря",
    "Почему некоторые камни умеют плавать",
    "Как растения понимают, где верх и низ",
    "Почему у перца чили появился острый вкус",
    "Как древние мореплаватели ориентировались без GPS",
    "Почему бетон трескается и как его лечат бактериями",
    "Как работает невидимая защита банковской карты",
    "Почему в пустыне ночью становится холодно",
    "Как ледяные керны рассказывают о древнем климате",
    "Почему зеркало меняет лево и право, но не верх и низ",
    "Как голубой пигмент стал редкостью в истории искусства",
    "Почему некоторые языки обходятся без слов для чисел",
    "Как работают шумоподавляющие наушники",
    "Почему чай темнеет, если в него добавить лимон",
    "Как древние города справлялись с канализацией",
    "Почему пыль дома в основном не с улицы",
    "Как работает эффект плацебо без магии",
    "Почему запахи так быстро возвращают воспоминания",
    "Как учёные узнают возраст деревянных построек",
    "Почему морская вода пенится",
    "Как работает застёжка-липучка",
    "Почему бумага желтеет со временем",
    "Как насекомые ходят по потолку",
    "Почему у некоторых людей абсолютный слух",
    "Как древние мастера делали стойкие красители",
    "Почему молния иногда бывает шаровой",
    "Как работает термос",
    "Почему некоторые здания поют на ветру",
    "Как образуются подземные реки",
    "Почему сыр пахнет сильнее, чем молоко",
    "Как работает археологическая радиоуглеродная датировка",
    "Почему кожа морщится в воде",
    "Как городские деревья охлаждают улицы",
    "Почему песок на пляжах бывает разного цвета",
    "Как работают автоматические двери",
    "Почему старые фотографии выцветают",
    "Как древние люди добывали огонь трением",
    "Почему у часов с маятником такой ровный ход",
    "Как работают датчики дыма",
    "Почему разные металлы звучат по-разному",
]

STRATEGIC_TOPICS = [
    "Как ИИ-агенты превращаются в личных сотрудников для обычных людей",
    "Почему малый бизнес начинает нанимать ИИ вместо ночной поддержки",
    "Как нейросети помогают врачам замечать детали, которые легко пропустить",
    "Почему роботы на складах меняют доставку быстрее, чем кажется",
    "Как ИИ составляет расписания, письма и отчёты за офисных сотрудников",
    "Почему голосовые ассистенты становятся интерфейсом к цифровым сервисам",
    "Как стартапы используют ИИ, чтобы запускать продукт без большой команды",
    "Почему автоматизация больше похожа на второго пилота, чем на замену человека",
    "Как ИИ помогает продавцам отвечать клиентам быстрее и точнее",
    "Почему персональные AI-помощники могут стать новой привычкой работы",
    "Как роботы учатся работать рядом с людьми без заводских клеток",
    "Почему цифровые двойники городов помогают экономить время и деньги",
    "Как ИИ ищет ошибки в коде до того, как продукт увидит пользователь",
    "Почему генеративный поиск меняет привычку открывать десятки вкладок",
    "Как нейросети превращают черновики в презентации и коммерческие предложения",
    "Почему компании строят внутренние базы знаний с ИИ-поиском",
    "Как ИИ помогает находить мошенничество в платежах и заказах",
    "Почему автоматические склады стали лабораторией будущей логистики",
    "Как роботы-доставщики учатся понимать тротуары и людей",
    "Почему ИИ в колл-центрах всё чаще решает простые вопросы без оператора",
    "Как нейросети помогают дизайнерам быстро проверять десятки идей",
    "Почему AI-агенты скоро будут вести рутинные переговоры с сервисами",
    "Как ИИ помогает фермерам видеть проблемы на поле раньше человека",
    "Почему умные камеры становятся частью городской инфраструктуры",
    "Как космические снимки и ИИ помогают следить за пожарами и урожаем",
    "Почему телеграф XIX века похож на первый интернет для бизнеса",
    "Как средневековые рынки предсказали современные цифровые платформы",
    "Почему фабричные конвейеры помогают понять офисную автоматизацию",
    "Как исследования внимания объясняют усталость от уведомлений",
    "Почему привычка доверять навигатору меняет наше чувство города",
]

_STOPWORDS = {
    "а", "без", "бы", "в", "во", "вот", "для", "до", "его", "ее", "её", "если",
    "и", "из", "или", "как", "к", "ко", "на", "но", "о", "об", "от", "по",
    "почему", "при", "про", "с", "со", "так", "то", "у", "что", "это",
    "этот", "эта", "эти", "же", "ли", "не", "чем", "откуда",
}

_POPULAR_TOPIC_FRAGMENTS = (
    "черные дыр",
    "черная дыр",
    "черн дыр",
    "чёрн дыр",
    "динозавр",
    "небо голуб",
    "квантов",
    "днк",
    "gps",
    "иммун",
    "вакцин",
    "марс",
    "луна",
    "атом",
)

_MODERN_RELEVANCE_MARKERS = (
    "ии", "ai", "нейросет", "агент", "робот", "автоматизац", "цифров",
    "платформ", "интернет", "сервис", "стартап", "бизнес", "технолог",
    "будущ", "данн", "алгоритм", "приложен", "онлайн",
)

_HISTORY_MARKERS = (
    "древн", "средневек", "римск", "xix", "истори", "телеграф", "замк",
    "мореплавател", "археолог", "прошл",
)

_ALLOWED_CATEGORIES = (
    "digital_services", "business_ai", "future_tech", "modern_history",
    "automation", "robots", "startup", "science", "psychology", "space", "ai",
)


def _normalize_topic(topic: str) -> str:
    topic = topic.lower().replace("ё", "е")
    topic = re.sub(r"[^a-zа-я0-9\s-]", " ", topic)
    return re.sub(r"\s+", " ", topic).strip()


def _stem_token(token: str) -> str:
    for ending in (
        "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
        "ых", "их", "ая", "яя", "ое", "ее", "ые", "ие", "ый", "ий",
        "ой", "ам", "ям", "ах", "ях", "ом", "ем", "ою", "ею", "ью",
        "ия", "ья", "и", "ы", "а", "я", "у", "ю", "е", "о",
    ):
        if len(token) - len(ending) >= 4 and token.endswith(ending):
            return token[: -len(ending)]
    return token


def _topic_tokens(topic: str) -> set[str]:
    tokens = set()
    for token in _normalize_topic(topic).split():
        token = token.strip("-")
        if len(token) < 4 or token in _STOPWORDS:
            continue
        tokens.add(_stem_token(token))
    return tokens


def _similarity(left: str, right: str) -> float:
    left_norm = _normalize_topic(left)
    right_norm = _normalize_topic(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.85

    left_tokens = _topic_tokens(left_norm)
    right_tokens = _topic_tokens(right_norm)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _is_too_similar(topic: str, recent_topics: list[str]) -> tuple[bool, str | None]:
    for published_topic in recent_topics:
        if _similarity(topic, published_topic) >= 0.42:
            return True, published_topic
    return False, None


def _sanitize_generated_title(value: object) -> str:
    title = str(value or "").strip()
    title = title.strip("\"'«»“”")
    title = re.sub(r"\s+", " ", title)
    return title[:120]


def _sanitize_keywords(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    keywords = []
    for item in value:
        keyword = str(item or "").strip()
        if keyword:
            keywords.append(keyword[:40])
    return tuple(keywords[:5])


def _sanitize_category(value: object) -> str | None:
    raw = str(value or "").strip().lower()
    for category in _ALLOWED_CATEGORIES:
        if category in raw:
            return category
    return raw[:40] or None


def _selection_from_candidate(candidate: dict) -> TopicSelection:
    return TopicSelection(
        title=_sanitize_generated_title(candidate.get("title")),
        category=_sanitize_category(candidate.get("category")),
        angle=str(candidate.get("angle") or "").strip()[:160] or None,
        keywords=_sanitize_keywords(candidate.get("keywords")),
    )


def _is_acceptable_generated_topic(title: str, recent_topics: list[str]) -> tuple[bool, str]:
    if not title:
        return False, "empty title"
    if len(title) < 20:
        return False, "too short"
    if len(title) > 100:
        return False, "too long"
    normalized = _normalize_topic(title)
    if any(fragment in normalized for fragment in _POPULAR_TOPIC_FRAGMENTS):
        return False, "popular topic fragment"
    if any(marker in normalized for marker in _HISTORY_MARKERS):
        if not any(marker in normalized for marker in _MODERN_RELEVANCE_MARKERS):
            return False, "history topic without modern relevance"
    similar, published_topic = _is_too_similar(title, recent_topics)
    if similar:
        return False, f"similar to '{published_topic}'"
    return True, ""


async def _pick_generated_topic() -> TopicSelection | None:
    recent_topics = get_recent_published_topics(RECENT_TOPICS_LIMIT, days=RECENT_TOPIC_DAYS)
    for attempt in range(1, GENERATED_TOPIC_ATTEMPTS + 1):
        try:
            candidate = await generate_topic_candidate(recent_topics, attempt)
        except Exception as e:
            logger.warning("Failed to generate topic candidate: %s", e)
            return None

        selection = _selection_from_candidate(candidate)
        ok, reason = _is_acceptable_generated_topic(selection.title, recent_topics)
        if ok:
            logger.info("Selected generated topic: %s", selection.title)
            return selection

        logger.info("Rejected generated topic '%s': %s", selection.title, reason)
        recent_topics = [selection.title, *recent_topics]

    return None


async def pick_next_topic() -> TopicSelection:
    generated_topic = await _pick_generated_topic()
    if generated_topic:
        return generated_topic

    published = set(get_published_topics())
    recent_topics = get_recent_published_topics(RECENT_TOPICS_LIMIT, days=RECENT_TOPIC_DAYS)
    available = [
        t for t in STRATEGIC_TOPICS
        if t not in published and not _is_too_similar(t, recent_topics)[0]
    ]
    if not available:
        available = [
            t for t in TOPICS
            if t not in published and not _is_too_similar(t, recent_topics)[0]
        ]
    if not available:
        available = [t for t in STRATEGIC_TOPICS if t not in published] or STRATEGIC_TOPICS
    logger.info("Selected fallback topic from static pool")
    return TopicSelection(title=random.choice(available))
