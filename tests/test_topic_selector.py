import unittest
from unittest.mock import AsyncMock, patch

from app.topic_selector import (
    _is_acceptable_generated_topic,
    _is_too_similar,
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
            "title": "Почему римский бетон крепнет в морской воде",
            "category": "history",
            "angle": "древняя технология материалов",
            "keywords": ["римский бетон", "морская вода", "вулканический пепел"],
        }

        selected_topic = await pick_next_topic()

        self.assertEqual(selected_topic.title, "Почему римский бетон крепнет в морской воде")
        self.assertEqual(selected_topic.category, "history")
        self.assertEqual(selected_topic.keywords, ("римский бетон", "морская вода", "вулканический пепел"))


if __name__ == "__main__":
    unittest.main()
