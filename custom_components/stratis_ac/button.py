"""Manual state refresh buttons for STRATIS thermostats."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StratisConfigEntry
from .const import DOMAIN
from .coordinator import StratisDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StratisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add refresh buttons, including for thermostats discovered on later polls."""
    coordinator = entry.runtime_data.coordinator
    known_device_ids: set[str] = set()

    @callback
    def async_add_new_entities() -> None:
        if coordinator.data is None:
            return
        new_device_ids = set(coordinator.data.thermostats) - known_device_ids
        known_device_ids.update(new_device_ids)
        if new_device_ids:
            async_add_entities(
                StratisRefreshButton(coordinator, device_id)
                for device_id in sorted(new_device_ids)
            )

    async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_entities))


class StratisRefreshButton(
    CoordinatorEntity[StratisDataUpdateCoordinator], ButtonEntity
):
    """Refresh the shared account snapshot from a thermostat's device page."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_state"
    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: StratisDataUpdateCoordinator, device_id: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{device_id}_refresh_state"
        thermostat = coordinator.data.thermostats[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=thermostat.display_name,
            manufacturer=thermostat.manufacturer,
            model=thermostat.model,
        )

    @property
    def available(self) -> bool:
        """Allow manual retries even after a failed poll or an offline report."""
        return True

    async def async_press(self) -> None:
        """Request a cloud poll using the coordinator's shared debounce."""
        await self.coordinator.async_request_refresh()
