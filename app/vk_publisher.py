from __future__ import annotations

import asyncio
from typing import Any

import requests

from app.config import VK_ACCESS_TOKEN, VK_GROUP_ID

_API_URL = "https://api.vk.com/method"
_API_VERSION = "5.199"
_VK_TEXT_LENGTH = 15000


def _require_access_token() -> str:
    if not VK_ACCESS_TOKEN:
        raise RuntimeError("VK_ACCESS_TOKEN is not set")
    return VK_ACCESS_TOKEN


def _require_group_id() -> int:
    if not VK_GROUP_ID:
        raise RuntimeError("VK_GROUP_ID is not set")
    try:
        return int(VK_GROUP_ID)
    except ValueError as e:
        raise RuntimeError("VK_GROUP_ID must be a numeric community id") from e


def _vk_error(data: dict[str, Any]) -> RuntimeError:
    error = data.get("error", {})
    if not isinstance(error, dict):
        return RuntimeError("VK API request failed")

    code = error.get("error_code", "unknown")
    message = error.get("error_msg", "unknown error")
    return RuntimeError(f"VK API error {code}: {message}")


def _call_vk(method: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{_API_URL}/{method}",
        data={
            **params,
            "access_token": _require_access_token(),
            "v": _API_VERSION,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise _vk_error(data)
    payload = data.get("response")
    return payload if isinstance(payload, dict) else {"items": payload}


def _upload_wall_photo(group_id: int, image_bytes: bytes) -> str:
    upload_server = _call_vk("photos.getWallUploadServer", {"group_id": group_id})
    upload_url = upload_server.get("upload_url")
    if not upload_url:
        raise RuntimeError("VK upload server response does not contain upload_url")

    upload_response = requests.post(
        upload_url,
        files={"photo": ("image.jpg", image_bytes, "image/jpeg")},
        timeout=60,
    )
    upload_response.raise_for_status()
    upload_data = upload_response.json()

    saved = _call_vk(
        "photos.saveWallPhoto",
        {
            "group_id": group_id,
            "photo": upload_data["photo"],
            "server": upload_data["server"],
            "hash": upload_data["hash"],
        },
    )
    items = saved.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("VK saveWallPhoto response does not contain saved photo")

    photo = items[0]
    owner_id = photo.get("owner_id")
    photo_id = photo.get("id")
    if owner_id is None or photo_id is None:
        raise RuntimeError("VK saved photo response does not contain owner_id/id")

    attachment = f"photo{owner_id}_{photo_id}"
    access_key = photo.get("access_key")
    if access_key:
        attachment = f"{attachment}_{access_key}"
    return attachment


def _publish_post(text: str, image_bytes: bytes | None = None) -> str:
    group_id = _require_group_id()
    params: dict[str, Any] = {
        "owner_id": -group_id,
        "from_group": 1,
        "message": text[:_VK_TEXT_LENGTH],
    }

    if image_bytes:
        params["attachments"] = _upload_wall_photo(group_id, image_bytes)

    post = _call_vk("wall.post", params)
    post_id = post.get("post_id")
    if post_id is None:
        raise RuntimeError("VK wall.post response does not contain post_id")
    return f"-{group_id}_{post_id}"


async def publish_to_vk(text: str, image_bytes: bytes | None = None) -> str:
    return await asyncio.to_thread(_publish_post, text, image_bytes)
