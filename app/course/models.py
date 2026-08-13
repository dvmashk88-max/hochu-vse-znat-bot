from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from enum import Enum
from typing import TypeAlias


class PartType(str, Enum):
    EXPLAIN = "explain"
    TRY = "try"
    REINFORCE = "reinforce"

    @property
    def public_name(self) -> str:
        return {
            self.EXPLAIN: "РАЗБИРАЕМ",
            self.TRY: "ПРОБУЕМ",
            self.REINFORCE: "ЗАКРЕПЛЯЕМ",
        }[self]

    @property
    def scheduled_time(self) -> time:
        return {
            self.EXPLAIN: time(9, 0),
            self.TRY: time(15, 0),
            self.REINFORCE: time(20, 0),
        }[self]


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    required: bool = True


@dataclass(frozen=True)
class Lesson:
    season_id: str
    season_number: int
    season_title: str
    course_id: str
    course_number: int
    course_title: str
    lesson_id: str
    lesson_number: int
    lesson_count: int
    date: date
    topic: str
    short_title: str
    learning_goal: str
    sources: tuple[Source, ...]
    explain_objective: str
    try_objective: str
    reinforce_objective: str

    @property
    def day_type(self) -> str:
        return "lesson"


@dataclass(frozen=True)
class SpecialDay:
    season_id: str
    season_number: int
    season_title: str
    special_id: str
    date: date
    kind: str
    cover_label: str
    topic: str
    short_title: str
    learning_goal: str
    sources: tuple[Source, ...]
    explain_objective: str
    try_objective: str
    reinforce_objective: str

    @property
    def day_type(self) -> str:
        return "special"

    @property
    def course_id(self) -> str:
        return "special-days"

    @property
    def course_number(self) -> int:
        return 0

    @property
    def course_title(self) -> str:
        return "Специальный день сезона"

    @property
    def lesson_id(self) -> str:
        return self.special_id

    @property
    def lesson_number(self) -> int:
        return 0

    @property
    def lesson_count(self) -> int:
        return 0


CourseDay: TypeAlias = Lesson | SpecialDay


@dataclass(frozen=True)
class CoursePart:
    part_type: PartType
    title: str
    text: str


@dataclass(frozen=True)
class GeneratedLesson:
    lesson: CourseDay
    parts: tuple[CoursePart, ...]
    model: str
    used_sources: tuple[str, ...]

    def part(self, part_type: PartType) -> CoursePart:
        return next(part for part in self.parts if part.part_type == part_type)


@dataclass(frozen=True)
class RetrievedSource:
    source: Source
    text: str
    content_hash: str
