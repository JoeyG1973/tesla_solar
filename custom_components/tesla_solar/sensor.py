"""Solar generation sensors for Tesla Solar (Fleet)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TeslaSolarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tesla Solar sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        TeslaSolarSensor(coordinator, entry, desc) for desc in SENSORS
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Tesla Solar",
            manufacturer="Tesla",
            model="Fleet API (energy site)",
            entry_type=DeviceEntryType.SERVICE,
        )

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
