from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from app.config import OPENROUTER_API_KEY
from app.marketcode.config import MarketCodeSettings
from app.marketcode.content_plan import ContentPlanEntry

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "marketcode_seo_prompt.txt"
_MIN_WORDS = 300
_MAX_WORDS = 500
_MIN_BODY_WORDS = 275
_MAX_BODY_WORDS = 440
_MAX_ARTICLE_CHARS = 3800
_MAX_GENERATION_ATTEMPTS = 3
_BANNED_CTA = "купить цифровые товары"
_SITE_URL = "https://www.marketcode.pro"
_RISKY_GUIDANCE = (
    "общедоступные адреса",
    "адрес публичной",
    "чужой адрес",
    "чужой номер",
    "реальные или правдоподобные данные",
    "используйте vpn",
    "использовать vpn",
    "рассмотрите возможность использования легальных сервисов",
    "могли бы предоставить свои данные",
)
_SAFE_RISK_NEGATIONS = (
    "не используйте vpn",
    "не использовать vpn",
    "не применяйте vpn",
)
_FORBIDDEN_PAYMENT_GUIDANCE = (
    "киви",
    "qiwi",
    "webmoney",
    "вебмани",
    "яндекс.деньги",
    "яндекс деньги",
    "yoomoney",
    "юmoney",
    "оплатите через банк",
    "оплата через банк",
    "банковский перевод",
    "переведите деньги",
    "введите данные карты",
    "укажите реквизиты",
    "номер банковской карты",
    "cvv",
    "cvc",
    "сбербанк",
    "т-банк",
    "тинькофф",
    "альфа-банк",
    "газпромбанк",
    "райффайзенбанк",
)


@dataclass(frozen=True)
class GeneratedArticle:
    title: str
    body: str
    word_count: int
    model: str

    @property
    def full_text(self) -> str:
        return f"{self.title}\n\n{self.body}"


_CTA_BY_CATEGORY = {
    "Apple ID / App Store": (
        "Нужен Apple ID другого региона, Apple Gift Card или пополнение App Store?\n"
        "В MarketCode Pro доступны решения для Apple ID разных регионов:"
    ),
    "Steam": (
        "Нужно пополнить Steam или приобрести игровые товары?\n"
        "В MarketCode Pro доступны Steam-пополнения и цифровые решения для игроков:"
    ),
    "Telegram": (
        "Нужны Telegram Stars или Premium?\n"
        "В MarketCode Pro доступны цифровые сервисы для Telegram:"
    ),
    "Gift Cards": (
        "Выбираете подарочную карту или хотите безопасно активировать цифровой код?\n"
        "В MarketCode Pro доступны подарочные карты и цифровые коды для разных регионов:"
    ),
    "Игровые товары": (
        "Нужно пополнить игровой баланс или получить внутриигровую валюту?\n"
        "В MarketCode Pro доступны пополнения и цифровые решения для популярных игр:"
    ),
}


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-–][A-Za-zА-Яа-яЁё0-9]+)*", text))


def _risky_guidance(text: str) -> str | None:
    normalized = text.lower()
    for safe_phrase in _SAFE_RISK_NEGATIONS:
        normalized = normalized.replace(safe_phrase, "")
    return next((phrase for phrase in _RISKY_GUIDANCE if phrase in normalized), None)


def _cta(category: str) -> str:
    try:
        lead = _CTA_BY_CATEGORY[category]
    except KeyError as exc:
        raise ValueError(f"Unsupported MarketCode category: {category}") from exc
    return f"{lead}\n\n{_SITE_URL}"


def _load_prompt(entry: ContentPlanEntry) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        topic=entry.topic,
        category=entry.category,
        keywords=", ".join(entry.keywords),
        goal=entry.goal,
    )


def _call_api(prompt: str, settings: MarketCodeSettings) -> tuple[str, str]:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    last_error: Exception | None = None
    for model in dict.fromkeys((settings.model, settings.fallback_model)):
        if not model:
            continue
        try:
            response = requests.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": _SITE_URL,
                    "X-OpenRouter-Title": "MarketCode Pro SEO Content",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1600,
                    "temperature": 0.4,
                },
                timeout=180,
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ValueError("OpenRouter stopped MarketCode article at the token limit")
            content = choice["message"]["content"].strip()
            if not content:
                raise ValueError("OpenRouter returned empty MarketCode article")
            return content, model
        except Exception as exc:
            last_error = exc
            logger.warning("MarketCode model %s failed: %s", model, exc)
    raise RuntimeError("All MarketCode OpenRouter models failed") from last_error


def _refinement_prompt(entry: ContentPlanEntry, body: str, words: int, chars: int) -> str:
    return f"""
Переработай статью ниже. Сейчас в ней {words} слов, а полный материал с заголовком и CTA занимает примерно {chars} символов.
Основная часть должна содержать строго {_MIN_BODY_WORDS}–{_MAX_BODY_WORDS} слов, а готовая публикация — не более {_MAX_ARTICLE_CHARS} символов.
Сохрани тему «{entry.topic}», полезные факты, пошаговую инструкцию, советы, короткий FAQ и вывод.
Удали повторы и второстепенные подробности. Оба ограничения по словам и символам жёсткие.
Не добавляй рекламу, ссылки, CTA и комментарии о процессе редактирования.
Не добавляй названия банков, платёжных систем, банковские инструкции или придуманные способы оплаты.
Если без упоминания оплаты нельзя сохранить смысл, используй только нейтральную формулировку: «Оплата производится удобным способом на сайте MarketCode Pro.»
Верни только готовый текст статьи без отдельного заголовка H1.

{body}
""".strip()


def _quality_review_prompt(entry: ContentPlanEntry, body: str) -> str:
    return f"""
Ты — выпускающий редактор экспертного материала про цифровые сервисы.
Перепиши статью по теме «{entry.topic}», сохранив полезную структуру и объём {_MIN_BODY_WORDS}–{_MAX_BODY_WORDS} слов.

Обязательная проверка качества:
- не предлагай VPN, вымышленные, публичные, чужие адреса или номера телефонов;
- не предлагай сервисы виртуальных адресов или номеров и передачу данных знакомых или родственников;
- не представляй региональный аккаунт как способ обхода ограничений;
- используй только официальные и законные сценарии: переезд, фактическое проживание и реальные данные пользователя, без описания способов оплаты;
- не утверждай, что покупки или подписки обязательно исчезнут при смене аккаунта или региона;
- не выдумывай пункты меню, сроки, цены и гарантии отсутствия блокировки;
- запрещено упоминать Киви, Qiwi, WebMoney, Вебмани, Яндекс.Деньги и любые другие устаревшие или конкретные платёжные системы;
- не называй банки, банковские продукты и реквизиты, не давай банковских инструкций и не придумывай способы оплаты;
- если оплата важна для смысла, используй только одну из нейтральных формулировок: «Оплата производится удобным способом на сайте MarketCode Pro.» или «После оформления заказа пользователь получает цифровой товар через сервис MarketCode Pro.»;
- если правила или интерфейс могут измениться, отправляй читателя к актуальной официальной справке сервиса;
- убери рекламные формулировки, ссылки и CTA: они добавляются программно;
- не повторяй заголовок в начале текста.

Верни только исправленную основную часть статьи.

{body}
""".strip()


def _normalize_body(text: str, title: str) -> str:
    body = text.strip()
    body = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", body, flags=re.IGNORECASE)
    body = re.sub(rf"^#\s*{re.escape(title)}\s*\n+", "", body, flags=re.IGNORECASE)
    lines = body.splitlines()
    if lines and lines[0].strip().lstrip("#").strip().casefold() == title.strip().casefold():
        body = "\n".join(lines[1:]).lstrip()
    return body.strip()


def _generate_sync(entry: ContentPlanEntry, settings: MarketCodeSettings) -> GeneratedArticle:
    prompt = _load_prompt(entry)
    body, model = _call_api(prompt, settings)
    body = _normalize_body(body, entry.topic)
    body, model = _call_api(_quality_review_prompt(entry, body), settings)
    body = _normalize_body(body, entry.topic)

    for _ in range(_MAX_GENERATION_ATTEMPTS):
        words = _word_count(body)
        full_body = f"{body}\n\n{_cta(entry.category)}"
        full_text = f"{entry.topic}\n\n{full_body}"
        if _MIN_BODY_WORDS <= words <= _MAX_BODY_WORDS and len(full_text) <= _MAX_ARTICLE_CHARS:
            break
        body, model = _call_api(
            _refinement_prompt(entry, body, words, len(full_text)),
            settings,
        )
        body = _normalize_body(body, entry.topic)

    words = _word_count(body)
    if not _MIN_BODY_WORDS <= words <= _MAX_BODY_WORDS:
        raise ValueError(
            f"MarketCode article body has {words} words; expected {_MIN_BODY_WORDS}-{_MAX_BODY_WORDS}"
        )
    if _BANNED_CTA in body.lower():
        raise ValueError("MarketCode article contains the forbidden generic CTA")
    risky_phrase = _risky_guidance(body)
    if risky_phrase:
        raise ValueError(f"MarketCode article contains risky guidance: {risky_phrase}")
    forbidden_payment = next(
        (phrase for phrase in _FORBIDDEN_PAYMENT_GUIDANCE if phrase in body.lower()),
        None,
    )
    if forbidden_payment:
        raise ValueError(
            f"MarketCode article contains forbidden payment guidance: {forbidden_payment}"
        )

    full_body = f"{body}\n\n{_cta(entry.category)}"
    full_text = f"{entry.topic}\n\n{full_body}"
    full_word_count = _word_count(full_text)
    if not _MIN_WORDS <= full_word_count <= _MAX_WORDS:
        raise ValueError(
            f"MarketCode article has {full_word_count} words after title and CTA; expected {_MIN_WORDS}-{_MAX_WORDS}"
        )
    if len(full_text) > _MAX_ARTICLE_CHARS:
        raise ValueError(
            f"MarketCode article has {len(full_text)} characters; maximum is {_MAX_ARTICLE_CHARS}"
        )
    return GeneratedArticle(
        title=entry.topic,
        body=full_body,
        word_count=full_word_count,
        model=model,
    )


async def generate_article(entry: ContentPlanEntry, settings: MarketCodeSettings) -> GeneratedArticle:
    logger.info("Generating MarketCode day %d: %s", entry.day, entry.topic)
    return await asyncio.to_thread(_generate_sync, entry, settings)
