"""Shared runtime state and confirm/discard actions.

Lives in its own module so both __init__ (services) and the entity
platforms can import it without circular imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from homeassistant.exceptions import HomeAssistantError

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
from .review import ReviewList
from .stats import ScanStats


@dataclass(slots=True)
class RohlikEanData:
    """Per-entry runtime objects."""

    hass: HomeAssistant
    resolver: EanResolver
    queue: PendingQueue
    review: ReviewList
    stats: ScanStats
    images: ImageCache = field(default_factory=ImageCache)
    # Last successful direct cart add, for undo: {ean, product_id, name, quantity}.
    last_add: dict | None = None

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

    def track_add(self, ean: str, product_id: int, name: str | None, quantity: int) -> None:
        """Remember the last direct cart add so it can be undone."""
        self.last_add = {
            "ean": ean,
            "product_id": product_id,
            "name": name,
            "quantity": quantity,
        }

    async def async_undo_last(self) -> dict:
        """Remove the last-added product's cart line via the rohlikcz hub.

        Best effort: rohlikcz exposes no remove-from-cart service, so we
        reach its account object and delete the whole line for that product
        (Rohlík has no per-unit removal here).
        """
        last = self.last_add
        if not last:
            raise ServiceValidationError("Není co vrátit — žádné poslední přidání")

        account = self.resolver.rohlikcz_account()
        delete = getattr(account, "delete_from_cart", None)
        if account is None or delete is None:
            raise HomeAssistantError(
                "Vrácení není dostupné — aktuální verze HA-RohlikCZ"
                " neumožňuje odebrání z košíku"
            )

        cart_item_id = None
        for item in await self.resolver.async_cart_items():
            if str(item.get("id")) == str(last["product_id"]):
                cart_item_id = item.get("cart_item_id")
                break
        if cart_item_id is None:
            self.last_add = None
            return {"status": "not_in_cart", ATTR_PRODUCT_ID: last["product_id"]}

        await delete(str(cart_item_id))
        self.last_add = None
        return {
            "status": "removed",
            ATTR_EAN: last["ean"],
            ATTR_PRODUCT_ID: last["product_id"],
            ATTR_NAME: last["name"],
        }

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
