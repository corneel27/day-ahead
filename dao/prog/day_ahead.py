"""
Het programma Day Ahead Optimalisatie kun je je energieverbruik en energiekosten optimaliseren als je gebruik maakt
van dynamische prijzen.
Zie verder: DOCS.md
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
import utils
from utils import get_value_from_dict, get_tibber_data, is_laagtarief
from _version import __version__
from da_config import Config
from da_meteo import Meteo
from da_prices import DA_Prices
from db_manager import DBmanagerObj


class DayAheadOpt(hass.Hass):

    def __init__(self, file_name=None):
        path = os.getcwd()
        new_path = "/".join(list(path.split('/')[0:-2]))
        sys.path.append(new_path)
        # print("python pad: ", sys.path)
        utils.make_data_path()
        self.debug = False
        self.config = Config(file_name)
        self.protocol_api = self.config.get(['homeassistant', 'protocol api'], default="http")
        self.ip_address = self.config.get(['homeassistant', 'ip adress'], default="supervisor")
        self.ip_port = self.config.get(['homeassistant', 'ip port'], default=None)
        if self.ip_port is None:
            self.hassurl = self.protocol_api + "://" + self.ip_address + "/core/"
        else:
            self.hassurl = self.protocol_api + "://" + self.ip_address + ":" + str(self.ip_port) + "/"
        self.hasstoken = self.config.get(['homeassistant', 'token'], default=os.environ.get("SUPERVISOR_TOKEN"))
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
        db_da_server = self.config.get(['database da', "server"], None, "core-mariadb")
        db_da_port = int(self.config.get(['database da', "port"], None, 3306))
        db_da_name = self.config.get(['database da', "database"], None, "day_ahead")
        db_da_user = self.config.get(['database da', "username"], None, "day_ahead")
        db_da_password = self.config.get(['database da', "password"])
        self.db_da = DBmanagerObj(db_name=db_da_name, db_server=db_da_server, db_port=db_da_port,
                                  db_user=db_da_user, db_password=db_da_password)
        db_ha_server = self.config.get(['database ha', "server"], None, "core-mariadb")
        db_ha_port = int(self.config.get(['database ha', "port"], None, 3306))
        db_ha_name = self.config.get(['database ha', "database"], None, "homeassistant")
        db_ha_user = self.config.get(['database ha', "username"], None, "day_ahead")
        db_ha_password = self.config.get(['database ha', "password"])
        self.db_ha = DBmanagerObj(db_name=db_ha_name, db_server=db_ha_server, db_port=db_ha_port,
                                  db_user=db_ha_user, db_password=db_ha_password)
        self.meteo = Meteo(self.config, self.db_da)
        self.solar = self.config.get(["solar"])
        self.prices = DA_Prices(self.config, self.db_da)
        self.strategy = self.config.get(["strategy"])
        self.tibber_options = self.config.get(["tibber"], None, None)
        self.notification_entity = self.config.get(["notifications", "notification entity"], None, None)
        self.notification_opstarten = self.config.get(["notifications", "opstarten"], None, False)
        self.notification_berekening = self.config.get(["notifications", "berekening"], None, False)
        self.last_activity_entity = self.config.get(["notifications", "last activity entity"], None, None)
        self.set_last_activity()
        self.graphics_options = self.config.get(["graphics"])
        self.history_options = self.config.get(["history"])
        self.boiler_options = self.config.get(["boiler"])
        self.battery_options = self.config.get(["battery"])
        self.prices_options = self.config.get(["prices"])
        self.ev_options = self.config.get(["electric vehicle"])
        self.heating_options = self.config.get(["heating"])
        self.tasks = self.config.get(["scheduler"])
        self.use_calc_baseload = (self.config.get(["use_calc_baseload"], None, "false").lower() == "true")
        self.heater_present = False
        self.boiler_present = False
        self.grid_max_power = self.config.get(["grid", "max_power"], None, 17)

    def set_last_activity(self):
        if self.last_activity_entity is not None:
            self.call_service("set_datetime", entity_id=self.last_activity_entity,
                              datetime=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def day_ahead_berekening_uitvoeren(self):
        self.calc_optimum()
        return

    def get_meteo_data(self, show_graph: bool = False):
        self.db_da.connect()
        self.meteo.get_meteo_data(show_graph)
        self.db_da.disconnect()

    @staticmethod
    def get_tibber_data():
        """
        """
        get_tibber_data()

    @staticmethod
    def consolidate_data():
        from da_report import Report
        report = Report()
        report.db_da.connect()
        report.db_ha.connect()
        report.consolidate_data()

    def get_day_ahead_prices(self):
        self.db_da.connect()
        self.prices.get_prices(self.config.get(["source day ahead"], self.prices_options, "nordpool"))
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
            "AND t1.`time` >= UNIX_TIMESTAMP('" +
            start.strftime('%Y-%m-%d') + "') "
            "AND t1.`time` < UNIX_TIMESTAMP('" +
            until.strftime('%Y-%m-%d') + "');"
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

    def save_df(self, tablename: str, tijd: list, df: pd.DataFrame):
        """
        Slaat de data in het dataframe op in de tabel "table"
        :param tablename: de naam van de tabel waarin de data worden opgeslagen
        :param tijd: de datum tijd van de rijen in het dataframe
        :param df: het dataframe met de code van de variabelen in de kolomheader
        :return: None
        """
        df_db = pd.DataFrame(columns=['time', 'code', 'value'])
        df = df.reset_index()
        columns = df.columns.values.tolist()[1:]
        for index in range(len(tijd)):
            utc = tijd[index].timestamp()
            for c in columns:
                db_row = [str(utc), c, float(df.loc[index, c])]
                # print(db_row)
                df_db.loc[df_db.shape[0]] = db_row
        # print(df_db)
        self.db_da.savedata(df_db, debug=False, tablename=tablename)
        return

    @staticmethod
    def get_calculated_baseload(weekday: int) -> list:
        """
        Haalt de berekende baseload op voor de weekdag.
        :param weekday: : 0 = maandag, 6 zondag
        :return: een lijst van eerder berekende baseload van 24uurvoor de betreffende dag
        """
        in_file = "../data/baseload/baseload_" + str(weekday) + ".json"
        with open(in_file, 'r') as f:
            result = json.load(f)
        return result

    def calc_optimum(self):

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
        modulo = now_dt % 3600
        if modulo > 3550:
            now_dt = now_dt + 3600 - modulo
        offset = 0  # offset in uren
        now_h = int(3600 * (math.floor(now_dt / 3600)) + offset * 3600)
        fraction_first_hour = 1 - (now_dt - now_h) / 3600
        prog_data = self.db_da.getPrognoseData(start=now_h, end=None)
        # start = datetime.datetime.timestamp(datetime.datetime.strptime("2022-05-27", "%Y-%m-%d"))
        # end = datetime.datetime.timestamp(datetime.datetime.strptime("2022-05-29", "%Y-%m-%d"))
        # prog_data = db_da.getPrognoseData(start, end)
        u = len(prog_data)
        if u <= 2:
            print("Er ontbreken voor een aantal uur gegevens (meteo en/of dynamische prijzen)\n",
                  "er kan niet worden gerekend")
            if self.notification_entity is not None:
                self.set_value(self.notification_entity,
                               "Er ontbreken voor een aantal uur gegevens; er kan niet worden gerekend")
            return
        if u <= 8:
            print("Er ontbreken voor een aantal uur gegevens (meteo en/of dynamische prijzen)\n",
                  "controleer of alle gegevens zijn opgehaald")
            if self.notification_entity is not None:
                self.set_value(self.notification_entity, "Er ontbreken voor een aantal uur gegevens")

        if self.notification_entity is not None and self.notification_berekening:
            self.set_value(self.notification_entity, "DAO calc gestart " +
                           datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))

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
        # opslag kosten leverancier
        ol_l_def = self.prices_options["cost supplier delivery"]
        # ol_l_def ["2022-01-01] = 0.002
        # ol_l_def ["2023-03-01] = 0.018
        # eb+ode teruglevering
        taxes_t_def = self.prices_options["energy taxes redelivery"]
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
            price_t_notax = row.da_price
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
        if self.use_calc_baseload:
            print(f"\nZelf berekende baseloads:")
            weekday = datetime.datetime.weekday(datetime.datetime.now())
            base_cons = self.get_calculated_baseload(weekday)
            if U >= 24:
                # volgende dag ophalen
                weekday += 1
                weekday = weekday % 7
                base_cons = base_cons + self.get_calculated_baseload(weekday)
        else:
            print(f"\nBaseload uit instellingen:")
            base_cons = self.config.get(["baseload"])
            if U >= 24:
                base_cons = base_cons + base_cons

        pprint(base_cons)  # basislast van 0 tot 23/47 uur

        # 0.015 kWh/J/cm² productie van mijn panelen per J/cm²
        pv_yield = []
        solar_prod = []
        solar_num = len(self.solar)
        for s in range(solar_num):
            pv_yield.append(float(self.config.get(["yield"], self.solar[s])))
            solar_prod.append([])

        time_first_hour = datetime.datetime.fromtimestamp(prog_data["time"].iloc[0])
        first_hour = int(time_first_hour.hour)
        b_l = base_cons[first_hour:]

        uur = []  # hulparray met uren
        tijd = []
        ts = []
        global_rad = []  # globale straling per uur
        pv_org = []  # opwekking zonnepanelen
        p_grl = []  # prijs levering
        p_grt = []  # prijs teruglevering
        hour_fraction = []
        first_hour = True

        prog_data = prog_data.reset_index()  # make sure indexes pair with number of rows
        for row in prog_data.itertuples():
            dtime = datetime.datetime.fromtimestamp(row.time)
            hour = int(dtime.hour)
            uur.append(hour)
            tijd.append(dtime)
            global_rad.append(row.glob_rad)
            pv_total = 0
            if first_hour:
                ts.append(now_dt)
                hour_fraction.append(fraction_first_hour)
                # pv.append(pv_total * fraction_first_hour)
            else:
                ts.append(row.time)
                hour_fraction.append(1)
                # pv.append(pv_total)
            for s in range(solar_num):
                prod = self.meteo.calc_solar_rad(
                    self.solar[s], row.time, row.glob_rad) * pv_yield[s] * hour_fraction[-1]
                solar_prod[s].append(prod)
                pv_total += prod
            pv_org.append(pv_total)
            dag_str = dtime.strftime("%Y-%m-%d")
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            taxes_t = get_value_from_dict(dag_str, taxes_t_def)
            btw = get_value_from_dict(dag_str, btw_def)
            if is_laagtarief(datetime.datetime(dtime.year, dtime.month, dtime.day, hour),
                             self.config.get(["switch to low"], self.prices_options, 23)):
                p_grl.append((gc_p_low + taxes_l) * (1 + btw / 100))
                p_grt.append((gc_p_low + taxes_t) * (1 + btw / 100))
            else:
                p_grl.append((gc_p_high + taxes_l) * (1 + btw / 100))
                p_grt.append((gc_p_high + taxes_t) * (1 + btw / 100))
            first_hour = False

        # volledig salderen?
        salderen = self.prices_options['tax refund'] == "True"

        last_invoice = datetime.datetime.strptime(
            self.prices_options['last invoice'], "%Y-%m-%d")
        cons_data_history = self.get_consumption(
            last_invoice, datetime.datetime.today())
        if not salderen:
            salderen = cons_data_history["production"] < cons_data_history["consumption"]

        if salderen:
            print("All taxes refund (alles wordt gesaldeerd)")
            consumption_today = 0
            production_today = 0
        else:
            consumption_today = float(self.get_state(
                "sensor.daily_grid_consumption").state)
            production_today = float(self.get_state(
                "sensor.daily_grid_production").state)
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
        pv_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=solar_prod[s][u] * 1.1)
                  for u in range(U)] for s in range(solar_num)]
        pv_ac_on_off = [[model.add_var(var_type=BINARY) for _ in range(U)] for _ in range(solar_num)]
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
        # pv_dc = []  # pv bruto productie per batterij per uur
        # pv_dc_hour_sum = []
        # pv_from_dc_hour_sum = []  # de som van pv_dc productie geleverd aan ac per uur
        # eff_ac_to_dc = []
        # eff_dc_to_ac = []
        eff_dc_to_bat = []
        eff_bat_to_dc = []
        # max_ac_to_dc = []
        # max_dc_to_ac = []

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
            # noinspection PyTypeChecker
            max_charge_power.append(int(self.battery_options[b]["charge stages"][-1]["power"])/1000)
            # CS is aantal charge stages
            CS.append(len(self.battery_options[b]["charge stages"]))
            max_discharge_power.append(self.battery_options[b]["discharge stages"][-1]["power"]/1000)
            # DS is aantal discharge stages
            DS.append(len(self.battery_options[b]["discharge stages"]))
            sum_eff = 0
            for ds in range(DS[b])[1:]:
                sum_eff += self.battery_options[b]["discharge stages"][ds]["efficiency"]
            avg_eff_dc_to_ac.append(sum_eff/(DS[b]-1))

            # 2 * 50 * 280/1000 #=28 kWh
            ac = float(self.battery_options[b]["capacity"])
            one_soc.append(ac / 100)  # 1% van 28 kWh = 0,28 kWh
            kwh_cycle_cost.append(self.battery_options[b]["cycle cost"])
            # kwh_cycle_cost = (cycle_cost/( 2 * ac) ) / ((self.battery_options["upper limit"] -
            # self.battery_options["lower limit"]) / 100)
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
            opt_low_level.append(
                float(self.battery_options[b]["optimal lower level"]))

            # pv dc mppt
            pv_dc_num.append(len(self.battery_options[b]["solar"]))
            # pv_dc_bat = []
            for s in range(pv_dc_num[b]):
                pv_prod_dc[b].append([])
                pv_prod_ac[b].append([])
                pv_yield = self.battery_options[b]["solar"][s]["yield"]
                for u in range(U):
                    # pv_prod productie van batterij b van solar s in uur u
                    prod_dc = self.meteo.calc_solar_rad(self.battery_options[b]["solar"][s],
                                                        int(tijd[u].timestamp()), global_rad[u]) * pv_yield
                    efficiency = 1
                    for ds in range(DS[b]):
                        if self.battery_options[b]["discharge stages"][ds]["power"]/1000 > prod_dc:
                            efficiency = self.battery_options[b]["discharge stages"][ds]["efficiency"]
                            break
                    prod_ac = prod_dc * efficiency
                    pv_prod_dc[b][s].append(prod_dc)
                    pv_prod_ac[b][s].append(prod_ac)

        # energie per uur, vanuit dc gezien
        # ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * \
        #                max_ac_to_dc[b]) for u in range(U)] for b in range(B) ]
        # hernoemd naar dc_from_ac
        # totaal elektra van ac naar de busbar, ieder uur

        # alle variabelen definieren alles in W tenzij aangegeven
        # mppt aan/uit evt bij netto prijzen onder nul
        pv_dc_on_off = [[[model.add_var(var_type=BINARY) for _ in range(U)]
                        for _ in range(pv_dc_num[b])] for b in range(B)]
        pv_prod_dc_sum = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b])
                          for _ in range(U)] for b in range(B)]

        # ac_to_dc met aan uit #############################################################
        '''
        #ac_to_dc: wat er gaat er vanuit ac naar de omvormer
        ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b])
                     for u in range(U)] for b in range(B)]
        ac_to_dc_on = [[model.add_var(var_type=BINARY) for u in range(U)] for b in range(B)]

        # elektra per vermogensklasse van ac naar de busbar, ieder uur
        ac_to_dc_st = [[[model.add_var(var_type=CONTINUOUS, lb=0,
                        ub=self.battery_options[b]["charge stages"][cs]["power"]/1000)
                        for u in range(U)] for cs in range(CS[b])] for b in range(B)]
        # vermogens klasse aan/uit
        ac_to_dc_st_on = [[[model.add_var(var_type=BINARY)
            for u in range(U)] for cs in range(CS[b])] for b in range(B)]
        '''
        # met sos ###################################################################
        ac_to_dc_samples = [[self.battery_options[b]["charge stages"][cs]["power"]/1000
                            for cs in range(CS[b])] for b in range(B)]
        dc_from_ac_samples = [[(self.battery_options[b]["charge stages"][cs]["efficiency"] *
                               self.battery_options[b]["charge stages"][cs]["power"] / 1000)
                               for cs in range(CS[b])] for b in range(B)]
        ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b])
                     for _ in range(U)] for b in range(B)]
        ac_to_dc_on = [[model.add_var(var_type=BINARY) for _ in range(U)] for _ in range(B)]
        ac_to_dc_w = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=1)
                        for _ in range(CS[b])] for _ in range(U)] for b in range(B)]
        # tot hier met sos
        # '''
        ac_from_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_discharge_power[b])
                       for _ in range(U)] for b in range(B)]
        ac_from_dc_on = [[model.add_var(var_type=BINARY) for _ in range(U)] for _ in range(B)]

        # elektra per vermogensklasse van busbar naar ac, ieder uur
        ac_from_dc_st = [[[model.add_var(var_type=CONTINUOUS, lb=0,
                           ub=self.battery_options[b]["discharge stages"][ds]["power"]/1000)
                           for _ in range(U)] for ds in range(DS[b])] for b in range(B)]
        ac_from_dc_st_on = [[[model.add_var(var_type=BINARY)
                              for _ in range(U)] for _ in range(DS[b])] for b in range(B)]

        # energiebalans dc
        dc_from_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_charge_power[b])
                       for _ in range(U)] for b in range(B)]
        dc_to_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_discharge_power[b])
                     for _ in range(U)] for b in range(B)]
        dc_from_bat = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=2 * max_discharge_power[b])
                        for _ in range(U)] for b in range(B)]
        dc_to_bat = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=2 * max_charge_power[b])
                      for _ in range(U)] for b in range(B)]

        # SoC
        soc = [[model.add_var(var_type=CONTINUOUS, lb=min(start_soc[b], float(self.battery_options[b]["lower limit"])),
                ub=max(start_soc[b], float(self.battery_options[b]["upper limit"])))
                for _ in range(U + 1)] for b in range(B)]
        soc_low = [[model.add_var(var_type=CONTINUOUS,
                    lb=min(start_soc[b], float(self.battery_options[b]["lower limit"])),
                    ub=opt_low_level[b]) for _ in range(U + 1)] for b in range(B)]
        soc_mid = [[model.add_var(var_type=CONTINUOUS, lb=0,
                    ub=-opt_low_level[b] + max(start_soc[b], float(self.battery_options[b]["upper limit"])))
                    for _ in range(U + 1)] for b in range(B)]

        # alle constraints
        for b in range(B):
            for u in range(U):
                # laden, alles uitgedrukt in vermogen kW
                # met aan/uit
                '''
                for cs in range(CS[b]):
                    model += (ac_to_dc_st[b][cs][u] <=
                        self.battery_options[b]["charge stages"][cs]["power"] * ac_to_dc_st_on[b][cs][u]/1000)
                for cs in range(CS[b])[1:]:
                    model += (ac_to_dc_st[b][cs][u] >=
                        self.battery_options[b]["charge stages"][cs - 1]["power"] * ac_to_dc_st_on[b][cs][u]/1000)

                model += ac_to_dc[b][u] == xsum(ac_to_dc_st[b][cs][u] for cs in range(CS[b]))
                model += (xsum(ac_to_dc_st_on[b][cs][u] for cs in range(CS[b]))) <= 1
                model += dc_from_ac[b][u] == xsum(ac_to_dc_st[b][cs][u] * \
                                    self.battery_options[b]["charge stages"][cs]["efficiency"] for cs in range(CS[b]))
                '''
                # met sos
                model += xsum(ac_to_dc_w[b][u][cs] for cs in range(CS[b])) == 1
                model += xsum(ac_to_dc_w[b][u][cs] * ac_to_dc_samples[b][cs]
                              for cs in range(CS[b])) == ac_to_dc[b][u]
                model += xsum(ac_to_dc_w[b][u][cs] * dc_from_ac_samples[b][cs]
                              for cs in range(CS[b])) == dc_from_ac[b][u]
                model.add_sos([(ac_to_dc_w[b][u][cs], ac_to_dc_samples[b][cs])
                               for cs in range(CS[b])], 2)
                # tot hier met sos

                # ontladen
                for ds in range(DS[b]):
                    model += ac_from_dc_st[b][ds][u] <= self.battery_options[b]["discharge stages"][ds]["power"] * \
                        ac_from_dc_st_on[b][ds][u]/1000
                for ds in range(DS[b])[1:]:
                    model += ac_from_dc_st[b][ds][u] >= self.battery_options[b]["discharge stages"][ds - 1]["power"] * \
                        ac_from_dc_st_on[b][ds][u]/1000

                model += ac_from_dc[b][u] == xsum(ac_from_dc_st[b][ds][u] for ds in range(DS[b]))
                model += (xsum(ac_from_dc_st_on[b][ds][u] for ds in range(DS[b]))) <= 1
                model += dc_to_ac[b][u] == xsum(ac_from_dc_st[b][ds][u] / self.battery_options[b]
                                                ["discharge stages"][ds]["efficiency"] for ds in range(DS[b]))

        for b in range(B):
            for u in range(U + 1):
                model += soc[b][u] == soc_low[b][u] + soc_mid[b][u]
            model += soc[b][0] == start_soc[b]

            entity_min_soc_end = self.config.get(["entity min soc end opt"], self.battery_options[b], None)
            if entity_min_soc_end is None:
                min_soc_end_opt = 0
            else:
                min_soc_end_opt = float(self.get_state(entity_min_soc_end).state)

            entity_max_soc_end = self.config.get(["entity max soc end opt"], self.battery_options[b], None)
            if entity_max_soc_end is None:
                max_soc_end_opt = 100
            else:
                max_soc_end_opt = float(self.get_state(entity_max_soc_end).state)

            model += soc[b][U] >= max(opt_low_level[b] / 2, min_soc_end_opt)
            model += soc[b][U] <= max_soc_end_opt
            for u in range(U):
                model += (soc[b][u + 1] == soc[b][u] +
                          (dc_to_bat[b][u] * eff_dc_to_bat[b] * hour_fraction[u] / one_soc[b]) -
                          ((dc_from_bat[b][u] * hour_fraction[u] / eff_bat_to_dc[b]) / one_soc[b]))
                model += pv_prod_dc_sum[b][u] == xsum(pv_prod_dc[b][s][u] * pv_dc_on_off[b][s][u]
                                                      for s in range(pv_dc_num[b]))
                # nakijken!!!
                model += (dc_from_ac[b][u] + dc_from_bat[b][u] + pv_prod_dc_sum[b][u] ==
                          dc_to_ac[b][u] + dc_to_bat[b][u])
                model += dc_from_ac[b][u] <= ac_to_dc_on[b][u] * max_charge_power[b]
                model += ac_from_dc[b][u] <= ac_from_dc_on[b][u] * max_discharge_power[b]
                model += (ac_to_dc_on[b][u] + ac_from_dc_on[b][u]) <= 1

        #####################################
        #             boiler                #
        #####################################
        boiler_on = [model.add_var(var_type=BINARY) for _ in range(U)]
        self.boiler_present = self.config.get(["boiler present"], self.boiler_options,
                                              "true").lower() == "true"
        if not self.boiler_present:
            # default values
            boiler_setpoint = 50
            boiler_hysterese = 10
            spec_heat_boiler = 200 * 4.2 + 100 * 0.5  # kJ/K
            cop_boiler = 3
            boiler_temp = [model.add_var(var_type=CONTINUOUS, lb=20, ub=20) for _ in range(U + 1)]  # end temp boiler
            c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for _ in range(U)]  # consumption boiler
            model += xsum(boiler_on[j] for j in range(U)) == 0
            print("Geen boiler aanwezig")
        else:
            # 50 huidige boilertemperatuur ophalen uit ha
            boiler_act_temp = float(self.get_state(self.boiler_options["entity actual temp."]).state)
            boiler_setpoint = float(self.get_state(self.boiler_options["entity setpoint"]).state)
            boiler_hysterese = float(self.get_state(self.boiler_options["entity hysterese"]).state)
            # 0.4 #K/uur instelbaar
            boiler_cooling = self.boiler_options["cooling rate"]
            # 45 # oC instelbaar daaronder kan worden verwarmd
            boiler_bovengrens = self.boiler_options["heating allowed below"]
            boiler_bovengrens = min(boiler_bovengrens, boiler_setpoint)
            # 41 #C instelbaar daaronder moet worden verwarmd
            boiler_ondergrens = boiler_setpoint - boiler_hysterese
            vol = self.boiler_options["volume"]  # liter
            # spec heat in kJ/K = vol in liter * 4,2 J/liter + 100 kg * 0,5 J/kg
            spec_heat_boiler = vol * 4.2 + 200 * 0.5  # kJ/K
            cop_boiler = self.boiler_options["cop"]
            power = self.boiler_options["elec. power"]  # W

            # tijdstip index waarop boiler kan worden verwarmd
            boiler_start = int(max(0, min(23, int((boiler_act_temp - boiler_bovengrens) / boiler_cooling))))

            # tijdstip index waarop boiler nog aan kan
            # (41-40)/0.4=2.5
            boiler_end = int(min(U - 1, max(0, int((boiler_act_temp - boiler_ondergrens) / boiler_cooling))))
            boiler_temp = [model.add_var(var_type=CONTINUOUS,
                                         lb=min(boiler_act_temp, boiler_setpoint - boiler_hysterese - 10),
                                         ub=boiler_setpoint + 10)
                           for _ in range(U + 1)]  # end temp boiler

            if boiler_start > boiler_end:  # geen boiler opwarming in deze periode
                c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0)
                       for _ in range(U)]  # consumption boiler
                model += xsum(boiler_on[j] for j in range(U)
                              [boiler_start:boiler_end + 1]) == 0
                print("\nBoiler: geen opwarming")
                boiler_end_temp = boiler_act_temp - boiler_cooling * U
                print("Boiler eind temperatuur: ", boiler_end_temp)
                for u in range(U):
                    # opwarming in K = kWh opwarming * 3600 = kJ / spec heat boiler - 3
                    model += boiler_temp[u + 1] == boiler_temp[u] - boiler_cooling
            else:
                print("\nBoiler opwarmen worden ingepland tussen: ", uur[boiler_start], " en ", uur[boiler_end], " uur")
                needed_elec = [0.0 for _ in range(U)]
                needed_time = [0 for _ in range(U)]
                needed_heat = max(0.0, float(spec_heat_boiler * (
                    boiler_setpoint - (boiler_act_temp - 4 - boiler_cooling * (boiler_end - boiler_start))) / 3600))
                for u in range(boiler_start, boiler_end + 1):
                    needed_elec[u] = needed_heat / cop_boiler  # kWh
                    needed_time[u] = needed_elec[u] * 1000 / power  # hour

                c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=needed_elec[u])
                       for u in range(U)]  # cons. boiler
                for u in range(U):
                    model += c_b[u] == boiler_on[u] * needed_elec[u]
                    if u < boiler_start:
                        model += boiler_on[u] == 0
                    elif u > boiler_end:
                        model += boiler_on[u] == 0
                model += xsum(boiler_on[j] for j in range(U)
                              [boiler_start:boiler_end + 1]) == 1
                model += boiler_temp[0] == boiler_act_temp
                for u in range(U):
                    # opwarming in K = kWh opwarming * 3600 = kJ / spec heat boiler - 3
                    model += boiler_temp[u + 1] == boiler_temp[u] - boiler_cooling + c_b[u] * cop_boiler \
                        * 3600 / spec_heat_boiler
        print("\n")

        ################################################
        #             electric vehicles
        ################################################
        EV = len(self.ev_options)
        actual_soc = []
        wished_level = []
        level_margin = []
        ready_u = []
        hours_needed = []
        max_power = []
        energy_needed = []
        ev_plugged_in = []
        ev_position = []
        now_dt = datetime.datetime.now()
        charge_stages = []
        ampere_factor = []
        ECS = []
        for e in range(EV):
            ev_capacity = self.ev_options[e]["capacity"]
            # plugged = self.get_state(self.ev_options["entity plugged in"]).state
            try:
                plugged_in = self.get_state(self.ev_options[e]["entity plugged in"]).state == "on"
            except Exception as ex:
                print(ex)
                plugged_in = False
            ev_plugged_in.append(plugged_in)
            try:
                position = self.get_state(self.ev_options[e]["entity position"]).state
            except Exception as ex:
                print(ex)
                position = "away"
            ev_position.append(position)
            try:
                soc_state = float(self.get_state(self.ev_options[e]["entity actual level"]).state)
            except Exception as ex:
                print(ex)
                soc_state = 100.0
            # if self.debug:
            #     soc_state = min(soc_state, 50.0)
            actual_soc.append(soc_state)
            wished_level.append(float(self.get_state(self.ev_options[e]["charge scheduler"]["entity set level"]).state))
            level_margin.append(self.config.get(["level margin"], self.ev_options[e]["charge scheduler"], 0))
            ready_str = self.get_state(self.ev_options[e]["charge scheduler"]["entity ready datetime"]).state
            if len(ready_str) > 9:
                # dus met datum en tijd
                ready = datetime.datetime.strptime(ready_str, '%Y-%m-%d %H:%M:%S')
            else:
                ready = datetime.datetime.strptime(ready_str, '%H:%M:%S')
                ready = datetime.datetime(now_dt.year, now_dt.month, now_dt.day, ready.hour, ready.minute)
                if (ready.hour == now_dt.hour and ready.minute < now_dt.minute) or (ready.hour < now_dt.hour):
                    ready = ready + datetime.timedelta(days=1)
            hours_available = (ready - now_dt).total_seconds()/3600
            ev_stages = self.ev_options[e]["charge stages"]
            if ev_stages[0]["ampere"] != 0.0:
                ev_stages = [{"ampere": 0.0, "efficiency": 1}] + ev_stages
            charge_stages.append(ev_stages)
            ECS.append(len(charge_stages[e]))
            max_ampere = charge_stages[e][-1]["ampere"]
            try:
                max_ampere = float(max_ampere)
            except ValueError:
                max_ampere = 10
            charge_three_phase = self.config.get(["charge three phase"], self.ev_options[e], "true").lower() == "true"
            if charge_three_phase:
                ampere_f = 3
            else:
                ampere_f = 1
            ampere_factor.append(ampere_f)
            max_power.append(max_ampere * ampere_f * 230 / 1000)  # vermogen in kW
            print("\nInstellingen voor laden van EV: ", self.ev_options[e]["name"], "\n")

            print(" Ampere  Effic. Grid kW Accu kW")
            for cs in range(ECS[e]):
                if not ("efficiency" in charge_stages[e][cs]):
                    charge_stages[e][cs]["efficiency"] = 1.0
                charge_stages[e][cs]["power"] = charge_stages[e][cs]["ampere"] * 230 * ampere_factor[e]/1000
                charge_stages[e][cs]["accu_power"] = charge_stages[e][cs]["power"] * charge_stages[e][cs]["efficiency"]
                print(f"{charge_stages[e][cs]['ampere']:>7.2f}", f"{charge_stages[e][cs]['efficiency']:>7.2f}",
                      f"{charge_stages[e][cs]['power']:>7.2f}", f"{charge_stages[e][cs]['accu_power']:>7.2f}")
            print()
            '''
            #test voor bug
            ev_plugged_in.append(True)
            wished_level.append(float(self.get_state(self.ev_options[e]["charge scheduler"]["entity set level"]).state))
            ev_position.append("home")
            actual_soc.append(40)
            max_power.append(10 * 230 / 1000)
            #tot hier
            '''
            print(f"Capaciteit accu: {ev_capacity} kWh")
            print("Maximaal laadvermogen:", max_power[e], "kW")
            print("Klaar met laden op:", ready.strftime('%d-%m-%Y %H:%M:%S'))
            print("Huidig laadniveau:", actual_soc[e], "%")
            print("Gewenst laadniveau:", wished_level[e], "%")
            print(f"Marge voor het laden: {level_margin[e]} %")
            print("Locatie:", ev_position[e])
            print("Ingeplugged:", ev_plugged_in[e])
            e_needed = ev_capacity * (wished_level[e] - actual_soc[e]) / 100
            e_needed = min(e_needed, max_power[e] * hours_available * charge_stages[e][-1]["efficiency"])
            energy_needed.append(e_needed)  # in kWh
            print(f"Benodigde energie: {energy_needed[e]} kWh")
            # uitgedrukt in aantal uren; bijvoorbeeld 1,5
            time_needed = energy_needed[e] / (max_power[e] * charge_stages[e][-1]["efficiency"])
            print(f"Tijd nodig om te laden: {time_needed} uur")
            old_switch_state = self.get_state(self.ev_options[e]["charge switch"]).state
            old_ampere_state = self.get_state(self.ev_options[e]["entity set charging ampere"]).state
            # afgerond naar boven in hele uren
            hours_needed.append(math.ceil(time_needed))
            print(f"Afgerond naar hele uren: {hours_needed[e]}")
            print(f"Stand laden schakelaar: {old_switch_state}")
            print(f"Stand aantal ampere laden: {old_ampere_state} A")
            ready_index = U
            reden = ""
            if (wished_level[e] - level_margin[e]) <= actual_soc[e]:
                reden = (f" werkelijk niveau ({actual_soc[e]:.1f}%) hoger is of gelijk aan gewenst niveau "
                         f"({wished_level[e]:.1f}% minus de marge {level_margin[e]}%),")
            if not (ev_position[e] == "home"):
                reden = reden + " auto is niet huis,"
            if not ev_plugged_in[e]:
                reden = reden + " auto is niet ingeplugd,"
            if not (tijd[0] < ready):
                reden = reden + f" opgegeven tijdstip ({str(ready)}) is verouderd,"
            if tijd[U-1] < ready:
                reden = reden + f" opgegeven tijdstip ({str(ready)}) ligt voorbij de planningshorizon ({tijd[U - 1]}),"
            if (ev_plugged_in[e] and (ev_position[e] == "home") and
                    (wished_level[e] - level_margin[e] > actual_soc[e]) and (tijd[0] < ready)):
                for u in range(U):
                    if (tijd[u] + datetime.timedelta(hours=1)) >= ready:
                        ready_index = u
                        break
            if ready_index == U:
                if len(reden) > 0:
                    reden = reden[:-1] + "."
                print(f"Opgeladen wordt niet ingepland, omdat{reden}\n")
            else:
                print("Opladen wordt ingepland.\n")
            ready_u.append(ready_index)

        # charger_on = [[model.add_var(var_type=BINARY) for u in range(U)] for e in range(EV)]
        # charger_ampere = [[model.add_var(var_type=CONTINUOUS, lb=0, ub= charge_stages[e][-1]["ampere"])
        #                     for cs in range(ECS[e])] for e in range(EV)]
        charger_power = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_power[e])
                           for _ in range(U)] for _ in range(ECS[e])] for e in range(EV)]
        charger_factor = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=1) for _ in range(U)]
                           for _ in range(ECS[e])] for e in range(EV)]
        charger_on = [[[model.add_var(var_type=BINARY) for _ in range(U)]
                       for _ in range(ECS[e])] for e in range(EV)]

        c_ev = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_power[e])
                 for _ in range(U)] for e in range(EV)]  # consumption charger
        ev_accu_in = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=max_power[e])
                       for _ in range(U)] for e in range(EV)]  # consumption charger

        for e in range(EV):
            if (energy_needed[e] > 0) and (ready_u[e] < U):
                for u in range(ready_u[e] + 1):
                    # laden, alles uitgedrukt in vermogen kW
                    for cs in range(ECS[e]):
                        # daadwerkelijk ac vermogen = vermogen van de stap x oplaadfactor (0..1)
                        model += charger_power[e][cs][u] == charge_stages[e][cs]["power"] * charger_factor[e][cs][u]
                        # idem met schakelaar
                        model += charger_power[e][cs][u] <= max_power[e] * charger_on[e][cs][u]
                    # som van alle oplaadfactoren is 1
                    model += (xsum(charger_factor[e][cs][u] for cs in range(ECS[e]))) == 1
                    # som van alle schakelaars boven 0 A en kleiner of gelijk aan 1
                    model += (xsum(charger_on[e][cs][u] for cs in range(ECS[e])[1:])) <= 1
                    model += c_ev[e][u] == xsum(charger_power[e][cs][u] * hour_fraction[u] for cs in range(ECS[e]))
                    model += ev_accu_in[e][u] == xsum(charge_stages[e][cs]["accu_power"] * hour_fraction[u] *
                                                      charger_factor[e][cs][u] for cs in range(ECS[e]))
                model += energy_needed[e] == xsum(ev_accu_in[e][u] for u in range(ready_u[e] + 1))

                '''
                max_beschikbaar = 0
                for u in range(ready_u[e] + 1):
                    model += c_ev[e][u] <= charger_on[e][u] * hour_fraction[u] * max_power[e]
                    max_beschikbaar += hour_fraction[u] * max_power[e]
                for u in range(ready_u[e] + 1, U):
                    model += charger_on[e][u] == 0
                    model += c_ev[e][u] == 0
                model += xsum(charger_on[e][j] for j in range(ready_u[e] + 1)) == hours_needed[e]
                model += xsum(c_ev[e][u] for u in range(ready_u[e] + 1)) == min(max_beschikbaar, energy_needed[e])
                '''
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
        c_l = [model.add_var(var_type=CONTINUOUS, lb=0, ub=self.grid_max_power) for _ in range(U)]
        # teruglevering
        c_t_total = [model.add_var(var_type=CONTINUOUS, lb=0, ub=self.grid_max_power) for _ in range(U)]
        c_t_w_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=self.grid_max_power) for _ in range(U)]
        c_l_on = [model.add_var(var_type=BINARY) for _ in range(U)]
        c_t_on = [model.add_var(var_type=BINARY) for _ in range(U)]

        # salderen == True
        # c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]

        if salderen:
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for _ in range(U)]
        else:
            # alles wat meer wordt teruggeleverd dan geleverd (c_t_no_tax) wordt niet gesaldeerd
            # (geen belasting terug): tarief pt_notax
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=self.grid_max_power) for _ in range(U)]
            model += (xsum(c_t_w_tax[u] for u in range(U)) + production_today) <= \
                     (xsum(c_l[u] for u in range(U)) + consumption_today)
        # netto per uur alleen leveren of terugleveren niet tegelijk?
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
            c_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0)
                    for _ in range(U)]  # elektriciteitsverbruik in kWh/h
            p_hp = None
            h_hp = None
        else:
            degree_days = self.meteo.calc_graaddagen()
            if U > 24:
                degree_days += self.meteo.calc_graaddagen(date=datetime.datetime.combine(
                    datetime.date.today() + datetime.timedelta(days=1), datetime.datetime.min.time()))
            print("\nWarmtepomp")
            print("Graaddagen: ", degree_days)

            # 3.6  heat factor kWh th / K.day
            degree_days_factor = self.heating_options["degree days factor"]
            heat_produced = float(self.get_state("sensor.daily_heat_production_heating").state)
            heat_needed = max(0.0, degree_days * degree_days_factor - heat_produced)  # heet needed
            stages = self.heating_options["stages"]
            S = len(stages)
            c_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10)
                    for _ in range(U)]  # elektriciteitsverbruik in kWh/h
            # p_hp[s][u]: het gevraagde vermogen in W in dat uur
            p_hp = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=stages[s]["max_power"])
                     for _ in range(U)] for s in range(S)]

            # schijven aan/uit, iedere schijf kan maar een keer in een uur
            hp_on = [[model.add_var(var_type=BINARY) for _ in range(U)] for _ in range(S)]

            # verbruik per uur
            for u in range(U):
                # verbruik in kWh is totaal vermogen in W/1000
                model += c_hp[u] == (xsum(p_hp[s][u] for s in range(S))) / 1000
                # kosten
                # model += k_hp[u] == c_hp[u] * pl[u]  # kosten = verbruik x tarief

            # geproduceerde warmte kWh per uur
            h_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10000) for _ in range(U)]

            # beschikbaar vermogen x aan/uit, want p_hpx[u] X hpx_on[u] kan niet
            for u in range(U):
                for s in range(S):
                    model += p_hp[s][u] <= stages[s]["max_power"] * hp_on[s][u]
                # ieder uur maar een aan
                model += (xsum(hp_on[s][u] for s in range(S))) + boiler_on[u] == 1
                # geproduceerde warmte = vermogen in W * COP_schijf /1000 in kWh
                model += h_hp[u] == xsum((p_hp[s][u] * stages[s]["cop"]/1000) for s in range(S)) * hour_fraction[u]
            # som van alle geproduceerde warmte == benodigde warmte
            model += xsum(h_hp[u] for u in range(U)) == heat_needed

        # alle verbruiken in de totaal balans in kWh
        for u in range(U):
            model += c_l[u] == c_t_total[u] + b_l[u] * hour_fraction[u] + \
                xsum(ac_to_dc[b][u] - ac_from_dc[b][u] for b in range(B)) * hour_fraction[u] + \
                c_b[u] + xsum(c_ev[e][u] for e in range(EV)) + \
                c_hp[u] * hour_fraction[u] - xsum(pv_ac[s][u] for s in range(solar_num))

        # cost variabele
        cost = model.add_var(var_type=CONTINUOUS, lb=-1000, ub=1000)
        delivery = model.add_var(var_type=CONTINUOUS, lb=0, ub=1000)
        model += delivery == xsum(c_l[u] for u in range(U))

        if salderen:
            p_bat = p_avg
        else:
            p_bat = sum(pt_notax)/U

        # alles in kWh * prijs = kosten in euro
        model += cost == xsum(c_l[u] * pl[u] - c_t_w_tax[u] * pt[u] - c_t_no_tax[u] * pt_notax[u] for u in range(U)) + \
            xsum(xsum((dc_to_bat[b][u] + dc_from_bat[b][u]) * kwh_cycle_cost[b] +
                      (opt_low_level[b] - soc_low[b][u]) * 0.0025 for u in range(U)) for b in range(B)) + \
            xsum((soc_mid[b][0] - soc_mid[b][U]) * one_soc[b] * eff_bat_to_dc[b]
                 * avg_eff_dc_to_ac[b] * p_bat for b in range(B))  # waarde opslag accu
        # +(boiler_temp[U] - boiler_ondergrens) * (spec_heat_boiler/(3600 * cop_boiler)) * p_avg # waarde energie boiler

        #####################################################
        #        strategy optimization
        #####################################################
        # settings
        model.max_gap = 0.1
        model.max_nodes = 1500

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
            # strategie = 'niet gekozen'
            return
        print("Strategie: " + strategie + "\n")

        if model.num_solutions == 0:
            print("Er is helaas geen oplossing gevonden, kijk naar je instellingen.")
            return
        else:  # er is een oplossing
            # afdrukken van de resultaten
            print("Het programma heeft een optimale oplossing gevonden.")
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
                    ac_to_dc_sum += ac_to_dc[b][u].x  # / eff_ac_to_dc[b]
                    dc_to_ac_sum += ac_from_dc[b][u].x  # * eff_dc_to_ac[b]
                accu_in_sum.append(ac_to_dc_sum)
                accu_out_sum.append(dc_to_ac_sum)
            for u in range(U):
                ev_sum = 0
                for e in range(EV):
                    ev_sum += c_ev[e][u].x
                c_ev_sum.append(ev_sum)
            pv_ac_hour_sum = []  # totale bruto pv_dc->ac productie
            solar_hour_sum = []  # totale netto pv_ac productie
            for u in range(U):
                pv_ac_hour_sum.append(0)
                solar_hour_sum.append(0)
                for b in range(B):
                    for s in range(pv_dc_num[b]):
                        pv_ac_hour_sum[u] += pv_prod_ac[b][s][u]
                for s in range(solar_num):
                    solar_hour_sum[u] += pv_ac[s][u].x
                netto = b_l[u] + c_b[u].x + c_hp[u].x + \
                    c_ev_sum[u] - solar_hour_sum[u] - pv_ac_hour_sum[u]
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
                # er wordt (een deel) niet gesaldeerd
                dag_str = datetime.datetime.now().strftime("%Y-%m-%d")
                taxes_l = get_value_from_dict(dag_str, taxes_l_def)
                btw = get_value_from_dict(dag_str, btw_def)
                saldeer_corr_gc = -sum_old_cons * \
                    (sum(p_grt) / len(p_grt) - 0.11)
                saldeer_corr_da = -sum_old_cons * taxes_l * (1 + btw)
                old_cost_gc += saldeer_corr_gc
                old_cost_da += saldeer_corr_da
                print("Saldeercorrectie: {:<6.2f} kWh".format(sum_old_cons))
                print("Saldeercorrectie niet geoptimaliseerd reg. tarieven: {:<6.2f} euro".format(
                    saldeer_corr_gc))
                print("Saldeercorrectie niet geoptimaliseerd day ahead tarieven: {:<6.2f} euro".format(
                    saldeer_corr_da))
            else:
                print("Geen saldeer correctie")
            print("Niet geoptimaliseerd, kosten met reguliere tarieven: {:<6.2f}".format(
                old_cost_gc))
            print("Niet geoptimaliseerd, kosten met day ahead tarieven: {:<6.2f}".format(
                old_cost_da))
            print(
                "Geoptimaliseerd, kosten met day ahead tarieven: {:<6.2f}".format(cost.x))
            print("Levering (kWh): {:<6.2f}".format(delivery.x))
            if self.boiler_present:
                boiler_at_23 = ((boiler_temp[U].x - (boiler_setpoint - boiler_hysterese)) *
                                (spec_heat_boiler / (3600 * cop_boiler)))
                print("Waarde boiler om 23 uur: {:<0.2f}".format(boiler_at_23), "kWh")
            if self.heater_present:
                print("\nInzet warmtepomp")
                print(
                    "u     tar     p0     p1     p2     p3     p4     p5     p6     p7   heat   cons")
                for u in range(U):
                    print("{:2.0f}".format(uur[u]), "{:6.4f}".format(pl[u]), "{:6.0f}".format(p_hp[0][u].x),
                          "{:6.0f}".format(p_hp[1][u].x), "{:6.0f}".format(p_hp[2][u].x),
                          "{:6.0f}".format(p_hp[3][u].x), "{:6.0f}".format(p_hp[4][u].x),
                          "{:6.0f}".format(p_hp[5][u].x), "{:6.0f}".format(p_hp[6][u].x),
                          "{:6.0f}".format(p_hp[7][u].x), "{:6.2f}".format(h_hp[u].x), "{:6.2f}".format(c_hp[u].x))
                print("\n")

            # overzicht per ac-accu:
            pd.options.display.float_format = '{:6.2f}'.format
            df_accu = []
            for b in range(B):
                cols = [['uur', 'ac->', 'eff', '->dc', 'pv->dc', 'dc->', 'eff', '->bat', 'o_eff', 'SoC'],
                        ["", "kWh", "%", "kWh", "kWh", "kWh", "%", "kWh", "%", "%"]]
                df_accu.append(pd.DataFrame(columns=cols))
                for u in range(U):
                    '''
                    for cs in range(CS[b]):
                        if ac_to_dc_st_on[b][cs][u].x == 1:
                            c_stage = cs
                            ac_to_dc_eff = self.battery_options[b]["charge stages"][cs]["efficiency"] * 100.0
                    '''
                    ac_to_dc_netto = ac_to_dc[b][u].x - ac_from_dc[b][u].x
                    dc_from_ac_netto = dc_from_ac[b][u].x - dc_to_ac[b][u].x
                    if ac_to_dc_netto > 0:
                        ac_to_dc_eff = dc_from_ac_netto * 100.0 / ac_to_dc_netto
                    elif ac_to_dc_netto < 0:
                        ac_to_dc_eff = ac_to_dc_netto * 100.0 / dc_from_ac_netto
                    else:
                        ac_to_dc_eff = "--"

                    dc_to_bat_netto = dc_to_bat[b][u].x - dc_from_bat[b][u].x
                    bat_from_dc_netto = dc_to_bat[b][u].x * eff_dc_to_bat[b] - dc_from_bat[b][u].x / eff_bat_to_dc[b]
                    if dc_to_bat_netto > 0:
                        dc_to_bat_eff = bat_from_dc_netto * 100.0/dc_to_bat_netto
                    elif dc_to_bat_netto < 0:
                        dc_to_bat_eff = dc_to_bat_netto * 100.0 / bat_from_dc_netto
                    else:
                        dc_to_bat_eff = "--"

                    if ac_to_dc_netto > 0:
                        overall_eff = bat_from_dc_netto * 100.0 / ac_to_dc_netto
                    elif bat_from_dc_netto < 0:
                        overall_eff = ac_to_dc_netto * 100.0 / bat_from_dc_netto
                    else:
                        overall_eff = "--"

                    '''
                    for ds in range(DS[b]):
                        if ac_from_dc_st_on[b][ds][u].x == 1:
                            d_stage = ds
                            dc_to_ac_eff = self.battery_options[b]["discharge stages"][ds]["efficiency"] * 100.0
                    '''

                    pv_prod = 0
                    for s in range(pv_dc_num[b]):
                        pv_prod += pv_dc_on_off[b][s][u].x * pv_prod_dc[b][s][u]
                    row = [str(uur[u]), ac_to_dc_netto, ac_to_dc_eff, dc_from_ac_netto,  pv_prod,
                           dc_to_bat_netto, dc_to_bat_eff, bat_from_dc_netto, overall_eff, soc[b][u + 1].x]
                    df_accu[b].loc[df_accu[b].shape[0]] = row

                # df_accu[b].loc['total'] = df_accu[b].select_dtypes(numpy.number).sum()
                # df_accu[b] = df_accu[b].astype({"uur": int})
                df_accu[b].loc["Total"] = df_accu[b].sum(axis=0, numeric_only=True)
                df_accu[b].at[df_accu[b].index[-1], "uur"] = "Totaal"
                df_accu[b].at[df_accu[b].index[-1], "eff"] = "--"
                df_accu[b].at[df_accu[b].index[-1], "o_eff"] = "--"
                df_accu[b].at[df_accu[b].index[-1], "SoC"] = ""

                print(f"In- en uitgaande energie per uur batterij {self.battery_options[b]['name']}")
                print(df_accu[b].to_string(index=False))
                print("\n")

            # totaal overzicht
            # pd.options.display.float_format = '{:,.3f}'.format
            cols = ['uur', 'bat_in', 'bat_out']
            cols = cols + ['cons', 'prod', 'base', 'boil', 'wp', 'ev', 'pv_ac', 'cost', 'profit', 'b_tem']
            d_f = pd.DataFrame(columns=cols)
            for u in range(U):
                row = [uur[u], accu_in_sum[u], accu_out_sum[u]]
                row = row + [c_l[u].x, c_t_total[u].x, b_l[u],
                             c_b[u].x, c_hp[u].x, c_ev_sum[u], solar_hour_sum[u], c_l[u].x * pl[u],
                             -c_t_w_tax[u].x * pt[u] - c_t_no_tax[u].x * pt_notax[u],
                             boiler_temp[u + 1].x]
                d_f.loc[d_f.shape[0]] = row
            if not self.debug:
                self.save_df(tablename='prognoses', tijd=tijd, df=d_f.iloc[:, 1:-1])
            else:
                print("Prognoses zijn niet opgeslagen.")

            d_f = d_f.astype({"uur": int})
            d_f.loc['total'] = d_f.iloc[:, 1:-1].sum()
            d_f.at[d_f.index[-1], "uur"] = "Totaal"
            d_f.at[d_f.index[-1], "b_tem"] = ""

            print(d_f.to_string(index=False))  # , formatters={'uur':'{:03d}'.format}))
            print("\nWinst: {:<0.2f}".format(old_cost_da - cost.x), "€")

            # doorzetten van alle settings naar HA
            if not self.debug:
                print("\nDoorzetten van alle settings naar HA")
            else:
                print("\nOnderstaande settings worden NIET doorgezet naar HA")

                '''
            set helpers output home assistant
            boiler c_b[0].x >0 trigger boiler
            ev     c_ev[0].x > 0 start laden auto, ==0 stop laden auto
            battery multiplus feedin from grid = accu_in[0].x - accu_out[0].x
            '''
            # boiler
            if self.boiler_present:
                if float(c_b[0].x) > 0.0:
                    if self.debug:
                        print("Boiler opwarmen zou zijn geactiveerd")
                    else:
                        self.call_service(self.boiler_options["activate service"],
                                          entity_id=self.boiler_options["activate entity"])
                        # "input_button.hw_trigger")
                        print("Boiler opwarmen geactiveerd")
                else:
                    print("Boiler opwarmen niet geactiveerd")
            print()

            # ev
            for e in range(EV):
                if ready_u[e] < U:
                    print(f"Inzet-factor laden {self.ev_options[e]['name']} per stap")
                    print("uur", end=" ")
                    for cs in range(ECS[0]):
                        print(f" {charge_stages[e][cs]['ampere']:4.1f}A", end=" ")
                    print()
                    for u in range(ready_u[e] + 1):
                        print(f"{uur[u]:2d}", end="    ")
                        for cs in range(ECS[0]):
                            print(f"{abs(charger_factor[0][cs][u].x):.2f}", end="   ")
                        print()
                entity_charge_switch = self.ev_options[e]["charge switch"]
                entity_charging_ampere = self.ev_options[e]["entity set charging ampere"]
                old_switch_state = self.get_state(entity_charge_switch).state
                old_ampere_state = self.get_state(entity_charging_ampere).state
                new_ampere_state = 0
                new_switch_state = "off"
                # print()
                # print(uur[0], end="  ")
                for cs in range(ECS[e])[1:]:
                    # print(f"{charger_factor[e][cs][0].x:.2f}", end="  ")
                    if charger_factor[e][cs][0].x > 0:
                        new_ampere_state = charge_stages[e][cs]["ampere"]
                        if new_ampere_state > 0:
                            new_switch_state = "on"
                        break
                ev_name = self.ev_options[e]["name"]
                print(f"Berekeningsuitkomst voor opladen van {ev_name}:")
                print(f"- aantal ampere {new_ampere_state}A (was {old_ampere_state}A)")
                print(f"- stand schakelaar '{new_switch_state}' (was '{old_switch_state}')")
                print(f"- positie: {ev_position[e]}")
                print(f"- ingeplugd: {ev_plugged_in[e]}")

                if ev_position[e] == "home" and ev_plugged_in[e]:
                    try:
                        if float(new_ampere_state) > 0.0:
                            if old_switch_state == "off":
                                if self.debug:
                                    print(f"Laden van {ev_name} zou zijn aangezet met {new_ampere_state} ampere")
                                else:
                                    print(f"Laden van {ev_name} aangezet met {new_ampere_state} ampere via "
                                          f"'{entity_charging_ampere}'")
                                    self.set_value(entity_charging_ampere, new_ampere_state)
                                    self.turn_on(entity_charge_switch)
                            if old_switch_state == "on":
                                if self.debug:
                                    print(f"Laden van {ev_name} zou zijn doorgegaan met {new_ampere_state} ampere")
                                else:
                                    print(f"Laden van {ev_name} is doorgegaan met {new_ampere_state} ampere")
                                    self.set_value(entity_charging_ampere, new_ampere_state)
                        else:
                            if old_switch_state == "on":
                                if self.debug:
                                    print(f"Laden van {ev_name} zou zijn uitgezet")
                                else:
                                    self.set_value(entity_charging_ampere, 0)
                                    self.turn_off(entity_charge_switch)
                                    print(f"Laden van {ev_name} uitgezet")
                    except Exception as ex:
                        error_str = utils.error_handling()
                        print(ex)
                        print(f"Onverwachte fout: {error_str}")
                else:
                    print(f"{ev_name} is niet thuis of niet ingeplugd")
                print(f"Evaluatie status laden {ev_name} op {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
                print(f"- schakelaar laden: {self.get_state(entity_charge_switch).state}")
                print(f"- aantal ampere: {self.get_state(entity_charging_ampere).state}")
                print()

            # solar
            for s in range(solar_num):
                entity_pv_switch = self.config.get(["entity pv switch"], self.solar[s])
                switch_state = self.get_state(entity_pv_switch).state
                pv_name = self.solar[s]["name"]
                if (pv_ac_on_off[s][0].x == 1.0) or (solar_prod[s][0] == 0.0):
                    if switch_state == "off":
                        if self.debug:
                            print(f"PV {pv_name} zou zijn aangezet")
                        else:
                            self.turn_on(entity_pv_switch)
                            print(f"PV {pv_name} aangezet")
                else:
                    if switch_state == "on":
                        if self.debug:
                            print(f"PV {pv_name} zou zijn uitgezet")
                        else:
                            self.turn_off(entity_pv_switch)
                            print(f"PV {pv_name} uitgezet")

                # battery
            for b in range(B):
                # vermogen aan ac kant
                netto_vermogen = int(1000 * (ac_to_dc[b][0].x - ac_from_dc[b][0].x))
                minimum_power = int(self.battery_options[b]["minimum power"])
                bat_name = self.battery_options[b]["name"]
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
                if stop_victron is None:
                    stop_str = "2000-01-01 00:00:00"
                else:
                    stop_str = stop_victron.strftime('%Y-%m-%d %H:%M')

                if self.debug:
                    print(f"Netto vermogen naar(+)/uit(-) batterij {bat_name} zou zijn: ", netto_vermogen, "W")
                    print("Balanceren zou zijn:", balance)
                    if stop_victron:
                        print("tot: ", stop_str)
                else:
                    self.set_value(self.battery_options[b]["entity set power feedin"], netto_vermogen)
                    self.select_option(self.battery_options[b]["entity set operating mode"], new_state)
                    if balance:
                        self.set_state(self.battery_options[b]["entity balance switch"], 'on')
                    else:
                        self.set_state(self.battery_options[b]["entity balance switch"], 'off')
                    print(f"Netto vermogen (+)/uit(-) batterij {bat_name}: ", netto_vermogen, "W")
                    print("Balanceren:", balance)
                    if stop_victron:
                        print("tot: ", stop_str)
                    helper_id = self.battery_options[b]["entity stop victron"]
                    self.call_service("set_datetime", entity_id=helper_id, datetime=stop_str)

                for s in range(pv_dc_num[b]):
                    entity_pv_switch = self.battery_options[b]["solar"][s]["entity pv switch"]
                    switch_state = self.get_state(entity_pv_switch).state
                    pv_name = self.battery_options[b]["solar"][s]["name"]
                    if pv_dc_on_off[b][s][0].x == 1 or pv_prod_dc[b][s][0] == 0.0:
                        if switch_state == "off":
                            if self.debug:
                                print(f"PV {pv_name} zou zijn aangezet")
                            else:
                                self.turn_on(entity_pv_switch)
                                print(f"PV {pv_name} aangezet")
                    else:
                        if switch_state == "on":
                            if self.debug:
                                print(f"PV {pv_name} zou zijn uitgezet")
                            else:
                                self.turn_off(entity_pv_switch)
                                print(f"PV {pv_name} uitgezet")
                        self.turn_on(entity_pv_switch)

            # heating
            if self.heater_present:
                entity_curve_adjustment = self.heating_options["entity adjust heating curve"]
                old_adjustment = float(self.get_state(
                    entity_curve_adjustment).state)
                # adjustment factor (K/%) bijv 0.4 K/10% = 0.04
                adjustment_factor = self.heating_options["adjustment factor"]
                adjustment = utils.calc_adjustment_heatcurve(
                    pl[0], p_avg, adjustment_factor, old_adjustment)
                if self.debug:
                    print("Aanpassing stooklijn zou zijn: ", adjustment)
                else:
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
                pv_ac_p.append(pv_ac_hour_sum[u])
                accu_in_sum = 0
                accu_out_sum = 0
                for b in range(B):
                    accu_in_sum += ac_to_dc[b][u].x
                    accu_out_sum += ac_from_dc[b][u].x
                accu_in_n.append(-accu_in_sum * hour_fraction[u])
                accu_out_p.append(accu_out_sum * hour_fraction[u])
                max_y = max(max_y, (c_l_p[u] + pv_p[u] + pv_ac_p[u]), abs(
                    c_t_total[u].x) + b_l[u] + c_b[u].x + c_hp[u].x + c_ev_sum[u] + accu_in_sum)
                for b in range(B):
                    if u == 0:
                        soc_p.append([])
                    soc_p[b].append(soc[b][u].x)
            for b in range(B):
                soc_p[b].append(soc[b][U].x)

            # grafiek 1
            import numpy as np
            from da_graph import GraphBuilder
            gr1_df = pd.DataFrame()
            gr1_df["index"] = np.arange(U)
            gr1_df["uur"] = uur[0:U]
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
            style = self.config.get(['graphics', 'style'])
            gr1_options = {
                "title": "Prognose berekend op: " + now_dt.strftime('%Y-%m-%d %H:%M'),
                "style": style,
                "haxis": {
                    "values": "uur",
                    "title": "uren van de dag"
                },
                "vaxis": [{
                    "title": "kWh"
                }
                ],
                "series": [{"column": "verbruik",
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
                            "color": 'yellow'
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
            backend = self.config.get(["graphical backend"], None, "")
            gb = GraphBuilder(backend)
            show_graph = self.config.get(['graphics', 'show'], None, "False").lower() == 'true'
            if show_graph:
                gb.build(gr1_df, gr1_options)

            grid0_df = pd.DataFrame()
            grid0_df["index"] = np.arange(U)
            grid0_df["uur"] = uur[0:U]
            grid0_df["verbruik"] = org_l
            grid0_df["productie"] = org_t
            grid0_df["baseload"] = base_n
            grid0_df["boiler"] = boiler_n
            grid0_df["heatpump"] = heatpump_n
            grid0_df["ev"] = ev_n
            grid0_df["pv_ac"] = pv_ac_p
            grid0_df["pv_dc"] = pv_p
            style = self.config.get(['graphics', 'style'], None, "default")
            import matplotlib.pyplot as plt
            import matplotlib.ticker as ticker

            plt.style.use(style)
            fig, axis = plt.subplots(figsize=(8, 9), nrows=3)
            ind = np.arange(U)
            axis[0].bar(ind, np.array(org_l), label='Levering', color='#00bfff', align="edge")
            if sum(pv_p) > 0:
                axis[0].bar(ind, np.array(pv_p), bottom=np.array(
                    org_l), label='PV AC', color='green', align="edge")
            if sum(pv_ac_p) > 0:
                axis[0].bar(ind, np.array(pv_ac_p), bottom=np.array(
                    org_l) + np.array(pv_p), label='PV DC', color='lime', align="edge")
            axis[0].bar(ind, np.array(base_n),
                        label="Overig verbr.", color='#f1a603', align="edge")
            if self.boiler_present:
                axis[0].bar(ind, np.array(boiler_n), bottom=np.array(
                    base_n), label="Boiler", color='#e39ff6', align="edge")
            if self.heater_present:
                axis[0].bar(ind, np.array(heatpump_n), bottom=np.array(
                    base_n), label="WP", color='#a32cc4', align="edge")
            axis[0].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n),
                        label="EV laden", color='yellow', align="edge")
            axis[0].bar(ind, np.array(org_t),
                        bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n),
                        label="Teruglev.", color='#0080ff', align="edge")
            axis[0].legend(loc='best', bbox_to_anchor=(1.05, 1.00))
            axis[0].set_ylabel('kWh')
            ylim = math.ceil(max_y)
            # math.ceil(max(max(accu_out_p) + max(c_l_p) + max(pv_p), -min(min(base_n), min(boiler_n),
            # min(heatpump_n), min(ev_n), min(c_t_n), min(accu_in_n) )))
            axis[0].set_ylim([-ylim, ylim])
            axis[0].set_xticks(ind, labels=uur)
            axis[0].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[0].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[0].set_title(
                "Berekend op: " + now_dt.strftime('%d-%m-%Y %H:%M') + "\nNiet geoptimaliseerd")

            axis[1].bar(ind, np.array(c_l_p),
                        label='Levering', color='#00bfff', align="edge")
            axis[1].bar(ind, np.array(pv_p), bottom=np.array(
                c_l_p), label='PV AC', color='green', align="edge")
            axis[1].bar(ind, np.array(accu_out_p), bottom=np.array(c_l_p) + np.array(pv_p), label='Accu uit',
                        color='red', align="edge")

            # axis[1].bar(ind, np.array(cons_n), label="Verbruik", color='yellow')
            axis[1].bar(ind, np.array(base_n),
                        label="Overig verbr.", color='#f1a603', align="edge")
            if self.boiler_present:
                axis[1].bar(ind, np.array(boiler_n), bottom=np.array(
                    base_n), label="Boiler", color='#e39ff6', align="edge")
            if self.heater_present:
                axis[1].bar(ind, np.array(heatpump_n), bottom=np.array(
                    base_n), label="WP", color='#a32cc4', align="edge")
            axis[1].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n),
                        label="EV laden", color='yellow', align="edge")
            axis[1].bar(ind, np.array(c_t_n),
                        bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n),
                        label="Teruglev.", color='#0080ff', align="edge")
            axis[1].bar(ind, np.array(accu_in_n),
                        bottom=np.array(base_n) + np.array(boiler_n) +
                        np.array(heatpump_n) + np.array(ev_n) + np.array(c_t_n),
                        label='Accu in', color='#ff8000', align="edge")
            axis[1].legend(loc='best', bbox_to_anchor=(1.05, 1.00))
            axis[1].set_ylabel('kWh')
            axis[1].set_ylim([-ylim, ylim])
            axis[1].set_xticks(ind, labels=uur)
            axis[1].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[1].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[1].set_title("Day Ahead geoptimaliseerd: " + strategie +
                              ", winst € {:<0.2f}".format(old_cost_da - cost.x))
            axis[1].sharex(axis[0])

            ln1 = []
            line_styles = ["solid", "dashed", "dotted"]
            ind = np.arange(U+1)
            uur.append(24)
            for b in range(B):
                ln1.append(axis[2].plot(ind, soc_p[b], label='SoC ' + self.battery_options[b]["name"],
                           linestyle=line_styles[b], color='red'))
            axis[2].set_xticks(ind, labels=uur)
            axis[2].set_ylabel('% SoC')
            axis[2].set_xlabel("uren van de dag")
            axis[2].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[2].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[2].set_ylim([0, 100])
            axis[2].set_title("Verloop SoC en tarieven")
            axis[2].sharex(axis[0])

            axis22 = axis[2].twinx()
            if self.config.get(["graphics", "prices delivery"], None, "true").lower() == "true":
                pl.append(pl[-1])
                ln2 = axis22.step(ind, np.array(pl), label='Tarief\nlevering', color='#00bfff', where='post')
            else:
                ln2 = None
            if self.config.get(["graphics", "prices redelivery"], None, "true").lower() == "true":
                pt_notax.append(pt_notax[-1])
                ln3 = axis22.step(ind, np.array(pt_notax), label="Tarief terug\nno tax", color='#0080ff', where='post')
            else:
                ln3 = None
            if self.config.get(["graphics", "average delivery"], None, "true").lower() == "true":
                pl_avg.append(pl_avg[-1])
                ln4 = axis22.plot(ind, np.array(pl_avg), label="Tarief lev.\ngemid.", linestyle="dashed",
                                  color='#00bfff')
            else:
                ln4 = None
            axis22.set_ylabel("euro/kWh")
            axis22.yaxis.set_major_formatter(
                ticker.FormatStrFormatter('% 1.2f'))
            bottom, top = axis22.get_ylim()
            if bottom > 0:
                axis22.set_ylim([0, top])
            lns = ln1[0]
            for b in range(B)[1:]:
                lns += ln1[b]
#            lns += ln2 + ln3 + ln4
            if ln2:
                lns += ln2
            if ln3:
                lns += ln3
            if ln4:
                lns += ln4
            labels = [line.get_label() for line in lns]
            axis22.legend(lns, labels, loc='best', bbox_to_anchor=(1.40, 1.00))

            plt.subplots_adjust(right=0.75)
            fig.tight_layout()
            plt.savefig("../data/images/optimum_" + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M") + ".png")
            if show_graph:
                plt.show()
            plt.close()

    def clean_data(self):
        """
        takes care for cleaning folders data/log and data/images
        """
        def clean_folder(folder: str, pattern: str):
            current_time = time.time()
            day = 24 * 60 * 60
            print(f"Start removing files in {folder} with pattern {pattern}")
            current_dir = os.getcwd()
            os.chdir(os.path.join(os.getcwd(), folder))
            list_files = os.listdir()
            for f in list_files:
                if fnmatch.fnmatch(f, pattern):
                    creation_time = os.path.getctime(f)
                    if (current_time - creation_time) >= self.config.get(["save days"], self.history_options, 7) * day:
                        os.remove(f)
                        print("{} removed".format(f))
            os.chdir(current_dir)
        clean_folder("../data/log", "*.log")
        clean_folder("../data/log", "dashboard.log.*")
        clean_folder("../data/images", "*.png")

    @staticmethod
    def calc_baseloads():
        from da_report import Report
        report = Report()
        report.calc_save_baseloads()

    def run_task(self, task):
        old_stdout = sys.stdout
        log_file = open("../data/log/" + task + "_" + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M") + ".log", "w")
        sys.stdout = log_file
        try:
            print("Day Ahead Optimalisatie gestart:",
                  datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'), ': ', task)
            print("Locatie: latitude", str(self.config.get(["latitude"])) + ' longitude:' +
                  str(self.config.get(["longitude"])))
            getattr(self, task)()
            self.set_last_activity()
        except Exception as ex:
            print(ex)
        sys.stdout = old_stdout
        log_file.close()

    def scheduler(self):
        if not (self.notification_entity is None) and self.notification_opstarten:
            self.set_value(self.notification_entity, "DAO scheduler gestart " +
                           datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))

        while True:
            t = datetime.datetime.now()
            next_min = t - datetime.timedelta(minutes=-1, seconds=t.second, microseconds=t.microsecond)
            # wacht tot hele minuut 0% cpu
            time.sleep((next_min - t).total_seconds())
            hour = next_min.hour
            minute = next_min.minute
            key1 = str(hour).zfill(2) + str(minute).zfill(2)
            # ieder uur in dezelfde minuut voorbeeld xx15
            key2 = "xx" + str(minute).zfill(2)
            # iedere minuut in een uur voorbeeld 02xx
            key3 = str(hour).zfill(2) + "xx"
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
        task = ""
        args = sys.argv[1:]
        for arg in args:
            if arg.lower() == "debug":
                day_ah.debug = not day_ah.debug
                print("Debug =", day_ah.debug)
                continue
            if arg.lower() == "calc":
                # task = "calc_optimum"
                # day_ah.run_task("calc_optimum")
                day_ah.calc_optimum()
                day_ah.set_last_activity()
                continue
            if arg.lower() == "meteo":
                # task = "get_meteo_data"
                # day_ah.run_task("get_meteo_data")
                day_ah.get_meteo_data()
                day_ah.set_last_activity()
                continue
            if arg.lower() == "prices":
                # task = "get_day_ahead_prices"
                # day_ah.run_task("get_day_ahead_prices")
                day_ah.get_day_ahead_prices()
                day_ah.set_last_activity()
                continue
            if arg.lower() == "tibber":
                # task = "get_tibber_data"
                # day_ah.run_task("get_tibber_data")
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
            if arg.lower() == "calc_baseloads":
                day_ah.calc_baseloads()
                day_ah.set_last_activity()
                continue
        if task != "":
            day_ah.run_task(task)
    else:
        day_ah.scheduler()


if __name__ == "__main__":
    main()
