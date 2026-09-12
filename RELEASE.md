## Endret

**3.0.0 – regnpause i stedet for feriemodus**

- **Feriemodus og vannpris er fjernet** fra ventilmodus, sammen med ferie-faktoren. Programmene har ikke lenger et ferie-flagg
- **Regnpause:** `number.<prefiks>_regnpause` viser timer igjen og kan settes direkte. Knappene `button.<prefiks>_regnpause_24_t` og `_48_t` setter pause, og `_nullstill_regnpause` fjerner den. Mens pausen går, starter ingen programmer
- **Hovedbryter:** `switch.<prefiks>_anlegget`. Av stopper det som går og hindrer at programmene starter
- **Stopp alt** som egen knapp: `button.<prefiks>_stopp_alt` stopper kjøringen og tømmer køen
- Nye tjenester: `sett_regnpause` (timer), `nullstill_regnpause` og `sett_anlegg` (på/av). `sett_ferie` er borte

Oversiktssensoren har nå `anlegg`, `regnpause`, `regnpause_minutter` og `regnpause_til` i stedet for ferie-feltene. Pris og kostnad vises bare når en vannpris finnes – altså i OpenSprinkler-modus.
