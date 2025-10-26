"""Platform for integration of KACO inverter readings."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PORT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import ProtocolException
from .client.client import KacoInverterClient
from .client.fields import AnnotatedValue
from .client.model_names import resolve_model_name
from .const import CONF_INVERTER_ADDRESS, CONF_SERIAL_NUMBER, DOMAIN

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Setup the inverter entities."""

    coordinator = KacoInverterCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        KacoSensor(coordinator, sensor_entity_type)
        for sensor_entity_type in coordinator.sensor_entity_descriptions
    )


_QUANTITY_MAPPING = {
    "W": (SensorDeviceClass.POWER, UnitOfPower.WATT, SensorStateClass.MEASUREMENT),
    "kW": (SensorDeviceClass.POWER, UnitOfPower.KILO_WATT, SensorStateClass.MEASUREMENT),
    "Wh": (SensorDeviceClass.ENERGY, UnitOfEnergy.WATT_HOUR, SensorStateClass.TOTAL_INCREASING),
    "kWh": (SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, SensorStateClass.TOTAL_INCREASING),
    "V": (SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, SensorStateClass.MEASUREMENT),
    "A": (SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, SensorStateClass.MEASUREMENT),
    "°C": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT),
    "min": (SensorDeviceClass.DURATION, UnitOfTime.MINUTES, SensorStateClass.TOTAL_INCREASING)
}

def _build_sensor_entity_descriptions(data_dict: dict[str, Any]) -> list[SensorEntityDescription]:
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


class KacoInverterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    _client: KacoInverterClient | None
    device_info: DeviceInfo | None
    sensor_entity_descriptions: list[SensorEntityDescription]

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name="My sensor",
            config_entry=config_entry,
            update_interval=timedelta(seconds=30),
            always_update=False,
        )
        self.device_info = None
        self._client = None

    async def _async_setup(self):
        assert self.config_entry
        config = self.config_entry.data
        port_name = config[CONF_PORT]
        inverter_address = config[CONF_INVERTER_ADDRESS]
        self._client = KacoInverterClient(port=port_name, address=inverter_address)
        try:
            with self._client as client:
                initial_reading = client.query_readings(annotate=True)
                actual_serial_number = None
                try:
                    actual_serial_number = client.query_serial_number()
                except ProtocolException:
                    pass
                else:
                    expected_serial_number = config.get(CONF_SERIAL_NUMBER)
                    if (
                        expected_serial_number
                        and expected_serial_number != actual_serial_number
                    ):
                        raise ConfigEntryError(
                            f"Serial number mismatch: {actual_serial_number} != {expected_serial_number}"
                        )
        except Exception as e:
            self._client = None
            raise UpdateFailed("Can't connect to inverter") from e
        else:
            inverter_type = initial_reading["inverter_type"]
            self.sensor_entity_descriptions = _build_sensor_entity_descriptions(
                initial_reading
            )
            self.device_info = DeviceInfo(
                manufacturer="KACO new energy",
                model_id=inverter_type,
                model=resolve_model_name(inverter_type),
                serial_number=actual_serial_number,
                connections={(DOMAIN, f"{port_name}: {inverter_address:02}")},
            )

    async def _async_update_data(self) -> dict[str, Any]:
        def _update_data():
            try:
                if not self._client:
                    assert self.config_entry
                    config = self.config_entry.data
                    self._client = KacoInverterClient(
                        port=config[CONF_PORT], address=config[CONF_INVERTER_ADDRESS]
                    )
                with self._client as client:
                    return client.query_readings()
            except ProtocolException as e:
                self._client = None
                raise UpdateFailed("Can't connect to inverter") from e
        return await self.hass.async_add_executor_job(_update_data)


class KacoSensor(CoordinatorEntity[KacoInverterCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KacoInverterCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, context=entity_description.key)
        self.entity_description = entity_description
        device_info = coordinator.device_info
        if device_info is None:
            raise ConfigEntryError("Missing device info")
        if serial_number := device_info.get("serial_number"):
            self._attr_unique_id = f"{serial_number}_{entity_description.key}"
        self._attr_device_info = device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.data[self.entity_description.key]
        self.async_write_ha_state()
