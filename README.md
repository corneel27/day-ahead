# DAY AHEAD OPTIMIZATION

![Supports aarch64 Architecture][aarch64-shield] ![Supports amd64 Architecture][amd64-shield] ![Supports i386 Architecture][i386-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg

## Inleiding
Het programma Day Ahead Optimization (DAO) voert de volgende acties, berekeningen en bewerkingen uit: 

* ophalen dynamische energie tarieven bij Entsoe en/of NordPool
* ophalen van je verbruiksgevens van de vorige dag(en) bij Tibber
* ophalen van meteogegevens bij Meteoserver
* berekenen van de optimale inzet van een aanwezige batterij, wp-boiler en elektrische auto.<br>

Het programma draait alleen als addon op HA installaties met een arm64 processor (bijv Raspberry Pi4),
een intel 64 bit processor (amd64), of intel 32 bit (i386).
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

![optimalisering](dao/images/optimum2300.png "optimalisering")

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
Heb je wensen, opmerkingen, suggesties, commentaar of kritiek: alles is welkom op de github pagina 
van deze addon. Bij het onderdeel issues:<br>
https://github.com/corneel27/day-ahead/issues <br>
of bij de discussions:<br>
https://github.com/corneel27/day-ahead/discussions <br>
Voordat je een issue invult of een discusie begint: doorzoek de geschiedenis, misschien is het probleem al 
eerder aangekaart.<br>
Of nog beter: Plaats een pull request met een oplossing of een nieuwe feature!