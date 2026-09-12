"""Felles grunnlag for entitetene i KI Vanning."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import ATTR_INTEGRASJON, DOMAIN
from .coordinator import KiVanningMotor


class KiVanningEntitet(Entity):
    """Alle entitetene våre henger på samme enhet og oppdateres av motoren."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, motor: KiVanningMotor, nokkel: str, navn: str) -> None:
        self.motor = motor
        self._attr_unique_id = f"{DOMAIN}_{motor.oppsett['prefiks']}_{nokkel}"
        self._attr_name = navn
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, motor.oppsett["prefiks"])},
            name="KI Vanning",
            manufacturer="KI",
            model="OpenSprinkler-forbruk",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.motor.abonner(self.async_write_ha_state))

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN}
