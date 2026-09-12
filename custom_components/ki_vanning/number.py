"""Vannprisen settes her."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, CONF_PRIS, DOMAIN, STD_PRIS
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    ut = [Vannpris(motor, entry)]
    if motor.plan:
        ut.append(FerieFaktor(motor, entry))
    add(ut)


class Vannpris(KiVanningEntitet, NumberEntity):
    _attr_native_unit_of_measurement = "kr/m³"
    _attr_native_min_value = 0
    _attr_native_max_value = 500
    _attr_native_step = 0.01
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:cash"

    def __init__(self, motor, entry: ConfigEntry) -> None:
        super().__init__(motor, "vannpris", "Vannpris")
        self.entry = entry

    @property
    def native_value(self) -> float:
        return float(self.motor.oppsett.get(CONF_PRIS, STD_PRIS))

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "vannpris"}

    async def async_set_native_value(self, value: float) -> None:
        self.motor.oppsett[CONF_PRIS] = value
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_PRIS: value}
        )
        self.async_write_ha_state()


class FerieFaktor(KiVanningEntitet, NumberEntity):
    """Hvor mye lenger sonene skal gå når feriemodus er på."""

    _attr_native_min_value = 1
    _attr_native_max_value = 3
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:beach"

    def __init__(self, motor, entry: ConfigEntry) -> None:
        super().__init__(motor, "ferie_faktor", "Ferie – lengre vanning")
        self.entry = entry

    @property
    def native_value(self) -> float:
        return float(self.motor.oppsett.get("ferie_faktor") or 1.3)

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "ferie_faktor"}

    async def async_set_native_value(self, value: float) -> None:
        self.motor.oppsett["ferie_faktor"] = value
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, "ferie_faktor": value}
        )
        await self.motor._hent_plan(None)
        self.async_write_ha_state()
