# Хочу всё знать — ИИ. Учимся каждый день

Production-oriented Python-сервис последовательных коротких курсов по искусственному интеллекту. Первый сезон начинается 14 августа 2026 года, первый курс — «ИИ без путаницы» — содержит 15 ежедневных уроков.

Каждый урок заранее генерируется как единое целое из трёх связанных частей:

- `09:00` — **РАЗБИРАЕМ**;
- `15:00` — **ПРОБУЕМ**;
- `20:00` — **ЗАКРЕПЛЯЕМ**.

Все часы основного курса работают в `Europe/Moscow`. Случайный legacy flow и интервал раз в 6 часов сохранены в коде для безопасной миграции, но больше не зарегистрированы в scheduler.

## Архитектура

```text
curriculum/season_01.yaml … season_05.yaml
    ↓
curriculum validator + date resolver
    ↓
HTTP SourceRetriever (официальные источники)
    ↓
Course AI через OpenRouter
    ↓
quality validation трёх связанных частей
    ↓
SQLite/PostgreSQL persistent state
    ↓
09:00 / 15:00 / 20:00 cron jobs
    ↓
Telegram | MAX | VK text-only | существующий Dzen Playwright adapter
```

Основные course-модули находятся в `app/course/`:

- `curriculum.py` — строгий YAML parser и fail-fast validation;
- `sources.py` — простой mock-friendly HTTP retrieval без embeddings;
- `generator.py` — отдельный платный Course AI flow;
- `quality.py` — лимиты, связность, действия и CTA;
- `covers.py` — локальные детерминированные квадратные обложки Pillow;
- `repository.py` — lesson/part/source/platform state и idempotency;
- `service.py` — подготовка и независимая публикация платформ;
- `reconciliation.py` — restart/catch-up policy.

## Curriculum

Versioned curriculum хранится в каталоге `curriculum/` как пять файлов `season_01.yaml` — `season_05.yaml`. Он полностью покрывает каждый календарный день с 14 августа по 31 декабря 2026 года: 135 обычных уроков и 5 специальных дней. Scheduler никогда не выбирает тему случайно и определяет учебный день по текущей московской дате.

При startup загружается весь каталог. Ошибкой считаются повторные season/course/lesson/special IDs, повторные даты, календарные дыры, пропуски внутри курса, выход урока за boundaries, пустые цели или отсутствие sources.

Программа до конца 2026 года:

| Сезон | Курсы | Даты | Special days |
|---|---|---|---|
| 1 — август | 1. «ИИ без путаницы» | 14–28 августа | 29 и 30 августа — повторение; 31 августа — итоги сезона |
| 2 — сентябрь | 2. «Промпты с нуля»; 3. «Промпты на практике» | 1–15 и 16–30 сентября | нет |
| 3 — октябрь | 4. «Поиск и проверка информации с ИИ»; 5. «Документы, тексты и данные» | 1–15 и 16–30 октября | 31 октября — итоги сезона |
| 4 — ноябрь | 6. «ИИ для работы и продуктивности»; 7. «ИИ для бизнеса» | 1–15 и 16–30 ноября | нет |
| 5 — декабрь | 8. «Создание контента с ИИ»; 9. «Автоматизация и AI-агенты с нуля» | 1–15 и 16–30 декабря | 31 декабря — итоги года |

Special day — отдельный тип, а не шестнадцатый урок. Он имеет собственные тему, цели, sources и cover label, но проходит через те же retrieval, генерацию трёх частей, quality check, state, idempotency, reconciliation и publishers.

Организационная отметка: 25 декабря 2026 года запланирован редакционный пересмотр концепции и составление curriculum на 2027 год. Внешнее календарное событие кодом не создаётся.

## Подготовка и recovery

Job `prepare_course_days` в `00:10 Europe/Moscow` готовит окно `today … today+3`, то есть до четырёх curriculum days, включая special days. Та же подготовка ставится one-shot при startup. Уже generated artifact не меняется, а `needs_review` не запускает бесконечную регенерацию. Если artifact отсутствует в момент cron, сохраняется idempotent lazy prepare.

`reconcile_course_publications` выполняется при startup и каждые 10 минут:

- рассматривает только сегодняшнюю дату;
- выбирает только последнюю наступившую часть;
- разрешает catch-up не позднее `COURSE_CATCHUP_MINUTES`;
- более ранние наступившие части фиксирует как `missed` и не публикует пачкой;
- опубликованные `lesson + part + platform` пропускаются.

## Database

Поддерживаются:

- `sqlite:///...` — local development/tests;
- `postgresql://...`, `postgres://...`, `postgresql+...` — PostgreSQL через `psycopg`.

Неизвестная scheme вызывает fail-fast. PostgreSQL URL больше не может молча превратиться в локальный `bot.db`.

Новые таблицы:

- `course_lessons`;
- `lesson_parts`;
- `platform_publications`;
- `source_snapshots`.

Уникальный publication key включает season, course, lesson, part и platform. Успешная платформа не вызывается повторно; `failed` допускает отдельную повторную попытку. Таблица `admin_alerts` хранит stable alert keys и не позволяет reconciliation отправлять один и тот же alert повторно.

Перед production требуется подключить Railway PostgreSQL и передать его URL через `DATABASE_URL`. Локальный SQLite не является production-safe state.

## Course AI и sources

Default models через OpenRouter:

- `google/gemini-2.5-flash-lite`;
- fallback `google/gemini-2.5-flash`.

Course generator не использует бесплатный legacy cascade. Каждый урок grounded в source material из официальных URL curriculum. Если required source недоступен, слепая генерация запрещена. Реально использованные тексты и hashes сохраняются в `source_snapshots`.

## Обложки

Course flow не вызывает Pexels/Pixabay. Pillow создаёт отдельный JPEG `1080×1080` для каждой части. В renderer встроены пять законченных production-тем: орбиты основ, prompt-сигналы, поисковая data-grid, рабочие workflow и агентные circuits. Для сезона можно добавить override `assets/course/season_NN_base.png`, но без него используется полноценная сезонная композиция, а не технический placeholder. Все текстовые bounds валидируются внутри safe area. Обычная обложка показывает `УРОК N ИЗ 15`, special cover — `СПЕЦИАЛЬНЫЙ УРОК`, `ИТОГИ СЕЗОНА` или `ИТОГИ ГОДА`.

## Admin alerts и readiness

При включённых `COURSE_ALERTS_ENABLED` и `ADMIN_TELEGRAM_CHAT_ID` существующий Telegram bot уведомляет владельца о required-source failure, `needs_review`, полном отказе всех платформ, критической ошибке course DB и startup/curriculum failure. Stable alert key сохраняется в PostgreSQL/SQLite; одиночные ошибки платформ не создают spam.

Если alerts выключены или chat ID отсутствует, приложение продолжает работу и пишет один warning. Секреты в alert и startup summary не выводятся.

`GET /health` возвращает безопасные флаги `curriculum_loaded`, `database_ready` и `scheduler_started`. При startup логируется сводка curriculum, backend, schedule, platforms и MarketCode без URL БД, tokens или Dzen storage state.

## SQLite → PostgreSQL

Перед production switch необходимо сохранить MarketCode progress. Утилита `app.migrations.sqlite_to_postgres` открывает source `bot.db` read-only и переносит только `marketcode_publications`. Dry-run ничего не создаёт и не записывает:

```bash
python -m app.migrations.sqlite_to_postgres --source bot.db --target-url "$DATABASE_URL" --dry-run
python -m app.migrations.sqlite_to_postgres --source bot.db --target-url "$DATABASE_URL" --execute
```

Повторный execute идемпотентен по `plan_day`. Старые random-topic/image/platform histories остаются архивом в SQLite: новый scheduler их не читает. Course state перед первым launch отсутствует и не выдумывается. Подробнее: `app/migrations/README.md`.

## Platforms

- Telegram: cover и весь текст одним photo-caption сообщением (курс ограничивает текст 1000 символами, то есть оставляет запас до caption limit); message ID сохраняется.
- MAX: существующий image + text API flow.
- VK: text-only для course flow; Photos API в этой миграции не меняется.
- Dzen: используется существующий production Playwright publisher без переписывания selectors/authorization flow.

Ошибка одной платформы не блокирует остальные. Результат каждой сохраняется отдельно.

## MarketCode

MarketCode остаётся отдельным ежедневным job `publish_marketcode_article` со своими env, content plan, Gemini generation, branded cover, CTA, text-only VK и platform isolation. Его генератор и Playwright flow в course migration не переписывались.

## Запуск

```bash
python3.12 -m pip install -r requirements.txt
python3.12 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health endpoints:

```text
GET /       → {"status": "ok", "bot": "Хочу всё знать"}
GET /health → {"status": "ok"}
```

## Основные env

См. `.env.example`. Course-specific настройки:

- `COURSE_ENABLED`;
- `COURSE_TIMEZONE`;
- `COURSE_CURRICULUM_PATH`;
- `COURSE_AI_MODEL`;
- `COURSE_AI_FALLBACK_MODEL`;
- `COURSE_SOURCE_TIMEOUT`;
- `COURSE_CATCHUP_MINUTES`.
- `COURSE_PREPARE_DAYS` (`3` означает сегодня плюс следующие три дня);
- `COURSE_ALERTS_ENABLED`;
- `ADMIN_TELEGRAM_CHAT_ID`.

`POST_INTERVAL_HOURS` остаётся legacy-параметром и новым scheduler не используется.

Полный Railway checklist и будущий порядок rollout описаны в `docs/production_rollout.md`.

## Dzen operational note

Существующий Playwright publisher не изменён. Если Dzen перестал создавать/публиковать статьи и лог сообщает об отсутствии авторизованной сессии, оператор вручную обновляет `DZEN_STORAGE_STATE_JSON`. Автоматический login не выполняется; startup summary показывает только `configured/not configured`.

## Tests

Все platform calls в тестах должны быть mocked. Запуск:

```bash
.venv/bin/python -m unittest discover -s tests
```
