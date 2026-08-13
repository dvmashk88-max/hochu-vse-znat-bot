# Course cover assets

`app/course/covers.py` всегда генерирует отдельную квадратную JPEG-обложку для каждой части урока локально и детерминированно. JPEG выбран для совместимости с текущими Telegram/MAX/Dzen adapters.

Опциональные брендовые фоны сезонов можно положить сюда:

```text
assets/course/season_01_base.png
assets/course/season_02_base.png
assets/course/season_03_base.png
assets/course/season_04_base.png
assets/course/season_05_base.png
```

Требования к base image:

- PNG;
- квадрат;
- рекомендуемый размер `1080×1080`;
- без важного текста по краям;
- центральная зона должна оставаться достаточно спокойной для динамических надписей.

Override необязателен. Без него renderer использует одну из пяти встроенных production-композиций:

- Season 1 — светящиеся орбиты и точки основ;
- Season 2 — prompt-сигналы и диалоговая геометрия;
- Season 3 — data-grid и поисковая линза;
- Season 4 — связанные workflow-блоки;
- Season 5 — agent/circuit network.

Общий branding, центральная карточка и типографика едины. Важный текст проверяется внутри `TEXT_SAFE_MARGIN=120`; внешний card safe area — 96 px. Для special day вместо `УРОК N ИЗ 15` выводится `cover_label`. Внешние image API не вызываются.

Контрольный прогон текущих 420 JPEG при `quality=88`: средний размер около 84 KB, диапазон примерно 67–102 KB, суммарно около 33.6 MiB. Для программы до конца 2026 года хранение image bytes в PostgreSQL остаётся разумным и отдельный object storage не требуется.
