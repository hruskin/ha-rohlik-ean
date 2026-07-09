"""Text: manual product-name search for the current pending scan.

For products missing everywhere (typically private labels): type a name,
the integration searches Rohlík with it and fills the candidate select.
"""
from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RohlikEanEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ManualSearchText(entry, entry.runtime_data)])


class ManualSearchText(RohlikEanEntity, TextEntity):
    """Action-text: submitting a value runs the search, then clears itself."""

    _attr_translation_key = "manual_search"
    _attr_icon = "mdi:magnify"
    _attr_mode = TextMode.TEXT
    _attr_native_value = ""

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "manual_search")

    async def async_set_value(self, value: str) -> None:
        value = value.strip()
        current = self._data.queue.current
        _LOGGER.info(
            "Manual search input %r (current pending scan: %s)",
            value,
            current["ean"] if current else None,
        )
        if value and current is not None:
            candidates = await self._data.async_manual_search(value)
            _LOGGER.info(
                "Manual search %r: %d candidates for EAN %s",
                value,
                len(candidates),
                current["ean"],
            )
        self._attr_native_value = ""
        self.async_write_ha_state()
