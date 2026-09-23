"""Varsler fra KI Vanning.

Én modul for begge modiene – OpenSprinkler og egne ventiler. I stedet for å hekte
seg inn i hver av dem, ser varslene på *tilstanden* motoren alt holder styr på, og
sammenligner med forrige gang: hvilket program går, hvilken sone vanner, er det
regnpause, renner det vann uten at noen sone går. Endringene blir varsler.

Motoren kaller `sjekk()` hver gang den oppdaterer entitetene – ved hver endring i
sonene og hvert 30. sekund. Første sjekk etter oppstart setter bare utgangspunktet:
en omstart midt i en vanning skal ikke gi et «vanning startet».

Hver varseltype har sin egen bryter, pluss en hovedbryter. Bryterne lagres sammen
med forbruket, så de overlever omstart.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# nøkkel → (navn på bryteren, på som standard, krever vannmåler)
VARSELTYPER: dict[str, tuple[str, bool, bool]] = {
    "program": ("Varsel program", True, False),
    "sone": ("Varsel hver sone", False, False),
    "regnpause": ("Varsel regnpause", True, False),
    "vann_renner": ("Varsel vann renner", True, True),
    "ingen_flyt": ("Varsel ingen vannføring", True, True),
}

STD_VANN_RENNER_MIN = 30      # så lenge vann kan renne uten sone før vi sier fra
INGEN_FLYT_MIN = 3            # så lenge en sone kan gå uten vann før vi sier fra


def _kl(t: datetime | None) -> str:
    return dt_util.as_local(t).strftime("%H:%M") if t else ""


def _naar(t: datetime | None) -> str:
    """«i dag kl. 07:00», «i morgen kl. 07:00», ellers dato."""
    if not t:
        return ""
    lokal = dt_util.as_local(t)
    dager = (lokal.date() - dt_util.now().date()).days
    if dager == 0:
        return f"i dag kl. {lokal:%H:%M}"
    if dager == 1:
        return f"i morgen kl. {lokal:%H:%M}"
    return f"{lokal:%d.%m} kl. {lokal:%H:%M}"


def _minutter(m: float) -> str:
    m = round(m)
    return f"{m // 60} t {m % 60} min" if m >= 60 else f"{m} min"


class Varsler:
    def __init__(self, motor) -> None:
        self.motor = motor
        self.hass = motor.hass
        self.pa: dict[str, bool] = {"hoved": True, **{k: v[1] for k, v in VARSELTYPER.items()}}
        self._forrige: dict[str, Any] | None = None
        self._program_start: dict[str, tuple[datetime, float]] = {}
        self._vann_renner_sendt = False
        self._ingen_flyt_sendt: set[int] = set()
        self.sist_sendt: str | None = None

    # ------------------------------------------------------------ oppsett
    @property
    def mottakere(self) -> list[str]:
        rå = self.motor.oppsett.get("varsel_til") or []
        if isinstance(rå, str):
            rå = [x.strip() for x in rå.split(",") if x.strip()]
        return [x.replace("notify.", "") for x in rå]

    @property
    def vann_renner_min(self) -> float:
        try:
            return float(self.motor.oppsett.get("varsel_vann_min") or STD_VANN_RENNER_MIN)
        except (TypeError, ValueError):
            return STD_VANN_RENNER_MIN

    def typer(self) -> list[str]:
        """Varseltypene som gir mening for dette anlegget."""
        flyt = self.motor.har_flyt
        return [k for k, v in VARSELTYPER.items() if flyt or not v[2]]

    def les(self, lagret: dict[str, Any] | None) -> None:
        for k, v in (lagret or {}).items():
            if k in self.pa:
                self.pa[k] = bool(v)

    def lagre(self) -> dict[str, bool]:
        return dict(self.pa)

    def sett(self, nokkel: str, pa: bool) -> None:
        self.pa[nokkel] = pa
        self.motor._varsle()
        self.hass.async_create_task(self.motor._skriv_lager())

    def paa(self, nokkel: str) -> bool:
        return self.pa.get("hoved", True) and self.pa.get(nokkel, False)

    # ------------------------------------------------------------ tilstand
    def _program_naa(self) -> str | None:
        """Programmet som kjører nå, i begge modiene."""
        m = self.motor
        if m.plan:
            p = m.plan
            if p.naa and p.naa.program:
                return p.naa.program
            for j in getattr(p, "parallelle", []) or []:
                if j.program:
                    return j.program
            # Mellom to soner i samme program står naa tom et øyeblikk, men køen
            # har fortsatt resten. Da går programmet fortsatt.
            for j in p.koe:
                if j.program:
                    return j.program
            return None
        for prog in m.programmer.values():
            st = self.hass.states.get(prog.gaar)
            if st and st.state == "on":
                return prog.navn
        return None

    def _regnpause(self) -> tuple[bool, datetime | None]:
        m = self.motor
        if m.plan:
            return m.plan.regnpause_aktiv, m.plan.regnpause_til
        p = m.oppsett.get("prefiks")
        if not p:
            return False, None
        st = self.hass.states.get(f"binary_sensor.{p}_rain_delay_active")
        til = self.hass.states.get(f"sensor.{p}_rain_delay_stop_time")
        slutt = dt_util.parse_datetime(til.state) if til and til.state not in ("unknown", "unavailable") else None
        return bool(st and st.state == "on"), slutt

    def _tilstand(self) -> dict[str, Any]:
        aktiv = self.motor.aktiv()
        regn, regn_til = self._regnpause()
        return {
            "program": self._program_naa(),
            "sone": aktiv.nr if aktiv else None,
            "regn": regn,
            "regn_til": regn_til,
        }

    # ------------------------------------------------------------ sjekk
    def sjekk(self) -> None:
        naa = self._tilstand()
        forrige = self._forrige
        self._forrige = naa
        if forrige is None:
            # Utgangspunkt. Kjører det noe ved oppstart, merkes det som startet nå,
            # så et «ferdig» senere får fornuftige tall – men det sendes ikke varsel.
            if naa["program"]:
                self._program_start[naa["program"]] = (dt_util.utcnow(), self.motor.total("liter"))
            return

        # --- program
        if naa["program"] != forrige["program"]:
            if forrige["program"]:
                self._program_ferdig(forrige["program"])
            if naa["program"]:
                self._program_startet(naa["program"])

        # --- sone
        if naa["sone"] != forrige["sone"]:
            if forrige["sone"] is not None:
                self._ingen_flyt_sendt.discard(forrige["sone"])
                self._sone_ferdig(forrige["sone"])
            if naa["sone"] is not None:
                self._sone_startet(naa["sone"])

        # --- regnpause
        if naa["regn"] != forrige["regn"]:
            self._regnpause_endret(naa["regn"], naa["regn_til"])

        self._sjekk_vann_renner()
        self._sjekk_ingen_flyt()

    # ------------------------------------------------------------ program
    def _program_startet(self, navn: str) -> None:
        self._program_start[navn] = (dt_util.utcnow(), self.motor.total("liter"))
        if not self.paa("program"):
            return
        detaljer = self._programdetaljer(navn)
        self.send("💧 Vanning startet", f"{navn}{detaljer}.", "program", ikon="mdi:sprinkler-variant")

    def _programdetaljer(self, navn: str) -> str:
        """«· 3 soner · ca. 40 min» ut fra det vi vet om programmet."""
        m = self.motor
        soner, minutter = 0, 0.0
        if m.plan:
            prog = next((p for p in m.plan.programmer if p.navn.lower() == navn.lower()), None)
            if prog:
                soner, minutter = len(prog.soner), prog.total_min
        else:
            prog = m._program_for(navn) if hasattr(m, "_program_for") else None
            if prog:
                soner, minutter = len(prog.soner), prog.total_min
        deler = []
        if soner:
            deler.append(f"{soner} {'sone' if soner == 1 else 'soner'}")
        if minutter:
            deler.append(f"ca. {_minutter(minutter)}")
        return (" · " + " · ".join(deler)) if deler else ""

    def _program_ferdig(self, navn: str) -> None:
        start = self._program_start.pop(navn, None)
        if not self.paa("program"):
            return
        deler = [navn]
        if start:
            varighet = (dt_util.utcnow() - start[0]).total_seconds() / 60
            if varighet >= 1:
                deler.append(_minutter(varighet))
            if self.motor.har_flyt:
                liter = self.motor.total("liter") - start[1]
                if liter >= 1:
                    deler.append(f"{round(liter)} L")
                    kr = self.motor.kostnad(liter)
                    if kr:
                        deler.append(f"{kr:.2f} kr".replace(".", ","))
        self.send("✅ Vanning ferdig", " · ".join(deler) + ".", "program", ikon="mdi:check-circle")

    # ------------------------------------------------------------ sone
    def _sone(self, nr: int):
        return self.motor.soner.get(nr) if nr else self.motor.hageslange

    def _sone_startet(self, nr: int) -> None:
        if not self.paa("sone"):
            return
        s = self._sone(nr)
        if s:
            self.send(f"💧 {s.navn}", f"Vanner nå, startet kl. {_kl(dt_util.utcnow())}.", "sone",
                      ikon="mdi:sprinkler")

    def _sone_ferdig(self, nr: int) -> None:
        if not self.paa("sone"):
            return
        s = self._sone(nr)
        if not s:
            return
        deler = []
        if s.siste_minutter >= 0.5:
            deler.append(_minutter(s.siste_minutter))
        if self.motor.har_flyt and s.siste_liter >= 1:
            deler.append(f"{round(s.siste_liter)} L")
        self.send(f"{s.navn} ferdig", (" · ".join(deler) + ".") if deler else "Ferdig vannet.", "sone",
                  ikon="mdi:check")

    # ------------------------------------------------------------ regnpause
    def _regnpause_endret(self, aktiv: bool, til: datetime | None) -> None:
        if not self.paa("regnpause"):
            return
        if aktiv:
            tekst = f"Vanningen står over til {_naar(til)}." if til else "Vanningen står over."
            self.send("🌧️ Regnpause", tekst, "regnpause", ikon="mdi:weather-pouring")
        else:
            self.send("☀️ Regnpausen er over", "Programmene kjører som vanlig igjen.", "regnpause",
                      ikon="mdi:weather-sunny")

    # ------------------------------------------------------------ vakter
    def _sjekk_vann_renner(self) -> None:
        """Vann gjennom måleren uten at noen sone går, lenger enn grensen:
        glemt hageslange eller en lekkasje."""
        h = self.motor.hageslange
        if h._start is None:
            self._vann_renner_sendt = False
            return
        if self._vann_renner_sendt or not self.paa("vann_renner"):
            return
        varighet = (dt_util.utcnow() - h._start).total_seconds() / 60
        if varighet < self.vann_renner_min:
            return
        self._vann_renner_sendt = True
        liter = round(h.liter - h._start_liter)
        self.send("🚰 Vannet renner",
                  f"Det har rent vann i {_minutter(varighet)} uten at noen sone går – "
                  f"glemt hageslange eller en lekkasje? {liter} L så langt.",
                  "vann_renner", ikon="mdi:water-alert", viktig=True)

    def _sjekk_ingen_flyt(self) -> None:
        """En sone har gått i flere minutter uten at det kommer vann: kranen er stengt,
        ventilen henger, eller slangen er klemt."""
        if not self.motor.har_flyt:
            return
        s = self.motor.aktiv()
        if not s or s._start is None or s.nr in self._ingen_flyt_sendt:
            return
        varighet = (dt_util.utcnow() - s._start).total_seconds() / 60
        if varighet < INGEN_FLYT_MIN or self.motor._flow(s) > 0:
            return
        # Har sonen fått vann siden den startet, er det ikke «ingen vannføring».
        if s.liter - s._start_liter >= 1:
            return
        self._ingen_flyt_sendt.add(s.nr)
        if not self.paa("ingen_flyt"):
            return
        self.send("⚠️ Ingen vannføring",
                  f"{s.navn} har gått i {_minutter(varighet)} uten at det kommer vann. "
                  "Sjekk kranen og ventilen.", "ingen_flyt", ikon="mdi:water-off", viktig=True)

    # ------------------------------------------------------------ sending
    def send(self, tittel: str, tekst: str, type_: str, *, ikon: str = "mdi:water",
             viktig: bool = False, test: bool = False) -> None:
        mottakere = self.mottakere
        self.sist_sendt = f"{tittel} – {tekst}"
        if not mottakere:
            return
        data: dict[str, Any] = {
            "tag": f"ki_vanning_{type_}",
            "group": "ki_vanning",
            "notification_icon": ikon,
            "channel": "Vanning",
        }
        if viktig:
            data["push"] = {"interruption-level": "time-sensitive"}
            data["importance"] = "high"
        for m in mottakere:
            self.hass.async_create_task(self._send_en(m, tittel if not test else f"TEST: {tittel}", tekst, data))

    async def _send_en(self, mottaker: str, tittel: str, tekst: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call(
                "notify", mottaker, {"title": tittel, "message": tekst, "data": data}, blocking=True)
        except Exception as err:  # noqa: BLE001 – én telefon som svikter skal ikke stoppe de andre
            _LOGGER.warning("KI Vanning: fikk ikke sendt varsel til %s: %s", mottaker, err)

    def test(self) -> None:
        self.send("💧 Vanning startet", "Plen nord · 3 soner · ca. 40 min.", "test",
                  ikon="mdi:sprinkler-variant", test=True)
