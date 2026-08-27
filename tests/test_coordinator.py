"""Tests for STRATIS account coordination."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stratis_ac.api import StratisAuthenticationError
from custom_components.stratis_ac.const import DOMAIN
from custom_components.stratis_ac.coordinator import StratisDataUpdateCoordinator


@pytest.mark.asyncio
async def test_coordinator_discovers_only_thermostats(
    hass, thermostat_api_data: dict[str, Any]
) -> None:
    client = AsyncMock()
    client.async_get_properties.return_value = [
        {"name": "properties/property-test", "display_name": "Test Property"}
    ]
    client.async_get_devices.return_value = [
        thermostat_api_data,
        {
            "name": "properties/property-test/devices/water-test",
            "property_id": "property-test",
            "device_type": {"device_class": {"display_name": "Water Sensor"}},
            "state": {"water_sensor": {"online": {"value": "ONLINE"}}},
        },
    ]
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = StratisDataUpdateCoordinator(hass, entry, client)

    data = await coordinator._async_update_data()

    assert list(data.properties) == ["property-test"]
    assert list(data.thermostats) == ["device-test"]
    client.async_get_devices.assert_awaited_once_with("property-test")

    coordinator.async_set_updated_data(data)
    coordinator.async_apply_thermostat_update(
        "device-test", {"@type": "ignored", "thermostat_mode": {"value": "HEAT"}}
    )
    assert data.thermostats["device-test"].state_value("thermostat_mode") == "HEAT"
    assert "@type" not in data.thermostats["device-test"].state


@pytest.mark.asyncio
async def test_coordinator_auth_failure_requests_reauthentication(hass) -> None:
    client = AsyncMock()
    client.async_get_properties.side_effect = StratisAuthenticationError
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = StratisDataUpdateCoordinator(hass, entry, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
