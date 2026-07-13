"""Small persistent counter: scans that reached the cart/review today."""
from __future__ import annotations

from datetime import date

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import SIGNAL_UPDATED, STATS_STORAGE_KEY, STORAGE_VERSION


class ScanStats:
    """Tracks a daily scan counter, reset automatically on date rollover."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, STATS_STORAGE_KEY)
        self._date: str = date.today().isoformat()
        self._count: int = 0

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self._date = data.get("date", date.today().isoformat())
        self._count = int(data.get("count", 0))

    @property
    def today(self) -> int:
        return self._count if self._date == date.today().isoformat() else 0

    async def async_increment(self, by: int = 1) -> None:
        today = date.today().isoformat()
        if self._date != today:
            self._date = today
            self._count = 0
        self._count += by
        await self._store.async_save({"date": self._date, "count": self._count})
        async_dispatcher_send(self._hass, SIGNAL_UPDATED)
