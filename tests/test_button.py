"""Tests for manual refresh through Home Assistant's button service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stratis_ac import StratisConfigEntry
from custom_components.stratis_ac.api import StratisConnectionError
from custom_components.stratis_ac.const import CONF_REFRESH_TOKEN, DOMAIN


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


async def test_button_refresh_updates_climate(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
    thermostat_api_data: dict[str, Any],
) -> None:
    """An actual button press fetches external mode and setpoint changes."""
    _, client = setup_integration
    registry = er.async_get(hass)
    button_id = registry.async_get_entity_id(
        "button", DOMAIN, "device-test_refresh_state"
    )
    climate_id = registry.async_get_entity_id("climate", DOMAIN, "device-test")
    assert button_id is not None and climate_id is not None
    assert (
        registry.async_get(button_id).device_id
        == registry.async_get(climate_id).device_id
    )
    assert hass.states.get(climate_id).state == "cool"

    updated = deepcopy(thermostat_api_data)
    updated["state"]["thermostat"]["thermostat_mode"]["value"] = "HEAT"
    updated["state"]["thermostat"]["setpoint_low"]["value"] = 71
    client.async_get_devices.return_value = [updated]
    client.reset_mock()

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()

    client.async_get_devices.assert_awaited_once_with("property-test")
    client.async_set_thermostat.assert_not_awaited()
    state = hass.states.get(climate_id)
    assert state.state == "heat"
    assert state.attributes["temperature"] == 71


async def test_button_can_retry_failed_poll(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
) -> None:
    """A cloud failure must not disable the manual retry button."""
    entry, client = setup_integration
    coordinator = entry.runtime_data.coordinator
    client.async_get_devices.side_effect = StratisConnectionError("Cannot connect")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    button_id = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, "device-test_refresh_state"
    )
    assert hass.states.get(button_id).state != "unavailable"

    client.async_get_devices.side_effect = None
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert coordinator.last_update_success


async def test_new_thermostat_gets_one_button(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
    thermostat_api_data: dict[str, Any],
) -> None:
    """Later discovery adds a button on the same device without duplicates."""
    entry, client = setup_integration
    new_device = deepcopy(thermostat_api_data)
    new_device["name"] = "properties/property-test/devices/device-second"
    new_device["display_name"] = "Bedroom Thermostat"
    client.async_get_devices.return_value.append(new_device)
    coordinator = entry.runtime_data.coordinator
    for _ in range(2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    buttons = [
        entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.domain == "button"
    ]
    assert {button.unique_id for button in buttons} == {
        "device-test_refresh_state",
        "device-second_refresh_state",
    }
    climate_id = registry.async_get_entity_id("climate", DOMAIN, "device-second")
    button_id = registry.async_get_entity_id(
        "button", DOMAIN, "device-second_refresh_state"
    )
    assert (
        registry.async_get(button_id).device_id
        == registry.async_get(climate_id).device_id
    )
