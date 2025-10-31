"""Fixtures for testing."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from serial.tools.list_ports_common import ListPortInfo


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


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
