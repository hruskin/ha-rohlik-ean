"""Base entity for Rohlík EAN — one service device, dispatcher updates."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_QUEUE_UPDATED
from .runtime import RohlikEanData


class RohlikEanEntity(Entity):
    """Entity backed by the pending-confirmation queue."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: RohlikEanData, key: str) -> None:
        self._data = data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Rohlík EAN",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_QUEUE_UPDATED, self._handle_queue_update
            )
        )

    def _handle_queue_update(self) -> None:
        self.async_write_ha_state()
