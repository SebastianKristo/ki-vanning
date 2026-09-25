# KI Vanning 3.3.2

## Hovedventilen åpnes før sonen starter — og du ser hvorfor når den ikke gjør det

**Start gjennom KI Vanning i OpenSprinkler-modus.** `ki_vanning.kjor` virket bare med egne ventiler. Nå virker den
også med OpenSprinkler: hovedventilen åpnes først, så startes stasjonen med `opensprinkler.run_station`. Vanningskortet
(ki-cards 8.99.5) starter sonene slik, så ventilen er åpen før vannet skal komme — i stedet for å åpnes etter at
OpenSprinkler har meldt at sonen går.

**Status for hovedventilen** i oversikten (`sensor.ki_vanning_oversikt`, attributtet `hovedventil`): entiteten,
tilstanden, om den står stengt mens en sone går, og hva som sist skjedde — `åpnet`, `var allerede åpen`, `feil`
(med feilmeldingen fra tjenesten) eller `utilgjengelig` (ventilen finnes ikke eller er utilgjengelig). Hvert forsøk
logges også på info-nivå.

**Ny tjeneste:** `ki_vanning.apne_hovedventil` åpner den nå. Kortet bruker den i varselet.

### Kontrollert

Python 3.13.15 og Home Assistant 2025.12.5: 31 tester bestått, to nye — `kjor` i OpenSprinkler-modus slår på
hovedventilen før `run_station` og status blir `åpnet`; en ventil som ikke finnes gir `utilgjengelig` og
«stengt mens sone går». Oppsettstesten går som før.
