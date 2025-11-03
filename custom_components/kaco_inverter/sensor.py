"""Platform for integration of KACO inverters via RS485."""

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .client.fields import AnnotatedValue
from .coordinator import KacoInverterCoordinator

PARALLEL_UPDATES = 1


_QUANTITY_MAPPING = {
    "W": (SensorDeviceClass.POWER, UnitOfPower.WATT, SensorStateClass.MEASUREMENT),
    "kW": (
        SensorDeviceClass.POWER,
        UnitOfPower.KILO_WATT,
        SensorStateClass.MEASUREMENT,
    ),
    "Wh": (
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.WATT_HOUR,
        SensorStateClass.TOTAL_INCREASING,
    ),
    "kWh": (
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.KILO_WATT_HOUR,
        SensorStateClass.TOTAL_INCREASING,
    ),
    "V": (
        SensorDeviceClass.VOLTAGE,
        UnitOfElectricPotential.VOLT,
        SensorStateClass.MEASUREMENT,
    ),
    "A": (
        SensorDeviceClass.CURRENT,
        UnitOfElectricCurrent.AMPERE,
        SensorStateClass.MEASUREMENT,
    ),
    "°C": (
        SensorDeviceClass.TEMPERATURE,
        UnitOfTemperature.CELSIUS,
        SensorStateClass.MEASUREMENT,
    ),
    "min": (
        SensorDeviceClass.DURATION,
        UnitOfTime.MINUTES,
        SensorStateClass.TOTAL_INCREASING,
    ),
}


def _build_sensor_entity_descriptions(
    data_dict: dict[str, Any],
) -> list[SensorEntityDescription]:
    descriptions = []
    for key, value in data_dict.items():
        if not isinstance(value, AnnotatedValue):
            continue
        quantity_info = _QUANTITY_MAPPING.get(value.quantity)
        if not quantity_info:
            continue
        descriptions.append(
            SensorEntityDescription(
                key=key,
                name=value.description,
                device_class=quantity_info[0],
                native_unit_of_measurement=quantity_info[1],
                state_class=quantity_info[2],
            )
        )

    return descriptions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup the inverter entities."""

    coordinator = KacoInverterCoordinator(hass, entry)

    annotated_initial_reading = (
        await coordinator.async_config_entry_first_refresh_annotated()
    )

    async_add_entities(
        KacoSensor(coordinator, sensor_entity_type)
        for sensor_entity_type in _build_sensor_entity_descriptions(
            annotated_initial_reading
        )
    )


class KacoSensor(CoordinatorEntity[KacoInverterCoordinator], SensorEntity):
    """Representation of a sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KacoInverterCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.device_identifier}_{entity_description.key}"
        )
        self._attr_device_info = coordinator.device_info
        self._attr_native_value = self.coordinator.data[self.entity_description.key]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.data[self.entity_description.key]
        self.async_write_ha_state()
