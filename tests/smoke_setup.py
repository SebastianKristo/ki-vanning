"""Innlastingstest: integrasjonen lastes gjennom Home Assistants egen laster, i begge
modiene, og avlastes rent. Viser at bryterne og testknappen faktisk blir entiteter,
og at innstillingsskjemaet kan lagres fra begynnelse til slutt."""
import asyncio
import re
import shutil
import tempfile
from pathlib import Path

from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (area_registry, device_registry, entity_registry,
                                   floor_registry, label_registry)

P = "ute"


async def main():
    with tempfile.TemporaryDirectory() as rot:
        shutil.copytree(Path(__file__).resolve().parents[1] / "custom_components", Path(rot) / "custom_components",
                        ignore=shutil.ignore_patterns("__pycache__"))
        h = HomeAssistant(rot)
        h.config.skip_pip = True
        loader.async_setup(h)
        h.config_entries = config_entries.ConfigEntries(h, {})
        await h.config_entries.async_initialize()
        for reg in [entity_registry, device_registry, area_registry, floor_registry, label_registry]:
            await reg.async_load(h)
        sendt = []

        async def notify(call):
            sendt.append(dict(call.data))

        h.services.async_register("notify", "mobile_app_test", notify)

        # ---- OpenSprinkler
        h.states.async_set(f"switch.{P}_s01_plen_station_enabled", "on", {"friendly_name": "S01 Plen Station Enabled"})
        h.states.async_set(f"binary_sensor.{P}_s01_plen_station_running", "off")
        h.states.async_set(f"switch.{P}_morgen_program_enabled", "on", {"friendly_name": "Morgen Program Enabled"})
        h.states.async_set(f"binary_sensor.{P}_morgen_program_running", "off")
        h.states.async_set(f"binary_sensor.{P}_rain_delay_active", "off")
        h.states.async_set("sensor.vannmaler", "0")
        os_entry = config_entries.ConfigEntry(
            version=1, minor_version=1, domain="ki_vanning", title="OpenSprinkler",
            data={"modus": "opensprinkler", "prefiks": P, "flow": "sensor.vannmaler", "pris": 41.11,
                  "varsel_til": ["mobile_app_test"]},
            options={}, source="user", unique_id=None, discovery_keys={}, subentries_data=[])
        await asyncio.wait_for(h.config_entries.async_add(os_entry), 30)
        await h.async_block_till_done()
        assert os_entry.state == config_entries.ConfigEntryState.LOADED, os_entry.state
        reg = entity_registry.async_get(h)
        egne = {e.entity_id for e in entity_registry.async_entries_for_config_entry(reg, os_entry.entry_id)}
        brytere = sorted(e for e in egne if e.startswith("switch.") and ("varsel" in e or e.endswith("_varsler")))
        print("OS-BRYTERE", brytere)
        assert len(brytere) == 6, brytere          # hoved + 5 typer, med vannmåler
        assert any(e.startswith("button.") and "test_varsel" in e for e in egne)
        assert h.states.get(brytere[0]).state in ("on", "off")

        # et program starter → varsel
        h.states.async_set(f"binary_sensor.{P}_morgen_program_running", "on")
        await h.async_block_till_done()
        assert sendt and sendt[-1]["title"] == "💧 Vanning startet", sendt
        print("OS VARSEL OK")

        # hovedbryteren av → ingen varsel
        hoved = next(e for e in brytere if re.search(r"_varsler(_\d+)?$", e))
        await h.services.async_call("switch", "turn_off", {"entity_id": hoved}, blocking=True)
        sendt.clear()
        h.states.async_set(f"binary_sensor.{P}_morgen_program_running", "off")
        await h.async_block_till_done()
        assert sendt == [], sendt
        assert h.states.get(hoved).state == "off"
        print("HOVEDBRYTER OK")

        # innstillingsskjemaet lagres hele veien gjennom HA
        flyt = await h.config_entries.options.async_init(os_entry.entry_id)
        assert flyt["type"] == "form" and flyt["step_id"] == "innstillinger", flyt
        svar = await h.config_entries.options.async_configure(
            flyt["flow_id"], {"pris": 40.0, "varsel_til": ["mobile_app_test"], "varsel_vann_min": 45})
        assert svar["type"] == "create_entry", svar
        await h.async_block_till_done()
        assert os_entry.options["varsel_vann_min"] == 45
        print("OS INNSTILLINGER LAGRET")
        assert await h.config_entries.async_unload(os_entry.entry_id)

        # ---- egne ventiler, med hovedventil
        async def slaa_pa(call):
            ider = call.data["entity_id"]
            for eid in ider if isinstance(ider, list) else [ider]:
                h.states.async_set(eid, "on")

        h.services.async_register("homeassistant", "turn_on", slaa_pa)
        h.states.async_set("switch.bed", "off")
        h.states.async_set("switch.hovedventil", "off")
        v_entry = config_entries.ConfigEntry(
            version=1, minor_version=1, domain="ki_vanning", title="Ventiler",
            data={"modus": "ventiler", "soner": [{"entity": "switch.bed", "navn": "Bed"}],
                  "programmer": [], "varsel_til": ["mobile_app_test"], "master_ventil": "switch.hovedventil"},
            options={}, source="user", unique_id=None, discovery_keys={}, subentries_data=[])
        await asyncio.wait_for(h.config_entries.async_add(v_entry), 30)
        await h.async_block_till_done()
        assert v_entry.state == config_entries.ConfigEntryState.LOADED, v_entry.state
        egne = {e.entity_id for e in entity_registry.async_entries_for_config_entry(reg, v_entry.entry_id)}
        vb = sorted(e for e in egne if e.startswith("switch.") and ("varsel" in e or re.search(r"_varsler(_\d+)?$", e)))
        print("VENTIL-BRYTERE", vb)
        assert len(vb) == 4, vb                    # uten vannmåler: hoved + program, sone, regnpause
        h.states.async_set("switch.bed", "on")
        await h.async_block_till_done()
        assert h.states.get("switch.hovedventil").state == "on", "hovedventilen ble ikke åpnet"
        print("HOVEDVENTIL OK")
        h.states.async_set("switch.bed", "off")
        await h.async_block_till_done()
        meny = await h.config_entries.options.async_init(v_entry.entry_id)
        assert meny["type"] == "menu"
        skjema = await h.config_entries.options.async_configure(meny["flow_id"], {"next_step_id": "innstillinger"})
        assert skjema["step_id"] == "innstillinger", skjema
        lagret = await h.config_entries.options.async_configure(skjema["flow_id"], {"varsel_til": ["mobile_app_test"]})
        assert lagret["type"] == "create_entry", lagret
        print("VENTIL INNSTILLINGER LAGRET")
        # Lagringen starter integrasjonen på nytt; vent til den er oppe igjen.
        await h.async_block_till_done()
        assert v_entry.state == config_entries.ConfigEntryState.LOADED, v_entry.state
        assert await h.config_entries.async_unload(v_entry.entry_id)
        await h.async_stop(force=True)
        print("UNLOAD OK")


asyncio.run(main())
