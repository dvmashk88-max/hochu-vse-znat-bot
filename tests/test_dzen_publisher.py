import inspect
import unittest

from app.dzen_publisher import (
    _click_final_article_publish,
    _is_public_dzen_url,
)


class _Candidate:
    def __init__(self, *, label="Опубликовать", comment=False, click_error=None):
        self.label = label
        self.comment = comment
        self.click_error = click_error
        self.clicked = False

    async def is_visible(self, timeout=None):
        return True

    async def is_disabled(self, timeout=None):
        return False

    async def evaluate(self, script):
        return self.comment

    async def inner_text(self):
        return self.label

    async def click(self, timeout=None):
        self.clicked = True
        if self.click_error:
            raise self.click_error


class _Locator:
    def __init__(self, candidates):
        self.candidates = candidates

    async def count(self):
        return len(self.candidates)

    def nth(self, index):
        return self.candidates[index]


class _Page:
    def __init__(self, candidates):
        self.candidates = candidates

    def locator(self, selector):
        if selector == '[role="dialog"] [data-testid="publish-btn"]':
            return _Locator(self.candidates)
        return _Locator([])


class DzenPublishRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_article_button_wins_when_comment_publish_also_exists(self):
        comment_publish = _Candidate(comment=True)
        article_publish = _Candidate(comment=False)
        await _click_final_article_publish(_Page([comment_publish, article_publish]))
        self.assertFalse(comment_publish.clicked)
        self.assertTrue(article_publish.clicked)

    async def test_final_selector_does_not_rank_buttons_by_geometry_or_generic_text(self):
        source = inspect.getsource(_click_final_article_publish)
        self.assertIn('data-testid="publish-btn"', source)
        self.assertNotIn("getBoundingClientRect", source)
        self.assertNotIn("get_by_text", source)

    async def test_click_transport_error_is_ambiguous_not_definitely_failed(self):
        from app.dzen_publisher import DzenPublishAmbiguousError

        candidate = _Candidate(click_error=RuntimeError("connection closed after dispatch"))
        with self.assertRaises(DzenPublishAmbiguousError):
            await _click_final_article_publish(_Page([candidate]))
        self.assertTrue(candidate.clicked)

    def test_public_article_url_must_not_be_an_editor_url(self):
        self.assertTrue(_is_public_dzen_url("https://dzen.ru/a/example-article"))
        self.assertFalse(_is_public_dzen_url("https://dzen.ru/profile/editor/id/1/edit"))


if __name__ == "__main__":
    unittest.main()
