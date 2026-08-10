from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


CONTENT_PLAN_PATH = Path(__file__).resolve().parents[2] / "MARKETCODE_CONTENT_PLAN.md"
EXPECTED_CATEGORY_COUNTS = {
    "Apple ID / App Store": 35,
    "Steam": 25,
    "Telegram": 15,
    "Gift Cards": 15,
    "Игровые товары": 10,
}


@dataclass(frozen=True)
class ContentPlanEntry:
    day: int
    topic: str
    category: str
    keywords: tuple[str, ...]
    goal: str


_ENTRY_RE = re.compile(
    r"^## День (?P<day>\d+)\s*\n"
    r"Тема: (?P<topic>[^\n]+)\n"
    r"Категория: (?P<category>[^\n]+)\n"
    r"Основные поисковые запросы: (?P<keywords>[^\n]+)\n"
    r"Цель статьи: (?P<goal>.+?)(?=\n## День|\Z)",
    re.MULTILINE | re.DOTALL,
)


def load_content_plan(path: Path = CONTENT_PLAN_PATH) -> list[ContentPlanEntry]:
    text = path.read_text(encoding="utf-8")
    entries = []
    for match in _ENTRY_RE.finditer(text):
        data = match.groupdict()
        entries.append(
            ContentPlanEntry(
                day=int(data["day"]),
                topic=data["topic"].strip(),
                category=data["category"].strip(),
                keywords=tuple(item.strip() for item in data["keywords"].split(",") if item.strip()),
                goal=data["goal"].strip(),
            )
        )

    expected_days = list(range(1, len(entries) + 1))
    actual_days = [entry.day for entry in entries]
    if actual_days != expected_days:
        raise ValueError("MarketCode content plan days must be consecutive and start at 1")
    if len(entries) != 100:
        raise ValueError("MarketCode content plan must contain exactly 100 days")
    if Counter(entry.category for entry in entries) != EXPECTED_CATEGORY_COUNTS:
        raise ValueError("MarketCode content plan category distribution is invalid")
    return entries
