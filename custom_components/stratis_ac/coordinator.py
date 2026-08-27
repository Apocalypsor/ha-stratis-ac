"""Data update coordinator for STRATIS thermostats."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    StratisApiClient,
    StratisAuthenticationError,
    StratisConnectionError,
    StratisError,
)
from .const import DOMAIN, UPDATE_INTERVAL
from .models import StratisData, StratisProperty, StratisThermostat

_LOGGER = logging.getLogger(__name__)


class StratisDataUpdateCoordinator(DataUpdateCoordinator[StratisData]):
    """Fetch properties and thermostat state for one STRATIS account."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: StratisApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> StratisData:
        try:
            raw_properties = await self.client.async_get_properties()
            properties = {
                item.property_id: item
                for raw in raw_properties
                if (item := StratisProperty.from_api(raw)) is not None
            }

            device_groups = await asyncio.gather(
                *(
                    self.client.async_get_devices(property_id)
                    for property_id in properties
                )
            )
            thermostats: dict[str, StratisThermostat] = {}
            for raw_devices in device_groups:
                for raw_device in raw_devices:
                    thermostat = StratisThermostat.from_api(raw_device)
                    if thermostat is not None:
                        thermostats[thermostat.device_id] = thermostat

            return StratisData(properties=properties, thermostats=thermostats)
        except StratisAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (StratisConnectionError, StratisError) as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def async_apply_thermostat_update(
        self, device_id: str, partial_state: dict[str, object]
    ) -> None:
        """Apply a command response while waiting for the next cloud poll."""
        if self.data is None:
            return
        thermostat = self.data.thermostats.get(device_id)
        if thermostat is None:
            return
        thermostat.state.update(
            {
                key: value
                for key, value in partial_state.items()
                if key != "@type" and isinstance(value, dict)
            }
        )
        self.async_set_updated_data(self.data)
