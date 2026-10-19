"""Shared fixtures for STRATIS AC tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stratis_ac import StratisConfigEntry
from custom_components.stratis_ac.const import CONF_REFRESH_TOKEN, DOMAIN


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in Home Assistant tests."""


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, thermostat_api_data: dict[str, Any]
) -> AsyncIterator[tuple[StratisConfigEntry, AsyncMock]]:
    """Load both platforms with a real coordinator and a mocked cloud client."""
    hass.config.units = US_CUSTOMARY_SYSTEM
    client = AsyncMock()
    client.async_get_properties.return_value = [
        {"name": "properties/property-test", "display_name": "Test Property"}
    ]
    client.async_get_devices.return_value = [deepcopy(thermostat_api_data)]
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_REFRESH_TOKEN: "test-refresh"})
    entry.add_to_hass(hass)
    with patch("custom_components.stratis_ac.StratisApiClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, client
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


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
