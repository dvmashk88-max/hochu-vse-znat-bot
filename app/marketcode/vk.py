from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.vk_publisher import _call_vk, _require_group_id, _upload_wall_photo


@dataclass(frozen=True)
class PreparedMarketCodeVkImage:
    group_id: int
    attachment: str


def _prepare_image(image_bytes: bytes) -> PreparedMarketCodeVkImage:
    group_id = _require_group_id()
    attachment = _upload_wall_photo(group_id, image_bytes)
    return PreparedMarketCodeVkImage(group_id=group_id, attachment=attachment)


async def prepare_marketcode_vk_image(image_bytes: bytes) -> PreparedMarketCodeVkImage:
    return await asyncio.to_thread(_prepare_image, image_bytes)


def _publish(text: str, prepared: PreparedMarketCodeVkImage) -> str:
    post = _call_vk(
        "wall.post",
        {
            "owner_id": -prepared.group_id,
            "from_group": 1,
            "message": text,
            "attachments": prepared.attachment,
        },
    )
    post_id = post.get("post_id")
    if post_id is None:
        raise RuntimeError("VK wall.post response does not contain post_id")
    return f"-{prepared.group_id}_{post_id}"


async def publish_marketcode_to_vk(text: str, prepared: PreparedMarketCodeVkImage) -> str:
    return await asyncio.to_thread(_publish, text, prepared)
