# Хочу всё знать — Telegram-бот

Автоматическая генерация и публикация образовательного контента в Telegram-канал с помощью AI.
Текст постов генерируется через [OpenRouter API](https://openrouter.ai), изображения — через Unsplash и Pexels.

**Требования:** Python 3.12+

## Архитектура

```
app/
  main.py           — FastAPI-приложение, точка входа
  config.py         — переменные окружения
  bot.py            — Telegram Bot API (отправка сообщений/фото)
  generator.py      — генерация текста поста через LLM
  images.py         — поиск и загрузка изображений (Unsplash → Pexels)
  db.py             — хранение тем и истории публикаций
  scheduler.py      — планировщик автопубликаций (APScheduler)
  publisher.py      — оркестрация: тема → текст → фото → публикация
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
| `UNSPLASH_ACCESS_KEY` | Access Key от Unsplash API |
| `PEXELS_API_KEY` | Ключ Pexels API для резервного поиска изображений |
| `DATABASE_URL` | URL базы данных (по умолчанию SQLite) |
| `POST_INTERVAL_HOURS` | Интервал публикаций в часах (по умолчанию 6) |

## Деплой на Railway

Проект готов к деплою через [Railway](https://railway.app). Конфигурация в `railway.json`, версия Python задана в `runtime.txt`.

1. Создать новый проект на Railway
2. Подключить репозиторий
3. Добавить переменные окружения в настройках сервиса
4. Railway автоматически запустит `uvicorn app.main:app`

## Health check

```
GET /  → {"status": "ok", "bot": "Хочу всё знать"}
GET /health → {"status": "ok"}
```
