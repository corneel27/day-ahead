# DAY AHEAD

## Inleiding
Het programma Day Ahead voert de volgende acties, berekeningen en bewerkingen uit:

* ophalen dynamische energie tarieven bij Entsoe en/of NordPool
* ophalen van je verbruiksgevens van de vorige dag(en) bij Tibber
* ophalen van meteogegevens bij Meteoserver
* berekenen van de optimale inzet van een aanwezige accu, wp-boiler en elektrische auto
---
## Optimalisering
De optimalisering van het verbruik gebeurt met behulp van een generiek wiskundig algoritme
met de naam "mixed-integer lineair programming". Meer daarover kun je lezen op de 
website die ook het algoritme en allerlei bijbehorende hulpmiddelen aanbiedt:
https://python-mip.com/

Deze implementatie berekent een optimale inzet van je accu, boiler en ev, waarbij naar keuze wordt 
gestreefd naar minimalisering van je kosten, naar minimalisering van je inkoop (nul op de meter) of 
een combinatie van beide. Daarvoor worden de volgende zaken berekend:
* uit de prognose van het weer (globale straling) per uur wordt een voorspelling berekend van de productie van je 
zonnepanelen
* met de tarieven van je dynamische leverancier (incl. opslag, belastingen en btw) worden per uur de kosten 
en opbrengsten van het verbruik cq teruglevering berekend
* m.b.v. de karakteristieken van je accu worden per uur het laad- cq ontlaadvermogen berekend
* wanneer moet je elektrische auto worden geladen

Dit resulteert (in de mip-module) in enkele honderden vergelijkingen en idem dito variabelen(onbekenden). 
Aan de hand van de gekozen strategie kan met behulp van het algoritme de meest optimale setting van al deze 
variabelen worden berekend. Dit zijn:
* per uur verbruik en kosten op de inkoopmeter
* per uur teruglevering en opbrengst op de inkoopmeter
* per uur laad- cq ontlaadvermogen van de accu en de SOC aan het einde van het uur
* tijdstip waarop de boiler moet worden opgewarmd
* uurvakken waarin de elektrische auto moet worden geladen

Het geheel kan grafisch worden weergegeven:
![optimalisering](./images/optimum2300.png "optimalisering")

Of in tabelvorm:
````
         uur  accu_in  accu_out     soc  con_l  c_t_t  c_t_n  bas_l   boil     wp     ev     pv  kos_l  kos_t  k_t_n   b_tem
0      23.00     0.00      0.00   20.00   0.55   0.00   0.00   0.55   0.00  -0.00   0.00   0.00   0.15  -0.00  -0.00   37.50
1       0.00     0.00      0.00   20.00   0.68   0.00   0.00   0.68   0.00  -0.00   0.00   0.00   0.17  -0.00  -0.00   37.10
2       1.00     0.00      0.00   20.00   1.93   0.00   0.00   1.03   0.90  -0.00   0.00   0.00   0.49  -0.00  -0.00   48.36
3       2.00     0.00      0.00   20.00   1.18   0.00   0.00   1.18   0.00  -0.00   0.00   0.00   0.29  -0.00  -0.00   47.96
4       3.00     0.22      0.00   20.71   1.76   0.00   0.00   0.65   0.00   0.23   0.66   0.00   0.41  -0.00  -0.00   47.56
5       4.00     4.50      0.00   35.02   7.64   0.00   0.00   0.54   0.00   0.30   2.30   0.00   1.63  -0.00  -0.00   47.16
6       5.00     0.00      0.00   35.02   0.63   0.00   0.00   0.63   0.00  -0.00   0.00   0.00   0.15  -0.00  -0.00   46.76
7       6.00     0.00      0.00   35.02   0.70   0.00   0.00   0.70   0.00   0.00   0.00   0.00   0.19  -0.00  -0.00   46.36
8       7.00     0.00      0.00   35.02   0.64   0.00   0.00   0.65   0.00  -0.00   0.00   0.01   0.18  -0.00  -0.00   45.96
9       8.00     0.00      0.00   35.02   0.11   0.00   0.00   0.34   0.00  -0.00   0.00   0.23   0.03  -0.00  -0.00   45.56
10      9.00     0.00      0.00   35.02   0.00   1.28   0.00   0.31   0.00  -0.00   0.00   1.59   0.00  -0.34  -0.00   45.16
11     10.00     4.50      0.00   49.32   2.46   0.00   0.00   0.16   0.00   0.23   0.00   2.42   0.55  -0.00  -0.00   44.76
12     11.00     4.50      0.00   63.62   2.37   0.00   0.00   0.38   0.00   0.30   0.00   2.81   0.51  -0.00  -0.00   44.36
13     12.00     4.50      0.00   77.93   2.91   0.00   0.00   0.69   0.00   0.30   0.00   2.58   0.63  -0.00  -0.00   43.96
14     13.00     4.50      0.00   92.23   3.80   0.00   0.00   0.59   0.00   0.30   0.00   1.59   0.83  -0.00  -0.00   43.56
15     14.00     0.00      0.00   92.23   0.21   0.00   0.00   1.13   0.00   0.23   0.00   1.14   0.05  -0.00  -0.00   43.16
16     15.00     0.00      0.00   92.23   0.00   0.97   0.00   0.93   0.00  -0.00   0.00   1.90   0.00  -0.23  -0.00   42.76
17     16.00     0.00      0.00   92.23   0.00   0.46   0.00   0.53   0.00  -0.00   0.00   0.99   0.00  -0.13  -0.00   42.36
18     17.00     0.00      4.50   74.17   0.00   4.21   0.00   1.02   0.00  -0.00   0.00   0.73   0.00  -1.34  -0.00   41.96
19     18.00     0.00      4.50   56.12   0.00   5.26   0.00   0.51   0.00  -0.00   0.00   1.27   0.00  -1.79  -0.00   41.56
20     19.00     0.00      4.50   38.06   0.00   3.92   0.00   0.62   0.00  -0.00   0.00   0.04   0.00  -1.37  -0.00   41.16
21     20.00     0.00      4.50   20.00   0.00   3.88   0.00   0.62   0.00  -0.00   0.00   0.00   0.00  -1.25  -0.00   40.76
22     21.00     0.00      0.00   20.00   0.62   0.00   0.00   0.62   0.00  -0.00   0.00   0.00   0.18  -0.00  -0.00   40.36
23     22.00     0.00      0.00   20.00   0.55   0.00   0.00   0.55   0.00  -0.00   0.00   0.00   0.15  -0.00  -0.00   39.96
24     23.00     0.00      0.00   20.00   0.55   0.00   0.00   0.55   0.00  -0.00   0.00   0.00   0.15  -0.00  -0.00   39.56
````

---

### Vereisten
Het programma day_ahead.py is een python-programma dat alleen draait onder python versie 3.8 of hoger. <br/>
Het programma draait alleen als de volgende modules zijn geïnstalleerd met pip3. <br/>
Je installeert de benodigde modules als volgt:<br/>
`pip3 install mip pandas entsoe-py mysql-connector hassapi matplotlib nordpool`
  

Het programma veronderstelt de volgende zaken aanwezig/bereikbaar:

**Home Assistant** actueel bijgewerkte laatste versie

**MariaDB** (best geïnstalleerd als addon van HA), waar ook HA gebruik van maakt  

**phpMyAdmin** (best geïnstalleerd als addon van HA), met toegang tot de MariaDB server  

**database "day_ahead"** een aparte database in MariaDB voor dit programma met daarin:  
	
* een user die alle rechten heeft (niet root) 
* tabel **variabel**:<br/>
  * Deze maak je met de query: <br/>
    CREATE TABLE \`variabel\` ( <br>
     \`id\` INT(10) UNSIGNED NOT NULL AUTO_INCREMENT, <br/>
     \`code\` CHAR(10) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci',<br/>
     \`name\` CHAR(50) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci',<br/>
     \`dim\` CHAR(10) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci',<br/>
      PRIMARY KEY (\`id\`) USING BTREE, UNIQUE INDEX \`code\` (\`code\`) USING BTREE,<br/>
      UNIQUE INDEX \`name\` (\`name\`) USING BTREE ) COLLATE='utf8mb4_unicode_ci'<br/> 
      ENGINE=InnoDB <br/>
      AUTO_INCREMENT=1;
  * Query voor het vullen van de inhoud van tabel "variabel" <br/>
   INSERT INTO \`variabel\` (\`id\`, \`code\`, \`name\`, \`dim\`) VALUES (1, 'cons', 'consumed', 'kWh'); <br/>
   INSERT INTO \`variabel\` (\`id\`, \`code\`, \`name\`, \`dim\`) VALUES (2, 'prod', 'produced', 'kWh'); <br/>
   INSERT INTO \`variabel\` (\`id\`, \`code\`, \`name\`, \`dim\`)VALUES (3, 'da', 'price', 'euro/kWh'); <br/>
   INSERT INTO \`variabel\` (\`id\`, \`code\`, \`name\`, \`dim\`) VALUES (4, 'gr', 'globale straling', 'J/cm2');<br/> 
   INSERT INTO \`variabel\` (\`id\`, \`code\`, \`name\`, \`dim\`) VALUES (5, 'temp', 'temperatuur', '°C'); <br/>
   INSERT INTO \`variabel\` (\`id\`, \`code\`, \`name\`, \`dim\`) VALUES (6, 'solar_rad', 'PV radiation', 'J/cm2');<br/> 
 * tabel **values**:<br/>
   * Deze maak je aan met de volgende query: <br/>
    CREATE TABLE \`values\` (<br/>
    \`id\` BIGINT(20) UNSIGNED NOT NULL  AUTO_INCREMENT,<br/>
    \`variabel\` INT(10) UNSIGNED NOT NULL DEFAULT '0', <br/>
    \`time\` BIGINT(20) UNSIGNED NOT NULL DEFAULT '0', <br/>
    \`value\` FLOAT NULL DEFAULT NULL, <br/>
    PRIMARY KEY (\`id\`) USING BTREE, <br/>
    UNIQUE INDEX \`variabel_time\` (\`variabel\`, \`time\`) USING BTREE, <br/>
    INDEX \`variabel\` (\`variabel\`) USING BTREE, <br/>
    INDEX \`time\` (\`time\`) USING BTREE ) COLLATE='utf8mb4_unicode_ci' <br/>
    ENGINE=InnoDB <br/>
    AUTO_INCREMENT=1;<br> 
   * De inhoud van values bouw je zelf op met het ophalen van de diverse gegevens  
---
## Programma starten
Je kunt het programma draaien en testen via een terminalvenster op je laptop/pc:   
	`python3 day_ahead.py [parameters]`  
  
Start je het programma zonder parameters dan worden de databases "geopend" en dan wacht het programma tot een opdracht uit  de takenplannen (zie hieronder) moet worden uitgevoerd.   
De volgende parameters kunnen worden gebruikt:  
**debug**  
  alleen van toepassing in combinatie met het onderdeel "calc" (zie hierna), voert wel de berekening uit maar zet de berekende resultaten niet door naar de apparaten  
**prices**  
  haalt de day ahead prijzen op nordpool, entsoe of easyenergy. Deze bron stel je in via options.json (prices).<br>
  Je kunt dit commando uitbreiden met een of twee extra datum-parameters: een start- en een eind datum. Laat je de tweede parameters achterwege dan wordt morgen als einddatum gekozen.
  Je kunt deze faciliteit gebruiken om een prijshistorie in de database op te bouwen.<br>
  Format: `jjjj-mm-dd` <br>
  Deze functionaliteit werkt alleen bij de bron easyenergy!<br>
  Voorbeeld ` python day_ahead.py prices 2022-09-01 [2023-03-01]`
    
**tibber**  
  haalt de verbruiks- en productiegegevens op bij tibber  
  Dit commando kan met een extra parameter worden gestart namelijk een datum. In dat geval worden de verbruiksdata opgehaald vanaf de ingegeven datum. <br>
  Format: `jjjj-mm-dd` <br>
  Voorbeeld: `python da_ahead.py tibber 2023-02-01`
**calc**  
  voert de "optimaliseringsberekening" uit: 
* haalt alle data (prijzen, meteo) op uit de database <br> 
* berekent de optimale inzet van de accu, boiler, warmtepomp en ev <br> 
* berekent de besparing tov een reguliere leverancier <br>
* berekent de besparing zonder optimalisering met alleen dynamische prijzen<br>
* berekent de besparing met optimalisering met dynamische prijzen <br>
* presenteert een tabel met alle geprognoticeerde uurdata <br>
* presenteert een grafiek met alle geprognoticeerde uurdata

**scheduler**  
 Hiermee komt het programma in een loop en checkt iedere minuut of er een taak moet worden uitgevoerd.<br>
 Dit wordt ook bereikt door het programma zonder parameter op te starten.
---
### Instellingen  
  
 Het bestand options.json bevat alle instellingen voor het programma day_ahead.py. 
Opmerking: alle instellingen die beginnen met "!secret" staan komen in het bestand `secrets.json`te staan  met de key die hier achter !secret staat  
**homeassistant**
 * url : de url waar de api van je home assistant bereikbaar is  
 * token: om de api te kunnen aanroepen is er  een token nodig.  
               Deze kun je genereren in je Home Assistant website

**database da**:  de database voor het day ahead programma  
 * server: ip adres van de server (waar mariadb draait)  
 * database: naam van de database  
 * port: poort op de server (meestal 3306)  
 * username: user name  
 * password: wachtwoord

**database ha**: de database van Home Assistant  
 * server: ip adres van de server (waar mariadb draait)  
 * database: naam van de database  
 * port: poort op de server (meestal 3306)  
 * username: user name  
 * password: wachtwoord
 
**meteoserver-key**: de meteodata worden opgehaald bij meteoserver  
    Ook hiervoor heb je een key nodig. <br>
    Je genereert deze key (token) als volgt: 
 * website: https://meteoserver.nl/login.php 
 * registreer je als gebruiker 
 * daarna klik je op Account, tabje "API Beheer" en je ziet je key staan<br>
Opmerking: je kunt gratis maximaal 500 dataverzoeken per maand doen, we doen er maar 4 per dag = max 124 per maand

**prices**  
 * source day ahead: waar wil je je day ahead prijzen vandaan halen. Je hebt de keuze uit drie bronnen:
   * nordpool
   * entsoe
   * easyenergy<br>

    Als je kiest voor **entsoe** dan moet je hieronder een api key invullen.
 * entsoe-api-key*  
	Deze key genereer je op de site van entsoe en heb je nodig om daar de energieprijzen van de volgende op te halen.
    Je genereert deze key (token) als volgt: 
 * Website: https://transparency.entsoe.eu      
 * Registreer je als gebruiker 
 * Klik op "My Account Settings"  
 * Klik op "Generate a new token"


 * regular high: het hoge tarief van een "reguliere" oude leverancier,
   ex btw, kaal, euro per kWh
 * regular low: idem het "lage" tarief, ex btw, kaal , euro per kWh
     switch to low: tijdstop waarop je omschakelt naar "laag tarief" (meestal 23 uur)
  * energy taxes delivery: energiebelasting op verbruik ex btw, euro per kWh  
           2022-01-01 : 0.06729,  
           2023-01-01 : 0.12599  
   * energy taxes redelivery: energiebelasting op teruglevering ex btw, euro per kWh  
           2022-01-01: 0.06729,  
           2023-01-01: 0.12599  
    * cost supplier delivery : opslag leverancier euro per kWh, ex btw  
        bijv voor Tibber:
        * 2022-01-01: 0.002
        * 2023-03-01: 0.018
   * cost supplier redelivery:  opslag leverancier voor teruglevering per kWh, ex btw  
        bijv voor Tibber:
        * 2022-01-01: 0.002
        * 2023-03-01: 0.018
   * vat:    btw in %  
      * 2022-01-01: 21
      * 2022-07-01: 9
      * 2023-01-01: 21,  
   
   * last invoice: datum laatste jaarfactuur en/of de begindatum van je contractjaar (formaat "yyyy-mm-dd")
   * tax refund: kun je alles salderen of is je teruglevering hoger dan je verbruik  (True of False) 

**strategy** het programma kent drie strategieën die je kunt inzetten om het voor jou optimale energieverbruik
en teruglevering te realiseren.<br>
Je kiest er één uit door daar **True** achter in te vullen.
De drie strategieën zijn:
  * minimize cost: True/False<br>
    Als je deze kiest worden je accu en je verbruiken zo ingezet dat deze leiden tot de laagste 
    kosten (= hoogste opbrengst)
  * minimize delivery: True/False<br>
    Deze strategie minimaliseert je levering (kWh) en streeft daarmee naar "nul op de meter"
  * combine minimize cost delivery: True/False<br>
    Hiermee worden de twee bovenstaande strategieën gecombineerd tot een nieuwe hybride strategie, 
    waarbij enerzijds wordt gestreefd naar lage kosten maar ook naar "nul op de meter".
    Er is een parameter die je moet invullen om in deze strategie tot een oplossing te komen:
  * cost marge combination: dit is het "verlies" dat je maximaal accepteert om tot een "nul op de meter"-oplossing te komen.

**boiler**  instellingen voor optimalisering van het elektraverbruik van je warmwater boiler
   * boiler present: True of False. Als je False invult worden onderstaande boiler-instellingen genegeerd.
   * entity actual temp. : entiteit in ha die de actuele boilertemp. presenteert  
   * entity setpoint: entiteit die de ingestelde boilertemp. presenteert  
   * entity hysterese: entiteit die de gehanteerde hysterese voor de boiler presenteert  
   * cop: cop van de boiler bijv 3: met 1 kWh elektriciteit wordt 3 kWh warm water gemaakt (een elektrische boiler heeft een cop = 1)
   * cooling rate: gemiddelde afkoelsnelheid van de boiler in K/uur  
   * volume: inhoud van de boiler in liter  
   * heating allowed below: temperatuurgrens in °C  waaronder de boiler mag worden opgewarmd  
   * elec. power: elektrisch vermogen van de boiler in W  
   * activate entity: entiteit (meestal van een inputhelper) waarmee de boiler opwarmen wordt gestart  
   * activate service: naam van de service van deze entiteit  

**heating**:  dit onderdeel is nog in ontwikkeling  
   * heater present : True of False. Als je False invult worden onderstaande heater-instellingen genegeerd.
   * degree days factor: kWh/K.dag hoeveel thermische kWh is er nodig per graaddag<br>
     zet deze op 0 als je geen wp hebt
   * stages : een lijst met vermogens schijven van de wp: hoe hoger het vermogen hoe lager de cop
     * max_power: het maximum elektrische vermogen van de betreffende schijf in W
     * cop: de cop van de wp behorende bij deze schijf. Dus een cop van 7 met een vermogen van 225 W 
        betekent een thermisch vermogen van 7 x 225 = 1575 W
   * entity adjust heating curve: entiteit waarmee de stooklijn kan worden verschoven
   * adjustment factor: float K/10% Het aantal graden voor de verschuiving van de stooklijn als de actuele 
      da prijs 10% afwijkt van het daggemiddelde

**battery**: de gegevens en de instellingen van geen, een of meer accu's
Je kunt de accu instellingen herhalen als je meer dan een accu hebt, of je laat de lijst leeg (geen accu)
   * name: de naam van de accu (komt terug in rapportages)
   * entity actual level: entiteit die de actuele soc van de accu presenteert  
   * capacity: capaciteit van de accu in kWh  
   * lower limit: onderste soc limiet (tijdelijk)  
   * upper limit: bovenste soc limiet  
   * optimal lower level: onderste soc limiet voor langere tijd  
   * entity min soc end opt: entity in home assistant (input_number), waarmee je de 
     minimale soc in procenten kunt opgeven die de batterij aan het einde van de berekening moet hebben 
   * entity max soc end opt: entity in home assistant (input_number), waarmee je de
     maximale soc in procenten kunt opgeven die de batterij aan het einde van de berekening moet hebben <br>
     **opmerking:** met deze twee instellingen kunt u bereiken dat de accu aan het eind "leeg" of "vol" is. Een lage accu 
     kan zinvol zijn als je de dag(en) na de berekening veel goedkope stroom en/of veel pv productie verwacht. Een volle batterij 
     kan zinvol zijn als je juist dure stroom en/of weinig eigen pv-productie verwacht. 
   * max charge power: maximaal laad vermogen in kW  
   * max discharge power: maximaal ontlaadvermogen in kW  
   * minimum power: minimaal laad/ontlaadvermogen
   * ac_to_dc efficiency: efficiency van de inverter bij omzetten van ac naar dc (factor van 1)
   * dc_to_ac efficiency: efficiency van de omvormer bij omzetten van dc naar ac (factor van 1)
   * dc_to_bat efficiency: efficiency van het laden van de batterij vanuit dc (factor van 1)
   * bat_to_dc efficiency: efficiency van het ontladen van de batterij naar dc (factor van 1)
   * cycle cost : afschrijfkosten (in euro) van het laden of ontladen van 1 kWh  
   * entity set power feedin: entiteit waar je het te laden / ontladen vermogen inzet  
   * entity set operating mode: entiteit waarmee je het ess aan/uit zet  
   * entity stop victron: entiteit waarmee je datum/tijd opgeeft wanneer het ess moet stoppen  
   * entity balance switch: entiteit waarmee je de victron op "balanceren" zet (overrult set power feedin)
   * solar lijst van pv installaties die direct invoeden op je batterij (mppt)<br>
     Per pv installatie geef je de volgende gegevens op:
       * tilt : de helling van de panelen in graden; 0 is vlak, 90 is verticaal  
       * orientation : orientatie in graden, 0 = zuid, -90 is oost, 90 west  
       * capacity: capaciteit in kWp  
       * yield: opbrengstfactor van je panelen als er 1 J/cm2 straling op je panelen valt in kWh/J/cm2  
        Deze bereken je als volgt: <br>
         * Een eerste schatting van de jaarlijkse opbrengst van je panelen is : Wp x 0,85.
Dus als je 6000 Wp hebt dan is je geschatte jaaropbrengst = 6000 x 0,85 = 5100 kWh. <br>
         * De gemiddelde direct opvallende straling gesommeerd over een jaar is "ongeveer" 400.000 J/cm2.<br>
         * Als jouw "geschatte" jaaropbrengst van je panelen stelt op 5000 kWh dan wordt de yield:
5000 / 400.000 = 0,0125 kWh/J/cm2<br>
         * Zo kun je voor iedere pv installatie een eerste schatting maken.<br>
         * Na een week kun je de berekende geprognotiseerde productie vergelijken met de werkelijke productie en dienovereenkomstig de yield aanpassen:
stel geprognoticeerd/berekend = 50 kWh gemeten is : 40 kWh dan wordt de nieuwe yield = oude_yield * 40 / 50  <br>
           
**solar** lijst van pv installaties die dmv een omvormer (of mini omvormers) direct invoeden op je ac installatie< br>
     Per pv installatie geef je de volgende gegevens op:
* tilt : de helling van de panelen in graden; 0 is vlak, 90 is verticaal  
* orientation : orientatie in graden, 0 = zuid, -90 is oost, 90 west  
* capacity: capaciteit in kWp  
* yield: opbrengstfactor van je panelen als er 1 J/cm2 straling op je panelen valt in kWh/J/cm2 (zie hierboven)  
 
**electric vehicle** dit is voorlopig gebaseerd op een Volkswagen auto die kan worden bereikt met WeConnect. 
    Andere auto's graag in overleg toevoegen. Ook hier kun je kiezen uit een lege lijst of een of meer auto's
   * name: de naam van de auto (komt straks terug in rapportages)
   * capacity: capaciteit accu in kWh,   
   * entity position: entiteit die aangeeft of de auto "thuis" (home) is  
   * entity max amperage: entiteit die het max aantal amperes aangeeft waarmee kan worden geladen  
   * entity actual level: entiteit die aangeeft hoe ver de auto is geladen (in %)  
   * entity plugged in: entiteit die aangeeft of de auto is ingeplugged  
   * charge scheduler: oplaad scheduler  
   * entity set level: entiteit van een input help die aangeeft tot welk niveau moet worden geladen in %  
   * entity ready time: entiteit van een input tijd hoe laat de auto op het gewenste niveau moet zijn  
   * charge switch:  entiteit waarmee het laden aan/uit kan worden gezet 

 **tibber** 
 * api url : url van de api van tibber  
 * api_token : het token van de api van tibber  
  Deze vraag je als volgt op:  
   * log in met je account op https://developer.tibber.com/explorer  
   * de token staat boven onder de balk 
 
 **scheduler** taken planner. 
 Het programma maakt gebruik van een eenvoudige takenplanner. <br/>
 De volgende taken kunnen worden gepland:
   * get_meteo_data: ophalen van meteo gegevens bij meteoserver  
   * get_tibber_data: ophalen van verbruiks- en productiegegevens per uur bij tibber  
   * get_day_ahead_prices: ophalen van day ahead prijzen bij nordpool cq entsoe  
   * calc_optimum: bereken de inzet accu, boiler en auto voor de komende uren,  
            de inzet van het lopende uur wordt doorgezet naar de betreffende apparaten (tenzij het programma is 
          gestart met de parameter debug)<br/>

De key heeft het formaat van "uumm": uu is het uur, mm is de minuut  
de uren en minuten zijn ofwel een twee cijferig getal of XX  
ingeval van XX zal de taak ieder uur cq iedere minuut worden uitgevoerd.<br/>
Bijvoorbeeld : <br/>`"0955": "get_meteo_data"`: de meteodata worden opgehaald om 9 uur 55<br/>
`"xx00": "calc_optimum"`: ieder uur exact om "00" wordt de optimaliseringsberekening uitgevoerd.
