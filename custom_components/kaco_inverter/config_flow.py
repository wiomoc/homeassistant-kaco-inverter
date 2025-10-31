"""Config Flow."""

import contextlib
from dataclasses import dataclass
from typing import Any

import serial.tools.list_ports
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PORT
from serial import SerialException

from .client.client import KacoInverterClient, ProtocolException
from .client.model_names import resolve_model_name
from .const import CONF_INVERTER_ADDRESS, CONF_SERIAL_NUMBER, DOMAIN


@dataclass
class _ConnectionInfo:
    model: str
    serial_number: str | None


def _try_connect(
    serial_port_path: str, inverter_address: int
) -> _ConnectionInfo | None:
    try:
        with KacoInverterClient(serial_port_path, inverter_address) as client:
            readings = client.query_readings()
            inverter_type = readings["inverter_type"]
            model = resolve_model_name(inverter_type) or inverter_type
            serial_number = None
            with contextlib.suppress(ProtocolException):
                serial_number = client.query_serial_number()
        return _ConnectionInfo(model=model, serial_number=serial_number)
    except (SerialException, ProtocolException):
        return None


class KacoInverterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Flow for setting up a single KACO device."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Step when user initializes the integration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            connection_info = await self.hass.async_add_executor_job(
                lambda: _try_connect(
                    user_input[CONF_PORT], user_input[CONF_INVERTER_ADDRESS]
                )
            )
            if not connection_info:
                errors["base"] = "cannot_connect"
            else:
                extra_data = {}
                if connection_info.serial_number:
                    extra_data[CONF_SERIAL_NUMBER] = connection_info.serial_number
                    await self.async_set_unique_id(connection_info.serial_number)
                    self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"KACO {connection_info.model} #{user_input[CONF_INVERTER_ADDRESS]:02}",
                    data={**user_input, **extra_data},
                )

        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        list_of_ports = {
            port.device: f"{port}, s/n: {port.serial_number or 'n/a'}"
            + (f" - {port.manufacturer}" if port.manufacturer else "")
            for port in ports
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT): vol.In(list_of_ports),
                    vol.Required(CONF_INVERTER_ADDRESS): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=99)
                    ),
                }
            ),
            errors=errors,
        )
