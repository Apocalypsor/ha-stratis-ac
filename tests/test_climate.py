"""Tests for STRATIS climate mappings and command payloads."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.unit_conversion import TemperatureConverter
from homeassistant.util.unit_system import METRIC_SYSTEM, US_CUSTOMARY_SYSTEM

from custom_components.stratis_ac.climate import StratisClimateEntity
from custom_components.stratis_ac.models import StratisData, StratisThermostat


@pytest.fixture
def entity(thermostat_api_data: dict[str, Any]) -> StratisClimateEntity:
    thermostat = StratisThermostat.from_api(thermostat_api_data)
    assert thermostat is not None
    coordinator = MagicMock()
    coordinator.data = StratisData(
        properties={}, thermostats={thermostat.device_id: thermostat}
    )
    coordinator.last_update_success = True
    entity = StratisClimateEntity(coordinator, thermostat.device_id)
    entity.hass = MagicMock()
    entity.hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT
    return entity


def test_climate_state_mapping(entity: StratisClimateEntity) -> None:
    assert entity.hvac_modes == [
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
        HVACMode.OFF,
    ]
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.hvac_action == HVACAction.COOLING
    assert entity.current_temperature == 76
    assert entity.current_humidity == 67
    assert entity.target_temperature == 73
    assert entity.temperature_unit == UnitOfTemperature.FAHRENHEIT
    assert entity.fan_mode == "auto"
    assert entity.fan_modes == ["auto", "on"]


@pytest.mark.parametrize(
    ("display_unit", "expected_step"),
    [
        (UnitOfTemperature.CELSIUS, 0.5),
        (UnitOfTemperature.FAHRENHEIT, 1.0),
    ],
)
def test_target_temperature_step_uses_display_unit(
    entity: StratisClimateEntity, display_unit: str, expected_step: float
) -> None:
    entity.hass = MagicMock()
    entity.hass.config.units.temperature_unit = display_unit

    assert entity.temperature_unit == UnitOfTemperature.FAHRENHEIT
    assert entity.target_temperature_step == expected_step


def test_temperature_controls_are_disabled_while_off(
    entity: StratisClimateEntity,
) -> None:
    entity.thermostat.state["thermostat_mode"]["value"] = "OFF"

    assert entity.hvac_mode == HVACMode.OFF
    assert entity.target_temperature is None
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not entity.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE


@pytest.mark.parametrize(
    ("mode", "field", "attribute"),
    [
        ("COOL", "setpoint_high", "temperature"),
        ("HEAT", "setpoint_low", "temperature"),
        ("AUTO", "auto_setpoint_low", "target_temp_low"),
        ("AUTO", "auto_setpoint_high", "target_temp_high"),
    ],
)
@pytest.mark.parametrize("celsius", [True, False])
def test_reported_targets_align_to_fixed_steps(
    entity: StratisClimateEntity,
    hass: HomeAssistant,
    mode: str,
    field: str,
    attribute: str,
    celsius: bool,
) -> None:
    entity.hass = hass
    hass.config.units = METRIC_SYSTEM if celsius else US_CUSTOMARY_SYSTEM
    entity.thermostat.state["thermostat_mode"]["value"] = mode
    entity.thermostat.state[field]["value"] = 73.2

    attributes = entity.state_attributes
    assert attributes[attribute] == (23.0 if celsius else 73.0)
    assert attributes["current_temperature"] == (24.4 if celsius else 76)
    assert entity.thermostat.temperature(field) == 73.2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("display_unit", "requested", "expected"),
    [
        (UnitOfTemperature.CELSIUS, 22, 22),
        (UnitOfTemperature.CELSIUS, 22.5, 22.5),
        (UnitOfTemperature.CELSIUS, 23, 23),
        (UnitOfTemperature.CELSIUS, 23.5, 23.5),
        (UnitOfTemperature.CELSIUS, 22.8, 23),
        (UnitOfTemperature.FAHRENHEIT, 72.3, 72),
    ],
)
@pytest.mark.parametrize("native_scale", ["C", "F"])
async def test_temperature_write_uses_fixed_display_steps(
    entity: StratisClimateEntity,
    display_unit: str,
    requested: float,
    expected: float,
    native_scale: str,
) -> None:
    entity.hass.config.units.temperature_unit = display_unit
    entity.thermostat.state["ambient_temperature"]["scale"] = native_scale
    entity._async_write = AsyncMock()
    native_request = TemperatureConverter.convert(
        requested, display_unit, entity.temperature_unit
    )

    await entity.async_set_temperature(temperature=native_request)

    payload = entity._async_write.call_args.args[0]["setpoint_high"]
    assert payload["value"] == pytest.approx(
        TemperatureConverter.convert(expected, display_unit, entity.temperature_unit)
    )
    assert payload["value_int"] == 73
    assert payload["scale"] == native_scale


@pytest.mark.asyncio
async def test_temperature_write_is_rejected_while_off(
    entity: StratisClimateEntity,
) -> None:
    entity.thermostat.state["thermostat_mode"]["value"] = "OFF"
    entity._async_write = AsyncMock()

    with pytest.raises(ServiceValidationError) as err:
        await entity.async_set_temperature(temperature=72)

    assert err.value.translation_key == "temperature_while_off"
    entity._async_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_cooling_temperature_payload_preserves_confirmed_value(
    entity: StratisClimateEntity,
) -> None:
    entity._async_write = AsyncMock()

    await entity.async_set_temperature(temperature=72)

    entity._async_write.assert_awaited_once_with(
        {
            "setpoint_high": {
                "value_int": 73,
                "scale": "F",
                "value": 72.0,
            }
        }
    )


@pytest.mark.asyncio
async def test_heat_mode_and_temperature_can_be_sent_together(
    entity: StratisClimateEntity,
) -> None:
    entity.thermostat.state["thermostat_mode"]["value"] = "OFF"
    entity._async_write = AsyncMock()

    await entity.async_set_temperature(hvac_mode=HVACMode.HEAT, temperature=69)

    entity._async_write.assert_awaited_once_with(
        {
            "thermostat_mode": {"value": "HEAT"},
            "setpoint_low": {
                "value_int": 68,
                "scale": "F",
                "value": 69.0,
            },
        }
    )


@pytest.mark.asyncio
async def test_auto_temperature_range_payload(entity: StratisClimateEntity) -> None:
    entity._async_write = AsyncMock()

    await entity.async_set_temperature(
        hvac_mode=HVACMode.HEAT_COOL,
        target_temp_low=71,
        target_temp_high=76,
    )

    entity._async_write.assert_awaited_once_with(
        {
            "thermostat_mode": {"value": "AUTO"},
            "auto_setpoint_low": {
                "value_int": 70,
                "scale": "F",
                "value": 71.0,
            },
            "auto_setpoint_high": {
                "value_int": 75,
                "scale": "F",
                "value": 76.0,
            },
        }
    )


@pytest.mark.asyncio
async def test_fan_mode_mapping(entity: StratisClimateEntity) -> None:
    entity._async_write = AsyncMock()

    await entity.async_set_fan_mode("on")

    entity._async_write.assert_awaited_once_with(
        {"thermostat_fan_mode": {"value": "FAN_ON"}}
    )
