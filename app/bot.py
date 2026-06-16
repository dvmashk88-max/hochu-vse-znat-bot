import io
import logging
from telegram import Bot, InputFile
from app.config import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

_bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Telegram limits photo captions to 1024 characters
_CAPTION_LIMIT = 1024


async def send_text(chat_id: str, text: str) -> None:
    await _bot.send_message(chat_id=chat_id, text=text)


async def send_photo_with_caption(chat_id: str, image_bytes: bytes, caption: str) -> None:
    if len(caption) <= _CAPTION_LIMIT:
        await _bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(io.BytesIO(image_bytes), filename="image.jpg"),
            caption=caption,
        )
    else:
        # Photo first, full text as follow-up message
        await _bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(io.BytesIO(image_bytes), filename="image.jpg"),
        )
        await _bot.send_message(chat_id=chat_id, text=caption)
