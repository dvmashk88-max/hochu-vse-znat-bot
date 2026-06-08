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
