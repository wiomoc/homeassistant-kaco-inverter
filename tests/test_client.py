from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.kaco_inverter.client import ProtocolException
from custom_components.kaco_inverter.client.client import KacoInverterClient
from custom_components.kaco_inverter.client.fields import FIELDS_00_02, AnnotatedValue
from custom_components.kaco_inverter.client.model_names import resolve_model_name


@pytest.fixture
def pyserial_serial_port() -> Generator[MagicMock]:
    port_obj_mock = MagicMock()

    with patch(
        "custom_components.kaco_inverter.client.client.Serial",
        MagicMock(return_value=port_obj_mock),
        create=True,
    ):
        yield port_obj_mock


@pytest.mark.parametrize(
    "response,expected_result,annotate",
    [
        (
            b"\n*030   4 486.8  1.29   627 236.0  2.43   558  24   3401 \x92 3600xi\r",
            {
                "status": 4,
                "dc_voltage": AnnotatedValue(
                    value=486.8, quantity="V", description="Generator Voltage"
                ),
                "dc_current": AnnotatedValue(
                    value=1.29, quantity="A", description="Generator Current"
                ),
                "dc_power": AnnotatedValue(
                    value=627, quantity="W", description="Generator Power"
                ),
                "ac_voltage": AnnotatedValue(
                    value=236.0, quantity="V", description="Grid Voltage"
                ),
                "ac_current": AnnotatedValue(
                    value=2.43, quantity="A", description="Grid- / Grid-feeding Current"
                ),
                "ac_power": AnnotatedValue(
                    value=558, quantity="W", description="Delivered (fed-in) Power"
                ),
                "device_temperature": AnnotatedValue(
                    value=24, quantity="°C", description="Device Temperature"
                ),
                "daily_yield": AnnotatedValue(
                    value=3401, quantity="Wh", description="Daily Yield"
                ),
                "inverter_type": "3600xi",
            },
            True,
        ),
        (
            b"\n*03n 20 3X24 4  214.7  1.97   421    0.0  0.04     0  231.1  0.80  234.1  0.79  234.4  0.81   421   413 0.735i  36.7   1640 FEB7\r",
            {
                "number_of_elements": 20,
                "inverter_type": "3X24",
                "status": 4,
                "dc_mppt1_voltage": AnnotatedValue(
                    value=214.7, quantity="V", description="DC Voltage of MPPT1"
                ),
                "dc_mppt1_current": AnnotatedValue(
                    value=1.97, quantity="A", description="DC Current of MPPT1"
                ),
                "dc_mppt1_power": AnnotatedValue(
                    value=421, quantity="W", description="DC Power of MPPT1"
                ),
                "dc_mppt2_voltage": AnnotatedValue(
                    value=0.0, quantity="V", description="DC Voltage of MPPT2"
                ),
                "dc_mppt2_current": AnnotatedValue(
                    value=0.04, quantity="A", description="DC Current of MPPT2"
                ),
                "dc_mppt2_power": AnnotatedValue(
                    value=0, quantity="W", description="DC Power of MPPT2"
                ),
                "ac_phase1_voltage": AnnotatedValue(
                    value=231.1, quantity="V", description="AC Voltage of Phase 1"
                ),
                "ac_phase1_current": AnnotatedValue(
                    value=0.8, quantity="A", description="AC Current of Phase 1"
                ),
                "ac_phase2_voltage": AnnotatedValue(
                    value=234.1, quantity="V", description="AC Voltage of Phase 2"
                ),
                "ac_phase2_current": AnnotatedValue(
                    value=0.79, quantity="A", description="AC Current of Phase 2"
                ),
                "ac_phase3_voltage": AnnotatedValue(
                    value=234.4, quantity="V", description="AC Voltage of Phase 3"
                ),
                "ac_phase3_current": AnnotatedValue(
                    value=0.81, quantity="A", description="AC Current of Phase 3"
                ),
                "dc_power": AnnotatedValue(
                    value=421, quantity="W", description="DC Power"
                ),
                "ac_power": AnnotatedValue(
                    value=413, quantity="W", description="AC Power"
                ),
                "cos_phi": 0.735,
                "device_temperature": AnnotatedValue(
                    value=36.7, quantity="°C", description="Circuit Board Temperature"
                ),
                "daily_yield": AnnotatedValue(
                    value=1640, quantity="Wh", description="Daily Yield"
                ),
            },
            True,
        ),
        (
            b"\n*030   4 486.8 111.29 123627 236.1 123.45   1558 42   13401 \xb3 100kTR 123456789\r",
            {
                "status": 4,
                "dc_voltage": 486.8,
                "dc_current": 111.29,
                "dc_power": 123627,
                "ac_voltage": 236.1,
                "ac_current": 123.45,
                "ac_power": 1558,
                "device_temperature": 42,
                "daily_yield": 13401,
                "inverter_type": "100kTR",
                "total_yield": 123456789,
            },
            False,
        ),
    ],
)
def test_query_readings(
    response: bytes, expected_result: dict[str, Any], annotate: bool
):
    port_mock = MagicMock()
    port_mock.is_open = True
    port_mock.read_until.return_value = response
    inverter_address = 3
    with KacoInverterClient(port_mock, inverter_address) as client:
        result = client.query_readings(annotate=annotate)
        assert result == expected_result
    port_mock.read_until.assert_called_with(b"\r")
    port_mock.open.assert_not_called()
    port_mock.close.assert_called()


@pytest.mark.parametrize("has_cached_is_000xi", [True, False])
def test_000xi_query_readings(
    has_cached_is_000xi: bool, pyserial_serial_port: MagicMock
):
    responses = [
        b"\n*021   4 186.8 11.29 123621 136.1 13.45   1558 12  13401 \x23  8k1\r",
        b"\n*022   5 286.8 21.29 223621 236.1 23.45   2558 22  23401 \x2d  8k2\r",
        b"\n*023   6 386.8 31.29 323621 336.1 33.45   3558 32  33401 \x37  8k3\r",
    ]
    if not has_cached_is_000xi:
        responses.insert(0, b"\n*024\r")

    expected_result = {
        "1_status": 4,
        "1_dc_voltage": 186.8,
        "1_dc_current": 11.29,
        "1_dc_power": 123621,
        "1_ac_voltage": 136.1,
        "1_ac_current": 13.45,
        "1_ac_power": 1558,
        "1_device_temperature": 12,
        "1_daily_yield": 13401,
        "1_inverter_type": "8k1",
        "2_status": 5,
        "2_dc_voltage": 286.8,
        "2_dc_current": 21.29,
        "2_dc_power": 223621,
        "2_ac_voltage": 236.1,
        "2_ac_current": 23.45,
        "2_ac_power": 2558,
        "2_device_temperature": 22,
        "2_daily_yield": 23401,
        "2_inverter_type": "8k2",
        "3_status": 6,
        "3_dc_voltage": 386.8,
        "3_dc_current": 31.29,
        "3_dc_power": 323621,
        "3_ac_voltage": 336.1,
        "3_ac_current": 33.45,
        "3_ac_power": 3558,
        "3_device_temperature": 32,
        "3_daily_yield": 33401,
        "3_inverter_type": "8k3",
        "inverter_type": "3x8k",
    }

    inverter_address = 2

    pyserial_serial_port.is_open = False
    pyserial_serial_port.read_until.side_effect = responses

    with KacoInverterClient("COM1", inverter_address) as client:
        client._is_000xi = has_cached_is_000xi
        result = client.query_readings(annotate=False)
        assert result == expected_result
        assert client._is_000xi
        pyserial_serial_port.is_open = True
    pyserial_serial_port.open.assert_called()
    pyserial_serial_port.close.assert_called()


def test_query_split_by_cr_checksum():
    port_mock = MagicMock()
    port_mock.read_until.side_effect = [
        b"\n*420   4 699.9 999.99 999999 999.1 123.45   1558 42   13401 \r",
        b" 100kTR 123456789\r",
    ]
    expected_result = {
        "status": 4,
        "dc_voltage": 699.9,
        "dc_current": 999.99,
        "dc_power": 999999,
        "ac_voltage": 999.1,
        "ac_current": 123.45,
        "ac_power": 1558,
        "device_temperature": 42,
        "daily_yield": 13401,
        "inverter_type": "100kTR",
        "total_yield": 123456789,
    }
    inverter_address = 42
    with KacoInverterClient(port_mock, inverter_address) as client:
        result = client.query_readings(annotate=False)
        assert result == expected_result
    port_mock.read_until.assert_called_with(b"\r")
    port_mock.close.assert_called()


@pytest.mark.parametrize(
    "response,expected_protocol_exception",
    [
        (b"\n*030  ...\r", "Expected response from '1', got response from '3'"),
        (b"\n*016  ...\r", "Expected '0', '4' or 'n' command response, got '6'"),
        (b"\n*\xff10  ...\r", "Expected ASCII characters, got b'\\n*\\xff10'"),
        (b"\n*010  ", "Unexpected end-of-frame"),
        (b"\n*010abcdef", "Expected ' ', got b'a'"),
        (b"\n*010  xx", "Expected integer, got b' xx'"),
        (b"\n*010   4  xx.x", "Expected float, got b' xx.x'"),
        (b"\n*010   4  1.23", "Expected 1 decimal places in field dc_voltage"),
        (
            b"\n*010   4 486.8  1.29   627 236.0  2.43   558  24   3401 \x90 3\xff00xi\r",
            "Expected ASCII characters, got b'3\\xff00xi'",
        ),
        (
            b"\n*010   4 486.8  1.29   627 236.0  2.43   558  24   3401 \x42 3600xi\r",
            "Expected checksum 66, got 144",
        ),
        (
            b"\n*010   4 486.8  1.29   627 236.0  2.43   558  24   3401 \x90 3600xi\ra",
            "Expected end-of-frame",
        ),
        (
            b"\n*01n 20 3X24 4  214.7  1.97   421    0.0  0.04",
            "Expected ' ', got end-of-frame",
        ),
        (
            b"\n*01n 20 3X24 4  214.7  1.97   421    0.0  0.04     0  231.1  0.80  234.1  0.79  234.4  0.81   421   413 0.735y ",
            "Expected c, i or o, got b'y'",
        ),
        (b"\n*01n 21 3X24 4 ", "Expected 20 elements for type '3X24', got 21"),
        (
            b"\n*01n 20 3X24 4  214.7  1.97   421    0.0  0.04     0  231.1  0.80  234.1  0.79  234.4  0.81   421   413 0.735i  36.7   1640 FEB7\r",
            "Expected CRC FEB7, got 7054",
        ),
        (
            b"\n*01n 20 3X24 4  214.7  1.97   421    0.0  0.04     0  231.1  0.80  234.1  0.79  234.4  0.81   421   413 0.735i  36.7   1640 ZZZZ\r",
            "Expected hex, got b'ZZZZ'",
        ),
        (
            b"\n*01n 20 3X24 4  214.7  1.97   421    0.0  0.04     0  231.1  0.80  234.1  0.79  234.4  0.81   421   413 0.735i  36.7   1640 7054\ra",
            "Expected end-of-frame",
        ),
    ],
)
def test_query_readings_exceptions(
    response: bytes, expected_protocol_exception: dict[str, Any]
):
    port_mock = MagicMock()
    port_mock.read_until.return_value = response

    inverter_address = 1
    with pytest.raises(ProtocolException) as excinfo:
        with KacoInverterClient(port_mock, inverter_address) as client:
            client._infered_standard_fields = FIELDS_00_02
            client.query_readings(annotate=False)
    assert excinfo.value.args[0] == expected_protocol_exception
    port_mock.read_until.assert_called_with(b"\r")
    port_mock.close.assert_called()


@pytest.mark.parametrize(
    "inverter_type,model",
    [
        ("3X24", "blueplanet 3.0NX3 M2"),
        ("03X24", "blueplanet 3.0NX3 M2"),
        ("0000", None),
        ("", None),
    ],
)
def test_resolve_model_name(inverter_type, model):
    assert resolve_model_name(inverter_type) == model
