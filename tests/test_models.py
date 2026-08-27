"""Tests for STRATIS response parsing."""

from __future__ import annotations

from typing import Any

from custom_components.stratis_ac.models import StratisProperty, StratisThermostat


def test_property_parsing() -> None:
    parsed = StratisProperty.from_api(
        {"name": "properties/property-test", "display_name": "Test Property"}
    )

    assert parsed is not None
    assert parsed.property_id == "property-test"
    assert parsed.display_name == "Test Property"


def test_thermostat_parsing(thermostat_api_data: dict[str, Any]) -> None:
    thermostat = StratisThermostat.from_api(thermostat_api_data)

    assert thermostat is not None
    assert thermostat.device_id == "device-test"
    assert thermostat.property_id == "property-test"
    assert thermostat.temperature_scale == "F"
    assert thermostat.temperature("ambient_temperature") == 76
    assert thermostat.temperature("setpoint_high") == 73
    assert thermostat.humidity == 67
    assert thermostat.is_online
    assert thermostat.modes == ("auto", "cool", "heat", "off")
    assert thermostat.fan_modes == ("auto", "on")


def test_non_thermostat_is_ignored() -> None:
    assert (
        StratisThermostat.from_api(
            {
                "name": "properties/property-test/devices/water-test",
                "property_id": "property-test",
                "device_type": {"device_class": {"display_name": "Water Sensor"}},
                "state": {"water_sensor": {"online": {"value": "ONLINE"}}},
            }
        )
        is None
    )


def test_zero_temperature_is_preserved(
    thermostat_api_data: dict[str, Any],
) -> None:
    thermostat_api_data["state"]["thermostat"]["ambient_temperature"] = {
        "value": 0,
        "value_int": 4,
        "scale": "C",
    }
    thermostat = StratisThermostat.from_api(thermostat_api_data)

    assert thermostat is not None
    assert thermostat.temperature("ambient_temperature") == 0
