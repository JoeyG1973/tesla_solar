"""Solar generation sensors for Tesla Solar (Fleet)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from datetime import datetime

from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TeslaSolarConfigEntry
from .const import DOMAIN
from .coordinator import TeslaSolarCoordinator

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="day",
        translation_key="solar_today",
        name="Solar today",
        icon="mdi:solar-power",
    ),
    SensorEntityDescription(
        key="month",
        translation_key="solar_month",
        name="Solar this month",
        icon="mdi:solar-power",
    ),
    SensorEntityDescription(
        key="year",
        translation_key="solar_year",
        name="Solar this year",
        icon="mdi:solar-power",
    ),
    SensorEntityDescription(
        key="lifetime",
        translation_key="solar_lifetime",
        name="Solar lifetime",
        icon="mdi:counter",
    ),
)


# Diagnostics. "last_production" is the one that matters: when a site stops
# reporting, calendar_history keeps returning HTTP 200 with trailing zero
# buckets, so the energy sensors look fine while silently frozen. This is the
# only entity that shows it.
DIAGNOSTIC_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="last_production",
        translation_key="last_production",
        name="Last reported production",
        icon="mdi:clock-alert-outline",
    ),
    SensorEntityDescription(
        key="last_successful_update",
        translation_key="last_successful_update",
        name="Last successful update",
        icon="mdi:cloud-check-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tesla Solar sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        TeslaSolarSensor(coordinator, entry, desc) for desc in SENSORS
    ]
    entities += [
        TeslaSolarDiagnosticSensor(coordinator, entry, desc)
        for desc in DIAGNOSTIC_SENSORS
    ]
    async_add_entities(entities)


def _device_info(entry: TeslaSolarConfigEntry) -> DeviceInfo:
    """Shared device entry for every Tesla Solar entity."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Tesla Solar",
        manufacturer="Tesla",
        model="Fleet API (energy site)",
        entry_type=DeviceEntryType.SERVICE,
    )


class TeslaSolarSensor(CoordinatorEntity[TeslaSolarCoordinator], SensorEntity):
    """A Tesla Fleet solar-generation total for a given period."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self,
        coordinator: TeslaSolarCoordinator,
        entry: TeslaSolarConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        """Return the total for this period."""
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Available when we have a value for this period."""
        return (
            super().available
            and self.coordinator.data.get(self.entity_description.key) is not None
        )


class TeslaSolarDiagnosticSensor(
    CoordinatorEntity[TeslaSolarCoordinator], SensorEntity
):
    """Timestamp diagnostics describing the health of the feed."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: TeslaSolarCoordinator,
        entry: TeslaSolarConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        """Always available -- these exist to explain outages."""
        return True

    @property
    def native_value(self) -> datetime | None:
        """Return the tracked timestamp."""
        return getattr(self.coordinator, self.entity_description.key, None)
