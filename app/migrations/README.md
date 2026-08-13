# SQLite → PostgreSQL migration

Утилита переносит только обязательный `marketcode_publications`, чтобы MarketCode не начал 100-дневный план заново. Source SQLite открывается в read-only mode. `published_topics`, старые platform/image histories и отсутствующий до первого запуска course state не переносятся: новый scheduler их не читает.

Ничего не запускается автоматически при startup.

Dry-run без подключения к target:

```bash
python -m app.migrations.sqlite_to_postgres --source bot.db --dry-run
```

Dry-run с будущим PostgreSQL для подсчёта конфликтов:

```bash
python -m app.migrations.sqlite_to_postgres --source bot.db --target-url "$DATABASE_URL" --dry-run
```

Реальное выполнение только явно:

```bash
python -m app.migrations.sqlite_to_postgres --source bot.db --target-url "$DATABASE_URL" --execute
```

Повторный запуск безопасен: `plan_day` имеет UNIQUE constraint, а существующая target-запись сохраняется через `ON CONFLICT DO NOTHING`. Команда не выводит URL, credentials, tokens или JSON channel statuses.
