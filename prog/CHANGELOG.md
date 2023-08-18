# Changelog Day Ahead Optimalisering
## [Unreleased]
De volgende zaken staan op de todo lijst: <br>
De software onderbrengen in een HA addon
Alle print opdrachten omzetten naar logger

## [v0.3.0] - 2023-08-18

### Added

- versienummer in bestand _version.py
- check op voldoende aantal rijen bij prognose data (dynamische prijzen en meteo)
    - bij 2 rijen of minder wordt er niet gerekend<br>
    - bij 3 tot 8 rijen wordt er wel gerekend maar wordt er wel een waarschuwing afgegeven 
    
- een changelog
- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Fixed

- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Changed
    
- notificatie via Home Assistant toegevoegd. Zie voor meer informatie README.md bij **notification entity**
- in het instellingenbestand options.json is de naam van de entity aanduiding veranderd: <br>
`"entity ready time"` wordt `"entity ready datetime"`
- aanvullingen en wijzigingen in README.md

### Removed

- prog/da_webserver.py verwijderd

### Deprecated

- geen

### Security

- geen
