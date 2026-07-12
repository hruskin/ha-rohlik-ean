"""Minimal OpenFoodFacts client — EAN → product metadata."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

from .const import OFF_URL, OFF_USER_AGENT, OFF_WRITE_URL

_LOGGER = logging.getLogger(__name__)


class OFFContributeError(Exception):
    """Writing a product to OpenFoodFacts failed."""


@dataclass(slots=True)
class EanMetadata:
    """Product metadata resolved from an EAN."""

    name: str | None
    brand: str | None
    quantity: str | None
    image: str | None = None

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
        image=product.get("image_front_small_url") or None,
    )
    if not meta.search_query:
        return None
    return meta


async def contribute_product(
    session: aiohttp.ClientSession,
    user_id: str,
    password: str,
    ean: str,
    name: str | None = None,
    brand: str | None = None,
    quantity: str | None = None,
) -> None:
    """Create/extend an OpenFoodFacts product with textual facts.

    Only name/brand/quantity — never images (Rohlík's photos are not ours
    to license).
    """
    form = {
        "code": ean,
        "user_id": user_id,
        "password": password,
        "lc": "cs",
        "lang": "cs",
    }
    if name:
        form["product_name"] = name
    if brand:
        form["brands"] = brand
    if quantity:
        form["quantity"] = quantity

    try:
        async with session.post(
            OFF_WRITE_URL,
            data=form,
            headers={"User-Agent": OFF_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            response.raise_for_status()
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise OFFContributeError(f"OpenFoodFacts unreachable: {err}") from err

    if payload.get("status") != 1:
        raise OFFContributeError(
            payload.get("status_verbose") or "unknown OpenFoodFacts error"
        )
