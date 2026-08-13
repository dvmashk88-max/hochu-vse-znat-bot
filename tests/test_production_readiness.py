import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.course import alerts, repository, service
from app.course.alerts import AdminAlert, lesson_alert, send_admin_alert
from app.course.curriculum import load_curriculum_catalog
from app.course.generator import CourseGenerationError
from app.course.models import PartType, RetrievedSource
from app.course.readiness import database_summary, startup_summary
from app.course.repository import StoredPart
from app.course.sources import SourceRetrievalError
from app.database import Connection, Database
from app.marketcode import repository as marketcode_repository
from app.marketcode.config import MarketCodeSettings
from app.migrations.sqlite_to_postgres import migrate_marketcode


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "curriculum"


class ProductionCoverTests(unittest.TestCase):
    def test_all_420_covers_have_safe_layout_and_five_distinct_themes(self):
        from app.course.covers import SIZE, cover_layout, render_cover

        catalog = load_curriculum_catalog(CATALOG)
        themes = set()
        season_digests = {}
        sizes = []
        count = 0
        for day in catalog.days:
            for part_type in PartType:
                layout = cover_layout(day, part_type)
                content, digest = render_cover(day, part_type, "missing-production-override.png")
                self.assertTrue(layout.text_within_safe_area)
                self.assertGreaterEqual(layout.title_font_size, 38)
                self.assertLessEqual(len(layout.title_lines), 3)
                self.assertTrue(content.startswith(b"\xff\xd8"))
                self.assertEqual(len(digest), 64)
                themes.add(layout.season_theme)
                season_digests.setdefault(day.season_number, digest)
                sizes.append(len(content))
                count += 1
        self.assertEqual(count, 420)
        self.assertEqual(len(themes), 5)
        self.assertEqual(len(set(season_digests.values())), 5)
        self.assertLess(sum(sizes) / len(sizes), 200_000)
        self.assertLess(sum(sizes), 100 * 1024 * 1024)
        self.assertEqual(SIZE, 1080)


class PreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepares_today_and_next_three_days(self):
        catalog = load_curriculum_catalog(CATALOG)
        start = date(2026, 9, 10)
        with (
            patch("app.course.service.curriculum", return_value=catalog),
            patch("app.course.service.COURSE_PREPARE_DAYS", 3),
            patch("app.course.service.prepare_lesson", new=AsyncMock(return_value=True)) as prepare,
        ):
            await service.prepare_course_days(start)
        self.assertEqual(
            [call.args[0].date for call in prepare.await_args_list],
            [start + timedelta(days=offset) for offset in range(4)],
        )

    async def test_generated_artifact_is_not_regenerated(self):
        day = load_curriculum_catalog(CATALOG).days[0]
        with (
            patch("app.course.service.generation_status", return_value="generated"),
            patch("app.course.service.claim_generation") as claim,
            patch("app.course.service.generate_lesson", new=AsyncMock()) as generate,
        ):
            self.assertTrue(await service.prepare_lesson(day))
        claim.assert_not_called()
        generate.assert_not_awaited()

    async def test_needs_review_is_not_regenerated(self):
        day = load_curriculum_catalog(CATALOG).days[0]
        with (
            patch("app.course.service.generation_status", return_value="needs_review"),
            patch("app.course.service.claim_generation", return_value=False),
            patch("app.course.service.generate_lesson", new=AsyncMock()) as generate,
        ):
            self.assertFalse(await service.prepare_lesson(day))
        generate.assert_not_awaited()


class AdminAlertTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        alerts._process_claims.clear()
        alerts._configuration_warning_logged = False

    async def test_disabled_alert_does_not_send_or_crash(self):
        with (
            patch("app.course.alerts.COURSE_ALERTS_ENABLED", False),
            patch("app.course.alerts.send_text", new=AsyncMock()) as send,
        ):
            self.assertFalse(await send_admin_alert(AdminAlert("key", "test", "message")))
        send.assert_not_awaited()

    async def test_missing_admin_chat_does_not_send_or_crash(self):
        with (
            patch("app.course.alerts.COURSE_ALERTS_ENABLED", True),
            patch("app.course.alerts.ADMIN_TELEGRAM_CHAT_ID", ""),
            patch("app.course.alerts.send_text", new=AsyncMock()) as send,
        ):
            self.assertFalse(await send_admin_alert(AdminAlert("key", "test", "message")))
        send.assert_not_awaited()

    async def test_alert_is_deduplicated(self):
        with (
            patch("app.course.alerts.COURSE_ALERTS_ENABLED", True),
            patch("app.course.alerts.ADMIN_TELEGRAM_CHAT_ID", "123"),
            patch("app.course.alerts.claim_admin_alert", return_value=True),
            patch("app.course.alerts.finish_admin_alert"),
            patch("app.course.alerts.send_text", new=AsyncMock(return_value="7")) as send,
        ):
            alert = AdminAlert("same-key", "test", "message")
            self.assertTrue(await send_admin_alert(alert))
            self.assertFalse(await send_admin_alert(alert))
        self.assertEqual(send.await_count, 1)

    async def test_required_source_failure_creates_alert(self):
        day = load_curriculum_catalog(CATALOG).days[0]
        retriever = AsyncMock()
        retriever.retrieve.side_effect = SourceRetrievalError("required sources offline")
        with (
            patch("app.course.service.generation_status", return_value=None),
            patch("app.course.service.claim_generation", return_value=True),
            patch("app.course.service.save_generation_failure"),
            patch("app.course.service.send_admin_alert", new=AsyncMock(return_value=True)) as send,
        ):
            self.assertFalse(await service.prepare_lesson(day, retriever))
        self.assertEqual(send.await_args.args[0].alert_type, "mandatory_sources_unavailable")

    async def test_database_read_failure_creates_non_persistent_emergency_alert(self):
        day = load_curriculum_catalog(CATALOG).days[0]
        with (
            patch("app.course.service.generation_status", side_effect=RuntimeError("database offline")),
            patch("app.course.service.send_admin_alert", new=AsyncMock(return_value=True)) as send,
        ):
            self.assertFalse(await service.prepare_lesson(day))
        self.assertEqual(send.await_args.args[0].alert_type, "database_error")
        self.assertFalse(send.await_args.kwargs["persistent_dedupe"])

    async def test_needs_review_failure_creates_alert(self):
        day = load_curriculum_catalog(CATALOG).days[0]
        source = RetrievedSource(day.sources[0], "материал " * 50, "hash")
        retriever = AsyncMock()
        retriever.retrieve.return_value = (source,)
        with (
            patch("app.course.service.generation_status", return_value=None),
            patch("app.course.service.claim_generation", return_value=True),
            patch("app.course.service.recent_reinforce_texts", return_value=()),
            patch("app.course.service.generate_lesson", new=AsyncMock(side_effect=CourseGenerationError("quality"))),
            patch("app.course.service.save_generation_failure"),
            patch("app.course.service.send_admin_alert", new=AsyncMock(return_value=True)) as send,
        ):
            self.assertFalse(await service.prepare_lesson(day, retriever))
        self.assertEqual(send.await_args.args[0].alert_type, "lesson_needs_review")

    async def test_all_platform_failure_creates_one_aggregate_alert(self):
        day = load_curriculum_catalog(CATALOG).days[0]
        part = StoredPart(day.season_id, day.course_id, day.lesson_id, day.date, PartType.EXPLAIN,
                          "title", "text", "ref", "hash", b"image")
        with (
            patch("app.course.service.curriculum") as plan,
            patch("app.course.service.prepare_lesson", new=AsyncMock(return_value=True)),
            patch("app.course.service.load_part", return_value=part),
            patch("app.course.service.hashlib.sha256") as sha,
            patch("app.course.service.claim_publication", return_value=1),
            patch("app.course.service._publish_platform", new=AsyncMock(side_effect=RuntimeError("offline"))),
            patch("app.course.service.finish_publication"),
            patch("app.course.service.publication_statuses", return_value={item: "failed" for item in service.PLATFORMS}),
            patch("app.course.service.send_admin_alert", new=AsyncMock(return_value=True)) as send,
        ):
            plan.return_value.day_for_date.return_value = day
            sha.return_value.hexdigest.return_value = "hash"
            await service.publish_lesson_part(PartType.EXPLAIN, target_date=day.date)
        aggregate = [call.args[0] for call in send.await_args_list if call.args[0].alert_type == "all_platforms_failed"]
        self.assertEqual(len(aggregate), 1)


class StartupSummaryTests(unittest.TestCase):
    def test_summary_is_complete_and_does_not_expose_secrets(self):
        catalog = load_curriculum_catalog(CATALOG)
        db = Database("postgresql://user:database-secret@host/app")
        settings = MarketCodeSettings(True, "12:00", "Europe/Moscow", "asset", "plan", "model", "fallback")
        with (
            patch("app.course.readiness.TELEGRAM_BOT_TOKEN", "telegram-secret"),
            patch("app.course.readiness.VK_ACCESS_TOKEN", "vk-secret"),
            patch("app.course.readiness.DZEN_STORAGE_STATE_JSON", "dzen-secret"),
        ):
            summary = startup_summary(catalog, db, settings)
        self.assertIn("Seasons: 5", summary)
        self.assertIn("Calendar days: 140", summary)
        self.assertIn("Backend: PostgreSQL", summary)
        self.assertIn("Today + 3 days", summary)
        self.assertNotIn("database-secret", summary)
        self.assertNotIn("telegram-secret", summary)
        self.assertNotIn("vk-secret", summary)
        self.assertNotIn("dzen-secret", summary)
        self.assertEqual(database_summary(db), ("PostgreSQL", "configured"))


class MigrationTests(unittest.TestCase):
    def _source(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE marketcode_publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, plan_day INTEGER NOT NULL UNIQUE,
            topic TEXT NOT NULL, category TEXT NOT NULL, word_count INTEGER NOT NULL,
            model TEXT NOT NULL, status TEXT NOT NULL, channel_statuses TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""INSERT INTO marketcode_publications
            (plan_day, topic, category, word_count, model, status, channel_statuses)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (
                7, "Тема", "Категория", 400, "gemini", "partial",
                json.dumps({"telegram": "published:1", "vk": "failed"}, ensure_ascii=False),
            ))
        conn.commit()
        conn.close()

    def test_dry_run_does_not_create_target_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.db"
            target_path = Path(tmp) / "target.db"
            self._source(source)
            target = Database(f"sqlite:///{target_path}")
            result = migrate_marketcode(source, target, dry_run=True, require_postgresql=False)
            self.assertEqual(result.source_rows, 1)
            self.assertEqual(result.would_insert, 1)
            conn = sqlite3.connect(target_path)
            table = conn.execute("SELECT name FROM sqlite_master WHERE name='marketcode_publications'").fetchone()
            conn.close()
            self.assertIsNone(table)

    def test_actual_migration_is_idempotent_and_preserves_marketcode_progress_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.db"
            target = Database(f"sqlite:///{Path(tmp) / 'target.db'}")
            self._source(source)
            first = migrate_marketcode(source, target, dry_run=False, require_postgresql=False)
            second = migrate_marketcode(source, target, dry_run=False, require_postgresql=False)
            self.assertEqual(first.inserted, 1)
            self.assertEqual(second.inserted, 0)
            with patch.object(marketcode_repository, "database", target):
                self.assertEqual(marketcode_repository.published_days(), {7})
            with target.connect() as conn:
                status, payload = conn.execute(
                    "SELECT status, channel_statuses FROM marketcode_publications WHERE plan_day=7"
                ).fetchone()
                course_table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE name='course_lessons'"
                ).fetchone()
            self.assertEqual(status, "partial")
            self.assertEqual(json.loads(payload)["telegram"], "published:1")
            self.assertIsNone(course_table)


class PostgreSQLCompatibilityTests(unittest.TestCase):
    def test_database_context_commits_and_rolls_back_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'transactions.db'}")
            with db.connect() as conn:
                conn.execute("CREATE TABLE records (value TEXT NOT NULL)")
            with self.assertRaises(RuntimeError):
                with db.connect() as conn:
                    conn.execute("INSERT INTO records (value) VALUES (?)", ("must rollback",))
                    raise RuntimeError("stop")
            with db.connect() as conn:
                count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            self.assertEqual(count, 0)

    def test_postgresql_connection_translates_placeholders_without_touching_binary_or_json(self):
        class Raw:
            def execute(self, statement, params):
                self.statement = statement
                self.params = params
                return self

        raw = Raw()
        connection = Connection(raw, "postgresql")
        payload = (b"jpeg", '{"status":"published"}')
        connection.execute("INSERT INTO t (image_data, payload) VALUES (?, ?)", payload)
        self.assertEqual(raw.statement, "INSERT INTO t (image_data, payload) VALUES (%s, %s)")
        self.assertEqual(raw.params, payload)

    def test_course_postgresql_schema_uses_native_types_constraints_and_indexes(self):
        class Cursor:
            rowcount = 0

        class FakeConnection:
            def __init__(self):
                self.statements = []

            def execute(self, statement, params=()):
                self.statements.append(statement)
                return Cursor()

        class FakeDatabase:
            config = type("Config", (), {"backend": "postgresql"})()

            def __init__(self):
                self.connection = FakeConnection()

            @contextmanager
            def connect(self, **kwargs):
                yield self.connection

        fake = FakeDatabase()
        with patch.object(repository, "database", fake):
            repository.init_course_storage()
        schema = "\n".join(fake.connection.statements)
        self.assertIn("BIGSERIAL PRIMARY KEY", schema)
        self.assertIn("BYTEA", schema)
        self.assertIn("TIMESTAMPTZ", schema)
        self.assertIn("lesson_date DATE", schema)
        self.assertIn("UNIQUE (season_id, course_id, lesson_id, part_type, platform)", schema)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_platform_publications_status", schema)

    def test_admin_alert_stable_key_is_persistently_unique_on_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(f"sqlite:///{Path(tmp) / 'alerts.db'}")
            with patch.object(repository, "database", db):
                self.assertTrue(repository.claim_admin_alert("stable-key", "test"))
                self.assertFalse(repository.claim_admin_alert("stable-key", "test"))


if __name__ == "__main__":
    unittest.main()
