# KI Vanning 3.1.0

## Vannmåleren fylles ikke inn automatisk lenger

`_finn_flow()` lette gjennom alle sensorer etter en med enheten L/min og satte den som
**standardverdi** i oppsettet. Har du ikke vannmåler på anlegget, men en eller annen
L/min-sensor i huset, ble den plukket som felles måler — og da ble sonenes egne målere
aldri brukt, siden `_flow()` bare faller tilbake på den felles når sonen mangler sin egen.

Feltet står nå tomt. Lar du det stå tomt, brukes sonenes egne målere. Forslaget fra
automatikken vises fortsatt i teksten, men fyller ikke inn noe.

Feltet er også `Optional` i OpenSprinkler-steget nå; det var `Required` med en
forhåndsutfylt verdi, så det var vanskelig å komme videre uten å velge noe.

## `har_flyt` i oversikten

Oversiktssensoren har fått to nye attributter:

* `har_flyt` – finnes det en vannmåler i det hele tatt, felles eller på en sone
* `felles_flyt` – er det satt en felles måler

`ki-vanning-card` 3.5.0 bruker `har_flyt` til å skjule forbruksdelen når det ikke finnes
noen måler, i stedet for å vise estimater som ser ut som målinger.
