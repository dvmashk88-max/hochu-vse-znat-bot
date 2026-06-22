import unittest
from unittest.mock import patch

from app.images import ImageCandidate, generate_image_query, _pick_best, _pixabay


class ImageQueryTests(unittest.TestCase):
    def test_ai_support_topic_gets_specific_english_query(self):
        query = generate_image_query("Как ИИ заменяет операторов поддержки")

        self.assertIn("customer support center", query)
        self.assertIn("AI assistant", query)
        self.assertNotEqual(query.lower(), "ai robot")

    def test_ai_agent_topic_gets_specific_english_query(self):
        query = generate_image_query("Почему ИИ-агенты станут личными сотрудниками каждого человека")

        self.assertIn("personal AI assistant", query)
        self.assertIn("productivity automation", query)

    def test_specific_topic_query_for_dna(self):
        self.assertEqual(
            generate_image_query("Как устроена ДНК"),
            "DNA gene editing biotechnology laboratory",
        )

    def test_fallback_keeps_topic_in_query(self):
        query = generate_image_query("Почему океан солёный")
        self.assertIn("ocean", query)

    def test_pick_best_prefers_cover_friendly_relevant_image(self):
        weak = ImageCandidate("Pexels", "https://example.com/weak.jpg", 640, 480, "abstract dark background")
        strong = ImageCandidate(
            "Pixabay",
            "https://example.com/strong.jpg",
            1800,
            1000,
            "people using artificial intelligence interface in modern office",
        )

        selected, reason = _pick_best([weak, strong], "artificial intelligence office people")

        self.assertEqual(selected, strong)
        self.assertIn("landscape cover format", reason)

    @patch("app.images.PIXABAY_API_KEY", "test-key")
    @patch("app.images.requests.get")
    def test_pixabay_returns_image_candidates(self, mock_get):
        mock_get.return_value.json.return_value = {
            "hits": [
                {
                    "largeImageURL": "https://example.com/large.jpg",
                    "webformatURL": "https://example.com/web.jpg",
                    "imageWidth": 1600,
                    "imageHeight": 900,
                    "tags": "robot, automation, warehouse",
                }
            ]
        }

        candidates = _pixabay("science")

        self.assertEqual(candidates[0].url, "https://example.com/large.jpg")
        self.assertEqual(candidates[0].source, "Pixabay")
        mock_get.return_value.raise_for_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
