from __future__ import annotations

import re
from dataclasses import dataclass

from app.course.models import CoursePart, PartType


LIMITS = {
    PartType.EXPLAIN: (850, 1000),
    PartType.TRY: (650, 900),
    PartType.REINFORCE: (450, 750),
}


class LessonQualityError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _tokens(text: str) -> set[str]:
    stop = {"который", "чтобы", "после", "этого", "теперь", "можно", "нужно", "ваш", "свой"}
    return {word for word in re.findall(r"[а-яёa-z0-9-]+", text.lower()) if len(word) >= 5 and word not in stop}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / max(1, len(a | b))


def _comments_cta(text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return next((sentence.lower().strip() for sentence in reversed(sentences) if "комментари" in sentence.lower()), "")


def validate_parts(parts: tuple[CoursePart, ...], previous_reinforce_texts: tuple[str, ...] = ()) -> None:
    errors: list[str] = []
    by_type = {part.part_type: part for part in parts}
    if set(by_type) != set(PartType):
        errors.append("all three lesson parts are required exactly once")
    for part_type in PartType:
        part = by_type.get(part_type)
        if not part:
            continue
        text = part.text.strip()
        minimum, maximum = LIMITS[part_type]
        if not text:
            errors.append(f"{part_type.value}: empty text")
        if not minimum <= len(text) <= maximum:
            errors.append(f"{part_type.value}: {len(text)} chars, expected {minimum}-{maximum}")
        if "```" in text:
            errors.append(f"{part_type.value}: markdown fence is forbidden")
        if re.search(r"(как языковая модель,? я|я — ии|я являюсь ии|вот ваш ответ|system prompt)", text, re.I):
            errors.append(f"{part_type.value}: model meta-instruction found")
    if len(by_type) == 3:
        explain, try_part, reinforce = (by_type[item].text for item in PartType)
        if not (_tokens(explain) & _tokens(try_part)):
            errors.append("try part is not lexically connected to explain part")
        if not (_tokens(reinforce) & (_tokens(explain) | _tokens(try_part))):
            errors.append("reinforce part is not connected to previous parts")
        if any(_similarity(a, b) > 0.55 for a, b in ((explain, try_part), (explain, reinforce), (try_part, reinforce))):
            errors.append("lesson parts repeat too much text")
        openings = [" ".join(text.lower().split()[:8]) for text in (explain, try_part, reinforce)]
        if len(set(openings)) != 3:
            errors.append("lesson parts have identical introductions")
        if not re.search(r"комментари", reinforce, re.I):
            errors.append("reinforce part must contain a concrete comments CTA")
        current_cta = _comments_cta(reinforce)
        previous_ctas = {_comments_cta(text) for text in previous_reinforce_texts}
        if current_cta and current_cta in previous_ctas:
            errors.append("reinforce comments CTA repeats a previous lesson")
        if not re.search(r"\b(сделайте|попробуйте|напишите|сравните|выберите|возьмите|откройте|составьте)\b", try_part, re.I):
            errors.append("try part must contain a clear action")
    if errors:
        raise LessonQualityError(errors)
