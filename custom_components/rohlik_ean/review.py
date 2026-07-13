"""Optional review list — resolved products staged before hitting the cart.

Only used when review mode is enabled. Unlike PendingQueue (unknown codes
awaiting learning), these are known products with a chosen quantity; the
user reviews them and commits the whole list to the cart at once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    EVENT_REVIEW_CHANGED,
    REVIEW_STORAGE_KEY,
    SIGNAL_UPDATED,
    STORAGE_VERSION,
)


class ReviewList:
    """Persistent EAN → {product_id, name, quantity} staging list."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[list[dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, REVIEW_STORAGE_KEY
        )
        self._items: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        self._items = await self._store.async_load() or []

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def total_units(self) -> int:
        return sum(int(i.get("quantity", 0)) for i in self._items)

    @property
    def items(self) -> list[dict[str, Any]]:
        return list(self._items)

    async def async_add(
        self, ean: str, product_id: int, name: str | None, quantity: int
    ) -> None:
        """Add a product; a re-scan of the same EAN sums the quantity."""
        for item in self._items:
            if item["ean"] == ean:
                item["quantity"] += quantity
                await self._save()
                return
        self._items.append(
            {
                "ean": ean,
                "product_id": product_id,
                "name": name,
                "quantity": quantity,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await self._save()

    async def async_set_quantity(self, ean: str, quantity: int) -> bool:
        for index, item in enumerate(self._items):
            if item["ean"] == ean:
                if quantity <= 0:
                    self._items.pop(index)
                else:
                    item["quantity"] = quantity
                await self._save()
                return True
        return False

    async def async_remove(self, ean: str) -> dict[str, Any] | None:
        for index, item in enumerate(self._items):
            if item["ean"] == ean:
                removed = self._items.pop(index)
                await self._save()
                return removed
        return None

    async def async_pop_last(self) -> dict[str, Any] | None:
        if not self._items:
            return None
        item = self._items.pop()
        await self._save()
        return item

    async def async_clear(self) -> None:
        self._items = []
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save(self._items)
        async_dispatcher_send(self._hass, SIGNAL_UPDATED)
        self._hass.bus.async_fire(EVENT_REVIEW_CHANGED)
