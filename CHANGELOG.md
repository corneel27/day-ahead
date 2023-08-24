# Changelog Day Ahead Optimalisering
## [Unreleased]
De volgende zaken staan op de todo lijst:
- Documentatie webserver in README
- De software onderbrengen in een HA addon
- Alle print opdrachten omzetten naar logger 
- prijzengrafiek(en) in blokvorm


## [v0.3.0] - 2023-08-18

### Added

- een logger is toegevoegd aan de webserver (wordt straks dashboard). <br>
De loggings zijn te vinden in data\log\dashboard.log.
- versienummer in bestand _version.py
- check op voldoende aantal rijen bij prognose data (dynamische prijzen en meteo)
    - bij 2 rijen of minder wordt er niet gerekend<br>
    - bij 3 tot 8 rijen wordt er wel gerekend maar wordt er wel een waarschuwing afgegeven 
    
- een changelog
- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Fixed

- ws parameter overal omgezet naar self.w_socket
- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Changed
    
- laden auto wordt alleen uitgezet als auto thuis is (en aangesloten) 
- ongebruikte instellingen uit README.md gehaald
- navigatieknoppen in webserver bij "home" omgezet
- menu optie **Meteo** in webserver voorzien van toelichting "in ontwikkeling"
- notificatie via Home Assistant toegevoegd. Zie voor meer informatie README.md bij **notification entity**
- in het instellingenbestand options.json is de naam van de entity aanduiding veranderd: <br>
`"entity ready time"` wordt `"entity ready datetime"`
- aanvullingen en wijzigingen in README.md


### Issues
Als het programma draait in scheduler-mode wordt een websocket geopend naar HA zodat vanuit HA een 
optimaliserings berekening kan worden gestart.
Als HA stopt (bijv voor een update) dan blijft de websocket "in de lucht" maar is niet meer effectief.

### Removed

- prog/da_webserver.py verwijderd

### Deprecated

- geen

### Security

- geen
