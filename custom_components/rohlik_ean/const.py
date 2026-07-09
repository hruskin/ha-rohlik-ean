"""Constants for the Rohlík EAN integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "rohlik_ean"
ROHLIKCZ_DOMAIN: Final = "rohlikcz"

STORAGE_KEY: Final = f"{DOMAIN}.cache"
QUEUE_STORAGE_KEY: Final = f"{DOMAIN}.queue"
STORAGE_VERSION: Final = 1

SIGNAL_QUEUE_UPDATED: Final = f"{DOMAIN}_queue_updated"

CONF_CONFIDENCE_THRESHOLD: Final = "confidence_threshold"
CONF_TRUST_EAN_HIT: Final = "trust_ean_hit"
CONF_NOTIFY_UNRESOLVED: Final = "notify_unresolved"

DEFAULT_CONFIDENCE_THRESHOLD: Final = 0.75
DEFAULT_TRUST_EAN_HIT: Final = True
DEFAULT_NOTIFY_UNRESOLVED: Final = True

ATTR_EAN: Final = "ean"
ATTR_QUANTITY: Final = "quantity"
ATTR_DRY_RUN: Final = "dry_run"
ATTR_PRODUCT_ID: Final = "product_id"
ATTR_NAME: Final = "name"

SERVICE_ADD_BY_EAN: Final = "add_by_ean"
SERVICE_CONFIRM_MATCH: Final = "confirm_match"
SERVICE_FORGET_EAN: Final = "forget_ean"
SERVICE_SEARCH_BY_NAME: Final = "search_by_name"

EVENT_MATCHED: Final = f"{DOMAIN}_matched"
EVENT_UNRESOLVED: Final = f"{DOMAIN}_unresolved"
EVENT_ADD_FAILED: Final = f"{DOMAIN}_add_failed"

OFF_URL: Final = (
    "https://world.openfoodfacts.org/api/v2/product/{ean}.json"
    "?fields=product_name,product_name_cs,brands,quantity"
)
OFF_USER_AGENT: Final = "ha-rohlik-ean/0.4.1 (https://github.com/hruskin/ha-rohlik-ean)"
