# KI Vanning 3.3.1

## Hovedventilen åpnes også når sonene dukker opp etter oppstart

En sone som startet, åpnet ikke hovedventilen. KI Vanning lyttet bare på sonene den fant *ved oppstart*. Lastet
Home Assistant KI Vanning før OpenSprinkler var klar, fant den ingen soner da — og fulgte dem aldri etterpå, så
hovedventilen ble ikke rørt uansett hvordan sonen ble startet.

- **Følger sonene fortløpende:** hvilke entiteter som følges, regnes ut på nytt ved hver hendelse, i stedet for en
  fast liste fra oppstart.
- **Finner sonene på nytt** hvert femte minutt (når planen hentes), så soner som kommer til senere, blir med.
- **Sikkerhetsnett:** hvert 30. sekund sjekkes det om en sone går mens hovedventilen står stengt. Da åpnes den —
  én gang per sone, så det ikke blir en løkke hvis ventilen stenger seg selv fordi det ikke kommer vann.
- **Navnet:** nyere OpenSprinkler setter enhetsnavnet foran («OpenSprinkler S01 Garasje/Roser»). Det fjernes nå,
  så sonen heter «Garasje/Roser» i varsler og i oversikten.

### Kontrollert

Python 3.13.15 og Home Assistant 2025.12.5: 29 tester bestått, to nye — soner som dukker opp etter oppstart (ingen
soner ved start, så sonen legges til, planen hentes, sonen starter og hovedventilen åpnes; navnet blir
«Garasje/Roser»), og tikket som åpner hovedventilen når en sone allerede går. Oppsettstesten (begge modiene,
hovedventil, varsler, avlasting) går som før.
