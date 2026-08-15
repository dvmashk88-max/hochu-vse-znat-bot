from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml

from app.course.models import CourseDay, Lesson, Source, SpecialDay


class CurriculumError(ValueError):
    pass


@dataclass(frozen=True)
class Curriculum:
    version: int
    season_id: str
    season_number: int
    season_title: str
    month: str
    timezone: str
    lessons: tuple[Lesson, ...]
    special_days: tuple[SpecialDay, ...] = ()

    def lesson_for_date(self, target: date) -> Lesson | None:
        return next((lesson for lesson in self.lessons if lesson.date == target), None)

    def special_day_for_date(self, target: date) -> SpecialDay | None:
        return next((item for item in self.special_days if item.date == target), None)

    def day_for_date(self, target: date) -> CourseDay | None:
        return self.lesson_for_date(target) or self.special_day_for_date(target)


@dataclass(frozen=True)
class CurriculumCatalog:
    seasons: tuple[Curriculum, ...]

    @property
    def lessons(self) -> tuple[Lesson, ...]:
        return tuple(lesson for season in self.seasons for lesson in season.lessons)

    @property
    def special_days(self) -> tuple[SpecialDay, ...]:
        return tuple(day for season in self.seasons for day in season.special_days)

    @property
    def days(self) -> tuple[CourseDay, ...]:
        return tuple(sorted((*self.lessons, *self.special_days), key=lambda item: item.date))

    @property
    def timezone(self) -> str:
        zones = {season.timezone for season in self.seasons}
        if len(zones) != 1:
            raise CurriculumError(f"All seasons must use one timezone, got: {sorted(zones)}")
        return next(iter(zones))

    def lesson_for_date(self, target: date) -> Lesson | None:
        return next((season.lesson_for_date(target) for season in self.seasons
                     if season.lesson_for_date(target)), None)

    def special_day_for_date(self, target: date) -> SpecialDay | None:
        return next((season.special_day_for_date(target) for season in self.seasons
                     if season.special_day_for_date(target)), None)

    def day_for_date(self, target: date) -> CourseDay | None:
        return self.lesson_for_date(target) or self.special_day_for_date(target)


def _required_text(data: dict, key: str, context: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise CurriculumError(f"{context}: required field '{key}' is empty")
    return value


def _parse_date(value: object, context: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise CurriculumError(f"{context}: invalid ISO date '{value}'") from exc


def load_curriculum(path: str | Path) -> Curriculum:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CurriculumError(f"Cannot load curriculum {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CurriculumError("Curriculum root must be a mapping")
    version = int(raw.get("version") or 0)
    if version < 1:
        raise CurriculumError("Curriculum version must be a positive integer")

    season = raw.get("season") or {}
    season_id = _required_text(season, "id", "season")
    season_title = _required_text(season, "title", "season")
    month = _required_text(season, "month", "season")
    try:
        date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise CurriculumError("season.month must use YYYY-MM format") from exc
    timezone = _required_text(season, "timezone", "season")
    season_number = int(season.get("number") or 0)
    if season_number < 1:
        raise CurriculumError("season.number must be positive")

    courses = raw.get("courses")
    if not isinstance(courses, list) or not courses:
        raise CurriculumError("Curriculum must contain at least one course")
    course_ids: set[str] = set()
    lesson_ids: set[str] = set()
    all_dates: set[date] = set()
    lessons: list[Lesson] = []
    for course_index, course in enumerate(courses, 1):
        context = f"course #{course_index}"
        course_id = _required_text(course, "id", context)
        if course_id in course_ids:
            raise CurriculumError(f"Duplicate course id: {course_id}")
        course_ids.add(course_id)
        course_title = _required_text(course, "title", context)
        course_number = int(course.get("number") or course_index)
        start = _parse_date(course.get("start_date"), context)
        end = _parse_date(course.get("end_date"), context)
        if start.strftime("%Y-%m") != month or end.strftime("%Y-%m") != month:
            raise CurriculumError(f"{context}: course dates must belong to season month {month}")
        if start > end:
            raise CurriculumError(f"{context}: start_date is after end_date")
        raw_lessons = course.get("lessons")
        if not isinstance(raw_lessons, list) or not raw_lessons:
            raise CurriculumError(f"{context}: lessons are required")
        course_topics = tuple(
            _required_text(item, "topic", f"{course_id} lesson #{index}")
            for index, item in enumerate(raw_lessons, 1)
        )
        course_dates: set[date] = set()
        for lesson_index, item in enumerate(raw_lessons, 1):
            item_context = f"{course_id} lesson #{lesson_index}"
            lesson_id = _required_text(item, "id", item_context)
            if lesson_id in lesson_ids:
                raise CurriculumError(f"Duplicate lesson id: {lesson_id}")
            lesson_ids.add(lesson_id)
            lesson_date = _parse_date(item.get("date"), item_context)
            if lesson_date in course_dates:
                raise CurriculumError(f"{course_id}: duplicate lesson date {lesson_date}")
            if lesson_date in all_dates:
                raise CurriculumError(f"Duplicate lesson date across curriculum: {lesson_date}")
            if not start <= lesson_date <= end:
                raise CurriculumError(f"{item_context}: date is outside course boundaries")
            expected = start.fromordinal(start.toordinal() + lesson_index - 1)
            if lesson_date != expected:
                raise CurriculumError(
                    f"{item_context}: expected consecutive date {expected}, got {lesson_date}"
                )
            course_dates.add(lesson_date)
            all_dates.add(lesson_date)
            raw_sources = item.get("sources")
            if not isinstance(raw_sources, list) or not raw_sources:
                raise CurriculumError(f"{item_context}: at least one source is required")
            sources = []
            for source in raw_sources:
                url = _required_text(source, "url", f"{item_context} source")
                if urlparse(url).scheme not in {"http", "https"}:
                    raise CurriculumError(f"{item_context}: source URL must be HTTP(S)")
                sources.append(Source(
                    title=_required_text(source, "title", f"{item_context} source"),
                    url=url,
                    required=bool(source.get("required", True)),
                ))
            lessons.append(Lesson(
                season_id=season_id,
                season_number=season_number,
                season_title=season_title,
                course_id=course_id,
                course_number=course_number,
                course_title=course_title,
                lesson_id=lesson_id,
                lesson_number=lesson_index,
                lesson_count=len(raw_lessons),
                date=lesson_date,
                topic=_required_text(item, "topic", item_context),
                short_title=_required_text(item, "short_title", item_context),
                learning_goal=_required_text(item, "learning_goal", item_context),
                sources=tuple(sources),
                explain_objective=_required_text(item, "explain_objective", item_context),
                try_objective=_required_text(item, "try_objective", item_context),
                reinforce_objective=_required_text(item, "reinforce_objective", item_context),
                future_topics=course_topics[lesson_index:],
            ))
        if course_dates != {start.fromordinal(start.toordinal() + offset) for offset in range((end - start).days + 1)}:
            raise CurriculumError(f"{course_id}: lessons must cover every date from start_date to end_date")

    specials: list[SpecialDay] = []
    special_ids: set[str] = set()
    for item in raw.get("special_days") or []:
        special_date = _parse_date(item.get("date"), "special day")
        if special_date.strftime("%Y-%m") != month:
            raise CurriculumError(f"Special day must belong to season month {month}")
        if special_date in all_dates:
            raise CurriculumError(f"Special day overlaps lesson date: {special_date}")
        if special_date in {day.date for day in specials}:
            raise CurriculumError(f"Duplicate special day date: {special_date}")
        special_id = _required_text(item, "id", "special day")
        if special_id in special_ids or special_id in lesson_ids:
            raise CurriculumError(f"Duplicate special day id: {special_id}")
        special_ids.add(special_id)
        raw_sources = item.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise CurriculumError(f"special day {special_id}: at least one source is required")
        sources = []
        for source in raw_sources:
            url = _required_text(source, "url", f"special day {special_id} source")
            if urlparse(url).scheme not in {"http", "https"}:
                raise CurriculumError(f"special day {special_id}: source URL must be HTTP(S)")
            sources.append(Source(
                title=_required_text(source, "title", f"special day {special_id} source"),
                url=url,
                required=bool(source.get("required", True)),
            ))
        specials.append(SpecialDay(
            season_id=season_id,
            season_number=season_number,
            season_title=season_title,
            special_id=special_id,
            date=special_date,
            kind=_required_text(item, "kind", f"special day {special_id}"),
            cover_label=_required_text(item, "cover_label", f"special day {special_id}"),
            topic=_required_text(item, "topic", f"special day {special_id}"),
            short_title=_required_text(item, "short_title", f"special day {special_id}"),
            learning_goal=_required_text(item, "learning_goal", f"special day {special_id}"),
            sources=tuple(sources),
            explain_objective=_required_text(item, "explain_objective", f"special day {special_id}"),
            try_objective=_required_text(item, "try_objective", f"special day {special_id}"),
            reinforce_objective=_required_text(item, "reinforce_objective", f"special day {special_id}"),
        ))
    return Curriculum(version, season_id, season_number, season_title, month, timezone, tuple(lessons), tuple(specials))


def load_curriculum_catalog(path: str | Path) -> CurriculumCatalog:
    path = Path(path)
    paths = sorted(path.glob("season_*.yaml")) if path.is_dir() else [path]
    if not paths:
        raise CurriculumError(f"No season_*.yaml files found in {path}")
    seasons = tuple(load_curriculum(item) for item in paths)
    ids = [season.season_id for season in seasons]
    numbers = [season.season_number for season in seasons]
    months = [season.month for season in seasons]
    for label, values in (("season id", ids), ("season number", numbers), ("season month", months)):
        if len(values) != len(set(values)):
            raise CurriculumError(f"Duplicate {label} across curriculum catalog")
    course_ids = [course_id for season in seasons for course_id in {item.course_id for item in season.lessons}]
    if len(course_ids) != len(set(course_ids)):
        raise CurriculumError("Duplicate course id across curriculum catalog")
    lesson_ids = [item.lesson_id for season in seasons for item in season.lessons]
    special_ids = [item.special_id for season in seasons for item in season.special_days]
    if len(lesson_ids) != len(set(lesson_ids)):
        raise CurriculumError("Duplicate lesson id across curriculum catalog")
    if len(special_ids) != len(set(special_ids)) or set(lesson_ids) & set(special_ids):
        raise CurriculumError("Duplicate special day id across curriculum catalog")
    days = [day for season in seasons for day in (*season.lessons, *season.special_days)]
    dates = [day.date for day in days]
    if len(dates) != len(set(dates)):
        raise CurriculumError("Duplicate date across curriculum catalog")
    ordered = sorted(dates)
    expected = {date.fromordinal(ordered[0].toordinal() + offset)
                for offset in range((ordered[-1] - ordered[0]).days + 1)}
    missing = sorted(expected - set(ordered))
    if missing:
        preview = ", ".join(item.isoformat() for item in missing[:5])
        raise CurriculumError(f"Curriculum catalog has uncovered dates: {preview}")
    catalog = CurriculumCatalog(seasons)
    catalog.timezone
    return catalog
