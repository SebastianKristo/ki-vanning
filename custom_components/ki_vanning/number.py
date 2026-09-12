"""Regnpause i timer – settes her eller med knappene."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, DOMAIN
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    if motor.plan:
        add([Regnpause(motor, entry)])


class Regnpause(KiVanningEntitet, NumberEntity):
    """Timer igjen av regnpausen. Sett den til 0 for å fjerne pausen."""

    _attr_icon = "mdi:weather-rainy"
    _attr_native_min_value = 0
    _attr_native_max_value = 168
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "t"
    _attr_mode = "box"

    def __init__(self, motor, entry: ConfigEntry) -> None:
        super().__init__(motor, "regnpause", "Regnpause")
        self.entry = entry

    @property
    def native_value(self) -> float:
        plan = self.motor.plan
        if not plan or not plan.regnpause_aktiv:
            return 0
        return round(plan.regnpause_minutter / 60, 1)

    @property
    def extra_state_attributes(self) -> dict:
        plan = self.motor.plan
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "regnpause",
            "aktiv": bool(plan and plan.regnpause_aktiv),
            "til": plan.regnpause_til.isoformat() if plan and plan.regnpause_til else None,
            "minutter": plan.regnpause_minutter if plan else 0,
        }

    async def async_set_native_value(self, value: float) -> None:
        self.motor.sett_regnpause(float(value))
