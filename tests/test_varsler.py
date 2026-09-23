"""Tester for vanningsvarslene, bryterne og innstillingsskjemaet.

Kjøres med en ekte Home Assistant-instans (samme versjon som i drift). OpenSprinkler
er simulert med tilstander, og notify er en tjeneste som bare husker hva den fikk –
testene sjekker hva som ville blitt sendt til telefonen, ikke at telefonen fikk det.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.ki_vanning.coordinator import KiVanningMotor

P = "ute"


class Grunnlag(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.tmp.name)
        self.sendt = []

        async def notify(call):
            self.sendt.append({"til": call.service, **dict(call.data)})

        self.hass.services.async_register("notify", "mobile_app_iphone", notify)
        self.hass.services.async_register("notify", "mobile_app_pixel", notify)
        self.motorer = []

    async def asyncTearDown(self):
        for m in self.motorer:
            await m.stopp()
        await self.hass.async_block_till_done()
        await self.hass.async_stop(force=True)
        self.tmp.cleanup()

    def sett(self, eid, state, **attr):
        self.hass.states.async_set(eid, state, attr)

    async def opensprinkler(self, flow=True, **oppsett):
        for nr, navn in ((1, "Plen nord · Spreder B1"), (2, "Urtebed · Drypp B1")):
            slug = "plen_nord" if nr == 1 else "urtebed"
            self.sett(f"switch.{P}_s{nr:02d}_{slug}_station_enabled", "on",
                      friendly_name=f"S{nr:02d} {navn} Station Enabled")
            self.sett(f"binary_sensor.{P}_s{nr:02d}_{slug}_station_running", "off")
        self.sett(f"switch.{P}_morgen_program_enabled", "on", friendly_name="Morgen Program Enabled")
        self.sett(f"binary_sensor.{P}_morgen_program_running", "off")
        self.sett(f"binary_sensor.{P}_rain_delay_active", "off")
        if flow:
            self.sett("sensor.vannmaler", "0")
        m = KiVanningMotor(self.hass, {"modus": "opensprinkler", "prefiks": P,
                                       "flow": "sensor.vannmaler" if flow else "",
                                       "varsel_til": ["mobile_app_iphone", "notify.mobile_app_pixel"],
                                       **oppsett})
        await m.start()
        self.motorer.append(m)
        return m

    async def steg(self, m):
        """Én runde i motoren: mål, og la varslene se på tilstanden."""
        m._akkumuler()
        m._varsle()
        await self.hass.async_block_till_done()

    def titler(self):
        return [x["title"] for x in self.sendt]


class OpenSprinkler(Grunnlag):
    async def test_oppstart_midt_i_vanning_gir_ikke_varsel(self):
        self.sett(f"binary_sensor.{P}_morgen_program_running", "on")
        m = await self.opensprinkler()
        await self.steg(m)
        self.assertEqual(self.sendt, [])

    async def test_program_start_og_ferdig_til_begge_telefonene(self):
        m = await self.opensprinkler()
        await self.steg(m)
        self.sett(f"binary_sensor.{P}_morgen_program_running", "on")
        await self.steg(m)
        self.assertEqual(self.titler(), ["💧 Vanning startet"] * 2)
        self.assertEqual({x["til"] for x in self.sendt}, {"mobile_app_iphone", "mobile_app_pixel"})
        self.assertIn("Morgen", self.sendt[0]["message"])
        self.assertEqual(self.sendt[0]["data"]["tag"], "ki_vanning_program")
        self.sendt.clear()
        self.sett(f"binary_sensor.{P}_morgen_program_running", "off")
        await self.steg(m)
        self.assertEqual(self.titler(), ["✅ Vanning ferdig"] * 2)

    async def test_ferdig_har_liter_og_kroner_med_vannmaler(self):
        m = await self.opensprinkler(pris=41.11)
        await self.steg(m)
        self.sett(f"binary_sensor.{P}_morgen_program_running", "on")
        await self.steg(m)
        # 400 liter gjennom måleren mens programmet gikk
        m.soner[1].liter += 400
        self.sendt.clear()
        self.sett(f"binary_sensor.{P}_morgen_program_running", "off")
        await self.steg(m)
        tekst = self.sendt[0]["message"]
        self.assertIn("400 L", tekst)
        self.assertIn("16,44 kr", tekst)   # 0,4 m³ × 41,11

    async def test_uten_vannpris_star_ikke_kroner(self):
        m = await self.opensprinkler()
        await self.steg(m)
        self.sett(f"binary_sensor.{P}_morgen_program_running", "on")
        await self.steg(m)
        m.soner[1].liter += 400
        self.sendt.clear()
        self.sett(f"binary_sensor.{P}_morgen_program_running", "off")
        await self.steg(m)
        self.assertNotIn("kr", self.sendt[0]["message"])

    async def test_sone_er_av_som_standard_og_kan_slaas_pa(self):
        m = await self.opensprinkler()
        await self.steg(m)
        self.sett(f"binary_sensor.{P}_s01_plen_nord_station_running", "on")
        await self.steg(m)
        self.assertEqual(self.sendt, [])
        self.sett(f"binary_sensor.{P}_s01_plen_nord_station_running", "off")
        await self.steg(m)
        m.varsler.sett("sone", True)
        self.sett(f"binary_sensor.{P}_s02_urtebed_station_running", "on")
        await self.steg(m)
        self.assertEqual(self.titler()[0], "💧 Urtebed")

    async def test_regnpause_fra_opensprinkler(self):
        m = await self.opensprinkler()
        await self.steg(m)
        til = (dt_util.now() + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
        self.sett(f"sensor.{P}_rain_delay_stop_time", til.isoformat())
        self.sett(f"binary_sensor.{P}_rain_delay_active", "on")
        await self.steg(m)
        self.assertEqual(self.titler()[0], "🌧️ Regnpause")
        self.assertIn("i morgen kl. 07:00", self.sendt[0]["message"])
        self.sendt.clear()
        self.sett(f"binary_sensor.{P}_rain_delay_active", "off")
        await self.steg(m)
        self.assertEqual(self.titler()[0], "☀️ Regnpausen er over")

    async def test_hovedbryter_stopper_alt(self):
        m = await self.opensprinkler()
        await self.steg(m)
        m.varsler.sett("hoved", False)
        self.sett(f"binary_sensor.{P}_morgen_program_running", "on")
        await self.steg(m)
        self.assertEqual(self.sendt, [])

    async def test_vann_renner_uten_sone(self):
        m = await self.opensprinkler(varsel_vann_min=30)
        await self.steg(m)
        self.sett("sensor.vannmaler", "8")
        await self.steg(m)             # hageslangen starter
        self.assertIsNotNone(m.hageslange._start)
        m.hageslange._start = dt_util.utcnow() - timedelta(minutes=31)
        await self.steg(m)
        self.assertEqual(self.titler(), ["🚰 Vannet renner"] * 2)
        self.assertEqual(self.sendt[0]["data"]["push"]["interruption-level"], "time-sensitive")
        self.sendt.clear()
        await self.steg(m)             # bare én gang per gang vannet renner
        self.assertEqual(self.sendt, [])

    async def test_sone_uten_vannforing(self):
        m = await self.opensprinkler()
        await self.steg(m)
        self.sett(f"binary_sensor.{P}_s01_plen_nord_station_running", "on")
        await self.steg(m)
        m.soner[1]._start = dt_util.utcnow() - timedelta(minutes=4)
        await self.steg(m)
        self.assertEqual(self.titler(), ["⚠️ Ingen vannføring"] * 2)
        self.assertIn("Plen nord", self.sendt[0]["message"])

    async def test_uten_vannmaler_finnes_ikke_maalerbryterne(self):
        m = await self.opensprinkler(flow=False)
        self.assertNotIn("vann_renner", m.varsler.typer())
        self.assertNotIn("ingen_flyt", m.varsler.typer())
        self.assertIn("program", m.varsler.typer())

    async def test_bryterne_overlever_omstart(self):
        m = await self.opensprinkler()
        m.varsler.sett("sone", True)
        m.varsler.sett("regnpause", False)
        await m._skriv_lager()
        await m.stopp()
        self.motorer.remove(m)
        ny = await self.opensprinkler()
        self.assertTrue(ny.varsler.pa["sone"])
        self.assertFalse(ny.varsler.pa["regnpause"])

    async def test_uten_mottakere_sendes_ingenting_men_det_huskes(self):
        m = await self.opensprinkler(varsel_til=[])
        await self.steg(m)
        self.sett(f"binary_sensor.{P}_morgen_program_running", "on")
        await self.steg(m)
        self.assertEqual(self.sendt, [])
        self.assertIn("Vanning startet", m.varsler.sist_sendt)

    async def test_testknappen(self):
        m = await self.opensprinkler()
        m.varsler.test()
        await self.hass.async_block_till_done()
        self.assertTrue(self.sendt[0]["title"].startswith("TEST:"))


class EgneVentiler(Grunnlag):
    async def ventiler(self):
        for eid in ("switch.bed", "switch.hekk"):
            self.sett(eid, "off", friendly_name=eid)

        # Ventilene slås av og på med homeassistant.turn_on/turn_off, som ikke finnes
        # i en tom testinstans. Her gjør de det en bryter ville gjort.
        async def slaa(call, pa):
            for eid in call.data["entity_id"] if isinstance(call.data["entity_id"], list) else [call.data["entity_id"]]:
                self.sett(eid, "on" if pa else "off", friendly_name=eid)

        async def pa(call):
            await slaa(call, True)

        async def av(call):
            await slaa(call, False)

        self.hass.services.async_register("homeassistant", "turn_on", pa)
        self.hass.services.async_register("homeassistant", "turn_off", av)
        m = KiVanningMotor(self.hass, {
            "modus": "ventiler",
            "soner": [{"entity": "switch.bed", "navn": "Bed"}, {"entity": "switch.hekk", "navn": "Hekk"}],
            "programmer": [{"navn": "Kveld", "tid": "20:00", "dager": ["man"],
                            "soner": [{"entity": "switch.bed", "min": 10}, {"entity": "switch.hekk", "min": 5}]}],
            "varsel_til": ["mobile_app_iphone"],
        })
        await m.start()
        self.motorer.append(m)
        return m

    async def test_program_gjennom_planleggeren(self):
        m = await self.ventiler()
        await self.steg(m)
        await m.kjor_program("Kveld")
        await self.hass.async_block_till_done()
        self.assertEqual(self.hass.states.get("switch.bed").state, "on")   # ventilen gikk faktisk på
        self.assertEqual(self.titler()[0], "💧 Vanning startet")
        self.assertIn("Kveld · 2 soner · ca. 15 min", self.sendt[0]["message"])
        self.sendt.clear()
        await m.stopp_alt()
        await self.hass.async_block_till_done()
        self.assertEqual(self.titler()[0], "✅ Vanning ferdig")

    async def test_regnpause_fra_planleggeren(self):
        m = await self.ventiler()
        await self.steg(m)
        m.sett_regnpause(24)
        await self.hass.async_block_till_done()
        self.assertEqual(self.titler()[0], "🌧️ Regnpause")
        self.sendt.clear()
        m.sett_regnpause(0)
        await self.hass.async_block_till_done()
        self.assertEqual(self.titler()[0], "☀️ Regnpausen er over")


class Innstillinger(Grunnlag):
    async def _flyt(self, modus):
        from custom_components.ki_vanning.config_flow import KiVanningOptions
        from types import SimpleNamespace
        entry = SimpleNamespace(data={"modus": modus, "prefiks": P}, options={})
        f = KiVanningOptions(entry)
        f.hass = self.hass
        f.handler = "ki_vanning"
        f.flow_id = "test"
        return f

    async def test_opensprinkler_lagrer_skjemaet(self):
        """Skjemaet ble vist på nytt i stedet for å lagres, fordi svaret ikke ble sendt videre."""
        f = await self._flyt("opensprinkler")
        vist = await f.async_step_init()
        self.assertEqual(vist["type"], "form")
        self.assertEqual(vist["step_id"], "innstillinger")
        lagret = await f.async_step_innstillinger({"pris": 40.0, "varsel_til": ["mobile_app_iphone"],
                                                    "varsel_vann_min": 45})
        self.assertEqual(lagret["type"], "create_entry")
        self.assertEqual(lagret["data"]["varsel_til"], ["mobile_app_iphone"])
        self.assertEqual(lagret["data"]["varsel_vann_min"], 45)
        # og veien skjemaet faktisk går: innsendingen kommer til init
        via_init = await f.async_step_init({"pris": 39.0})
        self.assertEqual(via_init["type"], "create_entry")

    async def test_ventiler_lagrer_skjemaet(self):
        f = await self._flyt("ventiler")
        meny = await f.async_step_init()
        self.assertEqual(meny["type"], "menu")
        vist = await f.async_step_innstillinger()
        self.assertEqual(vist["step_id"], "innstillinger")
        lagret = await f.async_step_innstillinger({"varsel_til": ["mobile_app_pixel"]})
        self.assertEqual(lagret["type"], "create_entry")

    async def test_mottakerlista_er_notify_tjenestene(self):
        f = await self._flyt("opensprinkler")
        vist = await f.async_step_init()
        felt = {str(k): v for k, v in vist["data_schema"].schema.items()}
        valg = felt["varsel_til"].config["options"]
        self.assertIn("mobile_app_iphone", valg)
        self.assertIn("mobile_app_pixel", valg)


if __name__ == "__main__":
    unittest.main()
