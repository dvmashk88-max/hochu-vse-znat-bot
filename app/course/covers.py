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


def render_cover(day: CourseDay, part_type: PartType,
                 base_path: str | Path | None = None) -> tuple[bytes, str]:
    theme = SEASON_THEMES.get(day.season_number)
    if not theme:
        raise ValueError(f"No production course theme for season {day.season_number}")
    path = Path(base_path or f"assets/course/season_{day.season_number:02d}_base.png")
    if path.exists():
        image = Image.open(path).convert("RGB").resize((SIZE, SIZE))
    else:
        image = _gradient(theme)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (SAFE_MARGIN, SAFE_MARGIN, SIZE - SAFE_MARGIN, SIZE - SAFE_MARGIN),
        radius=46, outline=theme["glow"], width=5, fill="#10152F",
    )
    _draw_motif(draw, day.season_number, theme)
    layout = cover_layout(day, part_type)
    colors = {
        "brand": "#FFFFFF", "subtitle": theme["accent"], "season": "#C9D5FF",
        "day": "#FFFFFF", "part": "#10152F",
    }
    for placement in layout.placements:
        if placement.name == "part":
            draw.rounded_rectangle((130, 790, SIZE - 130, 940), radius=38, fill=theme["accent"])
        color = colors.get(placement.name, "#FFFFFF")
        draw.text(
            placement.position, placement.text,
            font=_font(placement.font_size, placement.name not in {"season"}), fill=color,
        )

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True, progressive=False, subsampling=1)
    content = output.getvalue()
    return content, hashlib.sha256(content).hexdigest()
