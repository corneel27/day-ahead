## [V0.4.56] 2024-01-14
### Changed
Addon is met volledige ondersteuning voor 64 bit Intel/AMD Processor

## [v0.4.5] - 2024-01-09
# Changelog Day Ahead Optimalisering
## [Unreleased]
De volgende zaken staan op de todo lijst:
- Alle print opdrachten omzetten naar logger 
- webserver afmaken

### Changed

Het programma is ondergebracht in een addon van Home Assistant.<br>
Ten behoeve van de addon is alle software geplaatst onder de directory "dao". <br>
Alle documentatie is verplaatst naar docs\MANUAL.md

De volgende update query moet in de database "day_ahead" worden doorgevoerd:
````
UPDATE `day_ahead`.`variabel` SET `code`='pv_ac', `name`='Zonne energie AC' WHERE  `id`=15;
````
### Added
De volgende variabelen worden toegevoegd aan het bestand `variabel`:
````commandline
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (17, 'pv_dc', 'Zonne energie DC', 'kWh');
````
In options.json kun je nu het maximale vermogen opgeven van je netwerk aansluiting.
Zie README.md

##[v0.4.0] - 2023-10-15

### Removed
De functionaliteit om via de websocket in HA een berekening te starten is verwijderd.
Dat kan nu via een rest-command: /api/run


## [v0.3.1] - 2023-09-12

### Added
- je kunt nu de grafische stijl definieren o.a. darkmode. (zie README, graphics) 
- je kunt het presenteren van de grafieken na het uitvoeren van een berekening aan/uit zetten. (zie README, graphics)
- de volgende aanvullende python modules moeten worden geinstalleerd:
````
  pip3 install gunicorn ephem
````
- het protocol voor de api en de ws richting Home Assistant is instelbaar (zie in README, bij het onderdeel "Home Assistant") 
- voor de ondersteuning van een API moeten berekende resultaten worden opgeslagen.
Daarvoor moeten de volgende variabelen worden toegevoegd aan het bestand `variabel`:
````
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (9, 'bat_in', 'Batterij in', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (10, 'bat_out', 'Batterij uit', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (11, 'base', 'Basislast', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (12, 'boil', 'Boiler', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (13, 'wp', 'Warmtepomp', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (14, 'ev', 'Elektrische auto', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (15, 'pv', 'Zonnenergie', 'kWh');
INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (16, 'soc', 'SoC', '%');
````
Enkele rijen in de tabel `variabel` moeten worden geupdated: <br>
````
UPDATE `day_ahead`.`variabel` SET `name`='Verbruik' WHERE  `code`='cons';
UPDATE `day_ahead`.`variabel` SET `name`='Productie' WHERE  `code`='prod';
UPDATE `day_ahead`.`variabel` SET `name`='Tarief' WHERE  `code`='da';
UPDATE `day_ahead`.`variabel` SET `name`='Globale straling' WHERE  `code`='gr';
UPDATE `day_ahead`.`variabel` SET `name`='Temperatuur' WHERE  `code`='temp';
````
En er moet een extra tabel `prognoses` worden aangemaakt:
````
CREATE TABLE `prognoses` (
	`id` BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
	`variabel` INT(10) UNSIGNED NOT NULL DEFAULT '0',
	`time` BIGINT(20) UNSIGNED NOT NULL DEFAULT '0',
	`value` FLOAT NULL DEFAULT NULL,
	PRIMARY KEY (`id`) USING BTREE,
	UNIQUE INDEX `variabel_time` (`variabel`, `time`) USING BTREE,
	INDEX `variabel` (`variabel`) USING BTREE,
	INDEX `time` (`time`) USING BTREE
)
COLLATE='utf8mb4_unicode_ci'
ENGINE=InnoDB
AUTO_INCREMENT=1;
````
- de webserver/dashboard is uitgebreid met de volgende functionaliteit:
  * je kunt met een api-call gegevens opvragen die je o.a. kunt gebruiken in Home Assistant 
  om sensoren te voorzien van data en attributen en waar je met de apexcharts-card 
  grafieken kunt maken (zie README.md)
  * je kunt met een api call een berekening of bewerking uitvoeren. Deze nieuwe functionaliteit zal de
  websocket interface vervangen.
  * de "reports" zijn uitgebreid met meer perioden en bij de perioden waar ook de prognose die van toepassing zijn
  van toepassing is kun je "prognose" aan/uit zetten (zie README.md)
  * je kunt met de web-interface alle berekeningen en bewerkingen uitvoeren en je krijgt direct 
  de logging van het resultaat te zien (zie README.md) 

### Fixed
- Het laatste uur (meestal uur 23:00) wordt nu bij de grafieken volledig getoond. Dat geldt ook voor de SoC waarde die om 24:00 uur wordt bereikt.
- Grafieken worden niet meer getoond in de schedule-modus zodat het programma daar niet op blijft hangen
- De pv-productie werd niet goed berekend voor panelen die niet op zuid waren georienteerd.
Dit is aangepast.
- Het tarief voor teruglevering zonder belasting wordt nu berekend zonder de saldering van de 
inkoopvergoeding van de leverancier.
- Bij een tussentijdse berekening (dus niet op het hele uur) werd de boiler te snel ingezet.
Dit is hersteld.

### Changed
- het laden van de batterij (van omvormer naar dc) wordt nu berekend met een zogenaamde "special ordered set"(sos). 
Dit heeft twee voordelen: <br>
  - het rekent veel sneller
  - er wordt makkelijker tussen twee "stages" geinterpoleerd. <br>
  Als dit goed bevalt zal het ook worden geimplementeerd voor het ontladen (van dc naar ac) en van dc naar batterij en vice versa.<br>
- de prijzengrafieken zijn in blokvorm en uitgelijnd met de verbruiksgrafieken


### Issues
Als het programma draait in scheduler-mode wordt een websocket geopend naar HA zodat vanuit HA een 
optimaliseringsberekening kan worden gestart.
Als HA stopt (bijv. voor een update) dan blijft de websocket "in de lucht" maar is niet meer effectief.

### Removed


### Deprecated

- geen

### Security

- geen

## [v0.3.0] - 2023-08-18

### Added

- de staafjes van de staafgrafieken worden links aan het uurtijdstip uitgelijnd
- de grafieklijnen van de prijzen zijn nu stapsgewijs
- via de optie **graphics** kun je kiezen welke prijzen moeten worden getoond in de grafiek met prijzen (zie README)
- als je een berekening laat uitvoeren met de parameter **debug** krijg je nu meer info welke instellingen zouden zijn 
aangepast als je de berekening zonder **debug** zou hebben laten uitvoeren
- de webserver /het dasboard kan gedeeltelijk worden gebruikt (zie README)
- een input_datetime entity die wordt geupdate als door het programma een taak wordt uitgevoerd.
- een logger is toegevoegd aan de webserver (wordt straks dashboard). <br>
De loggings zijn te vinden in data\log\dashboard.log.
- versienummer in bestand _version.py
- check op voldoende aantal rijen bij prognose data (dynamische prijzen en meteo)
    - bij 2 rijen of minder wordt er niet gerekend<br>
    - bij 3 tot 8 rijen wordt er wel gerekend maar wordt er wel een waarschuwing afgegeven 
    
- een changelog
- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Fixed

- Tijdens een lopend uur (dus met een eerste uur wat minder dan 60 minuten duurt)
gaf het programma verkeerde resultaten voor dat eerste uur. Dit is gefixed.
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
