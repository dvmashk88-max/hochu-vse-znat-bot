import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.config import DZEN_CHANNEL_URL, DZEN_STORAGE_STATE_JSON

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage")
COOKIES_FILE = STORAGE_DIR / "dzen_cookies.json"


def _log_step(message: str) -> None:
    print(message)
    logger.info(message)


def _load_storage_state() -> dict[str, Any] | str:
    if DZEN_STORAGE_STATE_JSON:
        try:
            return json.loads(DZEN_STORAGE_STATE_JSON)
        except json.JSONDecodeError as e:
            raise ValueError("DZEN_STORAGE_STATE_JSON содержит невалидный JSON") from e

    if COOKIES_FILE.exists():
        return str(COOKIES_FILE)

    raise FileNotFoundError(
        f"Не найдена сессия Дзена. Добавьте DZEN_STORAGE_STATE_JSON в переменные окружения "
        f"или положите файл сессии в {COOKIES_FILE}."
    )


async def save_dzen_cookies(headless: bool = True) -> None:
    from playwright.async_api import async_playwright

    STORAGE_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        launch_kwargs = {"headless": headless}
        if COOKIES_FILE.exists():
            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context(storage_state=str(COOKIES_FILE))
            logger.info("Loaded existing session from %s", COOKIES_FILE)
        else:
            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context()

        page = await context.new_page()
        await page.goto("https://dzen.ru")

        await context.storage_state(path=str(COOKIES_FILE))
        logger.info("Cookies saved to %s", COOKIES_FILE)
        print(f"Сессия сохранена в {COOKIES_FILE}")

        await browser.close()


async def _type_into(page, el, text: str) -> None:
    """Пробует fill(), при неудаче — clipboard paste."""
    await el.click()
    try:
        await el.fill(text)
        logger.info("  fill() успешно.")
    except Exception:
        logger.warning("  fill() не сработал, пробуем через буфер обмена...")
        await page.evaluate(
            "(text) => navigator.clipboard.writeText(text)",
            text,
        )
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Control+v")
        logger.info("  Вставка через буфер обмена выполнена.")


async def _click_first_visible(locators: list, label: str, timeout: int = 6000):
    """Перебирает locators и кликает первый видимый. Возвращает использованный locator."""
    for loc in locators:
        try:
            el = loc.first if hasattr(loc, "first") else loc
            await el.wait_for(state="visible", timeout=timeout)
            await el.click()
            print(f"  OK: {label}")
            return el
        except Exception:
            continue
    raise RuntimeError(f"Элемент не найден: {label}")


async def _wait_element(locators: list, label: str, timeout: int = 8000):
    """Возвращает первый видимый locator из списка."""
    for loc in locators:
        try:
            el = loc.first if hasattr(loc, "first") else loc
            await el.wait_for(state="visible", timeout=timeout)
            print(f"  OK: найден элемент «{label}»")
            return el
        except Exception:
            continue
    raise RuntimeError(f"Поле не найдено: {label}")


async def publish_draft(title: str, text: str, headless: bool = True) -> None:
    from playwright.async_api import async_playwright

    storage_state = _load_storage_state()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(storage_state=storage_state)
            page = await context.new_page()

            _log_step(f"Открываю канал: {DZEN_CHANNEL_URL}")
            await page.goto(DZEN_CHANNEL_URL, wait_until="networkidle")
            logger.info("Dzen URL: %s", page.url)

            _log_step("Нажимаю аватар")
            await _click_first_visible([
                page.locator('[data-testid="user-avatar"]'),
                page.locator('[data-testid*="avatar"]'),
                page.locator('header [class*="Avatar"]'),
                page.locator('header [class*="avatar"]'),
                page.locator('header img[class*="avatar"]'),
                page.locator('[class*="UserMenu"] img'),
                page.locator('[class*="userMenu"] img'),
                page.locator('[class*="HeaderUser"]'),
                page.locator('[class*="header-user"]'),
                page.locator('header button').last,
            ], "аватар пользователя")

            await page.wait_for_timeout(800)

            _log_step("Нажимаю Создать публикацию")
            await _click_first_visible([
                page.get_by_text("Создать публикацию", exact=True),
                page.get_by_text("Создать публикацию", exact=False),
                page.locator('[role="menuitem"]:has-text("Создать публикацию")'),
                page.locator('li:has-text("Создать публикацию")'),
                page.locator('a:has-text("Создать публикацию")'),
                page.locator('button:has-text("Создать публикацию")'),
                page.locator('span:has-text("Создать публикацию")'),
            ], "«Создать публикацию»")

            await page.wait_for_timeout(600)

            _log_step("Нажимаю Написать статью")
            await _click_first_visible([
                page.get_by_text("Написать статью", exact=True),
                page.get_by_text("Написать статью", exact=False),
                page.locator('[role="menuitem"]:has-text("Написать статью")'),
                page.locator('li:has-text("Написать статью")'),
                page.locator('a:has-text("Написать статью")'),
                page.locator('button:has-text("Написать статью")'),
                page.locator('span:has-text("Написать статью")'),
            ], "«Написать статью»")

            _log_step("Жду редактор")
            try:
                await page.wait_for_url("**/profile/editor/id/**", timeout=25000)
            except Exception:
                try:
                    await page.wait_for_url("**/editor/**", timeout=10000)
                except Exception:
                    await page.wait_for_load_state("networkidle", timeout=15000)

            await page.wait_for_load_state("networkidle")
            logger.info("Dzen editor URL: %s", page.url)

            _log_step("Заполняю заголовок")
            title_el = await _wait_element([
                page.get_by_placeholder("Заголовок"),
                page.locator('[placeholder*="аголовок"]'),
                page.locator('[data-testid*="title"] [contenteditable]'),
                page.locator('[class*="title"][contenteditable="true"]'),
                page.locator('[class*="Title"][contenteditable="true"]'),
                page.locator('[contenteditable="true"]').first,
            ], "заголовок")

            await _type_into(page, title_el, title)
            logger.info("Dzen title inserted: %s", title)

            _log_step("Заполняю текст")
            body_el = await _wait_element([
                page.get_by_placeholder("Начните писать"),
                page.get_by_placeholder("Текст статьи"),
                page.locator('[placeholder*="Начните"]'),
                page.locator('[placeholder*="Текст"]'),
                page.locator('[data-testid*="body"] [contenteditable]'),
                page.locator('[data-testid*="content"] [contenteditable]'),
                page.locator('[class*="body"][contenteditable="true"]'),
                page.locator('[class*="Body"][contenteditable="true"]'),
                page.locator('[contenteditable="true"]').nth(1),
            ], "поле текста")

            await _type_into(page, body_el, text)
            _log_step("Черновик Дзена создан")
        finally:
            await browser.close()
            _log_step("Браузер закрыт")


if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "cookies":
        asyncio.run(save_dzen_cookies())
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(publish_draft(
            title="Тестовая статья Хочу всё знать",
            text="Это тестовый черновик для проверки автозаполнения Дзена. Публиковать пока не нужно.",
        ))
    else:
        print("Использование:")
        print("  python app/dzen_publisher.py cookies  — сохранить сессию")
        print("  python app/dzen_publisher.py test     — тест создания черновика")
