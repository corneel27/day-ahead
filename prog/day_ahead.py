"""
Het programma Day Ahead Optimalisatie kun je je energieverbruik en energiekosten optimaliseren als je gebruik maakt
van dynamische prijzen.
Zie verder: README.md
"""
import datetime
from pprint import pprint
import sys
import os
import fnmatch
import time
from requests import get
import math
import json
import hassapi as hass
import pandas as pd
from mip import Model, xsum, minimize, BINARY, CONTINUOUS
import numpy
import utils
from utils import get_value_from_dict, get_tibber_data, is_laagtarief
from _version import __version__
from da_config import Config
from da_meteo import Meteo
from da_prices import DA_Prices
from db_manager import DBmanagerObj
import websocket
import threading


class DayAheadOpt(hass.Hass):

    def __init__(self, file_name=None):
        utils.make_data_path()
        self.debug = False
        self.config = Config(file_name)
        self.ip_adress = self.config.get(['homeassistant', 'ip adress'])
        self.ip_port = self.config.get(['homeassistant', 'ip port'])
        self.hassurl = "http://" + self.ip_adress + ":" + str(self.ip_port) + "/"
        self.hasstoken = self.config.get(['homeassistant', 'token'])
        super().__init__(hassurl=self.hassurl, token=self.hasstoken)
        headers = {
            "Authorization": "Bearer " + self.hasstoken,
            "content-type": "application/json",
        }
        resp = get(self.hassurl + "api/config", headers=headers)
        resp_dict = json.loads(resp.text)
        # print(resp.text)
        self.config.set("latitude", resp_dict['latitude'])
        self.config.set("longitude", resp_dict['longitude'])
        print("Day Ahead Optimalisering versie:", __version__)
        print("Day Ahead Optimalisering gestart op:", datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))
        db_da_name = self.config.get(['database da', "database"])
        db_da_server = self.config.get(['database da', "server"])
        db_da_port = int(self.config.get(['database da', "port"]))
        db_da_user = self.config.get(['database da', "username"])
        db_da_password = self.config.get(['database da', "password"])
        self.db_da = DBmanagerObj(db_name=db_da_name, db_server=db_da_server, db_port=db_da_port, \
                                  db_user=db_da_user, db_password=db_da_password)
        db_ha_name = self.config.get(['database ha', "database"])
        db_ha_server = self.config.get(['database ha', "server"])
        db_ha_port = int(self.config.get(['database ha', "port"]))
        db_ha_user = self.config.get(['database ha', "username"])
        db_ha_password = self.config.get(['database ha', "password"])
        self.db_ha = DBmanagerObj(db_name=db_ha_name, db_server=db_ha_server, db_port=db_ha_port, \
                                  db_user=db_ha_user, db_password=db_ha_password)
        self.meteo = Meteo(self.config, self.db_da)
        self.solar = self.config.get(["solar"])
        self.prices = DA_Prices(self.config, self.db_da)
        self.strategy = self.config.get(["strategy"])
        self.tibber_options = self.config.get(["tibber"])
        self.notification_options = self.config.get(["notifications"])
        if "notification entity" in self.notification_options:        
            self.notification_entity = self.notification_options["notification entity"]
        else:
            self.notification_entity = None
        if "last activity entity" in self.notification_options:
            self.last_activity_entity = self.notification_options["last activity entity"]
        else:
            self.last_activity_entity = None
        self.set_last_activity()
        self .history_options = self.config.get(["history"])
        self.boiler_options = self.config.get(["boiler"])
        self.battery_options = self.config.get(["battery"])
        self.prices_options = self.config.get(["prices"])
        self.ev_options = self.config.get(["electric vehicle"])
        self.heating_options = self.config.get(["heating"])
        self.tasks = self.config.get(["scheduler"])
        self.base_cons = self.config.get(["baseload"])
        self.w_socket : websocket = None
        self.heater_present = False
        self.boiler_present = False
    def set_last_activity(self):
        if self.last_activity_entity != None:
            self.call_service("set_datetime", entity_id=self.last_activity_entity, \
                              datetime=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def day_ahead_berekening_uitvoeren(self):
        self.calc_optimum()
        return

    def get_meteo_data(self, show_graph: bool=False):
        self.db_da.connect()
        self.meteo.get_meteo_data(show_graph)
        self.db_da.disconnect()

    @staticmethod
    def get_tibber_data():
        get_tibber_data()

    def get_day_ahead_prices(self):
        self.db_da.connect()
        self.prices.get_prices(self.prices_options["source day ahead"])
        self.db_da.disconnect()

    def get_consumption(self, start: datetime.datetime, until=datetime.datetime.now()):
        """
        Berekent consumption en production tussen start en until
        :param start: begindatum periode, meestal de ingangsdatum van het lopende contractjaar
        :param until: einddatum periode, meestal vandaag
        :return: een dict met consumption en production
        """
        # from da database

        sql = (
                "SELECT SUM(t1.`value`) as consumed, SUM(t2.`value`) as produced "
                "FROM `values` AS t1, `values` AS t2, `variabel`AS v1, `variabel` AS v2 "
                "WHERE (t1.`time`= t2.`time`) "
                "AND (v1.`code` ='cons')AND (v2.`code` = 'prod') "
                "AND (v1.id = t1.variabel) AND (v2.id = t2.variabel) "
                "AND t1.`time` >= UNIX_TIMESTAMP('" + start.strftime('%Y-%m-%d') + "') "
                "AND t1.`time` < UNIX_TIMESTAMP('" + until.strftime('%Y-%m-%d') + "');"
        )
        data = self.db_da.run_select_query(sql)
        if len(data.index) == 1:
            consumption = data['consumed'][0]
            production = data['produced'][0]
        else:
            consumption = 0
            production = 0


        # from home assistant database
        '''
        self.db_ha.connect()
        grid_sensors = ['sensor.grid_consumption_low', 'sensor.grid_consumption_high', 'sensor.grid_production_low',
                        'sensor.grid_production_high']
        today = datetime.datetime.utcnow().date()
        consumption = 0
        production = 0
        sql = "FLUSH TABLES"
        self.db_ha.run_sql(sql)
        for sensor in grid_sensors:
            sql = (
                    "(SELECT CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') moment, statistics.state "
                    "FROM `statistics`, `statistics_meta` "
                    "WHERE statistics_meta.`id` = statistics.`metadata_id` "
                    "AND statistics_meta.`statistic_id` = '" + sensor + "' "
                    "AND `state` IS NOT null "
                    "AND (CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') BETWEEN '" + start.strftime('%Y-%m-%d') + "' "
                        "AND '" + until.strftime('%Y-%m-%d %H:%M') + "') "
                    "ORDER BY `start_ts` ASC LIMIT 1) " 
                    "UNION "
                    "(SELECT CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') moment, statistics.state "
                    "FROM `statistics`, `statistics_meta` "
                    "WHERE statistics_meta.`id` = statistics.`metadata_id` "
                    "AND statistics_meta.`statistic_id` = '" + sensor + "' "
                    "AND `state` IS NOT null "                    
                    "AND (CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') BETWEEN '" + start.strftime('%Y-%m-%d') + "' "
                        "AND '" + until.strftime('%Y-%m-%d %H:%M') + "') "
                    "ORDER BY `start_ts` DESC LIMIT 1); "
            )
            data = self.db_ha.run_select_query(sql)
            if len(data.index) == 2:
                value = data['state'][1] - data['state'][0]
                if 'consumption' in sensor:
                    consumption = consumption + value
                elif 'production' in sensor:
                    production = production + value

        self.db_ha.disconnect()
        '''
        result = {"consumption": consumption, "production": production}

        print(result)
        return result

    def calc_optimum(self, show_graph=False):

        def calc_da_avg():
            sql_avg = (
                "SELECT AVG(t1.`value`) avg_da FROM "
                "(SELECT `time`, `value`,  from_unixtime(`time`) 'begin' "
                "FROM `values` , `variabel` "
                "WHERE `variabel`.`code` = 'da' AND `values`.`variabel` = `variabel`.`id` "
                "ORDER BY `time` desc LIMIT 24) t1 "
            )
            data = self.db_da.run_select_query(sql_avg)
            result = float(data['avg_da'].values[0])
            return result

        self.db_da.connect()

        now_dt = int(datetime.datetime.now().timestamp())

        offset = 0  # offset in uren
        now_h = int(3600 * (math.floor(now_dt / 3600)) + offset * 3600)
        fraction_first_hour = 1 - (now_dt - now_h) / 3600

        prog_data = self.db_da.getPrognoseData(start=now_h, end=None)
        # start = datetime.datetime.timestamp(datetime.datetime.strptime("2022-05-27", "%Y-%m-%d"))
        # end = datetime.datetime.timestamp(datetime.datetime.strptime("2022-05-29", "%Y-%m-%d"))
        # prog_data = db_da.getPrognoseData(start, end)
        u = len(prog_data)
        if u <= 2 :
            print("Er ontbreken voor een aantal uur gegevens (meteo en/of dynamische prijzen)\n",
                  "er kan niet worden gerekend")
            if self.notification_entity != None:            
                self.set_value(self.notification_entity,
                           "Er ontbreken voor een aantal uur gegevens; er kan niet worden gerekend")
            return

        if u <= 8:
            print("Er ontbreken voor een aantal uur gegevens (meteo en/of dynamische prijzen)\n",
                  "controleer of alle gegevens zijn opgehaald")
            if self.notification_entity != None:            
                self.set_value(self.notification_entity,
                           "Er ontbreken voor een aantal uur gegevens")
                
        if self.notification_entity != None:
            if self.notification_options["berekening"].lower() == "true":
                self.set_value(self.notification_entity, "DAO calc gestart " + datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))

        print("\nPrognose data:")
        print(prog_data)

        '''
        day_ahead prijs omrekenen naar twee prijzen
        1. pl: prijs voor verbruik (levering)
            altijd met opslag voor 
            eb_l 0,12599 (2023)
            opslag leverancier, ol_l 0,001 (tibber)
            btw over het geheel 21%
        2. pt: prijs voor teruglevering
            alleen opslag voor saldering, 
            na 6 maanden saldo levering/teruglevering , als teruglevering > levering dan geen opslag eb en ode
            eb_t 0,12955
            opslag leverancier ol_t (aftrek!!) 0,0
            en btw over het geheel 21%
        '''
        taxes_l_def = self.prices_options["energy taxes delivery"]  # eb + ode levering
        # eb_l = 0.12955
        ol_l_def = self.prices_options["cost supplier delivery"]  # opslag kosten leverancier
        # ol_l_def ["2022-01-01] = 0.002
        # ol_l_def ["2023-03-01] = 0.018
        taxes_t_def = self.prices_options["energy taxes redelivery"]  # eb+ode teruglevering
        # eb_t = 0.12955
        # eb_t = 0
        # ode_t = 0
        ol_t_def = self.prices_options["cost supplier redelivery"]
        # ol_t = 0 #-0.011
        btw_def = self.prices_options["vat"]
        # btw = 0.09

        # prijzen van een traditionele leverancier zijn alleen indicatief; er wordt niet mee gerekend
        gc_p_low = self.prices_options['regular low']
        gc_p_high = self.prices_options['regular high']
        pl = []  # prijs levering day_ahead
        pt = []  # prijs teruglevering day_ahead
        pl_avg = []  # prijs levering day_ahead gemiddeld
        pt_notax = []  # prijs teruglevering day ahead zonder taxes
        uur = []  # datum_tijd van het betreffende uur
        prog_data = prog_data.reset_index()  # make sure indexes pair with number of rows
        for row in prog_data.itertuples():
            uur.append(row.tijd)
            dag_str = row.tijd.strftime("%Y-%m-%d")
            ol_l = get_value_from_dict(dag_str, ol_l_def)
            ol_t = get_value_from_dict(dag_str, ol_t_def)
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            taxes_t = get_value_from_dict(dag_str, taxes_t_def)
            btw = get_value_from_dict(dag_str, btw_def)
            price_l = round((row.da_price + taxes_l + ol_l) * (1 + btw / 100), 5)
            price_t = round((row.da_price + taxes_t + ol_t) * (1 + btw / 100), 5)
            pl.append(price_l)
            pt.append(price_t)
            # tarief teruglevering zonder eb en btw
            price_t_notax = (row.da_price + ol_t)
            pt_notax.append(price_t_notax)

        U = len(pl)
        if U >= 24:
            p_avg = sum(pl) / U  # max(pl) #
        else:
            dag_str = datetime.datetime.now().strftime("%Y-%m-%d")
            ol_l = get_value_from_dict(dag_str, ol_l_def)
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            btw = get_value_from_dict(dag_str, btw_def)
            p_avg = (calc_da_avg() + taxes_l + ol_l) * (1 + btw / 100)
            
        print("\nPrijs levering:")
        pprint(pl)

        print("\nPrijs teruglevering:")
        pprint(pt)
        
        for u in range(U):
            pl_avg.append(p_avg)

        # base load
        print("\nBase load:")
        pprint(self.base_cons)  # basislast van 0 tot 23 uur

        # 0.015 kWh/J/cm² productie van mijn panelen per J/cm²
        pv_yield = []
        solar_prod = []
        solar_num = len(self.solar)
        for s in range(solar_num):
            pv_yield.append(self.config.get(["yield"], self.solar[s]))
            solar_prod.append([])

        b_l = []  # basislast verbruik
        uur = []  # hulparray met uren
        tijd = []
        ts = []
        global_rad = []  #globale straling per uur
        pv_org = []  # opwekking zonnepanelen
        p_grl = []  # prijs levering
        p_grt = []  # prijs teruglevering
        hour_fraction = []
        prog_data = prog_data.reset_index()  # make sure indexes pair with number of rows
        first_hour = True

        for row in prog_data.itertuples():
            dtime = datetime.datetime.fromtimestamp(row.time)
            hour = int(dtime.hour)
            uur.append(hour)
            tijd.append(dtime)
            b_l.append(self.base_cons[hour])
            global_rad.append(row.glob_rad)
            pv_total = 0
            if first_hour:
                ts.append(now_dt)
                hour_fraction.append(fraction_first_hour)
                #pv.append(pv_total * fraction_first_hour)
            else:
                ts.append(row.time)
                hour_fraction.append(1)
                #pv.append(pv_total)
            for s in range(solar_num):
                prod = self.meteo.calc_solar_rad(self.solar[s], row.time, row.glob_rad) * pv_yield[s] * hour_fraction[-1]
                solar_prod[s].append(prod)
                pv_total += prod
            pv_org.append(pv_total)
            dag_str = dtime.strftime("%Y-%m-%d")
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            taxes_t = get_value_from_dict(dag_str, taxes_t_def)
            btw = get_value_from_dict(dag_str, btw_def)
            if is_laagtarief(datetime.datetime(dtime.year, dtime.month, dtime.day, hour), \
                             self.prices_options["switch to low"]):
                p_grl.append((gc_p_low + taxes_l) * (1 + btw / 100))
                p_grt.append((gc_p_low + taxes_t) * (1 + btw / 100))
            else:
                p_grl.append((gc_p_high + taxes_l) * (1 + btw / 100))
                p_grt.append((gc_p_high + taxes_t) * (1 + btw / 100))
            first_hour = False

        # volledig salderen?
        salderen = self.prices_options['tax refund'] == "True"

        last_invoice = datetime.datetime.strptime(self.prices_options['last invoice'], "%Y-%m-%d")
        cons_data_history = self.get_consumption(last_invoice, datetime.datetime.today())
        if not salderen:
            salderen = cons_data_history["production"] < cons_data_history["consumption"]

        if salderen:
            print("All taxes refund (alles wordt gesaldeerd)")
            consumption_today = 0
            production_today = 0
        else:
            consumption_today = float(self.get_state("sensor.daily_grid_consumption").state)
            production_today = float(self.get_state("sensor.daily_grid_production").state)
            print("consumption today: ", consumption_today)
            print("production today: ", production_today)
            print("verschil: ", consumption_today - production_today)

        model = Model()

        # reken met prijzen traditionele leverancier
        # pl = p_grl
        # pt = p_grt

        ##############################################################
        #                          pv
        ##############################################################
        pv_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=solar_prod[s][u] * 1.1) for u in range(U)] for s in range(solar_num)]
        pv_ac_on_off = [[model.add_var(var_type=BINARY) for u in range(U)] for s in range(solar_num)]
        for s in range(solar_num):
            for u in range(U):
                model += pv_ac[s][u] == solar_prod[s][u] * pv_ac_on_off[s][u]


        ##############################################################
        #                          accu / batterij
        ##############################################################
        # accu capaciteit
        # 2 batterijen 50V 280Ah
        B = len(self.battery_options)
        one_soc = []
        kwh_cycle_cost = []
        start_soc = []
        opt_low_level = []
        pv_dc = [] #pv bruto productie per batterij per uur
        pv_dc_hour_sum = []
        pv_from_dc_hour_sum = [] #de som van pv_dc productie geleverd aan ac per uur
        #eff_ac_to_dc = []
        eff_dc_to_ac = []
        eff_dc_to_bat = []
        eff_bat_to_dc = []
        #max_ac_to_dc = []
        #max_dc_to_ac = []

        CS = []
        DS = []
        max_charge_power = []
        max_discharge_power = []
        avg_eff_dc_to_ac = []
        pv_dc_num = []
        pv_prod_dc = []
        pv_prod_ac = []
        for b in range(B):
            pv_prod_ac.append([])
            pv_prod_dc.append([])
            max_charge_power.append(self.battery_options[b]["charge stages"][-1]["power"]/1000)
            CS.append(len(self.battery_options[b]["charge stages"]))
            max_discharge_power.append(self.battery_options[b]["discharge stages"][-1]["power"]/1000)
            DS.append(len(self.battery_options[b]["discharge stages"]))
            sum_eff = 0
            for ds in range(DS[b])[1:]:
                sum_eff += self.battery_options[b]["discharge stages"][ds]["efficiency"]
            avg_eff_dc_to_ac.append(sum_eff/(DS[b]-1))

            ac = float(self.battery_options[b]["capacity"])  # 2 * 50 * 280/1000 #=28 kWh
            one_soc.append(ac / 100) # 1% van 28 kWh = 0,28 kWh
            kwh_cycle_cost.append(self.battery_options[b]["cycle cost"])
            # kwh_cycle_cost = (cycle_cost/( 2 * ac) ) / ((self.battery_options["upper limit"] -
            #   self.battery_options["lower limit"]) / 100)
            # print ("cycle cost: ", kwh_cycle_cost, " eur/kWh")

            eff_dc_to_bat.append(float(self.battery_options[b]["dc_to_bat efficiency"]))  # fractie van 1
            eff_bat_to_dc.append(float(self.battery_options[b]["bat_to_dc efficiency"]))  # fractie van 1

            # state of charge
            # start soc
            start_soc_str = self.get_state(self.battery_options[b]["entity actual level"]).state
            if start_soc_str.lower() == "unavailable":
                start_soc.append(50)
            else:
                start_soc.append(float(start_soc_str))
            opt_low_level.append(float(self.battery_options[b]["optimal lower level"]))

            # pv dc
            pv_dc_num.append(len(self.battery_options[b]["solar"]))
            pv_dc_bat = []
            for s in range(pv_dc_num[b]):
                pv_prod_dc[b].append([])
                pv_prod_ac[b].append([])
                pv_yield = self.battery_options[b]["solar"][s]["yield"]
                for u in range(U):
                    #pv_prod productie van batterij b van solar s in uur u
                    prod_dc = self.meteo.calc_solar_rad(self.battery_options[b]["solar"][s], int(tijd[u].timestamp()), global_rad[u]) * pv_yield
                    efficiency = 1
                    for ds in range(DS[b]):
                        if self.battery_options[b]["discharge stages"][ds]["power"]/1000 > prod_dc:
                            efficiency = self.battery_options[b]["discharge stages"][ds]["efficiency"]
                            break
                    prod_ac = prod_dc * efficiency
                    pv_prod_dc[b][s].append(prod_dc)
                    pv_prod_ac[b][s].append(prod_ac)

        # energie per uur, vanuit dc gezien
        #ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * \
        #                max_ac_to_dc[b]) for u in range(U)] for b in range(B) ]
        #totaal elektra van ac naar de busbar, ieder uur
        pv_dc_on_off = [[[model.add_var(var_type=BINARY) for u in range(U)] for s in range(pv_dc_num[b])] for b in range(B) ]
        pv_prod_dc_sum = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b]) for u in range(U)] for b in range(B)]
        ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b]) for u in range(U)] for b in range(B)]
        dc_from_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b]) for u in range(U)] for b in range(B)]
        # elektra per vermogensklasse van ac naar de busbar, ieder uur
        ac_to_dc_st = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=self.battery_options[b]["charge stages"][cs]["power"]/1000)
                       for u in range(U)] for cs in range(CS[b])] for b in range(B)]
        # elektra per vermogensklasse van busbar naar ac, ieder uur
        dc_to_ac_st = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=self.battery_options[b]["discharge stages"][ds]["power"]/1000)
                       for u in range(U)] for ds in range(DS[b])] for b in range(B)]

        ac_to_dc_on = [[model.add_var(var_type=BINARY) for u in range(U)] for b in range(B) ]
        dc_to_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * \
                        max_discharge_power[b]) for u in range(U)] for b in range(B) ]
        ac_from_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_discharge_power[b])
                       for u in range(U)] for b in range(B)]
        dc_to_ac_on = [[model.add_var(var_type=BINARY) for u in range(U)] for b in range(B)]
        bat_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * 2 * max_discharge_power[b])
                        for u in range(U)] for b in range(B) ]
        dc_to_bat = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * 2 * max_charge_power[b])
                        for u in range(U)] for b in range(B) ]

        # vermogens klasse aan/uit
        ac_to_dc_st_on = [[[model.add_var(var_type=BINARY) for u in range(U)] for cs in range(CS[b])] for b in range(B)]
        dc_to_ac_st_on = [[[model.add_var(var_type=BINARY) for u in range(U)] for ds in range(DS[b])] for b in range(B)]

        soc = [[model.add_var(var_type=CONTINUOUS, lb=min(start_soc[b], float(self.battery_options[b]["lower limit"])), \
                 ub=max(start_soc[b], float(self.battery_options[b]["upper limit"]))) for u in range(U + 1)] for b in range(B)]
        soc_low = [[model.add_var(var_type=CONTINUOUS, lb=min(start_soc[b], float(self.battery_options[b]["lower limit"])), \
                    ub=opt_low_level[b]) for u in range(U + 1)] for b in range(B) ]
        soc_mid = [[model.add_var(var_type=CONTINUOUS, lb=0, \
                    ub=-opt_low_level[b] + max(start_soc[b], float(self.battery_options[b]["upper limit"])))
                   for u in range(U + 1)] for b in range(B) ]

        for b in range(B):
            for u in range(U):
                #laden
                for cs in range(CS[b]):
                    model += ac_to_dc_st[b][cs][u] <= self.battery_options[b]["charge stages"][cs]["power"] * ac_to_dc_st_on[b][cs][u]/1000
                for cs in range(CS[b])[1:]:
                    model += ac_to_dc_st[b][cs][u] >= self.battery_options[b]["charge stages"][cs-1]["power"] * ac_to_dc_st_on[b][cs][u]/1000
                model += ac_to_dc[b][u] == xsum(ac_to_dc_st[b][cs][u] for cs in range(CS[b]))
                model += (xsum(ac_to_dc_st_on[b][cs][u] for cs in range(CS[b]))) <= 1
                model += dc_from_ac[b][u] == xsum(ac_to_dc_st[b][cs][u] * self.battery_options[b]["charge stages"][cs]["efficiency"] for cs in range(CS[b]))
                #ontladen
                for ds in range(DS[b]):
                    model += dc_to_ac_st[b][ds][u] <= self.battery_options[b]["discharge stages"][ds]["power"] * dc_to_ac_st_on[b][ds][u]/1000
                for ds in range(DS[b])[1:]:
                    model += dc_to_ac_st[b][ds][u] >= self.battery_options[b]["discharge stages"][ds-1]["power"] * dc_to_ac_st_on[b][ds][u]/1000
                model += dc_to_ac[b][u] == xsum(dc_to_ac_st[b][ds][u] for ds in range(DS[b]))
                model += (xsum(dc_to_ac_st_on[b][ds][u] for ds in range(DS[b]))) <= 1
                model += ac_from_dc[b][u] == xsum(dc_to_ac_st[b][ds][u] / self.battery_options[b]["discharge stages"][ds]["efficiency"] for ds in range(DS[b]))


        for b in range(B):
            for u in range(U + 1):
                model += soc[b][u] == soc_low[b][u] + soc_mid[b][u]
            model += soc[b][0] == start_soc[b]
            min_soc_end_opt = float(self.get_state(self.battery_options[b]["entity min soc end opt"]).state)
            max_soc_end_opt = float(self.get_state(self.battery_options[b]["entity max soc end opt"]).state)
            model += soc[b][U] >= max(opt_low_level[b] / 2, min_soc_end_opt)
            model += soc[b][U] <= max_soc_end_opt
            for u in range(U):
                model += soc[b][u + 1] == soc[b][u] + (dc_to_bat[b][u] * eff_dc_to_bat[b] / one_soc[b]) - ((bat_to_dc[b][u] / eff_bat_to_dc[b]) / one_soc[b])
                model += pv_prod_dc_sum[b][u] == xsum(pv_prod_dc[b][s][u] *  pv_dc_on_off[b][s][u] for s in range (pv_dc_num[b]))
                model += dc_from_ac[b][u] + bat_to_dc[b][u] + pv_prod_dc_sum[b][u] == ac_from_dc[b][u] + dc_to_bat[b][u]
                model += dc_from_ac[b][u] <= ac_to_dc_on[b][u] * max_charge_power[b]
                model += dc_to_ac[b][u] <= dc_to_ac_on[b][u] * max_discharge_power[b]
                model += (ac_to_dc_on[b][u] + dc_to_ac_on[b][u] ) <= 1


        #####################################
        #             boiler                #
        #####################################
        boiler_on = [model.add_var(var_type=BINARY) for u in range(U)]
        self.boiler_present = self.boiler_options["boiler present"].lower() == "true"
        if not self.boiler_present:
            #default values
            boiler_setpoint = 50
            boiler_hysterese = 10
            spec_heat_boiler = 200 * 4.2 + 100 * 0.5  # kJ/K
            cop_boiler = 3
            boiler_temp = [model.add_var(var_type=CONTINUOUS, lb=20, ub=20) for u in range(U + 1)]  # end temp boiler
            c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]  # consumption boiler
            model += xsum(boiler_on[j] for j in range(U)) == 0
            print("Geen boiler aanwezig")
        else:
            # 50 huidige boilertemperatuur ophalen uit ha
            boiler_act_temp = float(self.get_state(self.boiler_options["entity actual temp."]).state)
            boiler_setpoint = float(self.get_state(self.boiler_options["entity setpoint"]).state)
            boiler_hysterese = float(self.get_state(self.boiler_options["entity hysterese"]).state)
            boiler_cooling = self.boiler_options["cooling rate"]  # 0.4 #K/uur instelbaar
            boiler_bovengrens = self.boiler_options["heating allowed below"]  # 45 # oC instelbaar daaronder kan worden verwarmd
            boiler_bovengrens = min(boiler_bovengrens, boiler_setpoint)
            boiler_ondergrens = boiler_setpoint - boiler_hysterese  # 41 #C instelbaar daaronder moet worden verwarmd
            vol = self.boiler_options["volume"]  # liter
            # spec heat in kJ/K = vol in liter * 4,2 J/liter + 100 kg * 0,5 J/kg
            spec_heat_boiler = vol * 4.2 + 200 * 0.5  # kJ/K
            cop_boiler = self.boiler_options["cop"]
            power = self.boiler_options["elec. power"]  # W

            # tijdstip index waarop boiler kan worden verwarmd
            boiler_start = int(max(0, min(23, int((boiler_act_temp - boiler_bovengrens) / boiler_cooling))))

            # tijdstip index waarop boiler nog aan kan
            boiler_end = int(min(U - 1, max(0, int((boiler_act_temp - boiler_ondergrens) / boiler_cooling))))  # (41-40)/0.4=2.5


            boiler_temp = [
                model.add_var(var_type=CONTINUOUS, lb=min(boiler_act_temp,boiler_setpoint - boiler_hysterese - 10), ub=boiler_setpoint + 10)
                for u in range(U + 1)]  # end temp boiler

            if boiler_start > boiler_end:  # geen boiler opwarming in deze periode
                c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]  # consumption boiler
                model += xsum(boiler_on[j] for j in range(U)[boiler_start:boiler_end + 1]) == 0
                print("\nBoiler: geen opwarming")
                boiler_end_temp = boiler_act_temp - boiler_cooling * U
                print("Boiler eind temperatuur: ", boiler_end_temp)
                for u in range(U):
                    # opwarming in K = kWh opwarming * 3600 = kJ / spec heat boiler - 3
                    model += boiler_temp[u + 1] == boiler_temp[u] - boiler_cooling
            else:
                print("\nBoiler: ", uur[boiler_start], uur[boiler_end])
                needed_elec = [0.0 for u in range(U)]
                needed_time = [0 for u in range(U)]
                needed_heat = max(0.0, float(spec_heat_boiler * (
                        boiler_setpoint - (boiler_act_temp - 4 - boiler_cooling * (boiler_end - boiler_start))) / 3600))  # kWh
                for u in range(boiler_start, boiler_end + 1):
                    #needed_heat = max(0.0, float(spec_heat_boiler * (
                    #        boiler_setpoint - (boiler_act_temp - 4 - boiler_cooling * (u - boiler_start))) / 3600))  # kWh
                    needed_elec[u] = needed_heat / cop_boiler  # kWh
                    needed_time[u] = needed_elec[u] * 1000 / power  # hour

                c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=needed_elec[u]) for u in range(U)]  # cons. boiler
                for u in range(U):
                    model += c_b[u] == boiler_on[u] * needed_elec[u]
                    if u < boiler_start:
                        model += boiler_on[u] == 0
                    elif u > boiler_end:
                        model += boiler_on[u] == 0
                model += xsum(boiler_on[j] for j in range(U)[boiler_start:boiler_end + 1]) == 1
                model += boiler_temp[0] == boiler_act_temp
                for u in range(U):
                    # opwarming in K = kWh opwarming * 3600 = kJ / spec heat boiler - 3
                    model += boiler_temp[u + 1] == boiler_temp[u] - boiler_cooling + c_b[u] * cop_boiler \
                             * 3600 / spec_heat_boiler

        ################################################
        #             electric vehicles
        ################################################
        EV = len(self.ev_options)
        actual_soc = []
        wished_level = []
        ready_u = []
        hours_needed = []
        max_power = []
        energy_needed = []
        ev_plugged_in = []
        ev_position = []
        now_dt = datetime.datetime.now()
        for e in range(EV):
            ev_capacity = self.ev_options[e]["capacity"]
            # plugged = self.get_state(self.ev_options["entity plugged in"]).state
            try:
                plugged_in = self.get_state(self.ev_options[e]["entity plugged in"]).state == "on"

            except:
               plugged_in = False
            ev_plugged_in.append(plugged_in)
            try:
                position = self.get_state(self.ev_options[e]["entity position"]).state
            except:
                position = "away"
            ev_position.append(position)
            try:
                soc_state = float(self.get_state(self.ev_options[e]["entity actual level"]).state)
            except:
                soc_state = 100.0
            actual_soc.append(soc_state)
            wished_level.append(float(self.get_state(self.ev_options[e]["charge scheduler"]["entity set level"]).state))
            ready_str = self.get_state(self.ev_options[e]["charge scheduler"]["entity ready datetime"]).state
            if len(ready_str) > 9:
                #dus met datum en tijd
                ready = datetime.datetime.strptime(ready_str, '%Y-%m-%d %H:%M:%S')
            else:
                ready = datetime.datetime.strptime(ready_str, '%H:%M:%S')
                ready = datetime.datetime(now_dt.year, now_dt.month, now_dt.day, ready.hour, ready.minute)
                if (ready.hour == now_dt.hour and ready.minute < now_dt.minute) or (ready.hour < now_dt.hour):
                    ready = ready + datetime.timedelta(days=1)
            max_ampere = self.get_state(self.ev_options[e]["entity max amperage"]).state
            try:
                max_ampere = float(max_ampere)
            except ValueError:
                max_ampere = 10
            charge_three_phase = self.ev_options[e]["charge three phase"].lower() == "true"
            if charge_three_phase:
                max_power.append(max_ampere * 3 * 230 / 1000) # vermogen in kW
            else:
                max_power.append(max_ampere * 230 / 1000) # vermogen in kW
            print ("\nInstellingen voor laden van EV:", self.ev_options[e]["name"])
            print("Laadvermogen:", max_power[e], "kW")
            print("Klaar met laden op:", ready.strftime('%d-%m-%Y %H:%M:%S'))
            print("Huidig laadniveau:", actual_soc[e], "%")
            print("Gewenst laadniveau:", wished_level[e], "%")
            print("Locatie:", ev_position[e])
            print("Ingeplugged:", ev_plugged_in[e])
            energy_needed.append(ev_capacity * (wished_level[e] - actual_soc[e]) / 100)  # in kWh
            time_needed = energy_needed[e] / max_power[e]  # uitgedrukt in aantal uren; bijvoorbeeld 1,5
            hours_needed.append(math.ceil(time_needed))  # afgerond naar boven in hele uren
            ready_index = U
            if ev_plugged_in[e] and (ev_position[e] == "home") and (wished_level[e] > actual_soc[e]) and \
                    ((tijd[U - 1] + datetime.timedelta(hours=1)) >= ready) and (tijd[0] < ready) :
                for u in range(U):
                    if (tijd[u] + datetime.timedelta(hours=1)) >= ready:
                        ready_index = u
                        break
            if ready_index == U:
                print ("Er wordt niet opgeladen.\n")
            else:
                print("Opladen wordt ingepland.\n")
            ready_u.append(ready_index)

        charger_on = [[model.add_var(var_type=BINARY) for u in range(U)] for e in range(EV)]

        c_ev = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_power[e] * hour_fraction[u])
                 for u in range(U)] for e in range(EV)]  # consumption charger

        for e in range(EV):
            if (energy_needed[e] > 0) and (ready_u[e] < U):
                max_beschikbaar = 0
                for u in range(ready_u[e] + 1):
                    model += c_ev[e][u] <= charger_on[e][u] * hour_fraction[u] * max_power[e]
                    max_beschikbaar += hour_fraction[u] * max_power[e]
                for u in range(ready_u[e] + 1, U):
                    model += charger_on[e][u] == 0
                    model += c_ev[e][u] == 0
                model += xsum(charger_on[e][j] for j in range(ready_u[e] + 1)) == hours_needed[e]
                model += xsum(c_ev[e][u] for u in range(ready_u[e] + 1)) == min(max_beschikbaar, energy_needed[e])
            else:
                model += xsum(c_ev[e][u] for u in range(U)) == 0
                for u in range(U):
                    model += c_ev[e][u] == 0

        ##################################################################
        #            salderen                                            #
        ##################################################################
        # total consumption per hour: base_load plus accuload
        # inkoop + pv + accu_out = teruglevering + base_cons + accu_in + boiler + ev + ruimteverwarming
        # in code:  c_l + pv + accu_out = c_t + b_l + accu_in + hw + ev + rv
        # c_l : verbruik levering
        # c_t : verbruik teruglevering met saldering
        # c_t_notax : verbruik teruglevering zonder saldering
        # pv : opwekking zonnepanelen

        # anders geschreven c_l = c_t + ct_notax + b_l + accu_in + hw + rv - pv - accu_out
        # continue variabele c consumption in kWh/h
        # minimaal 20 kW terugleveren max 20 kW leveren (3 x 25A = 17,5 kW)
        # instelbaar maken?
        # levering
        c_l = [model.add_var(var_type=CONTINUOUS, lb=0, ub=20) for u in range(U)]
        # teruglevering
        c_t_total = [model.add_var(var_type=CONTINUOUS, lb=0, ub=20) for u in range(U)]
        c_t_w_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=20) for u in range(U)]
        c_l_on = [model.add_var(var_type=BINARY) for u in range(U)]
        c_t_on = [model.add_var(var_type=BINARY) for u in range(U)]

        # salderen == True
        #c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]

        if salderen:
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]
        else:
            # alles wat meer wordt teruggeleverd dan geleverd (c_t_no_tax) wordt niet gesaldeerd (geen belasting terug): tarief pt_notax
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]

            """
            if U > 24:
                u_end = U - 24
            else:
                u_end = U

            #als
            if (production_today - consumption_today) > (
                    (u_end - 1 + fraction_first_hour) * float(self.battery_options[0]["max charge power"])):
                marge = production_today - consumption_today
            else:
                marge = 0
            # voor vandaag
            model += (xsum(c_t_w_tax[u] for u in range(u_end)) + production_today) <= \
                     (xsum(c_l[u] for u in range(u_end)) + consumption_today + marge)
            if u_end < U:
                # morgen
                model += xsum(c_t_w_tax[u] for u in range(u_end, U)) <= xsum(c_l[u] for u in range(u_end, U))
            """
            model += (xsum(c_t_w_tax[u] for u in range(U)) + production_today) <= \
                     (xsum(c_l[u] for u in range(U)) + consumption_today )
        #netto per uur alleen leveren of terugleveren niet tegelijk?
        for u in range(U):
            model += c_t_total[u] == c_t_w_tax[u] + c_t_no_tax[u]
            model += c_l[u] <= c_l_on[u] * 20
            model += c_t_total[u] <= c_t_on[u] * 20
            model += c_l_on[u] + c_t_on[u] <= 1

        #####################################
        #              heatpump             #
        #####################################

        self.heater_present = self.heating_options["heater present"].lower() == "true"
        if not self.heater_present:
            c_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]  # elektriciteitsverbruik in kWh/h
            p_hp = None
            h_hp = None
        else:
            degree_days = self.meteo.calc_graaddagen()
            if U > 24:
                degree_days += self.meteo.calc_graaddagen(date=datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.datetime.min.time()))
            print("\nWarmtepomp")
            print("Graaddagen: ", degree_days)

            degree_days_factor = self.heating_options["degree days factor"]  # 3.6  heat factor kWh th / K.day
            heat_produced = float(self.get_state("sensor.daily_heat_production_heating").state)
            heat_needed = max(0.0, degree_days * degree_days_factor - heat_produced)  # heet needed
            stages = self.heating_options["stages"]
            S = len(stages)
            c_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]  # elektriciteitsverbruik in kWh/h
            #p_hp[s][u] : het gevraagde vermogen in W in dat uur
            p_hp = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=stages[s]["max_power"]) for u in range(U)] for s in range(S)]

            # schijven aan/uit, iedere schijf kan maar een keer in een uur
            hp_on = [[model.add_var(var_type=BINARY) for u in range(U)] for s in range(S)]

            # verbruik per uur
            for u in range(U):
                # verbruik in kWh is totaal vermogen in W/1000
                model += c_hp[u] == (xsum(p_hp[s][u] for s in range(S))) / 1000
                #kosten
                #model += k_hp[u] == c_hp[u] * pl[u]  # kosten = verbruik x tarief

            # geproduceerde warmte kWh per uur
            h_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10000) for u in range(U)]

            #beschikbaar vermogen x aan/uit, want p_hpx[u] X hpx_on[u] kan niet
            for u in range(U):
                for s in range(S):
                    model += p_hp[s][u] <= stages[s]["max_power"] * hp_on[s][u]
                #ieder uur maar een aan
                model += (xsum(hp_on[s][u] for s in range(S))) + boiler_on[u] == 1
                # geproduceerde warmte = vermogen in W * COP_schijf /1000 in kWh
                model += h_hp[u] == xsum ( (p_hp[s][u] * stages[s]["cop"]/1000)  for s in range (S)) * hour_fraction[u]
            model += xsum(h_hp[u] for u in range(U)) == heat_needed  # som van alle geproduceerde warmte == benodigde warmte


        #alle verbruiken in de totaal balans
        for u in range(U):
            model += c_l[u] == c_t_total[u] + b_l[u] + \
                     xsum(ac_to_dc[b][u] - dc_to_ac[b][u] for b in range(B)) + \
                     c_b[u] + xsum(c_ev[e][u] for e in range(EV)) + c_hp[u] - xsum(pv_ac[s][u] for s in range(solar_num))

        #cost variabele
        cost = model.add_var(var_type=CONTINUOUS, lb=-1000, ub=1000)
        delivery = model.add_var(var_type=CONTINUOUS, lb=0, ub=1000)
        model += delivery == xsum(c_l[u] for u in range(U))

        if salderen:
            p_bat = p_avg
        else:
            p_bat = sum(pt_notax)/U

        model += cost == xsum(c_l[u] * pl[u] - c_t_w_tax[u] * pt[u] - c_t_no_tax[u] * pt_notax[u] for u in range(U) ) + \
                     xsum(xsum((dc_to_bat[b][u] + bat_to_dc[b][u]) * kwh_cycle_cost[b] + (opt_low_level[b] - soc_low[b][u]) * 0.0025
                        for u in range(U)) for b in range(B)) + \
                xsum((soc_mid[b][0] - soc_mid[b][U]) * one_soc[b] * eff_bat_to_dc[b] * avg_eff_dc_to_ac[b] * p_bat for b in range(B)) # waarde opslag accu
                # + (boiler_temp[U] - boiler_ondergrens) * (spec_heat_boiler/(3600 * cop_boiler)) * p_avg # waarde energie boiler

        #settings
        model.max_gap = 0.05
        model.max_nodes = 500

        # kosten optimalisering
        strategy = self.strategy.lower()
        if strategy == "minimize cost":
            strategie = 'minimale kosten'
            model.objective = minimize(cost)
            model.optimize()
            if model.num_solutions == 0:
                print("Geen oplossing  voor:", strategy)
                return
        elif strategy == "minimize consumption":
            strategie = 'minimale levering'
            model.objective = minimize(delivery)
            model.optimize()
            if model.num_solutions == 0:
                print("Geen oplossing  voor:", strategy)
                return
            min_delivery = max(0.0, delivery.x)
            print("Ronde 1")
            print("Kosten (euro): {:<6.2f}".format(cost.x))
            print("Levering (kWh): {:<6.2f}".format(delivery.x))
            model += (delivery <= min_delivery)
            model.objective = minimize(cost)
            model.optimize()
            if model.num_solutions == 0:
                print("Geen oplossing in ronde 2 voor:", strategy)
                return
            print("Ronde 2")
            print("Kosten (euro): {:<6.2f}".format(cost.x))
            print("Levering (kWh): {:<6.2f}".format(delivery.x))
        else:
            print("Kies een strategie in options")
            strategie = 'niet gekozen'     
            return
        print("Strategie: " + strategie + "\n") 

        if model.num_solutions: #er is een oplossing
            #afdrukken van de resultaten
            old_cost_gc = 0
            old_cost_da = 0
            sum_old_cons = 0
            org_l = []
            org_t = []
            c_ev_sum = []
            accu_in_sum = []
            accu_out_sum = []
            for u in range(U):
                ac_to_dc_sum = 0
                dc_to_ac_sum = 0
                for b in range(B):
                    ac_to_dc_sum += ac_to_dc[b][u].x # / eff_ac_to_dc[b]
                    dc_to_ac_sum += dc_to_ac[b][u].x # * eff_dc_to_ac[b]
                accu_in_sum.append(ac_to_dc_sum)
                accu_out_sum.append(dc_to_ac_sum)
            for u in range(U):
                ev_sum = 0
                for e in range(EV):
                    ev_sum += c_ev[e][u].x
                c_ev_sum.append(ev_sum)
            pv_ac_hour_sum = []
            solar_hour_sum = []
            for u in range(U):
                pv_ac_hour_sum.append(0)
                solar_hour_sum.append(0)
                for b in range(B):
                    for s in range(pv_dc_num[b]):
                        pv_ac_hour_sum[u] += pv_prod_ac[b][s][u]
                for s in range(solar_num):
                    solar_hour_sum[u] += pv_ac[s][u].x
                netto = b_l[u] + c_b[u].x + c_hp[u].x + c_ev_sum[u] - solar_hour_sum[u] - pv_ac_hour_sum[u]
                sum_old_cons += netto
                if netto >= 0:
                    old_cost_gc += netto * p_grl[u]
                    old_cost_da += netto * pl[u]
                    org_l.append(netto)
                    org_t.append(0)
                else:
                    old_cost_gc += netto * p_grt[u]
                    old_cost_da += netto * pt[u]
                    org_l.append(0)
                    org_t.append(netto)
            if (not salderen) and (sum_old_cons < 0):
                #er wordt (een deel) niet gesaldeerd
                dag_str = datetime.datetime.now().strftime("%Y-%m-%d")
                taxes_l = get_value_from_dict(dag_str, taxes_l_def)
                btw = get_value_from_dict(dag_str, btw_def)
                saldeer_corr_gc = -sum_old_cons * (sum(p_grt) / len(p_grt) - 0.11)
                saldeer_corr_da = -sum_old_cons * taxes_l * (1 + btw)
                old_cost_gc += saldeer_corr_gc
                old_cost_da += saldeer_corr_da
                print("Saldeercorrectie: {:<6.2f} kWh".format(sum_old_cons))
                print("Saldeercorrectie niet geoptimaliseerd reg. tarieven: {:<6.2f} euro".format(saldeer_corr_gc))
                print("Saldeercorrectie niet geoptimaliseerd day ahead tarieven: {:<6.2f} euro".format(saldeer_corr_da))
            else:
                print("Geen saldeer correctie")
            print("Niet geoptimaliseerd, kosten met reguliere tarieven: {:<6.2f}".format(old_cost_gc))
            print("Niet geoptimaliseerd, kosten met day ahead tarieven: {:<6.2f}".format(old_cost_da))
            print("Geoptimaliseerd, kosten met day ahead tarieven: {:<6.2f}".format(cost.x))
            print("Levering (kWh): {:<6.2f}".format(delivery.x))
            if self.boiler_present:
                print("Waarde boiler om 23 uur: {:<0.2f}".format(
                    (boiler_temp[U].x - (boiler_setpoint - boiler_hysterese)) * (spec_heat_boiler / (3600 * cop_boiler))),
                    "kWh")

            if self.heater_present:
                print("\nInzet warmtepomp")
                print("u     tar     p0     p1     p2     p3     p4     p5     p6     p7   heat   cons")
                for u in range(U):
                    print("{:2.0f}".format(uur[u]), "{:6.4f}".format(pl[u]), "{:6.0f}".format(p_hp[0][u].x), "{:6.0f}".format(p_hp[1][u].x),
                          "{:6.0f}".format(p_hp[2][u].x),
                          "{:6.0f}".format(p_hp[3][u].x), "{:6.0f}".format(p_hp[4][u].x), "{:6.0f}".format(p_hp[5][u].x),
                          "{:6.0f}".format(p_hp[6][u].x), "{:6.0f}".format(p_hp[7][u].x), "{:6.2f}".format(h_hp[u].x),
                          "{:6.2f}".format(c_hp[u].x))
                print("\n")

            #overzicht per ac-accu:
            pd.options.display.float_format = '{:6.2f}'.format
            df_accu = []
            for b in range(B):
                cols = ['uur', 'ac->dc', 'ch_st', 'c_eff', 'dc->ac', 'dc_st', 'd_eff', 'dc->ba', 'ba_dc', 'pv', 'soc']
                df_accu.append(pd.DataFrame(columns=cols))
                for u in range(U):
                    ac_to_dc_eff = "--"
                    c_stage = "--"
                    for cs in range(CS[b]):
                        if ac_to_dc_st_on[b][cs][u].x == 1:
                            c_stage = cs
                            ac_to_dc_eff = self.battery_options[b]["charge stages"][cs]["efficiency"] * 100.0
                    dc_to_ac_eff = "--"
                    d_stage = "--"
                    for ds in range(DS[b]):
                        if dc_to_ac_st_on[b][ds][u].x == 1:
                            d_stage = ds
                            dc_to_ac_eff = self.battery_options[b]["discharge stages"][ds]["efficiency"] * 100.0

                    pv_prod = 0
                    for s in range (pv_dc_num[b]):
                        pv_prod += pv_dc_on_off[b][s][u].x * pv_prod_dc[b][s][u]
                    row = [uur[u], dc_from_ac[b][u].x, c_stage, ac_to_dc_eff, dc_to_ac[b][u].x, d_stage, dc_to_ac_eff, dc_to_bat[b][u].x, bat_to_dc[b][u].x, pv_prod, soc[b][u+1].x]
                    df_accu[b].loc[df_accu[b].shape[0]] = row
                df_accu[b].loc['total'] = df_accu[b].select_dtypes(numpy.number).sum()
                df_accu[b] = df_accu[b].astype({"uur": int})
                print("Batterij:", self.battery_options[b]["name"])
                print("In- en uitgaande energie per uur in kWh op de busbar")
                print(df_accu[b].to_string(index=False))
                print("\n")

            #totaal overzicht
            cols = ['uur', 'bat in', 'bat out']
            cols = cols + ['con_l', 'c_t_t', 'c_t_n', 'bas_l', 'boil', 'wp', 'ev',
                            'pv', 'kos_l',  'k_t_t', 'k_t_n', 'kos_t', 'b_tem']
            d_f = pd.DataFrame(columns=cols)
            for u in range(U):
                row = [uur[u], accu_in_sum[u], accu_out_sum[u]]
                row = row + [c_l[u].x, c_t_w_tax[u].x, c_t_no_tax[u].x, b_l[u], \
                            c_b[u].x, c_hp[u].x, c_ev_sum[u], solar_hour_sum[u], c_l[u].x * pl[u], -c_t_w_tax[u].x * pt[u], \
                            -c_t_no_tax[u].x * pt_notax[u], -c_t_w_tax[u].x * pt[u] -c_t_no_tax[u].x * pt_notax[u], \
                             boiler_temp[u + 1].x]
                d_f.loc[d_f.shape[0]] = row
                '''
                print ("{:2}".format(uur[u]), "{:6.2f}".format(ac_to_dc_sum), "{:6.2f}".format(dc_to_ac_sum),
                       "{:6.2f}".format(c_l[u].x), "{:6.2f}".format(c_t_total[u].x), "{:6.2f}".format(b_l[u]),
                       "{:6.2f}".format(c_b[u].x), "{:6.2f}".format(c_ev[u].x),
                       "{:6.2f}".format(pv[u]), "{:6.2f}".format(c_l[u].x*pl[u]), "{:6.2f}".format(-c_t_total[u].x*pt[u]))
    
            sys.stdout.write('\n')
            '''
            #pd.options.display.float_format = '{:6.2f}'.format
            d_f.loc['total'] = d_f.select_dtypes(numpy.number).sum()
            d_f = d_f.astype({"uur": int})
            print(d_f.to_string(index=False))
            print("\nWinst: {:<0.2f}".format(old_cost_da - cost.x), "€")

            # doorzetten van alle settings naar HA
            if not self.debug:
                print("\nDoorzetten van alle settings naar HA")

                '''
                set helpers output home assistant
                boiler c_b[0].x >0 trigger boiler
                ev     c_ev[0].x > 0 start laden auto, ==0 stop laden auto
                battery multiplus feedin from grid = accu_in[0].x - accu_out[0].x
                '''
                # boiler
                if self.boiler_present:
                    if float(c_b[0].x) > 0.0:
                        self.call_service(self.boiler_options["activate service"],
                                          entity_id = self.boiler_options["activate entity"])
                        # "input_button.hw_trigger")
                        print("Boiler opwarmen geactiveerd")

                # ev
                for e in range(EV):
                    entity_charge_switch = self.ev_options[e]["charge switch"]
                    state = self.get_state(entity_charge_switch).state
                    if ev_position[e] == "home" and ev_plugged_in[e]:
                        ev_name = self.ev_options[e]["name"]
                        try:
                            if float(c_ev[e][0].x) > 0.0:
                                if state == "off":
                                    self.turn_on(entity_charge_switch)
                                    print(f"Laden van {ev_name}+aangezet")
                            else:
                                if state == "on":
                                    self.turn_off(entity_charge_switch)
                                    print(f"Laden van {ev_name}+uitgezet")
                        except BaseException:
                            pass
#                    else:
#                        self.turn_off(entity_charge_switch)  # charger uitzetten indien niet ingeplugd of niet thuis
#geeft error, bovendien als je elders aan de laadpaal staat moet ie doorgaan!

                #solar
                for s in range(solar_num):
                    entity_pv_switch = self.config.get(["entity pv switch"], self.solar[s])
                    if pv_ac_on_off[s][0].x == 1.0 or solar_prod[s][0] == 0.0:
                        self.turn_on(entity_pv_switch)
                    else:
                        self.turn_off(entity_pv_switch)

                # battery
                for b in range(B):
                    #vermogen aan ac kant
                    netto_vermogen = int(1000 * ((ac_to_dc[b][0].x - dc_to_ac[b][0].x) / hour_fraction[0]))
                    minimum_power = self.battery_options[b]["minimum power"]
                    if abs(netto_vermogen) <= 20:
                        netto_vermogen = 0
                        new_state = "Uit"
                        stop_victron = None
                        balance = False
                    elif abs(c_l[0].x - c_t_w_tax[0].x - c_t_no_tax[0].x) <= 0.01:
                        new_state = "Aan"
                        balance = True
                        stop_victron = None
                    elif abs(netto_vermogen) < minimum_power:
                        new_state = "Aan"
                        balance = False
                        new_ts = now_dt.timestamp() + (abs(netto_vermogen) / minimum_power) * 3600
                        stop_victron = datetime.datetime.fromtimestamp(int(new_ts))
                        if netto_vermogen > 0:
                            netto_vermogen = minimum_power
                        else:
                            netto_vermogen = -minimum_power
                    else:
                        new_state = "Aan"
                        balance = False
                        stop_victron = None

                    self.set_value(self.battery_options[b]["entity set power feedin"], netto_vermogen)
                    self.select_option(self.battery_options[b]["entity set operating mode"], new_state)
                    if balance:
                        self.set_state(self.battery_options[b]["entity balance switch"], 'on')
                    else:
                        self.set_state(self.battery_options[b]["entity balance switch"], 'off')
                    print("Netto vermogen uit grid batterij " + str(b) + ": ", netto_vermogen, "W")
                    print("Balanceren:", balance)
                    if stop_victron is None:
                        datetime_str = "2000-01-01 00:00:00"
                    else:
                        print("tot: ", stop_victron)
                        datetime_str = stop_victron.strftime('%Y-%m-%d %H:%M')
                    helper_id = self.battery_options[b]["entity stop victron"]
                    self.call_service("set_datetime", entity_id=helper_id, datetime=datetime_str)
                    for s in range(pv_dc_num[b]):
                        entity_pv_switch = self.battery_options[b]["solar"][s]["entity pv switch"]
                        if pv_dc_on_off[b][s][0].x == 1 or pv_prod_dc[b][s][0] == 0.0:
                            self.turn_on(entity_pv_switch)
                        else:
                            self.turn_off(entity_pv_switch)

                # heating
                if self.heater_present:
                    entity_curve_adjustment = self.heating_options["entity adjust heating curve"]
                    old_adjustment = float(self.get_state(entity_curve_adjustment).state)
                    # adjustment factor (K/%) bijv 0.4 K/10% = 0.04
                    adjustment_factor = self.heating_options["adjustment factor"]
                    adjustment = utils.calc_adjustment_heatcurve(pl[0], p_avg, adjustment_factor, old_adjustment)
                    print("Aanpassing stooklijn: ", adjustment)
                    self.set_value(entity_curve_adjustment, adjustment)

            self.db_da.disconnect()

            # graphs
            accu_in_n = []
            accu_out_p = []
            c_t_n = []
            base_n = []
            boiler_n = []
            heatpump_n = []
            ev_n = []
            c_l_p = []
            soc_p = []
            pv_p = []
            pv_ac_p = []
            max_y = 0
            for u in range(U):
                c_t_n.append(-c_t_total[u].x)
                c_l_p.append(c_l[u].x)
                base_n.append(-b_l[u])
                boiler_n.append(- c_b[u].x)
                heatpump_n.append(-c_hp[u].x)
                ev_n.append(-c_ev_sum[u])
                pv_p.append(solar_hour_sum[u])
                pv_ac_p.append (pv_ac_hour_sum[u])
                accu_in_sum = 0
                accu_out_sum = 0
                for b in range(B):
                    accu_in_sum += ac_to_dc[b][u].x
                    accu_out_sum += dc_to_ac[b][u].x
                accu_in_n.append(-accu_in_sum)
                accu_out_p.append(accu_out_sum)
                max_y = max(max_y, (c_l_p[u] + pv_p[u] + pv_ac_p[u]), abs (c_t_total[u].x) + b_l[u] + c_b[u].x + c_hp[u].x + c_ev_sum[u] + accu_in_sum)
                for b in range(B):
                    if u == 0:
                        soc_p.append([])
                    soc_p[b].append(soc[b][u].x)

            #grafiek 1
            import numpy as np
            from da_graph import GraphBuilder
            gr1_df = pd.DataFrame()
            gr1_df["index"] = np.arange(U)
            gr1_df["uur"] = uur
            gr1_df["verbruik"] = c_l_p
            gr1_df["productie"] = c_t_n
            gr1_df["baseload"] = base_n
            gr1_df["boiler"] = boiler_n
            gr1_df["heatpump"] = heatpump_n
            gr1_df["ev"] = ev_n
            gr1_df["pv_ac"] = pv_p
            gr1_df["pv_dc"] = pv_ac_p
            gr1_df["accu_in"] = accu_in_n
            gr1_df["accu_out"] = accu_out_p
            gr1_options = {
                "title" : "Prognose berekend op: " + now_dt.strftime('%Y-%m-%d %H:%M'),
                "haxis" : {
                    "values": "uur",
                    "title": "uren van de dag"
                },
                "vaxis" :[{
                    "title" : "kWh"
                    }
                ],
                "series":[ {"column" : "verbruik",
                    "type": "stacked",
                    "color": '#00bfff'
                    },
                    {"column": "pv_ac",
                     "title": "PV-AC",
                     "type": "stacked",
                     "color": 'green'
                     },
                    {"column": "accu_out",
                     "title": "Accu out",
                     "type": "stacked",
                     "color": 'red'
                    },
                   {"column": "baseload",
                    "title": "Overig verbr.",
                    "type": "stacked",
                    "color": "#f1a603"
                    },
                   {"column": "boiler",
                    "type": "stacked",
                    "color": '#e39ff6'
                    },
                   {"column": "heatpump",
                    "title": "WP",
                    "type": "stacked",
                    "color": '#a32cc4'
                    },
                   {"column": "ev",
                    "title": "EV",
                    "type": "stacked",
                    "color": '#fefbbd'
                    },
                   {"column": "productie",
                    "title": "Teruglev.",
                    "type": "stacked",
                    "color": '#0080ff'
                    },
                   {"column": "accu_in",
                    "title": "Accu in",
                    "type": "stacked",
                    "color": '#ff8000'
                    },
                  ]
            }
            backend = self.config.get(["graphical backend"])
            gb = GraphBuilder(backend)
            gb.build(gr1_df, gr1_options)


            import matplotlib
            import matplotlib.pyplot as plt
            import matplotlib.ticker as ticker
            fig, axis = plt.subplots(figsize=(8, 9), nrows=3)  # , sharex=True)
            ind = np.arange(U)
            axis[0].bar(ind, np.array(org_l), label='Levering', color='#00bfff')
            if sum(pv_p) > 0:
                axis[0].bar(ind, np.array(pv_p), bottom=np.array(org_l), label='PV AC', color='green')
            if sum(pv_ac_p) > 0:
                axis[0].bar(ind, np.array(pv_ac_p), bottom=np.array(org_l) + np.array(pv_p), label='PV DC', color='lime')
            axis[0].bar(ind, np.array(base_n), label="Overig verbr.", color='#f1a603')
            if self.boiler_present:
                axis[0].bar(ind, np.array(boiler_n), bottom=np.array(base_n), label="Boiler", color='#e39ff6')
            if self.heater_present:
                axis[0].bar(ind, np.array(heatpump_n), bottom=np.array(base_n), label="WP", color='#a32cc4')
            axis[0].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n), label="EV laden", \
                        color='#fefbbd')
            axis[0].bar(ind, np.array(org_t), bottom = np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n), \
                        label="Teruglev.", color='#0080ff')
            axis[0].legend(loc='best', bbox_to_anchor=(1.05, 1.00))
            axis[0].set_ylabel('kWh')
            ylim = math.ceil(max_y)
            #math.ceil(max(max(accu_out_p) + max(c_l_p) + max(pv_p), -min(min(base_n), min(boiler_n), min(heatpump_n), min(ev_n), min(c_t_n), min(accu_in_n) )))
            axis[0].set_ylim([-ylim, ylim])
            axis[0].set_xticks(ind, labels=uur)
            axis[0].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[0].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[0].set_title("Berekend op: " + now_dt.strftime('%d-%m-%Y %H:%M') + "\nNiet geoptimaliseerd")

            axis[1].bar(ind, np.array(c_l_p), label='Levering', color='#00bfff')
            axis[1].bar(ind, np.array(pv_p), bottom=np.array(c_l_p), label='PV AC', color='green')
            axis[1].bar(ind, np.array(accu_out_p), bottom=np.array(c_l_p) + np.array(pv_p), label='Accu uit', \
                        color = 'red')

            # axis[1].bar(ind, np.array(cons_n), label="Verbruik", color='yellow')
            axis[1].bar(ind, np.array(base_n), label="Overig verbr.", color='#f1a603')
            if self.boiler_present:
                axis[1].bar(ind, np.array(boiler_n), bottom=np.array(base_n), label="Boiler", color='#e39ff6')
            if self.heater_present:
                axis[1].bar(ind, np.array(heatpump_n), bottom=np.array(base_n), label="WP", color='#a32cc4')
            axis[1].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n), label="EV laden", \
                        color='#fefbbd')
            axis[1].bar(ind, np.array(c_t_n), bottom = np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n), \
                        label = "Teruglev.", color = '#0080ff')
            axis[1].bar(ind, np.array(accu_in_n),
                        bottom = np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n) + np.array(c_t_n), \
                        label='Accu in', color='#ff8000')
            axis[1].legend(loc='best', bbox_to_anchor=(1.05, 1.00))
            axis[1].set_ylabel('kWh')
            axis[1].set_ylim([-ylim, ylim])
            axis[1].set_xticks(ind, labels=uur)
            axis[1].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[1].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[1].set_title("Day Ahead geoptimaliseerd: " + strategie + ", winst € {:<0.2f}".format(old_cost_da - cost.x))

            ln1 = []
            line_styles = ["solid", "dashed", "dotted"]
            for b in range(B):
                ln1.append(axis[2].plot(ind, soc_p[b], label='SoC ' + self.battery_options[b]["name"], \
                           linestyle=line_styles[b], color='red'))
            axis[2].set_xticks(ind, labels=uur)
            axis[2].set_ylabel('% SoC')
            axis[2].set_xlabel("uren van de dag")
            axis[2].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[2].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[2].set_ylim([0, 100])
            axis[2].set_title("Verloop SoC en tarieven")

            axis22 = axis[2].twinx()
            ln2 = axis22.plot(ind, np.array(pl), label='Tarief\nlevering', color='#00bfff')
            ln3 = axis22.plot(ind, np.array(pt_notax), label="Tarief terug\nno tax", color='#0080ff')
            ln4 = axis22.plot(ind, np.array(pl_avg), label="Tarief lev.\ngemid.", linestyle="dashed", color='#00bfff')
            axis22.set_ylabel("euro/kWh")
            axis22.yaxis.set_major_formatter(ticker.FormatStrFormatter('% 1.2f'))
            bottom, top = axis22.get_ylim()
            if bottom > 0:
                axis22.set_ylim([0, top])
            lns = ln1[0]
            for b in range(B)[1:]:
                lns += ln1[b]
            lns += ln2 + ln3 + ln4
            labels = [l.get_label() for l in lns]
            axis22.legend(lns, labels, loc='best', bbox_to_anchor=(1.40, 1.00))
            plt.subplots_adjust(right=0.75)
            fig.tight_layout()
            plt.savefig("../data/images/optimum" + datetime.datetime.now().strftime("%H%M") + ".png")
            if show_graph:
                plt.show()
            plt.close()

    def clean_data(self):
        """
        takes care for cleaning folders data/log and data/images
        """
        def clean_folder(folder:str, pattern: str):
            current_time = time.time()
            day = 24 * 60 * 60
            print(f"Start removing files in {folder} with pattern {pattern}")
            current_dir = os.getcwd()
            os.chdir(os.path.join(os.getcwd(), folder))
            list_files = os.listdir()
            for f in list_files:
                if fnmatch.fnmatch(f, pattern):
                    creation_time = os.path.getctime(f)
                    if (current_time - creation_time) >= self.history_options["save days"] * day:
                        os.remove(f)
                        print("{} removed".format(f))
            os.chdir(current_dir)
        clean_folder("../data/log", "*.log")
        clean_folder("../data/images", "*.png")

    def run_task(self, task):
        old_stdout = sys.stdout
        log_file = open("../data/log/" + task + datetime.datetime.now().strftime("%H%M") + ".log", "w")
        sys.stdout = log_file
        print("Day Ahead Optimalistatie gestart:", datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'), ': ', task)
        print("Locatie: ", str(self.config.get(["latitude"])) + ':' + str(self.config.get(["longitude"])))
        getattr(self, task)()
        self.set_last_activity()
        sys.stdout = old_stdout
        log_file.close()

    '''
    def on_keyboard_press(self, key):
        char = sys.stdin()
            # Print the input value

        print("The input value is:%s" % char)

        # if key.char == 'a': # here you can choose the letter you want to get detected
        #ch = sys.stdin.read(1)
        #pchar = input()
        print("You pressed: ", char) # , " ", ch)
        match char:
            case "m":
                print("get meteo data")
                self.get_meteo_data()
            case "p":
                print("get day ahead prices")
                self.get_entsoe_data()
            case "o":
                print("optimize")
                self.calc_optimum()
            case "e":
                print("exit program")
                quit()
    '''

    def subscribe(self) -> None:
        """
        set a subscription for an event in ha, defined with subscribe_triger
        :param ws: websocket
        """
        trigger_entity = self.config.get(["trigger entity"])
        subscribe_trigger = {
            "id": 1,
            "type": "subscribe_trigger",
            "trigger": {
                "platform": "state",
                "entity_id": trigger_entity,
            }
        }
        send_str = json.dumps(subscribe_trigger)
        self.w_socket.send(send_str)
        mess = self.w_socket.recv()
        print(mess)


    def unsubscribe(self) -> None:
        """
        remove subscription
        :param ws: websocket
        """
        unsubscribe_mess = {
            "id": 3,
            "type": "unsubscribe_events",
            "subscription": 1
        }
        send_str = json.dumps(unsubscribe_mess)
        self.w_socket.send(send_str)
        mess = self.w_socket.recv()
        print(mess)


    def recieve_events(self, th_event: threading.Event) -> None:
        print("Wacht op binnenkomende messages van Home Assistant")
        while True:
            try:
                while True:
                    message = self.w_socket.recv()
                    if message != '':
                        print("Ontvangen message:" + message)
                        th_event.set()
                time.sleep(1)
            except websocket.WebSocketConnectionClosedException:
                print("Websocket verbinding verbroken")
                while not self.w_socket.connected:
                    time.sleep(60) #een minuut wachten
                    try:
                        self.w_socket = self.start_websocket()
                        print("Websocket verbinding hersteld")
                        self.subscribe()
                        th_event.clear()
                    except:
                        pass

    def start_websocket(self) -> websocket:
        ws = websocket.WebSocket()
        ws.connect("ws://" + self.ip_adress + ":" + str(self.ip_port) + "/api/websocket")
        print("Websocket connect: ", ws.recv())
        ws.send('{"type": "auth", "access_token": "' + self.hasstoken + '"}')
        print("Websocket auth: ", ws.recv())
        return ws

    def scheduler(self):
        self.w_socket = self.start_websocket()
        th_event = threading.Event()
        recieve_thread = threading.Thread(name="recieve thread", target=self.recieve_events, args=(th_event,))
        self.subscribe()
        th_event.clear()
        recieve_thread.start()
        if self.notification_entity != None:
            if self.notification_options["opstarten"].lower() == "true":
                self.set_value(self.notification_entity, "DAO scheduler gestart " + datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))

        while True:
            if th_event.is_set():
                th_event.clear()
                print("Event ontvangen")
                print("Start optimalisatieberekening")
                self.run_task("calc_optimum")
            t = datetime.datetime.now()
            next_min = t - datetime.timedelta(minutes=-1, seconds=t.second, microseconds=t.microsecond)
            #            if not (self.stop_victron == None):
            #                if (next_min.hour == self.stop_victron.hour) and (next_min.minute == self.stop_victron.minute):
            #                    self.set_value(self.battery_options["entity set power feedin"], 0)
            #                    self.select_option(self.battery_options["entity set operating mode"], 'Uit')
            time.sleep((next_min - t).total_seconds())  # wacht tot hele minuut 0% cpu
            hour = next_min.hour
            minute = next_min.minute
            key1 = str(hour).zfill(2) + str(minute).zfill(2)
            key2 = "xx" + str(minute).zfill(2)  # ieder uur in dezelfde minuut voorbeeld xx15
            key3 = str(hour).zfill(2) + "xx"  # iedere minuut in een uur voorbeeld 02xx
            task = None
            if key1 in self.tasks:
                task = self.tasks[key1]
            elif key2 in self.tasks:
                task = self.tasks[key2]
            elif key3 in self.tasks:
                task = self.tasks[key3]
            if task is not None:
                try:
                    self.run_task(task)
                except KeyboardInterrupt:
                    sys.exit()
                    pass
                except Exception as e:
                    print(e)
                    continue


def main():
    """
    main function
    """
    day_ah = DayAheadOpt("../data/options.json")
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        for arg in args:
            if arg.lower() == "debug":
                day_ah.debug = not day_ah.debug
                print("Debug =", day_ah.debug)
                continue
            if arg.lower() == "calc":
                day_ah.calc_optimum(show_graph=True)
                day_ah.set_last_activity()
                continue
            if arg.lower() == "meteo":
                day_ah.get_meteo_data(True)
                day_ah.set_last_activity()
                continue
            if arg.lower() == "prices":
                day_ah.get_day_ahead_prices()
                day_ah.set_last_activity()
                continue
            if arg.lower() == "tibber":
                day_ah.get_tibber_data()
                day_ah.set_last_activity()
                continue
            if arg.lower() == "scheduler":
                day_ah.scheduler()
                continue
            if arg.lower() == "clean":  
                day_ah.clean_data()
                day_ah.set_last_activity()
                continue
    else:
        day_ah.scheduler()


if __name__ == "__main__":
    main()
