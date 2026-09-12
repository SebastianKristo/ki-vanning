"""Er hageslangen i bruk, og vannes det i det hele tatt?"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_TYPE, DOMAIN
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor = hass.data[DOMAIN][entry.entry_id]
    add([Hageslange(motor), Vanner(motor)])


class Hageslange(KiVanningEntitet, BinarySensorEntity):
    """Vann som går uten at en sone kjører, regnes som hageslangen."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:hose"

    def __init__(self, motor) -> None:
        super().__init__(motor, "hageslange", "Hageslange i bruk")

    @property
    def is_on(self) -> bool:
        return self.motor.aktiv() is None and self.motor._flow() > 0

    @property
    def extra_state_attributes(self) -> dict:
        h = self.motor.hageslange
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "hageslange", "flow": self.motor._flow(),
                "liter_i_dag": round(h.perioder["i_dag"], 1), "liter_totalt": round(h.liter, 1),
                "kostnad_i_dag": self.motor.kostnad(h.perioder["i_dag"])}


class Vanner(KiVanningEntitet, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, motor) -> None:
        super().__init__(motor, "vanner", "Vanner nå")

    @property
    def is_on(self) -> bool:
        return self.motor.aktiv() is not None or self.motor._flow() > 0
