"""Motoren i KI Vanning.

Fordeler vannmålerens flow på den sonen som kjører, fører forbruk og kjøretid per
sone, regner ut kalibrert L/min, kostnad, estimat for dagens program og neste
vanning. Alt bygger på entitetene fra OpenSprinkler-integrasjonen pluss én
flow-sensor, slik at ingenting må settes opp manuelt.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import async_timeout

from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_INTEGRASJON,
    DOMAIN,
    LAGER_NOKKEL,
    LAGER_VERSJON,
    PERIODER,
    STD_FALLBACK_RATE,
)

_LOGGER = logging.getLogger(__name__)

TIKK = timedelta(seconds=30)
PLAN_INTERVALL = timedelta(minutes=5)

UKEDAGER = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]


@dataclass
class Sone:
    """En OpenSprinkler-sone med tallene vi fører for den."""

    nr: int
    slug: str
    navn: str
    metode: str = ""
    boks: str = ""
    bryter: str = ""
    gaar: str = ""
    status: str = ""
    liter: float = 0.0
    minutter: float = 0.0
    perioder: dict[str, float] = field(default_factory=lambda: {p: 0.0 for p in PERIODER})
    min_perioder: dict[str, float] = field(default_factory=lambda: {p: 0.0 for p in PERIODER})
    siste_liter: float = 0.0
    siste_minutter: float = 0.0
    siste_slutt: str | None = None
    _start: datetime | None = None
    _start_liter: float = 0.0
    _start_min: float = 0.0

    @property
    def rate(self) -> float:
        """Kalibrert L/min: faktisk forbruk delt på faktisk kjøretid."""
        if self.minutter > 2:
            return round(self.liter / self.minutter, 2)
        return 0.0


class KiVanningMotor:
    """Holder tallene, lytter på entitetene og henter programplanen."""

    def __init__(self, hass: HomeAssistant, oppsett: dict[str, Any]) -> None:
        self.hass = hass
        self.oppsett = oppsett
        self.soner: dict[int, Sone] = {}
        self.hageslange = Sone(nr=0, slug="hageslange", navn="Hageslange", metode="Slange")
        self.planlagt: list[dict[str, Any]] = []
        self.neste: dict[str, Any] | None = None
        self.plan_feil: str | None = None
        self._lytter: list[Any] = []
        self._sist: datetime | None = None
        self._anker: dict[str, str] = {}
        self._lager = Store(hass, LAGER_VERSJON, f"{LAGER_NOKKEL}_{oppsett.get('prefiks','os')}")
        self._lyttere: list[Any] = []

    # ------------------------------------------------------------------ oppsett
    async def start(self) -> None:
        await self._les_lager()
        self._finn_soner()
        self._lytter.append(async_track_time_interval(self.hass, self._tikk, TIKK))
        self._lytter.append(async_track_time_interval(self.hass, self._hent_plan, PLAN_INTERVALL))
        fulgte = [self.oppsett["flow"]] + [s.gaar for s in self.soner.values()]
        self._lytter.append(async_track_state_change_event(self.hass, fulgte, self._endring))
        await self._hent_plan(None)

    async def stopp(self) -> None:
        for av in self._lytter:
            av()
        self._lytter.clear()
        await self._skriv_lager()

    def abonner(self, cb) -> Any:
        """Entitetene melder seg på her og oppdateres når tallene endrer seg."""
        self._lyttere.append(cb)

        def av() -> None:
            if cb in self._lyttere:
                self._lyttere.remove(cb)

        return av

    def _varsle(self) -> None:
        for cb in list(self._lyttere):
            cb()

    # ------------------------------------------------------------------ soner
    def _finn_soner(self) -> None:
        """Leser sonene rett ut av OpenSprinkler-entitetene."""
        pref = self.oppsett["prefiks"]
        moenster = re.compile(rf"^switch\.{re.escape(pref)}_s(\d\d)(.*)_station_enabled$")
        for eid in self.hass.states.async_entity_ids("switch"):
            traff = moenster.match(eid)
            if not traff:
                continue
            nr, hale = int(traff.group(1)), traff.group(2)
            st = self.hass.states.get(eid)
            fn = (st.attributes.get("friendly_name") or "") if st else ""
            tekst = re.sub(r"^S\d\d\s*", "", fn)
            tekst = re.sub(r"\s*Station Enabled$", "", tekst, flags=re.I).strip()
            ubrukt = not tekst or re.fullmatch(r"S?\d+", tekst) is not None
            deler = [d.strip() for d in tekst.split("·")]
            navn = deler[0] if deler and deler[0] else f"Sone {nr:02d}"
            metode = deler[1] if len(deler) > 1 else ""
            boks = ""
            if m := re.search(r"B(\d)", metode or tekst, re.I):
                boks = m.group(1)
            slug = re.sub(r"[^a-z0-9]+", "_", navn.lower().replace("ø", "o").replace("æ", "a").replace("å", "a")).strip("_")
            if ubrukt:
                continue
            gammel = self.soner.get(nr)
            sone = gammel or Sone(nr=nr, slug=slug, navn=navn)
            sone.navn, sone.metode, sone.boks, sone.slug = navn, metode, boks, slug
            sone.bryter = eid
            sone.gaar = f"binary_sensor.{pref}_s{nr:02d}{hale}_station_running"
            sone.status = f"sensor.{pref}_s{nr:02d}{hale}_station_status"
            self.soner[nr] = sone
        _LOGGER.debug("KI Vanning fant %s soner", len(self.soner))

    def alle(self) -> list[Sone]:
        return [self.soner[n] for n in sorted(self.soner)] + [self.hageslange]

    def aktiv(self) -> Sone | None:
        for s in self.soner.values():
            st = self.hass.states.get(s.gaar)
            if st and st.state == "on":
                return s
        return None

    def _flow(self) -> float:
        st = self.hass.states.get(self.oppsett["flow"])
        try:
            v = float(st.state) if st else 0.0
        except (TypeError, ValueError):
            return 0.0
        return v if v >= self.oppsett.get("min_flow", 0.3) else 0.0

    # ------------------------------------------------------------------ måling
    @callback
    def _endring(self, hendelse) -> None:
        self._akkumuler()
        self._varsle()

    @callback
    def _tikk(self, _nå) -> None:
        self._akkumuler()
        self._varsle()
        self.hass.async_create_task(self._skriv_lager())

    def _akkumuler(self) -> None:
        """Legger til liter og minutter siden forrige gang, på riktig sone."""
        nå = dt_util.utcnow()
        self._nullstill_perioder()
        if self._sist is None:
            self._sist = nå
            return
        minutter = (nå - self._sist).total_seconds() / 60
        self._sist = nå
        if minutter <= 0 or minutter > 10:      # hopp over lange pauser (omstart)
            return
        flow = self._flow()
        sone = self.aktiv()
        mål = sone or (self.hageslange if flow > 0 else None)
        if mål is None:
            self._avslutt_kjoringer(None)
            return
        liter = flow * minutter
        mål.liter += liter
        for p in PERIODER:
            mål.perioder[p] += liter
        if sone is not None or flow > 0:
            mål.minutter += minutter
            for p in PERIODER:
                mål.min_perioder[p] += minutter
        self._avslutt_kjoringer(mål)

    def _avslutt_kjoringer(self, aktiv: Sone | None) -> None:
        """Fører «siste kjøring» når en sone stopper."""
        for s in list(self.soner.values()) + [self.hageslange]:
            kjorer = s is aktiv
            if kjorer and s._start is None:
                s._start = dt_util.utcnow()
                s._start_liter, s._start_min = s.liter, s.minutter
            elif not kjorer and s._start is not None:
                s.siste_liter = round(s.liter - s._start_liter, 1)
                s.siste_minutter = round(s.minutter - s._start_min, 1)
                s.siste_slutt = dt_util.now().isoformat(timespec="minutes")
                s._start = None

    def _nullstill_perioder(self) -> None:
        """Nullstiller dag, uke, måned og år når perioden er over."""
        nå = dt_util.now()
        anker = {
            "i_dag": nå.strftime("%Y-%m-%d"),
            "uke": f"{nå.isocalendar().year}-{nå.isocalendar().week}",
            "maaned": nå.strftime("%Y-%m"),
            "aar": nå.strftime("%Y"),
        }
        for p, verdi in anker.items():
            if self._anker.get(p) != verdi:
                if self._anker.get(p) is not None:
                    for s in list(self.soner.values()) + [self.hageslange]:
                        s.perioder[p] = 0.0
                        s.min_perioder[p] = 0.0
                self._anker[p] = verdi

    # ------------------------------------------------------------------ tall ut
    def pris(self) -> float:
        return float(self.oppsett.get("pris") or 0)

    def kostnad(self, liter: float) -> float:
        return round(liter / 1000 * self.pris(), 2)

    def total(self, felt: str = "liter", periode: str | None = None) -> float:
        soner = list(self.soner.values()) + [self.hageslange]
        if periode:
            kilde = "perioder" if felt == "liter" else "min_perioder"
            return round(sum(getattr(s, kilde)[periode] for s in soner), 1)
        return round(sum(getattr(s, felt) for s in soner), 1)

    def rate(self, sone: Sone) -> float:
        """Kalibrert rate, ellers målt flow, ellers standardverdi."""
        if sone.rate > 0:
            return sone.rate
        flow = self._flow()
        return round(flow, 2) if flow > 0 else STD_FALLBACK_RATE

    # ------------------------------------------------------------------ lagring
    async def _les_lager(self) -> None:
        data = await self._lager.async_load() or {}
        self._anker = data.get("anker", {})
        for rad in data.get("soner", []):
            nr = rad.get("nr")
            s = self.hageslange if nr == 0 else self.soner.get(nr) or Sone(nr=nr, slug=rad.get("slug", ""), navn=rad.get("navn", ""))
            s.liter = rad.get("liter", 0.0)
            s.minutter = rad.get("minutter", 0.0)
            s.perioder.update(rad.get("perioder", {}))
            s.min_perioder.update(rad.get("min_perioder", {}))
            s.siste_liter = rad.get("siste_liter", 0.0)
            s.siste_minutter = rad.get("siste_minutter", 0.0)
            s.siste_slutt = rad.get("siste_slutt")
            if nr:
                self.soner[nr] = s

    async def _skriv_lager(self) -> None:
        await self._lager.async_save(
            {
                "anker": self._anker,
                "soner": [
                    {
                        "nr": s.nr, "slug": s.slug, "navn": s.navn,
                        "liter": round(s.liter, 2), "minutter": round(s.minutter, 2),
                        "perioder": {k: round(v, 2) for k, v in s.perioder.items()},
                        "min_perioder": {k: round(v, 2) for k, v in s.min_perioder.items()},
                        "siste_liter": s.siste_liter, "siste_minutter": s.siste_minutter,
                        "siste_slutt": s.siste_slutt,
                    }
                    for s in list(self.soner.values()) + [self.hageslange]
                ],
            }
        )

    async def nullstill(self, hva: str = "alt") -> None:
        """Nullstiller tellerne – brukes av knappene."""
        for s in list(self.soner.values()) + [self.hageslange]:
            if hva in ("alt", "forbruk"):
                s.liter = 0.0
                s.perioder = {p: 0.0 for p in PERIODER}
            if hva in ("alt", "kalibrering"):
                s.minutter = 0.0
                s.min_perioder = {p: 0.0 for p in PERIODER}
        await self._skriv_lager()
        self._varsle()

    # ------------------------------------------------------------------ plan
    async def _hent_plan(self, _nå) -> None:
        """Leser programmene fra OpenSprinkler (/jp) og regner ut dagens plan."""
        vert, passord = self.oppsett.get("host"), self.oppsett.get("passord")
        if not vert:
            self._plan_fra_kalender()
            return
        url = f"http://{vert}/jp?pw={passord or ''}"
        try:
            økt = aiohttp.ClientSession()
            async with async_timeout.timeout(10):
                async with økt.get(url) as svar:
                    data = await svar.json(content_type=None)
        except Exception as feil:  # noqa: BLE001 – vi vil bare vite at det gikk galt
            self.plan_feil = str(feil)
            _LOGGER.debug("KI Vanning: klarte ikke hente /jp: %s", feil)
            self._plan_fra_kalender()
            return
        finally:
            try:
                await økt.close()
            except Exception:  # noqa: BLE001
                pass
        self.plan_feil = None
        self._tolk_plan(data.get("pd") or [])
        self._varsle()

    def _navn_liste(self) -> list[str]:
        """Sonenavn i stasjonsrekkefølge, slik OpenSprinkler teller dem."""
        ut: list[str] = []
        for nr in range(1, 33):
            s = self.soner.get(nr)
            ut.append(s.navn if s else f"Sone {nr:02d}")
        return ut

    @staticmethod
    def _ukeprogram(flagg: int) -> bool:
        """Aktivt ukeprogram (ikke intervall eller soltid)."""
        stype = ((flagg // 16) % 2) + (((flagg // 32) % 2) * 2)
        return bool(flagg % 2 == 1 and stype == 0)

    def _tolk_plan(self, pd: list) -> None:
        navn = self._navn_liste()
        idag = dt_util.now()
        bit = 2 ** idag.weekday()
        programmer: list[dict[str, Any]] = []
        for p in pd:
            try:
                flagg, dager, _, start, varigheter = int(p[0]), int(p[1]), p[2], p[3], p[4]
                pnavn = p[5] if len(p) > 5 else "Program"
            except (IndexError, TypeError, ValueError):
                continue
            if not self._ukeprogram(flagg):
                continue
            soner = [
                {"navn": navn[i], "min": int(v) // 60, "nr": i + 1}
                for i, v in enumerate(varigheter)
                if int(v or 0) > 0
            ]
            if not soner:
                continue
            st = int(start[0]) if isinstance(start, list) else int(start)
            tid = f"{st // 60:02d}:{st % 60:02d}" if 0 <= st < 1440 else "––"
            rad = {
                "navn": pnavn, "tid": tid, "start_min": st, "dager": dager,
                "soner": soner, "total_min": sum(z["min"] for z in soner),
            }
            rad["estimat_liter"] = round(sum(z["min"] * self.rate(self.soner.get(z["nr"], self.hageslange)) for z in soner))
            rad["i_dag"] = bool((dager // bit) % 2 == 1)
            programmer.append(rad)
        self.planlagt = programmer
        self._finn_neste(programmer, idag)

    def _finn_neste(self, programmer: list[dict[str, Any]], nå: datetime) -> None:
        """Første programstart fra og med nå, opptil en uke fram."""
        best: dict[str, Any] | None = None
        nå_min = nå.hour * 60 + nå.minute
        for dag in range(8):
            ukedag = (nå.weekday() + dag) % 7
            bit = 2 ** ukedag
            for p in programmer:
                if (p["dager"] // bit) % 2 != 1 or p["start_min"] < 0:
                    continue
                if dag == 0 and p["start_min"] <= nå_min:
                    continue
                naar = "I dag" if dag == 0 else "I morgen" if dag == 1 else UKEDAGER[ukedag]
                kandidat = {
                    "naar": naar, "tid": p["tid"], "navn": p["navn"], "dager_fram": dag,
                    "minutter_til": dag * 1440 + p["start_min"] - nå_min,
                    "soner": p["soner"], "total_min": p["total_min"], "estimat_liter": p["estimat_liter"],
                }
                if best is None or kandidat["minutter_til"] < best["minutter_til"]:
                    best = kandidat
            if best is not None:
                break
        self.neste = best

    def _plan_fra_kalender(self) -> None:
        """Uten OpenSprinkler-adresse brukes kalenderen fra integrasjonen."""
        st = self.hass.states.get("calendar.opensprinkler_schedule")
        if not st:
            return
        start = st.attributes.get("start_time")
        if start:
            self.neste = {
                "naar": "Neste", "tid": str(start)[11:16], "navn": st.attributes.get("message", "Program"),
                "dager_fram": 0, "minutter_til": 0, "soner": [], "total_min": 0, "estimat_liter": 0,
            }

    # ------------------------------------------------------------------ estimat
    def dagens_programmer(self) -> list[dict[str, Any]]:
        return [p for p in self.planlagt if p.get("i_dag")]

    def estimat_i_dag(self) -> dict[str, Any]:
        """Estimert forbruk for dagens programmer, kalibrert per sone."""
        rader: list[dict[str, Any]] = []
        sum_liter = 0.0
        for p in self.dagens_programmer():
            for z in p["soner"]:
                sone = self.soner.get(z["nr"])
                rate = self.rate(sone) if sone else STD_FALLBACK_RATE
                liter = z["min"] * rate
                sum_liter += liter
                rader.append({
                    "program": p["navn"], "sone": z["navn"], "minutter": z["min"],
                    "liter": round(liter), "rate": round(rate, 2),
                    "kalibrert": bool(sone and sone.rate > 0),
                })
        return {"liter": round(sum_liter), "kostnad": self.kostnad(sum_liter), "per_sone": rader}
