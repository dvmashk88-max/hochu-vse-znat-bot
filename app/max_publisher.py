from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests

from app.config import MAX_BOT_TOKEN, MAX_CHANNEL_ID

logger = logging.getLogger(__name__)

_API_URL = "https://platform-api.max.ru"
_ATTACHMENT_NOT_READY = "attachment.not.ready"
_MAX_TEXT_LENGTH = 4000


def _headers() -> dict[str, str]:
    if not MAX_BOT_TOKEN:
        raise RuntimeError("MAX_BOT_TOKEN is not set")
    return {"Authorization": MAX_BOT_TOKEN}


def _require_channel_id() -> str:
    if not MAX_CHANNEL_ID:
        raise RuntimeError("MAX_CHANNEL_ID is not set")
    return MAX_CHANNEL_ID


def _extract_upload_payload(response_data: dict[str, Any]) -> dict[str, Any]:
    token = response_data.get("token")
    if token:
        return {"token": token}

    payload = response_data.get("payload")
    if isinstance(payload, dict) and payload.get("token"):
        return payload

    photos = response_data.get("photos")
    if isinstance(photos, dict):
        for photo_payload in photos.values():
            if isinstance(photo_payload, dict) and photo_payload.get("token"):
                return photo_payload

    raise RuntimeError("MAX upload response does not contain an image token")


def _upload_image(image_bytes: bytes) -> dict[str, Any]:
    response = requests.post(
        f"{_API_URL}/uploads",
        params={"type": "image"},
        headers=_headers(),
        timeout=20,
    )
    response.raise_for_status()
    upload_url = response.json()["url"]

    upload_response = requests.post(
        upload_url,
        files={"data": ("image.jpg", image_bytes, "image/jpeg")},
        timeout=60,
    )
    upload_response.raise_for_status()
    return _extract_upload_payload(upload_response.json())


def _send_message(text: str, image_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "text": text[:_MAX_TEXT_LENGTH],
        "notify": True,
    }
    if image_payload:
        body["attachments"] = [{"type": "image", "payload": image_payload}]

    response = requests.post(
        f"{_API_URL}/messages",
        params={"chat_id": _require_channel_id()},
        headers={**_headers(), "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _publish_post(text: str, image_bytes: bytes | None = None) -> str:
    image_payload = None
    if image_bytes:
        image_payload = _upload_image(image_bytes)

    for attempt in range(4):
        try:
            data = _send_message(text, image_payload=image_payload)
            message = data.get("message", data)
            body = message.get("body", {}) if isinstance(message, dict) else {}
            return body.get("mid") or message.get("id") or message.get("message_id") or "sent"
        except requests.HTTPError as e:
            response = e.response
            error_code = ""
            if response is not None:
                try:
                    error_code = response.json().get("code", "")
                except ValueError:
                    error_code = ""

            if image_payload and error_code == _ATTACHMENT_NOT_READY and attempt < 3:
                delay = 2**attempt
                logger.info("MAX image is not ready yet; retrying in %s seconds", delay)
                time.sleep(delay)
                continue
            raise

    raise RuntimeError("MAX message was not sent")


async def publish_to_max(text: str, image_bytes: bytes | None = None) -> str:
    return await asyncio.to_thread(_publish_post, text, image_bytes)
