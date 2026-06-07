import unittest
from unittest.mock import patch

from app.images import generate_image_query, _pick_url, _pixabay


class ImageQueryTests(unittest.TestCase):
    def test_specific_topic_query_for_gps(self):
        self.assertEqual(
            generate_image_query("Как работает GPS"),
            "GPS satellite navigation technology map",
        )

    def test_specific_topic_query_for_dna(self):
        self.assertEqual(
            generate_image_query("Как устроена ДНК"),
            "DNA gene editing biotechnology laboratory",
        )

    def test_fallback_keeps_topic_in_query(self):
        query = generate_image_query("Почему океан солёный")
        self.assertIn("ocean", query)

    def test_pick_url_randomizes_from_candidates(self):
        with patch("app.images.random.choice", return_value="second"):
            self.assertEqual(_pick_url(["first", "second"]), "second")

    @patch("app.images.PIXABAY_API_KEY", "test-key")
    @patch("app.images.random.choice", return_value="https://example.com/large.jpg")
    @patch("app.images.requests.get")
    def test_pixabay_picks_large_image_url(self, mock_get, _mock_choice):
        mock_get.return_value.json.return_value = {
            "hits": [
                {
                    "largeImageURL": "https://example.com/large.jpg",
                    "webformatURL": "https://example.com/web.jpg",
                }
            ]
        }

        self.assertEqual(_pixabay("science"), "https://example.com/large.jpg")
        mock_get.return_value.raise_for_status.assert_called_once()


if __name__ == "__main__":
    unittest.main()
