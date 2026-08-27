"""Diagnostics for STRATIS AC."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from . import StratisConfigEntry
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
)

TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: StratisConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a STRATIS config entry."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    thermostats = []
    if data is not None:
        thermostats = [
            {
                "manufacturer": thermostat.manufacturer,
                "model": thermostat.model,
                "modes": thermostat.modes,
                "fan_modes": thermostat.fan_modes,
                "temperature_scale": thermostat.temperature_scale,
                "state_fields": sorted(thermostat.state),
                "online": thermostat.is_online,
            }
            for thermostat in data.thermostats.values()
        ]

    return {
        "entry": {
            "version": entry.version,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "token_expiry_stored": CONF_ACCESS_TOKEN_EXPIRES_AT in entry.data,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "property_count": len(data.properties) if data is not None else 0,
            "thermostats": thermostats,
        },
    }
