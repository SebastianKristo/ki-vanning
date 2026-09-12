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


def _tolk_soner(valgte, oppsett) -> list[dict[str, Any]]:
    """Sonene i et program: valgte entiteter, med minutter fra «entity:min»-lista."""
    minutter: dict[str, float] = {}
    for bit in str(oppsett.get("_minutter") or "").split(","):
        if ":" in bit:
            e, m = bit.split(":", 1)
            try:
                minutter[e.strip()] = float(m)
            except ValueError:
                pass
    ut = []
    for e in (valgte or []):
        ut.append({"entity": e, "min": minutter.get(e, 10)})
    return ut


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
                                    "metode": user_input.get("metode") or "",
                                    "gruppe": user_input.get("gruppe") or "",
                                    "flow": user_input.get("flow") or ""})
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
            vol.Optional("gruppe", default=""): str,
            vol.Optional("flow"): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
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
    """Endringer etterpå: innstillinger, ventiler og programmer."""

    def __init__(self, entry) -> None:
        self.entry = entry
        self._valgt: str | None = None

    def _alt(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _lagre(self, felt: dict[str, Any]):
        return self.async_create_entry(title="", data={**self.entry.options, **felt})

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Meny: hva vil du endre?"""
        d = self._alt()
        if d.get("modus") != MODUS_VENTILER:
            return await self.async_step_innstillinger()
        return self.async_show_menu(step_id="init", menu_options=["innstillinger", "programmer", "ventiler_endre"])

    # ------------------------------------------------------------ programmer
    async def async_step_programmer(self, user_input: dict[str, Any] | None = None):
        """Velg et program å endre, eller lag et nytt."""
        liste = self._alt().get(CONF_PROGRAMMER) or []
        if user_input is not None:
            self._valgt = user_input["program"]
            return await self.async_step_program()
        valg = [{"value": p.get("navn", ""), "label": f"{p.get('navn')} – kl. {p.get('tid', '')}"} for p in liste]
        valg.append({"value": "__nytt", "label": "+ Nytt program"})
        skjema = vol.Schema({vol.Required("program", default=valg[0]["value"]): selector.SelectSelector(
            selector.SelectSelectorConfig(options=valg, mode="list"))})
        return self.async_show_form(step_id="programmer", data_schema=skjema)

    async def async_step_program(self, user_input: dict[str, Any] | None = None):
        """Skjemaet for ett program."""
        liste = list(self._alt().get(CONF_PROGRAMMER) or [])
        nytt = self._valgt == "__nytt"
        gammel = {} if nytt else next((p for p in liste if p.get("navn") == self._valgt), {})

        if user_input is not None:
            if user_input.get("slett") and not nytt:
                liste = [p for p in liste if p.get("navn") != self._valgt]
                return self._lagre({CONF_PROGRAMMER: liste})
            rad = {
                "navn": user_input["navn"].strip(),
                "tid": str(user_input.get("tid") or "06:00")[:5],
                "dager": user_input.get("dager") or [],
                "intervall": int(user_input.get("intervall") or 0),
                "start_dato": str(user_input.get("start_dato") or ""),
                "soner": _tolk_soner(user_input.get("soner"), {"_minutter": user_input.get("minutter")}),
                "samtidig": bool(user_input.get("samtidig")),
                "ferie": bool(user_input.get("ferie")),
                "aktiv": bool(user_input.get("aktiv", True)),
            }
            liste = [p for p in liste if p.get("navn") not in (self._valgt, rad["navn"])]
            liste.append(rad)
            return self._lagre({CONF_PROGRAMMER: liste})

        soner = self._alt().get(CONF_SONER) or []
        valg = [{"value": (s.get("entity") if isinstance(s, dict) else s),
                 "label": (s.get("navn") or s.get("entity")) if isinstance(s, dict) else s} for s in soner]
        gamle_soner = {z.get("entity"): z.get("min") for z in (gammel.get("soner") or [])}
        skjema = vol.Schema({
            vol.Required("navn", default=gammel.get("navn", "")): str,
            vol.Required("tid", default=gammel.get("tid", "06:00")): selector.TimeSelector(),
            vol.Optional("dager", default=gammel.get("dager", ["man", "tor"])): selector.SelectSelector(
                selector.SelectSelectorConfig(options=list(UKEDAGER), multiple=True, mode="list")),
            vol.Optional("intervall", default=gammel.get("intervall", 0)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=30, mode="box")),
            vol.Optional("start_dato", default=gammel.get("start_dato", "")): str,
            vol.Optional("soner", default=[e for e in gamle_soner]): selector.SelectSelector(
                selector.SelectSelectorConfig(options=valg, multiple=True, mode="list")),
            vol.Optional("minutter", default=str(", ".join(f"{k}:{v}" for k, v in gamle_soner.items()) or "")): str,
            vol.Optional("samtidig", default=gammel.get("samtidig", False)): bool,
            vol.Optional("ferie", default=gammel.get("ferie", False)): bool,
            vol.Optional("aktiv", default=gammel.get("aktiv", True)): bool,
            **({vol.Optional("slett", default=False): bool} if not nytt else {}),
        })
        return self.async_show_form(step_id="program", data_schema=skjema,
                                    description_placeholders={"navn": gammel.get("navn", "nytt program")})

    # ------------------------------------------------------------ ventiler
    async def async_step_ventiler_endre(self, user_input: dict[str, Any] | None = None):
        """Rediger ventillista som ren tekst: entitet | navn | gruppe | flow-sensor."""
        soner = self._alt().get(CONF_SONER) or []
        if user_input is not None:
            nye = []
            for linje in str(user_input.get("soner") or "").splitlines():
                if not linje.strip():
                    continue
                d = [x.strip() for x in linje.split("|")]
                if not d[0]:
                    continue
                nye.append({"entity": d[0], "navn": d[1] if len(d) > 1 else "",
                            "gruppe": d[2] if len(d) > 2 else "", "flow": d[3] if len(d) > 3 else ""})
            return self._lagre({CONF_SONER: nye})
        tekst = "\n".join(
            " | ".join([s.get("entity", ""), s.get("navn", ""), s.get("gruppe", ""), s.get("flow", "")]).rstrip(" |")
            for s in soner)
        skjema = vol.Schema({vol.Optional("soner", default=tekst): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True))})
        return self.async_show_form(step_id="ventiler_endre", data_schema=skjema)

    # ------------------------------------------------------------ innstillinger
    async def async_step_innstillinger(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self._lagre(user_input)
        d = self._alt()
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
