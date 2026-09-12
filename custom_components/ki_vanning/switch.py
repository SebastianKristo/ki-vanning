"""Hovedbryter for anlegget – av stopper alt og hindrer at programmene starter."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, DOMAIN
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    if motor.plan:
        add([Anlegg(motor, entry)])


class Anlegg(KiVanningEntitet, SwitchEntity):
    """Av betyr at ingenting vannes – verken program eller planlagt kjøring."""

    _attr_icon = "mdi:power"

    def __init__(self, motor, entry: ConfigEntry) -> None:
        super().__init__(motor, "anlegg", "Anlegget")
        self.entry = entry

    @property
    def is_on(self) -> bool:
        return self.motor.oppsett.get("anlegg", True) is not False

    @property
    def extra_state_attributes(self) -> dict:
        plan = self.motor.plan
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "anlegg",
            "regnpause": bool(plan and plan.regnpause_aktiv),
            "regnpause_minutter": plan.regnpause_minutter if plan else 0,
        }

    async def async_turn_on(self, **_kwargs) -> None:
        self.motor.sett_anlegg(True)

    async def async_turn_off(self, **_kwargs) -> None:
        self.motor.sett_anlegg(False)
