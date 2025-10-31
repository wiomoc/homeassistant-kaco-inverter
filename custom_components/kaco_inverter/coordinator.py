"""Coordinator for fetching measurements from a inverter."""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PORT,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import slugify

from .client import ProtocolException
from .client.client import KacoInverterClient
from .client.fields import AnnotatedValue
from .client.model_names import resolve_model_name
from .const import CONF_INVERTER_ADDRESS, CONF_SERIAL_NUMBER, DOMAIN

_LOGGER = logging.getLogger(__name__)


class KacoInverterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for fetching all measurments via a single reading."""

    device_info: DeviceInfo | None
    device_identifier: str | None
    _client: KacoInverterClient | None

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Kaco Inverter",
            config_entry=config_entry,
            update_interval=timedelta(seconds=30),
        )
        self.device_info = None
        self.device_identifier = None
        self._client = None

    async def async_config_entry_first_refresh_annotated(
        self,
    ) -> dict[str, AnnotatedValue]:
        """Perform the initial, annotated refresh of inverter data and configure device metadata.

        This coroutine performs the first successful data fetch from a KACO inverter when
        a config entry is being set up. It opens a KacoInverterClient using configuration
        values from self.config_entry, requests annotated readings, and attempts to
        retrieve the inverter serial number. The method also validates an expected
        serial from the config entry (if present) and raises ConfigEntryError on a
        mismatch.

        Returns:
            The annotated initial readings retrieved from the inverter.

        Raises:
            ConfigEntryError: If an expected serial number (provided in the config entry)
                    does not match the inverter's actual serial number.
            ConfigEntryNotReady: If any unexpected error occurs during the initial fetch
                    (errors are also stored in self.last_exception and logged).
        """
        assert self.config_entry
        config = self.config_entry.data
        port_name = config[CONF_PORT]
        inverter_address = config[CONF_INVERTER_ADDRESS]
        self._client = KacoInverterClient(port=port_name, address=inverter_address)
        with self._client as client:
            try:
                initial_reading = client.query_readings(annotate=True)
            except Exception as err:  # pylint: disable=broad-except
                self.last_exception = err
                self.logger.exception("Unexpected error fetching %s data", self.name)
                self.last_update_success = False
                raise ConfigEntryNotReady from err

            actual_serial_number = None
            try:
                actual_serial_number = client.query_serial_number()
            except ProtocolException:
                # Not all inverters support the query serial number command
                pass
            else:
                expected_serial_number = config.get(CONF_SERIAL_NUMBER)
                if (
                    expected_serial_number
                    and expected_serial_number != actual_serial_number
                ):
                    raise ConfigEntryError(
                        "Serial number mismatch: "
                        f"{actual_serial_number} != {expected_serial_number}"
                    )

        inverter_type = initial_reading["inverter_type"]
        if actual_serial_number:
            identifier = slugify(actual_serial_number)
        else:
            identifier = f"{slugify(port_name)}__{inverter_address:02}"
        self.device_identifier = identifier
        self.device_info = DeviceInfo(
            manufacturer="KACO new energy",
            model_id=inverter_type,
            model=resolve_model_name(inverter_type),
            serial_number=actual_serial_number,
            identifiers={(DOMAIN, identifier)},
        )
        self.data = {
            key: value.value if isinstance(value, AnnotatedValue) else value
            for key, value in initial_reading.items()
        }
        self.last_update_success = True

        return initial_reading

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
