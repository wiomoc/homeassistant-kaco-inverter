from unittest.mock import MagicMock

from custom_components.kaco_inverter.client.client import KacoInverterClient
from custom_components.kaco_inverter.client.fields import AnnotatedValue


def test_smoke_legacy_protocol():
    port_mock = MagicMock()
    port_mock.is_open = True
    port_mock.read_until.return_value = (
        b"\n*020   4 486.8  1.29   627 236.0  2.43   558  24   3401 \x91 3600xi\r"
    )
    client = KacoInverterClient(port_mock, 2)
    result = client.query_readings(annotate=True)
    assert result == {
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
    }

def test_smoke_generic_protocol():
    port_mock = MagicMock()
    port_mock.is_open = True
    port_mock.read_until.return_value = b"\n*03n 20 3X24 4  214.7  1.97   421    0.0  0.04     0  231.1  0.80  234.1  0.79  234.4  0.81   421   413 0.735i  36.7   1640 FEB7\r"
    client = KacoInverterClient(port_mock, 3)
    result = client.query_readings(annotate=True)
    assert result == {
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
        "dc_power": AnnotatedValue(value=421, quantity="W", description="DC Power"),
        "ac_power": AnnotatedValue(value=413, quantity="W", description="AC Power"),
        "cos_phi": 0.735,
        "device_temperature": AnnotatedValue(
            value=36.7, quantity="°C", description="Circuit Board Temperature"
        ),
        "daily_yield": AnnotatedValue(
            value=1640, quantity="Wh", description="Daily Yield"
        ),
    }
