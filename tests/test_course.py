import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PIL import Image

from app import bot as bot_module
from app.course import repository
from app.course.covers import (
    FONT_CANDIDATES,
    SAFE_MARGIN,
    SIZE,
    cover_layout,
    cover_metadata,
    lesson_art_path,
    render_cover,
)
from app.course.curriculum import CurriculumError, load_curriculum, load_curriculum_catalog
from app.course.generator import CourseAIClient, _generate_sync, _trim_complete_sentences
from app.course.models import CoursePart, GeneratedLesson, PartType, RetrievedSource, Source
from app.course.quality import LIMITS, LessonQualityError, validate_parts
from app.course.reconciliation import decide_reconciliation
from app.course.repository import StoredPart
from app.course.service import _publish_platform, _telegram, publish_lesson_part
from app.course.sources import SourceRetrievalError, SourceRetriever
from app.database import Database, UnsupportedDatabaseURL, parse_database_url
from app import db as legacy_db
from app.marketcode.config import MarketCodeSettings
from app.scheduler import configure_scheduler
from app.config import COURSE_AI_FALLBACK_MODEL, COURSE_AI_MODEL


ROOT = Path(__file__).resolve().parents[1]
CURRICULUM = ROOT / "curriculum" / "season_01.yaml"
CURRICULUM_DIR = ROOT / "curriculum"


def _fitted(prefix: str, action: str, length: int, filler: str) -> str:
    if length >= LIMITS[PartType.EXPLAIN][0]:
        cta = "Какой пример оказался самым понятным? Напишите в комментариях свой вариант."
    elif length >= LIMITS[PartType.TRY][0]:
        cta = "Что изменилось после упражнения? Расскажите в комментариях о наблюдении."
    else:
        cta = "Какой вывод вы сохраните? Поделитесь в комментариях своим правилом."
    paragraphs = [
        prefix,
        f"{action} Например, бытовая ситуация помогает увидеть принцип без лишней теории. {filler}",
        "Главное — связать наблюдение с целью урока и проверить результат на понятном случае.",
        cta,
    ]
    while len("\n\n".join(paragraphs)) + len(filler) <= length:
        paragraphs[1] += filler
    return "\n\n".join(paragraphs)


class CurriculumTests(unittest.TestCase):
    def setUp(self):
        self.plan = load_curriculum(CURRICULUM)

    def test_season_and_course_boundaries(self):
        self.assertEqual(self.plan.version, 1)
        self.assertEqual(self.plan.season_id, "season-01")
        self.assertEqual(len(self.plan.lessons), 15)
        self.assertEqual(self.plan.lessons[0].date, date(2026, 8, 14))
        self.assertEqual(self.plan.lessons[-1].date, date(2026, 8, 28))

    def test_resolves_lesson_by_date(self):
        self.assertEqual(self.plan.lesson_for_date(date(2026, 8, 20)).lesson_number, 7)
        self.assertIsNone(self.plan.lesson_for_date(date(2026, 8, 29)))

    def test_31st_day_is_explicit_special_day(self):
        special = self.plan.special_day_for_date(date(2026, 8, 31))
        self.assertEqual(special.kind, "season_summary")
        self.assertIsNone(self.plan.lesson_for_date(date(2026, 8, 31)))

    def test_all_lessons_have_sources_and_objectives(self):
        for lesson in self.plan.lessons:
            self.assertTrue(lesson.sources)
            self.assertTrue(lesson.explain_objective)
            self.assertTrue(lesson.try_objective)
            self.assertTrue(lesson.reinforce_objective)

    def test_duplicate_date_fails_fast(self):
        text = CURRICULUM.read_text(encoding="utf-8").replace("2026-08-15", "2026-08-14", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(CurriculumError, "duplicate lesson date"):
                load_curriculum(path)

    def test_course_must_stay_inside_season_month(self):
        text = CURRICULUM.read_text(encoding="utf-8").replace("month: 2026-08", "month: 2026-09", 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-month.yaml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(CurriculumError, "season month"):
                load_curriculum(path)

    def test_catalog_has_seasons_one_to_five_and_courses_one_to_nine(self):
        catalog = load_curriculum_catalog(CURRICULUM_DIR)
        self.assertEqual([item.season_number for item in catalog.seasons], list(range(1, 6)))
        self.assertEqual(sorted({item.course_number for item in catalog.lessons}), list(range(1, 10)))
        self.assertEqual(len(catalog.lessons), 135)
        for course_number in range(1, 10):
            lessons = [item for item in catalog.lessons if item.course_number == course_number]
            self.assertEqual(len(lessons), 15)
            self.assertEqual([item.lesson_number for item in lessons], list(range(1, 16)))

    def test_catalog_covers_every_day_through_end_of_2026_without_duplicates(self):
        catalog = load_curriculum_catalog(CURRICULUM_DIR)
        expected = [date(2026, 8, 14) + timedelta(days=offset) for offset in range(140)]
        actual = [item.date for item in catalog.days]
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))
        self.assertTrue(all(day.sources for day in catalog.days))

    def test_all_required_special_days_are_resolved_as_special(self):
        catalog = load_curriculum_catalog(CURRICULUM_DIR)
        expected = {
            date(2026, 8, 29), date(2026, 8, 30), date(2026, 8, 31),
            date(2026, 10, 31), date(2026, 12, 31),
        }
        self.assertEqual({item.date for item in catalog.special_days}, expected)
        for target in expected:
            day = catalog.day_for_date(target)
            self.assertEqual(day.day_type, "special")
            self.assertIsNone(catalog.lesson_for_date(target))

    def test_catalog_has_no_placeholders_or_product_bound_course_titles(self):
        catalog = load_curriculum_catalog(CURRICULUM_DIR)
        serialized = " ".join(
            f"{item.topic} {item.learning_goal} {item.explain_objective} "
            f"{item.try_objective} {item.reinforce_objective}" for item in catalog.days
        ).lower()
        self.assertNotIn("tbd", serialized)
        self.assertNotIn("topic pending", serialized)
        self.assertTrue(all("chatgpt" not in item.course_title.lower() for item in catalog.lessons))


class DatabaseTests(unittest.TestCase):
    def test_sqlite_development_url(self):
        parsed = parse_database_url("sqlite:///./local.db")
        self.assertEqual(parsed.backend, "sqlite")
        self.assertEqual(parsed.sqlite_path, "./local.db")

    def test_postgresql_urls_are_not_downgraded_to_sqlite(self):
        self.assertEqual(parse_database_url("postgresql://u:p@db/app").backend, "postgresql")
        parsed = parse_database_url("postgresql+psycopg://u:p@db/app")
        self.assertEqual(parsed.backend, "postgresql")
        self.assertTrue(parsed.url.startswith("postgresql://"))

    def test_unknown_database_scheme_fails_fast(self):
        with self.assertRaises(UnsupportedDatabaseURL):
            parse_database_url("mysql://db/app")

    def test_legacy_topic_storage_still_works_on_sqlite_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'legacy.db'}")
            with patch.object(legacy_db, "database", db):
                legacy_db.init_db()
                legacy_db.save_published_topic("Тестовая тема", category="ai", keywords=("курс",))
                self.assertEqual(legacy_db.get_published_topics(), ["Тестовая тема"])

    def test_publication_claim_is_idempotent_and_failed_is_retryable(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'course.db'}")
            with patch.object(repository, "database", db):
                self.assertEqual(repository.claim_publication(lesson, PartType.EXPLAIN, "telegram", "time"), 1)
                self.assertEqual(repository.claim_publication(lesson, PartType.EXPLAIN, "telegram", "time"), 0)
                repository.finish_publication(lesson, PartType.EXPLAIN, "telegram", status="failed", error="x")
                self.assertEqual(repository.claim_publication(lesson, PartType.EXPLAIN, "telegram", "time"), 2)
                repository.finish_publication(lesson, PartType.EXPLAIN, "telegram", status="published", external_id="1")
                self.assertEqual(repository.claim_publication(lesson, PartType.EXPLAIN, "telegram", "time"), 0)

    def test_stale_publication_claim_is_recovered_after_restart(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'course.db'}")
            with patch.object(repository, "database", db):
                self.assertTrue(repository.claim_publication(lesson, PartType.EXPLAIN, "telegram", "time"))
                with db.connect() as conn:
                    conn.execute("UPDATE platform_publications SET updated_at='2000-01-01 00:00:00'")
                self.assertEqual(repository.recover_stale_work(30)[0], 1)
                self.assertTrue(repository.claim_publication(lesson, PartType.EXPLAIN, "telegram", "time"))

    def test_needs_review_is_not_automatically_regenerated(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'course.db'}")
            with patch.object(repository, "database", db):
                repository.save_generation_failure(lesson, "quality exhausted", "needs_review")
                self.assertFalse(repository.claim_generation(lesson))
                self.assertEqual(repository.generation_status(lesson), "needs_review")

    def test_controlled_needs_review_recovery_is_retryable_without_duplicates(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'course.db'}")
            with patch.object(repository, "database", db):
                repository.save_generation_failure(lesson, "header encoding bug", "needs_review")
                with db.connect(immediate=True) as conn:
                    recovered = conn.execute(
                        """UPDATE course_lessons SET generation_status='failed', error=NULL,
                        updated_at=CURRENT_TIMESTAMP WHERE lesson_id=? AND lesson_date=?
                        AND generation_status='needs_review'
                        AND NOT EXISTS (
                            SELECT 1 FROM lesson_parts WHERE lesson_parts.lesson_id=course_lessons.lesson_id
                        ) AND NOT EXISTS (
                            SELECT 1 FROM platform_publications
                            WHERE platform_publications.lesson_id=course_lessons.lesson_id
                        )""",
                        (lesson.lesson_id, lesson.date.isoformat()),
                    ).rowcount
                self.assertEqual(recovered, 1)
                self.assertEqual(repository.generation_status(lesson), "failed")
                self.assertTrue(repository.claim_generation(lesson))
                with db.connect() as conn:
                    rows = conn.execute(
                        "SELECT lesson_id FROM course_lessons WHERE lesson_id=?", (lesson.lesson_id,)
                    ).fetchall()
                self.assertEqual(rows, [(lesson.lesson_id,)])

    def test_generated_parts_sources_and_cover_artifact_persist(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        parts = tuple(CoursePart(kind, kind.public_name, f"text-{kind.value}") for kind in PartType)
        generated = GeneratedLesson(lesson, parts, "test/model", (lesson.sources[0].url,))
        source = RetrievedSource(lesson.sources[0], "official source text", "source-hash")
        artifacts = {
            kind: (f"course-cover://{kind.value}", f"hash-{kind.value}", f"png-{kind.value}".encode())
            for kind in PartType
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'course.db'}")
            with patch.object(repository, "database", db):
                repository.save_generated_lesson(generated, (source,), artifacts)
                stored = repository.load_part(lesson, PartType.TRY)
                self.assertEqual(stored.text, "text-try")
                self.assertEqual(stored.image_bytes, b"png-try")
                with db.connect() as conn:
                    snapshot = conn.execute("SELECT source_url, content_hash FROM source_snapshots").fetchone()
                self.assertEqual(snapshot, (lesson.sources[0].url, "source-hash"))

    def test_special_day_state_and_idempotency_use_stable_special_key(self):
        special = load_curriculum_catalog(CURRICULUM_DIR).special_day_for_date(date(2026, 10, 31))
        parts = tuple(CoursePart(kind, kind.public_name, f"special-{kind.value}") for kind in PartType)
        generated = GeneratedLesson(special, parts, "test/model", (special.sources[0].url,))
        source = RetrievedSource(special.sources[0], "official special material", "special-source-hash")
        artifacts = {
            kind: (f"course-cover://special/{kind.value}", f"special-{kind.value}", b"image")
            for kind in PartType
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'special.db'}")
            with patch.object(repository, "database", db):
                repository.save_generated_lesson(generated, (source,), artifacts)
                self.assertEqual(repository.load_part(special, PartType.REINFORCE).text, "special-reinforce")
                self.assertEqual(repository.claim_publication(
                    special, PartType.REINFORCE, "telegram", "scheduled"
                ), 1)
                self.assertEqual(repository.claim_publication(
                    special, PartType.REINFORCE, "telegram", "scheduled"
                ), 0)
                self.assertIn("special-2026-10-31", repository.publication_key(
                    special, PartType.REINFORCE, "telegram"
                ))


class QualityAndGenerationTests(unittest.TestCase):
    def test_over_limit_text_is_trimmed_only_at_complete_sentence_boundaries(self):
        sentences = " ".join(
            f"Предложение номер {index} содержит полезное пояснение для учебного материала и пример."
            for index in range(1, 28)
        )
        text = "\n\n".join((
            "Короткая зацепка открывает тему.",
            sentences,
            "Главное предложение сохраняет естественный вывод материала.",
            "Что вы заметили? Напишите итог наблюдения в комментариях.",
        ))

        trimmed = _trim_complete_sentences(text, 1600, 2200)

        self.assertGreater(len(text), 2200)
        self.assertGreaterEqual(len(trimmed), 1600)
        self.assertLessEqual(len(trimmed), 2200)
        self.assertTrue(trimmed.endswith("Напишите итог наблюдения в комментариях."))
        self.assertNotIn("Предложение номер 27", trimmed)
        self.assertEqual(len(trimmed.split("\n\n")), 4)
        self.assertTrue(trimmed.endswith("."))

    def test_course_ai_headers_are_ascii_safe_and_primary_request_is_sent(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": "result"}}]
        }
        client = CourseAIClient("primary/model", "fallback/model")

        def post(_url, *, headers, json, timeout):
            for name, value in headers.items():
                name.encode("ascii")
                value.encode("ascii")
            self.assertEqual(headers["X-OpenRouter-Title"], "HochuVseZnat-AI")
            self.assertNotIn("Хочу всё знать", " ".join(headers.values()))
            self.assertEqual(json["model"], "primary/model")
            self.assertEqual(json["max_tokens"], 3600)
            self.assertEqual(json["temperature"], 0.45)
            self.assertEqual(json["reasoning"], {"effort": "none"})
            self.assertEqual(timeout, 180)
            return response

        with (
            patch("app.course.generator.OPENROUTER_API_KEY", "test-key"),
            patch("app.course.generator.requests.post", side_effect=post) as request,
        ):
            content, model = client.complete("prompt")

        self.assertEqual((content, model), ("result", "primary/model"))
        self.assertEqual(client.models, ("primary/model", "fallback/model"))
        request.assert_called_once()

    def test_course_ai_fallback_remains_available(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"finish_reason": "stop", "message": {"content": "fallback result"}}]
        }
        client = CourseAIClient("primary/model", "fallback/model")
        with (
            patch("app.course.generator.OPENROUTER_API_KEY", "test-key"),
            patch(
                "app.course.generator.requests.post",
                side_effect=(RuntimeError("primary unavailable"), response),
            ) as request,
        ):
            content, model = client.complete("prompt")

        self.assertEqual((content, model), ("fallback result", "fallback/model"))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[1].kwargs["json"]["model"], "fallback/model")

    def test_quality_exhaustion_uses_configured_fallback_model(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        source = RetrievedSource(lesson.sources[0], "официальный материал " * 30, "hash")
        invalid = json.dumps({item.value: "коротко" for item in PartType}, ensure_ascii=False)
        valid = json.dumps({
            "explain": _fitted(
                "Генеративный интеллект создаёт новый ответ.", "Выберите пример.", 1850,
                "Модель использует закономерности учебного материала и строит продолжение. ",
            ),
            "try": _fitted(
                "Проверяем генеративный интеллект на практике.", "Сравните два ответа.", 1450,
                "Задайте одну бытовую цель поиску и помощнику, затем отметьте различия. ",
            ),
            "reinforce": _fitted(
                "Закрепляем отличие генерации от поиска.",
                "Напишите найденное отличие в комментариях.", 1100,
                "Укажите, где появился новый ответ и где потребовалась проверка результата. ",
            ),
        }, ensure_ascii=False)
        client = CourseAIClient("primary/model", "fallback/model")

        def complete(_prompt, *, model=None):
            return (invalid, model) if model == "primary/model" else (valid, model)

        with patch.object(client, "complete", side_effect=complete) as call:
            generated = _generate_sync(lesson, (source,), client)

        self.assertEqual(generated.model, "fallback/model")
        self.assertEqual(call.call_count, 6)
        self.assertEqual(
            [item.kwargs["model"] for item in call.call_args_list],
            ["primary/model", "primary/model", "primary/model", "primary/model", "primary/model", "fallback/model"],
        )
        self.assertIn(invalid, call.call_args_list[1].args[0])
        self.assertIn(invalid, call.call_args_list[5].args[0])
        self.assertIn("ниже минимума содержательно дополни", call.call_args_list[1].args[0])

    def test_length_limits_and_coherence(self):
        parts = (
            CoursePart(PartType.EXPLAIN, "РАЗБИРАЕМ", _fitted("Объясняем языковую модель.", "Выберите пример.", 1850, "Вероятное продолжение строится из элементов учебного материала. ")),
            CoursePart(PartType.TRY, "ПРОБУЕМ", _fitted("Практика с языковой моделью.", "Попробуйте запрос.", 1450, "Измените начальную фразу и внимательно сравните полученные варианты. ")),
            CoursePart(PartType.REINFORCE, "ЗАКРЕПЛЯЕМ", _fitted("Закрепляем языковую модель.", "Напишите результат в комментариях.", 1100, "Отметьте уверенную формулировку и оцените необходимость проверки. ")),
        )
        validate_parts(parts)

    def test_over_limit_is_rejected(self):
        parts = tuple(CoursePart(kind, kind.public_name, "x" * 2500) for kind in PartType)
        with self.assertRaises(LessonQualityError):
            validate_parts(parts)

    def test_every_part_requires_paragraph_structure_and_comments_cta(self):
        parts = (
            CoursePart(PartType.EXPLAIN, "РАЗБИРАЕМ", _fitted("Объясняем языковую модель.", "Выберите пример.", 1850, "Вероятное продолжение строится из элементов учебного материала. ")),
            CoursePart(PartType.TRY, "ПРОБУЕМ", _fitted("Практика с языковой моделью.", "Попробуйте запрос.", 1450, "Измените начало фразы и сравните продолжения. ")),
            CoursePart(PartType.REINFORCE, "ЗАКРЕПЛЯЕМ", _fitted("Закрепляем языковую модель.", "Проверьте результат.", 1100, "Отметьте уверенную формулировку и необходимость проверки. ")),
        )
        broken = (replace(parts[0], text=parts[0].text.replace("\n\n", " ")), *parts[1:])
        with self.assertRaisesRegex(LessonQualityError, "paragraphs"):
            validate_parts(broken)
        missing_cta = (replace(parts[0], text=parts[0].text.rsplit("\n\n", 1)[0]), *parts[1:])
        with self.assertRaisesRegex(LessonQualityError, "comments CTA"):
            validate_parts(missing_cta)

    def test_unsupported_certainty_and_anthropomorphic_claims_are_rejected(self):
        parts = (
            CoursePart(PartType.EXPLAIN, "РАЗБИРАЕМ", _fitted("Объясняем языковую модель.", "Выберите пример.", 1850, "Вероятное продолжение строится из элементов учебного материала. ")),
            CoursePart(PartType.TRY, "ПРОБУЕМ", _fitted("Практика с языковой моделью.", "Попробуйте запрос.", 1450, "Измените начало фразы и сравните продолжения. ")),
            CoursePart(PartType.REINFORCE, "ЗАКРЕПЛЯЕМ", _fitted("Закрепляем языковую модель.", "Проверьте результат.", 1100, "Отметьте уверенную формулировку и необходимость проверки. ")),
        )
        unsupported = (
            replace(parts[0], text=parts[0].text.replace("Главное", "Модель понимает тысячи вариантов. Главное")),
            *parts[1:],
        )
        with self.assertRaisesRegex(LessonQualityError, "anthropomorphic|unsupported"):
            validate_parts(unsupported)
        warning = (
            replace(parts[0], text=parts[0].text.replace(
                "Главное", "Ошибка — надеяться, что ИИ сам догадается. Главное"
            )),
            *parts[1:],
        )
        validate_parts(warning)

    def test_repeated_comments_cta_is_rejected(self):
        parts = (
            CoursePart(PartType.EXPLAIN, "РАЗБИРАЕМ", _fitted("Объясняем контекст модели.", "Выберите пример.", 1850, "Исходные сведения направляют содержание и делают результат конкретнее. ")),
            CoursePart(PartType.TRY, "ПРОБУЕМ", _fitted("Проверяем контекст модели.", "Попробуйте запрос.", 1450, "Добавьте аудиторию и обстоятельства, а затем оцените полученный вариант. ")),
            CoursePart(PartType.REINFORCE, "ЗАКРЕПЛЯЕМ", _fitted("Закрепляем контекст модели.", "Напишите результат в комментариях.", 1100, "Отметьте полезную деталь и сформулируйте собственный итог работы. ")),
        )
        with self.assertRaisesRegex(LessonQualityError, "CTA repeats"):
            validate_parts(parts, (parts[-1].text,))

    def test_lesson_generation_uses_one_json_for_three_parts(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        source = RetrievedSource(lesson.sources[0], "официальный материал " * 30, "hash")
        payload = {
            "explain": _fitted("Генеративный интеллект создаёт ответ.", "Выберите пример.", 1950, "Модель соединяет изученные закономерности и формирует новое продолжение. "),
            "try": _fitted("Проверяем генеративный интеллект.", "Попробуйте сравнение.", 1500, "Задайте одинаковую бытовую цель поиску и помощнику, затем сопоставьте выдачу. "),
            "reinforce": _fitted("Закрепляем генеративный интеллект.", "Напишите вывод в комментариях.", 1150, "Назовите найденное отличие и объясните, какой результат требует проверки. "),
        }
        client = CourseAIClient("test/model", "")
        with patch.object(client, "complete", return_value=(json.dumps(payload, ensure_ascii=False), "test/model")) as call:
            generated = _generate_sync(lesson, (source,), client)
        self.assertEqual(len(generated.parts), 3)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(generated.used_sources, (lesson.sources[0].url,))
        self.assertIn(lesson.future_topics[0], call.call_args.args[0])

    def test_special_day_generation_uses_special_context_and_three_parts(self):
        special = load_curriculum_catalog(CURRICULUM_DIR).special_day_for_date(date(2026, 12, 31))
        source = RetrievedSource(special.sources[0], "официальный итоговый материал " * 30, "hash")
        payload = {
            "explain": _fitted("Подводим итоги навыкам искусственного интеллекта.", "Выберите пример.", 1850, "Программа связывает проверку создание и безопасное применение изученных подходов. "),
            "try": _fitted("Создаём карту навыков искусственного интеллекта.", "Составьте результат.", 1450, "Отметьте освоенные действия и выберите понятное продолжение образовательной программы. "),
            "reinforce": _fitted("Закрепляем карту навыков искусственного интеллекта.", "Напишите самый полезный курс в комментариях.", 1100, "Предложите тему для продолжения и назовите практический результат этого года. "),
        }
        client = CourseAIClient("test/model", "")
        with patch.object(client, "complete", return_value=(json.dumps(payload, ensure_ascii=False), "test/model")) as call:
            generated = _generate_sync(special, (source,), client)
        self.assertEqual(len(generated.parts), 3)
        prompt = call.call_args.args[0]
        self.assertIn("ИТОГИ ГОДА", prompt)
        self.assertNotIn("Урок: 0 из 0", prompt)


class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_retrieval_is_mockable(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        retriever = SourceRetriever()
        item = RetrievedSource(lesson.sources[0], "материал " * 40, "hash")
        with patch.object(retriever, "_fetch", return_value=item):
            self.assertEqual(await retriever.retrieve(lesson), (item,))

    async def test_required_source_failure_stops_blind_generation(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        retriever = SourceRetriever()
        with patch.object(retriever, "_fetch", side_effect=RuntimeError("offline")):
            with self.assertRaises(SourceRetrievalError):
                await retriever.retrieve(lesson)

    async def test_optional_source_failure_does_not_block_required_source(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        required = lesson.sources[0]
        optional = Source("Optional", "https://example.com/optional", required=False)
        lesson = replace(lesson, sources=(required, optional))
        retrieved = RetrievedSource(required, "материал " * 40, "hash")
        retriever = SourceRetriever()

        def fetch(source):
            if source.required:
                return retrieved
            raise RuntimeError("optional offline")

        with patch.object(retriever, "_fetch", side_effect=fetch):
            self.assertEqual(await retriever.retrieve(lesson), (retrieved,))


class CoverTests(unittest.TestCase):
    def test_production_liberation_font_paths_are_supported(self):
        self.assertIn(
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            FONT_CANDIDATES[False],
        )
        self.assertIn(
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            FONT_CANDIDATES[True],
        )

    def test_cover_is_square_deterministic_and_uses_safe_margin(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        first, first_hash = render_cover(lesson, PartType.EXPLAIN, "missing-base.png")
        second, second_hash = render_cover(lesson, PartType.EXPLAIN, "missing-base.png")
        with Image.open(__import__("io").BytesIO(first)) as image:
            self.assertEqual(image.size, (SIZE, SIZE))
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(first, second)
        self.assertGreaterEqual(SAFE_MARGIN, 80)

    def test_every_curriculum_title_fits_every_part_cover(self):
        for lesson in load_curriculum_catalog(CURRICULUM_DIR).days:
            for part_type in PartType:
                layout = cover_layout(lesson, part_type)
                self.assertTrue(layout.text_within_safe_area)
                self.assertLessEqual(len(layout.title_lines), 3)

    def test_lesson_specific_art_is_stored_once_and_reused_for_three_parts(self):
        lesson = load_curriculum(CURRICULUM).lessons[1]
        self.assertTrue(lesson_art_path(lesson).exists())
        covers = [render_cover(lesson, part_type)[0] for part_type in PartType]
        self.assertEqual(len(set(covers)), 3)
        for content in covers:
            with Image.open(__import__("io").BytesIO(content)) as image:
                self.assertEqual(image.size, (SIZE, SIZE))

    def test_special_cover_has_no_fake_lesson_16_of_15(self):
        special = load_curriculum_catalog(CURRICULUM_DIR).special_day_for_date(date(2026, 8, 29))
        metadata = " ".join(cover_metadata(special))
        self.assertIn("СПЕЦИАЛЬНЫЙ УРОК", metadata)
        self.assertNotIn("УРОК 16", metadata)
        self.assertNotIn("ИЗ 15", metadata)


class SchedulerAndReconciliationTests(unittest.TestCase):
    def test_course_ai_uses_qwen_primary_and_paid_gemini_fallback(self):
        self.assertEqual(COURSE_AI_MODEL, "qwen/qwen3.5-flash-02-23")
        self.assertEqual(COURSE_AI_FALLBACK_MODEL, "google/gemini-2.5-flash")

    def test_scheduler_has_three_moscow_jobs_and_unchanged_marketcode_job(self):
        target = AsyncIOScheduler(timezone="Europe/Moscow")
        settings = MarketCodeSettings(True, "12:00", "Europe/Moscow", "cover", "plan", "m", "f")
        with patch("app.scheduler.load_settings", return_value=settings):
            configure_scheduler(target)
        jobs = {job.id: job for job in target.get_jobs()}
        for job_id, hour in (("publish_course_explain", 9), ("publish_course_try", 15), ("publish_course_reinforce", 20)):
            self.assertIn(job_id, jobs)
            self.assertIn(f"hour='{hour}'", str(jobs[job_id].trigger))
            self.assertEqual(str(jobs[job_id].trigger.timezone), "Europe/Moscow")
        self.assertIn("publish_marketcode_article", jobs)
        self.assertIn("hour='12'", str(jobs["publish_marketcode_article"].trigger))
        self.assertNotIn("publish_post", jobs)

    def test_reconciliation_catches_only_latest_reasonable_part(self):
        tz = ZoneInfo("Europe/Moscow")
        decision = decide_reconciliation(datetime(2026, 8, 14, 16, 0, tzinfo=tz), 90)
        self.assertEqual(decision.publish, PartType.TRY)
        self.assertEqual(decision.missed, (PartType.EXPLAIN,))

    def test_reconciliation_marks_old_parts_missed(self):
        tz = ZoneInfo("Europe/Moscow")
        decision = decide_reconciliation(datetime(2026, 8, 14, 22, 0, tzinfo=tz), 90)
        self.assertIsNone(decision.publish)
        self.assertEqual(decision.missed, tuple(PartType))


class PublisherContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_cover_and_whole_text_in_one_message(self):
        text = "цельная учебная часть"
        with patch(
            "app.course.service.send_photo_with_caption", new=AsyncMock(return_value="10")
        ) as photo:
            result = await _telegram(text, b"image")
        from app.course.service import TELEGRAM_CHANNEL_ID

        photo.assert_awaited_once_with(TELEGRAM_CHANNEL_ID, b"image", text)
        self.assertEqual(result, "10")

    async def test_long_course_article_sends_cover_then_full_text_without_truncation(self):
        text = "Полный учебный материал. " * 80
        photo_result = Mock(message_id=10)
        text_result = Mock(message_id=11)
        fake_bot = Mock()
        fake_bot.send_photo = AsyncMock(return_value=photo_result)
        fake_bot.send_message = AsyncMock(return_value=text_result)
        with patch.object(bot_module, "_bot", fake_bot):
            result = await bot_module.send_photo_with_caption("channel", b"image", text)
        self.assertEqual(result, "10,11")
        self.assertNotIn("caption", fake_bot.send_photo.await_args.kwargs)
        fake_bot.send_message.assert_awaited_once_with(chat_id="channel", text=text)

    def test_editorial_limits_fit_platform_text_messages(self):
        self.assertGreater(LIMITS[PartType.EXPLAIN][0], bot_module._CAPTION_LIMIT)
        self.assertLess(max(maximum for _, maximum in LIMITS.values()), 4000)

    async def test_platform_calls_are_compatible_and_vk_is_text_only(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        with (
            patch("app.course.service.publish_to_max", new=AsyncMock(return_value="m")) as max_call,
            patch("app.course.service.publish_to_vk", new=AsyncMock(return_value="v")) as vk_call,
            patch("app.course.service.publish_draft", new=AsyncMock(return_value="published")) as dzen_call,
        ):
            await _publish_platform("max", lesson, PartType.EXPLAIN, "title", "text", b"image")
            await _publish_platform("vk", lesson, PartType.EXPLAIN, "title", "text", b"image")
            await _publish_platform("dzen", lesson, PartType.EXPLAIN, "title", "text", b"image")
        max_call.assert_awaited_once_with(text="text", image_bytes=b"image")
        vk_call.assert_awaited_once_with(text="text", image_bytes=None)
        dzen_call.assert_awaited_once_with(title=f"РАЗБИРАЕМ: {lesson.topic}", text="text", image_bytes=b"image")

    async def test_one_platform_failure_does_not_define_other_fake_operations(self):
        operations = [AsyncMock(side_effect=RuntimeError("telegram")), AsyncMock(return_value="max"), AsyncMock(return_value="vk")]
        results = []
        for operation in operations:
            try:
                results.append(await operation())
            except RuntimeError:
                results.append("failed")
        self.assertEqual(results, ["failed", "max", "vk"])

    async def test_real_course_orchestrator_continues_after_platform_failure(self):
        lesson = load_curriculum(CURRICULUM).lessons[0]
        part = StoredPart(
            lesson.season_id, lesson.course_id, lesson.lesson_id, lesson.date,
            PartType.EXPLAIN, "РАЗБИРАЕМ", "цельный текст", "course-cover://test", "hash", b"image",
        )
        platform_result = AsyncMock(side_effect=[RuntimeError("telegram failed"), "max-id", "vk-id", "published"])
        with (
            patch("app.course.service.curriculum") as plan,
            patch("app.course.service.prepare_lesson", new=AsyncMock(return_value=True)),
            patch("app.course.service.load_part", return_value=part),
            patch("app.course.service.hashlib.sha256") as sha,
            patch("app.course.service.claim_publication", return_value=True),
            patch("app.course.service._publish_platform", platform_result),
            patch("app.course.service.finish_publication") as finish,
            patch("app.course.service.publication_statuses", return_value={
                "telegram": "failed", "max": "published", "vk": "published", "dzen": "published"
            }),
        ):
            plan.return_value.day_for_date.return_value = lesson
            sha.return_value.hexdigest.return_value = "hash"
            await publish_lesson_part(PartType.EXPLAIN, target_date=lesson.date)
        self.assertEqual(platform_result.await_count, 4)
        self.assertEqual(finish.call_count, 4)
        self.assertEqual(finish.call_args_list[0].kwargs["status"], "failed")
        self.assertTrue(all(call.kwargs["status"] == "published" for call in finish.call_args_list[1:]))

    async def test_special_day_uses_same_publication_orchestrator(self):
        special = load_curriculum_catalog(CURRICULUM_DIR).special_day_for_date(date(2026, 8, 31))
        part = StoredPart(
            special.season_id, special.course_id, special.lesson_id, special.date,
            PartType.EXPLAIN, "РАЗБИРАЕМ", "итоговый текст", "course-cover://special", "hash", b"image",
        )
        with (
            patch("app.course.service.curriculum") as plan,
            patch("app.course.service.prepare_lesson", new=AsyncMock(return_value=True)) as prepare,
            patch("app.course.service.load_part", return_value=part),
            patch("app.course.service.hashlib.sha256") as sha,
            patch("app.course.service.claim_publication", side_effect=[1, 1, 1, 1]),
            patch("app.course.service._publish_platform", new=AsyncMock(return_value="published")) as publish,
            patch("app.course.service.finish_publication"),
        ):
            plan.return_value.day_for_date.return_value = special
            sha.return_value.hexdigest.return_value = "hash"
            await publish_lesson_part(PartType.EXPLAIN, target_date=special.date)
        prepare.assert_awaited_once_with(special)
        self.assertEqual(publish.await_count, 4)

    def test_course_flow_does_not_import_legacy_image_search(self):
        import inspect
        import app.course.service as service
        self.assertNotIn("app.images", inspect.getsource(service))
        self.assertNotIn("fetch_image", inspect.getsource(service))


if __name__ == "__main__":
    unittest.main()
