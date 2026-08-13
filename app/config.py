import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db")
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "6"))
DZEN_CHANNEL_URL = os.getenv("DZEN_CHANNEL_URL", "https://dzen.ru/aibotpro163")
DZEN_STORAGE_STATE_JSON = os.getenv("DZEN_STORAGE_STATE_JSON", "")
DZEN_AUTO_PUBLISH = os.getenv("DZEN_AUTO_PUBLISH", "false").lower() == "true"
DZEN_DEBUG_SCREENSHOTS = os.getenv("DZEN_DEBUG_SCREENSHOTS", "true").lower() == "true"
DZEN_DEBUG_DIR = os.getenv("DZEN_DEBUG_DIR", "storage/dzen_debug")
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
MAX_CHANNEL_ID = os.getenv("MAX_CHANNEL_ID", "")
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "")
COURSE_ENABLED = os.getenv("COURSE_ENABLED", "true").lower() == "true"
COURSE_TIMEZONE = os.getenv("COURSE_TIMEZONE", "Europe/Moscow")
COURSE_CURRICULUM_PATH = os.getenv("COURSE_CURRICULUM_PATH", "curriculum")
COURSE_AI_MODEL = os.getenv("COURSE_AI_MODEL", "google/gemini-2.5-flash-lite")
COURSE_AI_FALLBACK_MODEL = os.getenv("COURSE_AI_FALLBACK_MODEL", "google/gemini-2.5-flash")
COURSE_SOURCE_TIMEOUT = int(os.getenv("COURSE_SOURCE_TIMEOUT", "20"))
COURSE_CATCHUP_MINUTES = int(os.getenv("COURSE_CATCHUP_MINUTES", "90"))
COURSE_PREPARE_DAYS = int(os.getenv("COURSE_PREPARE_DAYS", "3"))
COURSE_ALERTS_ENABLED = os.getenv("COURSE_ALERTS_ENABLED", "false").lower() == "true"
ADMIN_TELEGRAM_CHAT_ID = os.getenv("ADMIN_TELEGRAM_CHAT_ID", "")
