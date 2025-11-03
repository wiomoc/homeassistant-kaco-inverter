"""Tests the config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.kaco_inverter.client import ProtocolException
from custom_components.kaco_inverter.const import DOMAIN


@pytest.fixture(name="mock_setup_entry")
def mock_setup_entry_fixture() -> Generator[AsyncMock]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.kaco_inverter.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture(name="mock_kaco_client")
def mock_kaco_client_fixture() -> Generator[MagicMock]:
    """Mock inverter client."""
    client_obj_mock = MagicMock()
    with patch(
        "custom_components.kaco_inverter.config_flow.KacoInverterClient",
        MagicMock(return_value=client_obj_mock),
    ):
        client_obj_mock.__enter__ = lambda *args, **kwargs: client_obj_mock
        client_obj_mock.__exit__ = lambda *args, **kwargs: None
        yield client_obj_mock


async def test_user_flow_no_input(
    hass: HomeAssistant, pyserial_comports: MagicMock
) -> None:
    """Test the flow done in the correct way."""
    # test if a form is returned if no input is provided
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    # show the login form
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["data_schema"]
    assert result["data_schema"].schema["port"]
    assert result["data_schema"].schema["address"]
    pyserial_comports.assert_called()


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, mock_kaco_client: MagicMock, pyserial_comports: MagicMock
) -> None:
    """Test the flow but connecting fails."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    pyserial_comports.assert_called()

    mock_kaco_client.query_readings.side_effect = ProtocolException()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"port": "/dev/ttyUSB1234", "address": 42}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}

    mock_kaco_client.query_readings.assert_called()


async def test_user_flow_success_without_serial(
    hass: HomeAssistant,
    mock_kaco_client: MagicMock,
    pyserial_comports: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test the flow succedding, but without the inverter providing a serialnumber."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    pyserial_comports.assert_called()

    mock_kaco_client.query_readings.return_value = {"inverter_type": "3600xi"}
    mock_kaco_client.query_serial_number.side_effect = ProtocolException()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"port": "/dev/ttyUSB1234", "address": 42}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    expected_title = "KACO Powador 3600xi #42"
    assert result["title"] == expected_title
    assert not result.get("errors")
    await hass.async_block_till_done()

    mock_kaco_client.query_serial_number.assert_called()
    mock_kaco_client.query_readings.assert_called()
    mock_setup_entry.assert_called_once()
    config_entry: ConfigEntry = mock_setup_entry.call_args.args[1]
    assert config_entry.title == expected_title
    assert config_entry.data == {"port": "/dev/ttyUSB1234", "address": 42}


async def test_user_flow_success_with_serial(
    hass: HomeAssistant,
    mock_kaco_client: MagicMock,
    pyserial_comports: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test the flow succedding, but with the inverter providing a serialnumber."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    pyserial_comports.assert_called()

    mock_kaco_client.query_readings.return_value = {"inverter_type": "3600xi"}
    serial_number = "1337"
    mock_kaco_client.query_serial_number.return_value = serial_number

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"port": "/dev/ttyUSB1234", "address": 42}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    expected_title = "KACO Powador 3600xi #42"
    assert result["title"] == expected_title
    assert not result.get("errors")
    await hass.async_block_till_done()

    mock_kaco_client.query_serial_number.assert_called()
    mock_kaco_client.query_readings.assert_called()
    mock_setup_entry.assert_called_once()
    config_entry: ConfigEntry = mock_setup_entry.call_args.args[1]
    assert config_entry.title == expected_title
    assert config_entry.data == {
        "port": "/dev/ttyUSB1234",
        "address": 42,
        "serial_number": serial_number,
    }
    assert config_entry.unique_id == serial_number
