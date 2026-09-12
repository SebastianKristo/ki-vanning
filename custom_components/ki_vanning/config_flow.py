"""Oppsett i brukergrensesnittet – finner det meste selv."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_FERIE_FAKTOR,
    CONF_FLOW,
    CONF_MODUS,
    CONF_PROGRAMMER,
    CONF_SONER,
    MODUS_OS,
    MODUS_VENTILER,
    STD_FERIE_FAKTOR,
    UKEDAGER,
    CONF_HOST,
    CONF_MIN_FLOW,
    CONF_PASSORD,
    CONF_PREFIKS,
    CONF_PRIS,
    DOMAIN,
    STD_MIN_FLOW,
    STD_PRIS,
)


def _finn_prefiks(hass) -> str | None:
    """Gjetter OpenSprinkler-prefikset ut fra entitetene som finnes."""
    for eid in hass.states.async_entity_ids("binary_sensor"):
        if traff := re.match(r"^binary_sensor\.(.+)_s\d\d.*_station_running$", eid):
            return traff.group(1)
    return None


def _finn_flow(hass) -> str | None:
    """Finner en sannsynlig flow-sensor (L/min)."""
    for eid in hass.states.async_entity_ids("sensor"):
        st = hass.states.get(eid)
        if not st:
            continue
        enhet = (st.attributes.get("unit_of_measurement") or "").lower()
        if enhet in ("l/min", "lpm") or "liter_per_minutt" in eid:
            return eid
    return None


class KiVanningFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Første oppsett."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._soner: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Velg hva slags anlegg det er."""
        if user_input is not None:
            if user_input[CONF_MODUS] == MODUS_VENTILER:
                return await self.async_step_ventiler()
            return await self.async_step_opensprinkler()
        skjema = vol.Schema({
            vol.Required(CONF_MODUS, default=MODUS_OS if _finn_prefiks(self.hass) else MODUS_VENTILER):
                selector.SelectSelector(selector.SelectSelectorConfig(options=[
                    {"value": MODUS_OS, "label": "OpenSprinkler"},
                    {"value": MODUS_VENTILER, "label": "Egne ventiler (brytere)"}], mode="list")),
        })
        return self.async_show_form(step_id="user", data_schema=skjema)

    # ------------------------------------------------------------ egne ventiler
    async def async_step_ventiler(self, user_input: dict[str, Any] | None = None):
        """Vannmåler og pris – deretter legges sonene til én etter én."""
        if user_input is not None:
            self._data = {**user_input, CONF_MODUS: MODUS_VENTILER}
            return await self.async_step_sone()
        skjema = vol.Schema({
            vol.Optional(CONF_FLOW, default=_finn_flow(self.hass) or ""): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")),
            vol.Optional(CONF_PRIS, default=STD_PRIS): vol.Coerce(float),
            vol.Optional(CONF_FERIE_FAKTOR, default=STD_FERIE_FAKTOR): vol.Coerce(float),
        })
        return self.async_show_form(step_id="ventiler", data_schema=skjema)

    async def async_step_sone(self, user_input: dict[str, Any] | None = None):
        """Legg til én ventil om gangen."""
        if user_input is not None:
            if user_input.get("entity"):
                self._soner.append({"entity": user_input["entity"], "navn": user_input.get("navn") or "",
                                    "metode": user_input.get("metode") or ""})
            if user_input.get("flere") and user_input.get("entity"):
                return await self.async_step_sone()
            if not self._soner:
                return self.async_abort(reason="ingen_soner")
            await self.async_set_unique_id("ki_vanning_ventiler")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="KI Vanning", data={**self._data, CONF_SONER: self._soner,
                                                                     CONF_PROGRAMMER: []})
        skjema = vol.Schema({
            vol.Optional("entity"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "valve", "input_boolean"])),
            vol.Optional("navn", default=""): str,
            vol.Optional("metode", default=""): str,
            vol.Optional("flere", default=True): bool,
        })
        return self.async_show_form(step_id="sone", data_schema=skjema,
                                    description_placeholders={"antall": str(len(self._soner))})

    async def async_step_opensprinkler(self, user_input: dict[str, Any] | None = None):
        feil: dict[str, str] = {}
        prefiks = _finn_prefiks(self.hass)
        flow = _finn_flow(self.hass)

        if user_input is not None:
            if not user_input.get(CONF_PREFIKS):
                feil[CONF_PREFIKS] = "fant_ikke_opensprinkler"
            else:
                await self.async_set_unique_id(user_input[CONF_PREFIKS])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="KI Vanning", data={**user_input, CONF_MODUS: MODUS_OS})

        skjema = vol.Schema(
            {
                vol.Required(CONF_PREFIKS, default=prefiks or ""): str,
                vol.Required(CONF_FLOW, default=flow or ""): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_HOST, default=""): str,
                vol.Optional(CONF_PASSORD, default=""): str,
                vol.Optional(CONF_PRIS, default=STD_PRIS): vol.Coerce(float),
                vol.Optional(CONF_MIN_FLOW, default=STD_MIN_FLOW): vol.Coerce(float),
            }
        )
        return self.async_show_form(
            step_id="opensprinkler", data_schema=skjema, errors=feil,
            description_placeholders={"prefiks": prefiks or "ikke funnet"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return KiVanningOptions(entry)


class KiVanningOptions(config_entries.OptionsFlow):
    """Endringer etterpå."""

    def __init__(self, entry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        d = {**self.entry.data, **self.entry.options}
        skjema = vol.Schema(
            {
                vol.Required(CONF_FLOW, default=d.get(CONF_FLOW, "")): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_HOST, default=d.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PASSORD, default=d.get(CONF_PASSORD, "")): str,
                vol.Optional(CONF_PRIS, default=d.get(CONF_PRIS, STD_PRIS)): vol.Coerce(float),
                vol.Optional(CONF_MIN_FLOW, default=d.get(CONF_MIN_FLOW, STD_MIN_FLOW)): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="init", data_schema=skjema)
