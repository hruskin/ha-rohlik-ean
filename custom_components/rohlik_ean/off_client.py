"""Minimal OpenFoodFacts client — EAN → product metadata."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

from .const import OFF_URL, OFF_USER_AGENT

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class EanMetadata:
    """Product metadata resolved from an EAN."""

    name: str | None
    brand: str | None
    quantity: str | None

    @property
    def search_query(self) -> str:
        parts = [self.brand.split(",")[0].strip() if self.brand else "", self.name or ""]
        return " ".join(part for part in parts if part).strip()


async def fetch_metadata(session: aiohttp.ClientSession, ean: str) -> EanMetadata | None:
    """Look up an EAN in OpenFoodFacts; None when unknown or unreachable."""
    try:
        async with session.get(
            OFF_URL.format(ean=ean),
            headers={"User-Agent": OFF_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 404:
                return None
            response.raise_for_status()
            payload = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.warning("OpenFoodFacts lookup for %s failed: %s", ean, err)
        return None

    if payload.get("status") != 1:
        return None

    product = payload.get("product", {})
    name = product.get("product_name_cs") or product.get("product_name") or None
    meta = EanMetadata(
        name=name,
        brand=product.get("brands") or None,
        quantity=product.get("quantity") or None,
    )
    if not meta.search_query:
        return None
    return meta
