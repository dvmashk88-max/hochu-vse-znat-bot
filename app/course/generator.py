from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import requests

from app.config import COURSE_AI_FALLBACK_MODEL, COURSE_AI_MODEL, OPENROUTER_API_KEY
from app.course.models import CourseDay, CoursePart, GeneratedLesson, PartType, RetrievedSource
from app.course.quality import LessonQualityError, validate_parts

logger = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "course_lesson_prompt.txt"
_MAX_ATTEMPTS = 3


class CourseGenerationError(RuntimeError):
    pass


class CourseAIClient:
    def __init__(self, model: str = COURSE_AI_MODEL, fallback_model: str = COURSE_AI_FALLBACK_MODEL):
        self.models = tuple(dict.fromkeys(item for item in (model, fallback_model) if item))

    def complete(self, prompt: str) -> tuple[str, str]:
        if not OPENROUTER_API_KEY:
            raise CourseGenerationError("OPENROUTER_API_KEY is not set")
        last_error: Exception | None = None
        for model in self.models:
            try:
                response = requests.post(
                    _API_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://t.me/hochu_vse_znat",
                        "X-OpenRouter-Title": "Хочу всё знать — ИИ",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2400,
                        "temperature": 0.35,
                    },
                    timeout=180,
                )
                response.raise_for_status()
                choice = response.json()["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ValueError("Course lesson was truncated at token limit")
                content = choice["message"]["content"].strip()
                if not content:
                    raise ValueError("OpenRouter returned empty course lesson")
                return content, model
            except Exception as exc:
                last_error = exc
                logger.warning("Course model %s failed: %s", model, exc)
        raise CourseGenerationError("All Course AI models failed") from last_error


def _source_context(sources: tuple[RetrievedSource, ...]) -> str:
    return "\n\n".join(
        f"ИСТОЧНИК: {item.source.title}\nURL: {item.source.url}\nМАТЕРИАЛ:\n{item.text}"
        for item in sources
    )


def _prompt(lesson: CourseDay, sources: tuple[RetrievedSource, ...], feedback: str = "",
            previous_reinforce_texts: tuple[str, ...] = ()) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        season=lesson.season_title,
        day_context=(
            f"Курс: {lesson.course_title}\nУрок: {lesson.lesson_number} из {lesson.lesson_count}"
            if lesson.day_type == "lesson"
            else f"Тип дня: {lesson.cover_label}\nЭто отдельный специальный день, не дополнительный урок курса."
        ),
        date=lesson.date.isoformat(),
        topic=lesson.topic,
        learning_goal=lesson.learning_goal,
        explain_objective=lesson.explain_objective,
        try_objective=lesson.try_objective,
        reinforce_objective=lesson.reinforce_objective,
        source_context=_source_context(sources),
        previous_ctas="\n".join(previous_reinforce_texts) or "Нет предыдущих частей.",
        feedback=feedback or "Нет: это первая версия.",
    )


def _extract_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        return json.loads(cleaned[start:end + 1])


def _parts(data: dict) -> tuple[CoursePart, ...]:
    return tuple(
        CoursePart(part_type, part_type.public_name, str(data.get(part_type.value) or "").strip())
        for part_type in PartType
    )


def _generate_sync(lesson: CourseDay, sources: tuple[RetrievedSource, ...], client: CourseAIClient,
                   previous_reinforce_texts: tuple[str, ...] = ()) -> GeneratedLesson:
    feedback = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw, model = client.complete(_prompt(lesson, sources, feedback, previous_reinforce_texts))
        try:
            parts = _parts(_extract_json(raw))
            validate_parts(parts, previous_reinforce_texts)
        except (ValueError, KeyError, LessonQualityError) as exc:
            feedback = (
                f"Версия {attempt} отклонена. Исправь все ошибки и верни весь JSON заново: {exc}. "
                "Не обрезай текст механически; заверши каждую часть естественно."
            )
            logger.warning("Course lesson %s quality attempt %d failed: %s", lesson.lesson_id, attempt, exc)
            continue
        return GeneratedLesson(
            lesson=lesson,
            parts=parts,
            model=model,
            used_sources=tuple(item.source.url for item in sources),
        )
    raise CourseGenerationError(f"Lesson {lesson.lesson_id} needs review after {_MAX_ATTEMPTS} attempts: {feedback}")


async def generate_lesson(lesson: CourseDay, sources: tuple[RetrievedSource, ...],
                          client: CourseAIClient | None = None,
                          previous_reinforce_texts: tuple[str, ...] = ()) -> GeneratedLesson:
    return await asyncio.to_thread(
        _generate_sync, lesson, sources, client or CourseAIClient(), previous_reinforce_texts
    )
