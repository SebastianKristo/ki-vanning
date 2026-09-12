# KI Vanning

Forbruk, kostnad og estimat for OpenSprinkler – som en egen integrasjon i stedet for en haug med
template-pakker. Den setter seg opp selv: du peker på flow-sensoren fra vannmåleren, resten leses ut av
OpenSprinkler-integrasjonen.

## Hva den gjør

- **Fordeler vannet.** Flowen fra måleren tilskrives den sonen som kjører akkurat nå. Går det vann uten at
  en sone er i gang, føres det på **hageslangen**.
- **Fører forbruk** per sone: totalt, i dag, denne uken, denne måneden og i år – i liter og kroner.
- **Kalibrerer seg selv.** Kjøretiden per sone måles, og L/min regnes ut som faktisk forbruk delt på faktisk
  kjøretid. Sonen som aldri har kjørt bruker målt flow eller 8 L/min.
- **Leser programplanen** fra OpenSprinkler-integrasjonen selv: kalenderen `calendar.opensprinkler_schedule`
  gir kommende kjøringer, og programmenes egne entiteter gir navn, starttid og – der integrasjonen oppgir dem –
  minutter per sone. Ut av det kommer planlagt i dag, neste vanning og hva det kommer til å koste, kalibrert
  per sone. Ingen API-adresse eller passord er nødvendig.
- **Lærer av programmene.** Hver gang et program kjører, måles hvor mye vann det faktisk brukte. Kjenner vi
  ikke minuttene per sone, brukes snittet fra tidligere kjøringer som estimat.
- **Siste kjøring** per sone: liter, minutter og når den ble ferdig.

Alt ligger på én enhet, og `sensor.<navn>_oversikt` har hele oppsettet som attributter, slik at
`ki-vanning-card` kan tegne kortet uten at du lister opp entiteter.

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
