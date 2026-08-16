from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.course.models import CourseDay, PartType

SIZE = 1080
SAFE_MARGIN = 96
TEXT_SAFE_MARGIN = 120
MIN_TITLE_FONT = 38
LESSON_ART_DIR = Path("assets/course/lesson_art")
COVER_RENDERER_VERSION = "thematic-v2"

PART_ACCENTS = {
    PartType.EXPLAIN: "#67F5D1",
    PartType.TRY: "#68C7FF",
    PartType.REINFORCE: "#B8A7FF",
}

THEME_RULES = (
    ("reliability", ("ошиб", "галлюцин", "провер", "огранич", "безопас", "риск", "довер")),
    ("automation", ("агент", "автомат", "процесс", "сценари", "цепоч", "workflow")),
    ("vision", ("изображ", "картин", "визуал", "видео", "аудио", "голос")),
    ("data", ("данн", "таблиц", "документ", "файл", "поиск", "анализ", "исслед")),
    ("prompting", ("запрос", "инструкц", "промпт", "контекст", "формат", "уточн", "задач")),
    ("language", ("язык", "текст", "токен", "модел", "перевод", "ответ")),
    ("work", ("работ", "бизнес", "клиент", "продаж", "маркет", "команд")),
    ("creativity", ("иде", "твор", "креатив", "контент", "дизайн")),
)

THEME_STYLES = {
    "reliability": {"top": (44, 16, 67), "bottom": (10, 58, 86), "accent": "#FFCF5A", "labels": ("ПРОВЕРКА", "НАДЁЖНОСТЬ")},
    "automation": {"top": (20, 17, 72), "bottom": (13, 94, 99), "accent": "#7DFFB2", "labels": ("СВЯЗИ", "АВТОМАТИЗАЦИЯ")},
    "vision": {"top": (63, 16, 77), "bottom": (19, 64, 112), "accent": "#FF83DA", "labels": ("ОБРАЗ", "МУЛЬТИМЕДИА")},
    "data": {"top": (8, 37, 66), "bottom": (8, 104, 111), "accent": "#63E9FF", "labels": ("ДАННЫЕ", "АНАЛИЗ")},
    "prompting": {"top": (38, 18, 84), "bottom": (31, 70, 132), "accent": "#B99CFF", "labels": ("ИНСТРУКЦИЯ", "РЕЗУЛЬТАТ")},
    "language": {"top": (8, 38, 77), "bottom": (15, 94, 119), "accent": "#67F5D1", "labels": ("ТЕКСТ", "СМЫСЛОВЫЕ СВЯЗИ")},
    "work": {"top": (50, 24, 47), "bottom": (120, 54, 38), "accent": "#FFC857", "labels": ("ПРАКТИКА", "РАБОЧИЙ ПРОЦЕСС")},
    "creativity": {"top": (64, 19, 83), "bottom": (29, 63, 116), "accent": "#FF8DD8", "labels": ("ИДЕЯ", "НОВЫЙ ВАРИАНТ")},
    "learning": {"top": (12, 31, 67), "bottom": (25, 84, 104), "accent": "#72E6FF", "labels": ("ПОНЯТНО", "ШАГ ЗА ШАГОМ")},
}

FONT_CANDIDATES = {
    False: (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
    ),
    True: (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
    ),
}

SEASON_THEMES = {
    1: {"name": "foundation-orbits", "top": (9, 20, 52), "bottom": (22, 70, 91), "accent": "#67F5D1", "glow": "#3E5BFF"},
    2: {"name": "prompt-signals", "top": (24, 14, 58), "bottom": (73, 24, 105), "accent": "#FF77D5", "glow": "#7C4DFF"},
    3: {"name": "search-data-grid", "top": (7, 31, 48), "bottom": (8, 81, 93), "accent": "#57E8FF", "glow": "#16A4B8"},
    4: {"name": "workflows", "top": (27, 22, 48), "bottom": (79, 46, 31), "accent": "#FFC857", "glow": "#F06B3D"},
    5: {"name": "agent-circuits", "top": (15, 20, 47), "bottom": (41, 33, 91), "accent": "#A7FF83", "glow": "#845EF7"},
}


@dataclass(frozen=True)
class TextPlacement:
    name: str
    text: str
    position: tuple[float, float]
    bbox: tuple[int, int, int, int]
    font_size: int


@dataclass(frozen=True)
class CoverLayout:
    season_theme: str
    placements: tuple[TextPlacement, ...]
    title_lines: tuple[str, ...]
    title_font_size: int

    @property
    def text_within_safe_area(self) -> bool:
        return all(
            item.bbox[0] >= TEXT_SAFE_MARGIN
            and item.bbox[1] >= TEXT_SAFE_MARGIN
            and item.bbox[2] <= SIZE - TEXT_SAFE_MARGIN
            and item.bbox[3] <= SIZE - TEXT_SAFE_MARGIN
            for item in self.placements
        )


def _font(size: int, bold: bool = False):
    for path in FONT_CANDIDATES[bold]:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    raise RuntimeError("Course cover renderer requires a local Cyrillic TrueType font")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def cover_metadata(day: CourseDay) -> tuple[str, str]:
    if day.day_type == "lesson":
        return (
            f"СЕЗОН {day.season_number}   •   КУРС {day.course_number}",
            f"УРОК {day.lesson_number} ИЗ {day.lesson_count}",
        )
    return f"СЕЗОН {day.season_number}", day.cover_label.upper()


def _placement(draw: ImageDraw.ImageDraw, name: str, text: str, position: tuple[float, float],
               size: int, bold: bool = False) -> TextPlacement:
    font = _font(size, bold)
    bbox = draw.textbbox(position, text, font=font)
    return TextPlacement(name, text, position, bbox, size)


def cover_layout(day: CourseDay, part_type: PartType) -> CoverLayout:
    theme = SEASON_THEMES.get(day.season_number)
    if not theme:
        raise ValueError(f"No production course theme for season {day.season_number}")
    draw = ImageDraw.Draw(Image.new("RGB", (SIZE, SIZE)))
    season_line, day_line = cover_metadata(day)
    placements = [
        _placement(draw, "brand", "ХОЧУ ВСЁ ЗНАТЬ — ИИ", (140, 140), 44, True),
        _placement(draw, "subtitle", "УЧИМСЯ КАЖДЫЙ ДЕНЬ", (140, 202), 29, True),
        _placement(draw, "season", season_line, (140, 286), 32),
        _placement(draw, "day", day_line, (140, 345), 40, True),
    ]
    title_lines: list[str] = []
    title_size = 60
    while title_size >= MIN_TITLE_FONT:
        title_lines = _wrap(draw, day.short_title.upper(), _font(title_size, True), SIZE - 280)
        if len(title_lines) <= 3 and 455 + len(title_lines) * 72 <= 690:
            break
        title_size -= 2
    if title_size < MIN_TITLE_FONT or len(title_lines) > 3:
        raise ValueError(f"Course cover short_title does not fit safely: {day.short_title}")
    y = 455
    for index, line in enumerate(title_lines):
        placements.append(_placement(draw, f"title-{index}", line, (140, y), title_size, True))
        y += 72
    label = part_type.public_name
    label_font = _font(52, True)
    label_box = draw.textbbox((0, 0), label, font=label_font)
    label_x = (SIZE - (label_box[2] - label_box[0])) / 2
    placements.append(_placement(draw, "part", label, (label_x, 836), 52, True))
    result = CoverLayout(theme["name"], tuple(placements), tuple(title_lines), title_size)
    if not result.text_within_safe_area:
        unsafe = [item.name for item in result.placements if not (
            item.bbox[0] >= TEXT_SAFE_MARGIN and item.bbox[1] >= TEXT_SAFE_MARGIN
            and item.bbox[2] <= SIZE - TEXT_SAFE_MARGIN and item.bbox[3] <= SIZE - TEXT_SAFE_MARGIN
        )]
        raise ValueError(f"Course cover text exceeds safe area: {unsafe}")
    return result


def _gradient(theme: dict[str, object]) -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE), theme["top"])
    draw = ImageDraw.Draw(image)
    top, bottom = theme["top"], theme["bottom"]
    for y in range(SIZE):
        ratio = y / (SIZE - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, SIZE, y), fill=color)
    return image


def _draw_motif(draw: ImageDraw.ImageDraw, season: int, theme: dict[str, object]) -> None:
    glow = theme["glow"]
    accent = theme["accent"]
    if season == 1:
        for radius in (110, 180, 250):
            draw.ellipse((790-radius, 185-radius, 790+radius, 185+radius), outline=glow, width=5)
        for point in ((940, 185), (790, 75), (690, 300)):
            draw.ellipse((point[0]-12, point[1]-12, point[0]+12, point[1]+12), fill=accent)
    elif season == 2:
        for y, width in ((90, 220), (160, 310), (230, 180)):
            draw.rounded_rectangle((740, y, 740 + width, y + 48), radius=20, outline=glow, width=5)
        draw.line((775, 325, 985, 325), fill=accent, width=10)
    elif season == 3:
        for x in range(720, 1081, 54):
            draw.line((x, 0, x, 350), fill=glow, width=2)
        for y in range(28, 350, 54):
            draw.line((690, y, 1080, y), fill=glow, width=2)
        draw.ellipse((815, 90, 975, 250), outline=accent, width=12)
        draw.line((945, 225, 1030, 310), fill=accent, width=16)
    elif season == 4:
        boxes = ((720, 80, 865, 155), (900, 185, 1040, 260), (690, 285, 835, 360))
        for box in boxes:
            draw.rounded_rectangle(box, radius=18, outline=accent, width=6)
        draw.line((865, 118, 940, 118, 940, 185), fill=glow, width=7)
        draw.line((900, 223, 790, 223, 790, 285), fill=glow, width=7)
    else:
        for x, y in ((755, 95), (900, 90), (995, 205), (865, 300), (720, 260)):
            draw.ellipse((x-15, y-15, x+15, y+15), fill=accent)
        for left, right in (((755, 95), (900, 90)), ((900, 90), (995, 205)), ((995, 205), (865, 300)), ((865, 300), (720, 260)), ((720, 260), (755, 95))):
            draw.line((*left, *right), fill=glow, width=7)


def cover_theme_key(day: CourseDay) -> str:
    context = " ".join((day.topic, day.short_title, day.learning_goal)).casefold()
    for key, keywords in THEME_RULES:
        if any(keyword in context for keyword in keywords):
            return key
    return "learning"


def _thematic_background(day: CourseDay, part_type: PartType) -> Image.Image:
    key = cover_theme_key(day)
    style = THEME_STYLES[key]
    image = Image.new("RGB", (SIZE, SIZE), style["top"])
    draw = ImageDraw.Draw(image)
    top, bottom = style["top"], style["bottom"]
    for y in range(SIZE):
        ratio = y / (SIZE - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line((0, y, SIZE, y), fill=color)

    accent = style["accent"]
    part_accent = PART_ACCENTS[part_type]
    for radius, width in ((430, 5), (330, 4), (235, 3)):
        draw.ellipse((790 - radius, 510 - radius, 790 + radius, 510 + radius), outline=accent, width=width)
    for x, y, radius in ((682, 165, 14), (1000, 260, 9), (930, 850, 18), (620, 760, 8)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=part_accent)

    if key == "language":
        draw.rounded_rectangle((610, 250, 1010, 470), radius=48, fill=(7, 25, 55), outline=accent, width=8)
        draw.polygon(((690, 470), (650, 535), (760, 470)), fill=(7, 25, 55))
        for x, width in ((650, 96), (764, 128), (910, 68)):
            draw.rounded_rectangle((x, 320, x + width, 376), radius=22, fill=part_accent)
    elif key == "prompting":
        draw.rounded_rectangle((610, 210, 1010, 650), radius=42, fill=(13, 20, 58), outline=accent, width=8)
        for y, width in ((290, 290), (390, 220), (490, 320)):
            draw.rounded_rectangle((660, y, 660 + width, y + 48), radius=20, outline=part_accent, width=6)
            draw.ellipse((625, y + 11, 651, y + 37), fill=accent)
    elif key == "reliability":
        draw.polygon(((810, 190), (1010, 265), (980, 600), (810, 760), (640, 600), (610, 265)), fill=(13, 28, 61), outline=accent)
        draw.line((705, 470, 785, 550, 930, 370), fill=part_accent, width=30, joint="curve")
    elif key == "data":
        draw.rounded_rectangle((620, 205, 990, 650), radius=38, fill=(7, 30, 55), outline=accent, width=7)
        for index, height in enumerate((120, 210, 165, 270)):
            x = 680 + index * 67
            draw.rounded_rectangle((x, 580 - height, x + 40, 580), radius=14, fill=part_accent)
        draw.ellipse((825, 245, 1015, 435), outline="#FFFFFF", width=14)
        draw.line((970, 400, 1040, 475), fill="#FFFFFF", width=20)
    elif key == "automation":
        nodes = ((650, 300), (835, 210), (1000, 350), (870, 540), (660, 650))
        for left, right in zip(nodes, (*nodes[1:], nodes[0])):
            draw.line((*left, *right), fill=accent, width=10)
        for index, (x, y) in enumerate(nodes):
            radius = 42 if index else 56
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=part_accent, outline="#FFFFFF", width=5)
    elif key == "vision":
        draw.rounded_rectangle((600, 210, 1020, 690), radius=54, fill=(17, 24, 61), outline=accent, width=8)
        draw.ellipse((720, 300, 900, 480), outline=part_accent, width=20)
        draw.ellipse((782, 362, 838, 418), fill="#FFFFFF")
        draw.polygon(((640, 625), (760, 480), (835, 560), (920, 440), (990, 625)), fill=accent)
    elif key == "work":
        for index, height in enumerate((170, 250, 340)):
            x = 650 + index * 105
            draw.rounded_rectangle((x, 680-height, x+70, 680), radius=18, fill=part_accent)
        draw.line((630, 700, 1010, 700), fill="#FFFFFF", width=8)
        draw.line((690, 440, 830, 330, 995, 210), fill=accent, width=18, joint="curve")
        draw.polygon(((995, 210), (930, 222), (980, 275)), fill=accent)
    else:
        draw.ellipse((655, 195, 965, 505), fill=(16, 27, 69), outline=accent, width=9)
        draw.rounded_rectangle((730, 475, 890, 575), radius=28, fill=part_accent)
        for angle_x, angle_y in ((610, 260), (580, 430), (1010, 270), (1040, 455), (810, 130)):
            draw.line((810, 350, angle_x, angle_y), fill=accent, width=9)
            draw.ellipse((angle_x-15, angle_y-15, angle_x+15, angle_y+15), fill="#FFFFFF")
    return image


def lesson_art_path(day: CourseDay) -> Path:
    return LESSON_ART_DIR / (
        f"season_{day.season_number:02d}_lesson_{day.lesson_number:02d}.jpg"
    )


def _draw_series_cover(image: Image.Image, day: CourseDay, part_type: PartType) -> Image.Image:
    image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    accent = PART_ACCENTS[part_type]
    style = THEME_STYLES[cover_theme_key(day)]

    # The illustration remains the hero; this quiet panel guarantees readable
    # programmatic Cyrillic typography without baking text into generated art.
    draw.rounded_rectangle(
        (54, 54, 574, SIZE - 54),
        radius=44,
        fill=(5, 14, 37, 232),
        outline=accent,
        width=3,
    )
    draw.rounded_rectangle((84, 82, 544, 150), radius=24, fill=(12, 29, 61, 220))
    draw.text((108, 101), "ХОЧУ ВСЁ ЗНАТЬ — ИИ", font=_font(27, True), fill="#FFFFFF")
    draw.text((108, 164), "УЧИМСЯ КАЖДЫЙ ДЕНЬ", font=_font(20, True), fill=accent)

    season_line, day_line = cover_metadata(day)
    draw.text((108, 232), season_line, font=_font(20), fill="#B8C8E8")
    draw.text((108, 272), day_line, font=_font(27, True), fill="#FFFFFF")

    title_font_size = 48
    title_lines = _wrap(draw, day.short_title.upper(), _font(title_font_size, True), 408)
    while len(title_lines) > 3 and title_font_size > 38:
        title_font_size -= 2
        title_lines = _wrap(draw, day.short_title.upper(), _font(title_font_size, True), 408)
    title_y = 365
    for line in title_lines:
        draw.text((108, title_y), line, font=_font(title_font_size, True), fill="#FFFFFF")
        title_y += title_font_size + 17

    draw.line((108, 570, 516, 570), fill=(103, 245, 209, 95), width=2)
    draw.text((108, 600), style["labels"][0], font=_font(20, True), fill="#CFE5FF")
    draw.text((108, 634), style["labels"][1], font=_font(20, True), fill=style["accent"])

    part_number = {
        PartType.EXPLAIN: "ЧАСТЬ 1 ИЗ 3",
        PartType.TRY: "ЧАСТЬ 2 ИЗ 3",
        PartType.REINFORCE: "ЧАСТЬ 3 ИЗ 3",
    }[part_type]
    draw.text((108, 796), part_number, font=_font(20, True), fill="#B8C8E8")
    draw.rounded_rectangle((88, 842, 540, 958), radius=32, fill=accent)
    label = part_type.public_name
    label_font = _font(32, True)
    label_box = draw.textbbox((0, 0), label, font=label_font)
    label_x = 314 - (label_box[2] - label_box[0]) / 2
    label_y = 900 - (label_box[3] - label_box[1]) / 2 - label_box[1]
    draw.text((label_x, label_y), label, font=label_font, fill="#08152F")

    return Image.alpha_composite(image, overlay).convert("RGB")


def render_cover(day: CourseDay, part_type: PartType,
                 base_path: str | Path | None = None) -> tuple[bytes, str]:
    if day.season_number not in SEASON_THEMES:
        raise ValueError(f"No production course theme for season {day.season_number}")
    candidate = Path(base_path) if base_path is not None else lesson_art_path(day)
    path = candidate if candidate.exists() else None
    if path is not None:
        image = Image.open(path).convert("RGB").resize((SIZE, SIZE))
    else:
        image = _thematic_background(day, part_type)
    image = _draw_series_cover(image, day, part_type)

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True, progressive=False, subsampling=1)
    content = output.getvalue()
    return content, hashlib.sha256(content).hexdigest()
