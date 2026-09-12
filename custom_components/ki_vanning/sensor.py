"""Sensorene i KI Vanning."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_INTEGRASJON, ATTR_SONE, ATTR_TYPE, DOMAIN, PERIODER, PERIODE_NAVN
from .coordinator import KiVanningMotor, Sone
from .entity import KiVanningEntitet


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    motor: KiVanningMotor = hass.data[DOMAIN][entry.entry_id]
    ut: list[SensorEntity] = []

    for sone in motor.alle():
        ut.append(SoneForbruk(motor, sone))
        ut.append(SoneKostnad(motor, sone))
        ut.append(SoneKjoretid(motor, sone))
        ut.append(SoneRate(motor, sone))
        ut.append(SoneSiste(motor, sone))
        for p in PERIODER:
            ut.append(SonePeriode(motor, sone, p))

    for p in PERIODER:
        ut.append(TotalPeriode(motor, p))
    ut += [TotalForbruk(motor), TotalKostnad(motor), Estimat(motor), PlanlagtIDag(motor),
           NesteVanning(motor), AktivSone(motor), Oversikt(motor)]
    add(ut)


class _Liter(KiVanningEntitet, SensorEntity):
    _attr_native_unit_of_measurement = "L"
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water"


class SoneForbruk(_Liter):
    """Alt vann sonen har brukt."""

    def __init__(self, motor, sone: Sone) -> None:
        super().__init__(motor, f"{sone.slug}_forbruk", f"Forbruk {sone.navn}")
        self.sone = sone

    @property
    def native_value(self) -> float:
        return round(self.sone.liter, 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "forbruk", ATTR_SONE: self.sone.navn,
            "nr": self.sone.nr, "metode": self.sone.metode, "boks": self.sone.boks,
            "bryter": self.sone.bryter, "gaar": self.sone.gaar, "status": self.sone.status,
            "rate": self.motor.rate(self.sone), "kalibrert": self.sone.rate > 0,
            "kostnad": self.motor.kostnad(self.sone.liter),
            **{f"liter_{p}": round(self.sone.perioder[p], 1) for p in PERIODER},
            **{f"minutter_{p}": round(self.sone.min_perioder[p], 1) for p in PERIODER},
            "siste_liter": self.sone.siste_liter, "siste_minutter": self.sone.siste_minutter,
            "siste_slutt": self.sone.siste_slutt,
        }


class SonePeriode(_Liter):
    """Forbruk i dag, denne uken, måneden og året."""

    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, motor, sone: Sone, periode: str) -> None:
        super().__init__(motor, f"{sone.slug}_forbruk_{periode}", f"Forbruk {sone.navn} {PERIODE_NAVN[periode]}")
        self.sone, self.periode = sone, periode

    @property
    def native_value(self) -> float:
        return round(self.sone.perioder[self.periode], 1)

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: f"forbruk_{self.periode}", ATTR_SONE: self.sone.navn,
                "kostnad": self.motor.kostnad(self.sone.perioder[self.periode]),
                "minutter": round(self.sone.min_perioder[self.periode], 1)}


class SoneKostnad(KiVanningEntitet, SensorEntity):
    _attr_native_unit_of_measurement = "kr"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash"

    def __init__(self, motor, sone: Sone) -> None:
        super().__init__(motor, f"{sone.slug}_kostnad", f"Kostnad {sone.navn}")
        self.sone = sone

    @property
    def native_value(self) -> float:
        return self.motor.kostnad(self.sone.liter)

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "kostnad", ATTR_SONE: self.sone.navn,
                **{f"kostnad_{p}": self.motor.kostnad(self.sone.perioder[p]) for p in PERIODER}}


class SoneKjoretid(KiVanningEntitet, SensorEntity):
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-outline"

    def __init__(self, motor, sone: Sone) -> None:
        super().__init__(motor, f"{sone.slug}_kjoretid", f"Kjøretid {sone.navn}")
        self.sone = sone

    @property
    def native_value(self) -> float:
        return round(self.sone.minutter, 1)


class SoneRate(KiVanningEntitet, SensorEntity):
    """Kalibrert vannmengde per minutt for sonen."""

    _attr_native_unit_of_measurement = "L/min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:speedometer"

    def __init__(self, motor, sone: Sone) -> None:
        super().__init__(motor, f"{sone.slug}_rate", f"Rate {sone.navn}")
        self.sone = sone

    @property
    def native_value(self) -> float:
        return self.motor.rate(self.sone)

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "rate", ATTR_SONE: self.sone.navn,
                "kalibrert": self.sone.rate > 0, "grunnlag_liter": round(self.sone.liter, 1),
                "grunnlag_minutter": round(self.sone.minutter, 1)}


class SoneSiste(KiVanningEntitet, SensorEntity):
    """Siste fullførte kjøring for sonen."""

    _attr_native_unit_of_measurement = "L"
    _attr_icon = "mdi:history"

    def __init__(self, motor, sone: Sone) -> None:
        super().__init__(motor, f"{sone.slug}_siste", f"Siste kjøring {sone.navn}")
        self.sone = sone

    @property
    def native_value(self) -> float:
        return self.sone.siste_liter

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "siste", ATTR_SONE: self.sone.navn,
                "minutter": self.sone.siste_minutter, "slutt": self.sone.siste_slutt,
                "kostnad": self.motor.kostnad(self.sone.siste_liter)}


class TotalForbruk(_Liter):
    """Alt vann gjennom måleren, fordelt på soner og hageslange."""

    def __init__(self, motor) -> None:
        super().__init__(motor, "forbruk_totalt", "Forbruk totalt")

    @property
    def native_value(self) -> float:
        return self.motor.total("liter")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "total",
            "kostnad": self.motor.kostnad(self.motor.total("liter")),
            "per_sone": [
                {"sone": s.navn, "nr": s.nr, "boks": s.boks, "metode": s.metode,
                 "liter": round(s.liter, 1), "i_dag": round(s.perioder["i_dag"], 1),
                 "uke": round(s.perioder["uke"], 1), "maaned": round(s.perioder["maaned"], 1),
                 "aar": round(s.perioder["aar"], 1),
                 "minutter": round(s.minutter, 1), "rate": self.motor.rate(s),
                 "kalibrert": s.rate > 0, "kostnad": self.motor.kostnad(s.liter)}
                for s in self.motor.alle()
            ],
        }


class TotalPeriode(_Liter):
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, motor, periode: str) -> None:
        super().__init__(motor, f"forbruk_{periode}", f"Forbruk {PERIODE_NAVN[periode]}")
        self.periode = periode

    @property
    def native_value(self) -> float:
        return self.motor.total("liter", self.periode)

    @property
    def extra_state_attributes(self) -> dict:
        liter = self.motor.total("liter", self.periode)
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: f"total_{self.periode}",
            "kostnad": self.motor.kostnad(liter),
            "minutter": self.motor.total("minutter", self.periode),
            "per_sone": [
                {"sone": s.navn, "liter": round(s.perioder[self.periode], 1),
                 "minutter": round(s.min_perioder[self.periode], 1),
                 "kostnad": self.motor.kostnad(s.perioder[self.periode])}
                for s in self.motor.alle()
            ],
        }


class TotalKostnad(KiVanningEntitet, SensorEntity):
    _attr_native_unit_of_measurement = "kr"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, motor) -> None:
        super().__init__(motor, "kostnad_totalt", "Kostnad totalt")

    @property
    def native_value(self) -> float:
        return self.motor.kostnad(self.motor.total("liter"))

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "kostnad_total", "pris_m3": self.motor.pris(),
                **{f"kostnad_{p}": self.motor.kostnad(self.motor.total("liter", p)) for p in PERIODER}}


class Estimat(KiVanningEntitet, SensorEntity):
    """Hvor mye dagens programmer kommer til å bruke."""

    _attr_native_unit_of_measurement = "L"
    _attr_icon = "mdi:water-check"

    def __init__(self, motor) -> None:
        super().__init__(motor, "estimat_i_dag", "Estimat i dag")

    @property
    def native_value(self) -> float:
        return self.motor.estimat_i_dag()["liter"]

    @property
    def extra_state_attributes(self) -> dict:
        e = self.motor.estimat_i_dag()
        brukt = self.motor.total("liter", "i_dag")
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "estimat",
            "kostnad": e["kostnad"], "per_sone": e["per_sone"],
            "brukt_i_dag": brukt, "igjen": max(0, round(e["liter"] - brukt)),
            "andel": round(min(100, brukt / e["liter"] * 100)) if e["liter"] else 0,
        }


class PlanlagtIDag(KiVanningEntitet, SensorEntity):
    """Programmene som står på planen i dag."""

    _attr_icon = "mdi:calendar-check"

    def __init__(self, motor) -> None:
        super().__init__(motor, "planlagt_i_dag", "Planlagt i dag")

    @property
    def native_value(self) -> int:
        return len(self.motor.dagens_programmer())

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "plan",
                "programmer": self.motor.dagens_programmer(),
                "alle_programmer": self.motor.planlagt,
                "program_historikk": self.motor.programliste(),
                "feil": self.motor.plan_feil}


class NesteVanning(KiVanningEntitet, SensorEntity):
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, motor) -> None:
        super().__init__(motor, "neste_vanning", "Neste vanning")

    @property
    def native_value(self) -> str:
        n = self.motor.neste
        return f"{n['naar']} {n['tid']}" if n else "—"

    @property
    def extra_state_attributes(self) -> dict:
        n = self.motor.neste or {}
        return {ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "neste", **n}


class AktivSone(KiVanningEntitet, SensorEntity):
    """Hvilken sone som vanner akkurat nå."""

    _attr_icon = "mdi:sprinkler-variant"

    def __init__(self, motor) -> None:
        super().__init__(motor, "aktiv_sone", "Aktiv sone")

    @property
    def native_value(self) -> str:
        s = self.motor.aktiv()
        if s:
            return s.navn
        return "Hageslange" if self.motor._flow() > 0 else "Ingen"

    @property
    def extra_state_attributes(self) -> dict:
        s = self.motor.aktiv()
        flow = self.motor._flow(s)
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "aktiv", "flow": flow,
            **({"planlegger": self.motor.plan.status()} if self.motor.plan else {}),
            "sone_nr": s.nr if s else None, "metode": s.metode if s else "",
            "liter_denne_kjoringen": round(s.liter - s._start_liter, 1) if s and s._start else 0,
            "minutter_denne_kjoringen": round(s.minutter - s._start_min, 1) if s and s._start else 0,
        }


class Oversikt(KiVanningEntitet, SensorEntity):
    """Ett samlet attributt kortet kan lese hele oppsettet fra."""

    _attr_icon = "mdi:view-dashboard-outline"

    def __init__(self, motor) -> None:
        super().__init__(motor, "oversikt", "Oversikt")

    @property
    def native_value(self) -> str:
        return f"{len(self.motor.soner)} soner"

    @property
    def extra_state_attributes(self) -> dict:
        m = self.motor
        e = m.estimat_i_dag()
        return {
            ATTR_INTEGRASJON: DOMAIN, ATTR_TYPE: "oversikt",
            "modus": m.modus, "prefiks": m.oppsett.get("prefiks") or "",
            **({"planlegger": m.plan.status(),
                "anlegg": m.oppsett.get("anlegg", True) is not False,
                "regnpause": m.plan.regnpause_aktiv,
                "regnpause_minutter": m.plan.regnpause_minutter,
                "regnpause_til": m.plan.regnpause_til.isoformat() if m.plan.regnpause_til else None}
               if m.plan else {}),
            "i_dag": m.total("liter", "i_dag"), "uke": m.total("liter", "uke"),
            "maaned": m.total("liter", "maaned"), "aar": m.total("liter", "aar"),
            "totalt": m.total("liter"),
            **({"pris_m3": m.pris(), "kostnad_i_dag": m.kostnad(m.total("liter", "i_dag"))} if m.pris() else {}),
            "estimat_i_dag": e["liter"], "estimat_kostnad": e["kostnad"],
            "neste": m.neste, "programmer": m.planlagt, "program_historikk": m.programliste(),
            "soner": [
                {"nr": s.nr, "navn": s.navn, "metode": s.metode, "boks": s.boks,
                 "bryter": s.bryter, "gaar": s.gaar, "status": s.status, "flow": s.flow,
                 **{p: round(s.perioder[p], 1) for p in PERIODER},
                 "totalt": round(s.liter, 1), "minutter": round(s.minutter, 1),
                 "rate": m.rate(s), "kalibrert": s.rate > 0,
                 "kostnad": m.kostnad(s.liter), "kostnad_i_dag": m.kostnad(s.perioder["i_dag"]),
                 "siste_liter": s.siste_liter, "siste_minutter": s.siste_minutter,
                 "siste_slutt": s.siste_slutt}
                for s in m.alle()
            ],
        }
