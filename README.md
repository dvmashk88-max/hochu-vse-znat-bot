# Хочу всё знать — Telegram-бот

Автоматическая генерация и публикация образовательного контента в Telegram-канал с помощью AI.
Текст постов генерируется через [OpenRouter API](https://openrouter.ai), изображения — через Pexels и Pixabay.

**Требования:** Python 3.12+

## Архитектура

```
app/
  main.py           — FastAPI-приложение, точка входа
  config.py         — переменные окружения
  bot.py            — Telegram Bot API (отправка сообщений/фото)
  generator.py      — генерация текста поста через LLM
  images.py         — поиск и загрузка изображений (Pexels → Pixabay)
  db.py             — хранение тем и истории публикаций
  scheduler.py      — планировщик автопубликаций (APScheduler)
  publisher.py      — оркестрация: тема → текст → фото → публикация
  dzen_publisher.py — публикация в Дзен через Playwright
  max_publisher.py  — публикация в MAX через Bot API
  vk_publisher.py   — публикация в VK через VK API
  topic_selector.py — выбор следующей незатронутой темы

prompts/
  post_prompt.txt   — промпт для генерации поста
  style_prompt.txt  — промпт для стилизации текста
```

## Быстрый старт

```bash
# 1. Установить зависимости
python3.12 -m pip install -r requirements.txt

# 2. Создать .env из примера
cp .env.example .env

# 3. Запустить
python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Тестовая публикация вручную

```bash
python3.12 -c "import asyncio; from app.publisher import publish_next_post; asyncio.run(publish_next_post())"
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `TELEGRAM_CHANNEL_ID` | ID или @username канала |
| `OPENROUTER_API_KEY` | Ключ OpenRouter API (openrouter.ai) |
| `PEXELS_API_KEY` | Ключ Pexels API для основного поиска изображений |
| `PIXABAY_API_KEY` | Ключ Pixabay API для резервного поиска изображений |
| `DATABASE_URL` | URL базы данных (по умолчанию SQLite) |
| `POST_INTERVAL_HOURS` | Интервал публикаций в часах (по умолчанию 6) |
| `DZEN_CHANNEL_URL` | URL канала Дзена |
| `DZEN_STORAGE_STATE_JSON` | JSON-содержимое Playwright storage state для авторизации в Дзене |
| `DZEN_AUTO_PUBLISH` | Автопубликация статей в Дзен (`false` по умолчанию) |
| `DZEN_DEBUG_SCREENSHOTS` | Сохранять debug-скриншоты Дзена при публикации (`true` по умолчанию) |
| `DZEN_DEBUG_DIR` | Папка для debug-скриншотов Дзена (`storage/dzen_debug` по умолчанию) |
| `MAX_BOT_TOKEN` | Токен бота MAX |
| `MAX_CHANNEL_ID` | Числовой ID канала MAX |
| `VK_ACCESS_TOKEN` | Access token сообщества VK с правами `wall` и `photos` |
| `VK_GROUP_ID` | Числовой ID сообщества VK без минуса |

## Деплой на Railway

Проект готов к деплою через [Railway](https://railway.app). Конфигурация в `railway.json`, версия Python задана в `runtime.txt`.

1. Создать новый проект на Railway
2. Подключить репозиторий
3. Добавить переменные окружения в настройках сервиса
4. Railway установит зависимости и Chromium для Playwright через `buildCommand`
5. Railway автоматически запустит `uvicorn app.main:app`

## Дзен

Дзен работает через Playwright: заполняет статью, создаёт черновик и при `DZEN_AUTO_PUBLISH=true` нажимает кнопки публикации.

По умолчанию `DZEN_AUTO_PUBLISH=false`, поэтому Дзен только создаёт черновик. Чтобы включить автоматическую публикацию в Railway, задайте переменную окружения `DZEN_AUTO_PUBLISH=true`.

Внимание: `DZEN_AUTO_PUBLISH=true` публикует статьи в Дзен автоматически.

Для Railway нужно добавить переменную окружения `DZEN_STORAGE_STATE_JSON`. Её значение — содержимое файла `storage/dzen_cookies.json` одной строкой. Если эта переменная задана, бот использует её вместо локального файла cookies.

Локально можно использовать файл `storage/dzen_cookies.json`. Если `DZEN_STORAGE_STATE_JSON` не задана, код попробует взять сессию из этого файла.

```bash
# 1. Установить зависимости (если ещё не установлены)
python3.12 -m pip install -r requirements.txt

# 2. Установить браузер Chromium для Playwright
python3.12 -m playwright install chromium
```

Сессия хранится в `storage/dzen_cookies.json` (в `.gitignore`). Для Railway скопируйте всё содержимое этого файла в `DZEN_STORAGE_STATE_JSON` без переносов строк.

## Health check

```
GET /  → {"status": "ok", "bot": "Хочу всё знать"}
GET /health → {"status": "ok"}
```
