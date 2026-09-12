<p align="center"><img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/logo.svg" width="110"></p>

# KI Vanning

Forbruk, kostnad og estimat for OpenSprinkler – som en egen integrasjon i stedet for en haug med
template-pakker. Den setter seg opp selv: du peker på flow-sensoren fra vannmåleren, resten leses ut av
OpenSprinkler-integrasjonen.

## Hva den gjør

- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/forbruk.svg" width="22" align="absmiddle"> **Fordeler vannet.** Flowen fra måleren tilskrives den sonen som kjører akkurat nå. Går det vann uten at
  en sone er i gang, føres det på **hageslangen**.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/soner.svg" width="22" align="absmiddle"> **Fører forbruk** per sone: totalt, i dag, denne uken, denne måneden og i år – i liter og kroner.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/kostnad.svg" width="22" align="absmiddle"> **Kalibrerer seg selv.** Kjøretiden per sone måles, og L/min regnes ut som faktisk forbruk delt på faktisk
  kjøretid. Sonen som aldri har kjørt bruker målt flow eller 8 L/min.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/plan.svg" width="22" align="absmiddle"> **Leser programplanen** fra OpenSprinkler-integrasjonen selv: kalenderen `calendar.opensprinkler_schedule`
  gir kommende kjøringer, og programmenes egne entiteter gir navn, starttid og – der integrasjonen oppgir dem –
  minutter per sone. Ut av det kommer planlagt i dag, neste vanning og hva det kommer til å koste, kalibrert
  per sone. Ingen API-adresse eller passord er nødvendig.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/plan.svg" width="22" align="absmiddle"> **Lærer av programmene.** Hver gang et program kjører, måles hvor mye vann det faktisk brukte. Kjenner vi
  ikke minuttene per sone, brukes snittet fra tidligere kjøringer som estimat.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/hageslange.svg" width="22" align="absmiddle"> **Siste kjøring** per sone: liter, minutter og når den ble ferdig.

Alt ligger på én enhet, og `sensor.<navn>_oversikt` har hele oppsettet som attributter, slik at
`ki-vanning-card` kan tegne kortet uten at du lister opp entiteter.

## To måter å bruke den på

Ved oppsettet velger du hva slags anlegg du har.

**OpenSprinkler** – sonene, programmene og kalenderen leses fra OpenSprinkler-integrasjonen, og KI Vanning
legger forbruk, kostnad og estimat oppå.

**Egne ventiler** – har du Sonoff-ventiler eller andre brytere, styrer KI Vanning dem selv. Du legger til
ventilene én etter én i oppsettet, og får:

- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/plan.svg" width="20" align="absmiddle"> **Ukeprogram.** Hvert program har klokkeslett, hvilke
  ukedager det gjelder, og hvor mange minutter hver sone skal gå. Sonene kjøres etter tur, aldri to samtidig.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/logo.svg" width="20" align="absmiddle"> **Feriemodus.** `switch.feriemodus` slår på
  ferieprogrammene – programmer merket `ferie: true` kjører bare da, og vanningstiden ganges med `ferie_faktor`
  (1,3 som standard) fordi ingen er hjemme til å følge med.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/soner.svg" width="20" align="absmiddle"> **Flow per sone.**
  Har hver ventil sin egen måler, settes den på sonen – da føres literne fra riktig måler, og en felles
  vannmåler er ikke nødvendig. Uten felles måler droppes «hageslange»-posten, siden det ikke er noe å fange
  den opp med.
- <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/forbruk.svg" width="20" align="absmiddle"> **Kjøring på tid.** `ki_vanning.kjor` med 1, 5, 10,
  30 eller 60 minutter – det samme som knappene i kortet. Køen håndteres av integrasjonen, og en kjøring
  stopper av seg selv (maks tre timer som sikkerhet).

```yaml
# Eksempel på programmer (lagres i integrasjonens innstillinger)
programmer:
  - navn: Morgen
    tid: '06:00'
    dager: [man, ons, fre]
    soner:
      - {entity: switch.kjokkenbed, min: 10}
      - {entity: switch.veranda_blomster, min: 15}
  - navn: Ferieuke
    tid: '07:00'
    dager: [man, tir, ons, tor, fre, lor, son]
    ferie: true
    soner:
      - {entity: switch.veranda_spirea, min: 20}
```

### Tjenester for egne ventiler

- `ki_vanning.kjor` – `sone` (entitet eller navn) og `minutter`
- `ki_vanning.kjor_program` – `program`
- `ki_vanning.stopp` – tømmer køen og slår av alt
- `ki_vanning.sett_ferie` – `pa: true/false`

## Installasjon

**HACS:** Legg til `https://github.com/SebastianKristo/ki-vanning` som egendefinert repository (type
*Integration*), installer, start HA på nytt og legg til **KI Vanning** under Innstillinger → Enheter og
tjenester.

**Manuelt:** Kopier `custom_components/ki_vanning` til `/config/custom_components/` og start på nytt.

## Oppsett

| Felt | Betydning |
|---|---|
| OpenSprinkler-prefiks | Fylles ut automatisk, f.eks. `ute_opensprinkler` |
| Flow-sensor | Sensoren fra vannmåleren i L/min |
| OpenSprinkler-adresse | Valgfri. Gir den nøyaktige programtabellen med minutter per sone |
| API-passord | Valgfri, hører sammen med adressen |
| Vannpris | kr per m³ – kan endres etterpå med `number.vannpris` |
| Laveste flow | Under denne regnes flow som null, så dryppet i røret ikke teller |

## Entiteter

Per sone (og for hageslangen): `forbruk`, `forbruk i dag / uken / måneden / året`, `kostnad`, `kjøretid`,
`rate` (L/min) og `siste kjøring`. I tillegg: `forbruk totalt`, `kostnad totalt`, `estimat i dag`,
`planlagt i dag`, `neste vanning`, `aktiv sone`, `oversikt`, `hageslange i bruk`, `vanner nå`,
`number.vannpris` og knapper for å nullstille tellere eller hente programplanen på nytt.

## Tjenester

- `ki_vanning.nullstill` – `hva: alt | forbruk | kalibrering`
- `ki_vanning.hent_plan` – leser programmene fra OpenSprinkler på nytt

## Erstatter

Pakkene `vanning_komplett.yaml`, `vanning_plan.yaml`, `vann_kostnad.yaml`, `vann_kjoretid.yaml`,
`vann_hageslange.yaml`, `vann_estimat.yaml` og `forbruk_per_sone_i_dag.yaml`.

## Ikoner

| | |
|---|---|
| <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/logo.svg" width="34"> | Integrasjonen – spreder med vann |
| <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/soner.svg" width="34"> | Soner |
| <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/forbruk.svg" width="34"> | Forbruk i liter |
| <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/kostnad.svg" width="34"> | Kostnad og kalibrering |
| <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/plan.svg" width="34"> | Programplan og neste vanning |
| <img src="https://raw.githubusercontent.com/SebastianKristo/ki-vanning/main/brand/hageslange.svg" width="34"> | Hageslangen |

Ikonene ligger i `brand/` som SVG og PNG (256 px). `brand/logo.png` passer som *Social preview* i
repo-innstillingene.
