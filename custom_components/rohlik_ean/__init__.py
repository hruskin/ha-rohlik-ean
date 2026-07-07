"""Rohlík EAN — add products to the Rohlík.cz cart by barcode."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_DRY_RUN,
    ATTR_EAN,
    ATTR_NAME,
    ATTR_PRODUCT_ID,
    ATTR_QUANTITY,
    CONF_NOTIFY_UNRESOLVED,
    DEFAULT_NOTIFY_UNRESOLVED,
    DOMAIN,
    EVENT_MATCHED,
    EVENT_UNRESOLVED,
    SERVICE_ADD_BY_EAN,
    SERVICE_CONFIRM_MATCH,
    SERVICE_FORGET_EAN,
)
from .resolver import (
    STATUS_MATCHED,
    STATUS_NEEDS_CONFIRMATION,
    EanResolver,
    Resolution,
)

_LOGGER = logging.getLogger(__name__)

_EAN_SCHEMA = vol.All(cv.string, vol.Match(r"^\d{8,14}$"))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the (single) Rohlík EAN entry."""
    resolver = EanResolver(hass, entry)
    await resolver.async_load()
    hass.data[DOMAIN] = resolver
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the entry and its services."""
    hass.data.pop(DOMAIN, None)
    for service in (SERVICE_ADD_BY_EAN, SERVICE_CONFIRM_MATCH, SERVICE_FORGET_EAN):
        hass.services.async_remove(DOMAIN, service)
    return True


def _register_services(hass: HomeAssistant) -> None:
    resolver: EanResolver = hass.data[DOMAIN]

    async def add_by_ean(call: ServiceCall) -> dict[str, Any]:
        ean: str = call.data[ATTR_EAN]
        quantity: int = call.data[ATTR_QUANTITY]
        dry_run: bool = call.data[ATTR_DRY_RUN]

        resolution = await resolver.async_resolve(ean)

        # A cached product may have been delisted; retry the cascade once.
        if (
            resolution.status == STATUS_MATCHED
            and not dry_run
            and resolution.source == "cache"
        ):
            try:
                await resolver.async_add_to_cart(
                    resolution.product["id"], quantity
                )
                return _report_matched(hass, resolution, quantity, added=True)
            except HomeAssistantError:
                _LOGGER.warning(
                    "Cached product %s for EAN %s failed to add, re-resolving",
                    resolution.product["id"],
                    ean,
                )
                await resolver.async_forget(ean)
                resolution = await resolver.async_resolve(ean)

        if resolution.status == STATUS_MATCHED:
            added = False
            if not dry_run:
                await resolver.async_add_to_cart(resolution.product["id"], quantity)
                added = True
                await resolver.async_remember(
                    ean, resolution.product["id"], resolution.product.get("name")
                )
            return _report_matched(hass, resolution, quantity, added=added)

        return _report_unresolved(hass, resolver, resolution, quantity)

    async def confirm_match(call: ServiceCall) -> dict[str, Any]:
        ean: str = call.data[ATTR_EAN]
        product_id: int = call.data[ATTR_PRODUCT_ID]
        quantity: int = call.data[ATTR_QUANTITY]
        name: str | None = call.data.get(ATTR_NAME)

        await resolver.async_remember(ean, product_id, name)
        if quantity > 0:
            await resolver.async_add_to_cart(product_id, quantity)
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_{ean}")
        hass.bus.async_fire(
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
        return {"status": "confirmed", ATTR_EAN: ean, ATTR_PRODUCT_ID: product_id}

    async def forget_ean(call: ServiceCall) -> dict[str, Any]:
        ean: str = call.data[ATTR_EAN]
        removed = await resolver.async_forget(ean)
        return {"status": "forgotten" if removed else "not_cached", ATTR_EAN: ean}

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_BY_EAN,
        add_by_ean,
        schema=vol.Schema(
            {
                vol.Required(ATTR_EAN): _EAN_SCHEMA,
                vol.Optional(ATTR_QUANTITY, default=1): cv.positive_int,
                vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIRM_MATCH,
        confirm_match,
        schema=vol.Schema(
            {
                vol.Required(ATTR_EAN): _EAN_SCHEMA,
                vol.Required(ATTR_PRODUCT_ID): cv.positive_int,
                vol.Optional(ATTR_QUANTITY, default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0)
                ),
                vol.Optional(ATTR_NAME): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORGET_EAN,
        forget_ean,
        schema=vol.Schema({vol.Required(ATTR_EAN): _EAN_SCHEMA}),
        supports_response=SupportsResponse.OPTIONAL,
    )


def _report_matched(
    hass: HomeAssistant, resolution: Resolution, quantity: int, added: bool
) -> dict[str, Any]:
    hass.bus.async_fire(
        EVENT_MATCHED,
        {
            ATTR_EAN: resolution.ean,
            ATTR_PRODUCT_ID: resolution.product["id"],
            ATTR_NAME: resolution.product.get("name"),
            "source": resolution.source,
            "confidence": resolution.confidence,
            "added": added,
            ATTR_QUANTITY: quantity,
        },
    )
    return {
        "status": resolution.status,
        ATTR_EAN: resolution.ean,
        "source": resolution.source,
        "confidence": resolution.confidence,
        "product": resolution.product,
        "added": added,
    }


def _report_unresolved(
    hass: HomeAssistant,
    resolver: EanResolver,
    resolution: Resolution,
    quantity: int,
) -> dict[str, Any]:
    hass.bus.async_fire(
        EVENT_UNRESOLVED,
        {
            ATTR_EAN: resolution.ean,
            "status": resolution.status,
            "candidates": resolution.candidates,
            "metadata": resolution.metadata,
            ATTR_QUANTITY: quantity,
        },
    )
    if resolver.entry.options.get(CONF_NOTIFY_UNRESOLVED, DEFAULT_NOTIFY_UNRESOLVED):
        persistent_notification.async_create(
            hass,
            _unresolved_message(resolution, quantity),
            title=f"Rohlík EAN: nerozpoznaný kód {resolution.ean}",
            notification_id=f"{DOMAIN}_{resolution.ean}",
        )
    return {
        "status": resolution.status,
        ATTR_EAN: resolution.ean,
        "source": resolution.source,
        "confidence": resolution.confidence,
        "candidates": resolution.candidates,
        "metadata": resolution.metadata,
        "added": False,
    }


def _unresolved_message(resolution: Resolution, quantity: int) -> str:
    lines: list[str] = []
    if resolution.metadata:
        meta = resolution.metadata
        lines.append(
            f"OpenFoodFacts: **{meta.get('brand') or '?'} {meta.get('name') or '?'}**"
            f" ({meta.get('quantity') or 'gramáž neznámá'})"
        )
    else:
        lines.append("Kód nebyl nalezen v OpenFoodFacts.")

    if resolution.status == STATUS_NEEDS_CONFIRMATION:
        lines.append("\nKandidáti na Rohlíku:")
        for idx, candidate in enumerate(resolution.candidates, start=1):
            score = f" · skóre {candidate['score']}" if "score" in candidate else ""
            lines.append(
                f"{idx}. **{candidate.get('name')}** ({candidate.get('amount') or '?'})"
                f" – {candidate.get('price') or '?'} – ID `{candidate['id']}`{score}"
            )
        first_id = resolution.candidates[0]["id"] if resolution.candidates else 0
        lines.append(
            "\nPotvrď správný produkt (uloží se do cache a přidá do košíku):\n"
            "```yaml\n"
            f"service: {DOMAIN}.{SERVICE_CONFIRM_MATCH}\n"
            "data:\n"
            f"  ean: \"{resolution.ean}\"\n"
            f"  product_id: {first_id}\n"
            f"  quantity: {quantity}\n"
            "```"
        )
    else:
        lines.append(
            "\nProdukt se nepodařilo najít ani na Rohlíku. Najdi ho ručně a nauč"
            " integraci mapování:\n"
            "```yaml\n"
            f"service: {DOMAIN}.{SERVICE_CONFIRM_MATCH}\n"
            "data:\n"
            f"  ean: \"{resolution.ean}\"\n"
            "  product_id: <ID produktu z URL na rohlik.cz>\n"
            f"  quantity: {quantity}\n"
            "```"
        )
    return "\n".join(lines)
