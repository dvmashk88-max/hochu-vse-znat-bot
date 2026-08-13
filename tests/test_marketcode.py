import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.marketcode.config import MarketCodeSettings, parse_post_time
from app.marketcode.content_plan import ContentPlanEntry, load_content_plan
from app.marketcode.generator import _cta, _generate_sync, _normalize_body, _risky_guidance
from app.marketcode.generator import GeneratedArticle
from app.marketcode import publisher as marketcode_publisher
from app.marketcode import repository
from app.marketcode import vk as marketcode_vk
from app.marketcode.image import _download_image
from app.database import Database


class MarketCodeContentPlanTests(unittest.TestCase):
    def test_plan_has_exactly_100_consecutive_days(self):
        entries = load_content_plan()

        self.assertEqual(len(entries), 100)
        self.assertEqual([entry.day for entry in entries], list(range(1, 101)))

    def test_plan_has_required_category_distribution(self):
        counts = Counter(entry.category for entry in load_content_plan())

        self.assertEqual(
            counts,
            {
                "Apple ID / App Store": 35,
                "Steam": 25,
                "Telegram": 15,
                "Gift Cards": 15,
                "Игровые товары": 10,
            },
        )

    def test_plan_rejects_non_consecutive_days(self):
        content = """# Test

## День 2
Тема: Тест
Категория: Steam
Основные поисковые запросы: тест
Цель статьи: Проверка.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "plan.md"
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_content_plan(path)


class MarketCodeGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.entry = ContentPlanEntry(
            day=1,
            topic="Как пополнить Steam",
            category="Steam",
            keywords=("пополнить Steam",),
            goal="Помочь читателю.",
        )
        self.settings = MarketCodeSettings(
            enabled=True,
            post_time="12:00",
            timezone="Europe/Moscow",
            image_url="",
            content_plan="MARKETCODE_CONTENT_PLAN.md",
            model="test/model",
            fallback_model="test/fallback",
        )

    def test_category_cta_is_natural_and_has_site_url(self):
        cta = _cta("Steam")

        self.assertIn("MarketCode Pro", cta)
        self.assertIn("Steam-пополнения", cta)
        self.assertIn("https://www.marketcode.pro", cta)
        self.assertNotIn("Купить цифровые товары", cta)

    @patch("app.marketcode.generator._call_api")
    def test_safe_generation_passes_on_first_attempt(self, mock_call):
        article_body = " ".join(["полезная"] * 330)
        mock_call.return_value = (article_body, "test/model")

        result = _generate_sync(self.entry, self.settings)

        self.assertGreaterEqual(result.word_count, 300)
        self.assertLessEqual(result.word_count, 500)
        self.assertLessEqual(len(result.full_text), 3800)
        self.assertTrue(result.body.endswith("https://www.marketcode.pro"))
        self.assertTrue(result.full_text.startswith(self.entry.topic))
        self.assertEqual(mock_call.call_count, 2)

    def test_normalization_removes_plain_duplicate_title(self):
        body = _normalize_body(f"{self.entry.topic}\n\nВступление", self.entry.topic)

        self.assertEqual(body, "Вступление")

    def test_risky_guidance_allows_do_not_use_vpn_warning(self):
        self.assertIsNone(_risky_guidance("Не используйте VPN для смены региона."))

    def test_risky_guidance_allows_not_recommended_vpn_warning(self):
        self.assertIsNone(_risky_guidance("Не рекомендуется использовать VPN для смены региона."))

    def test_risky_guidance_blocks_vpn_recommendation(self):
        self.assertEqual(_risky_guidance("Используйте VPN для смены региона."), "используйте vpn")

    @patch("app.marketcode.generator._call_api")
    def test_unsafe_first_attempt_regenerates_and_safe_version_passes(self, mock_call):
        unsafe_body = "Используйте VPN для смены региона. " + " ".join(["полезный"] * 310)
        safe_body = "Не используйте VPN для смены региона. " + " ".join(["полезный"] * 310)
        mock_call.side_effect = [
            (unsafe_body, "test/model"),
            (unsafe_body, "test/model"),
            (safe_body, "test/model"),
            (safe_body, "test/model"),
        ]

        result = _generate_sync(self.entry, self.settings)

        self.assertIn("Не используйте VPN", result.body)
        self.assertEqual(mock_call.call_count, 4)
        retry_prompt = mock_call.call_args_list[2].args[0]
        self.assertIn("MarketCode article contains risky guidance: используйте vpn", retry_prompt)
        self.assertIn(self.entry.topic, retry_prompt)
        self.assertIn(self.entry.goal, retry_prompt)

    @patch("app.marketcode.generator._call_api")
    def test_three_unsafe_attempts_return_controlled_error(self, mock_call):
        unsafe_body = "Используйте VPN для смены региона. " + " ".join(["полезный"] * 310)
        mock_call.return_value = (unsafe_body, "test/model")

        with self.assertRaisesRegex(
            ValueError,
            "failed safety validation after 3 attempts.*используйте vpn",
        ):
            _generate_sync(self.entry, self.settings)

        self.assertEqual(mock_call.call_count, 6)

    @patch("app.marketcode.generator._call_api")
    def test_generation_rejects_forbidden_payment_guidance(self, mock_call):
        for forbidden_phrase in ("Киви", "WebMoney", "Яндекс.Деньги", "банковский перевод"):
            with self.subTest(forbidden_phrase=forbidden_phrase):
                article_body = f"{forbidden_phrase} " + " ".join(["полезный"] * 310)
                mock_call.return_value = (article_body, "test/model")

                with self.assertRaisesRegex(ValueError, "forbidden payment guidance"):
                    _generate_sync(self.entry, self.settings)

    @patch("app.marketcode.generator._call_api")
    def test_generation_allows_neutral_marketcode_payment_phrase(self, mock_call):
        article_body = (
            "Оплата производится удобным способом на сайте MarketCode Pro. "
            + " ".join(["полезный"] * 310)
        )
        mock_call.return_value = (article_body, "test/model")

        result = _generate_sync(self.entry, self.settings)

        self.assertIn("Оплата производится удобным способом", result.body)

    def test_post_time_validation(self):
        self.assertEqual(parse_post_time("12:00"), (12, 0))
        with self.assertRaises(ValueError):
            parse_post_time("25:00")

    def test_final_brand_cover_can_be_loaded_locally(self):
        image = _download_image("assets/marketcode/marketcode_cover.png")

        self.assertGreater(len(image), 10_000)


class MarketCodeRepositoryTests(unittest.TestCase):
    def test_failed_day_is_retryable_and_successful_retry_is_consumed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "marketcode.db")
            with patch.object(repository, "database", Database(f"sqlite:///{db_path}")):
                repository.save_publication(
                    plan_day=1,
                    topic="Тема",
                    category="Steam",
                    word_count=1600,
                    model="test/model",
                    channel_statuses={"telegram": "failed: test", "max": "failed: test"},
                )
                self.assertNotIn(1, repository.published_days())

                repository.save_publication(
                    plan_day=1,
                    topic="Тема",
                    category="Steam",
                    word_count=1600,
                    model="test/model",
                    channel_statuses={"telegram": "published: ok", "max": "published: ok"},
                )
                self.assertIn(1, repository.published_days())


class MarketCodePublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_vk_failure_does_not_block_other_channels(self):
        settings = MarketCodeSettings(
            enabled=True,
            post_time="12:00",
            timezone="Europe/Moscow",
            image_url="assets/marketcode/marketcode_cover.png",
            content_plan="MARKETCODE_CONTENT_PLAN.md",
            model="test/model",
            fallback_model="test/fallback",
        )
        entry = load_content_plan()[0]
        article = GeneratedArticle(entry.topic, "Полезный текст", 300, "test/model")

        with (
            patch.object(marketcode_publisher, "load_settings", return_value=settings),
            patch.object(marketcode_publisher, "_next_entry", return_value=entry),
            patch.object(
                marketcode_publisher,
                "generate_article",
                new=AsyncMock(return_value=article),
            ),
            patch.object(
                marketcode_publisher,
                "fetch_brand_cover",
                new=AsyncMock(return_value=b"image-bytes"),
            ),
            patch.object(marketcode_publisher, "send_photo_with_caption", new=AsyncMock()) as send_cover,
            patch.object(marketcode_publisher, "send_text", new=AsyncMock()) as send_text,
            patch.object(
                marketcode_publisher,
                "publish_to_max",
                new=AsyncMock(return_value="max-id"),
            ) as publish_max,
            patch.object(
                marketcode_publisher,
                "publish_marketcode_to_vk",
                new=AsyncMock(side_effect=RuntimeError("VK wall.post rejected")),
            ) as publish_vk,
            patch.object(
                marketcode_publisher,
                "publish_draft",
                new=AsyncMock(return_value="dzen-id"),
            ) as publish_dzen,
            patch.object(marketcode_publisher, "save_publication") as save_publication,
        ):
            await marketcode_publisher.publish_marketcode_article()

        send_cover.assert_awaited_once_with(
            marketcode_publisher.TELEGRAM_CHANNEL_ID,
            b"image-bytes",
            "",
        )
        send_text.assert_awaited_once_with(
            marketcode_publisher.TELEGRAM_CHANNEL_ID,
            article.full_text,
        )
        publish_max.assert_awaited_once_with(text=article.full_text, image_bytes=b"image-bytes")
        publish_vk.assert_awaited_once_with(text=article.full_text)
        publish_dzen.assert_awaited_once_with(
            title=article.title,
            text=article.body,
            image_bytes=b"image-bytes",
        )
        statuses = save_publication.call_args.kwargs["channel_statuses"]
        self.assertTrue(statuses["telegram"].startswith("published"))
        self.assertTrue(statuses["max"].startswith("published"))
        self.assertEqual(statuses["vk"], "failed: VK wall.post rejected")
        self.assertTrue(statuses["dzen"].startswith("published"))

    async def test_article_is_not_split_for_any_channel(self):
        entry = ContentPlanEntry(
            day=1,
            topic="Как пополнить Steam",
            category="Steam",
            keywords=("пополнить Steam",),
            goal="Помочь читателю.",
        )
        settings = MarketCodeSettings(
            enabled=True,
            post_time="12:00",
            timezone="Europe/Moscow",
            image_url="assets/marketcode/marketcode_cover.png",
            content_plan="MARKETCODE_CONTENT_PLAN.md",
            model="test/model",
            fallback_model="test/fallback",
        )
        article = GeneratedArticle(
            title=entry.topic,
            body="Полезный текст\n\nhttps://www.marketcode.pro",
            word_count=6,
            model="test/model",
        )

        with (
            patch.object(marketcode_publisher, "load_settings", return_value=settings),
            patch.object(marketcode_publisher, "_next_entry", return_value=entry),
            patch.object(
                marketcode_publisher,
                "generate_article",
                new=AsyncMock(return_value=article),
            ),
            patch.object(
                marketcode_publisher,
                "fetch_brand_cover",
                new=AsyncMock(return_value=b"image-bytes"),
            ),
            patch.object(
                marketcode_publisher,
                "send_photo_with_caption",
                new=AsyncMock(),
            ) as send_cover,
            patch.object(marketcode_publisher, "send_text", new=AsyncMock()) as send_text,
            patch.object(
                marketcode_publisher,
                "publish_to_max",
                new=AsyncMock(return_value="max-id"),
            ) as publish_max,
            patch.object(
                marketcode_publisher,
                "publish_marketcode_to_vk",
                new=AsyncMock(return_value="vk-id"),
            ) as publish_vk,
            patch.object(
                marketcode_publisher,
                "publish_draft",
                new=AsyncMock(return_value="dzen-id"),
            ) as publish_dzen,
            patch.object(marketcode_publisher, "save_publication"),
        ):
            await marketcode_publisher.publish_marketcode_article()

        send_cover.assert_awaited_once_with(
            marketcode_publisher.TELEGRAM_CHANNEL_ID,
            b"image-bytes",
            "",
        )
        send_text.assert_awaited_once_with(
            marketcode_publisher.TELEGRAM_CHANNEL_ID,
            article.full_text,
        )
        publish_max.assert_awaited_once_with(text=article.full_text, image_bytes=b"image-bytes")
        publish_vk.assert_awaited_once_with(text=article.full_text)
        publish_dzen.assert_awaited_once_with(
            title=article.title,
            text=article.body,
            image_bytes=b"image-bytes",
        )


class MarketCodeVkTests(unittest.TestCase):
    def test_publish_uses_wall_post_without_image_attachment(self):
        with (
            patch.object(marketcode_vk, "_require_group_id", return_value=123),
            patch.object(marketcode_vk, "_call_vk", return_value={"post_id": 456}) as call_vk,
        ):
            result = marketcode_vk._publish("MarketCode text\n\nhttps://www.marketcode.pro")

        self.assertEqual(result, "-123_456")
        call_vk.assert_called_once_with(
            "wall.post",
            {
                "owner_id": -123,
                "from_group": 1,
                "message": "MarketCode text\n\nhttps://www.marketcode.pro",
            },
        )


if __name__ == "__main__":
    unittest.main()
