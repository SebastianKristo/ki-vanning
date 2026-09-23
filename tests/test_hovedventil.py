"""Tester for hovedventilen.

Sonoff-ventilen stenger seg selv når det ikke har gått vann på en stund. Testene sjekker
at KI Vanning åpner den hver gang en sone starter – i begge modiene, og uansett om
sonen startes av et program eller for hånd – og at den ikke havner i en løkke.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.core import HomeAssistant

import custom_components.ki_vanning.coordinator as koordinator
from custom_components.ki_vanning.coordinator import KiVanningMotor

P = "ute"


class Grunnlag(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.tmp.name)
        self.kall = []          # (tjeneste, entity) i den rekkefølgen de kom

        async def pa(call):
            for eid in self._ider(call):
                self.kall.append(("pa", eid))
                self.hass.states.async_set(eid, "on")

        async def av(call):
            for eid in self._ider(call):
                self.kall.append(("av", eid))
                self.hass.states.async_set(eid, "off")

        async def apne(call):
            for eid in self._ider(call):
                self.kall.append(("open_valve", eid))
                self.hass.states.async_set(eid, "open")

        async def lukk(call):
            for eid in self._ider(call):
                self.kall.append(("close_valve", eid))
                self.hass.states.async_set(eid, "closed")

        self.hass.services.async_register("homeassistant", "turn_on", pa)
        self.hass.services.async_register("homeassistant", "turn_off", av)
        self.hass.services.async_register("valve", "open_valve", apne)
        self.hass.services.async_register("valve", "close_valve", lukk)
        self.motorer = []

    @staticmethod
    def _ider(call):
        e = call.data["entity_id"]
        return e if isinstance(e, list) else [e]

    async def asyncTearDown(self):
        for m in self.motorer:
            await m.stopp()
        await self.hass.async_block_till_done()
        await self.hass.async_stop(force=True)
        self.tmp.cleanup()

    async def ventiler(self, **oppsett):
        for eid in ("switch.bed", "switch.hekk"):
            self.hass.states.async_set(eid, "off")
        self.hass.states.async_set("switch.hovedventil", "off")
        self.hass.states.async_set("valve.hovedventil", "closed")
        m = KiVanningMotor(self.hass, {
            "modus": "ventiler",
            "soner": [{"entity": "switch.bed", "navn": "Bed"}, {"entity": "switch.hekk", "navn": "Hekk"}],
            "programmer": [{"navn": "Kveld", "tid": "20:00", "dager": ["man"],
                            "soner": [{"entity": "switch.bed", "min": 10}, {"entity": "switch.hekk", "min": 5}]}],
            "master_ventil": "switch.hovedventil", **oppsett})
        await m.start()
        self.motorer.append(m)
        await self.hass.async_block_till_done()
        return m


class EgneVentiler(Grunnlag):
    async def test_hovedventilen_apnes_for_sonen(self):
        m = await self.ventiler()
        await m.kjor_program("Kveld")
        await self.hass.async_block_till_done()
        rekkefolge = [e for _, e in self.kall]
        self.assertLess(rekkefolge.index("switch.hovedventil"), rekkefolge.index("switch.bed"))
        self.assertEqual(self.hass.states.get("switch.hovedventil").state, "on")

    async def test_ogsa_ved_neste_sone_i_programmet(self):
        """Ventilen kan ha stengt seg selv mellom to soner."""
        m = await self.ventiler()
        await m.kjor_program("Kveld")
        await self.hass.async_block_till_done()
        self.hass.states.async_set("switch.hovedventil", "off")   # stengte seg selv
        self.kall.clear()
        await m.plan._avslutt()                                    # første sone ferdig → neste
        await self.hass.async_block_till_done()
        rekkefolge = [e for h, e in self.kall if h == "pa"]
        self.assertEqual(rekkefolge[:2], ["switch.hovedventil", "switch.hekk"])

    async def test_sone_slatt_pa_for_hand(self):
        m = await self.ventiler()
        self.hass.states.async_set("switch.hekk", "on")            # rett i HA, ikke via KI Vanning
        await self.hass.async_block_till_done()
        self.assertIn(("pa", "switch.hovedventil"), self.kall)

    async def test_apnes_igjen_bare_en_gang(self):
        m = await self.ventiler()
        self.hass.states.async_set("switch.bed", "on")
        await self.hass.async_block_till_done()
        self.kall.clear()
        self.hass.states.async_set("switch.hovedventil", "off")    # stengte midt i
        await self.hass.async_block_till_done()
        self.assertEqual(self.kall.count(("pa", "switch.hovedventil")), 1)
        self.kall.clear()
        self.hass.states.async_set("switch.hovedventil", "off")    # stenger igjen
        await self.hass.async_block_till_done()
        self.assertEqual(self.kall, [], "ingen løkke: andre gang får den stå")

    async def test_valve_domenet_bruker_open_valve(self):
        m = await self.ventiler(master_ventil="valve.hovedventil")
        self.hass.states.async_set("switch.bed", "on")
        await self.hass.async_block_till_done()
        self.assertIn(("open_valve", "valve.hovedventil"), self.kall)
        self.assertEqual(self.hass.states.get("valve.hovedventil").state, "open")

    async def test_steng_nar_ferdig(self):
        koordinator.MASTER_STENG_SEK = 0.05
        try:
            m = await self.ventiler(master_steng=True)
            self.hass.states.async_set("switch.bed", "on")
            await self.hass.async_block_till_done()
            self.hass.states.async_set("switch.bed", "off")
            await self.hass.async_block_till_done()
            await asyncio.sleep(0.2)
            await self.hass.async_block_till_done()
            self.assertIn(("av", "switch.hovedventil"), self.kall)
        finally:
            koordinator.MASTER_STENG_SEK = 15

    async def test_ikke_stengt_nar_neste_sone_folger(self):
        koordinator.MASTER_STENG_SEK = 0.05
        try:
            m = await self.ventiler(master_steng=True)
            self.hass.states.async_set("switch.bed", "on")
            await self.hass.async_block_till_done()
            self.hass.states.async_set("switch.bed", "off")
            self.hass.states.async_set("switch.hekk", "on")        # neste sone rett etter
            await self.hass.async_block_till_done()
            await asyncio.sleep(0.2)
            await self.hass.async_block_till_done()
            self.assertNotIn(("av", "switch.hovedventil"), self.kall)
        finally:
            koordinator.MASTER_STENG_SEK = 15

    async def test_uten_hovedventil_skjer_ingenting_ekstra(self):
        m = await self.ventiler(master_ventil="")
        self.hass.states.async_set("switch.bed", "on")
        await self.hass.async_block_till_done()
        self.assertNotIn("switch.hovedventil", [e for _, e in self.kall])


class OpenSprinkler(Grunnlag):
    async def test_stasjon_som_starter_apner_hovedventilen(self):
        self.hass.states.async_set(f"switch.{P}_s01_plen_station_enabled", "on",
                                   {"friendly_name": "S01 Plen Station Enabled"})
        self.hass.states.async_set(f"binary_sensor.{P}_s01_plen_station_running", "off")
        self.hass.states.async_set("switch.hovedventil", "off")
        m = KiVanningMotor(self.hass, {"modus": "opensprinkler", "prefiks": P,
                                       "master_ventil": "switch.hovedventil"})
        await m.start()
        self.motorer.append(m)
        self.hass.states.async_set(f"binary_sensor.{P}_s01_plen_station_running", "on")
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get("switch.hovedventil").state, "on")


if __name__ == "__main__":
    unittest.main()
