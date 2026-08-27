"""Shared fixtures for STRATIS AC tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in Home Assistant tests."""


@pytest.fixture
def thermostat_api_data() -> dict[str, Any]:
    """Return a sanitized thermostat response based on the captured schema."""
    return {
        "name": "properties/property-test/devices/device-test",
        "property_id": "property-test",
        "unit_id": "unit-test",
        "display_name": "Living Room Thermostat",
        "device_type": {
            "display_name": "Thermostat (Nest)",
            "device_class": {"display_name": "Thermostat"},
        },
        "device_model": {},
        "attributes": {
            "thermostat_fan_modes_available": ["auto", "on"],
            "thermostat_modes_available": ["auto", "cool", "heat", "off"],
        },
        "state": {
            "thermostat": {
                "ambient_temperature": {"value": 76, "scale": "F"},
                "thermostat_mode": {"value": "COOL"},
                "operating_state": {"value": "HVAC_COOLING"},
                "setpoint_high": {"value_int": 73, "value": 73, "scale": "F"},
                "setpoint_low": {"value_int": 68, "value": 68, "scale": "F"},
                "auto_setpoint_high": {
                    "value_int": 75,
                    "value": 75,
                    "scale": "F",
                },
                "auto_setpoint_low": {
                    "value_int": 70,
                    "value": 70,
                    "scale": "F",
                },
                "thermostat_fan_mode": {"value": "FAN_AUTO"},
                "online": {"value": "ONLINE"},
                "humidity": {"value": 67, "scale": "PERCENTAGE"},
            }
        },
    }
