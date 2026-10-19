"""Tests for state refreshes when Home Assistant clients connect."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.components.websocket_api.const import SIGNAL_WEBSOCKET_CONNECTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import DATA_DISPATCHER, async_dispatcher_send
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.stratis_ac import StratisConfigEntry
from custom_components.stratis_ac.api import StratisConnectionError
from custom_components.stratis_ac.const import DOMAIN


async def test_client_connection_refreshes_climate(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
    thermostat_api_data: dict[str, Any],
    hass_ws_client: WebSocketGenerator,
) -> None:
    """An authenticated WebSocket connection fetches the latest cloud state."""
    _, client = setup_integration
    climate_id = er.async_get(hass).async_get_entity_id(
        "climate", DOMAIN, "device-test"
    )
    assert hass.states.get(climate_id).state == "cool"
    updated = deepcopy(thermostat_api_data)
    updated["state"]["thermostat"]["thermostat_mode"]["value"] = "HEAT"
    updated["state"]["thermostat"]["setpoint_low"]["value"] = 71
    client.async_get_devices.return_value = [updated]
    client.reset_mock()

    websocket = await hass_ws_client(hass)
    await hass.async_block_till_done()

    client.async_get_devices.assert_awaited_once_with("property-test")
    client.async_set_thermostat.assert_not_awaited()
    state = hass.states.get(climate_id)
    assert state.state == "heat"
    assert state.attributes["temperature"] == 71

    await websocket.close()
    await hass.async_block_till_done()
    client.async_get_devices.assert_awaited_once()


async def test_connections_share_manual_refresh_debounce(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
) -> None:
    """A burst of connections and button presses shares a single cooldown."""
    _, client = setup_integration
    button_id = er.async_get(hass).async_get_entity_id(
        "button", DOMAIN, "device-test_refresh_state"
    )
    client.reset_mock()

    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.async_block_till_done()
    client.async_get_devices.assert_awaited_once()

    for _ in range(5):
        async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await hass.async_block_till_done()
    client.async_get_devices.assert_awaited_once()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert client.async_get_devices.await_count == 2


async def test_connection_retries_failed_poll(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
) -> None:
    """A new client can recover state after a cloud connection failure."""
    entry, client = setup_integration
    coordinator = entry.runtime_data.coordinator
    client.async_get_devices.side_effect = StratisConnectionError("Cannot connect")
    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success

    client.async_get_devices.side_effect = None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    client.reset_mock()
    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.async_block_till_done()

    client.async_get_devices.assert_awaited_once_with("property-test")
    assert coordinator.last_update_success


async def test_unload_removes_connection_listener(
    hass: HomeAssistant,
    setup_integration: tuple[StratisConfigEntry, AsyncMock],
) -> None:
    """Unload cancels pending refreshes; reload installs only one listener."""
    entry, client = setup_integration
    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.async_block_till_done()
    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.data[DATA_DISPATCHER].get(SIGNAL_WEBSOCKET_CONNECTED)
    client.reset_mock()
    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    client.async_get_properties.assert_not_awaited()
    client.async_get_devices.assert_not_awaited()

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client.reset_mock()
    assert len(hass.data[DATA_DISPATCHER][SIGNAL_WEBSOCKET_CONNECTED]) == 1
    async_dispatcher_send(hass, SIGNAL_WEBSOCKET_CONNECTED)
    await hass.async_block_till_done()
    client.async_get_devices.assert_awaited_once_with("property-test")
