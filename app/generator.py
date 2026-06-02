import asyncio
import logging
import requests
from pathlib import Path
from app.config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/post_prompt.txt")
_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "openai/gpt-4o-mini"


def _load_prompt(topic: str) -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").format(topic=topic)


def _call_api(prompt: str) -> str:
    response = requests.post(
        _API_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://t.me/hochu_vse_znat",
        },
        json={
            "model": _MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1200,
            "temperature": 0.8,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


async def generate_post(topic: str) -> str:
    prompt = _load_prompt(topic)
    logger.info("Generating post for topic: %s", topic)
    return await asyncio.to_thread(_call_api, prompt)
