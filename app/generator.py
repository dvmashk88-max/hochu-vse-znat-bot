import asyncio
import json
import logging
import re
import requests
from pathlib import Path
from app.config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/post_prompt.txt")
_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_PRIMARY_MODEL = "openai/gpt-4o-mini"
_FREE_MODELS = (
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "openrouter/free",
)
_MODEL_CASCADE = (_PRIMARY_MODEL, *_FREE_MODELS)
_TOPIC_CANDIDATE_MAX_TOKENS = 350
_RECENT_TOPICS_LIMIT = 50
_MIN_POST_CHARS = 800
_MAX_POST_CHARS = 1200
_POST_LENGTH_REFINEMENT_ATTEMPTS = 2


def _load_prompt(topic: str) -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").format(topic=topic)


def _ensure_model_cascade(models: tuple[str, ...]) -> None:
    if not models or models[0] != _PRIMARY_MODEL:
        raise ValueError(f"The primary OpenRouter model must be first: {_PRIMARY_MODEL}")

    paid_models = [
        model for model in models[1:]
        if not (model.endswith(":free") or model == "openrouter/free")
    ]
    if paid_models:
        raise ValueError(f"Fallback OpenRouter models must be free: {paid_models}")


def _call_api(prompt: str, *, max_tokens: int = 1200, temperature: float = 0.8) -> str:
    _ensure_model_cascade(_MODEL_CASCADE)
    last_error: Exception | None = None

    for model in _MODEL_CASCADE:
        try:
            response = requests.post(
                _API_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://t.me/hochu_vse_znat",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=60,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            if content:
                return content
            raise ValueError("OpenRouter returned empty content")
        except Exception as e:
            last_error = e
            logger.warning("OpenRouter model failed, trying next fallback: %s", e)

    raise RuntimeError("All OpenRouter models failed") from last_error


def _post_length_prompt(topic: str, text: str) -> str:
    return f"""
Сократи или дополни пост строго до {_MIN_POST_CHARS}–{_MAX_POST_CHARS} символов.
Сохрани тему, факты, живой стиль, заголовок и 3–5 хэштегов.
Не добавляй пояснений вне поста.

Тема: {topic}

Текущий текст:
{text}
""".strip()


def _hard_trim_post(text: str) -> str:
    if len(text) <= _MAX_POST_CHARS:
        return text

    hashtags = re.findall(r"#[A-Za-zА-Яа-яЁё0-9_]+", text)
    suffix = ""
    if hashtags:
        suffix = "\n\n" + " ".join(dict.fromkeys(hashtags[:5]))

    room = _MAX_POST_CHARS - len(suffix)
    if room < _MIN_POST_CHARS:
        suffix = ""
        room = _MAX_POST_CHARS

    trimmed = text[:room].rstrip()
    sentence_end = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
    if sentence_end >= _MIN_POST_CHARS:
        trimmed = trimmed[:sentence_end + 1].rstrip()

    return (trimmed + suffix).strip()


def _fit_post_length(topic: str, text: str) -> str:
    fitted = text.strip()
    for attempt in range(1, _POST_LENGTH_REFINEMENT_ATTEMPTS + 1):
        if _MIN_POST_CHARS <= len(fitted) <= _MAX_POST_CHARS:
            return fitted

        logger.info(
            "Refining post length for '%s': %d chars, attempt %d",
            topic,
            len(fitted),
            attempt,
        )
        fitted = _call_api(
            _post_length_prompt(topic, fitted),
            max_tokens=650,
            temperature=0.5,
        ).strip()

    if len(fitted) > _MAX_POST_CHARS:
        logger.info("Hard-trimming post for '%s': %d chars", topic, len(fitted))
        return _hard_trim_post(fitted)

    return fitted


def _extract_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def _format_recent_topics(recent_topics: list[str]) -> str:
    if not recent_topics:
        return "Пока нет опубликованных тем."
    selected = recent_topics[:_RECENT_TOPICS_LIMIT]
    return "\n".join(f"- {topic}" for topic in selected)


def _topic_prompt(recent_topics: list[str], attempt: int) -> str:
    return f"""
Ты — редактор канала «Хочу всё знать».
Придумай одну новую тему для короткой образовательной статьи.

Нужна не статья, а только тема-кандидат.

Требования к теме:
- тема должна быть уникальной и малоизвестной;
- подойдут наука, история, техника, природа, психология, археология, космос, культура или повседневная жизнь;
- не используй избитые научпоп-темы: чёрные дыры, динозавры, нейросети, почему небо голубое, GPS, ДНК, атомы, квантовая запутанность, иммунитет, вакцины, Марс, Луна;
- не повторяй смысл, объект изучения и объясняемый механизм последних публикаций;
- тема должна быть понятной широкой аудитории и годиться для поста на 800–1200 символов;
- формулируй конкретно: не "Как работает память", а более узкий и неожиданный ракурс.

Последние публикации:
{_format_recent_topics(recent_topics)}

Попытка: {attempt}

Ответь строго JSON без Markdown:
{{
  "title": "короткая русская тема",
  "category": "science|history|technology|nature|psychology|archaeology|space|culture|everyday",
  "angle": "чем именно тема отличается от обычного научпопа",
  "keywords": ["ключевое слово 1", "ключевое слово 2", "ключевое слово 3"]
}}
""".strip()


def _generate_topic_candidate_sync(recent_topics: list[str], attempt: int) -> dict:
    text = _call_api(
        _topic_prompt(recent_topics, attempt),
        max_tokens=_TOPIC_CANDIDATE_MAX_TOKENS,
        temperature=1.0,
    )
    data = _extract_json_object(text)
    if not isinstance(data, dict):
        raise ValueError("Topic candidate response is not a JSON object")
    return data


async def generate_post(topic: str) -> str:
    prompt = _load_prompt(topic)
    logger.info("Generating post for topic: %s", topic)
    text = await asyncio.to_thread(_call_api, prompt)
    return await asyncio.to_thread(_fit_post_length, topic, text)


async def generate_topic_candidate(recent_topics: list[str], attempt: int = 1) -> dict:
    logger.info("Generating topic candidate, attempt %d", attempt)
    return await asyncio.to_thread(_generate_topic_candidate_sync, recent_topics, attempt)
