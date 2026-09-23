"""Hovedbryter for anlegget – av stopper alt og hindrer at programmene starter."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, DOMAIN
from .entity import KiVanningEntitet
from .varsler import VARSELTYPER


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    ut = []
    if motor.plan:
        ut.append(Anlegg(motor, entry))
    # Varselbryterne finnes i begge modiene. De som krever vannmåler, lages bare når
    # anlegget har en – en bryter for «vann renner» uten måler kan aldri slå til.
    ut.append(VarselBryter(motor, "hoved", "Varsler", "mdi:bell"))
    ikoner = {"program": "mdi:calendar-clock", "sone": "mdi:sprinkler", "regnpause": "mdi:weather-pouring",
              "vann_renner": "mdi:water-alert", "ingen_flyt": "mdi:water-off"}
    for nokkel in motor.varsler.typer():
        ut.append(VarselBryter(motor, nokkel, VARSELTYPER[nokkel][0], ikoner.get(nokkel, "mdi:bell-outline")))
    add(ut)


class VarselBryter(KiVanningEntitet, SwitchEntity):
    """Slår én type vanningsvarsel av og på. «Varsler» er hovedbryteren."""

    def __init__(self, motor, nokkel: str, navn: str, ikon: str) -> None:
        super().__init__(motor, f"varsel_{nokkel}", navn)
        self.nokkel = nokkel
        self._attr_icon = ikon

    @property
    def is_on(self) -> bool:
        return bool(self.motor.varsler.pa.get(self.nokkel, False))

    @property
    def extra_state_attributes(self) -> dict:
        v = self.motor.varsler
        a = {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: f"varsel_{self.nokkel}"}
        if self.nokkel == "hoved":
            a.update({"mottakere": v.mottakere, "sist_sendt": v.sist_sendt})
        return a

    async def async_turn_on(self, **_kwargs) -> None:
        self.motor.varsler.sett(self.nokkel, True)

    async def async_turn_off(self, **_kwargs) -> None:
        self.motor.varsler.sett(self.nokkel, False)


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
