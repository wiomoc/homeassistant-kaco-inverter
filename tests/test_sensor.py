"""Test the coordinator and the setup of sensor entites."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import EntityRegistry
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.kaco_inverter.client.fields import AnnotatedValue, Status


@pytest.fixture(name="mock_kaco_client")
def mock_kaco_client_fixture() -> Generator[MagicMock]:
    """Mock inverter client."""
    client_obj_mock = MagicMock()
    with patch(
        "custom_components.kaco_inverter.coordinator.KacoInverterClient",
        MagicMock(return_value=client_obj_mock),
    ):
        client_obj_mock.__enter__ = lambda *args, **kwargs: client_obj_mock
        client_obj_mock.__exit__ = lambda *args, **kwargs: None
        yield client_obj_mock


async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    mock_config_entry: MockConfigEntry,
    mock_kaco_client: MagicMock,
    entity_registry: EntityRegistry,
) -> None:
    """Test the setup of sensor entities."""
    mock_kaco_client.query_serial_number.return_value = "serial-42"
    data = {
        "inverter_type": "3600xi",
        "dc_voltage": AnnotatedValue(
            value=232.1, description="DC Voltage", quantity="V"
        ),
        "dc_current": AnnotatedValue(
            value=1.23, description="AC Current", quantity="A"
        ),
        "dc_power": AnnotatedValue(value=400, description="DC Power", quantity="W"),
        "daily_yield": AnnotatedValue(
            value=3431, description="Daily Yield", quantity="Wh"
        ),
        "device_temperature": AnnotatedValue(
            value=32, description="Temperature", quantity="°C"
        ),
        "status": Status.NORMAL_MPP_SEARCHING,
        "ignored": 42,
    }

    def mock_query_readings(*args, annotate: bool, **kwargs):
        if annotate:
            return data
        return {
            k: v.value if isinstance(v, AnnotatedValue) else v for k, v in data.items()
        }

    mock_kaco_client.query_readings.side_effect = mock_query_readings
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)
