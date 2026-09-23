"""Knapper: stopp alt, regnpause, nullstilling og programplan."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, DOMAIN
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    ut = [Nullstill(motor, "alt", "Nullstill alt"),
          Nullstill(motor, "forbruk", "Nullstill forbruk"),
          Nullstill(motor, "kalibrering", "Nullstill kalibrering"),
          HentPlan(motor), TestVarsel(motor)]
    if motor.plan:
        ut += [StoppAlt(motor), Regn(motor, 24), Regn(motor, 48), NullstillRegn(motor)]
    add(ut)


class Nullstill(KiVanningEntitet, ButtonEntity):
    _attr_icon = "mdi:restart"

    def __init__(self, motor, hva: str, navn: str) -> None:
        super().__init__(motor, f"nullstill_{hva}", navn)
        self.hva = hva

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "nullstill_" + self.hva}

    async def async_press(self) -> None:
        await self.motor.nullstill(self.hva)


class TestVarsel(KiVanningEntitet, ButtonEntity):
    """Sender et eksempelvarsel til mottakerne, uansett bryterne."""

    _attr_icon = "mdi:bell-ring-outline"

    def __init__(self, motor) -> None:
        super().__init__(motor, "test_varsel", "Test varsel")

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "test_varsel"}

    async def async_press(self) -> None:
        self.motor.varsler.test()


class HentPlan(KiVanningEntitet, ButtonEntity):
    _attr_icon = "mdi:calendar-refresh"

    def __init__(self, motor) -> None:
        super().__init__(motor, "hent_plan", "Hent programplan")

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "hent_plan"}

    async def async_press(self) -> None:
        await self.motor._hent_plan(None)


class StoppAlt(KiVanningEntitet, ButtonEntity):
    """Stopper det som går nå, og tømmer køen."""

    _attr_icon = "mdi:stop"

    def __init__(self, motor) -> None:
        super().__init__(motor, "stopp_alt", "Stopp alt")

    @property
    def extra_state_attributes(self) -> dict:
        plan = self.motor.plan
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "stopp_alt",
                "gaar": bool(plan and plan.naa), "i_koe": len(plan.koe) if plan else 0}

    async def async_press(self) -> None:
        if self.motor.plan:
            await self.motor.plan.stopp_alt()


class Regn(KiVanningEntitet, ButtonEntity):
    """Setter regnpause i et gitt antall timer."""

    _attr_icon = "mdi:weather-pouring"

    def __init__(self, motor, timer: int) -> None:
        super().__init__(motor, f"regn_{timer}t", f"Regnpause {timer} t")
        self.timer = timer

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "regnpause_sett", "timer": self.timer}

    async def async_press(self) -> None:
        self.motor.sett_regnpause(self.timer)


class NullstillRegn(KiVanningEntitet, ButtonEntity):
    """Fjerner regnpausen, slik at programmene går som vanlig igjen."""

    _attr_icon = "mdi:weather-sunny"

    def __init__(self, motor) -> None:
        super().__init__(motor, "nullstill_regnpause", "Nullstill regnpause")

    @property
    def extra_state_attributes(self) -> dict:
        plan = self.motor.plan
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "regnpause_nullstill",
                "aktiv": bool(plan and plan.regnpause_aktiv)}

    async def async_press(self) -> None:
        self.motor.sett_regnpause(0)
