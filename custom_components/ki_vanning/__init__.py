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
            if m.soner and (m.sone_for(sone) or not sone):
                await m.kjor_sone(sone or next(iter(m.soner.values())).bryter, minutter)

    async def apne_hovedventil(call: ServiceCall) -> None:
        """Åpner hovedventilen nå (knappen i kortet når den står stengt mens en sone går)."""
        for m in list(hass.data[DOMAIN].values()):
            await m.master_pa()

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

    async def sett_regnpause(call: ServiceCall) -> None:
        """Setter eller fjerner regnpause, i timer."""
        for m in list(hass.data[DOMAIN].values()):
            m.sett_regnpause(float(call.data.get("timer") or 0))

    async def nullstill_regnpause(_call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            m.sett_regnpause(0)

    async def sett_anlegg(call: ServiceCall) -> None:
        for m in list(hass.data[DOMAIN].values()):
            m.sett_anlegg(bool(call.data.get("pa", True)))

    hass.services.async_register(DOMAIN, "nullstill", nullstill)
    hass.services.async_register(DOMAIN, "hent_plan", hent_plan)
    hass.services.async_register(DOMAIN, "kjor", kjor)
    hass.services.async_register(DOMAIN, "apne_hovedventil", apne_hovedventil)
    hass.services.async_register(DOMAIN, "kjor_program", kjor_program)
    hass.services.async_register(DOMAIN, "stopp", stopp)
    hass.services.async_register(DOMAIN, "sett_regnpause", sett_regnpause)
    hass.services.async_register(DOMAIN, "nullstill_regnpause", nullstill_regnpause)
    hass.services.async_register(DOMAIN, "sett_anlegg", sett_anlegg)
    hass.services.async_register(DOMAIN, "lag_program", lag_program)
    hass.services.async_register(DOMAIN, "slett_program", slett_program)
    return True


MYKE_FELT = {"programmer", "anlegg"}


async def _oppdater(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Endringer i programmer og hovedbryter tas rett inn i motoren.
    Bare endringer i oppsettet ellers krever full omstart av integrasjonen."""
    motor = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if motor is not None:
        nye = {**entry.data, **entry.options}
        endret = {k for k in set(nye) | set(motor.oppsett) if nye.get(k) != motor.oppsett.get(k)}
        if not endret:
            # Motoren har allerede skrevet endringen selv – da er det ikke noe
            # å laste inn på nytt. Uten dette ble hele integrasjonen startet om
            # hver gang et program ble slått av eller på.
            motor._varsle()
            return
        if endret <= MYKE_FELT:
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
