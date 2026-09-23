# KI Vanning 3.3.0

## Hovedventil som åpnes hver gang en sone starter

Sonoff-ventilen stenger seg selv når det ikke har gått vann på en stund. Mellom to soner i et program,
eller når en sone slås på for hånd, kan den altså stå stengt — og da kommer det ikke vann.

Velg **Hovedventil** under **Konfigurer → Innstillinger**. Den kan være en `switch`, en `valve` eller en
`input_boolean`.

- **Hver gang en sone slår seg på, åpnes hovedventilen.** I begge modiene, og uansett hva som slo
  sonen på: et program, kortet, en tjeneste eller en bryter rett i Home Assistant.
- **Med egne ventiler åpnes den først**, før sonen, så vannet står klart i det sonen åpner. Også når
  sonene går samtidig.
- **Stenger den mens en sone går, åpnes den igjen — én gang per sone.** Stenger den på nytt, kommer det
  trolig ikke vann. Da får den stå, og det er varselet om manglende vannføring fra 3.2.0 som sier fra,
  i stedet for at ventilen åpnes og lukkes i en løkke.
- **Steng når ferdig** (valgfritt, av som standard): hovedventilen stenges 15 s etter at siste sone er
  av. Ventetiden er der så en sone som følger rett etter, ikke møter en lukket ventil; så lenge
  planleggeren har flere soner i kø, stenges den ikke.
- En `valve`-entitet åpnes med `valve.open_valve` og stenges med `valve.close_valve`; alt annet med
  `turn_on`/`turn_off`.
- Svikter hovedventilen, går vanningen likevel, og feilen havner i loggen.

Tømmer du feltet i innstillingene, slutter integrasjonen å styre ventilen.

### Kontrollert

Kjørt med Python 3.13.15 og Home Assistant 2025.12.5, med kjøretidsadvarsler som feil.

- `tests/test_hovedventil.py` — 9 nye tester: hovedventilen åpnes før sonen i et program; også ved
  neste sone etter at den har stengt seg selv; når en sone slås på rett i HA; åpnes igjen bare én gang
  når den stenger midt i; `valve`-domenet med `open_valve`; stenging når ferdig; ingen stenging når neste
  sone følger rett etter; ingenting ekstra uten hovedventil; og en OpenSprinkler-stasjon som starter.
- `tests/smoke_setup.py` — egne ventiler lastet gjennom Home Assistants egen laster med hovedventil:
  en sone slås på, og hovedventilen åpnes.
- Alle 27 tester og innlastingstesten går, også fra zip-en.

Ikke testet mot den ekte Sonoff-ventilen.
