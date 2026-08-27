"""The STRATIS AC integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import StratisApiClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    PLATFORMS,
)
from .coordinator import StratisDataUpdateCoordinator
from .models import StratisTokens


@dataclass(slots=True)
class StratisRuntimeData:
    """Objects shared by STRATIS platforms."""

    client: StratisApiClient
    coordinator: StratisDataUpdateCoordinator


type StratisConfigEntry = ConfigEntry[StratisRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: StratisConfigEntry) -> bool:
    """Set up STRATIS AC from a config entry."""

    async def async_save_tokens(tokens: StratisTokens) -> None:
        data: dict[str, Any] = {
            **entry.data,
            CONF_ACCESS_TOKEN: tokens.access_token,
            CONF_REFRESH_TOKEN: tokens.refresh_token,
            CONF_ACCESS_TOKEN_EXPIRES_AT: tokens.expires_at,
        }
        hass.config_entries.async_update_entry(entry, data=data)

    client = StratisApiClient(
        async_get_clientsession(hass),
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        access_token_expires_at=entry.data.get(CONF_ACCESS_TOKEN_EXPIRES_AT, 0),
        token_update_callback=async_save_tokens,
    )
    coordinator = StratisDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = StratisRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StratisConfigEntry) -> bool:
    """Unload a STRATIS AC config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
