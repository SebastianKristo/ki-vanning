"""Feriemodus for egne ventiler."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, CONF_FERIE, DOMAIN
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    if motor.plan:
        add([Ferie(motor, entry)])


class Ferie(KiVanningEntitet, SwitchEntity):
    """Når ferien er på, kjører ferieprogrammene og vanningstiden ganges opp."""

    _attr_icon = "mdi:beach"

    def __init__(self, motor, entry: ConfigEntry) -> None:
        super().__init__(motor, "ferie", "Feriemodus")
        self.entry = entry

    @property
    def is_on(self) -> bool:
        return bool(self.motor.oppsett.get(CONF_FERIE))

    async def async_turn_on(self, **kwargs) -> None:
        await self._sett(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._sett(False)

    async def _sett(self, pa: bool) -> None:
        self.motor.sett_ferie(pa)
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, CONF_FERIE: pa})
        await self.motor._hent_plan(None)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "ferie",
                "faktor": self.motor.oppsett.get("ferie_faktor"),
                "ferieprogrammer": [p["navn"] for p in self.motor.programliste() if p.get("ferie")]}
