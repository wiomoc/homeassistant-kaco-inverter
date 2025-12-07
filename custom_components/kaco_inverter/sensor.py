"""Platform for integration of KACO inverters via RS485."""

from collections.abc import Iterable
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
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

from .client.fields import AnnotatedValue, Status
from .coordinator import KacoConfigEntry, KacoInverterCoordinator

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
) -> Iterable[SensorEntityDescription]:
    yield SensorEntityDescription(
        key="status",
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        state_class=SensorStateClass.MEASUREMENT,
    )
    for key, value in data_dict.items():
        if not isinstance(value, AnnotatedValue):
            continue
        quantity_info = _QUANTITY_MAPPING.get(value.quantity)
        if not quantity_info:
            continue
        yield SensorEntityDescription(
            key=key,
            name=value.description,
            device_class=quantity_info[0],
            native_unit_of_measurement=quantity_info[1],
            state_class=quantity_info[2],
        )


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: KacoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup the inverter entities."""
    coordinator = entry.runtime_data

    assert coordinator.annotated_initial_reading
    async_add_entities(
        KacoSensor(coordinator, sensor_entity_type)
        for sensor_entity_type in _build_sensor_entity_descriptions(
            coordinator.annotated_initial_reading
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
        self._update_value()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.entity_description.key == "daily_yield" and self.coordinator.data.get(
            "status"
        ) in (Status.STARTING_UP, Status.SYNCING_TO_GRID, Status.TURNING_OFF):
            # Ignore daily yield from past day
            return
        self._update_value()
        self.async_write_ha_state()

    def _update_value(self) -> None:
        value = self.coordinator.data[self.entity_description.key]
        if self.entity_description.key == "status":
            value = value.name
        self._attr_native_value = value
