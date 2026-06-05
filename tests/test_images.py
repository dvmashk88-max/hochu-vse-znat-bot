import unittest
from unittest.mock import patch

from app.images import generate_image_query, _pick_url


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


if __name__ == "__main__":
    unittest.main()
