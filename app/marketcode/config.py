import os
from dataclasses import dataclass


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MarketCodeSettings:
    enabled: bool
    post_time: str
    timezone: str
    image_url: str
    content_plan: str
    model: str
    fallback_model: str


def load_settings() -> MarketCodeSettings:
    return MarketCodeSettings(
        enabled=_as_bool(os.getenv("MARKETCODE_ENABLED", "false")),
        post_time=os.getenv("MARKETCODE_POST_TIME", "12:00").strip(),
        timezone=os.getenv("MARKETCODE_TIMEZONE", "Europe/Moscow").strip(),
        image_url=os.getenv(
            "MARKETCODE_IMAGE_URL",
            "assets/marketcode/marketcode_cover.png",
        ).strip(),
        content_plan=os.getenv("MARKETCODE_CONTENT_PLAN", "MARKETCODE_CONTENT_PLAN.md").strip(),
        model=os.getenv(
            "MARKETCODE_OPENROUTER_MODEL",
            "google/gemini-2.5-flash-lite",
        ).strip(),
        fallback_model=os.getenv("MARKETCODE_OPENROUTER_FALLBACK_MODEL", "google/gemini-2.5-flash").strip(),
    )


def parse_post_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("MARKETCODE_POST_TIME must use HH:MM format") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("MARKETCODE_POST_TIME must be a valid 24-hour time")
    return hour, minute
