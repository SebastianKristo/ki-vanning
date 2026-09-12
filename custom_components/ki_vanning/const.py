"""Konstanter for KI Vanning."""
from __future__ import annotations

DOMAIN = "ki_vanning"
PLATFORMS = ["sensor", "number", "button", "binary_sensor", "switch"]

# Konfigurasjon
CONF_PREFIKS = "prefiks"          # entitetsprefiks for OpenSprinkler, f.eks. ute_opensprinkler
CONF_FLOW = "flow"                # sensor med L/min fra vannmåleren
CONF_HOST = "host"                # OpenSprinkler-adresse (valgfri, gir programplan)
CONF_PASSORD = "passord"          # md5-passord til OpenSprinkler-API-et
CONF_PRIS = "pris"                # kr per m³
CONF_MIN_FLOW = "min_flow"        # under denne regnes flow som null (L/min)
CONF_MODUS = "modus"              # opensprinkler | ventiler
CONF_SONER = "soner"              # egne ventiler: [{entity, navn, ikon}]
CONF_PROGRAMMER = "programmer"    # [{navn, dager, tid, soner:[{entity,min}], aktiv}]
CONF_ANLEGG = "anlegg"            # hovedbryter: av stopper alt
CONF_REGNPAUSE = "regnpause"      # timer med pause

MODUS_OS = "opensprinkler"
MODUS_VENTILER = "ventiler"

MAKS_MINUTTER = 180               # sikkerhetsgrense for én kjøring
UKEDAGER = ["man", "tir", "ons", "tor", "fre", "lor", "son"]

STD_PRIS = 41.11
STD_MIN_FLOW = 0.3
STD_FALLBACK_RATE = 8.0           # L/min når en sone aldri har kjørt

# Lagring
LAGER_VERSJON = 1
LAGER_NOKKEL = "ki_vanning_data"

# Perioder vi fører tall for
PERIODER = ["i_dag", "uke", "maaned", "aar"]
PERIODE_NAVN = {"i_dag": "i dag", "uke": "denne uken", "maaned": "denne måneden", "aar": "i år"}

# Attributtmarkør så kortet finner entitetene våre
ATTR_INTEGRASJON = "integrasjon"
ATTR_SONE = "sone"
ATTR_TYPE = "ki_type"
