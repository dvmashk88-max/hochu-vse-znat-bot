# Production rollout checklist

Документ описывает будущий rollout. Никакие Railway/Git/production-операции этой документацией автоматически не выполняются.

## Railway environment

| ENV | Required? | Existing likely? | New? | Default | Purpose | Secret? | Must set before first deploy? |
|---|---|---|---|---|---|---|---|
| `DATABASE_URL` | Да | Нет для нового PostgreSQL | Да | local SQLite | Course и MarketCode persistent state | Да | Да |
| `OPENROUTER_API_KEY` | Да | Вероятно да | Нет | — | Course AI и MarketCode AI | Да | Да |
| `TELEGRAM_BOT_TOKEN` | Да | Вероятно да | Нет | — | Telegram publisher и admin alerts | Да | Да |
| `TELEGRAM_CHANNEL_ID` | Да | Вероятно да | Нет | — | Course/MarketCode Telegram channel | Нет | Да |
| `COURSE_ENABLED` | Да | Нет | Да | `true` | Включение course jobs | Нет | Да, задать явно |
| `COURSE_TIMEZONE` | Да | Нет | Да | `Europe/Moscow` | Curriculum и scheduler timezone | Нет | Да, задать явно |
| `COURSE_CURRICULUM_PATH` | Да | Нет | Да | `curriculum` | Каталог season YAML | Нет | Нет при стандартном пути |
| `COURSE_AI_MODEL` | Да | Нет | Да | `google/gemini-2.5-flash-lite` | Primary Course AI | Нет | Нет, но рекомендуется явно |
| `COURSE_AI_FALLBACK_MODEL` | Да | Нет | Да | `google/gemini-2.5-flash` | Course AI fallback | Нет | Нет, но рекомендуется явно |
| `COURSE_SOURCE_TIMEOUT` | Нет | Нет | Да | `20` | HTTP source timeout | Нет | Нет |
| `COURSE_CATCHUP_MINUTES` | Нет | Нет | Да | `90` | Restart catch-up window | Нет | Нет |
| `COURSE_PREPARE_DAYS` | Нет | Нет | Да | `3` | Сегодня + 3 следующих дня | Нет | Нет |
| `COURSE_ALERTS_ENABLED` | Нет | Нет | Да | `false` | Telegram admin alerts | Нет | Рекомендуется `true` |
| `ADMIN_TELEGRAM_CHAT_ID` | При alerts | Нет | Да | — | Получатель служебных alerts | Частично | Да при alerts |
| `MAX_BOT_TOKEN` | Для MAX | Вероятно да | Нет | — | MAX publisher | Да | Да для MAX |
| `MAX_CHANNEL_ID` | Для MAX | Вероятно да | Нет | — | MAX channel | Нет | Да для MAX |
| `VK_ACCESS_TOKEN` | Для VK | Вероятно да | Нет | — | VK text publication | Да | Да для VK |
| `VK_GROUP_ID` | Для VK | Вероятно да | Нет | — | VK group | Нет | Да для VK |
| `DZEN_CHANNEL_URL` | Для Dzen | Вероятно да | Нет | project channel URL | Dzen channel | Нет | Проверить |
| `DZEN_STORAGE_STATE_JSON` | Для Dzen | Вероятно да | Нет | — | Playwright authorization state | Да | Да для Dzen |
| `DZEN_AUTO_PUBLISH` | Для auto-publish | Вероятно да | Нет | `false` | Publish вместо draft-only | Нет | Проверить текущее значение |
| `DZEN_DEBUG_SCREENSHOTS` | Нет | Возможно | Нет | `true` | Диагностические screenshots | Нет | Нет |
| `DZEN_DEBUG_DIR` | Нет | Возможно | Нет | `storage/dzen_debug` | Screenshot directory | Нет | Нет |
| `MARKETCODE_ENABLED` | Для MarketCode | Да | Нет | `false` | Отдельный MarketCode job | Нет | Сохранить текущее |
| `MARKETCODE_POST_TIME` | Для MarketCode | Да | Нет | `12:00` | Daily schedule | Нет | Сохранить текущее |
| `MARKETCODE_TIMEZONE` | Для MarketCode | Да | Нет | `Europe/Moscow` | MarketCode timezone | Нет | Сохранить текущее |
| `MARKETCODE_IMAGE_URL` | Нет | Да | Нет | branded asset path | Постоянная обложка | Нет | Нет при стандартном asset |
| `MARKETCODE_CONTENT_PLAN` | Нет | Да | Нет | `MARKETCODE_CONTENT_PLAN.md` | 100-day plan | Нет | Нет |
| `MARKETCODE_OPENROUTER_MODEL` | Нет | Да | Нет | Gemini Flash Lite | Primary model | Нет | Сохранить |
| `MARKETCODE_OPENROUTER_FALLBACK_MODEL` | Нет | Да | Нет | Gemini Flash | Fallback model | Нет | Сохранить |
| `PEXELS_API_KEY` / `PIXABAY_API_KEY` | Нет для course | Возможно legacy | Нет | — | Только отключённый legacy flow | Да | Нет |
| `POST_INTERVAL_HOURS` | Нет | Возможно legacy | Нет | `6` | Отключённый legacy scheduler | Нет | Нет |

`Existing likely?` основано на текущем коде и прежнем production flow, а не на чтении Railway variables.

## Future rollout order

1. Сделать backup текущего `bot.db` и зафиксировать количество MarketCode rows/plan days.
2. Создать Railway PostgreSQL и получить secret `DATABASE_URL`.
3. Выполнить migration `--dry-run` с source SQLite и target PostgreSQL.
4. Проверить source/target/would-insert counts и последний MarketCode `plan_day`.
5. Выполнить явный `--execute` и повторный `--dry-run`; `would_insert` должен стать нулём.
6. Проверить `published_days()` на target и не удалять source SQLite.
7. Настроить новые course/alert env с `COURSE_ENABLED=false`; пока не переключать running service на новый `DATABASE_URL`.
8. Проверить актуальность существующих platform/MarketCode env и `DZEN_STORAGE_STATE_JSON`, не выводя секреты.
9. Только затем выполнить отдельные commit и push; дождаться первого auto-deploy с course jobs выключенными.
10. Проверить curriculum startup validation и `/health` на новом коде.
11. Переключить service `DATABASE_URL` на уже заполненный PostgreSQL и дождаться controlled redeploy, всё ещё с `COURSE_ENABLED=false`.
12. Проверить safe startup summary, course schema/indexes и MarketCode `published_days()` в PostgreSQL.
13. Включить `COURSE_ENABLED=true` и выполнить финальный controlled redeploy.
14. Проверить, что подготовлены artifacts окна today…today+3 без публикации будущих частей.
15. Проверить IDs/timezone трёх course jobs и неизменённый MarketCode job.
16. Наблюдать первый учебный день и alerts; реальные smoke-публикации выполнять только по отдельному решению владельца.

## Dzen authorization

Симптом истёкшей сессии — явная ошибка отсутствия авторизации/сессии до создания статьи. Обновляется только `DZEN_STORAGE_STATE_JSON` вручную. Playwright login, selectors и auto-publish flow не изменяются и автоматический login не выполняется.
