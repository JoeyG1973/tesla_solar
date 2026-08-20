"""Health diagnostics for Tesla Solar (Fleet).

Exposes a single problem sensor that is ``on`` when the solar figures cannot
be trusted -- either because the API is failing, or (the harder case) because
the API is happily returning HTTP 200 for a site that has stopped reporting.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarConfigEntry
from .const import DOMAIN
from .coordinator import TeslaSolarCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tesla Solar health sensor."""
    async_add_entities([TeslaSolarProblemSensor(entry.runtime_data, entry)])


class TeslaSolarProblemSensor(
    CoordinatorEntity[TeslaSolarCoordinator], BinarySensorEntity
):
    """On when the Tesla Solar data is stale or the feed is failing."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "data_problem"
    _attr_icon = "mdi:solar-power-variant-outline"

    def __init__(
        self, coordinator: TeslaSolarCoordinator, entry: TeslaSolarConfigEntry
    ) -> None:
        """Initialize the health sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_data_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Tesla Solar",
            manufacturer="Tesla",
            model="Fleet API (energy site)",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Always available.

        Deliberately NOT gated on ``coordinator.last_update_success``: a health
        sensor that disappears exactly when the integration breaks is useless.
        """
        return True

    @property
    def is_on(self) -> bool:
        """Return True when the solar figures should not be trusted."""
        return self.coordinator.has_problem

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Explain *why*, so a notification can be actionable."""
        coordinator = self.coordinator
        age = coordinator.data_age
        if coordinator.is_stale:
            reason = "site_not_reporting"
        elif not coordinator.last_update_success:
            reason = "api_failing"
        else:
            reason = None
        return {
            "reason": reason,
            "last_production": (
                coordinator.last_production.isoformat()
                if coordinator.last_production
                else None
            ),
            "hours_since_production": (
                round(age.total_seconds() / 3600, 1) if age is not None else None
            ),
            "stale_after_hours": int(
                coordinator.stale_after.total_seconds() // 3600
            ),
            "last_successful_update": (
                coordinator.last_successful_update.isoformat()
                if coordinator.last_successful_update
                else None
            ),
            "last_error": coordinator.last_error,
        }
