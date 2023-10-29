# DAY AHEAD OPTIMALISERING

## Inleiding
Het programma Day Ahead Optimalisering (DAO) voert de volgende acties, berekeningen en bewerkingen uit: 

* ophalen dynamische energie tarieven bij Entsoe en/of NordPool
* ophalen van je verbruiksgevens van de vorige dag(en) bij Tibber
* ophalen van meteogegevens bij Meteoserver
* berekenen van de optimale inzet van een aanwezige batterij, wp-boiler en elektrische auto
---
## Optimalisering
De optimalisering van het verbruik gebeurt met behulp van een generiek wiskundig algoritme
met de naam "Mixed-Integer lineair Programming". Meer daarover kun je lezen op de 
website die ook het algoritme en allerlei bijbehorende hulpmiddelen aanbiedt:
https://python-mip.com/

Deze implementatie berekent een optimale inzet van je batterij, boiler en e.v., waarbij naar keuze wordt 
gestreefd naar minimalisering van je kosten, naar minimalisering van je inkoop (nul op de meter) of 
een combinatie van beide. Daarvoor worden de volgende zaken berekend:
* uit de prognose van het weer (globale straling) per uur wordt een voorspelling berekend van de productie van je 
zonnepanelen
* met de tarieven van je dynamische leverancier (incl. opslag, belastingen en btw) worden per uur de kosten 
en opbrengsten van het verbruik c.q. teruglevering berekend
* m.b.v. de karakteristieken van je accu worden per uur het laad- c.q. ontlaadvermogen berekend
* wanneer moet je elektrische auto worden geladen

Dit resulteert (in de mip-module) in enkele honderden vergelijkingen en idem dito variabelen(onbekenden). 
Aan de hand van de gekozen strategie kan met behulp van het algoritme de meest optimale setting van al deze 
variabelen worden berekend. Dit zijn:
* per uur verbruik en kosten op de inkoopmeter
* per uur teruglevering en opbrengst op de inkoopmeter
* per uur laad- cq ontlaadvermogen van de batterij en de SoC aan het einde van het uur
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

## Vereisten
Het programma day_ahead.py is een python-programma dat alleen draait onder python versie 3.8 of hoger. <br/>
Het programma draait alleen als de volgende modules zijn geïnstalleerd met pip3. <br/>
Je installeert de benodigde modules als volgt:<br/>
````
pip3 install mip pandas entsoe-py mysql-connector hassapi matplotlib nordpool flask gunicorn ephem
````

Het programma veronderstelt de volgende zaken aanwezig/bereikbaar:

### **Home Assistant**<br>
Actueel bijgewerkte laatste versie.

### **MariaDB**<br>
Best geïnstalleerd als addon van HA waar ook HA gebruik van maakt. Zet hierbij poort 3306 open door in de Add-on dit poortnummer in te vullen bij het onderdeel Netwerk. Indien het leeg blijft is de MariaDB database alleen bereikbaar voor HA.

### **phpMyAdmin**<br>
Best geïnstalleerd als addon van HA met toegang tot de MariaDB server.

### **database "day_ahead"**<br>
Een aparte database in MariaDB voor dit programma met daarin:  
	
* een user die alle rechten heeft (niet root) 
* tabel **variabel**:<br/>

  * Deze maak je met de query: <br/>
````
    CREATE TABLE `variabel` (
    `id` INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
    `code` CHAR(10) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci',
    `name` CHAR(50) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci',
    `dim` CHAR(10) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci',
    PRIMARY KEY (`id`) USING BTREE, UNIQUE INDEX `code` (`code`) USING BTREE,
    UNIQUE INDEX `name` (`name`) USING BTREE ) COLLATE='utf8mb4_unicode_ci' 
    ENGINE=InnoDB
    AUTO_INCREMENT=1;
````
  * Query voor het vullen van de inhoud van tabel "variabel" <br/>
````  
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (1, 'cons', 'Verbruik', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (2, 'prod', 'Productie', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`)VALUES (3, 'da', 'Tarief', 'euro/kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (4, 'gr', 'Globale straling', 'J/cm2'); 
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (5, 'temp', 'Temperatuur', '°C');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (6, 'solar_rad', 'PV radiation', 'J/cm2'); 
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (7, 'cost', 'cost', 'euro');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (8, 'profit', 'profit', 'euro');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (9, 'bat_in', 'Batterij in', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (10, 'bat_out', 'Batterij uit', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (11, 'base', 'Basislast', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (12, 'boil', 'Boiler', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (13, 'wp', 'Warmtepomp', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (14, 'ev', 'Elektrische auto', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (15, 'pv', 'Zonnenergie', 'kWh');
   INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (16, 'soc', 'SoC', '%');
   
````
 * tabel **values**:<br/>
   * Deze maak je aan met de volgende query: <br/>
````   
    CREATE TABLE `values` (
    `id` BIGINT(20) UNSIGNED NOT NULL  AUTO_INCREMENT,
    `variabel` INT(10) UNSIGNED NOT NULL DEFAULT '0',
    `time` BIGINT(20) UNSIGNED NOT NULL DEFAULT '0',
    `value` FLOAT NULL DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE INDEX `variabel_time` (`variabel`, `time`) USING BTREE,
    INDEX `variabel` (`variabel`) USING BTREE,
    INDEX `time` (`time`) USING BTREE ) 
    COLLATE='utf8mb4_unicode_ci'
    ENGINE=InnoDB
    AUTO_INCREMENT=1;
````
   * De inhoud van values bouw je zelf op met het ophalen van de diverse gegevens. <br> 
* tabel **prognoses**
  * Deze maak je aan met de volgende query:
````
CREATE TABLE `prognoses` (
	`id` BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
	`variabel` INT(10) UNSIGNED NOT NULL DEFAULT '0',
	`time` BIGINT(20) UNSIGNED NOT NULL DEFAULT '0',
	`value` FLOAT NULL DEFAULT NULL,
	PRIMARY KEY (`id`) USING BTREE,
	UNIQUE INDEX `variabel_time` (`variabel`, `time`) USING BTREE,
	INDEX `variabel` (`variabel`) USING BTREE,
	INDEX `time` (`time`) USING BTREE )
    COLLATE='utf8mb4_unicode_ci'
    ENGINE=InnoDB
    AUTO_INCREMENT=1;
````

  * Deze tabel wordt gevuld/aangevuld/geupdate met data door het programma als je een optimaliseringsberekening uitvoert.<br>  

---
## Programma starten<br>
Je kunt het programma draaien en testen via een terminalvenster op je laptop/pc:   
`python3 day_ahead.py [parameters]`  
  
Start je het programma zonder parameters dan worden de databases "geopend" en dan wacht het programma tot een opdracht uit de takenplanner (zie hieronder) moet worden uitgevoerd. De volgende parameters kunnen worden gebruikt:  

### **debug**<br>
Alleen van toepassing in combinatie met het onderdeel "calc" (zie hierna), voert wel de berekening uit maar zet de berekende resultaten niet door naar de apparaten.  

### **prices**<br>
Het programmam haalt de day ahead prijzen op bij een van de volgende bronnen: nordpool, entsoe of easyenergy. Deze bron stel je in via options.json (prices).<br>
Je kunt dit commando uitbreiden met een of twee extra datum-parameters: een start- en een eind datum. Laat je de tweede parameters achterwege dan wordt morgen als einddatum gekozen. Je kunt deze faciliteit gebruiken om een prijshistorie in de database op te bouwen.<br>
Format: `jjjj-mm-dd`<br>
Deze functionaliteit werkt alleen bij de bron easyenergy!<br>
Voorbeeld ` python3 day_ahead.py prices 2022-09-01 [2023-03-01]`
    
### **tibber**<br>
Haalt de verbruiks- en productiegegevens op bij tibber. Dit commando kan met een extra parameter worden gestart namelijk een datum. In dat geval worden de verbruiksdata opgehaald vanaf de ingegeven datum.<br>
Format: `jjjj-mm-dd` <br>
Voorbeeld: `python3 day_ahead.py tibber 2023-02-01`

### **meteo**<br>
Haalt de meteorologische gegevens op.

### **calc**<br>
Voert de "optimaliseringsberekening" uit: 
* haalt alle data (prijzen, meteo) op uit de database <br> 
* berekent de optimale inzet van de batterij, boiler, warmtepomp en ev <br> 
    als debug als parameter wordt meegegeven dan wordt de berekende inzet niet doorgevoerd
* berekent de besparing tov een reguliere leverancier <br>
* berekent de besparing zonder optimalisering met alleen dynamische prijzen<br>
* berekent de besparing met optimalisering met dynamische prijzen <br>
* presenteert een tabel met alle geprognoticeerde uurdata <br>
* presenteert een grafiek met alle geprognoticeerde uurdata

### **scheduler**<br>
Hiermee komt het programma in een loop en checkt iedere minuut of er een taak moet worden uitgevoerd. Dit wordt ook bereikt door het programma zonder parameter op te starten.<br>
Voorbeeld: `python3 day_ahead.py`<br>
Wil je dat het programma in de achtergrond blijft draaien dan plaats je er een '&' teken achter: `python3 day_ahead.py &`<br>

---
## Instellingen<br>
  
Het bestand `options.json` in de folder `data` bevat alle instellingen voor het programma day_ahead.py en dien je zelf aan te maken. Het voorbeeld bestand `options_vb.json` kun je als basis gebruiken en dien je aan passen naar jouw omgeving en omstandigheden.<br>
Opmerking: alle instellingen die beginnen met "!secret" staan komen in het bestand `secrets.json` te staan met de key die hier achter !secret staat.

### **homeassistant**<br>
 * protocol api: hiermee geeft je aan met welke protocol jouw HA installatie 
bereikbaar is. Je kunt kiezen uit `http` (zonder ssl) of `https` (met ssl).
 * ip adress: het ip-adres waar je home assistant installatie bereikbaar is.  
 * ip port: de ip-poort waar je home assistant installatie bereikbaar is.
 * token: om de api te kunnen aanroepen is er een token nodig.  
   Deze kun je genereren in Home Assistant in je profiel. Maak een token met lange levensduur aan.

### **database da**<br>
De database voor het day ahead programma.  
 * server: ip adres van de server (waar mariadb draait)  
 * database: naam van de database  
 * port: poort op de server (meestal 3306)  
 * username: user name  
 * password: wachtwoord

### **database ha**<br>
De database van Home Assistant. Wordt gebruikt om de rapporten te kunnen genereren. 
 * server: ip adres van de server (waar mariadb draait)  
 * database: naam van de database  
 * port: poort op de server (meestal 3306)  
 * username: user name  
 * password: wachtwoord
 
### **meteoserver-key**<br>
De meteodata worden opgehaald bij meteoserver. Ook hiervoor heb je een key nodig. Je genereert deze key (token) als volgt:<br> 
 * website: https://meteoserver.nl/login.php 
 * registreer je als gebruiker 
 * daarna klik je op Account, tabje "API Beheer" en je ziet je key staan<br>
 Opmerking: je kunt gratis maximaal 500 dataverzoeken per maand doen, we doen er maar 4 per dag = max 124 per maand.

### **prices**<br>
 * source day ahead
     Hier bepaal je waar je je day ahead prijzen vandaan wilt halen. Je hebt de keuze uit drie bronnen:
   * nordpool
   * entsoe
   * easyenergy<br>

    Als je kiest voor **entsoe** dan moet je hieronder een api key invullen.
 * entsoe-api-key:  
	  Deze key genereer je op de site van entsoe en heb je nodig om daar de energieprijzen van de volgende op te halen.
    Je genereert deze key (token) als volgt: 
   * Website: https://transparency.entsoe.eu      
   * Registreer je als gebruiker 
   * Vraag via een email naar transparency@entsoe.eu met “Restful API access” als onderwerp. 
     Vermeld het email adres waarmee je je hebt geregistreerd in de body van de email. 
     De ENTSO-E Helpdesk doet haar uiterste besto binnen 3 werkdagen te reageren.
   * Na ontvangst van een positieve reactie:
   * Log in
   * Klik op "My Account Settings"  
   * Klik op "Generate a new token"
   * Meer info: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
   Hoofdstuk 2 Authentication and Authorisation<br><br>

 * regular high: het hoge tarief van een "reguliere" oude leverancier,
   excl. btw, kaal, euro per kWh
 * regular low: idem het "lage" tarief, excl. btw, kaal , euro per kWh
     switch to low: tijdstop waarop je omschakelt naar "laag tarief" (meestal 23 uur)
  * energy taxes delivery: energiebelasting op verbruik excl. btw, euro per kWh  
           2022-01-01 : 0.06729,  
           2023-01-01 : 0.12599  
   * energy taxes redelivery: energiebelasting op teruglevering excl. btw, euro per kWh  
           2022-01-01: 0.06729,  
           2023-01-01: 0.12599  
    * cost supplier delivery : opslag leverancier euro per kWh, excl. btw  
        bijv voor Tibber:
        * 2022-01-01: 0.002
        * 2023-03-01: 0.018
  * cost supplier redelivery:  opslag leverancier voor teruglevering per kWh, ex btw  
        bijv voor Tibber:
        * 2022-01-01: 0.002
        * 2023-03-01: 0.018
        * 2023-09-01: 0.009
  * vat:    btw in %  
      * 2022-01-01: 21
      * 2022-07-01: 9
      * 2023-01-01: 21,  
   
  * last invoice: datum laatste jaarfactuur en/of de begindatum van je contractjaar (formaat "yyyy-mm-dd")
  * tax refund: kun je alles salderen of is je teruglevering hoger dan je verbruik  (True of False) 

### **baseload**<br> 
Hier vul je voor de 24 uren van een etmaal het basisverbruik van je woning in.
Deze bepaal je als volgt:<br>
* neem voor een voldoende lange periode (minimaal een maand) de geregistreerde energiehoeveelheden per uur op de volgende onderdelen:
* inkoop van je aansluiting op het netwerk: inkoop 
* teruglevering van je aansluiting op het netwerk: teruglevering
* het verbruik van je warmtepomp: wp
* het verbruik van je boiler: boiler
* het totale verbruik van je elektrische auto('s): ev
* de totale productie van je zonnepanelen: pv<br>
Als in deze periode ook je batterij al gedraaid heeft:
* de energie naar je batterij: accu_in
* de energie uit je batterij: accu_uit
* de basislast voor ieder uur reken je uit met de volgende formule:<br>
* basislast = inkoop - teruglevering - wp - boiler - ev + pv - accu_in + accu_uit
* de resultaten zet je samen met het begintijdstip van ieder uur in een spreadsheet<br>
  dat ziet er dan als volgt uit: <br>
  ![img_1.png](images/img_1.png)
* daarnaast begin je een nieuwe tabel met in de eerste kolom de getallen 0, 1 tot en met 23
* in de tweede kolom bereken je met "averageif" (of in libreoffice "gemiddelde.als") het gemiddelde van de baseloadkolom voor het uur 0, 1 enz. 
  Dat ziet er dan als volgt uit: <br>
  ![img_2.png](images/img_2.png)
* de 24 getallen uit de tweede kolom vul je in in de lijst.

### **graphical backend**<br/>
Het programma draait op een groot aantal operating systemen en architecturen, Voor het presenteren en opslaan van grafieken
maakt het programma gebruik van de bibliotheek **matplotlib**. Die probeert de correcte backend (canvas) te detecteren,
maar dat wil niet altijd lukken. Je kunt met deze instelling de voor jou goed werkende backend selecteren en instellen.
Je hebt de keuze uit de volgende backends: MacOSX, QtAgg, GTK4Agg, Gtk3Agg, TkAgg, WxAgg, Agg.<br>
**Gtk3Agg** werkt goed op Ubuntu met desktop.<br>
**Agg** werkt goed op een headless linux (zoals Rasberry PI of Ubuntu in een VM).<br>
Je kunt beginnen te proberen om de keuze blanco te laten: **""**. Dan zoekt het programma het zelf uit.

### graphics
Voor de lijngrafieken van de prijzen kun je met **True** of **False** kiezen welke je wil zien:
* prices delivery: prijzen voor levering
* prices redelivery: prijzen voor teruglevering (ex btw en belasting)
* average delivery": gemiddelde prijs voor levering

### **strategy**<br>
Het programma kent twee strategieën die je kunt inzetten om het voor jou optimale energieverbruik
en teruglevering te realiseren.<br>
Je kiest er één uit de betreffende naam in te vullen:
Bijvoorbeeld "strategy": "minimize cost"<br>
De twee strategieën zijn:
  * minimize cost<br>
    Als je deze kiest worden je batterij en je verbruiken zo ingezet dat deze leiden tot de laagste 
    kosten (= hoogste opbrengst)
Als voorbeeld levert deze het volgende resultaat:
  ![img_3.png](images/img_3.png)
  * minimize consumption<br>
    Deze strategie minimaliseert je levering (kWh) en streeft daarmee naar "nul op de meter" bij zo laag mogelijke kosten.
Onder dezelfde condities levert deze strategie een ander verbruikspatroon op:
  ![img_4.png](images/img_4.png)

### **notifications**

 * entity<br>
Maak in Home Assistant een helper (max 100 tekens) aan in de vorm van een input_text.
Wanneer er problemen ontstaan tijdens de berekening of tijdens het ophalen van gegevens dan wordt
hier een in betreffende helper een tekst gezet.
Desgewenst kun je met behulp van een automatisering een notificatie starten naar analogie van onderstaand voorbeeld: <br>
````
alias: Notification DAO
description: Send notification from DAO
trigger:
  - platform: state
    entity_id: input_text.notification_dao
condition: []
action:
  - service: notify.mobile_app_nokia_7_plus
    data:
      message: "{{ trigger.to_state.state }}"
      title: DAO let op
      data:
        color: blue
        sticky: true
        ttl: 0
        priority: high
mode: single
````
* opstarten
* berekening<br>
Met "True" of "False" geeft je aan of je een notificatie wilt bij het opstarten van het programma
en bij het uitvoeren van een optimaliseringsberekening
*  last activity entity<br>
In deze entity (helper van het type input_datetime) wordt de datum-tijd weggeschreven als er door het programma 
een activiteit is uitgevoerd (berekening, ophalen prijzen enz). Als deze helper niet uurlijks wordt geupdate kun je daar in
Home Assistant met een automatisering een alarm notificatie op zetten. <br>
Voorbeeld van een watchdog timer in HA:
````
alias: DAO herstart watchdog timer
description: ""
trigger:
  - platform: state
    entity_id:
      - input_datetime.dao_laatste_activiteit
condition: []
action:
  - service: timer.start
    data:
      duration: "01:01:00"
    target:
      entity_id: timer.dao_watchdog_timer
mode: single
````
Zodra de timer voltooid is er wat loos. Als je aan deze functionaliteit geen behoefte hebt kun je de entity instelling weglaten uit de options.

### **boiler**<br>
Instellingen voor optimalisering van het elektraverbruik van je warmwater boiler
   * boiler present: True of False. Als je False invult worden onderstaande boiler-instellingen genegeerd.
   * entity actual temp. : entiteit in ha die de actuele boilertemp. presenteert  
   * entity setpoint: entiteit die de ingestelde boilertemp. presenteert  
   * entity hysterese: entiteit die de gehanteerde hysterese voor de boiler presenteert  
   * cop: cop van de boiler bijv. 3: met 1 kWh elektriciteit wordt 3 kWh warm water gemaakt (een elektrische boiler heeft een cop = 1)
   * cooling rate: gemiddelde afkoelsnelheid van de boiler in K/uur  
   * volume: inhoud van de boiler in liter  
   * heating allowed below: temperatuurgrens in °C waaronder de boiler mag worden opgewarmd  
   * elec. power: elektrisch vermogen van de boiler in W  
   * activate service: naam van de service van deze entiteit  
   * activate entity: entiteit (meestal van een inputhelper) waarmee de boiler opwarmen wordt gestart  

### **heating**<br>
Dit onderdeel is nog in ontwikkeling. 
   * `heater present` : True of False. Als je False invult worden onderstaande heater-instellingen genegeerd.
   * `degree days factor`: kWh/K.dag hoeveel thermische kWh is er nodig per graaddag<br>
     zet deze op 0 als je geen wp hebt
   * `stages` : een lijst met vermogens schijven van de wp: hoe hoger het vermogen hoe lager de cop
     * `max_power`: het maximum elektrische vermogen van de betreffende schijf in W
     * `cop`: de cop van de wp behorende bij deze schijf. Dus een cop van 7 met een vermogen van 225 W 
        betekent een thermisch vermogen van 7 x 225 = 1575 W
   * `entity adjust heating curve`: entiteit waarmee de stooklijn kan worden verschoven
   * `adjustment factor`: float K/10% Het aantal graden voor de verschuiving van de stooklijn als de actuele 
      da prijs 10% afwijkt van het daggemiddelde

### **battery**<br> 
  De gegevens en de instellingen van geen, een of meer batterijen
  Je kunt de batterij instellingen herhalen als je meer dan een batterij hebt, of je laat de lijst leeg (geen batterij)
   * name: de naam van de batterij (komt terug in rapportages)
   * entity actual level: entiteit die de actuele SoC van de batterij presenteert  
   * capacity: capaciteit van de batterij in kWh  
   * lower limit: onderste SoC limiet (tijdelijk)  
   * upper limit: bovenste SoC limiet  
   * optimal lower level: onderste SoC limiet voor langere tijd  
   * entity min soc end opt: entity in home assistant (input_number), waarmee je de 
     minimale SoC in procenten kunt opgeven die de batterij aan het einde van de berekening moet hebben 
   * entity max soc end opt: entity in home assistant (input_number), waarmee je de
     maximale SoC in procenten kunt opgeven die de batterij aan het einde van de berekening moet hebben <br>
     **opmerking:** met deze twee instellingen kunt je bereiken dat de batterij aan het eind "leeg" of "vol" is. Een lage batterij 
     kan zinvol zijn als je de dag(en) na de berekening veel goedkope stroom en/of veel pv productie verwacht. Een volle batterij 
     kan zinvol zijn als je juist dure stroom en/of weinig eigen pv-productie verwacht. 
   * charge stages: hier vul je een zelf te kiezen aantal stappen of schijven in voor het laden via de omvormer. In een drie fase systeem tel je het vermogen van alle omvormers bij elkaar op.
    Per schijf vul je in: 
     * power: het maximale vermogen van de schijf (het minimale vermogen van de schijf is het maximale vermogen van de vorige schijf)
     * efficiency: de efficiency (het rendement) voor deze schijf als een factor 
     * van 1. Voor de duidelijkheid: je vult hier de efficiency van omvormer 
       * van ac to dc in. Het rendement van de batterij (dc to bat) vul je hieronder in.<br>
   Bijvoorbeeld: {"power": 30.0, "efficiency": 0.949} <br>
   De eerste schijf is altijd:  {"power": 0.0, "efficiency": 1},
   De "power" van de laatste schijf geeft ook het maximale 
   * discharge stages: op dezelfde wijze als de "charge stages" vul je hier voor het ontladen een aantal stappen of schijven in voor het ontladen via je omvormer/inverter. 
   * minimum power: minimaal laad/ontlaadvermogen
   * dc_to_bat efficiency: efficiency van het laden van de batterij vanuit dc (factor van 1)
   * bat_to_dc efficiency: efficiency van het ontladen van de batterij naar dc (factor van 1)
   * cycle cost : afschrijfkosten (in euro) van het laden of ontladen van 1 kWh  
   * entity set power feedin: entiteit waar je het te laden / ontladen vermogen inzet  
   * entity set operating mode: entiteit waarmee je het ess aan/uit zet  
   * entity stop victron: entiteit waarmee je datum/tijd opgeeft wanneer het ess moet stoppen  
   * entity balance switch: entiteit waarmee je Home Assistant in samenwerking met de omvormer op "balanceren" zet (overrult set power feedin)<br>
Hiermee zorg je ervoor dat er geen levering c.q. teruglevering aan het net plaatsvindt. Deze optie wordt met name interessant en bruikbaar als er een verschil is in tarief tussen leveren en terugleveren. Bijvoorbeeld als je niet meer kunt salderen. Maar ook bij de strategie "nul op de meter", zal het programma vaker van deze mogelijkheid gebruik willen maken. 
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
stel geprognoticeerd/berekend = 50 kWh gemeten is : 40 kWh dan wordt de nieuwe yield = oude_yield * 40 / 50. <br>
     * entity pv switch: een entity (meestal een helper in de vorm van een input_boolean), waarmee je
     de betreffende pv installatie aan/uit kunt zetten en die het programma gebruikt om bij hele lage inkoopprijzen 
     (of beter lage of negatieve terugleververgoedingen) de pv uit te zetten.<br>
           
### **solar**<br> 
  Lijst van pv installaties die dmv een omvormer (of mini omvormers) direct invoeden op je ac installatie<br>
  Per pv installatie geef je de volgende gegevens op:
* tilt : de helling van de panelen in graden; 0 is vlak, 90 is verticaal  
* orientation : orientatie in graden, 0 = zuid, -90 is oost, 90 west  
* capacity: capaciteit in kWp  
* yield: opbrengstfactor van je panelen als er 1 J/cm2 straling op je panelen valt in kWh/J/cm2 (zie hierboven)  
* entity pv switch: een entity (meestal een helper in de vorm van een input_boolean), waarmee je
de betreffende pv installatie aan/uit kunt zetten en die het programma gebruikt om bij hele lage inkoopprijzen 
(of beter lage of negatieve terugleververgoedingen) de pv uit te zetten.<br>
 
### **electric vehicle**<br> 
  Dit is voorlopig gebaseerd op een Volkswagen auto die kan worden bereikt met WeConnect. 
    Andere auto's graag in overleg toevoegen. Ook hier kun je kiezen uit een lege lijst of een of meer auto's
   * name: de naam van de auto (komt straks terug in rapportages)
   * capacity: capaciteit batterij in kWh   
   * entity position: entiteit die aangeeft of de auto "thuis" (home) is  
   * entity max amperage: entiteit die het max aantal amperes aangeeft waarmee kan worden geladen
   * charge three phase: of de EV met drie fasen wordt geleden  
   * entity actual level: entiteit die aangeeft hoe ver de auto is geladen (in %)  
   * entity plugged in: entiteit die aangeeft of de auto is ingeplugged  
   * charge scheduler: oplaad scheduler  
     * entity set level: entiteit van een input helper die aangeeft tot welk niveau moet worden geladen in %  
     * entity ready datetime: entiteit van een input_datetime die het tijdstip en eventueel de datum weergeeft hoe laat de auto op het gewenste niveau moet zijn. 
     Je kunt zelf kiezen of je een helper met of zonder datum gebruikt. Een helper zonder datum zal er altijd voor zorgen dat de auto iedere dag op hetzelfde
     gewenste tijdstip is geladen. Een helper met datum zul je steeds moeten updaten maar heeft wel als voordeel dat je verder in de toekomst kunt plannen. <br>
     * Er zal alleen geladen worden als het eindtijdstip binnen het tijdvenster van het optimaliseringsprogramma valt. 
     Het begintijdstip van venster is het huidige uur en het eindtijdstip is het laatste uur waarvoor nog dynamische prijzen bekend zijn in het programma.
   * charge switch: entiteit waarmee het laden aan/uit kan worden gezet 

 ### **tibber**<br>
 * api url : url van de api van tibber  
 * api_token : het token van de api van tibber  
  Deze vraag je als volgt op:  
   * log in met je account op https://developer.tibber.com/explorer  
   * de token staat boven onder de balk 
 
 ### **scheduler**<br>
 Het programma maakt gebruik van een eenvoudige takenplanner. <br/>
 De volgende taken kunnen worden gepland:
   * **get_meteo_data**: ophalen van meteo gegevens bij meteoserver  
   * **get_tibber_data**: ophalen van verbruiks- en productiegegevens per uur bij tibber  
   * **get_day_ahead_prices**: ophalen van day ahead prijzen bij nordpool cq entsoe  
   * **calc_optimum**: bereken de inzet batterij, boiler en auto voor de komende uren, de inzet van het lopende uur 
wordt doorgezet naar de betreffende apparaten (tenzij het programma is gestart met de 
parameter debug)<br/>
   * **clean_data**: hiermee worden log en png bestanden in de mappen data\log\ respectievelijk data\images\ die ouder zijn 7 dagen verwijderd.

De key heeft het formaat van "uumm": uu is het uur, mm is de minuut de uren en minuten zijn ofwel een twee cijferig getal of XX ingeval van XX zal de taak ieder uur cq iedere minuut worden uitgevoerd.<br/>
Bijvoorbeeld : <br/>
`"0955": "get_meteo_data"`: de meteodata worden opgehaald om 9 uur 55<br/>
`"1255": "get_day_ahead_prices"`: haal de actuele prijzen op op 12 uur 55<br>
`"xx00": "calc_optimum"`: ieder uur exact om "00" wordt de optimaliseringsberekening uitgevoerd.

## Dashboard
Het programma wordt geleverd met een webserver die je als een dashboard kunt benaderen.
Dit onderdeel is nog helemaal in ontwikkeling, maar kan al wel gedeeltelijk worden  getest.

De webserver kan op twee manieren worden opgestart:
* om te testen start je het programma op in een console in de directory ```webserver``` met het commando: ````python3 da_server.py````
* voor een productiesituatie dien je gebruik te maken van gunicorn en 
dan geef je in de directory ```webserver``` het commando: <br>
````gunicorn --config gunicorn_config.py  app:app````
* het bestand ```gunicorn_config.py``` bevat de configuatieinstellingen voor de webserver.
Verander dit alleen als je weet wat en waarom je het doet. De port waarop je 
de webserver kunt benaderen kun je instellen in het option.json bestand onder dashboard (zie hierna).<br />

Je benadert de webserver/het dashboard met een browser als volgt:
```http://<ip-adres>:<ip-poort>/```, waarbij je voor:<br />
```<ip-adres>``` het ipadres invult van de machine waarop de webserver draait
```<ip-poort``` het poortnummer invult waarop je de webserver kunt bereiken (zie verder).<br/>
Bijvoorbeeld : ```http://192.168.178.36:5000/```

De specifieke instellingen voor dit onderdeel staan ook in options.json onder de sleutel **dashboard**
Je kunt de volgende instellingen maken:
* port: dit is de poort op de server waarop je de webserver kunt benaderen.

Het hoofdmenu van het dashboard bestaat uit 4 opties: <br />
  ![Img_5.png](images/Img_5.png) <br />

- Home (huisje)
- Run
- Reports
- Settings

**Home**<br/>
Deze webpagina komt ook naar voren als je de webservervia je browser benadert: <br />
  ![Img_6.png](images/Img_6.png) <br />
Daarin toont zich een submenu met daarin de informatie die je met submenu selecteert:
Het submenu geeft links de keuze de keuze uit (voorlopig twee **onderwerpen**):
 - grid (deze is nu actief, dat wordt aangegeven met de kleur rood)
 - accu1 (de naam van je accu), helaas werkt dit nog niet <br />

In het midden van het submenu kun je kiezen **hoe** je de gevraagde informatie wil zien:
 - grafiek (nu actief)
 - tabel <br />

Rechts kun je bladeren door de aangeboden informatie:
- **|<** de laatste aanwezige grafiek/tabel
- **<** de vorige
- **>** de volgende
- **>|** de eerste
- ![delete.png](images/delete.png) met de afvalbak kun je de aangeboden informatie verwijderen

**Run**<br/>
![Img_8.png](images/Img_8.png) <br />
Via deze menu-optie kun je alle mogelijke berekeningen en bewerkingen van het programma activeren 
(zie ook het begin van deze handleiding). <br/>
Je activeert een bewerking door deze aan te klikken.<br/>
Je krijgt direct een bevestiging dat de betreffende berekening/bewerking wordt uitgevoerd.<br/>
Na 10 tot 15 seconden komt het log-bestand van de bewerking/berekening in beeld.
Wil je het grafische resultaat van een optimaliseringsberekening zien klik dan op "Home",
Je krijgt dan de laatste berekende grafiek in beeld.

**Reports**<br/>
![Img_7.png](images/Img_7.png) <br />
Dit onderdeel is nog in ontwikkeling, maar biedt nu al veel mogelijkheden.<br/>
Er is nog geen verschil tussen verbruik en kosten, omdat alles netjes in een tabel past.
Maar er komen nog wel verschillende verbruiks- en kostengrafieken.
Het grafische deel werkt nu nog basaal, maar wordt ook nog verder uitgewerkt.
In het pull-down menu kun je de periode kiezen waarvan je een rapport wil zien.
Je hebt de keuze uit de volgende perioden:
* vandaag _*_ <br/>
* vandaag en morgen (alleen zinvol na 13:00 uur) _*_ <br/>
* gisteren <br/>
* deze week _*_ <br/>
* vorige week <br/>
* deze maand _*_ <br/>
* vorige maand <br/>
* dit jaar _*_ <br/>
* vorig jaar <br/>
* dit contractjaar _*_ <br/>

De perioden met een _*_ hebben de optie "met prognose".
Als je die aanvinkt wordt een rapportage berekend inclusief de resultaten van de laatst uitgevoerde optimaliseringsberekening.
Dit geldt zowel voor de tabel als de grafiek. In de toekomst zullen in de grafiek de "prognose waarden" iets afwijkend worden getoond.

**Settings**<br/>
-    ***Options***<br/>
Hiermee kun je het instellingen bestand (options.json) bewerken
- ***Secrets***<br />
Hiermee bewerk je het bestand (secrets.json) met je wachtwoorden en andere zaken die je niet in options.json wil opnemen.

# Api
Het dashboard is ook benaderbaar via een api:
* \<url>/api/run/\<commando>
* \<url>/api/report/\<variable>/\<period>?parameter=parameter_value <br/>

De ```<url>``` bestaat uit: ```http://<ip-adres>:<ip-poort>```
Voor ```<ip-adres>``` en ```<ip-poort>``` zie hierboven.<br/> 

## \<url>/api/run/\<commando><br />
Met dit onderdeel van de api kun je via het dashboard alle berekeningen en bewerkingen
van het programma starten. Dit kan met **curl** maar ook kun je hiermee vanuit Home Assistant een bewerking of berekening uitvoeren. <br/>
Bij ```<commando>``` vul je een van de volgende commando's in:<br />
* ```calc_zonder_debug```: een optimaliseringsberekening wordt uitgevoerd. 
De resultaten worden doorgezet naar Home Assistant.<br />  
* ```calc_met_debug```: een optimaliseringsbereking wordt uitgevoerd. De resultaten worden **niet**
doorgezet naar Home Assistant.
* ```get_tibber```: haalt verbruiksgegevens (consumption, production, cost, profit) op bij Tibber en slaat deze op in de database<br/>
* ```get_meteo```: haalt prognose van meteogegevens op bij Meteoserver en slaat deze op in de database
* ```get_prices```: haalt de day-ahead prijzen voor de volgende dag op en slaat deze op in de database<br/>

Een uitgewerkt voorbeeld hoe je vanuit Home Assistant een berekening kunt starten:<br/>
- Maak een (of meer) rest-commands aan. <br/>
    Voeg de volgende code toe aan configuration.yaml van Home Assistant:<br/>
    ````
    rest_command:
      start_dao_calc:
        url: http://192.168.178.36:8012/api/run/calc_zonder_debug
        verify_ssl: false
    ````
-   Maak een helper aan Home Assistant bijvoorbeeld: ```input_button.start_day_ahead_berekening``` en
zet deze helper op een voor jou passende entity card.<br/>
- Maak een automatisering aan die wordt getriggerd als je op deze helper klikt.
Bijvoorbeeld:<br/>
    ````
    alias: Start berekening DAO via rest
    description: Start berekening DAO
    trigger:
      - platform: state
        entity_id:
          - input_button.start_day_ahead_berekening
    condition: []
    action:
      - service: rest_command.start_dao_calc
        data: {}
    mode: single
    ````

## \<url>/api/report/\<variable>/\<period>?\<param>=\<param_value>
Hiermee kun je diverse gegevens uit de database ophalen en deze kun je dan bijv. in Home Assistant
gebruiken om grafieken te maken met bijv. apex-charts (zie hieronder).<br/>
Voor **\<variabele>** kun je (voorlopig) een van de volgende mogelijkheden invullen (wordt uitgebreid):
- **da**<br/>
    Hiermee vraag je de day ahead prijzen op. Het programma retourneert de volgende gegevens (json):
```{ "message":"Success", "recorded": [{"time":"2023-10-13 00:00","da_ex":0.12399,"da_cons":0.3242558,"da_prod":0.3242558},{"time":"2023-10-13 01:00","da_ex":0.115,"da_cons":0.3133779,"da_prod":0.3133779},{"time":"2023-10-13 02:00","da_ex":0.10714,"da_cons":0.3038673,"da_prod":0.3038673},{"time":"2023-10-13 03:00","da_ex":0.1014,"da_cons":0.2969219,"da_prod":0.2969219}, .....```
per uur worden de drie prijzen geretourneerd:
  - ```da_ex```: kale day ahead prijs, excl. belasting, excl. btw en excl opslag leverancier
  - ```da_cons```: de day ahead prijs waarvoor jij elektriciteit koopt, dus inclusief energiebelasting, btw en opslag leverancier
  - ```da_prod```: de day ahead prijs waarvoor jij elektriciteit teruglevert. Dit is afhankelijk van: kun je nog salderen en in hoeverre
  (voorlopig is dit bij de meeste gelijk aan da_cons) 
- **consumption** <br/>
  Hiermee vraag je je verbruiksgegevens op. Bijvoorbeeld:<br/>
```{ "message":"Success", "recorded": [{"time":"2023-10-13 00:00","value":0.177},{"time":"2023-10-13 01:00","value":0.458},{"time":"2023-10-13 02:00","value":0.158},{"time":"2023-10-13 03:00","value":0.648},{"time":"2023-10-13 04:00","value":0.134},{"time":"2023-10-13 05:00","value":0.129},{"time":"2023-10-13 06:00","value":0.128},{"time":"2023-10-13 07:00","value":0.1},{"time":"2023-10-13 08:00","value":0.02}, ...  ,{"time":"2023-10-13 15:00","value":5.343}], "expected" : [{"time":"2023-10-13 16:00","value":2.20486},{"time":"2023-10-13 17:00","value":0.501},{"time":"2023-10-13 18:00","value":0.0},{"time":"2023-10-13 19:00","value":0.0},{"time":"2023-10-13 20:00","value":0.0},{"time":"2023-10-13 21:00","value":0.19},{"time":"2023-10-13 22:00","value":1.605},{"time":"2023-10-13 23:00","value":1.585}] }```<br/>
Deze reeks data bestaat uit twee onderdelen:
  - ```recorded```: het geregistreerde verbruik (hier vanaf 0:00 uur tot en met 15:00 uur)
  - ```expected```: het geprognotiseerde verbruik (hier vanaf 16:00 uur). 
  Dit is het verwachte verbruik zoals het programma dit de laatste keer dat het heeft gedraaid heeft berekend. 
- **production**<br/>
    Hiermee vraag je je teruglevering gegevens op. De indeling is hetzelfde als bij consumption.
- **cost**<br/>
    Hiermee vraag je je verbruikskosten op.
- **profit**<br/>
    Hiermee vraag je je teruglevering inkomsten op.

Bij **\<period>** kun je de periode opgeven waarover je de gevraagde gegevens wilt ontvangen. 
Je kunt kiezen uit:
- **vandaag** met interval uur
- **vandaag_en_morgen** met interval uur
- **morgen** met interval uur
- **deze_week** met interval dag
- **vorige_week**  met interval dag
- **deze_maand**  met interval dag
- **vorige_maand**  met interval dag
- **dit jaar** met interval maand
- **vorig_jaar** met interval maand
- **dit_contractjaar**  met interval maand

Het laatste stuk **?\<param>=\<param_value>** is facultatief.
Voorlopig is is parameter die je kunt invullen: 
- **?cumulate=1**<br/>
    Als je cumulate opgeeft en je zet deze op "1" dan worden alle resultaten cumulatief berekend.
Bijvoorbeeld: ```/api/report/profit/vorige_week?cumulate=1``` geeft als resultaat:<br/>
```{ "message":"Success", "recorded": [{"time":"2023-10-02 00:00","value":10.9429554939},{"time":"2023-10-03 00:00","value":19.7526173011},{"time":"2023-10-04 00:00","value":24.1756554841},{"time":"2023-10-05 00:00","value":31.4851145427},{"time":"2023-10-06 00:00","value":37.0579458385},{"time":"2023-10-07 00:00","value":38.6841635039},{"time":"2023-10-08 00:00","value":40.9582582529}], "expected" : [] }```

## Gebruik van deze api voor presentatie in Home Assistant

### Aanmaken van sensoren
Je maakt gebruik van de restful integratie van Home Assistant (https://www.home-assistant.io/integrations/rest/). 
Daarvoor maak je in ```configuration.yaml``` de gewenste sensoren aan.
Bijvoorbeeld:<br/>
````
rest:
  - resource: http://192.168.178.64:5000/api/report/da/vandaag_en_morgen
    verify_ssl: false
    scan_interval: 600
    sensor:
      - name: DA Price
        unique_id: da_price
        unit_of_measurement: 'euro/kWh'
        value_template: "{{ (value_json.recorded[now().hour].da_ex) | round(5) }}"
        json_attributes:
          - recorded
          - expected
  - resource: http://192.168.178.64:5000/api/report/consumption/vandaag_en_morgen
    verify_ssl: false
    scan_interval: 600
    sensor:
      - name: DAO Grid consumption
        unique_id: dao_grid_consumption
        unit_of_measurement: 'kWh'
        value_template: "{{ (value_json.recorded[now().hour-1].value) | round(3) }}"
        json_attributes:
          - recorded
          - expected
  - resource: http://192.168.178.64:5000/api/report/consumption/vandaag?cumulate=1
    verify_ssl: false
    scan_interval: 600
    sensor:
      - name: DAO Grid consumption cumulatief
        unique_id: dao_grid_consumption_cumulatief
        unit_of_measurement: 'kWh'
        value_template: "{{ (value_json.recorded[now().hour-1].value) | round(3) }}"
        json_attributes:
          - recorded
          - expected
  - resource: http://192.168.178.64:5000/api/report/production/vandaag_en_morgen
    verify_ssl: false
    scan_interval: 600
    sensor:
      - name: DAO Grid production
        unique_id: dao_grid_production
        unit_of_measurement: 'kWh'
        value_template: "{{ (value_json.recorded[now().hour-1].value) | round(3) }}"
        json_attributes:
          - recorded
          - expected
````
Korte toelichting:
- **resource: http://192.168.178.64:5000/api/report/da/vandaag_en_morgen** verwijst naar de url-api waarmee je de data ophaalt van de gewenste sensor
- **verify_ssl**: false, voorlopig nog geen https
- **scan_interval: 600**: haal de data iedere 10 minuten op
- **sensor:**
    - **name: da_price** naam van de sensor in Home Assistant
    - **unit_of_measurement: 'euro/kWh'** de dimensie
    - **value_template: "{{ (value_json.recorded[now().hour].value) | round(5) }}"**<br/>
    de template waarmee de actuele waarde van de sensor uit de attributen wordt gehaald
    - **json_attributes:<br/>
          - recorded** de daadwerkelijk geregistreerde waarden (in de values tabel)
          - **expected** de geprognotiseerde waarden (in de prognoses tabel)<br />

Kijk je in Home Assistant via Ontwikkelhulpmiddelen/Statussen en filter je bijvoorbeeld 
je sensoren op "da_", dan moet je zoiets te zien krijgen:<br/>
![Img_9.png](images/Img_9.png) <br />
waarmee duidelijk is dat je de gegevens binnenkrijgt in Home Assistant en dat de aangemaakte sensor(en) werken.

### Presentatie van deze data in Home Assistant 
Je kunt op de jouw bekende wijze deze sensoren opnemen in allerlei entiteits kaarten,
maar nog mooier als je er met behulp van de apex charts grafieken van maakt.
Zie voor alle informatie: https://github.com/RomRider/apexcharts-card
Daar staat ook hoe je de software installeert en alleinfo over de configuratie-opties.
Voorbeeld:
<br/>
![Img_10.png](images/Img_10.png) <br />
De configuratie van deze grafiek ziet er als volgt uit:<br/>
````
type: custom:apexcharts-card
graph_span: 48h
span:
  start: day
header:
  show: true
  title: Day Ahead Price vandaag en morgen
  colorize_states: true
  show_states: true
yaxis:
  - min: ~0
    max: ~0.2
    decimals: 2
series:
  - entity: sensor.da_price
    attribute: recorded
    name: Exclusief historie
    type: line
    curve: stepline
    show:
      in_header: true
      legend_value: false
    color: orange
    opacity: 1
    float_precision: 5
    statistics:
      align: start
    data_generator: |
      return entity.attributes.recorded.map(row => {
              return [row.time, row.da_ex];
            });
  - entity: sensor.da_price
    attribute: expected
    name: Exclusief prognose
    type: line
    curve: stepline
    show:
      in_header: false
      legend_value: false
    color: orange
    opacity: 0.5
    float_precision: 5
    data_generator: |
      return entity.attributes.expected.map(row => {
              return [row.time, row.da_ex];
            });
  - entity: sensor.da_price
    attribute: recorded
    name: Consumptie historie
    type: line
    curve: stepline
    show:
      in_header: true
      legend_value: false
    color: blue
    opacity: 1
    float_precision: 5
    statistics:
      align: start
    data_generator: |
      return entity.attributes.recorded.map(row => {
              return [row.time, row.da_cons];
            });
  - entity: sensor.da_price
    attribute: expected
    name: Consumptie prognose
    type: line
    curve: stepline
    show:
      in_header: false
      legend_value: false
    color: blue
    opacity: 0.5
    float_precision: 5
    data_generator: |
      return entity.attributes.expected.map(row => {
              return [row.time, row.da_cons];
            });
````
Voor de uitleg van deze instellingen verwijs ik je (voorlopig)naar de documentatie van de apexcharts:<br/>
```https://github.com/RomRider/apexcharts-card/blob/master/README.md```


# Addon
Het bovenstaande programma en de webserver voor het dashboard kunnen samen draaien in een addon van Home Assistant.
Voorlopig draait deze addon alleen op de platforms met een arm64 
processor, zoals een Raspberry PI4 of Odroid.

Ik ga het zo proberen te maken dat je deze addon met alle software kunt installeren vanuit 
de addon winkel van Home Assistant,

wordt vervolgd
