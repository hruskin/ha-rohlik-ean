"""Sensor: number of scans awaiting confirmation + detail of the current one."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RohlikEanEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([PendingSensor(entry, entry.runtime_data)])


class PendingSensor(RohlikEanEntity, SensorEntity):
    """How many scans wait for confirmation; attributes carry the first one."""

    _attr_translation_key = "pending"
    _attr_icon = "mdi:barcode-scan"
    _attr_native_unit_of_measurement = "skenů"

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "pending")

    @property
    def native_value(self) -> int:
        return self._data.queue.count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self._data.queue.current
        if current is None:
            return {"pending_eans": []}
        return {
            "ean": current["ean"],
            "quantity": current["quantity"],
            "metadata": current.get("metadata"),
            "candidates": current["candidates"],
            "added_at": current.get("added_at"),
            "pending_eans": self._data.queue.eans,
        }
