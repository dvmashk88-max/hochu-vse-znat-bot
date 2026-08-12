from __future__ import annotations

import asyncio

from app.vk_publisher import _call_vk, _require_group_id


def _publish(text: str) -> str:
    group_id = _require_group_id()
    post = _call_vk(
        "wall.post",
        {
            "owner_id": -group_id,
            "from_group": 1,
            "message": text,
        },
    )
    post_id = post.get("post_id")
    if post_id is None:
        raise RuntimeError("VK wall.post response does not contain post_id")
    return f"-{group_id}_{post_id}"


async def publish_marketcode_to_vk(text: str) -> str:
    return await asyncio.to_thread(_publish, text)
