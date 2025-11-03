"""Fixtures for testing."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import (
    CONF_PORT,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from serial.tools.list_ports_common import ListPortInfo
from syrupy.assertion import SnapshotAssertion

from custom_components.kaco_inverter.const import (
    CONF_INVERTER_ADDRESS,
    CONF_SERIAL_NUMBER,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable component-under-test."""
    yield  # noqa: PT022


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return snapshot assertion fixture with the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def pyserial_comports() -> Generator[MagicMock]:
    """Mock pyserial comports."""
    port = ListPortInfo("/dev/ttyUSB1234")
    port.device = "/dev/ttyUSB1234"
    port.manufacturer = "TI"

    with patch(
        "serial.tools.list_ports.comports",
        MagicMock(return_value=[port]),
    ) as comports_mock:
        yield comports_mock


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return the default mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="ViCare",
        entry_id="1234",
        data={
            CONF_PORT: "COM42",
            CONF_INVERTER_ADDRESS: 3,
            CONF_SERIAL_NUMBER: "serial-42",
        },
    )
