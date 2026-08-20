"""Solar generation sensors for Tesla Solar (Fleet)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from datetime import datetime

from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
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


# Diagnostics. "last_production" is the one that matters during the day: when a
# site stops reporting, calendar_history keeps returning HTTP 200 with trailing
# zero buckets, so the energy sensors look fine while silently frozen.
# "site_last_communication" is its night-time counterpart -- the live_status
# timestamp keeps advancing while the gateway is alive even when production is
# legitimately zero, so it can tell a dark site from a dead one after sunset.
DIAGNOSTIC_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="last_production",
        translation_key="last_production",
        name="Last reported production",
        icon="mdi:clock-alert-outline",
    ),
    SensorEntityDescription(
        key="site_last_communication",
        translation_key="site_last_communication",
        name="Site last communication",
        icon="mdi:radio-tower",
    ),
    SensorEntityDescription(
        key="last_successful_update",
        translation_key="last_successful_update",
        name="Last successful update",
        icon="mdi:cloud-check-outline",
    ),
)


# Instantaneous solar output from live_status (watts). Unlike the four energy
# totals this is a live power reading, not a calendar_history accumulation --
# so it is a real production sensor, not a diagnostic.
POWER_SENSOR = SensorEntityDescription(
    key="solar_power",
    translation_key="solar_power",
    name="Solar power",
    icon="mdi:solar-power",
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
    entities.append(TeslaSolarPowerSensor(coordinator, entry, POWER_SENSOR))
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


class TeslaSolarPowerSensor(CoordinatorEntity[TeslaSolarCoordinator], SensorEntity):
    """Live solar power (watts) from the live_status endpoint."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TeslaSolarCoordinator,
        entry: TeslaSolarConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the power sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        """Return the site's instantaneous solar output in watts."""
        return self.coordinator.site_power

    @property
    def available(self) -> bool:
        """Available once live_status has produced a reading."""
        return super().available and self.coordinator.site_power is not None


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
