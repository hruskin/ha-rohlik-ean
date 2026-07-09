"""Rohlík EAN — add products to the Rohlík.cz cart by barcode."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
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
    SERVICE_SEARCH_BY_NAME,
)
from .pending import PendingQueue
from .resolver import (
    STATUS_MATCHED,
    STATUS_NEEDS_CONFIRMATION,
    EanResolver,
    Resolution,
)
from .runtime import RohlikEanData

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR, Platform.TEXT]

_EAN_SCHEMA = vol.All(cv.string, vol.Match(r"^\d{8,14}$"))

type RohlikEanConfigEntry = ConfigEntry[RohlikEanData]


async def async_setup_entry(hass: HomeAssistant, entry: RohlikEanConfigEntry) -> bool:
    """Set up the (single) Rohlík EAN entry."""
    resolver = EanResolver(hass, entry)
    await resolver.async_load()
    queue = PendingQueue(hass)
    await queue.async_load()

    data = RohlikEanData(hass=hass, resolver=resolver, queue=queue)
    entry.runtime_data = data
    hass.data[DOMAIN] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass, data)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RohlikEanConfigEntry) -> bool:
    """Unload the entry, its platforms and services."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN, None)
        for service in (
            SERVICE_ADD_BY_EAN,
            SERVICE_CONFIRM_MATCH,
            SERVICE_FORGET_EAN,
            SERVICE_SEARCH_BY_NAME,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok


def _register_services(hass: HomeAssistant, data: RohlikEanData) -> None:
    resolver = data.resolver

    async def add_by_ean(call: ServiceCall) -> dict[str, Any]:
        ean: str = call.data[ATTR_EAN]
        quantity: int = call.data[ATTR_QUANTITY]
        dry_run: bool = call.data[ATTR_DRY_RUN]

        resolution = await resolver.async_resolve(ean)
        if resolution.status != STATUS_MATCHED:
            return await _report_unresolved(hass, data, resolution, quantity, dry_run)
        if dry_run:
            return _report_matched(hass, resolution, quantity, added=False)

        added = await resolver.async_add_to_cart(resolution.product["id"], quantity)

        # A cached mapping whose product no longer adds may point to a
        # delisted id that Rohlík replaced — re-run the cascade without the
        # cache and retry only when it yields a DIFFERENT product. Same id
        # (or no match) means the mapping is fine and the product is merely
        # out of stock: keep the learned mapping.
        if not added and resolution.source == "cache":
            fresh = await resolver.async_resolve(ean, bypass_cache=True)
            if (
                fresh.status == STATUS_MATCHED
                and fresh.product["id"] != resolution.product["id"]
            ):
                _LOGGER.info(
                    "EAN %s: cached product %s replaced by %s, relearning",
                    ean,
                    resolution.product["id"],
                    fresh.product["id"],
                )
                resolution = fresh
                added = await resolver.async_add_to_cart(
                    resolution.product["id"], quantity
                )

        if not added:
            await data.async_report_add_failed(
                ean,
                resolution.product["id"],
                resolution.product.get("name"),
                quantity,
            )
            return {
                "status": "add_failed",
                ATTR_EAN: ean,
                "source": resolution.source,
                "confidence": resolution.confidence,
                "product": resolution.product,
                "added": False,
            }

        # Backfill the product name (older cache entries may lack it) so
        # events and responses can drive TTS announcements.
        name = resolution.product.get("name") or await resolver.async_cart_product_name(
            resolution.product["id"]
        )
        resolution.product["name"] = name
        await resolver.async_remember(ean, resolution.product["id"], name)
        return _report_matched(hass, resolution, quantity, added=True)

    async def confirm_match(call: ServiceCall) -> dict[str, Any]:
        ean: str = call.data[ATTR_EAN]
        product_id: int = call.data[ATTR_PRODUCT_ID]
        quantity: int = call.data[ATTR_QUANTITY]
        name: str | None = call.data.get(ATTR_NAME)

        await data.async_confirm(ean, product_id, name=name, quantity=quantity)
        return {"status": "confirmed", ATTR_EAN: ean, ATTR_PRODUCT_ID: product_id}

    async def forget_ean(call: ServiceCall) -> dict[str, Any]:
        ean: str = call.data[ATTR_EAN]
        removed = await resolver.async_forget(ean)
        return {"status": "forgotten" if removed else "not_cached", ATTR_EAN: ean}

    async def search_by_name(call: ServiceCall) -> dict[str, Any]:
        candidates = await data.async_manual_search(
            call.data[ATTR_NAME],
            ean=call.data.get(ATTR_EAN),
            quantity=call.data.get(ATTR_QUANTITY),
        )
        return {"candidates": candidates}

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
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH_BY_NAME,
        search_by_name,
        schema=vol.Schema(
            {
                vol.Required(ATTR_NAME): cv.string,
                vol.Optional(ATTR_EAN): _EAN_SCHEMA,
                vol.Optional(ATTR_QUANTITY): cv.positive_int,
            }
        ),
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


async def _report_unresolved(
    hass: HomeAssistant,
    data: RohlikEanData,
    resolution: Resolution,
    quantity: int,
    dry_run: bool,
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
    # Queue even zero-candidate scans: the dashboard card offers a manual
    # name search (text entity) to fill the candidates afterwards.
    if not dry_run:
        await data.queue.async_push(
            {
                "ean": resolution.ean,
                "quantity": quantity,
                "candidates": resolution.candidates,
                "metadata": resolution.metadata,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    if data.resolver.entry.options.get(
        CONF_NOTIFY_UNRESOLVED, DEFAULT_NOTIFY_UNRESOLVED
    ):
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
        lines.append(
            "\nVyber kandidáta v entitě **Kandidát** (select) na dashboardu,"
            " nebo potvrď službou:\n"
            "```yaml\n"
            f"service: {DOMAIN}.{SERVICE_CONFIRM_MATCH}\n"
            "data:\n"
            f"  ean: \"{resolution.ean}\"\n"
            f"  product_id: {resolution.candidates[0]['id'] if resolution.candidates else 0}\n"
            f"  quantity: {quantity}\n"
            "```"
        )
    else:
        if resolution.metadata:
            lines.append(
                "\nProdukt je známý, ale hledání na Rohlíku nic nevrátilo —"
                " Rohlík ho nejspíš vůbec neprodává, případně pod jiným názvem."
            )
        else:
            lines.append(
                "\nKód nezná OpenFoodFacts ani fulltext Rohlíku (časté u"
                " privátních značek)."
            )
        lines.append(
            "Zadej název produktu do pole **Hledat název** na dashboardu"
            " (sken čeká ve frontě) a vyber z nabídnutých kandidátů."
            " Alternativně nauč mapování službou (ID produktu je číslo v URL"
            " na rohlik.cz):\n"
            "```yaml\n"
            f"service: {DOMAIN}.{SERVICE_CONFIRM_MATCH}\n"
            "data:\n"
            f"  ean: \"{resolution.ean}\"\n"
            "  product_id: <ID produktu z URL na rohlik.cz>\n"
            f"  quantity: {quantity}\n"
            "```"
        )
    return "\n".join(lines)
