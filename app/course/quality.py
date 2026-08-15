from __future__ import annotations

import re
from dataclasses import dataclass

from app.course.models import CoursePart, PartType


LIMITS = {
    PartType.EXPLAIN: (1600, 2200),
    PartType.TRY: (1200, 1700),
    PartType.REINFORCE: (900, 1300),
}

PARAGRAPH_LIMITS = {
    PartType.EXPLAIN: (4, 7),
    PartType.TRY: (4, 7),
    PartType.REINFORCE: (3, 6),
}
MAX_HOOK_CHARS = 500

_COMMENT_ACTION = re.compile(
    r"\b(напишите|расскажите|поделитесь|предложите|ответьте)\b.*\bкомментари",
    re.I | re.S,
)
_TRY_ACTION = re.compile(
    r"\b(сделайте|попробуйте|напишите|сравните|выберите|возьмите|откройте|составьте|измените|проверьте)\b",
    re.I,
)
_EXAMPLE_MARKER = re.compile(r"\b(например|представьте|допустим|к примеру|возьмём|сравним)\b", re.I)
_BANNED_CLICHE = re.compile(
    r"\b(искусственный интеллект стремительно меняет мир|в современном мире|"
    r"ни для кого не секрет|давайте погрузимся|революционная технология)\b",
    re.I,
)
_ANTHROPOMORPHIC_CLAIM = re.compile(
    r"\b(?:модел[а-яё]*|ии|систем[а-яё]*|помощник[а-яё]*)\s+"
    r"(?:сам[а-яё]*\s+|действительно\s+)?"
    r"(?:вспомина[а-яё]*|пойм[а-яё]*|поня[а-яё]*|понима[а-яё]*|догад[а-яё]*|"
    r"зна[а-яё]*|осозна[а-яё]*)\b",
    re.I,
)
_UNSUPPORTED_CERTAINTY = re.compile(
    r"\b(?:тысяч[а-яё]*|миллион[а-яё]*|исключительно|"
    r"доказывает|скорее\s+всего|чаще\s+всего|любая\s+современная|"
    r"быстрее\s+(?:человека|людей))\b",
    re.I,
)


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


def _paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", text.strip()) if item.strip()]


def _anthropomorphic_claim(text: str) -> re.Match | None:
    for match in _ANTHROPOMORPHIC_CLAIM.finditer(text):
        sentence_start = max(text.rfind(mark, 0, match.start()) for mark in ".!?\n") + 1
        prefix = text[sentence_start:match.start()].lower()
        if re.search(r"\b(?:не|нельзя|ошибк[а-яё]*|неверн[а-яё]*|не\s+стоит|не\s+ждите)\b", prefix):
            continue
        return match
    return None


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
        paragraphs = _paragraphs(text)
        min_paragraphs, max_paragraphs = PARAGRAPH_LIMITS[part_type]
        if not min_paragraphs <= len(paragraphs) <= max_paragraphs:
            errors.append(
                f"{part_type.value}: {len(paragraphs)} paragraphs, "
                f"expected {min_paragraphs}-{max_paragraphs}"
            )
        if paragraphs and len(paragraphs[0]) > MAX_HOOK_CHARS:
            errors.append(f"{part_type.value}: opening hook is too long")
        if paragraphs and not (
            re.search(r"комментари", paragraphs[-1], re.I)
            and (_COMMENT_ACTION.search(paragraphs[-1]) or "?" in paragraphs[-1])
        ):
            errors.append(f"{part_type.value}: final paragraph must contain a concrete comments CTA")
        if _BANNED_CLICHE.search(text):
            errors.append(f"{part_type.value}: generic AI cliche found")
        anthropomorphic = _anthropomorphic_claim(text)
        if anthropomorphic:
            errors.append(
                f"{part_type.value}: anthropomorphic model claim found: {anthropomorphic.group(0)}"
            )
        unsupported = _UNSUPPORTED_CERTAINTY.search(text)
        if unsupported:
            errors.append(
                f"{part_type.value}: unsupported quantity or certainty claim found: {unsupported.group(0)}"
            )
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
        if not _EXAMPLE_MARKER.search(explain):
            errors.append("explain part must contain a concrete example or analogy")
        current_ctas = [_comments_cta(text) for text in (explain, try_part, reinforce)]
        if len(set(current_ctas)) != 3:
            errors.append("lesson parts must use different comments CTAs")
        previous_ctas = {_comments_cta(text) for text in previous_reinforce_texts}
        if any(current_cta and current_cta in previous_ctas for current_cta in current_ctas):
            errors.append("comments CTA repeats a previous lesson")
        if not _TRY_ACTION.search(try_part):
            errors.append("try part must contain a clear action")
    if errors:
        raise LessonQualityError(errors)
