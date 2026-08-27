"""Data models and defensive parsers for STRATIS responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _resource_id(name: object, collection: str) -> str:
    """Extract an identifier from a STRATIS resource name."""
    if not isinstance(name, str):
        return ""
    marker = f"/{collection}/"
    if marker in name:
        return name.rsplit(marker, 1)[1]
    if name.startswith(f"{collection}/"):
        return name.split("/", 1)[1]
    return name


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


@dataclass(frozen=True, slots=True)
class StratisTokens:
    """An OAuth token pair returned by STRATIS."""

    access_token: str
    refresh_token: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class StratisProperty:
    """A STRATIS property accessible to the account."""

    property_id: str
    display_name: str

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> StratisProperty | None:
        property_id = _resource_id(value.get("name"), "properties")
        if not property_id:
            raw_id = value.get("property_id") or value.get("id")
            property_id = raw_id if isinstance(raw_id, str) else ""
        if not property_id:
            return None
        display_name = value.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            display_name = property_id
        return cls(property_id=property_id, display_name=display_name)


@dataclass(slots=True)
class StratisThermostat:
    """A thermostat plus its latest reported state."""

    property_id: str
    unit_id: str
    device_id: str
    display_name: str
    manufacturer: str
    model: str
    modes: tuple[str, ...]
    fan_modes: tuple[str, ...]
    state: dict[str, Any]

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> StratisThermostat | None:
        state = value.get("state")
        thermostat_state = state.get("thermostat") if isinstance(state, dict) else None
        device_type = value.get("device_type")
        device_class = (
            device_type.get("device_class") if isinstance(device_type, dict) else None
        )
        class_name = (
            device_class.get("display_name") if isinstance(device_class, dict) else None
        )
        if not isinstance(thermostat_state, dict) and class_name != "Thermostat":
            return None

        device_id = _resource_id(value.get("name"), "devices")
        property_id = value.get("property_id")
        unit_id = value.get("unit_id")
        if not all(isinstance(item, str) and item for item in (device_id, property_id)):
            return None

        attributes = value.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        modes = attributes.get("thermostat_modes_available")
        fan_modes = attributes.get("thermostat_fan_modes_available")

        device_model = value.get("device_model")
        device_model = device_model if isinstance(device_model, dict) else {}
        manufacturer = device_model.get("manufacturer")
        if not isinstance(manufacturer, str) or not manufacturer:
            manufacturer = "STRATIS"
        model = device_model.get("display_name") or device_model.get("model_number")
        if not isinstance(model, str) or not model:
            type_name = (
                device_type.get("display_name")
                if isinstance(device_type, dict)
                else None
            )
            model = type_name if isinstance(type_name, str) else "Thermostat"

        display_name = value.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            display_name = device_id

        return cls(
            property_id=property_id,
            unit_id=unit_id if isinstance(unit_id, str) else "",
            device_id=device_id,
            display_name=display_name,
            manufacturer=manufacturer,
            model=model,
            modes=tuple(item.lower() for item in modes if isinstance(item, str))
            if isinstance(modes, list)
            else (),
            fan_modes=tuple(item.lower() for item in fan_modes if isinstance(item, str))
            if isinstance(fan_modes, list)
            else (),
            state=thermostat_state if isinstance(thermostat_state, dict) else {},
        )

    def state_field(self, name: str) -> dict[str, Any]:
        value = self.state.get(name)
        return value if isinstance(value, dict) else {}

    def state_value(self, name: str) -> str | None:
        value = self.state_field(name).get("value")
        return value if isinstance(value, str) else None

    def temperature(self, name: str) -> float | None:
        field = self.state_field(name)
        value = _number(field.get("value"))
        return value if value is not None else _number(field.get("value_int"))

    @property
    def temperature_scale(self) -> str:
        for name in (
            "ambient_temperature",
            "setpoint_high",
            "setpoint_low",
            "auto_setpoint_high",
            "auto_setpoint_low",
        ):
            scale = self.state_field(name).get("scale")
            if scale in ("C", "F"):
                return scale
        return "F"

    @property
    def humidity(self) -> int | None:
        value = _number(self.state_field("humidity").get("value"))
        return round(value) if value is not None else None

    @property
    def is_online(self) -> bool:
        return self.state_value("online") != "OFFLINE"

    def confirmed_integral_temperature(self, name: str, fallback: float) -> int:
        field = self.state_field(name)
        confirmed = _number(field.get("value_int"))
        if confirmed is None:
            confirmed = _number(field.get("value"))
        return round(confirmed if confirmed is not None else fallback)


@dataclass(frozen=True, slots=True)
class StratisData:
    """Coordinator snapshot for an account."""

    properties: dict[str, StratisProperty]
    thermostats: dict[str, StratisThermostat]
