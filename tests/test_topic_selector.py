import unittest
from unittest.mock import AsyncMock, patch

from app.topic_selector import (
    _is_acceptable_generated_topic,
    _is_too_similar,
    _selection_from_candidate,
    pick_next_topic,
)


class TopicSelectorTests(unittest.IsolatedAsyncioTestCase):
    def test_rejects_similar_recent_topic(self):
        similar, published_topic = _is_too_similar(
            "Почему старые книги пахнут ванилью",
            ["Откуда у старых книг запах ванили"],
        )

        self.assertTrue(similar)
        self.assertEqual(published_topic, "Откуда у старых книг запах ванили")

    def test_rejects_popular_generated_topic(self):
        ok, reason = _is_acceptable_generated_topic(
            "Как работают чёрные дыры внутри галактик",
            [],
        )

        self.assertFalse(ok)
        self.assertEqual(reason, "popular topic fragment")

    def test_rejects_history_without_modern_relevance(self):
        ok, reason = _is_acceptable_generated_topic(
            "Как древние мореплаватели ориентировались по звёздам",
            [],
        )

        self.assertFalse(ok)
        self.assertEqual(reason, "history topic without modern relevance")

    def test_sanitizes_combined_generated_category(self):
        selection = _selection_from_candidate({
            "title": "Как стартапы используют AI для рекламы",
            "category": "startup|business_ai|ai",
        })

        self.assertEqual(selection.category, "business_ai")

    @patch("app.topic_selector.get_published_topics", return_value=[])
    @patch("app.topic_selector.get_recent_published_topics", return_value=[])
    @patch("app.topic_selector.generate_topic_candidate", new_callable=AsyncMock)
    async def test_pick_next_topic_uses_generated_unique_topic(
        self,
        mock_generate_topic_candidate,
        _mock_recent,
        _mock_published,
    ):
        mock_generate_topic_candidate.return_value = {
            "title": "Как ИИ-агенты помогают малому бизнесу отвечать клиентам ночью",
            "category": "business_ai",
            "angle": "показывает практический кейс автоматизации без большой команды",
            "keywords": ["ии-агенты", "малый бизнес", "поддержка клиентов"],
        }

        selected_topic = await pick_next_topic()

        self.assertEqual(
            selected_topic.title,
            "Как ИИ-агенты помогают малому бизнесу отвечать клиентам ночью",
        )
        self.assertEqual(selected_topic.category, "business_ai")
        self.assertEqual(selected_topic.keywords, ("ии-агенты", "малый бизнес", "поддержка клиентов"))
        _mock_recent.assert_called_with(80, days=30)


if __name__ == "__main__":
    unittest.main()
