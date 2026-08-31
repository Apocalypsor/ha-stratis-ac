"""Climate platform for STRATIS thermostats."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StratisRuntimeData
from .api import StratisError
from .const import (
    DOMAIN,
    STRATIS_FAN_AUTO,
    STRATIS_FAN_ON,
    STRATIS_MODE_AUTO,
    STRATIS_MODE_COOL,
    STRATIS_MODE_HEAT,
    STRATIS_MODE_OFF,
)
from .coordinator import StratisDataUpdateCoordinator
from .models import StratisThermostat

STRATIS_TO_HA_MODE: dict[str, HVACMode] = {
    STRATIS_MODE_AUTO: HVACMode.HEAT_COOL,
    STRATIS_MODE_COOL: HVACMode.COOL,
    STRATIS_MODE_HEAT: HVACMode.HEAT,
    STRATIS_MODE_OFF: HVACMode.OFF,
}
HA_TO_STRATIS_MODE = {value: key for key, value in STRATIS_TO_HA_MODE.items()}

STRATIS_TO_HA_ACTION: dict[str, HVACAction] = {
    "HVAC_COOLING": HVACAction.COOLING,
    "HVAC_HEATING": HVACAction.HEATING,
    "HVAC_OFF": HVACAction.OFF,
    "HVAC_IDLE": HVACAction.IDLE,
    "COOLING": HVACAction.COOLING,
    "HEATING": HVACAction.HEATING,
    "IDLE": HVACAction.IDLE,
    "OFF": HVACAction.OFF,
}

STRATIS_TO_HA_FAN = {
    STRATIS_FAN_AUTO: "auto",
    STRATIS_FAN_ON: "on",
}
HA_TO_STRATIS_FAN = {value: key for key, value in STRATIS_TO_HA_FAN.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[StratisRuntimeData],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up thermostat entities and add newly discovered ones."""
    coordinator = entry.runtime_data.coordinator
    known_device_ids: set[str] = set()

    @callback
    def async_add_new_entities() -> None:
        if coordinator.data is None:
            return
        new_device_ids = set(coordinator.data.thermostats) - known_device_ids
        if not new_device_ids:
            return
        known_device_ids.update(new_device_ids)
        async_add_entities(
            StratisClimateEntity(coordinator, device_id)
            for device_id in sorted(new_device_ids)
        )

    async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_entities))


class StratisClimateEntity(
    CoordinatorEntity[StratisDataUpdateCoordinator], ClimateEntity
):
    """A STRATIS-managed thermostat."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self, coordinator: StratisDataUpdateCoordinator, device_id: str
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._last_thermostat = coordinator.data.thermostats[device_id]
        self._attr_unique_id = device_id
        current_mode = self.hvac_mode
        self._last_non_off_mode = (
            current_mode
            if current_mode is not None and current_mode != HVACMode.OFF
            else self._preferred_on_mode()
        )

    @property
    def thermostat(self) -> StratisThermostat:
        """Return the latest thermostat data, retaining the last known snapshot."""
        if self.coordinator.data is not None:
            latest = self.coordinator.data.thermostats.get(self._device_id)
            if latest is not None:
                self._last_thermostat = latest
        return self._last_thermostat

    @property
    def available(self) -> bool:
        """Return whether both the coordinator and thermostat are available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._device_id in self.coordinator.data.thermostats
            and self.thermostat.is_online
        )

    @property
    def device_info(self) -> DeviceInfo:
        thermostat = self.thermostat
        return DeviceInfo(
            identifiers={(DOMAIN, thermostat.device_id)},
            name=thermostat.display_name,
            manufacturer=thermostat.manufacturer,
            model=thermostat.model,
        )

    @property
    def temperature_unit(self) -> str:
        return (
            UnitOfTemperature.CELSIUS
            if self.thermostat.temperature_scale == "C"
            else UnitOfTemperature.FAHRENHEIT
        )

    @property
    def target_temperature_step(self) -> float:
        return (
            0.5
            if self.hass.config.units.temperature_unit == UnitOfTemperature.CELSIUS
            else 1.0
        )

    @property
    def min_temp(self) -> float:
        return 10.0 if self.temperature_unit == UnitOfTemperature.CELSIUS else 50.0

    @property
    def max_temp(self) -> float:
        return 32.0 if self.temperature_unit == UnitOfTemperature.CELSIUS else 90.0

    @property
    def current_temperature(self) -> float | None:
        return self.thermostat.temperature("ambient_temperature")

    @property
    def current_humidity(self) -> int | None:
        return self.thermostat.humidity

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = self.thermostat.modes or ("auto", "cool", "heat", "off")
        supported = {
            STRATIS_TO_HA_MODE[mode.upper()]
            for mode in modes
            if mode.upper() in STRATIS_TO_HA_MODE
        }
        supported.add(HVACMode.OFF)
        order = (
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.HEAT_COOL,
            HVACMode.OFF,
        )
        return [mode for mode in order if mode in supported]

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = self.thermostat.state_value("thermostat_mode")
        return STRATIS_TO_HA_MODE.get(mode) if mode is not None else None

    @property
    def hvac_action(self) -> HVACAction | None:
        action = self.thermostat.state_value("operating_state")
        return STRATIS_TO_HA_ACTION.get(action) if action is not None else None

    @property
    def target_temperature(self) -> float | None:
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            return self.thermostat.temperature("setpoint_low")
        if mode == HVACMode.COOL:
            return self.thermostat.temperature("setpoint_high")
        return None

    @property
    def target_temperature_low(self) -> float | None:
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None
        return self.thermostat.temperature("auto_setpoint_low")

    @property
    def target_temperature_high(self) -> float | None:
        if self.hvac_mode != HVACMode.HEAT_COOL:
            return None
        return self.thermostat.temperature("auto_setpoint_high")

    @property
    def fan_modes(self) -> list[str] | None:
        if not self.thermostat.fan_modes:
            return None
        return [mode for mode in ("auto", "on") if mode in self.thermostat.fan_modes]

    @property
    def fan_mode(self) -> str | None:
        mode = self.thermostat.state_value("thermostat_fan_mode")
        return STRATIS_TO_HA_FAN.get(mode) if mode is not None else None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self.hvac_mode != HVACMode.OFF:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
            if HVACMode.HEAT_COOL in self.hvac_modes:
                features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        return features

    def _preferred_on_mode(self) -> HVACMode:
        for mode in (HVACMode.COOL, HVACMode.HEAT, HVACMode.HEAT_COOL):
            if mode in self.hvac_modes:
                return mode
        return HVACMode.COOL

    def _temperature_payload(
        self, field_name: str, requested_temperature: float
    ) -> dict[str, float | int | str]:
        return {
            "value_int": self.thermostat.confirmed_integral_temperature(
                field_name, requested_temperature
            ),
            "scale": self.thermostat.temperature_scale,
            "value": requested_temperature,
        }

    async def _async_write(self, state: Mapping[str, Any]) -> None:
        try:
            result = await self.coordinator.client.async_set_thermostat(
                self.thermostat.property_id,
                self.thermostat.device_id,
                state,
            )
            partial_state = result.get("response")
            if isinstance(partial_state, dict):
                self.coordinator.async_apply_thermostat_update(
                    self.thermostat.device_id, partial_state
                )
            else:
                await self.coordinator.async_request_refresh()
        except StratisError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
            ) from err

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"mode": hvac_mode},
            )
        stratis_mode = HA_TO_STRATIS_MODE[hvac_mode]
        await self._async_write({"thermostat_mode": {"value": stratis_mode}})
        if hvac_mode != HVACMode.OFF:
            self._last_non_off_mode = hvac_mode

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if self.fan_modes is None or fan_mode not in self.fan_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_fan_mode",
                translation_placeholders={"mode": fan_mode},
            )
        await self._async_write(
            {"thermostat_fan_mode": {"value": HA_TO_STRATIS_FAN[fan_mode]}}
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        requested_mode = kwargs.get(ATTR_HVAC_MODE)
        if requested_mode is not None:
            requested_mode = HVACMode(requested_mode)
        mode = requested_mode or self.hvac_mode or self._preferred_on_mode()
        if mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"mode": mode},
            )
        if mode == HVACMode.OFF:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="temperature_while_off",
            )

        payload: dict[str, Any] = {}
        if requested_mode is not None:
            payload["thermostat_mode"] = {"value": HA_TO_STRATIS_MODE[requested_mode]}

        if mode == HVACMode.HEAT_COOL:
            low = kwargs.get(ATTR_TARGET_TEMP_LOW)
            high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
            if low is not None and high is not None and low > high:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_temperature_range",
                )
            if low is not None:
                payload["auto_setpoint_low"] = self._temperature_payload(
                    "auto_setpoint_low", float(low)
                )
            if high is not None:
                payload["auto_setpoint_high"] = self._temperature_payload(
                    "auto_setpoint_high", float(high)
                )
        else:
            temperature = kwargs.get(ATTR_TEMPERATURE)
            if temperature is not None:
                field_name = (
                    "setpoint_low" if mode == HVACMode.HEAT else "setpoint_high"
                )
                payload[field_name] = self._temperature_payload(
                    field_name, float(temperature)
                )

        if not payload:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_temperature",
            )
        await self._async_write(payload)
        if mode != HVACMode.OFF:
            self._last_non_off_mode = mode

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(self._last_non_off_mode)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
