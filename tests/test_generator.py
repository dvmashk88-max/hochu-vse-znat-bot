import unittest
from unittest.mock import Mock, patch

from app import generator


class _Response:
    def __init__(self, content: str, error: Exception | None = None):
        self._content = content
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class GeneratorTests(unittest.TestCase):
    def test_call_api_uses_primary_model_first(self):
        with patch(
            "app.generator.requests.post",
            return_value=_Response("готовый текст"),
        ) as mock_post:
            self.assertEqual(generator._call_api("prompt"), "готовый текст")

        used_model = mock_post.call_args.kwargs["json"]["model"]
        self.assertEqual(used_model, generator._PRIMARY_MODEL)

    def test_call_api_tries_free_fallback_after_primary_failure(self):
        with patch(
            "app.generator.requests.post",
            side_effect=[
                _Response("", error=RuntimeError("first failed")),
                _Response("готовый текст"),
            ],
        ) as mock_post:
            self.assertEqual(generator._call_api("prompt"), "готовый текст")

        used_models = [call.kwargs["json"]["model"] for call in mock_post.call_args_list]
        self.assertEqual(used_models[:2], [generator._PRIMARY_MODEL, generator._FREE_MODELS[0]])
        self.assertTrue(used_models[1].endswith(":free"))

    def test_rejects_paid_model_in_fallback_cascade(self):
        with self.assertRaises(ValueError):
            generator._ensure_model_cascade((generator._PRIMARY_MODEL, "anthropic/claude-3.5-haiku"))

    def test_rejects_missing_primary_model(self):
        with self.assertRaises(ValueError):
            generator._ensure_model_cascade((generator._FREE_MODELS[0],))

    def test_fit_post_length_refines_long_text(self):
        long_text = "x" * 1323
        fitted_text = "y" * 900

        with patch("app.generator._call_api", Mock(return_value=fitted_text)) as mock_call:
            result = generator._fit_post_length("Тема", long_text)

        self.assertEqual(result, fitted_text)
        mock_call.assert_called_once()

    def test_fit_post_length_hard_trims_when_model_keeps_text_too_long(self):
        long_text = "Начало. " + ("Очень длинное предложение. " * 80) + "#наука #история"

        with patch("app.generator._call_api", Mock(return_value=long_text)):
            result = generator._fit_post_length("Тема", long_text)

        self.assertLessEqual(len(result), 1200)
        self.assertIn("#наука", result)

    def test_fit_post_length_keeps_valid_text(self):
        valid_text = "x" * 900

        with patch("app.generator._call_api") as mock_call:
            result = generator._fit_post_length("Тема", valid_text)

        self.assertEqual(result, valid_text)
        mock_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
