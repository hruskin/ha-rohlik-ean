"""Persistent queue of scans awaiting manual confirmation."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import QUEUE_STORAGE_KEY, SIGNAL_QUEUE_UPDATED, STORAGE_VERSION


class PendingQueue:
    """FIFO of unresolved scans; survives restarts, notifies entities."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[list[dict[str, Any]]] = Store(
            hass, STORAGE_VERSION, QUEUE_STORAGE_KEY
        )
        self._items: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        self._items = await self._store.async_load() or []

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def current(self) -> dict[str, Any] | None:
        """The item entities present for confirmation (oldest first)."""
        return self._items[0] if self._items else None

    @property
    def eans(self) -> list[str]:
        return [item["ean"] for item in self._items]

    async def async_push(self, item: dict[str, Any]) -> None:
        """Add a scan; a re-scan of the same EAN replaces the older entry."""
        self._items = [i for i in self._items if i["ean"] != item["ean"]]
        self._items.append(item)
        await self._save_and_notify()

    async def async_remove(self, ean: str) -> dict[str, Any] | None:
        for index, item in enumerate(self._items):
            if item["ean"] == ean:
                removed = self._items.pop(index)
                await self._save_and_notify()
                return removed
        return None

    async def async_pop_current(self) -> dict[str, Any] | None:
        if not self._items:
            return None
        item = self._items.pop(0)
        await self._save_and_notify()
        return item

    async def _save_and_notify(self) -> None:
        await self._store.async_save(self._items)
        async_dispatcher_send(self._hass, SIGNAL_QUEUE_UPDATED)
