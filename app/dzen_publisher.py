import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage")
COOKIES_FILE = STORAGE_DIR / "dzen_cookies.json"


async def save_dzen_cookies() -> None:
    from playwright.async_api import async_playwright

    STORAGE_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        launch_kwargs = {"headless": False}
        if COOKIES_FILE.exists():
            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context(storage_state=str(COOKIES_FILE))
            logger.info("Loaded existing session from %s", COOKIES_FILE)
        else:
            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context()

        page = await context.new_page()
        await page.goto("https://dzen.ru")

        print("\nОткрылся браузер с Дзеном.")
        print("Войдите в аккаунт вручную, затем нажмите Enter здесь, чтобы сохранить сессию.")
        await asyncio.to_thread(input, "")

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


CHANNEL_URL = "https://dzen.ru/aibotpro163"


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


async def publish_draft(title: str, text: str) -> None:
    from playwright.async_api import async_playwright

    if not COOKIES_FILE.exists():
        raise FileNotFoundError(
            f"Файл сессии не найден: {COOKIES_FILE}. "
            "Сначала запустите save_dzen_cookies()."
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=str(COOKIES_FILE))
        page = await context.new_page()

        # ── 1. Открываем страницу канала ─────────────────────────────────────
        print(f"[1/7] Открываю канал: {CHANNEL_URL}")
        await page.goto(CHANNEL_URL, wait_until="networkidle")
        print(f"  URL: {page.url}")

        # ── 2. Кликаем на аватар (правый верхний угол) ────────────────────────
        print("[2/7] Нажимаю аватар...")
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
            # последний вариант — любая кликабельная иконка в правом углу шапки
            page.locator('header button').last,
        ], "аватар пользователя")

        # небольшая пауза, чтобы меню успело появиться
        await page.wait_for_timeout(800)

        # ── 3. Нажимаем «Создать публикацию» ─────────────────────────────────
        print("[3/7] Нажимаю «Создать публикацию»...")
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

        # ── 4. Нажимаем «Написать статью» ────────────────────────────────────
        print("[4/7] Нажимаю «Написать статью»...")
        await _click_first_visible([
            page.get_by_text("Написать статью", exact=True),
            page.get_by_text("Написать статью", exact=False),
            page.locator('[role="menuitem"]:has-text("Написать статью")'),
            page.locator('li:has-text("Написать статью")'),
            page.locator('a:has-text("Написать статью")'),
            page.locator('button:has-text("Написать статью")'),
            page.locator('span:has-text("Написать статью")'),
        ], "«Написать статью»")

        # ── 5. Ждём открытия редактора ────────────────────────────────────────
        print("[5/7] Жду редактор (URL: /profile/editor/id/.../edit)...")
        try:
            await page.wait_for_url("**/profile/editor/id/**", timeout=25000)
        except Exception:
            # Дзен может использовать другой паттерн — ждём любой /editor/
            try:
                await page.wait_for_url("**/editor/**", timeout=10000)
            except Exception:
                await page.wait_for_load_state("networkidle", timeout=15000)

        await page.wait_for_load_state("networkidle")
        print(f"  Редактор открыт: {page.url}")

        # ── 6. Заполняем заголовок ────────────────────────────────────────────
        print("[6/7] Заполняю заголовок...")
        title_el = await _wait_element([
            page.get_by_placeholder("Заголовок"),
            page.locator('[placeholder*="аголовок"]'),
            page.locator('[data-testid*="title"] [contenteditable]'),
            page.locator('[class*="title"][contenteditable="true"]'),
            page.locator('[class*="Title"][contenteditable="true"]'),
            page.locator('[contenteditable="true"]').first,
        ], "заголовок")

        await _type_into(page, title_el, title)
        print(f"  Заголовок вставлен: «{title}»")

        # ── 7. Заполняем текст ────────────────────────────────────────────────
        print("[7/7] Заполняю текст...")
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
        print("  Текст вставлен.")

        print("\nЧерновик заполнен. Кнопка публикации НЕ нажата.")
        print("Проверьте черновик в браузере. Нажмите Enter, чтобы закрыть браузер.")
        await asyncio.to_thread(input, "")

        await browser.close()
        print("Браузер закрыт.")


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
