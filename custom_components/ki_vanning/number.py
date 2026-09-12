"""Vannprisen settes her."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PRIS, DOMAIN, STD_PRIS
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([Vannpris(hass.data[DOMAIN][entry.entry_id], entry)])


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

    async def async_set_native_value(self, value: float) -> None:
        self.motor.oppsett[CONF_PRIS] = value
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_PRIS: value}
        )
        self.async_write_ha_state()
