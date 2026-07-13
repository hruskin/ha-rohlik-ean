"""Sensors: pending-confirmation queue, review list and usage statistics."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RohlikEanEntity


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    async_add_entities(
        [
            PendingSensor(entry, data),
            ReviewSensor(entry, data),
            LearnedSensor(entry, data),
            ContributedSensor(entry, data),
            ScansTodaySensor(entry, data),
        ]
    )


class PendingSensor(RohlikEanEntity, SensorEntity):
    """How many scans wait for confirmation; attributes carry the first one."""

    _attr_translation_key = "pending"
    _attr_icon = "mdi:barcode-scan"
    _attr_native_unit_of_measurement = "skenů"

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "pending")

    @property
    def native_value(self) -> int:
        return self._data.queue.count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self._data.queue.current
        if current is None:
            return {"pending_eans": []}
        return {
            "ean": current["ean"],
            "quantity": current["quantity"],
            "metadata": current.get("metadata"),
            "candidates": current["candidates"],
            "added_at": current.get("added_at"),
            "pending_eans": self._data.queue.eans,
        }


class ReviewSensor(RohlikEanEntity, SensorEntity):
    """Products staged in the review list (review mode)."""

    _attr_translation_key = "review"
    _attr_icon = "mdi:cart-outline"
    _attr_native_unit_of_measurement = "položek"

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "review")

    @property
    def native_value(self) -> int:
        return self._data.review.count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "total_units": self._data.review.total_units,
            "items": self._data.review.items,
        }


class LearnedSensor(RohlikEanEntity, SensorEntity):
    """Number of learned EAN → product mappings."""

    _attr_translation_key = "learned"
    _attr_icon = "mdi:database-check"
    _attr_native_unit_of_measurement = "kódů"

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "learned")

    @property
    def native_value(self) -> int:
        return self._data.resolver.learned_count


class ContributedSensor(RohlikEanEntity, SensorEntity):
    """Number of mappings contributed to OpenFoodFacts."""

    _attr_translation_key = "contributed"
    _attr_icon = "mdi:earth-plus"
    _attr_native_unit_of_measurement = "kódů"

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "contributed")

    @property
    def native_value(self) -> int:
        return self._data.resolver.contributed_count


class ScansTodaySensor(RohlikEanEntity, SensorEntity):
    """Scans that reached the cart/review today."""

    _attr_translation_key = "scans_today"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "skenů"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, entry, data) -> None:
        super().__init__(entry, data, "scans_today")

    @property
    def native_value(self) -> int:
        return self._data.stats.today
