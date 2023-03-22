import datetime as dt
import hassapi as hass
import csv
from pprint import pprint
import sys
from mip import Model, xsum, minimize, BINARY, CONTINUOUS
import time
import numpy

import utils
from utils import *
from da_meteo import *
from da_prices import *
from db_manager import DBmanagerObj


class DayAheadOpt(hass.Hass):

    def __init__(self, file_name=None):
        self.debug = False
        self.config = Config(file_name)
        self.hassurl = self.config.get(['homeassistant', 'url'])
        self.token = self.config.get(['homeassistant', 'token'])
        super().__init__(hassurl=self.hassurl, token=self.token)
        headers = {
            "Authorization": "Bearer " + self.token,
            "content-type": "application/json",
        }
        resp = get(self.hassurl + "api/config", headers=headers)
        resp_dict = json.loads(resp.text)
        # print(resp.text)
        self.config.set("latitude", resp_dict['latitude'])
        self.config.set("longitude", resp_dict['longitude'])
        print(str(self.config.get(["latitude"])) + ':' + str(self.config.get(["longitude"])))
        db_da_name = self.config.get(['database da', "database"])
        db_da_server = self.config.get(['database da', "server"])
        db_da_port = int(self.config.get(['database da', "port"]))
        db_da_user = self.config.get(['database da', "username"])
        db_da_password = self.config.get(['database da', "password"])
        self.db_da = DBmanagerObj(db_name=db_da_name, db_server=db_da_server, db_port=db_da_port,
                                  db_user=db_da_user, db_password=db_da_password)
        db_ha_name = self.config.get(['database ha', "database"])
        db_ha_server = self.config.get(['database ha', "server"])
        db_ha_port = int(self.config.get(['database ha', "port"]))
        db_ha_user = self.config.get(['database ha', "username"])
        db_ha_password = self.config.get(['database ha', "password"])
        self.db_ha = DBmanagerObj(db_name=db_ha_name, db_server=db_ha_server, db_port=db_ha_port,
                                  db_user=db_ha_user, db_password=db_ha_password)
        self.meteo = Meteo(self.config, self.db_da)
        self.solar = self.config.get(["solar"])
        self.prices = DA_Prices(self.config, self.db_da)
        self.tibber_options = self.config.get(["tibber"])
        self.boiler_options = self.config.get(["boiler"])
        self.battery_options = self.config.get(["battery"])
        self.prices_options = self.config.get(["prices"])
        self.ev_options = self.config.get(["electric vehicle"])
        self.heating_options = self.config.get(["heating"])
        self.tasks = self.config.get(["scheduler"])

    def get_meteo_data(self, show_graph: bool = False):
        self.db_da.connect()
        self.meteo.get_meteo_data(show_graph)
        self.db_da.disconnect()

    def get_tibber_data(self):
        self.db_da.connect()
        utils.get_tibber_data(self)
        self.db_da.disconnect()

    def get_day_ahead_prices(self):
        self.db_da.connect()
        self.prices.get_prices()
        self.db_da.disconnect()

    def get_consumption(self, start: datetime.datetime, until=dt.datetime.now()):
        """
        berekent consumption en production tussen start en until
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
        grid_sensors = ['sensor.grid_consumption_low', 'sensor.grid_consumption_high', 'sensor.grid_production_low',
                        'sensor.grid_production_high']
        today = dt.datetime.utcnow().date()
        consumption = 0
        production = 0
        sql = "FLUSH TABLES"
        self.db_ha.run_sql(sql)
        for sensor in grid_sensors:
            sql = (
                    "(SELECT CONVERT_TZ(statistics.`start`, 'GMT', 'CET') moment, statistics.state "
                    "FROM `statistics`, `statistics_meta` "
                    "WHERE statistics_meta.`id` = statistics.`metadata_id` "
                    "AND statistics_meta.`statistic_id` = '" + sensor + "' "
                    "AND `state` IS NOT null "
                    "AND (`start` BETWEEN '" + start.strftime('%Y-%m-%d') + "' "
                        "AND '" + until.strftime('%Y-%m-%d %H:%M') + "') "
                    "ORDER BY `start` ASC LIMIT 1) " 
                    "UNION "
                    "(SELECT CONVERT_TZ(statistics.`start`, 'GMT', 'CET') moment, statistics.state "
                    "FROM `statistics`, `statistics_meta` "
                    "WHERE statistics_meta.`id` = statistics.`metadata_id` "
                    "AND statistics_meta.`statistic_id` = '" + sensor + "' "
                    "AND `state` IS NOT null "                    
                    "AND (`start` BETWEEN '" + start.strftime('%Y-%m-%d') + "' "
                        "AND '" + until.strftime('%Y-%m-%d %H:%M') + "') "
                    "ORDER BY `start` DESC LIMIT 1); "
            )
            data = self.db_ha.run_select_query(sql)
            if len(data.index) == 2:
                value = data['state'][1] - data['state'][0]
                if 'consumption' in sensor:
                    consumption = consumption + value
                elif 'production' in sensor:
                    production = production + value
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

        # global boiler_temp
        now_dt = int(dt.datetime.now().timestamp())

        offset = 0  # offset in uren
        now_h = int(3600 * (math.floor(now_dt / 3600)) + offset * 3600)
        fraction_first_hour = 1 - (now_dt - now_h) / 3600

        prog_data = self.db_da.getPrognoseData(start=now_h, end=None)
        # start = dt.datetime.timestamp(dt.datetime.strptime("2022-05-27", "%Y-%m-%d"))
        # end = dt.datetime.timestamp(dt.datetime.strptime("2022-05-29", "%Y-%m-%d"))
        # prog_data = db_da.getPrognoseData(start, end)
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

        # prijzen "reguliere" leverancier, alleen indicatief, wordt niet mee gerekend
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
            price_l = (row.da_price + taxes_l + ol_l) * (1 + btw / 100)
            price_t = (row.da_price + taxes_t + ol_t) * (1 + btw / 100)
            pl.append(price_l)
            pt.append(price_t)
            # tarief teruglevering zonder eb en btw
            price_t_notax = (row.da_price + ol_t)
            pt_notax.append(price_t_notax)

        U = len(pl)
        if U >= 24:
            p_avg = sum(pl) / U  # max(pl) #
        else:
            dag_str = dt.datetime.now().strftime("%Y-%m-%d")
            ol_l = get_value_from_dict(dag_str, ol_l_def)
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            btw = get_value_from_dict(dag_str, btw_def)
            p_avg = (calc_da_avg() + taxes_l + ol_l) * (1 + btw / 100)
        p_max = max(pl)
        print(pl)
        print(pt)
        for u in range(U):
            pl_avg.append(p_avg)

        # base load
        base_cons = []
        with open('verbruik.csv', newline='') as csvfile:
            verbruikreader = csv.reader(csvfile, delimiter=';')
            i = 0
            for row in verbruikreader:
                if (i > 0) and (i <= 24):
                    base_cons.append(float(row[6].replace(',', '.')))
                i += 1
        pprint(base_cons)  # basislast van 0 tot 23 uur

        # omwerken naar de goede lengte
        # 0.015 kWh/J/cm2 productie van mijn panelen per J/cm2
        pv_yield = []
        solar_num = len(self.solar)
        for s in range(solar_num):
            pv_yield.append(self.config.get(["yield"], self.solar[s]))

        b_l = []  # basislast verbruik
        uur = []  # hulparray met uren
        tijd = []
        ts = []
        global_rad = []  #globale straling per uur
        pv = []  # opwekking zonnepanelen
        p_grl = []  # prijs greenchoice levering
        p_grt = []  # prijs greenchoice teruglevering
        hour_fraction = []
        prog_data = prog_data.reset_index()  # make sure indexes pair with number of rows
        first_hour = True
        for row in prog_data.itertuples():
            dtime = dt.datetime.fromtimestamp(row.time)
            hour = int(dtime.hour)
            uur.append(hour)
            tijd.append(dtime)
            b_l.append(base_cons[hour])
            global_rad.append(row.glob_rad)
            pv_total = 0
            for s in range(solar_num):
                pv_total += self.meteo.calc_solar_rad(self.solar[s], row.time, row.glob_rad)*pv_yield[s]
            if first_hour:
                ts.append(now_dt)
                hour_fraction.append(fraction_first_hour)
                pv.append(pv_total * fraction_first_hour)
            else:
                ts.append(row.time)
                hour_fraction.append(1)
                pv.append(pv_total)
            dag_str = dtime.strftime("%Y-%m-%d")
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            taxes_t = get_value_from_dict(dag_str, taxes_t_def)
            btw = get_value_from_dict(dag_str, btw_def)
            if is_laagtarief(dt.datetime(dtime.year, dtime.month, dtime.day, hour),
                             self.prices_options["switch to low"]):
                p_grl.append((gc_p_low + taxes_l) * (1 + btw / 100))
                p_grt.append((gc_p_low + taxes_t) * (1 + btw / 100))
            else:
                p_grl.append((gc_p_high + taxes_l) * (1 + btw / 100))
                p_grt.append((gc_p_high + taxes_t) * (1 + btw / 100))
            first_hour = False

        # volledig salderen?
        salderen = self.prices_options['tax refund'] == "True"
        last_invoice = dt.datetime.strptime(self.prices_options['last invoice'], "%Y-%m-%d")
        cons_data_history = self.get_consumption(last_invoice, dt.datetime.today())
        if not salderen:
            salderen = cons_data_history["production"] < cons_data_history["consumption"]
        if salderen:
            print("all taxes refund (alles wordt gesaldeerd")
            consumption_today = 0
            production_today = 0
        else:
            consumption_today = float(self.get_state("sensor.daily_grid_consumption").state)
            production_today = float(self.get_state("sensor.daily_grid_production").state)
            print("consumption today: ", consumption_today)
            print("production today: ", production_today)
            print("verschil: ", consumption_today - production_today)

        model = Model()

        # bereken met greenchoice prijzen
        # pl = p_grl
        # pt = p_grt

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
        pv_dc = []
        eff_ac_to_dc = []
        eff_dc_to_ac = []
        eff_dc_to_bat = []
        eff_bat_to_dc = []

        for b in range(B):
            ac = float(self.battery_options[b]["capacity"])  # 2 * 50 * 280/1000 #=28 kWh
            one_soc.append(ac / 100) # 1% van 28 kWh = 0,28 kWh
            kwh_cycle_cost.append(self.battery_options[b]["cycle cost"])
            # kwh_cycle_cost = (cycle_cost/( 2 * ac) ) / ((self.battery_options["upper limit"] -
            #   self.battery_options["lower limit"]) / 100)
            # print ("cycl cost: ", kwh_cycle_cost, " eur/kWh")

            #efficiencies
            eff_ac_to_dc.append(float(self.battery_options[b]["ac_to_dc efficiency"]))  # fractie van 1
            eff_dc_to_ac.append(float(self.battery_options[b]["dc_to_ac efficiency"]))  # fractie van 1
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
            pv_dc_num = len(self.battery_options[b]["solar"])
            pv_dc_bat = []
            for u in range(U):
                pv_total = 0
                for s in range(pv_dc_num):
                    pv_yield = self.battery_options[b]["solar"][s]["yield"]
                    pv_total += self.meteo.calc_solar_rad(self.battery_options[b]["solar"][s], int(tijd[u].timestamp()), global_rad[u]) * pv_yield
                pv_dc_bat.append(pv_total)
            pv_dc.append(pv_dc_bat)


        # energie per uur, vanuit dc gezien
        ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * \
                        float(self.battery_options[b]["max charge power"]))*eff_ac_to_dc[b] for u in range(U)] for b in range(B) ]
        dc_to_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * \
                        float(self.battery_options[b]["max discharge power"]))/eff_dc_to_ac[b] for u in range(U)] for b in range(B) ]
        bat_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * 2 *\
                        float(self.battery_options[b]["max discharge power"])) for u in range(U)] for b in range(B) ]
        dc_to_bat = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=hour_fraction[u] * 2 *\
                        float(self.battery_options[b]["max charge power"])) for u in range(U)] for b in range(B) ]

        soc = [[model.add_var(var_type=CONTINUOUS, lb=min(start_soc[b], float(self.battery_options[b]["lower limit"])),
                 ub=max(start_soc[b], float(self.battery_options[b]["upper limit"]))) for u in range(U + 1)] for b in range(B)]
        soc_low = [[model.add_var(var_type=CONTINUOUS, lb=min(start_soc[b], float(self.battery_options[b]["lower limit"])),
                    ub=opt_low_level[b]) for u in range(U + 1)] for b in range(B) ]
        soc_mid = [[model.add_var(var_type=CONTINUOUS, lb=0,
                                 ub=-opt_low_level[b] + max(start_soc[b], float(self.battery_options[b]["upper limit"])))
                   for u in range(U + 1)] for b in range(B) ]

        for b in range(B):
            for u in range(U + 1):
                model += soc[b][u] == soc_low[b][u] + soc_mid[b][u]
            model += soc[b][0] == start_soc[b]
            model += soc[b][U] >= opt_low_level[b] / 2
            for u in range(U):
                model += soc[b][u + 1] == soc[b][u] + (dc_to_bat[b][u] * eff_dc_to_bat[b] / one_soc[b]) - ((bat_to_dc[b][u] / eff_bat_to_dc[b]) / one_soc[b])
                model += ac_to_dc[b][u] + bat_to_dc[b][u] + pv_dc[b][u] == dc_to_ac[b][u] + dc_to_bat[b][u]

        #####################################
        #             boiler                #
        #####################################
        boiler_act_temp = float(
            self.get_state(self.boiler_options["entity actual temp."]).state)  # 50 huidige boilertemp ophalen uit ha
        boiler_setpoint = float(self.get_state(self.boiler_options["entity setpoint"]).state)
        boiler_hysterese = float(self.get_state(self.boiler_options["entity hysterese"]).state)
        boiler_cooling = self.boiler_options["cooling rate"]  # 0.4 #K/uur instelbaar
        boiler_bovengrens = self.boiler_options[
            "heating allowed below"]  # 45 # oC instelbaar daaronder kan worden verwarmd
        boiler_ondergrens = boiler_setpoint - boiler_hysterese  # 41 #C instelbaar daaronder moet worden verwarmd
        vol = self.boiler_options["volume"]  # liter
        spec_heat_boiler = vol * 4.2 + 100 * 0.5  # kJ/K
        cop_boiler = self.boiler_options["cop"]
        power = self.boiler_options["elec. power"]  # W

        # tijdstip index waarop boiler kan worden verwarmd
        boiler_start = int(max(0, min(23, int((boiler_act_temp - boiler_bovengrens) / boiler_cooling))))

        # tijdstip index waarop boiler nog aan kan
        boiler_end = int(
            min(U - 1, max(0, int((boiler_act_temp - boiler_ondergrens) / boiler_cooling))))  # (41-40)/0.4=2.5

        boiler_on = [model.add_var(var_type=BINARY) for u in range(U)]
        boiler_temp = [
            model.add_var(var_type=CONTINUOUS, lb=boiler_setpoint - boiler_hysterese - 5, ub=boiler_setpoint + 10)
            for u in range(U + 1)]  # end temp boiler

        if boiler_start > boiler_end:  # geen boiler opwarming in deze periode
            c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]  # consumption boiler
            model += xsum(boiler_on[j] for j in range(U)[boiler_start:boiler_end + 1]) == 0
            print("boiler: geen opwarming")
            boiler_end_temp = boiler_act_temp - boiler_cooling * (U)
            print("boiler eind temperatuur: ", boiler_end_temp)
            for u in range(U):
                # opwarming in K = kWh opwarming * 3600 = kJ / spec heat boiler - 3
                model += boiler_temp[u + 1] == boiler_temp[u] - boiler_cooling
        else:
            print("boiler: ", uur[boiler_start], uur[boiler_end])
            needed_elec = [0.0 for u in range(U)]
            needed_time = [0 for u in range(U)]
            # spec heat in kJ/K vol in liter * 4,2 J/liter + 100 kg * 0,5 J/kg
            for u in range(boiler_start, boiler_end + 1):
                needed_heat = max(0.0, float(spec_heat_boiler * (
                        boiler_setpoint - (boiler_act_temp - 3 - boiler_cooling * (u - boiler_start))) / 3600))  # kWh
                needed_elec[u] = 0.9  # needed_heat / cop_boiler  # kWh
                needed_time[u] = needed_elec[u] * 1000 / power  # hour

            c_b = [model.add_var(var_type=CONTINUOUS, lb=0, ub=needed_elec[u]) for u in range(U)]  # consumption boiler
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
                model += boiler_temp[u + 1] == boiler_temp[u] - boiler_cooling + c_b[
                    u] * cop_boiler * 3600 / spec_heat_boiler

        ################################################
        # electric vehicle
        ################################################
        ev_capacity = self.ev_options["capacity"]
        # plugged = self.get_state(self.ev_options["entity plugged in"]).state
        ev_plugged_in = self.get_state(self.ev_options["entity plugged in"]).state == "on"
        ev_position = self.get_state(self.ev_options["entity position"]).state
        actual_soc = float(self.get_state(self.ev_options["entity actual level"]).state)
        wished_level = float(self.get_state(self.ev_options["charge scheduler"]["entity set level"]).state)
        ready_str = self.get_state(self.ev_options["charge scheduler"]["entity ready time"]).state
        ready = dt.datetime.strptime(ready_str, '%H:%M:%S')
        now_dt = dt.datetime.now()
        ready = dt.datetime(now_dt.year, now_dt.month, now_dt.day, ready.hour, ready.minute)
        if (ready.hour == now_dt.hour and ready.minute < now_dt.minute) or (ready.hour < now_dt.hour):
            ready = ready + dt.timedelta(days=1)
        max_ampere = float(self.get_state(self.ev_options["entity max amperage"]).state)
        max_power = max_ampere * 230 / 1000  # vermogen in kW
        energy_needed = ev_capacity * (wished_level - actual_soc) / 100  # in kWh
        time_needed = energy_needed / max_power  # aantal uren bijv 1,5
        start = ready - dt.timedelta(hours=time_needed)
        ready_index = U
        if ev_plugged_in and (ev_position == "home") and (wished_level > actual_soc) and (
                (tijd[U - 1] + dt.timedelta(hours=1)) >= ready):
            for u in range(U):
                if (tijd[u] + dt.timedelta(hours=1)) >= ready:
                    ready_index = u
                    break

            print("ev klaar om: ", (1 + uur[ready_index]), "uur")  # ready index =laatste uur waarin wordt geladen
            hours_needed = math.ceil(time_needed)  # hele uren
            charger_on = [model.add_var(var_type=BINARY) for u in range(U)]
            c_ev = [model.add_var(var_type=CONTINUOUS, lb=0, ub=max_power * hour_fraction[u]) for u in
                    range(U)]  # consumption charger
            max_beschikbaar = 0
            for u in range(ready_index + 1):
                model += c_ev[u] <= charger_on[u] * hour_fraction[u] * max_power
                max_beschikbaar += hour_fraction[u] * max_power
            for u in range(ready_index + 1, U):
                model += charger_on[u] == 0
                model += c_ev[u] == 0
            model += xsum(charger_on[j] for j in range(ready_index + 1)) == hours_needed
            model += xsum(c_ev[u] for u in range(ready_index + 1)) == min(max_beschikbaar, energy_needed)
        else:
            c_ev = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]
            for u in range(U):
                model += c_ev[u] == 0

        # total consumption per hour: base_load plus accuload
        # inkoop + pv + accu_out = teruglevering + base_cons + accu_in + boiler + ev + ruimteverwarming
        # in code:  c_l + pv + accu_out = c_t + b_l + accu_in + hw + ev + rv
        # c_l : verbruik levering
        # c_t : verbruik teruglevering met saldering
        # c_t_notax : verbruik teruglevering zonder saldering
        # pv : opwekking zonnepanelen

        # anders geschreven c_l = c_t + ct_notax + b_l + accu_in + hw + rv - pv - accu_out
        # continue variabele c consumption in kWh/h
        # minimaal 20 kW terugleveren max 10 kW leveren
        # levering
        c_l = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]
        # teruglevering
        c_t_total = [model.add_var(var_type=CONTINUOUS, lb=0, ub=20) for u in range(U)]
        c_t_w_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]
        c_l_on = [model.add_var(var_type=BINARY) for u in range(U)]
        c_t_on = [model.add_var(var_type=BINARY) for u in range(U)]

        # salderen == True
        c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]
        """
        if salderen:
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]
        else:
            # alles wat meer wordt teruggeleverd dan geleverd (c_t_no_tax) wordt niet gesaldeerd (geen belasting terug): tarief pt_notax
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]

            if U > 24:
                u_end = U - 24
            else:
                u_end = U

            #als
            if (production_today - consumption_today) > (
                    (u_end - 1 + fraction_first_hour) * float(self.battery_options["max charge power"])):
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

        #netto per uur alleen leveren of terugleveren niet tegelijk?
        for u in range(U):
            model += c_t_total[u] == c_t_w_tax[u] + c_t_no_tax[u]
            model += c_l[u] <= c_l_on[u] * 20
            model += c_t_total[u] <= c_t_on[u] * 20
            model += c_l_on[u] + c_t_on[u] <= 1


        #heatpump
        degree_days = self.meteo.calc_graaddagen()
        if U>24:
            degree_days += self.meteo.calc_graaddagen(date=datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.datetime.min.time()))
        print("Graaddagen: ", degree_days)

        degree_days_factor = 3.6  # heat factor kWh th / K.day
        heat_produced = float(self.get_state("sensor.daily_heat_production_heating").state)
        heat_needed = max(0.0, degree_days * degree_days_factor - heat_produced)# heet needed
        stages = self.heating_options["stages"]
        S = len(stages)
        c_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]  # elektriciteitsverbruik in kWh/h
        p_hp = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=stages[s]["max_power"]) for u in range(U)] for s in range(S)]

        # schijven aan/uit, iedere schijf kan maar een keer in een uur
        hp_on = [[model.add_var(var_type=BINARY) for u in range(U)] for s in range(S)]

        # verbruik per uur
        for u in range(U):
            # verbruik in kWh is totaal vermogen in W/1000
            model += c_hp[u] == (xsum(p_hp[s][u] for s in range(S))) / 1000
            #kosten
            #model += k_hp[u] == c_hp[u] * pl[u]  # kosten = verbruik x tarief

        # geproduceerde warmte per uur
        h_hp = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10000) for u in range(U)]

        #beschikbaar vermogen x aan/uit, want p_hpx[u] X hpx_on[u] kan niet
        for u in range(U):
            for s in range(S):
                model += p_hp[s][u] <= stages[s]["max_power"] * hp_on[s][u]
            #ieder uur maar een aan
            model += (xsum(hp_on[s][u] for s in range(S))) + boiler_on[u] == 1
            # geprod. warmte = vermogen in W * COP schijf /1000 in kWh
            model += h_hp[u] == xsum ( (p_hp[s][u] * stages[s]["cop"]/1000)  for s in range (S)) * hour_fraction[u]
        model += xsum(h_hp[u] for u in range(U)) == heat_needed  # som van alle warmte == benodigde warmte


        #alle verbruiken in de totaal balans
        for u in range(U):
            model += c_l[u] == c_t_total[u] + b_l[u] + \
                     xsum(ac_to_dc[b][u]/eff_ac_to_dc[b] - dc_to_ac[b][u]*eff_dc_to_ac[b]  for b in range(B)) + \
                     c_b[u] + c_ev[u] + c_hp[u] - pv[u]

        # kosten optimalisering
        model.objective = minimize(
            xsum(c_l[u] * pl[u] - c_t_w_tax[u] * pt[u] - c_t_no_tax[u] * pt_notax[u]  for u in range(U) ) +
                 xsum(xsum((dc_to_bat[b][u] + bat_to_dc[b][u]) * kwh_cycle_cost[b] + (opt_low_level[b] - soc_low[b][u]) * 0.0025
                    for u in range(U)) for b in range(B))
            + xsum((soc_mid[b][0] - soc_mid[b][U]) * one_soc[b] * eff_bat_to_dc[b] * eff_dc_to_ac[b] * p_avg  for b in range(B)) # waarde opslag accu
            # + (boiler_temp[U] - boiler_ondergrens) * (spec_heat_boiler/(3600 * cop_boiler)) * p_avg # waarde energie boiler
        )


        '''
        #optimize minimaliseer levering
        model.objective = minimize(xsum(c_l[u] for u in range(U)) )
        '''

        # optimizing
        model.optimize()

        if model.num_solutions: #er is een oplossing
            #afdrukken van de resultaten
            old_cost_gc = 0
            old_cost_da = 0
            sum_old_cons = 0
            org_l = []
            org_t = []
            for u in range(U):
                netto = b_l[u] + c_b[u].x + c_hp[u].x + c_ev[u].x - pv[u]
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
                dag_str = uur[0].strftime("%Y-%m-%d")
                taxes_l = get_value_from_dict(dag_str, taxes_l_def)
                btw = get_value_from_dict(dag_str, btw_def)
                saldeer_corr_gc = -sum_old_cons * (sum(p_grt) / len(p_grt) - 0.11)
                saldeer_corr_da = -sum_old_cons * taxes_l * (1 + btw)
                old_cost_gc += saldeer_corr_gc
                old_cost_da += saldeer_corr_da
                print("Saldeercorrectie: {:6.2f} kWh".format(sum_old_cons))
                print("Saldeercorrectie niet geoptimaliseerd reg. tarieven: {:6.2f} euro".format(saldeer_corr_gc))
                print("Saldeercorrectie niet geoptimaliseerd day ahead tarieven: {:6.2f} euro".format(saldeer_corr_da))
            else:
                print('Geen saldeer correctie')
            print("Niet geoptimaliseerd, kosten met reguliere tarieven: {:6.2f}".format(old_cost_gc))
            print("Niet geoptimaliseerd, kosten met day ahead tarieven: {:6.2f}".format(old_cost_da))
            print("Geoptimaliseerd, kosten met day ahead tarieven: {:6.2f}".format(float(model.objective_value)))
            print("Waarde boiler om 23 uur: {:6.2f}".format(
                (boiler_temp[U].x - (boiler_setpoint - boiler_hysterese)) * (spec_heat_boiler / (3600 * cop_boiler))),
                " kWh")

            sys.stdout.write('\n optimale kosten %g found: %s\n'
                             % (float(model.objective_value), U))
            print("\nInzet warmtepomp")
            print("u     tar     p0     p1     p2     p3     p4     p5     p6     p7   heat   cons")
            for u in range(U):
                print("{:2.0f}".format(uur[u]), "{:6.4f}".format(pl[u]), "{:6.0f}".format(p_hp[0][u].x), "{:6.0f}".format(p_hp[1][u].x),
                      "{:6.0f}".format(p_hp[2][u].x),
                      "{:6.0f}".format(p_hp[3][u].x), "{:6.0f}".format(p_hp[4][u].x), "{:6.0f}".format(p_hp[5][u].x),
                      "{:6.0f}".format(p_hp[6][u].x), "{:6.0f}".format(p_hp[7][u].x), "{:6.2f}".format(h_hp[u].x),
                      "{:6.2f}".format(c_hp[u].x))
            print("\n")

            #overzicht per accu:
            pd.options.display.float_format = '{:6.2f}'.format
            for b in range(B):
                cols = ['uur', 'ac->dc', 'dc->ac', 'dc->ba', 'ba_dc', 'pv', 'soc']
                d_f = pd.DataFrame(columns = cols)
                for u in range(U):
                    row = [uur[u], ac_to_dc[b][u].x, dc_to_ac[b][u].x, dc_to_bat[b][u].x, bat_to_dc[b][u].x, pv_dc[b][u], soc[b][u+1].x]
                    d_f.loc[d_f.shape[0]] = row
                d_f.loc['total'] = d_f.select_dtypes(numpy.number).sum()
                d_f = d_f.astype({"uur": int})
                print("Accu: ", self.battery_options[b]["name"])
                print("In- en uitgaande energie per uur in kWh op de busbar")
                print(d_f.to_string(index=False))
                print("\n")

            #totaal overzicht
            cols = ['uur', 'bat in', 'bat out']
            cols = cols + ['con_l', 'c_t_t', 'c_t_n', 'bas_l', 'boil', 'wp', 'ev',
                            'pv', 'kos_l', 'kos_t', 'k_t_n', 'b_tem']
            accu_in_sum = []
            accu_out_sum = []
            d_f = pd.DataFrame(columns = cols)
            #print('uur ac->ba ba->ac   lev    tlv   base   boil     ev     pv   cost   prof')
            for u in range(U):
                ac_to_dc_sum = 0
                dc_to_ac_sum = 0
                for b in range(B):
                    ac_to_dc_sum += ac_to_dc[b][u].x / eff_ac_to_dc[b]
                    dc_to_ac_sum += dc_to_ac[b][u].x * eff_dc_to_ac[b]
                accu_in_sum.append(ac_to_dc_sum)
                accu_out_sum.append(dc_to_ac_sum)
                row = [uur[u], ac_to_dc_sum, dc_to_ac_sum]
                row = row + [c_l[u].x, c_t_w_tax[u].x, c_t_no_tax[u].x, b_l[u],
                            c_b[u].x, c_hp[u].x, c_ev[u].x, pv[u], c_l[u].x * pl[u], -c_t_total[u].x * pt[u],
                            -c_t_no_tax[u].x * pt_notax[u], boiler_temp[u + 1].x]
                d_f.loc[d_f.shape[0]] = row
                '''
                print ("{:2}".format(uur[u]), "{:6.2f}".format(ac_to_dc_sum), "{:6.2f}".format(dc_to_ac_sum),
                       "{:6.2f}".format(c_l[u].x), "{:6.2f}".format(c_t_total[u].x), "{:6.2f}".format(b_l[u]),
                       "{:6.2f}".format(c_b[u].x), "{:6.2f}".format(c_ev[u].x),
                       "{:6.2f}".format(pv[u]), "{:6.2f}".format(c_l[u].x*pl[u]), "{:6.2f}".format(-c_t_total[u].x*pt[u]))
    
            sys.stdout.write('\n')
            '''
            pd.options.display.float_format = '{:6.2f}'.format
            d_f.loc['total'] = d_f.select_dtypes(numpy.number).sum()
            d_f = d_f.astype({"uur": int})
            print(d_f.to_string(index=False))
            print("\nWinst: ", "{:6.2f}".format(old_cost_gc - model.objective_value))

            # doorzetten van alle settings naar HA
            if not self.debug:

                '''
                set helpers output home assistant
                boiler c_b[0].x >0 trigger boiler
                ev     c_ev[0].x > 0 start laden auto, ==0 stop laden auto
                battery multiplus feedin from grid = accu_in[0].x - accu_out[0].x
                '''
                # boiler
                # print(self.boiler_options["activate service"], ' ', self.boiler_options["activate entity"])
                if float(c_b[0].x) > 0.0:
                    self.call_service(self.boiler_options["activate service"],
                                      entity_id=self.boiler_options["activate entity"])
                    # "input_button.hw_trigger")
                    print("boiler opwarmen geactiveerd")

                # ev
                if ev_position == "home" and ev_plugged_in:
                    state = self.get_state(self.ev_options["charge switch"]).state
                    try:
                        if float(c_ev[0].x) > 0.0:
                            if state == "off":
                                self.turn_on(self.ev_options["charge switch"])
                        else:
                            if state == "on":
                                self.turn_off(self.ev_options["charge switch"])
                    except:
                        pass

                # battery
                for b in range(B):
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
                    print("Netto vermogen uit grid batterij "+str(b)+": ", netto_vermogen, " W")
                    print("Balanceren: ", balance)
                    if stop_victron == None:
                        datetime_str = "2000-01-01 00:00:00"
                    else:
                        print("tot: ", stop_victron)
                        datetime_str = stop_victron.strftime('%Y-%m-%d %H:%M')
                    helper_id = self.battery_options[b]["entity stop victron"]
                    self.call_service("set_datetime", entity_id=helper_id, datetime=datetime_str)

                # heating
                entity_curve_adjustment = self.heating_options["entity adjust heating curve"]
                old_adjustment = float(self.get_state(entity_curve_adjustment).state)
                # adjustment factor (K/%) bijv 0.4 K/10% = 0.04
                adjustment_factor = self.heating_options["adjustment factor"]
                adjustment = calc_adjustment_heatcurve(pl[0], p_avg, adjustment_factor, old_adjustment)
                print("Aanpassing stooklijn: ", adjustment)
                self.set_value(entity_curve_adjustment, adjustment)
            self.db_da.disconnect()

            # graphs
            accu_in_n = []
            accu_out_p = []
            c_t_n = []
            base_n = []
            boiler_n = []
            heatpump_n= []
            ev_n = []
            cons_n = []
            c_l_p = []
            soc_p = []
            pv_p = []
            for u in range(U):
                c_t_n.append(-c_t_total[u].x)
                c_l_p.append(c_l[u].x)
                base_n.append(-b_l[u])
                boiler_n.append(- c_b[u].x)
                heatpump_n.append(-c_hp[u].x)
                ev_n.append(-c_ev[u].x)
                pv_p.append(pv[u])
                accu_in_sum =0
                accu_out_sum = 0
                for b in range(B):
                    accu_in_sum += ac_to_dc[b][u].x
                    accu_out_sum += dc_to_ac[b][u].x
                accu_in_n.append(-accu_in_sum)
                accu_out_p.append(accu_out_sum)
                soc_p.append(soc[0][u].x)

            import matplotlib.ticker as ticker
            import matplotlib.pyplot as plt
            import numpy as np
            fig, axis = plt.subplots(figsize=(8, 9), nrows=3)  # , sharex= True)
            ind = np.arange(U)
            axis[0].bar(ind, np.array(org_l), label='Levering', color='#00bfff')
            axis[0].bar(ind, np.array(pv_p), bottom=np.array(org_l), label='PV', color='green')
            axis[0].bar(ind, np.array(base_n), label="Overig verbr.", color='#f1a603')
            axis[0].bar(ind, np.array(boiler_n), bottom=np.array(base_n), label="Boiler", color='#e39ff6')
            axis[0].bar(ind, np.array(heatpump_n), bottom=np.array(base_n), label="WP", color='#a32cc4')
            axis[0].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n), label="EV laden",
                        color='#fefbbd')
            axis[0].bar(ind, np.array(org_t), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n),
                        label="Teruglev.", color='#0080ff')
            axis[0].legend(loc='best', bbox_to_anchor=(1.05, 1.00))
            axis[0].set_ylabel('kWh')
            axis[0].set_ylim([-7, 7])
            axis[0].set_xticks(ind, labels=uur)
            axis[0].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[0].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[0].set_title("Berekend op: " + now_dt.strftime('%Y-%m-%d %H:%M') + "\nNiet geoptimaliseerd")

            axis[1].bar(ind, np.array(c_l_p), label='Levering', color='#00bfff')
            axis[1].bar(ind, np.array(pv_p), bottom=np.array(c_l_p), label='PV', color='green')
            axis[1].bar(ind, np.array(accu_out_p), bottom=np.array(c_l_p) + np.array(pv_p), label='Accu uit',
                        color='red')

            # axis[1].bar(ind, np.array(cons_n), label="Verbruik", color = 'yellow')
            axis[1].bar(ind, np.array(base_n), label="Overig verbr.", color='#f1a603')
            axis[1].bar(ind, np.array(boiler_n), bottom=np.array(base_n), label="Boiler", color='#e39ff6')
            axis[1].bar(ind, np.array(heatpump_n), bottom=np.array(base_n), label="WP", color='#a32cc4')
            axis[1].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n), label="EV laden",
                        color='#fefbbd')
            axis[1].bar(ind, np.array(c_t_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n),
                        label="Teruglev.", color='#0080ff')
            axis[1].bar(ind, np.array(accu_in_n),
                        bottom=np.array(base_n) + np.array(boiler_n) + np.array(heatpump_n) + np.array(ev_n) + np.array(c_t_n),
                        label='Accu in', color='#ff8000')
            axis[1].legend(loc='best', bbox_to_anchor=(1.05, 1.00))
            axis[1].set_ylabel('kWh')
            axis[1].set_ylim([-7, 7])
            axis[1].set_xticks(ind, labels=uur)
            axis[1].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[1].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[1].set_title("Geoptimaliseerd")

            ln1 = axis[2].plot(ind, soc_p, label='SOC', color='red')
            axis[2].set_xticks(ind, labels=uur)
            axis[2].set_ylabel('% SOC')
            axis[2].set_xlabel("uren van de dag")
            axis[2].xaxis.set_major_locator(ticker.MultipleLocator(2))
            axis[2].xaxis.set_minor_locator(ticker.MultipleLocator(1))
            axis[2].set_ylim([0, 100])
            axis[2].set_title("Verloop SOC en tarieven")

            axis22 = axis[2].twinx()
            ln2 = axis22.plot(ind, np.array(pl), label='Tarief\nlevering', color='#00bfff')
            ln3 = axis22.plot(ind, np.array(pt_notax), label="Tarief terug\nno tax", color='#0080ff')
            ln4 = axis22.plot(ind, np.array(pl_avg), label="Tarief lev.\ngemid.", linestyle="dashed", color='#00bfff')
            axis22.set_ylabel("euro/kWh")
            axis22.yaxis.set_major_formatter(ticker.FormatStrFormatter('% 1.2f'))
            bottom, top = axis22.get_ylim()
            if bottom > 0:
                axis22.set_ylim([0, top])
            lns = ln1 + ln2 + ln3 + ln4
            labels = [l.get_label() for l in lns]
            axis22.legend(lns, labels, loc='best', bbox_to_anchor=(1.40, 1.00))
            plt.subplots_adjust(right=0.75)
            fig.tight_layout()
            plt.savefig("../data/images/optimum" + datetime.datetime.now().strftime("%H%M") + ".png")
            if show_graph:
                plt.show()
            plt.close()

    def realize(self):
        # get values this hour
        # make settings
        exit()

    def run_task(self, task):
        old_stdout = sys.stdout
        log_file = open("data/log/" + task + datetime.datetime.now().strftime("%H%M") + ".log", "w")
        sys.stdout = log_file
        print(datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S'), ' : ', task, "\n")
        getattr(self, task)()
        sys.stdout = old_stdout
        log_file.close()

    '''
    def on_keyboard_press(self, key):
        char = sys.stdin()
            # Print the input value

        print('The input value is:%s' % char)

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

    def scheduler(self):
        while True:
            t = dt.datetime.now()
            next_min = t - dt.timedelta(minutes=-1, seconds=t.second, microseconds=t.microsecond)
            #            if not (self.stop_victron == None):
            #                if (next_min.hour == self.stop_victron.hour) and (next_min.minute == self.stop_victron.minute):
            #                    self.set_value(self.battery_options["entity set power feedin"], 0)
            #                    self.select_option(self.battery_options["entity set operating mode"], 'Uit')
            time.sleep((next_min - t).total_seconds())  # wacht tot hele minuut 0% cpu
            hour = next_min.hour
            minute = next_min.minute
            key1 = str(hour).zfill(2) + str(minute).zfill(2)
            key2 = "xx" + str(minute).zfill(2)  # ieder uur in dezelfde minuut vb xx15
            key3 = str(hour).zfill(2) + "xx"  # iedere minuut in een uur vb 02xx
            task = None
            if key1 in self.tasks:
                task = self.tasks[key1]
            elif key2 in self.tasks:
                task = self.tasks[key2]
            elif key3 in self.tasks:
                task = self.tasks[key3]
            if task != None:
                try:
                    self.run_task(task)
                except KeyboardInterrupt:
                    sys.exit()
                    pass
                except Exception as e:
                    print(e)
                    continue


def main():
    day_ah = DayAheadOpt("../data/options.json")
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        for arg in args:
            if arg.lower() == "debug":
                day_ah.debug = not day_ah.debug
                print("Debug = ", day_ah.debug)
                continue
            if arg.lower() == "calc":
                day_ah.calc_optimum(show_graph=True)
                continue
            if arg.lower() == "meteo":
                day_ah.get_meteo_data(True)
                continue
            if arg.lower() == "prices":
                day_ah.get_day_ahead_prices()
                continue
            if arg.lower() == "tibber":
                day_ah.get_tibber_data()
                continue
            if arg.lower() == "scheduler":
                day_ah.scheduler()
                continue
    else:
        day_ah.scheduler()


if __name__ == "__main__":
    main()
