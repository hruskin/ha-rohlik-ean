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
CONF_OFF_USER: Final = "off_user"
CONF_OFF_PASSWORD: Final = "off_password"

DEFAULT_CONFIDENCE_THRESHOLD: Final = 0.75
DEFAULT_TRUST_EAN_HIT: Final = True
DEFAULT_NOTIFY_UNRESOLVED: Final = True

ATTR_EAN: Final = "ean"
ATTR_EANS: Final = "eans"
ATTR_QUANTITY: Final = "quantity"
ATTR_DRY_RUN: Final = "dry_run"
ATTR_PRODUCT_ID: Final = "product_id"
ATTR_PRODUCT_IDS: Final = "product_ids"
ATTR_NAME: Final = "name"

SERVICE_ADD_BY_EAN: Final = "add_by_ean"
SERVICE_CONFIRM_MATCH: Final = "confirm_match"
SERVICE_FORGET_EAN: Final = "forget_ean"
SERVICE_SEARCH_BY_NAME: Final = "search_by_name"
SERVICE_GET_QUEUE: Final = "get_queue"
SERVICE_DISCARD_SCAN: Final = "discard_scan"
SERVICE_GET_MAPPINGS: Final = "get_mappings"
SERVICE_FORGET_EANS: Final = "forget_eans"
SERVICE_SEARCH_PRODUCTS: Final = "search_products"
SERVICE_GET_PRODUCT_IMAGES: Final = "get_product_images"
SERVICE_CONTRIBUTE_TO_OFF: Final = "contribute_to_off"

PANEL_URL_PATH: Final = "rohlik-ean"
PANEL_JS_URL: Final = "/rohlik_ean_panel/panel.js"

EVENT_MATCHED: Final = f"{DOMAIN}_matched"
EVENT_UNRESOLVED: Final = f"{DOMAIN}_unresolved"
EVENT_ADD_FAILED: Final = f"{DOMAIN}_add_failed"
EVENT_QUEUE_CHANGED: Final = f"{DOMAIN}_queue_changed"
EVENT_CACHE_CHANGED: Final = f"{DOMAIN}_cache_changed"

OFF_URL: Final = (
    "https://world.openfoodfacts.org/api/v2/product/{ean}.json"
    "?fields=product_name,product_name_cs,brands,quantity,image_front_small_url"
)
OFF_WRITE_URL: Final = "https://world.openfoodfacts.org/cgi/product_jqm2.pl"
OFF_USER_AGENT: Final = "ha-rohlik-ean/0.10.2 (https://github.com/hruskin/ha-rohlik-ean)"
