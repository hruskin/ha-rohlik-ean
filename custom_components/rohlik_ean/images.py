"""Product thumbnails from Rohlík's public product-detail endpoint.

No authentication needed; results are cached in memory for the lifetime
of the integration (image URLs are stable per product).
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from .const import OFF_USER_AGENT

_LOGGER = logging.getLogger(__name__)

PRODUCT_URL = "https://www.rohlik.cz/api/v1/products/{pid}"
MAX_BATCH = 40


class ImageCache:
    """Lazy product-id → image-URL cache backed by the public API."""

    def __init__(self) -> None:
        self._cache: dict[int, str | None] = {}

    async def async_get_many(
        self, session: aiohttp.ClientSession, product_ids: list[int]
    ) -> dict[int, str | None]:
        ids = list(dict.fromkeys(product_ids))[:MAX_BATCH]
        missing = [pid for pid in ids if pid not in self._cache]
        if missing:
            results = await asyncio.gather(
                *(self._async_fetch(session, pid) for pid in missing)
            )
            self._cache.update(dict(zip(missing, results)))
        return {pid: self._cache.get(pid) for pid in ids}

    async def _async_fetch(
        self, session: aiohttp.ClientSession, pid: int
    ) -> str | None:
        info = await fetch_product_info(session, pid)
        return info.get("image") if info else None


async def fetch_product_info(
    session: aiohttp.ClientSession, pid: int
) -> dict | None:
    """Fetch name/brand/amount/image from Rohlík's public product endpoint."""
    try:
        async with session.get(
            PRODUCT_URL.format(pid=pid),
            headers={"User-Agent": OFF_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                return None
            data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.debug("Product lookup for %s failed: %s", pid, err)
        return None
    images = data.get("images") or []
    return {
        "name": data.get("name"),
        "brand": data.get("brand"),
        "amount": data.get("textualAmount"),
        "image": images[0] if images else None,
    }
