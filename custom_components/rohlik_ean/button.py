"""Button: discard the current pending scan without learning anything."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RohlikEanEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DiscardButton(entry, entry.runtime_data)])


class DiscardButton(RohlikEanEntity, ButtonEntity):
    """Drops the oldest queue item (wrong scan, product not wanted)."""

    _attr_translation_key = "discard"
    _attr_icon = "mdi:close-circle-outline"

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "discard")

    async def async_press(self) -> None:
        await self._data.async_discard_current()
