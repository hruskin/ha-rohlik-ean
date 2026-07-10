"""Shared runtime state and confirm/discard actions.

Lives in its own module so both __init__ (services) and the entity
platforms can import it without circular imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import (
    ATTR_EAN,
    ATTR_NAME,
    ATTR_PRODUCT_ID,
    ATTR_QUANTITY,
    CONF_NOTIFY_UNRESOLVED,
    DEFAULT_NOTIFY_UNRESOLVED,
    DOMAIN,
    EVENT_ADD_FAILED,
    EVENT_MATCHED,
)
from .images import ImageCache
from .pending import PendingQueue
from .resolver import EanResolver


@dataclass(slots=True)
class RohlikEanData:
    """Per-entry runtime objects."""

    hass: HomeAssistant
    resolver: EanResolver
    queue: PendingQueue
    images: ImageCache = field(default_factory=ImageCache)

    async def async_confirm(
        self,
        ean: str,
        product_id: int,
        name: str | None = None,
        quantity: int = 0,
    ) -> None:
        """Teach the cache, optionally add to cart, and clear pending state."""
        added = False
        if quantity > 0:
            added = await self.resolver.async_add_to_cart(product_id, quantity)
            if added and not name:
                name = await self.resolver.async_cart_product_name(product_id)
        await self.resolver.async_remember(ean, product_id, name)
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
                "added": added,
                ATTR_QUANTITY: quantity,
            },
        )
        if quantity > 0 and not added:
            await self.async_report_add_failed(ean, product_id, name, quantity)

    async def async_report_add_failed(
        self, ean: str, product_id: int, name: str | None, quantity: int
    ) -> None:
        """Announce that a resolved product could not be added to the cart."""
        self.hass.bus.async_fire(
            EVENT_ADD_FAILED,
            {
                ATTR_EAN: ean,
                ATTR_PRODUCT_ID: product_id,
                ATTR_NAME: name,
                ATTR_QUANTITY: quantity,
                "reason": "unavailable",
            },
        )
        if self.resolver.entry.options.get(
            CONF_NOTIFY_UNRESOLVED, DEFAULT_NOTIFY_UNRESOLVED
        ):
            label = name or f"ID {product_id}"
            persistent_notification.async_create(
                self.hass,
                f"**{label}** (EAN {ean}) se nepodařilo přidat do košíku —"
                " nejspíš je vyprodaný. Naučené mapování zůstává uložené;"
                " zkus to později.",
                title="Rohlík EAN: produkt nedostupný",
                notification_id=f"{DOMAIN}_fail_{ean}",
            )

    async def async_manual_search(
        self,
        name: str,
        ean: str | None = None,
        quantity: int | None = None,
    ) -> list[dict]:
        """Search Rohlík by a user-typed name and offer results as candidates.

        Without an explicit EAN targets the current pending scan.
        """
        if ean is None:
            current = self.queue.current
            if current is None:
                raise ServiceValidationError(
                    "No pending scan to search for — provide an EAN"
                )
            ean = current["ean"]
        candidates = await self.resolver.async_search(name, limit=8)
        await self.queue.async_set_candidates(ean, candidates, quantity=quantity)
        return candidates

    async def async_discard(self, ean: str | None = None) -> dict | None:
        """Drop a pending scan (oldest when no EAN given) without learning."""
        if ean is None:
            item = await self.queue.async_pop_current()
        else:
            item = await self.queue.async_remove(ean)
        if item:
            persistent_notification.async_dismiss(
                self.hass, f"{DOMAIN}_{item['ean']}"
            )
        return item
