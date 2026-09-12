"""KI Vanning – forbruk, kostnad og estimat for OpenSprinkler."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS
from .coordinator import KiVanningMotor


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    oppsett = {**entry.data, **entry.options}
    motor = KiVanningMotor(hass, oppsett)
    motor.entry = entry
    await motor.start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = motor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_oppdater))

    async def nullstill(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            await m.nullstill(call.data.get("hva", "alt"))

    async def hent_plan(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            await m._hent_plan(None)

    async def kjor(call: ServiceCall) -> None:
        """Kjør én sone i et gitt antall minutter."""
        sone = call.data.get("sone")
        minutter = float(call.data.get("minutter") or 10)
        for m in list(hass.data[DOMAIN].values()):
            if m.plan and (m.sone_for(sone) or not sone):
                await m.kjor_sone(sone or next(iter(m.soner.values())).bryter, minutter)

    async def kjor_program(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            if m.plan:
                await m.kjor_program(call.data.get("program"))

    async def stopp(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            await m.stopp_alt()

    async def lag_program(call: ServiceCall) -> None:
        """Lager et nytt program eller oppdaterer et som finnes fra før."""
        for m in list(hass.data[DOMAIN].values()):
            if m.plan:
                await m.lagre_program(dict(call.data))

    async def slett_program(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            if m.plan:
                await m.slett_program(call.data.get("navn"))

    async def sett_ferie(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            m.sett_ferie(bool(call.data.get("pa", True)))

    hass.services.async_register(DOMAIN, "nullstill", nullstill)
    hass.services.async_register(DOMAIN, "hent_plan", hent_plan)
    hass.services.async_register(DOMAIN, "kjor", kjor)
    hass.services.async_register(DOMAIN, "kjor_program", kjor_program)
    hass.services.async_register(DOMAIN, "stopp", stopp)
    hass.services.async_register(DOMAIN, "sett_ferie", sett_ferie)
    hass.services.async_register(DOMAIN, "lag_program", lag_program)
    hass.services.async_register(DOMAIN, "slett_program", slett_program)
    return True


MYKE_FELT = {"programmer", "ferie", "ferie_faktor", "pris"}


async def _oppdater(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Endringer i programmer, ferie og pris tas rett inn i motoren.
    Bare endringer i oppsettet ellers krever full omstart av integrasjonen."""
    motor = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if motor is not None:
        nye = {**entry.data, **entry.options}
        endret = {k for k in set(nye) | set(motor.oppsett) if nye.get(k) != motor.oppsett.get(k)}
        if endret and endret <= MYKE_FELT:
            motor.oppsett.update(nye)
            if motor.plan:
                motor.plan.les_programmer()
            await motor._hent_plan(None)
            motor._varsle()
            return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        motor = hass.data[DOMAIN].pop(entry.entry_id)
        await motor.stopp()
    return ok
