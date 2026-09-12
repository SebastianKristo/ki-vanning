"""KI Vanning – forbruk, kostnad og estimat for OpenSprinkler."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS
from .coordinator import KiVanningMotor


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    oppsett = {**entry.data, **entry.options}
    motor = KiVanningMotor(hass, oppsett)
    await motor.start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = motor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_oppdater))

    async def nullstill(call: ServiceCall) -> None:
        for m in hass.data[DOMAIN].values():
            await m.nullstill(call.data.get("hva", "alt"))

    async def hent_plan(call: ServiceCall) -> None:
        for m in hass.data[DOMAIN].values():
            await m._hent_plan(None)

    hass.services.async_register(DOMAIN, "nullstill", nullstill)
    hass.services.async_register(DOMAIN, "hent_plan", hent_plan)
    return True


async def _oppdater(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        motor = hass.data[DOMAIN].pop(entry.entry_id)
        await motor.stopp()
    return ok
