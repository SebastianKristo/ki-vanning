"""Oppsett i brukergrensesnittet – finner det meste selv."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_FLOW,
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

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        feil: dict[str, str] = {}
        prefiks = _finn_prefiks(self.hass)
        flow = _finn_flow(self.hass)

        if user_input is not None:
            if not user_input.get(CONF_PREFIKS):
                feil[CONF_PREFIKS] = "fant_ikke_opensprinkler"
            else:
                await self.async_set_unique_id(user_input[CONF_PREFIKS])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="KI Vanning", data=user_input)

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
            step_id="user", data_schema=skjema, errors=feil,
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
