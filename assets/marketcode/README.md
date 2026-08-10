# MarketCode Pro visual assets

## QR-код

- Файл: `marketcode_qr.png`
- Целевой адрес: `https://www.marketcode.pro`
- Размер: 800×800 px
- Уровень коррекции ошибок: H
- SHA-256: `8def33d546899fc0a6472261da987f5f638ae7779951ea162e63d9e63ab3a44a`
- Обратное распознавание после генерации вернуло точный целевой адрес без ошибки.

QR следует накладывать на готовую обложку без растяжения, обрезки, прозрачности и
визуальных эффектов. Вокруг кода нужно сохранить светлое свободное поле. После любого
ресайза или экспорта итоговую композицию необходимо повторно проверить сканированием.

## Фирменная обложка

- формат 16:9, ориентир 1280×720 px;
- фон: тёмно-синий, близкий к `hsl(231 65% 6%)`;
- основной акцент: фиолетовый, близкий к `hsl(262 83% 58%)`;
- дополнительный акцент: cyan, близкий к `hsl(188 94% 43%)`;
- смартфон, Apple Gift Card, узнаваемые знаки Steam и Telegram, Telegram Stars/Premium,
  игровая карточка PUBG UC и карточка Free Fire Diamonds;
- точные надписи `MarketCode Pro`, `Apple ID`, `Apple Gift Card`, `Steam`,
  `Telegram Stars`, `Telegram Premium`, `PUBG UC`, `Free Fire Diamonds` и
  `https://www.marketcode.pro`;
- отдельная светлая зона с настоящим QR-кодом.

Финальная обложка хранится в `marketcode_cover.png` (SHA-256:
`4eb4258a939ff7b8f2ce3b8d2e79ef33cfd2c3ca3e07f95f8a62defae439851d`). Поток читает её
по локальному пути `assets/marketcode/marketcode_cover.png`; при необходимости настройка
`MARKETCODE_IMAGE_URL` также принимает публичный HTTP(S)-адрес.
