"""Shared runtime state and confirm/discard actions.

Lives in its own module so both __init__ (services) and the entity
platforms can import it without circular imports.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_EAN,
    ATTR_NAME,
    ATTR_PRODUCT_ID,
    ATTR_QUANTITY,
    DOMAIN,
    EVENT_MATCHED,
)
from .pending import PendingQueue
from .resolver import EanResolver


@dataclass(slots=True)
class RohlikEanData:
    """Per-entry runtime objects."""

    hass: HomeAssistant
    resolver: EanResolver
    queue: PendingQueue

    async def async_confirm(
        self,
        ean: str,
        product_id: int,
        name: str | None = None,
        quantity: int = 0,
    ) -> None:
        """Teach the cache, optionally add to cart, and clear pending state."""
        await self.resolver.async_remember(ean, product_id, name)
        if quantity > 0:
            await self.resolver.async_add_to_cart(product_id, quantity)
        await self.queue.async_remove(ean)
        persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{ean}")
        self.hass.bus.async_fire(
            EVENT_MATCHED,
            {
                ATTR_EAN: ean,
                ATTR_PRODUCT_ID: product_id,
                ATTR_NAME: name,
                "source": "manual",
                "confidence": 1.0,
                "added": quantity > 0,
                ATTR_QUANTITY: quantity,
            },
        )

    async def async_discard_current(self) -> dict | None:
        """Drop the oldest pending scan without learning anything."""
        item = await self.queue.async_pop_current()
        if item:
            persistent_notification.async_dismiss(
                self.hass, f"{DOMAIN}_{item['ean']}"
            )
        return item
