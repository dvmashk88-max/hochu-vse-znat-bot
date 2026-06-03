import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot.db")
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "6"))
DZEN_CHANNEL_URL = os.getenv("DZEN_CHANNEL_URL", "https://dzen.ru/aibotpro163")
DZEN_STORAGE_STATE_JSON = os.getenv("DZEN_STORAGE_STATE_JSON", "")
