"""Planlegger for egne ventiler – uker, regnpause og manuell kjøring.

Brukes når man ikke har OpenSprinkler: sonene er vanlige brytere (for eksempel
Sonoff-ventiler), og denne modulen står for køen, klokka og regnpausen.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_time, async_track_time_change
from homeassistant.util import dt as dt_util

from .const import MAKS_MINUTTER, UKEDAGER

_LOGGER = logging.getLogger(__name__)


@dataclass
class Koe:
    """En kjøring som venter eller pågår."""

    entity: str
    navn: str
    minutter: float
    program: str | None = None
    start: datetime | None = None
    slutt: datetime | None = None


@dataclass
class Program:
    """Et program: enten faste ukedager eller et intervall, og sonene i rekkefølge
    eller samtidig."""

    navn: str
    tid: str = "06:00"
    dager: list[str] = field(default_factory=lambda: list(UKEDAGER))
    intervall: int = 0                  # 0 = bruk ukedager, ellers hver N. dag
    start_dato: str = ""                # ankerdato for intervallet (YYYY-MM-DD)
    soner: list[dict[str, Any]] = field(default_factory=list)   # [{entity, min}]
    samtidig: bool = False              # true: alle sonene åpnes samtidig
    aktiv: bool = True


    @property
    def total_min(self) -> float:
        """Sekvensielt er det summen, samtidig er det den lengste sonen."""
        tider = [float(z.get("min") or 0) for z in self.soner]
        if not tider:
            return 0
        return max(tider) if self.samtidig else sum(tider)

    def _anker(self) -> datetime | None:
        if not self.start_dato:
            return None
        try:
            return datetime.strptime(str(self.start_dato)[:10], "%Y-%m-%d")
        except ValueError:
            return None

    def gjelder(self, nå: datetime) -> bool:
        if not self.aktiv:
            return False
            return False
        if self.intervall and self.intervall > 0:
            anker = self._anker()
            if anker is None:
                return True                      # uten ankerdato: hver dag til den settes
            dager = (nå.date() - anker.date()).days
            return dager >= 0 and dager % int(self.intervall) == 0
        return UKEDAGER[nå.weekday()] in self.dager

    def som_dict(self) -> dict[str, Any]:
        return {"navn": self.navn, "tid": self.tid, "dager": self.dager, "intervall": self.intervall,
                "start_dato": self.start_dato, "soner": self.soner, "samtidig": self.samtidig,
                "aktiv": self.aktiv, "total_min": self.total_min}


class Planlegger:
    """Kjører sonene etter tur, med klokke og kø."""

    def __init__(self, hass: HomeAssistant, motor) -> None:
        self.hass = hass
        self.motor = motor
        self.koe: list[Koe] = []
        self.naa: Koe | None = None
        self.programmer: list[Program] = []
        self.regnpause_til: datetime | None = None
        self._av: list[Any] = []
        self._timer = None

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        self.les_programmer()
        self._av.append(async_track_time_change(self.hass, self._minutt, second=5))

    def stopp(self) -> None:
        for av in self._av:
            av()
        self._av.clear()
        if self._timer:
            self._timer()
            self._timer = None

    def les_programmer(self) -> None:
        rå = self.motor.oppsett.get("programmer") or []
        self.programmer = [Program(**{**{"navn": "Program"}, **p}) for p in rå]

    # ------------------------------------------------------------- regnpause
    @property
    def regnpause_aktiv(self) -> bool:
        return bool(self.regnpause_til and dt_util.utcnow() < self.regnpause_til)

    @property
    def regnpause_minutter(self) -> int:
        if not self.regnpause_aktiv:
            return 0
        return max(0, int((self.regnpause_til - dt_util.utcnow()).total_seconds() // 60))

    def sett_regnpause(self, timer: float) -> None:
        """Setter pause i så mange timer. 0 fjerner den."""
        if timer and float(timer) > 0:
            self.regnpause_til = dt_util.utcnow() + timedelta(hours=float(timer))
        else:
            self.regnpause_til = None
        self.motor._varsle()

    @property
    def anlegg_pa(self) -> bool:
        return self.motor.oppsett.get("anlegg", True) is not False

    # ------------------------------------------------------------------ klokke
    @callback
    def _minutt(self, nå: datetime) -> None:
        if not self.anlegg_pa or self.regnpause_aktiv:
            return                       # anlegget er av, eller det er regnpause
        lokal = dt_util.as_local(nå)
        klokke = lokal.strftime("%H:%M")
        for p in self.programmer:
            if p.tid == klokke and p.gjelder(lokal):
                self.hass.async_create_task(self.kjor_program(p.navn))

    # ------------------------------------------------------------------ kjøring
    async def kjor_program(self, navn: str) -> None:
        p = next((x for x in self.programmer if x.navn.lower() == str(navn).lower()), None)
        if not p:
            _LOGGER.warning("KI Vanning: fant ikke programmet %s", navn)
            return
        faktor = 1.0
        jobber = []
        for z in p.soner:
            sone = self.motor.sone_for(z.get("entity"))
            if not sone:
                continue
            jobber.append(Koe(entity=sone.bryter, navn=sone.navn,
                              minutter=min(MAKS_MINUTTER, float(z.get("min") or 0) * faktor),
                              program=p.navn))
        if not jobber:
            return
        if p.samtidig:
            await self._kjor_samtidig(jobber)
            return
        self.koe.extend(jobber)
        await self._neste()

    async def _kjor_samtidig(self, jobber: list[Koe]) -> None:
        """Alle sonene åpnes med én gang, og hver stenges når sin egen tid er ute."""
        nå = dt_util.now()
        self.parallelle = getattr(self, "parallelle", [])
        for j in jobber:
            j.start = nå
            j.slutt = nå + timedelta(minutes=j.minutter)
            self.parallelle.append(j)
            await self.hass.services.async_call("homeassistant", "turn_on", {"entity_id": j.entity}, blocking=False)
            async_track_point_in_time(self.hass, self._stopp_en(j), dt_util.as_utc(j.slutt))
        self.naa = max(jobber, key=lambda x: x.slutt)      # heroen viser den som varer lengst
        self.motor._varsle()

    def _stopp_en(self, jobb: Koe):
        @callback
        def _av(_nå):
            self.hass.async_create_task(self._avslutt_en(jobb))
        return _av

    async def _avslutt_en(self, jobb: Koe) -> None:
        await self._slaa_av(jobb.entity)
        self.parallelle = [j for j in getattr(self, "parallelle", []) if j is not jobb]
        if self.naa is jobb:
            self.naa = (self.parallelle or [None])[0]
        self.motor._varsle()

    async def kjor_sone(self, entity: str, minutter: float) -> None:
        sone = self.motor.sone_for(entity)
        if not sone:
            return
        self.koe.append(Koe(entity=sone.bryter, navn=sone.navn, minutter=min(MAKS_MINUTTER, float(minutter))))
        await self._neste()

    async def stopp_alt(self) -> None:
        self.koe.clear()
        for j in list(getattr(self, "parallelle", [])):
            await self._slaa_av(j.entity)
        self.parallelle = []
        if self._timer:
            self._timer()
            self._timer = None
        if self.naa:
            await self._slaa_av(self.naa.entity)
            self.naa = None
        for s in self.motor.soner.values():
            st = self.hass.states.get(s.bryter)
            if st and st.state == "on":
                await self._slaa_av(s.bryter)
        self.motor._varsle()

    async def _neste(self) -> None:
        if self.naa or not self.koe:
            self.motor._varsle()
            return
        jobb = self.koe.pop(0)
        jobb.start = dt_util.now()
        jobb.slutt = jobb.start + timedelta(minutes=jobb.minutter)
        self.naa = jobb
        await self.hass.services.async_call("homeassistant", "turn_on", {"entity_id": jobb.entity}, blocking=False)
        self._timer = async_track_point_in_time(self.hass, self._ferdig, dt_util.as_utc(jobb.slutt))
        self.motor._varsle()

    @callback
    def _ferdig(self, _nå) -> None:
        self.hass.async_create_task(self._avslutt())

    async def _avslutt(self) -> None:
        self._timer = None
        if self.naa:
            await self._slaa_av(self.naa.entity)
            self.naa = None
        await self._neste()

    async def _slaa_av(self, entity: str) -> None:
        await self.hass.services.async_call("homeassistant", "turn_off", {"entity_id": entity}, blocking=False)

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        n = self.naa
        return {
            "kjorer": bool(n),
            "sone": n.navn if n else None,
            "entity": n.entity if n else None,
            "program": n.program if n else None,
            "slutt": n.slutt.isoformat() if n and n.slutt else None,
            "sekunder_igjen": int((n.slutt - dt_util.now()).total_seconds()) if n and n.slutt else 0,
            "i_koe": [{"sone": k.navn, "minutter": k.minutter, "program": k.program} for k in self.koe],
            "samtidig": [{"sone": j.navn, "slutt": j.slutt.isoformat() if j.slutt else None}
                         for j in getattr(self, "parallelle", [])],
            "regnpause_til": self.regnpause_til.isoformat() if self.regnpause_til else None,
            "regnpause": self.regnpause_aktiv,
        }

    def planlagt(self, dager: int = 8) -> list[dict[str, Any]]:
        """Kommende kjøringer, brukt til «planlagt i dag» og «neste vanning»."""
        nå = dt_util.now()
        ut: list[dict[str, Any]] = []
        faktor = 1.0
        for d in range(dager):
            dag = nå + timedelta(days=d)
            for p in self.programmer:
                if not p.gjelder(dag):
                    continue
                try:
                    t, m = [int(x) for x in str(p.tid).split(":")[:2]]
                except ValueError:
                    continue
                start = dag.replace(hour=t, minute=m, second=0, microsecond=0)
                if start < nå:
                    continue
                soner = [{"navn": (self.motor.sone_for(z.get("entity")).navn
                                   if self.motor.sone_for(z.get("entity")) else z.get("entity")),
                          "nr": 0, "min": round(float(z.get("min") or 0) * faktor)} for z in p.soner]
                liter = sum(z["min"] * self.motor.rate(self.motor.sone_for(y.get("entity")))
                            for z, y in zip(soner, p.soner) if self.motor.sone_for(y.get("entity")))
                ut.append({
                    "navn": p.navn, "tid": start.strftime("%H:%M"), "start": start.isoformat(),
                    "minutter_til": int((start - nå).total_seconds() // 60),
                    "i_dag": start.date() == nå.date(), "soner": soner,
                    "total_min": round(max([z["min"] for z in soner] or [0]) if p.samtidig
                                       else sum(z["min"] for z in soner)),
                    "samtidig": p.samtidig, "intervall": p.intervall,
                    "estimat_liter": round(liter), "kilde": "planlegger",
                })
        ut.sort(key=lambda x: x["minutter_til"])
        return ut
