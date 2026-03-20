from types import SimpleNamespace
from unittest import TestCase

from core.services import browser_posting


class FakeLocator:
    def __init__(self, *, count=1, visible=True, attrs=None):
        self._count = count
        self._visible = visible
        self._attrs = attrs or {}
        self.clicked = False
        self.scrolled = False

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def is_visible(self):
        return self._visible

    def get_attribute(self, name):
        return self._attrs.get(name)

    def scroll_into_view_if_needed(self, timeout=None):
        self.scrolled = True

    def click(self, timeout=None):
        self.clicked = True


class FakeKeyboard:
    def __init__(self):
        self.presses = []

    def press(self, combo):
        self.presses.append(combo)


class FakeExpectResponse:
    def __init__(self, page):
        self.page = page

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        result = self.page.expect_results.pop(0)
        if result == 'timeout':
            raise browser_posting.PlaywrightTimeoutError('timeout')
        return False

    @property
    def value(self):
        return self.page.response


class FakePage:
    def __init__(self, locators, expect_results):
        self.locators = locators
        self.expect_results = list(expect_results)
        self.response = SimpleNamespace(status=200)
        self.keyboard = FakeKeyboard()
        self.waits = []

    def locator(self, selector):
        return self.locators.get(selector, FakeLocator(count=0))

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    def expect_response(self, predicate, timeout):
        return FakeExpectResponse(self)


class BrowserPostingTests(TestCase):
    def test_click_post_button_skips_disabled_candidates(self):
        disabled = FakeLocator(attrs={'aria-disabled': 'true'})
        enabled = FakeLocator()
        page = FakePage(
            {
                browser_posting.POST_BUTTON_SELECTORS[0]: disabled,
                browser_posting.POST_BUTTON_SELECTORS[1]: enabled,
            },
            expect_results=[],
        )

        selector = browser_posting._click_post_button(page, timeout_ms=250)

        self.assertEqual(selector, browser_posting.POST_BUTTON_SELECTORS[1])
        self.assertFalse(disabled.clicked)
        self.assertTrue(enabled.clicked)

    def test_dispatch_post_falls_back_to_keyboard_submit(self):
        enabled = FakeLocator()
        page = FakePage(
            {
                browser_posting.POST_BUTTON_SELECTORS[0]: enabled,
            },
            expect_results=['timeout', 'success'],
        )

        response = browser_posting._dispatch_post(page, timeout_ms=500)

        self.assertIs(response, page.response)
        self.assertTrue(enabled.clicked)
        self.assertEqual(page.keyboard.presses, ['Control+Enter'])
