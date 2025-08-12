# Changelog 刀 DAO
# Day Ahead Optimizer

# 2025.8.1.rc1

- Fixed error handling getting meteo-data
- Clear graph with the new meteodata
- Retry once if no meteodata recieved

# 2025.8.0.rc2
- Clear error message when no data present from Nordpool 
- Supplement documentation instant start

# 2025.8.0.rc1
Fixed report error second ev (reported by @DaBit)

# 2025.7.4.rc3
Fixed name-error

# 2025.7.4.rc2
- Implemented instant start for boiler and machines
- Energy needed to charge ev limited op 0 kWh as minimum
- Correct error exceeding max grid power in partial first hour (reported by @sMoKeFiSh)
- Fixed error logging planning second ev (reported by @DaBit)

# 2025.7.4.rc1
- Only draw consumption/production of configured devices.
- Implemented instant charging electric vehicle(s) (see DOCS.md) 

# 2025.7.3.rc2
- Changed calculation of baseloads to omit NaN
- Timeout webpage set to 120 seconds

# 2025.7.2
Fix error in api-calculation prognose pv_dc

# 2025.7.1.rc3
Extra logging op debug-level tijdens berekening baseloads.

# 2025.7.1.rc2
Fixed error get_meteo when solar is configured with strings (reported by @Mirabis)

# 2025.7.1.rc1

Introduction for support of more strings in pv-inverters.<br>
See DOCS.md

# 2025.7.1
Implemented the use of more han one string on one inverter or mppt.<br>
With backward compatibility!

# 2025.7.0

# BREAKING CHANGE<br>support stops for i386 
Machines with i386-processor will not be supported anymore.<br>
Some necessary modules (o.a. cryptography) are not available for the i386 architecture.<br>
There are a few users with this processor (5 of ca 200).
Please look out for another machine with an amd64 or aarch64 processor (perhaps a separate Docker-container on your NAS).

Other changes:
- Added cryptography to requirements.txt
- Updated several python-modules (dependabot)
- Users with postgresql-database get a message when timezone differs from local timezone.

# 2025.6.2
- Introduction new buildsystem (thanks @simnet)
- Repair vat delivery -> vat consumption, vat redelivery -> vat production

# 2025.6.1
Fixed error with api-call for data with parameter "cumulate=1" (reported by @konehead and @simnet)


# 2025.6.0

## Breaking changes
1. The calculation of the cost and profit with a "regular" energy-supplier is removed.
So you can remove the corresponding settings:
````
    "regular high" : 0.40,
    "regular low" : 0.35,
    "switch to low": 23,
````

2. The terms "delivery" and "redelivery" will be exchanged for the more commonly used terms **consumption** and **production**.
This will be done with backwards compatibilty, so you can use the old names, but you get a warning in the logging.
These are the new settings with the new names:
````
    "energy taxes consumption": {
      "2022-01-01": 0.06729,
      "2023-01-01": 0.12599,
      "2024-01-01": 0.10880,
      "2025-01-01": 0.10154
    },
    "energy taxes production": {
      "2022-01-01": 0.06729,
      "2023-01-01": 0.12599,
      "2024-01-01": 0.10880,
      "2025-01-01": 0.10154
    },
    "cost supplier consumption": {
      "2022-01-01": 0.002,
      "2023-03-01": 0.018,
      "2024-04-01": 0.0175,
      "2024-08-01": 0.020496
    },
    "cost supplier production": {
      "2022-01-01": 0.002,
      "2023-03-01": 0.018,
      "2024-04-01": 0.0175,
      "2024-08-01": 0.020496
    },
    
````
   The **cost supplier** values above are for Tibber so please adjust if you have another supplier.

3. The calculation of the total volume of consumption and production (and the tax refund) in the current contractperiod with your provider is removed.
You must set your tax refund value by yourself with the setting : **"tax refund" : "True"** whether the energy tax will be refund or not.

4. The graphics of the prices are adjusted. You can now set the following graphs on or off:
````
    "prices consumption": "True",
    "prices production": "True",
    "prices spot": "True",
    "average consumption": "True"
````
The "prices production" are only relevant if they differ from "prices consumption".
When you set both "True" and the values are equal, they will be plotted over each other.

5. The VAT (BTW) is now divided in two categories "vat consumption" and "vat production" and so are the settings:
This is done for the Belgian users of DAO wich have a different vat for redelivery but also for the future when tax refund and possible also vat refund 
will stop.<br>
To keep it backwards compatible the following logic is implemented:
   - when "vat consumption" is not found: "vat" will be used
   - when "vat production" is not found: "vat consumption" will be used and when that is not found "vat" will be used. <br>

   It is recommended for the future to change your settings now.<br>
  For instance:
````
    "vat consumption": {
      "2022-01-01": 21,
      "2022-07-01": 9,
      "2023-01-01": 21
    },
    "vat production": {
      "2022-01-01": 21,
      "2022-07-01": 9,
      "2023-01-01": 21
    },

````
6. The term **ip adress** in the settings for connecting your Home Assistant machine is deprecated.
Use the generic term **host** for it in the future (feature request of ebbz)

## New features 
- Introduction of a new optional setting for your solar strings (ac and dc):
  **max power**. With this setting (in kW) you can cap the power of your pv-string with the max power of your inverter(s) (feature request)
- Extend the result of the api-call for pv_ac and pv_dc (the last one is new) when invoked with the period "vandaag_en_morgen".
Therefor the period of getting meteo-data is enlarged until 96 hour from "now" (feature request Torch1969 e.a)

## Other changes
- Fixed calculation error when boiler set temperature is lower then boiler actual temperature (reported by timenator)

# [V2025.5.0]

- Start with a pre-builded repository on Github (thanks to bvw)
- Introduction of a check on "last invoice", warning when more than one year ago.
- Fix Dockerfile for build error Pillow library
- Corrected VAT-calculation when calculating the profit during the DAO optimal-calculation (reported bij bvw)
- Fix heatpump planning: when heat_demand-entity is false there will be no heat-pump power calculated in the first hour (reported by bvw)
- Fixed errors planning machine when planning calculation is in the previous planned period (reported by @sjampeter)
- Fixed error and show error-message when no entities are configured for setting the calculated planning of a machine in HA (reported by llevering)
- Fixed error with postgresql during reporting of balance and calculation of baseloads (reported by @balk77)
- Fixed error not switching off pv-switch with negative prices with more than one pv-string

# [V2025.4.2]

- Fixed futurewarning dataframe (reported by @Torch1969)
- Fixed error when deleting an image/log and deny or cancel confirmation (the item was deleted) (reported by @Bravo)
- Fixed error when calling api with data for **base** (=baseload) (reported by @Torch1969)
- Adjusted documentation of the api-call
- Fixed error planning machine when planning exceeds 24:00/0:00 barrier (reported by @sjampeter)
- Fixed error when more than one EV is configured (reported by @DaBit)
- Fixed error when generating \Reports\Balans (reported by @Torch1969)

# [V2025.4.1]
- Fixed error with postgresql during reporting of savings (reported by @balk77)
- Fixed planning error when calculating the planning of a machine during the planning window (reported by @bvw)

# [V2025.4.0] 

### BREAKING CHANGE
- Fixed the error (two hours too late) in the timestamp in the result-records from api/report-calls<br>
- The optional parameter "expected" isn't used anymore
The records now have a different structure:
  - the attributes "realised" and "expected" are now in the record as **datatype**
  - the attribute "time" now has a string presenting the date and time of the startmoment of the record
  - the new atribute "time_ts" present the date and time as a timestamp in milliseconds.
  - for instance a record of the price-info:
  ```
  {
  "message": "Success",
  "data": [
    {
      "time_ts": 1743890400000,
      "time": "2025-04-06 00:00",
      "da_ex": 0.07045,
      "da_cons": 0.23290806,
      "da_prod": 0.23290806,
      "datatype": "recorded"
    },
    {
      "time_ts": 1743894000000,
      "time": "2025-04-06 01:00",
      "da_ex": 0.061,
      "da_cons": 0.22147356,
      "da_prod": 0.22147356,
      "datatype": "recorded"
    },
    .....
  ```
  - for instance the data-structure for a consumption request:
  ``` 
  {"message": "Success",
  "data": [
    {
      "time_ts": 1743890400000,
      "time": "2025-04-06 00:00",
      "value": 0.653,
      "datatype": "recorded"
    },
    {
      "time_ts": 1743894000000,
      "time": "2025-04-06 01:00",
      "value": 0,
      "datatype": "recorded"
    },
    ...
    ```

<br>
<br>

**Other fixes:** <br>
- Fixed warning when getting prices from Nordpool for a day with changing to/from daylight saving <br>
- Fixed warning when calculating optimization for a day with changing to/from daylight saving

# [V2025.3.1] 
- Fixed error: no version-info when rendering api_run.html
- Fixed error when using sqlite for Home Assistant database during generating reports
- Fixed time error, when calling api-report over long periodes

# [V2025.3.0] 
- Fixed error when one use postgresql and get prices from Nordpool
- Fixed error when no co2-sensor is configured in the settings
- Introduction of new reports of **Savings** when you use one or more home baterries:
  - consumption (most of the time this saving wil be negative, because the use of the battery cost energy)
  - cost
  - CO2-emission; only available when you have activated the integration **Electricity Maps** 
  and when you have configured the sensor CO2-intensity in your settings
- All reports of CO2-emissions are restricted till the current hour, because the sensor CO2-intensity
only have values till the current hour. You cannot use the checbox "met prognose" and also the periods "morgen"
and "vandaag_en_morgen" are deleted.
- Introduction of generic calculating routines. With these routines new reports can easily be programmed.
In the near future the calculation of all reports will based on these routines.
- Introduction of a new type of graph (Waterfall-type) to present calculated savings.
For instance:
 ![saving_cost_graph.png](images/saving_cost_graph.png) <br />


# [V2025.2.0] 
- Fixed error calculating historic consumption and production since last invoice day
- Fixed error calculating baseload and balance with no/zero values sensor growatt inverter
- Better log and notification of errors, warnings and exceptions, also when you use a notification entity
- Correct a few typos in DOCS.md (o.a. homeassistant_v2.db -> home-assistant_v2.db)
- Time correction of one hour in meteo-data is removed

# [V2025.1.3] 
- Fixed "no optimal solution" when no zero-power stage is configured with a battery
- Implemented calculation and report of CO2-emission (see [DOCS.md](https://github.com/corneel27/day-ahead/blob/main/dao/DOCS.md#co2-emissie))
- Fixed year with copyright/license

# [V2025.1.2] 
- Fixed errors when postgresql db-engine is used
- Fixed error calculating report/balance with period "vorige maand"

# [V2025.1.1] 
Fixed errors when consumption-data in last contractyear could not be calculated.

# [V2025.1.0] 
- Fixed error saving prognoses with postgresql database
- Fixed error getting history consumption data: also data in ha-db are taken in account
- Optimum low level for the battery is back again
- When choosen for strategy "minimize consumption", there was sometimes "no solution",
this is corrected

# [V2024.12.3] 
Fixed error getting battery limits when no battery is configured

# [V2024.12.2] 
Fixed typo in utils.py

# [V2024.12.1] 
Fixed error: cycle costs (last) battery were not taken into account

# [V2024.12.0] 
# LET OP
De energiebelasting wijzigt per 1 januari 2025.<br>
Neem deze over van onderstaande lijst in je instellingen:<br>
```
    "energy taxes delivery": {
      "2022-01-01": 0.06729,
      "2023-01-01": 0.12599,
      "2024-01-01": 0.10880,
      "2025-01-01": 0.10154
    },
    "energy taxes redelivery": {
      "2022-01-01": 0.06729,
      "2023-01-01": 0.12599,
      "2024-01-01": 0.10880,
      "2025-01-01": 0.10154
    },
```
# Breaking change
There is an extra optional parameter when calling an api-report: **expected**.<br>
When you call the api without `expected` or `expected=0` (default value) then only **recorded** values 
are reported and the expected part of the json-result will be empty.
When you call with the parameter `expected=1` then the expected values are reported in the expected 
part of the json-result.<br>
For periods with the interval "hour", there will be no change.
But for periodes with the interval "day" or "month" this can lead to new results. 
For instance when you call the api for period "deze_week", without the parameter "expected" you get this result:<br>
```{ "message":"Success", "recorded": [{"time":"2024-12-02 00:00","value":36.7450000558},{"time":"2024-12-03 00:00","value":19.1840000708},{"time":"2024-12-04 00:00","value":36.8009995644},{"time":"2024-12-05 00:00","value":19.7590002147},{"time":"2024-12-06 00:00","value":43.3299993972},{"time":"2024-12-07 00:00","value":24.9570001736},{"time":"2024-12-08 00:00","value":6.462}], "expected" : [] }```<br>
But when you call it with "expected=1" then you get:<br>
```{ "message":"Success", "recorded": [{"time":"2024-12-02 00:00","value":36.7450000558},{"time":"2024-12-03 00:00","value":19.1840000708},{"time":"2024-12-04 00:00","value":36.8009995644},{"time":"2024-12-05 00:00","value":19.7590002147},{"time":"2024-12-06 00:00","value":43.3299993972},{"time":"2024-12-07 00:00","value":24.9570001736}], "expected" : [{"time":"2024-12-08 00:00","value":14.282395}] }```<br>
The total consumption of "2024-12-08" is now mentioned in the expexted part, because a part of the consumption is expected.

# Other changes
- "optimal lower level" is not used anymore: it was too difficult and too complex to understand and
didn't give enough good results
- The calculated cycle costs  are (per battery) logged (level info).
- There was a general error in api-calls, fixed.
- There is an error reported in a api-call: `http://<ip-adres>:5000/api/report/cost/deze_maand`. <br>This error is fixed?
- Fixed error api call "netto_cost"
- Scheduling of boiler can be postponed via a ha-entity
- when boiler is heated bij the heat pump for room-heating then there can only be "one" heating 
function in an hour, therefore is a new setting introduced in the boiler-section: "boiler heated 
by heatpump". This setting can be "True" or "False"
- the code is brought inline with PEP 8 (Style Guide for Python Code)
- Scheduling of heatpump can be set via a ha-entity
- Scheduling of heatpump can be achieved in three ways:
  - on/off
  - heat curve adjustment
  - calculated power
- When setting a state of an entity failed then an error message is written in the log 
  (name of the entity, new failed value)

## [V2024.11.1]
- Fixed an error when getting Tibber-data when using a Tibber pulse: 
only data before today are stored

## [V2024.11.0]
- Fixed a db-error when getting Tibber-data with the default sqlite-db

## [V2024.10.6]
- Fixed a few errors in the graphics for users with more than one battery

## [V2024.10.5]
- Correct error change to winter-time
  
## [V2024.10.4]
- When there are no batteries configured there was a soc-calculation error. This is corrected.
- The color of all the soc-lines are changed to "olive"

## [V2024.10.3]
- There is an extra optionalgraph (for each battery one) which shows the energybalance of the battery(ies).
You can omit this graph with a setting in the "graphics"-section": <br> 
`"battery balance": "False",`
- There was in the dasboard during an optimum calculation sometimes an **internal server error** caused by a too low timeout (30 sec).
The new timeout is raised to 60 sec. 
- When Nordpool data were not present there was a json-error message. This is corrected: there is now a not present message.
- The Nordpool source didn't work anymore. The module with the api library for Nordpool is updated.


## [V2024.10.2]
- New version of entsoe-py module fixed entsoe-issue
- New optional feature is introduced: "reduced hours". With this feature you can limit the max power
(charge and discharge) of your inverter/battery. You can use this to prevent too much noise. (zie DOCS.md)  
- There was a malformed string in an error-message, this is corrected
A new installation with sqlite had a failure, this is corrected.
- There were configuration errors for the sqlite-dialect. These generated errors during reporting.
These are repaired.
- The watchdog restarted the scheduler too often. Now it only restarts the scheduler after a change 
of "options.json" or "secrets.json".

## [V2024.10.1]
- There was an error in reporting with sqlite-db, this is corrected

## Belangrijk
De eerder opgenomen tijden in `options.json` voor het ophalen van meteodata via de scheduler geven regelmatig verkeerde data aan de kant van Meteoserver (in de tijd verschoven). 
Je kunt ze beter vervangen door onderstaande tijden:
```
    "0430": "get_meteo_data",
    "1030": "get_meteo_data",
    "1630": "get_meteo_data",
    "2230": "get_meteo_data",
```
## [V2024.10.0]
- There was an error during saving the calculated soc of more than one battery. This is fixed.
- A better report when there is a json-format error in the settings or secrets file
- The calculated use of a formerly planned engine is beter calculated and taken in account in the 
total consumption and cost
- There was an error in calculating start=time of engine(s), this is corrected.
- The calculated use of a formerly planned engine is now correct reported

## [V2024.8.7]
- The calculated bat-in was not saved; as a consequence the balance report was wrong or not presented 
(error). This corrected.
- Changed pythonmodule postgresql (psycopg2-binary -> psycopg2)

## [V2024.8.6]
- added saving calculated soc's
- added api for presenting calculated soc's
- made get meteo-data redundant, when gfs failed, take harmonie

## [V2024.8.5]
- name changed to Day Ahead Optimizer (from Day Ahead Optimizing)
- DOCS.md expanded with "DAO eerste keer opstarten"
- fixed errors when using the db-engine sqlite
- options_vb.json split in two options:
  - options_example.json, with all examples
  - options_start.json, with the minimum start settings


## [V2024.8.4]
- the extended logging of saving prognoses (prices, meteo-data and calculated consumptions) is moved from info to debug  
- there were issues with "lost connections" in combination with the mysql/mariadb db-engine; 
with extra parameters during the engine-initialisation these issues are solved.


## [V2024.8.3]
- there were resource leaks in the graphical module which caused runtime warnings/errors; the leaks are found and sealed.


## [V2024.8.2]

The following changes are implemented:
- for hybrid inverters: you can now limit the power from dc to bat and vice versa with two (optional) settings
(zie DOCS.md):
  - bat_to_dc max power
  - dc_to_bat max power
- there was an error when pv-dc production was higher than the max power of the inverter, this is corrected.
- the prognoses table is extended with a column with expected hourly pv-dc production
- there was a resource leak (db-connections) which caused runtime errors; the leak is found and sealed.

## [V2024.8.1]

Fixed two issues:
- when saving calculated prognoses the column "uur" couldn't be saved. This give an error.
- the new calculated entities for battery power are now mentioned in options_vb.json

## [V2024.8.0]
This is a major update with a lot of improvements:
 - The addon works now with 3 possible database engines. This is for the HA database but also for the DAO-database.
It is even possible to work with different engines for HA and DAO. <br>
The following engines are possible:
   - mariadb/mysql
   - progresql
   - sqlite3 <br>
 
    To make it easy for the current users: "mysql/mariadb" is the default engine. 
    So there is for them no need to change something in the settings. 
    Further info in DOCS.md<br><br>
   
 - There are 4 extra possible (=optional) entities which you can use to manage and operate your battery(ies):
   - entity from battery: how much energy is going from the battery to the dc-bar (W)
   - entity from pv: how much energy is going from the dc-solar system to the dc-bar (W)
   - entity from ac: how much energy is going from the inverter to the dc-bar (W)
   - entity calculated soc: how what is the expected value of the SoC after this hour (%)<br>

   This expansion is made for customers with hybrid inverters (Deye, Growatt etc.)
so they can better manage there batteries with DAO.<br>
Further info in DOCS.md<br><br>

- DAO stops with the naming of `victron` in the settings. The name of the setting `entity stop victron` is
"deprecated" and will change in the near future to `entity stop inverter`. <br>
For now the old name still works, but you get a warning and a request to change in the logging.


## [V2024.5.6]
- When there is "no battery" configured in the settings the program produced a "list indexout of range".
This error is solved.
- The error messages are now more clear and accurate: correct filename and line nr.
- There was an error in the dasbboard invoking a report (Report\Balans). This error is solved.


## [V2024.5.5]
There is a fourth source added to get day-ahead prices: tibber.
In cases as on June 25th when nordpool and entsoe have don't have epex prices you can get them from Tibber. 

## [V2024.5.4]
- If there are not enough meteo from Meteoserver from the fineley meshed model (Harmonie), 
then the missing data are retrieved from the coarse model (GFS).<br>
Conclusion:the optimization calculation will now always calculate as far as the day-ahead prices are known.
- The meteo log file was name "tibber_...", this is corrected, and now they are named "meteo_..."
- In the dashboard at the menu-option **Home** and the suboption **tabel** now all loggings (not only calc, but also meteo, prices etc.)
are showed. To begin with the most recent one. 
- Meteograph is now showed in the style as defined in the graph-settings
 

## Breaking change
The filenames of the loggings and the images are again (sorry) changed. After installtion of the new version
are the old files not visible anymore in the dashboard. But you can see them with your favorite file-explorer in combination with the Samba add-on. 
## [V2024.5.6]
- When there is "no battery" configured in the settings the program produced a "list indexout of range".
This error is solved.
- The error messages are now more clear and accurate: correct filename and line nr.
- There was an error in the dasbboard invoking a report (Report\Balans). This error is solved.

## [V2024.5.5]
There is a fourth source added to get day-ahead prices: **tibber**.<br>
In cases as on June 25th when Nordpool and Entsoe don't have epex prices you can get them from Tibber. 

## [V2024.5.4]
- If there are not enough meteo from Meteoserver from the fineley meshed model (Harmonie), 
then the missing data are retrieved from the coarse model (GFS).<br>
Conclusion:the optimization calculation will now always calculate as far as the day-ahead prices are known.
- The meteo log file was name "tibber_...", this is corrected, and now they are named "meteo_..."
- In the dashboard at the menu-option **Home** and the suboption **tabel** now all loggings (not only calc, but also meteo, prices etc.)
are showed. To begin with the most recent one. 
- Meteograph is now showed in the style as defined in the graph-settings
 

## Breaking change
The filenames of the loggings and the images are again (sorry) changed. After installtion of the new version
are the old files not visible anymore in the dashboard. But you can see them with your favorite file-explorer in combination with the Samba add-on. 

## [V2024.5.3]
- Fixed the calculation stop when prognose arrays are not equal. Further tests are necessay!!
- The use of the `"entity pv switch"` in solar installations (pv_ac as well as pv_dc) is now optional. 
When entity is not mentioned in the settings in one or more of your pv-installations, that pv-installation(s) will never be turned off. 
- When the program encounters a warning or an error a message is placed in the `notification entity`.
When you have installed the Home Assistant app you can get a notification with that message on your smartphone (zie DOCS.md)
- The filenames of the loggings and the images are again (sorry) changed. After installtion of the new version
are the old files not visible anymore in the dashboard. But you can see them with your favorite file-explorer in combination with the Samba add-on. 


## [V2024.5.2]
- Fixed error retrieving nordpool prices
- There is still a small error in the naming of the logfiles. That will be fixed later.

## [V2024.5.1]
- Hier en daar tekstverduidelijking in DOCS.md
- naamgeving van log- en grafiekbestanden aangepast

## [V2024.5.0]
- Alle output is ondergebracht in het loggingsysteem van Python. Via de instellingen kun je zelf het loglevel instellen
  - debug: veel informatie
  - info (default): wat je nu ook al kreeg
  - warning: waarschuwing bij mogelijke (toekomstige) fouten
  - error: alleen fouten worden gemeld
  Alle output is voorzien van datum/tijd en het bijpassende logging level
- Wanneer door optimalisering PV wordt uitgeschakeld (bij negatieve energieprijzen) wordt in de "niet geoptimlaiseerde grafiek" nu ook
de verwachte PV-productie getoond
- Er zat een foutje in de balans-rapporten van het dashboard. Dit is gerepareerd.
- De code is meer gestroomlijnd. De scheduler is ondergebracht in een aparte module net als de berekeningsmodule.

## [V2024.3.9]
Volgende fouten zijn hersteld:
- er zat een storende fout in `options_vb.json`, zodat een versie installatie niet werkte.
- er zat een fout in een de html-template die een bewerking/berekening initialiseert

## [V2024.3.8]
Een soms optredende fout bij het sommeren van de accutabel zorgde voor het niet doorzetten van de berekende resultaten.
Het sommeren is (tijdelijk) eruit gehaald.

## [V2024.3.7]
- De installatieprocedure is verkort door over te stappen van pip naar uv als tool voor het installeren van Python modules 
- In het laatste uur van het laden van een elektrische auto wordt geen eindtijd doorgegeven aan de entiteit **entity stop charging**
- Format specifier opgenomen voor het invoeren datums bij het ophalen van prijzen.
- DAO is uitgebreid met optionele functionaliteit voor het inplannen van diverse huishuidelijke machines en apparaten (zie DOCS.md)

## [V2024.3.6]
Er is een optionele aanvulling te gebruiken bij het inplannen van het laden van een elektrische auto.
Soms komt het voor het beter is om in een uur maar een deel van dat uur met een beter rendement (en een hoger vermogen)
de auto te laden.
Je kunt nu bij je instellingen een entiteit opgeven (entity stop charging) waarin het programma het eindstip van het 
berekende eindstip opslaat van de oplaadactie in het betreffende (alleen als er niet een heel uur hoeft te worden geladen).
Je zult daar dan zelf in HA een automatisering voor moeten maken die wordt getriggerd op het betreffende tijdstip.
Zie voor informatie en een voorbeeld DOCS.md

## [V2024.3.5]
Bij de uitbreiding van het Run-menu is een storende fout geslopen in het onderdeel waarmee bij nordpool prijzen worden opgehaald.
In deze versie is die fout hersteld.
Alle bestandnamen van all logfiles en grafieken (ook van het ophalen van meteogegevens) zijn nu voorzien van datum-tijd info

## [V2024.3.4]
Er mist een bestand in versie 2024.3.3.
Is hiermee hersteld.

## [V2024.3.3]
Voor de gebruikers die op 3,4 en/of 5 april 2024 geen day ahead prijzen binnen hebben gekregen is in deze versie een kleine
uitbreiding aangebracht in het Run-menu van de webserver. Daarmee kun je nu een vanaf- en tot-datum invullen bij het 
ophalen van de prijsinformatie. Dat werkt bij alle drie de providers (nordpool, entsoe en easyenergy), maar bij nordpool
kun je steeds maar een dag tegelijk ophalen en dat doet hij dan op de ingevulde vanaf-datum.
Meer info in DOCS.md

## [V2024.3.2]
Met de versie 2024.4.0 van Home Asssistant is een nieuw attribuut geintroduceerd (last_reported).  
De nieuwe versie (0.2.1) van module hassapi gaat hier goed mee om, 
de oude versies genereerde foutmeldingen.
Deze versie installeert de nieuwe versie van deze module.

## [V2024.3.1]
In sommige browsers (o.a. Firefox oner Windows) worden oude bestanden van de grafieken getoond.
De naamgeving van de grafieken is aangepast met datum en tijd zodat het probleem over zou moeten zijn.

## [V2024.3.0]
Vanaf deze versie kun je de te gebruiken baseload(s) in de berekening door het systeem zelf laten berekenen.
Zie DOCS.md

## [V2024.2.8]
Er zat een fout in de opgehaalde meteogegevens. In tegenstelling tot de documentatie van 
Meteoserver waren de tijdstippen een uur verschoven. Dit is gecorrigeerd.

## [V2024.2.7]
Er is een extra instelling geintroduceerd voor het inplannen van het opladen van een auto.
De *level margin* (default 0) zorgt desgewenst voor een extra marge voordat opladen wordt ingeplan 
(zie voor meer uitleg DOCS.md)

Heel soms startte een ingeplande berekening een seconde voor het hele uur.
Dat gaf dan veel ongewenste resultaten
Als nu een ingeplande berekening minder dan 10 seconden voor het hele uur start wordt deze 
berekend alsof deze op het hele uur is gestart.

## [V2024.2.6]
De logging van de verwerking van de data voor het laden de van de auto richting HA is nog verder uitgebreid.

## [V2024.2.5]
De logging van de bestaande situatie en de nieuwe situatie voor het laden van de auto
is uitgebreid.

## [V2024.2.4]
De schakelaar is terug voor het aan- en uitzetten van het laden van een elektrische auto

## [V2024.2.3]
Enkele opmaakfoutjes zijn hersteld

## [V2024.2.2]
- De opmaak van de tabel die een overzicht geeft van de invoer van trappen van een e.v. is verbeterd.
- Als "0 ampere" ontbreekt, wordt deze toegevoegd.

## [V2024.2.1]
In deze versie zijn veel zaken toegevoegd en gewijzigd:
- We stappen over op eenzelfde soort **versienummering** als Home Assistant: jaar, maand en opvolgende nummering binnen die maand.
- Voor de rapportages is het niet meer verplicht om de data op te halen bij **Tibber**.
Je kunt dus ook klant zijn bij een andere leverancier (bijv. ANWB). Je haalt dus alle aanroepen voor het ophalen 
van data bij Tibber (`get_tibber_data`) uit de scheduler. In dat geval kan ook het invullen van de url en het token
bij Tibber in de instellingen achterwege blijven. <br>
Om toch goede rapportages te kunnen maken is het dan wel noodzakelijk dat je je verbruiksgegevens van de slimme 
meter bijhoudt in Home Assistant (via de instellingen van het Energiedashboard van HA) en de entiteiten waarmee je deze 
bijhoudt moet je opgeven bij de sectie **report** van de instellingen (zie ook DOCS.md).
- Voor het **opladen van je elektrische auto('s)** kun je nu een lijst met amperages opgeven (eventueel aangevuld met efficiency)
waaruit het programma de voor jouw gunstigste amperages kiest gegeven de prijs van elektriciteit, de capaciteit van je aansluiting
en het tijdstip waarop de auto het jouw gewenste laadniveau moet hebben (zie ook DOCS.md).<br>
**breaking change** Naast de instellingen voor de verschillende laadniveaus moet je nu ook een entiteit ("entity set charging ampere", input_number) opgeven,
waarin het programma de gewenste hoeveelheid ampere kan doorgeven waarmee in het lopende uur geladen moet worden.<br>
- Het invoeren je **baseload** bij je instellingen kan vervallen als het programma jouw baseload kan berekenen uit opgeslagen 
  verbruiken over een voldoende lange periode. <br>
  Daarvoor moet je over minimaal twee maanden de volgende gegevens bijhouden in Home Assistant (via de instellingen van het energiedashboard):
    - de verbruiksgegevens van de slimme meter
    - indien van toepassing het verbruik voor het opladen van je elektrische auto('s)
    - de in- en uitgaande elektriciteit naar en van je thuisbatterij(en)
    - indien van toepassing het verbruik van je wp
    - indien van toepassing het verbruik van je boiler
    - de productie van je zonnepanelen<br>
  
    Bij de instellingen (zie DOCS.md) geef je dan op dat de baseload moet worden berekend en 
  hoeveel dagen terug daarvoor moet worden gerekend. <br>
 **Bonus**: de baseload wordt per weekdag berekend. Met name in het weekend wijkt de baseload af van het 
weekgemiddelde en de verwachting is dat dit de nauwkeurigheid van de voorspellingen ten goede komt.
- Bij een flink aantal instellingen zijn "**default**" (standaard) instellingen geintroduceerd. Dat betekent dat 
je deze instellingen kunt weglaten in het instellingenbestand als de standaard instelling voor jou voldoet.
Belangrijkste instelling die weggelaten kan worden als je het programma als addon op je HomeAssistant-machine
installeert zijn de instellingen voor de communicatiemet Home Assistant. Dit regelt dan de Home Assistant 
supervisor voor je. In DOC.md is een tabel opgenomen van alle instellingen inclusief de default-instelling (voor zover van toepassing)
- De rapportage functie is uitgebreid met een rapportage van je **energiebalans**:
![img_11.png](images/img_11.png)
![img_12.png](images/img_12.png)
Om dat goed te laten werken zul je in Home Assistant (net als voor het berekenen van de baseload) alle verbruiksgegevens
van diverse meters en verbruikers moeten bijhouden(zie voor verdere uitleg DOCS.md)
- Na een berekening is kreeg je al een hele uitdraai van allerlei berekeningen.
Met name de tabel met de in- en uitgaande energie en de efficiency van je thuisbatterij(en) riep hier en daar wat vragen op.
Deze tabel is nu aangepast (de berekeningen zijn hetzelfde):
```   
   In- en uitgaande energie per uur batterij: Accu1
   
   uur   ac->    eff   ->dc pv->dc   dc->    eff  ->bat  o_eff    SoC
          kWh      %    kWh    kWh    kWh      %    kWh      %      %
    15   0.00     --   0.00   0.00   0.00     --   0.00     --  43.50
    16   0.00     --   0.00   0.00   0.00     --   0.00     --  43.50
    17  -1.20  95.50  -1.26   0.00  -1.26  98.00  -1.28  93.59  39.23
    18  -3.60  93.40  -3.85   0.00  -3.85  98.00  -3.93  91.53  26.12
    19  -2.26  94.90  -2.39   0.00  -2.39  98.00  -2.43  93.00  18.00
    20   0.00     --   0.00   0.00   0.00     --   0.00     --  18.00
    21   0.00     --   0.00   0.00   0.00     --   0.00     --  18.00
    22   0.00     --   0.00   0.00   0.00     --   0.00     --  18.00
    23   0.00     --   0.00   0.00   0.00     --   0.00     --  18.00
Totaal  -7.06     --  -7.50   0.00  -7.50     --  -7.65     --       
```
## [Unreleased]
De volgende zaken staan nog op de todo lijst:
- Alle uitvoer omzetten naar logger 
- dashboard afmaken

## [V0.4.73]
In deze versie zijn de volgende zaken gewijzigd:
- fout bij niet melden van datum/tijd van notificatie opgelost
- op een aantal punten is de documentatie verhelderd
- optioneel: <br>
  - het basisverbruik (baseload) kan berekend worden uit de geschiedenis (zie DOCS.md)
  - voor het goed kunnen berekenen van de baseload dient een lijst met sensoren ingevuld te worden 
    het verbruik/productie van inkoop, maar ook van de batterij(en) en 
    de stuurbare verbruikers/producenten registreren.

## [V0.4.72]
- apparmor is geimplementeerd
- er is icon toegevoegd voor de zijbalk 

## [V0.4.70]
- apparmor is (gedeeltelijk) geactiveerd
- het creeeren van de tables en de benodigde inhoud in de database wordt 
na installatie of update van de addon door de software uitgevoerd

## [V0.4.61]
- kleuren DOCS.md staan nu goed
- addon kan ook voor niet-admin gebruikers in zijbalk worden geplaatst
- notificatie datum/tijd moet nu werken
- in titels wordt nu alleen nog maar "Optimization" gebruik

## [V0.4.57] 2024-01-20
### Added
- Ingress is toegevoegd aan de presentatie van de addon via het dashboard ("toon zijbalk")
### Changed
- README.md is gesplitst:
  - een korte inleiding in het programma (heet nog steeds README.md)
  - een uitgebreide handleiding (DOCS.md) die ook benaderd kan worden via "documentatie" vanuit de addon

## [V0.4.56] 2024-01-14
### Changed
Addon is met volledige ondersteuning voor 64 bit Intel/AMD Processor

## [v0.4.5] - 2024-01-09

### Changed

Het programma is ondergebracht in een addon van Home Assistant.<br>
Voor de addon is alle software geplaatst onder de directory "dao". <br>
Alle documentatie is verplaatst naar docs\MANUAL.md

De volgende update query moet in de database "day_ahead" worden doorgevoerd:
````
UPDATE `day_ahead`.`variabel` SET `code`='pv_ac', `name`='Zonne energie AC' WHERE  `id`=15;
````
### Added
De volgende variabelen worden toegevoegd aan het bestand `variabel`:
```
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (17, 'pv_dc', 'Zonne energie DC', 'kWh');
```
In options.json kun je nu het maximale vermogen opgeven van je netwerk aansluiting.
Zie DOCS.md

##[v0.4.0] - 2023-10-15

### Removed
De functionaliteit om via de websocket in HA een berekening te starten is verwijderd.
Dat kan nu via een rest-command: `/api/run`


## [v0.3.1] - 2023-09-12

### Added
- je kunt nu de grafische stijl definieren o.a. darkmode. (zie DOCS.md, graphics) 
- je kunt het presenteren van de grafieken na het uitvoeren van een berekening aan/uit zetten. (zie DOCS.md, graphics)
- de volgende aanvullende python modules moeten worden geinstalleerd:
````
  pip3 install gunicorn ephem
````
- het protocol voor de api en de ws richting Home Assistant is instelbaar (zie in DOCS.md, bij het onderdeel "Home Assistant") 
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
  grafieken kunt maken (zie DOCS.md)
  * je kunt met een api call een berekening of bewerking uitvoeren. Deze nieuwe functionaliteit zal de
  websocket interface vervangen.
  * de "reports" zijn uitgebreid met meer perioden en bij de perioden waar ook de prognose van toepassing
  van toepassing is, kun je "prognose" aan/uit zetten (zie DOCS.md)
  * je kunt via de web-gui alle berekeningen en bewerkingen uitvoeren en je krijgt direct 
  de logging van het resultaat te zien (zie DOCS.md) 

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
  Als dit goed bevalt, zal het ook worden geimplementeerd voor het ontladen (van `dc` naar `ac`) en van `dc` naar batterij en vice versa.<br>
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
    - bij 3 tot 8 rijen wordt er wel gerekend, maar wordt er wel een waarschuwing afgegeven 
    
- een changelog
- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Fixed

- Tijdens een lopend uur (dus met een eerste uur wat minder dan 60 minuten duurt)
gaf het programma verkeerde resultaten voor dat eerste uur. Dit is gefixed.
- ws parameter overal omgezet naar self.w_socket
- naar keuze datum-tijd of alleen tijd input helper voor aangeven wanneer een elektrische auto geladen moet zijn

### Changed
    
- laden auto wordt alleen uitgezet als auto thuis is (en aangesloten) 
- ongebruikte instellingen uit DOCS.md gehaald
- navigatieknoppen in webserver bij "home" omgezet
- menuoptie **Meteo** in webserver voorzien van toelichting "in ontwikkeling"
- notificatie via Home Assistant toegevoegd. Zie voor meer informatie DOCS.md bij **notification entity**
- in het instellingenbestand options.json is de naam van de entity aanduiding veranderd: <br>
`"entity ready time"` wordt `"entity ready datetime"`
- aanvullingen en wijzigingen in DOCS.md


### Issues
Als het programma draait in scheduler-mode wordt een websocket geopend naar HA zodat vanuit HA een 
optimaliseringsberekening kan worden gestart.
Als HA stopt (bijv. voor een update) dan blijft de websocket "in de lucht" maar is niet meer effectief.

### Removed

- prog/da_webserver.py verwijderd

### Deprecated

- geen

### Security

- geen
