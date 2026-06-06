import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import (
    DZEN_AUTO_PUBLISH,
    DZEN_CHANNEL_URL,
    DZEN_DEBUG_DIR,
    DZEN_DEBUG_SCREENSHOTS,
    DZEN_STORAGE_STATE_JSON,
)

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage")
COOKIES_FILE = STORAGE_DIR / "dzen_cookies.json"
DEBUG_DIR = Path(DZEN_DEBUG_DIR)


def _log_step(message: str) -> None:
    print(message)
    logger.info(message)


def _safe_artifact_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.lower())
    return "_".join(part for part in cleaned.split("_") if part)[:80] or "dzen"


async def _save_debug_screenshot(page, name: str) -> None:
    if not DZEN_DEBUG_SCREENSHOTS:
        return

    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = DEBUG_DIR / f"{stamp}_{_safe_artifact_name(name)}.png"
        await page.screenshot(path=str(path), full_page=True)
        logger.info("Dzen debug screenshot saved: %s", path)
    except Exception as e:
        logger.warning("Не удалось сохранить debug-скриншот Дзена: %s", e)


async def _log_visible_controls(page, label: str) -> None:
    try:
        controls = await page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.visibility !== 'hidden'
                        && style.display !== 'none'
                        && rect.width > 0
                        && rect.height > 0;
                };
                return Array.from(document.querySelectorAll('button, [role="button"], a, input[type="file"]'))
                    .filter(isVisible)
                    .slice(0, 80)
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        return {
                            tag: el.tagName.toLowerCase(),
                            text: text.slice(0, 90),
                            aria: (el.getAttribute('aria-label') || '').slice(0, 90),
                            title: (el.getAttribute('title') || '').slice(0, 90),
                            testid: (el.getAttribute('data-testid') || '').slice(0, 90),
                            type: (el.getAttribute('type') || '').slice(0, 40),
                            disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                        };
                    });
            }
            """
        )
        logger.info("Dzen visible controls at %s: %s", label, json.dumps(controls, ensure_ascii=False))
    except Exception as e:
        logger.warning("Не удалось собрать список кнопок Дзена (%s): %s", label, e)


def _page_from_locators(locators: list):
    for loc in locators:
        page = getattr(loc, "page", None)
        if callable(page):
            page = page()
        if page:
            return page
    return None


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
    await _dismiss_editor_popups(page)
    try:
        await el.click(timeout=8000)
    except Exception:
        await _dismiss_editor_popups(page)
        await el.click(timeout=8000, force=True)
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


async def _dismiss_editor_popups(page) -> None:
    """Закрывает подсказки редактора Дзена, которые перекрывают поле статьи."""
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    except Exception:
        pass

    close_locators = [
        page.get_by_role("button", name="Понятно", exact=True),
        page.get_by_role("button", name="Закрыть", exact=True),
        page.get_by_role("button", name="Продолжить", exact=True),
        page.locator('button:has-text("Понятно")'),
        page.locator('button:has-text("Закрыть")'),
        page.locator('[aria-label="Закрыть"]'),
        page.locator('[aria-label*="закры"]'),
        page.locator('.ReactModal__Overlay--after-open button').last,
    ]

    for loc in close_locators:
        try:
            el = loc.first if hasattr(loc, "first") else loc
            if await el.is_visible(timeout=700):
                await el.click(timeout=1500, force=True)
                await page.wait_for_timeout(300)
                logger.info("  Всплывающее окно редактора закрыто.")
                break
        except Exception:
            continue

    try:
        await page.evaluate(
            """
            () => {
                for (const overlay of document.querySelectorAll('.ReactModal__Overlay')) {
                    const text = (overlay.innerText || '').toLowerCase();
                    const className = overlay.className || '';
                    if (className.includes('help-popup') || text.includes('подсказ') || text.includes('помощ')) {
                        const portal = overlay.closest('.ReactModalPortal');
                        (portal || overlay).remove();
                    }
                }
                document.body.style.overflow = '';
            }
            """
        )
    except Exception:
        pass


async def _click_first_visible(locators: list, label: str, timeout: int = 6000):
    """Перебирает locators и кликает первый видимый. Возвращает использованный locator."""
    for idx, loc in enumerate(locators, start=1):
        try:
            el = loc.first if hasattr(loc, "first") else loc
            await el.wait_for(state="visible", timeout=timeout)
            await el.click()
            print(f"  OK: {label}")
            logger.info("  Clicked %s locator #%s", label, idx)
            return el
        except Exception:
            continue
    page = _page_from_locators(locators)
    if page:
        await _save_debug_screenshot(page, f"missing_{label}")
        await _log_visible_controls(page, f"missing {label}")
    raise RuntimeError(f"Элемент не найден: {label}")


async def _click_first_enabled(locators: list, label: str, timeout: int = 6000):
    """Перебирает locators и кликает первый видимый включенный элемент."""
    for idx, loc in enumerate(locators, start=1):
        try:
            el = loc.first if hasattr(loc, "first") else loc
            await el.wait_for(state="visible", timeout=timeout)
            if await el.is_disabled(timeout=700):
                logger.info("  Locator #%s for %s is disabled", idx, label)
                continue
            await el.click()
            print(f"  OK: {label}")
            logger.info("  Clicked %s locator #%s", label, idx)
            return el
        except Exception:
            continue
    page = _page_from_locators(locators)
    if page:
        await _save_debug_screenshot(page, f"missing_or_disabled_{label}")
        await _log_visible_controls(page, f"missing or disabled {label}")
    raise RuntimeError(f"Элемент не найден или выключен: {label}")


async def _wait_element(locators: list, label: str, timeout: int = 8000):
    """Возвращает первый видимый locator из списка."""
    for idx, loc in enumerate(locators, start=1):
        try:
            el = loc.first if hasattr(loc, "first") else loc
            await el.wait_for(state="visible", timeout=timeout)
            print(f"  OK: найден элемент «{label}»")
            logger.info("  Found %s locator #%s", label, idx)
            return el
        except Exception:
            continue
    page = _page_from_locators(locators)
    if page:
        await _save_debug_screenshot(page, f"missing_field_{label}")
        await _log_visible_controls(page, f"missing field {label}")
    raise RuntimeError(f"Поле не найдено: {label}")


def _save_temp_image(image_bytes: bytes) -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    try:
        tmp.write(image_bytes)
        return Path(tmp.name)
    finally:
        tmp.close()


async def _upload_image_file(page, image_path: Path) -> bool:
    upload_buttons = [
        page.get_by_role("button", name="Добавить изображение", exact=False),
        page.get_by_role("button", name="Добавить картинку", exact=False),
        page.get_by_role("button", name="Изображение", exact=False),
        page.get_by_role("button", name="Картинка", exact=False),
        page.get_by_role("button", name="Фото", exact=False),
        page.get_by_label("Добавить изображение", exact=False),
        page.get_by_label("Добавить картинку", exact=False),
        page.get_by_label("Изображение", exact=False),
        page.get_by_label("Картинка", exact=False),
        page.get_by_label("Фото", exact=False),
        page.locator('button[aria-label*="изображ" i]'),
        page.locator('button[aria-label*="картин" i]'),
        page.locator('button[aria-label*="фото" i]'),
        page.locator('[role="button"][aria-label*="изображ" i]'),
        page.locator('[role="button"][aria-label*="картин" i]'),
        page.locator('[role="button"][aria-label*="фото" i]'),
        page.locator('button:has(svg)').filter(has_text="").last,
    ]

    for input_loc in [
        page.locator('input[type="file"][accept*="image"]').last,
        page.locator('input[type="file"]').last,
    ]:
        try:
            if await input_loc.count() > 0:
                await input_loc.set_input_files(str(image_path))
                logger.info("Dzen image file attached through input[type=file]")
                return True
        except Exception:
            continue

    for idx, loc in enumerate(upload_buttons, start=1):
        try:
            el = loc.first if hasattr(loc, "first") else loc
            await el.wait_for(state="visible", timeout=2000)
            async with page.expect_file_chooser(timeout=4000) as fc_info:
                await el.click(timeout=2000, force=True)
            file_chooser = await fc_info.value
            await file_chooser.set_files(str(image_path))
            logger.info("Dzen image file attached through upload button #%s", idx)
            return True
        except Exception:
            continue

    return False


async def _wait_image_uploaded(page) -> bool:
    for loc in [
        page.locator('article img, [contenteditable="true"] img').first,
        page.locator('img[src^="blob:"], img[src^="data:"], img[src*="avatars"], img[src*="zen"]').first,
        page.locator('[class*="image" i], [class*="Image" i]').first,
    ]:
        try:
            await loc.wait_for(state="visible", timeout=15000)
            return True
        except Exception:
            continue
    return False


async def _click_publish_fallback_button(page, label: str, pattern: str) -> bool:
    clicked = await page.evaluate(
        """
        ({ label, pattern }) => {
            const re = new RegExp(pattern, 'i');
            const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.visibility !== 'hidden'
                    && style.display !== 'none'
                    && rect.width > 0
                    && rect.height > 0;
            };
            const isEnabled = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true';
            const textOf = (el) => [
                el.innerText,
                el.textContent,
                el.getAttribute('aria-label'),
                el.getAttribute('title'),
                el.getAttribute('data-testid'),
                el.getAttribute('class'),
            ].filter(Boolean).join(' ');

            const controls = Array.from(document.querySelectorAll('button, [role="button"]'))
                .filter((el) => isVisible(el) && isEnabled(el));

            let target = controls.find((el) => re.test(textOf(el)));
            if (!target) {
                const width = window.innerWidth || document.documentElement.clientWidth;
                const height = window.innerHeight || document.documentElement.clientHeight;
                const positioned = controls
                    .map((el) => ({ el, rect: el.getBoundingClientRect(), text: textOf(el) }))
                    .filter(({ rect }) => (
                        rect.x > width * 0.55
                        && (rect.y < 180 || rect.y > height - 220)
                        && rect.width >= 20
                        && rect.height >= 20
                    ))
                    .sort((a, b) => (b.rect.x + b.rect.y) - (a.rect.x + a.rect.y));
                target = positioned[0]?.el;
            }

            if (!target) {
                return false;
            }
            target.click();
            return true;
        }
        """,
        {"label": label, "pattern": pattern},
    )
    if clicked:
        logger.info("  Clicked %s by JS fallback", label)
        print(f"  OK: {label}")
        return True
    return False


async def _insert_header_image(page, body_el, image_bytes: bytes | None) -> bool:
    if not image_bytes:
        logger.info("Картинка для Дзена не передана, публикуем только текст")
        return False

    image_path = _save_temp_image(image_bytes)
    try:
        _log_step("Добавляю картинку в Дзен")
        await _dismiss_editor_popups(page)
        await body_el.click(timeout=5000, force=True)
        await page.wait_for_timeout(400)

        uploaded = await _upload_image_file(page, image_path)
        if not uploaded:
            logger.warning("Не удалось найти кнопку/поле загрузки картинки в редакторе Дзена")
            await _save_debug_screenshot(page, "dzen_image_upload_control_missing")
            await _log_visible_controls(page, "image upload control missing")
            return False

        if not await _wait_image_uploaded(page):
            logger.warning("Картинка была передана в Дзен, но загрузка не подтвердилась по DOM")
            await _save_debug_screenshot(page, "dzen_image_upload_not_confirmed")
            await _log_visible_controls(page, "image upload not confirmed")
            return False

        await _save_debug_screenshot(page, "dzen_image_uploaded")
        _log_step("Картинка добавлена в начало статьи Дзена")
        return True
    except Exception as e:
        logger.warning("Не удалось добавить картинку в Дзен: %s", e)
        return False
    finally:
        try:
            image_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Не удалось удалить временный файл картинки: %s", image_path)


async def _append_text_after_media(page, body_el, text: str) -> None:
    await _dismiss_editor_popups(page)
    try:
        await body_el.click(timeout=8000, force=True)
        await page.keyboard.press("Control+End")
        await page.keyboard.press("Enter")
        await page.keyboard.insert_text(text)
        logger.info("  Текст вставлен после картинки.")
    except Exception:
        logger.warning("  Не удалось вставить текст после картинки, пробуем обычный ввод...")
        await _type_into(page, body_el, text)


async def _published_or_left_editor(page) -> bool:
    try:
        await page.wait_for_url(lambda url: "/editor/" not in url and "/profile/editor/" not in url, timeout=15000)
        return True
    except Exception:
        pass

    for loc in [
        page.get_by_text("опублик", exact=False),
        page.get_by_text("публикация создана", exact=False),
        page.get_by_text("статья опубликована", exact=False),
    ]:
        try:
            if await loc.first.is_visible(timeout=1200):
                return True
        except Exception:
            continue
    return False


async def _auto_publish_article(page) -> None:
    _log_step("Автопубликация Дзена включена")
    await _dismiss_editor_popups(page)
    await _save_debug_screenshot(page, "before_dzen_next")
    await _log_visible_controls(page, "before next")

    _log_step("Нажимаю Далее")
    try:
        await _click_first_enabled([
            page.get_by_role("button", name="Далее", exact=True),
            page.get_by_role("button", name="Далее", exact=False),
            page.get_by_role("button", name="Продолжить", exact=True),
            page.get_by_role("button", name="Продолжить", exact=False),
            page.get_by_label("Далее", exact=False),
            page.get_by_label("Продолжить", exact=False),
            page.locator('button:has-text("Далее")'),
            page.locator('[role="button"]:has-text("Далее")'),
            page.locator('button:has-text("Продолжить")'),
            page.locator('[role="button"]:has-text("Продолжить")'),
            page.locator('button[aria-label*="далее" i]'),
            page.locator('[role="button"][aria-label*="далее" i]'),
            page.locator('button[title*="далее" i]'),
            page.locator('[role="button"][title*="далее" i]'),
            page.locator('button[aria-label*="next" i]'),
            page.locator('[role="button"][aria-label*="next" i]'),
            page.locator('button[title*="next" i]'),
            page.locator('[role="button"][title*="next" i]'),
            page.locator('[data-testid*="next" i]'),
            page.locator('[data-testid*="publish" i] button').last,
            page.locator('button[type="submit"]').last,
        ], "кнопка «Далее» для публикации")
    except RuntimeError:
        if not await _click_publish_fallback_button(
            page,
            "кнопка «Далее» для публикации",
            "далее|продолж|next|publish|публик|arrow|submit",
        ):
            raise

    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        await page.wait_for_timeout(2000)

    await _dismiss_editor_popups(page)
    await _save_debug_screenshot(page, "before_dzen_publish")
    await _log_visible_controls(page, "before publish")

    _log_step("Нажимаю Опубликовать")
    try:
        await _click_first_enabled([
            page.get_by_role("button", name="Опубликовать", exact=True),
            page.get_by_role("button", name="Опубликовать", exact=False),
            page.get_by_role("button", name="Опубликовать сейчас", exact=False),
            page.get_by_role("button", name="Разместить", exact=False),
            page.get_by_label("Опубликовать", exact=False),
            page.get_by_label("Разместить", exact=False),
            page.locator('button:has-text("Опубликовать")'),
            page.locator('[role="button"]:has-text("Опубликовать")'),
            page.locator('button:has-text("Разместить")'),
            page.locator('[role="button"]:has-text("Разместить")'),
            page.locator('button[aria-label*="публик" i]'),
            page.locator('[role="button"][aria-label*="публик" i]'),
            page.locator('button[title*="публик" i]'),
            page.locator('[role="button"][title*="публик" i]'),
            page.locator('button[aria-label*="размест" i]'),
            page.locator('[role="button"][aria-label*="размест" i]'),
            page.locator('button[title*="размест" i]'),
            page.locator('[role="button"][title*="размест" i]'),
            page.locator('[data-testid*="publish" i]'),
            page.locator('button[type="submit"]').last,
            page.locator('footer button').last,
            page.locator('[class*="footer" i] button').last,
            page.locator('[class*="publish" i] button').last,
        ], "финальная кнопка «Опубликовать»")
    except RuntimeError:
        if not await _click_publish_fallback_button(
            page,
            "финальная кнопка «Опубликовать»",
            "опубликов|размест|publish|submit",
        ):
            raise

    if not await _published_or_left_editor(page):
        await _save_debug_screenshot(page, "dzen_publish_not_confirmed")
        await _log_visible_controls(page, "publish not confirmed")
        raise RuntimeError("После клика по публикации статья осталась в редакторе Дзена")

    _log_step("Статья опубликована в Дзене")


async def publish_draft(
    title: str,
    text: str,
    headless: bool = True,
    image_bytes: bytes | None = None,
) -> str:
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
            await _dismiss_editor_popups(page)

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
            await _dismiss_editor_popups(page)

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

            image_inserted = await _insert_header_image(page, body_el, image_bytes)
            if image_inserted:
                await _append_text_after_media(page, body_el, text)
            else:
                await _type_into(page, body_el, text)

            await page.wait_for_timeout(500)
            body_text = await page.locator('[contenteditable="true"]').last.inner_text()
            if len(body_text.strip()) < min(20, len(text.strip())):
                raise RuntimeError("Текст статьи не появился в редакторе Дзена")

            if not DZEN_AUTO_PUBLISH:
                _log_step("Черновик Дзена создан")
                return "draft"

            await _auto_publish_article(page)
            return "published"
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
