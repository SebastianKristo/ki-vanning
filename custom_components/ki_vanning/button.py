"""Knapper for å nullstille tellerne og hente programplanen."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    add([Nullstill(motor, "alt", "Nullstill alt"),
         Nullstill(motor, "forbruk", "Nullstill forbruk"),
         Nullstill(motor, "kalibrering", "Nullstill kalibrering"),
         HentPlan(motor)])


class Nullstill(KiVanningEntitet, ButtonEntity):
    _attr_icon = "mdi:restart"

    def __init__(self, motor, hva: str, navn: str) -> None:
        super().__init__(motor, f"nullstill_{hva}", navn)
        self.hva = hva

    async def async_press(self) -> None:
        await self.motor.nullstill(self.hva)


class HentPlan(KiVanningEntitet, ButtonEntity):
    _attr_icon = "mdi:calendar-refresh"

    def __init__(self, motor) -> None:
        super().__init__(motor, "hent_plan", "Hent programplan")

    async def async_press(self) -> None:
        await self.motor._hent_plan(None)
