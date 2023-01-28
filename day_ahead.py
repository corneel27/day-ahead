import datetime as dt
from requests import post
import hassapi as hass
import csv
from pprint import pprint
import sys
from mip import Model, xsum, minimize, BINARY, CONTINUOUS
import time
import numpy
from utils import *
from da_config import *
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
        self.prices = DA_Prices(self.config, self.db_da)
        self.tibber_options = self.config.get(["tibber"])
        self.boiler_options = self.config.get(["boiler"])
        self.battery_options = self.config.get(["battery"])
        self.prices_options = self.config.get(["prices"])
        self.ev_options = self.config.get(["electric vehicle"])
        self.heating_options = self.config.get(["heating"])
        self.tasks = self.config.get(["scheduler"])

    def get_meteo_data(self, show_graph: bool = False):
        self.meteo.get_meteo_data(show_graph)

    def get_day_ahead_prices(self):
        self.prices.get_prices()

    def get_consumption(self, start, until=dt.datetime.now()):
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

        result = {"consumption" : consumption, "production": production}
        print (result)
        return (result)

    def get_tibber_data(self):
        def get_datetime_from_str(s):
            result = dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")  # "2022-09-01T01:00:00.000+02:00"
            return result

        url = self.tibber_options["api url"]
        headers = {
            "Authorization": "Bearer " + self.tibber_options["api_token"],
            "content-type": "application/json",
        }
        now_ts = latest_ts = math.ceil(datetime.datetime.now().timestamp()/3600)*3600
        for cat in ['cons', 'prod']:
            sql_latest_ts = (
                "SELECT t1.time, from_unixtime(t1.`time`) 'begin', t1.value "
                "FROM `values` t1, `variabel` v1 "
                "WHERE v1.`code` = '"+cat+"' and v1.id = t1.variabel and 1 <> "
                    "(SELECT COUNT( *) "
                    "FROM `values` t2, `variabel` v2 "
                    "WHERE v2.`code` = '"+cat+"' AND v2.id = t2.variabel AND t1.time + 3600 = t2.time);")
            data = self.db_da.run_select_query(sql_latest_ts)
            latest = data['time'].values[0]
            latest_ts = min (latest_ts, latest)
        count = math.ceil((now_ts - latest_ts)/3600)
        print("Tibber data present tot en met:", str(datetime.datetime.fromtimestamp(latest_ts)))
        if count < 24:
            print("Er worden geen data opgehaald")
            return
        query = '{ ' \
                '"query": ' \
                    ' "{ ' \
                    '   viewer { ' \
                    '     homes { ' \
                    '      production(resolution: HOURLY, last: '+str(count)+') { ' \
                    '        nodes { ' \
                    '          from ' \
                    '          profit ' \
                    '          production ' \
                    '        } ' \
                    '      } ' \
                    '    consumption(resolution: HOURLY, last: '+str(count)+') { ' \
                    '        nodes { ' \
                    '          from ' \
                    '          cost ' \
                    '          consumption ' \
                    '        } ' \
                    '      } ' \
                    '    } ' \
                    '  } ' \
                    '}" ' \
                '}'

        # print(query)
        resp = post (url, headers=headers, data=query)
        tibber_dict = json.loads(resp.text)
        if self.debug:
            print(tibber_dict)
        production_nodes = tibber_dict['data']['viewer']['homes'][0]['production']['nodes']
        consumption_nodes = tibber_dict['data']['viewer']['homes'][0]['consumption']['nodes']
        tibber_df = pd.DataFrame(columns=['time', 'code', 'value'])
        code = "prod"
        for node in production_nodes:
            if not(node["production"] is None):
                time_stamp = str(int(get_datetime_from_str(node['from']).timestamp()))
                value = float(node["production"])
                print(node, time_stamp, value)
                tibber_df.loc[tibber_df.shape[0]] = [time_stamp, code, value]
        code = "cons"
        for node in consumption_nodes:
            if not (node["consumption"] is None):
                timest = str(int(get_datetime_from_str(node['from']).timestamp()))
                value = float(node["consumption"])
                print(node, timest, value)
                tibber_df.loc[tibber_df.shape[0]] = [timest, code, value]
        print (tibber_df)
        self.db_da.savedata(tibber_df)

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

        global boiler_temp
        now_dt = int(dt.datetime.now().timestamp())

        offset = 0  # offset in uren
        now_h = int(3600 * (math.floor(now_dt / 3600)) + offset * 3600)
        fraction_first_hour = 1 - (now_dt - now_h) / 3600

        prog_data = self.db_da.getPrognoseData(start=now_h, end=None)
        # start = dt.datetime.timestamp(dt.datetime.strptime("2022-05-27", "%Y-%m-%d"))
        # end = dt.datetime.timestamp(dt.datetime.strptime("2022-05-29", "%Y-%m-%d"))
        # prog_data = db_da.getPrognoseData(start, end)
        print(prog_data)

        print("Graaddagen: ", self.meteo.calc_graaddagen())

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
        taxes_l = self.prices_options["energy taxes delivery"]  # eb + ode levering
        # eb_l = 0.12955
        ol_l = self.prices_options["cost supplier delivery"]
        # ol_l = 0.002
        taxes_t = self.prices_options["energy taxes redelivery"]  # eb+ode teruglevering
        # eb_t = 0.12955
        # eb_t = 0
        # ode_t = 0
        ol_t = self.prices_options["cost supplier redelivery"]
        # ol_t = 0 #-0.011
        btw = self.prices_options["vat"]
        # btw = 0.09

        # greenchoice prijzen 1e halfjaar 2022
        gc_p_low = self.prices_options['regular low']
        gc_p_high = self.prices_options['regular high']
        pl = []  # prijs levering day_ahead
        pt = []  # prijs teruglevering day_ahead
        pl_avg = [] # prijs levering day_ahead gemiddeld
        pt_notax = []  # prijs teruglevering day ahead zonder taxes
        prog_data = prog_data.reset_index()  # make sure indexes pair with number of rows
        for row in prog_data.itertuples():
            jaar = str(row.tijd.year)
            price_l = (row.da_price + taxes_l[jaar] + ol_l) * (1 + btw[jaar]/100)
            price_t = (row.da_price + taxes_t[jaar] + ol_t) * (1 + btw[jaar]/100)
            pl.append(price_l)
            pt.append(price_t)
            price_t_notax = (row.da_price + ol_t)
            pt_notax.append(price_t_notax)

        U = len(pl)
        if U>=24:
            p_avg = sum(pl) / U  # max(pl) #
        else:
            p_avg = (calc_da_avg() + taxes_l["2023"] + ol_l) * (1 + btw["2023"]/100)
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
        pv_factor = self.config.get(["solar", "yield"])

        b_l = []  # basislast verbruik
        uur = []  # hulparray met uren
        time = []
        ts = []
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
            time.append(dtime)
            b_l.append(base_cons[hour])
            if first_hour:
                ts.append(now_dt)
                hour_fraction.append(fraction_first_hour)
                pv.append(row.pv_rad * pv_factor * fraction_first_hour)
            else:
                ts.append(row.time)
                hour_fraction.append(1)
                pv.append(row.pv_rad * pv_factor)
            jaar = str(dtime.year)
            if is_laagtarief(dt.datetime(dtime.year, dtime.month, dtime.day, hour), self.prices_options["switch to low"]):
                p_grl.append((gc_p_low + taxes_l[jaar]) * (1 + btw[jaar]/100))
                p_grt.append((gc_p_low + taxes_t[jaar]) * (1 + btw[jaar]/100))
            else:
                p_grl.append((gc_p_high + taxes_l[jaar]) * (1 + btw[jaar]/100))
                p_grt.append((gc_p_high + taxes_t[jaar]) * (1 + btw[jaar]/100))
            first_hour = False

        # volledig salderen?
        salderen = self.prices_options['tax refund'] == "True"
        last_invoice = dt.datetime.strptime(self.prices_options['last invoice'], "%d-%m-%Y")
        cons_data_history = self.get_consumption(last_invoice, dt.datetime.today())
        if not salderen:
            salderen = cons_data_history["production"] < cons_data_history["consumption"]
        if salderen:
            print ("all taxes refund")
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
        #                          accu
        ##############################################################
        # accu capaciteit
        # 2 batterijen 50V 280Ah
        ac = float(self.battery_options["capacity"])  # 2 * 50 * 280/1000 #=28 kWh
        one_soc = ac / 100  # 1% van 28 kWh = 0,28 kWh

        # accu load per uur
        accu_in = [model.add_var(var_type=CONTINUOUS, lb=0,
                                 ub=hour_fraction[u] * float(self.battery_options["max charge power"])) for u in
                   range(U)]
        accu_out = [model.add_var(var_type=CONTINUOUS, lb=0,
                                  ub=hour_fraction[u] * float(self.battery_options["max discharge power"])) for u in
                    range(U)]
        kwh_cycle_cost = self.battery_options["cycle cost"]
        # kwh_cycle_cost = (cycle_cost/( 2 * ac) ) / ((self.battery_options["upper limit"] - self.battery_options["lower limit"]) / 100)
        # print ("cycl cost: ", kwh_cycle_cost, " eur/kWh")

        # state of charge
        # start soc
        start_soc_str = self.get_state(self.battery_options["entity actual level"]).state
        if start_soc_str.lower() == "unavailable":
            start_soc = 50
        else:
            start_soc = float(start_soc_str)
        opt_low_level = float(self.battery_options["optimal lower level"])

        soc = [model.add_var(var_type=CONTINUOUS, lb=min(start_soc, float(self.battery_options["lower limit"])),
                             ub=max(start_soc, float(self.battery_options["upper limit"]))) for u in range(U + 1)]
        soc_low = [model.add_var(var_type=CONTINUOUS, lb=min(start_soc, float(self.battery_options["lower limit"])),
                             ub=opt_low_level) for u in range(U + 1)]
        soc_mid = [model.add_var(var_type=CONTINUOUS, lb=0,
                             ub=-opt_low_level+max(start_soc, float(self.battery_options["upper limit"]))) for u in range(U + 1)]
        for u in range(U + 1):
            model += soc[u] == soc_low[u] + soc_mid[u]

        model += soc[0] == start_soc
        model += soc[U] >= opt_low_level/2
        eff_charge = float(self.battery_options["charge efficiency"])  # fractie van 1
        eff_discharge = float(self.battery_options["discharge efficiency"])  # fractie van 1
        for u in range(U):
            model += soc[u + 1] == soc[u] + accu_in[u] * eff_charge / one_soc - (accu_out[u] / eff_discharge) / one_soc

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
        boiler_end = int(min(U - 1, max(0, int((boiler_act_temp - boiler_ondergrens) / boiler_cooling)))) #(41-40)/0.4=2.5

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
                needed_elec[u] = 0.9 #needed_heat / cop_boiler  # kWh
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
        if ev_plugged_in and (ev_position == "home") and (wished_level > actual_soc) and ((time[U - 1] + dt.timedelta(hours=1)) >= ready):
            for u in range(U):
                if (time[u] + dt.timedelta(hours=1)) >= ready:
                    ready_index = u
                    break

            print("ev klaar om: ", (1 + uur[ready_index]), "uur")  # ready index =laatste uur waarin wordt geladen
            hours_needed = math.ceil(time_needed)  # hele uren
            charger_on = [model.add_var(var_type=BINARY) for u in range(U)]
            c_ev = [model.add_var(var_type=CONTINUOUS, lb=0, ub=max_power * hour_fraction[u]) for u in
                    range(U)]  # consumption charger
            max_beschikbaar = 0
            for u in range(ready_index+1):
                model += c_ev[u] <= charger_on[u] * hour_fraction[u] * max_power
                max_beschikbaar += hour_fraction[u] * max_power
            for u in range(ready_index+1, U):
                model += charger_on[u] == 0
                model += c_ev[u] == 0
            model += xsum(charger_on[j] for j in range(ready_index+1)) == hours_needed
            model += xsum(c_ev[u] for u in range(ready_index+1)) == min(max_beschikbaar, energy_needed)
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
        # minimaal 6 kW terugleveren max 6 kW leveren
        # levering
        c_l = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]
        # teruglevering
        c_t_total = [model.add_var(var_type=CONTINUOUS, lb=0, ub=20) for u in range(U)]
        c_t_w_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]
        c_l_on = [model.add_var(var_type=BINARY) for u in range(U)]
        c_t_on = [model.add_var(var_type=BINARY) for u in range(U)]

        # salderen == True
        if salderen:
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=0) for u in range(U)]
        else:
            #alles wat meer wordt teruggeleverd dan geleverd (c_t_no_tax) wordt niet gesaldeerd (geen belasting terug): tarief pt_notax
            c_t_no_tax = [model.add_var(var_type=CONTINUOUS, lb=0, ub=10) for u in range(U)]

            if U>24:
                u_end = U-24
            else:
                u_end = U

            if (production_today - consumption_today) > ((u_end - 1 + fraction_first_hour) * float(self.battery_options["max charge power"])):
                marge = production_today - consumption_today
            else:
                marge = 0
            # voor vandaag
            model += (xsum(c_t_w_tax[u] for u in range(u_end)) + production_today) <= \
                     (xsum(c_l[u] for u in range(u_end)) + consumption_today + marge)
            if u_end < U:
                #morgen
                model += xsum(c_t_w_tax[u] for u in range(u_end,U)) <= xsum(c_l[u] for u in range(u_end,U))

        for u in range(U):
            model += c_t_total[u] == c_t_w_tax[u] + c_t_no_tax[u]
            model += c_l[u] <= c_l_on[u] * 10
            model += c_t_total[u] <= c_t_on[u] * 20
            model += c_l_on[u] + c_t_on[u] <= 1

        for u in range(U):
            model += c_l[u] == c_t_total[u] + b_l[u] + accu_in[u] + c_b[u] + c_ev[u] - pv[u] - accu_out[u]

        # kosten optimalisering
        model.objective = minimize(
            xsum(c_l[u] * pl[u] - c_t_w_tax[u] * pt[u] - c_t_no_tax[u] * pt_notax[u] + (accu_in[u] + accu_out[u]) * kwh_cycle_cost + (opt_low_level - soc_low[u])*0.0025 for u in range(U))
            + (soc_mid[0] - soc_mid[U]) * one_soc * eff_discharge * p_avg  # waarde opslag accu
            # + (boiler_temp[U] - boiler_ondergrens) * (spec_heat_boiler/(3600 * cop_boiler)) * p_avg # waarde energie boiler
        )
        '''
        #optimize minimaliseer levering
        model.objective = minimize(xsum(c_l[u] for u in range(U)) )
        '''

        # optimizing
        model.optimize()

        if model.num_solutions:
            old_cost_gc = 0
            old_cost_da = 0
            sum_old_cons = 0
            org_l = []
            org_t = []
            for u in range(U):
                netto = b_l[u] + c_b[u].x + c_ev[u].x - pv[u]
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
                saldeer_corr_gc = -sum_old_cons * (sum(p_grt)/len(p_grt) - 0.11)
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
            # print ("uur", " a_in", " a_out", "  soc1", " con_l"," con_t", " bas_l", "  boil", "    ev", "    pv"," kos_l", " kos_t" )
            d_f = pd.DataFrame(
                columns=['uur', 'accu_in', 'accu_out', 'soc', 'con_l', 'c_t_t',  'c_t_n', 'bas_l', 'boil', 'ev', 'pv', 'kos_l',
                         'kos_t', 'k_t_n', 'b_tem'])
            for u in range(U):
                d_f.loc[d_f.shape[0]] = [uur[u], accu_in[u].x, accu_out[u].x, soc[u + 1].x, c_l[u].x, c_t_w_tax[u].x, c_t_no_tax[u].x, b_l[u],
                                         c_b[u].x, c_ev[u].x, pv[u], c_l[u].x * pl[u], -c_t_total[u].x * pt[u], -c_t_no_tax[u].x * pt_notax[u],
                                         boiler_temp[u + 1].x]
                '''
                print ("{:2}".format(uur[u]), "{:6.2f}".format(accu_in[u].x), "{:6.2f}".format(accu_out[u].x),
                       "{:6.2f}".format(soc[u+1].x), "{:6.2f}".format(c_l[u].x), "{:6.2f}".format(c_t[u].x), "{:6.2f}".format(b_l[u]),
                       "{:6.2f}".format(c_b[u].x), "{:6.2f}".format(c_ev[u].x),
                       "{:6.2f}".format(pv[u]), "{:6.2f}".format(c_l[u].x*pl[u]), "{:6.2f}".format(-c_t[u].x*pt[u]))
                '''
            sys.stdout.write('\n')
            pd.options.display.float_format = '{:6.2f}'.format
            d_f.loc['total'] = d_f.select_dtypes(numpy.number).sum()
            print(d_f.to_string())
            print("Winst: ", "{:6.2f}".format(old_cost_gc - model.objective_value))

            if not self.debug:
                # bij debug niet opslaan en ook niet activeren
                # berekende prognose opslaan in db
                df_db = pd.DataFrame(columns=['time', 'code', 'value'])
                for u in range(U):
                    df_db.loc[df_db.shape[0]] = [str(ts[u]), 'accu', -accu_in[u].x + accu_out[u].x]
                    df_db.loc[df_db.shape[0]] = [str(ts[u]), 'soc', soc[u + 1].x]
                    df_db.loc[df_db.shape[0]] = [str(ts[u]), 'grid', -c_t_total[u].x + c_l[u].x]
                    df_db.loc[df_db.shape[0]] = [str(ts[u]), 'boiler', -c_b[u].x]
                    df_db.loc[df_db.shape[0]] = [str(ts[u]), 'ev', -c_ev[u].x]
                # print(df_db)
                # geeft integriteitsfouten
                # self.db_da.savedata(df_db)

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
                if ev_position == "home" and ev_plugged_in :
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
                netto_vermogen = int(1000 * ((accu_in[0].x - accu_out[0].x) / fraction_first_hour))
                minimum_power = self.battery_options["minimum power"]
                if abs(netto_vermogen) <= 20:
                    netto_vermogen = 0
                    new_state = "Uit"
                    stop_victron = None
                    balance = False
                elif abs(c_l[0].x - c_t_w_tax[0].x - c_t_no_tax[0].x) <= 0.01 :
                    new_state = "Aan"
                    balance = True
                    stop_victron = None
                elif abs(netto_vermogen) < minimum_power:
                    new_state = "Aan"
                    balance = False
                    new_ts = now_dt.timestamp() + (abs(netto_vermogen)/minimum_power)*3600
                    stop_victron = datetime.datetime.fromtimestamp(int(new_ts))
                    if netto_vermogen > 0:
                        netto_vermogen = minimum_power
                    else:
                        netto_vermogen = -minimum_power
                else:
                    new_state = "Aan"
                    balance = False
                    stop_victron = None

                self.set_value(self.battery_options["entity set power feedin"], netto_vermogen)
                self.select_option(self.battery_options["entity set operating mode"], new_state)
                if balance:
                    self.set_state(self.battery_options["entity balance switch"], 'on')
                else:
                    self.set_state(self.battery_options["entity balance switch"], 'off')
                print("Netto vermogen uit grid: ", netto_vermogen, " W")
                print("Balanceren: ", balance)
                if stop_victron == None:
                    datetime_str = "2000-01-01 00:00:00"
                else:
                    print("tot: ", stop_victron)
                    datetime_str = stop_victron.strftime('%Y-%m-%d %H:%M')
                helper_id =self.battery_options["entity stop victron"]
                self.call_service("set_datetime", entity_id=helper_id, datetime=datetime_str)

                #heating
                entity_curve_adjustment = self.heating_options["entity adjust heating curve"]
                old_adjustment = float(self.get_state(entity_curve_adjustment).state)
                #adjustment factor (K/%) bijv 0.4 K/10% = 0.04
                adjustment_factor = self.heating_options["adjustment factor"]
                adjustment = calc_adjustment_heatcurve(pl[0], p_avg, adjustment_factor, old_adjustment)
                '''
                if pl[0] < p_avg * 0.9:
                    adjustment = 0.5
                elif pl[0] > p_avg * 1.1:
                    #in stapjes van 0.5 K verlagen
                    if old_adjustment == 0.5:
                        adjustment = 0
                    else:
                        adjustment = -0.5
                else:
                    adjustment = 0
                '''
                print("Aanpassing stooklijn: ", adjustment)
                self.set_value(entity_curve_adjustment, adjustment)

            # graphs
            accu_in_n = []
            accu_out_p = []
            c_t_n = []
            base_n = []
            boiler_n = []
            ev_n = []
            cons_n = []
            c_l_p = []
            soc_p = []
            pv_p = []
            for u in range(U):
                c_t_n.append(-c_t_total[u].x)
                c_l_p.append(c_l[u].x)
                accu_in_n.append(-accu_in[u].x)
                accu_out_p.append(accu_out[u].x)
                base_n.append(-b_l[u])
                boiler_n.append(- c_b[u].x)
                ev_n.append(-c_ev[u].x)
                soc_p.append(soc[u].x)
                pv_p.append(pv[u])

            import matplotlib.ticker as ticker
            import matplotlib.pyplot as plt
            import numpy as np
            fig, axis = plt.subplots(figsize=(8, 9), nrows=3)  # , sharex= True)
            ind = np.arange(U)
            axis[0].bar(ind, np.array(org_l), label='Levering', color='#00bfff')
            axis[0].bar(ind, np.array(pv_p), bottom=np.array(org_l), label='PV', color='green')
            axis[0].bar(ind, np.array(base_n), label="Overig verbr.", color='#f1a603')
            axis[0].bar(ind, np.array(boiler_n), bottom=np.array(base_n), label="Boiler", color='#ffef00')
            axis[0].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n), label="EV laden",
                        color='#fefbbd')
            axis[0].bar(ind, np.array(org_t), bottom=np.array(base_n) + np.array(boiler_n) + np.array(ev_n),
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
            axis[1].bar(ind, np.array(boiler_n), bottom=np.array(base_n), label="Boiler", color='#ffef00')
            axis[1].bar(ind, np.array(ev_n), bottom=np.array(base_n) + np.array(boiler_n), label="EV laden",
                        color='#fefbbd')
            axis[1].bar(ind, np.array(c_t_n), bottom=np.array(base_n) + np.array(boiler_n) + np.array(ev_n),
                        label="Teruglev.", color='#0080ff')
            axis[1].bar(ind, np.array(accu_in_n),
                        bottom=np.array(base_n) + np.array(boiler_n) + np.array(ev_n) + np.array(c_t_n),
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
            plt.savefig("images/optimum" + datetime.datetime.now().strftime("%H%M") + ".png")
            if show_graph:
                plt.show()
            plt.close()

    def realize(self):
        # get values this hour
        # make settings
        exit()

    def run_task(self, task):
        old_stdout = sys.stdout
        log_file = open("log/" + task + datetime.datetime.now().strftime("%H%M") + ".log", "w")
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
    day_ah = DayAheadOpt("options.json")
    if len(sys.argv)>1:
        args = sys.argv[1:]
        for arg in args:
            if arg.lower() == "debug":
                day_ah.debug = not day_ah.debug
                print ("Debug = ", day_ah.debug)
                continue
            if arg.lower() == "calc":
                day_ah.calc_optimum(show_graph=True)
                continue
            if arg.lower() == "meteo":
                day_ah.meteo.get_meteo_data(True)
                continue
            if arg.lower() == "prices":
                day_ah.prices.get_prices()
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
