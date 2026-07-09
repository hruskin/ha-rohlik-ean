"""Select: pick the right Rohlík product for the scan waiting in the queue.

Selecting an option IS the confirmation — it teaches the cache and adds
the product to the cart with the originally requested quantity.
"""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RohlikEanEntity

_LOGGER = logging.getLogger(__name__)

_EMPTY = "—"


def _format_option(index: int, candidate: dict) -> str:
    name = candidate.get("name") or f"ID {candidate['id']}"
    amount = candidate.get("amount") or "?"
    price = candidate.get("price") or "?"
    return f"{index} · {name} ({amount}) – {price}"


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([CandidateSelect(entry, entry.runtime_data)])


class CandidateSelect(RohlikEanEntity, SelectEntity):
    """Action-select: choosing an option confirms the current pending scan."""

    _attr_translation_key = "candidate"
    _attr_icon = "mdi:format-list-numbered"
    _attr_current_option = None

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "candidate")

    @property
    def options(self) -> list[str]:
        current = self._data.queue.current
        if current is None or not current["candidates"]:
            return [_EMPTY]
        return [
            _format_option(index, candidate)
            for index, candidate in enumerate(current["candidates"], start=1)
        ]

    @property
    def current_option(self) -> str | None:
        # Action-select: nothing is ever "selected"; state stays unknown
        # while there is something to pick, placeholder otherwise (queue
        # empty, or a scan without candidates awaiting a manual search).
        current = self._data.queue.current
        return _EMPTY if current is None or not current["candidates"] else None

    async def async_select_option(self, option: str) -> None:
        current = self._data.queue.current
        if current is None or option == _EMPTY:
            return
        try:
            index = int(option.split(" · ", 1)[0]) - 1
            candidate = current["candidates"][index]
        except (ValueError, IndexError):
            _LOGGER.warning("Stale candidate option selected: %s", option)
            return
        await self._data.async_confirm(
            current["ean"],
            candidate["id"],
            name=candidate.get("name"),
            quantity=current["quantity"],
        )
