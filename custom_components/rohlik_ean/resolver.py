"""EAN → Rohlík productId resolution cascade.

Order of attempts:
1. local cache (learned mappings, persisted in .storage)
2. Rohlík fulltext with the raw EAN — when Rohlík has the EAN indexed,
   a single hit is an exact match
3. OpenFoodFacts metadata → Rohlík fulltext by brand+name → candidate scoring
4. give up → caller notifies the user; a manual confirm_match teaches the cache
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CONFIDENCE_THRESHOLD,
    CONF_TRUST_EAN_HIT,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_TRUST_EAN_HIT,
    EVENT_CACHE_CHANGED,
    ROHLIKCZ_DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .matcher import score_candidate, size_conflict
from .off_client import EanMetadata, fetch_metadata

_LOGGER = logging.getLogger(__name__)

STATUS_MATCHED = "matched"
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
STATUS_NOT_FOUND = "not_found"


@dataclass(slots=True)
class Resolution:
    """Result of one resolution attempt."""

    status: str
    ean: str
    source: str | None = None  # cache | rohlik_fulltext | openfoodfacts
    confidence: float = 0.0
    product: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None


class EanResolver:
    """Resolves EANs to Rohlík products, learning from confirmed matches."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cache: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        self._cache = await self._store.async_load() or {}

    @property
    def entry(self) -> ConfigEntry:
        return self._entry

    @property
    def _threshold(self) -> float:
        return self._entry.options.get(
            CONF_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE_THRESHOLD
        )

    @property
    def _trust_ean_hit(self) -> bool:
        return self._entry.options.get(CONF_TRUST_EAN_HIT, DEFAULT_TRUST_EAN_HIT)

    def cached(self, ean: str) -> dict[str, Any] | None:
        return self._cache.get(ean)

    @property
    def mappings(self) -> dict[str, dict[str, Any]]:
        """All learned EAN → product mappings."""
        return dict(self._cache)

    async def async_remember(
        self, ean: str, product_id: int, name: str | None = None
    ) -> None:
        """Persist a confirmed EAN → productId mapping."""
        self._cache[ean] = {
            "product_id": product_id,
            "name": name,
            "cached_at": date.today().isoformat(),
        }
        await self._store.async_save(self._cache)
        self._hass.bus.async_fire(EVENT_CACHE_CHANGED)

    async def async_forget(self, ean: str) -> bool:
        if ean in self._cache:
            del self._cache[ean]
            await self._store.async_save(self._cache)
            self._hass.bus.async_fire(EVENT_CACHE_CHANGED)
            return True
        return False

    async def async_import(self, mappings: dict[str, Any], replace: bool = False) -> int:
        """Import mappings (from a GitHub backup); returns how many changed.

        replace=False only fills EANs missing locally; replace=True swaps
        the whole database for the imported one.
        """
        valid = {
            ean: entry
            for ean, entry in mappings.items()
            if isinstance(entry, dict) and entry.get("product_id")
        }
        if replace:
            changed = 0 if valid == self._cache else len(valid)
            self._cache = valid
        else:
            changed = 0
            for ean, entry in valid.items():
                if ean not in self._cache:
                    self._cache[ean] = entry
                    changed += 1
        if changed:
            await self._store.async_save(self._cache)
            self._hass.bus.async_fire(EVENT_CACHE_CHANGED)
        return changed

    async def async_forget_many(self, eans: list[str]) -> int:
        """Delete a batch of mappings with one save and one change event."""
        removed = 0
        for ean in eans:
            if ean in self._cache:
                del self._cache[ean]
                removed += 1
        if removed:
            await self._store.async_save(self._cache)
            self._hass.bus.async_fire(EVENT_CACHE_CHANGED)
        return removed

    async def async_resolve(self, ean: str, bypass_cache: bool = False) -> Resolution:
        """Run the cascade for one EAN."""
        if not bypass_cache and (cached := self._cache.get(ean)):
            return Resolution(
                status=STATUS_MATCHED,
                ean=ean,
                source="cache",
                confidence=1.0,
                product={"id": cached["product_id"], "name": cached.get("name")},
            )

        session = async_get_clientsession(self._hass)
        meta, ean_hits = await asyncio.gather(
            fetch_metadata(session, ean),
            self.async_search(ean, limit=5),
        )

        # A single fulltext hit for a raw digit string is almost certainly an
        # exact EAN-index match — random digits return nothing.
        if len(ean_hits) == 1 and self._trust_ean_hit:
            hit = ean_hits[0]
            if not (meta and size_conflict(meta.quantity, hit.get("amount"))):
                return Resolution(
                    status=STATUS_MATCHED,
                    ean=ean,
                    source="rohlik_fulltext",
                    confidence=0.9,
                    product=hit,
                    metadata=self._meta_dict(meta),
                )

        candidates = list(ean_hits)
        if meta:
            name_hits = await self.async_search(meta.search_query, limit=8)
            if not name_hits and meta.brand and meta.name:
                name_hits = await self.async_search(meta.name, limit=8)
            seen = {c["id"] for c in candidates}
            candidates.extend(c for c in name_hits if c["id"] not in seen)

        if meta and candidates:
            return self._score(ean, meta, candidates, ean_hits)

        if candidates:
            # No metadata to validate against — let the user pick.
            return Resolution(
                status=STATUS_NEEDS_CONFIRMATION,
                ean=ean,
                source="rohlik_fulltext",
                candidates=candidates[:3],
            )

        return Resolution(
            status=STATUS_NOT_FOUND, ean=ean, metadata=self._meta_dict(meta)
        )

    def _score(
        self,
        ean: str,
        meta: EanMetadata,
        candidates: list[dict[str, Any]],
        ean_hits: list[dict[str, Any]],
    ) -> Resolution:
        ean_hit_ids = {c["id"] for c in ean_hits}
        scored: list[tuple[float, dict[str, Any]]] = []
        for candidate in candidates:
            score = score_candidate(
                meta.name,
                meta.brand,
                meta.quantity,
                candidate.get("name"),
                candidate.get("brand"),
                candidate.get("amount"),
            )
            # Appearing in the raw-EAN search is corroborating evidence.
            if candidate["id"] in ean_hit_ids:
                score = min(1.0, score + 0.2)
            scored.append((score, candidate))
        scored.sort(key=lambda item: item[0], reverse=True)

        best_score, best = scored[0]
        if best_score >= self._threshold:
            return Resolution(
                status=STATUS_MATCHED,
                ean=ean,
                source="openfoodfacts",
                confidence=best_score,
                product=best,
                metadata=self._meta_dict(meta),
            )
        return Resolution(
            status=STATUS_NEEDS_CONFIRMATION,
            ean=ean,
            source="openfoodfacts",
            confidence=best_score,
            candidates=[
                dict(candidate, score=score) for score, candidate in scored[:3]
            ],
            metadata=self._meta_dict(meta),
        )

    async def async_search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Call rohlikcz.search_product and return its result list."""
        response = await self._hass.services.async_call(
            ROHLIKCZ_DOMAIN,
            "search_product",
            {
                "config_entry_id": self.rohlikcz_entry_id(),
                "product_name": query,
                "limit": limit,
            },
            blocking=True,
            return_response=True,
        )
        if not response:
            return []
        return [c for c in response.get("search_results", []) if c.get("id")]

    async def async_add_to_cart(self, product_id: int, quantity: int) -> bool:
        """Add a product to the Rohlík cart; True when it really was added.

        The underlying client swallows per-item errors (out of stock,
        delisted) and only reports successfully added ids.
        """
        response = await self._hass.services.async_call(
            ROHLIKCZ_DOMAIN,
            "add_to_cart",
            {
                "config_entry_id": self.rohlikcz_entry_id(),
                "product_id": product_id,
                "quantity": quantity,
            },
            blocking=True,
            return_response=True,
        )
        added = (response or {}).get("added_products", [])
        return any(str(item) == str(product_id) for item in added)

    async def async_cart_product_name(self, product_id: int) -> str | None:
        """Look up a product's name from the current cart content."""
        response = await self._hass.services.async_call(
            ROHLIKCZ_DOMAIN,
            "get_cart_content",
            {"config_entry_id": self.rohlikcz_entry_id()},
            blocking=True,
            return_response=True,
        )
        for item in (response or {}).get("products", []):
            if str(item.get("id")) == str(product_id):
                return item.get("name")
        return None

    def rohlikcz_entry_id(self) -> str:
        """Return the first loaded rohlikcz config entry."""
        for entry in self._hass.config_entries.async_entries(ROHLIKCZ_DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                return entry.entry_id
        raise ServiceValidationError(
            "No loaded Rohlík.cz (rohlikcz) integration found — install and "
            "configure HA-RohlikCZ first"
        )

    @staticmethod
    def _meta_dict(meta: EanMetadata | None) -> dict[str, Any] | None:
        if meta is None:
            return None
        return {
            "name": meta.name,
            "brand": meta.brand,
            "quantity": meta.quantity,
            "image": meta.image,
        }
