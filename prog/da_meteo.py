import math
from requests import get
import json
import pandas as pd

from db_manager import DBmanagerObj
import graphs
import datetime

#import os, sys
#sys.path.append(os.path.abspath("../dalib"))
from da_config import Config


class Meteo:
    def __init__(self, config: Config, db_da: DBmanagerObj):
        self.config = config
        self.db_da = db_da
        self.meteoserver_key = config.get(["meteoserver-key"])
        self.latitude = config.get(["latitude"])
        self.longitude = config.get(["longitude"])
        self.solar = config.get(["solar"])
        self.bat = config.get(["battery"])

    @staticmethod
    def makerefmoment(moment):
        """
        :param moment: timestamp in utc
        :return: zelfde moment in 1972 in utc timestamp
        """
        mom = datetime.datetime.fromtimestamp(moment)
        date_ref = datetime.datetime(1972, mom.month, mom.day, mom.hour, 30, 0)
        return datetime.datetime.timestamp(date_ref)

    @staticmethod
    def direct_radiation_factor(hcol: float, acol: float, hzon: float, azon: float) -> float:
        """
        berekent de omrekenfacor van directe zon straling op het collectorvlak
        alle parameters in radialen
        :param hcol: helling van de collector: 0 = horizontaal, 0.5 pi verticaal
        :param acol: azimuth van de collector: 0 = zuid , -0,5 pi = oost, +0,5 pi = west
        :param hzon: hoogte van de zon, 0 = horizontaal, 0.5 pi verticaal
        :param azon: azimuth van de zon 0 = zuid , -0,5 pi = oost, +0,5 pi = west
        :return: de omrekenfactor
        """
        if hzon <= 0:
            return 0
        else:
            return max(0.0, (math.cos(hcol) * math.sin(hzon) + math.sin(hcol) * math.cos(hzon) * math.cos(
                acol - azon))) / math.sin(hzon)

    def sun_position(self, utc_time):
        """
        berekent postie van de zon op tijdstip time op coord. noorderbreedte en oosterlengte
        :param utc_time: timestamp in utc seconds
        :return: een array met positie van de zon hoogte(h) (elevatie) en azimuth(A) in radialen
        """
        # param NB: latitude: noorderbreed in graden
        # param OL: longitude: oosterlengte in graden

        jd = (float(utc_time) / 86400.0) + 2440587.5
        delta_j = jd - 2451545  # J - J2000
        m_deg = (357.5291 + 0.98560028 * delta_j) % 360  # in graden
        m_rad = math.radians(m_deg)  # in radialen
        c_aarde = 1.9148 * math.sin(m_rad) + 0.02 * math.sin(2 * m_rad) + 0.0003 * math.sin(3 * m_rad)  # in graden
        lamda_zon_deg = (m_deg + 102.9372 + c_aarde + 180) % 360  # in graden
        lamda_zon_rad = math.radians(lamda_zon_deg)

        alfa_zon = lamda_zon_deg - 2.468 * math.sin(2 * lamda_zon_rad) + 0.053 * math.sin(
            4 * lamda_zon_rad) - 0.0014 * math.sin(6 * lamda_zon_rad)  # in graden
        delta_zon = 22.8008 * math.sin(lamda_zon_rad) + 0.5999 * pow(math.sin(lamda_zon_rad), 3) + 0.0493 * pow(
            math.sin(lamda_zon_rad), 5)
        delta_zon_rad = math.radians(delta_zon)
        noorder_breedte = self.latitude
        ooster_lengte = self.longitude
        # wester_lengte_rad = math.radians(-ooster_lengte)
        noorder_breedte_rad = math.radians(noorder_breedte)

        theta = 280.16 + 360.9856235 * delta_j + ooster_lengte
        theta_deg = theta % 360
        # theta_rad = math.radians(theta_deg)

        h_deg = theta_deg - alfa_zon
        h_rad = math.radians(h_deg)

        # hoogte boven horizon
        h_rad = math.asin(math.sin(noorder_breedte_rad) * math.sin(delta_zon_rad)
                          + math.cos(noorder_breedte_rad) * math.cos(delta_zon_rad) * math.cos(h_rad))
        a_rad = math.atan2(math.sin(h_rad),
                           math.cos(h_rad) * math.sin(noorder_breedte_rad) - math.tan(delta_zon_rad) * math.cos(
                               noorder_breedte_rad))  # links of rechts van zuid
        result = {'h': h_rad, 'A': a_rad}
        return result

    def get_dif_rad_factor(self, utc_time):
        cor_utc_time = float(utc_time) + 1800  # een half uur verder voor berekenen van gem zonpositie in dat uur.
        sunpos = self.sun_position(cor_utc_time)  # 52 graden noorderbreedte, 5 graden oosterlengte
        sun_h = sunpos['h']  # hoogte boven horizon in rad
        if sun_h > 0:
            value = 360 * 1.37 * math.sin(sun_h)  # maximale theoretische straling op hor vlak
        else:
            value = 0.0
        return value

    def solar_rad(self, utc_time: float, radiation: float, h_col: float, a_col: float) -> float:
        """
        :param utc_time: utc tijd in sec
        :param radiation: globale straling in J/cm2
        :param h_col: hoogte van de collector in radialen
        :param a_col: azimuth van de collector in radialen
        :return: de straling (direct en diffuus) in J/cm2 op het vlak van de collector
        """
        if radiation <= 0:
            q_tot = 0
        elif radiation <= 5:
            q_tot = radiation
        else:
            sun_pos = self.sun_position(utc_time)
            dir_rad_factor = min(2.0, self.direct_radiation_factor(h_col, a_col, sun_pos['h'], sun_pos['A']))

            q_oz = self.get_dif_rad_factor(utc_time)  # maximale straling op horz.vlak

            if q_oz > 0:
                k_t = max(0.2, min(0.8, radiation / q_oz))
                q_dif0 = radiation * (1 - 1.12 * k_t)
            else:
                q_dif0 = radiation

            q_dir0 = radiation - q_dif0

            coshcol = math.cos(h_col)
            q_difc = q_dif0 * (1 + coshcol + 0.2 * (1 - coshcol)) / 2
            q_dirc = q_dir0 * dir_rad_factor
            q_tot = q_difc + q_dirc
        return q_tot

    def solar_rad_df(self, global_rad):
        """
        argumemten
            global_rad: df met tijden en globale straling (time, gr)
        berekent netto instraling op collector in J/cm2
        retouneert dataframe met (time, solar_rad)
        """
        # tilt: helling tov plat vlak in graden
        # orientation: orientatie oost = -90, zuid = 0, west = 90 in graden
        # zoek de eerste de beste pv installatie op
        solar = None
        if len(self.solar) > 0:
            solar = self.solar[0]
        else:
            for b in range(len(self.bat)):
                if len(self.bat[b]["solar"]) > 0:
                    solar = self.bat[b]["solar"][0]
        if solar != None:
            tilt = solar["tilt"]
            orientation = solar["orientation"]
        else:
            tilt = 45
            orientation = 0
        tilt = min(90, max(0, tilt))
        hcol = math.radians(tilt)
        acol = math.radians(orientation)
        global_rad['solar_rad'] = ''  # new column empty
        global_rad = global_rad.reset_index()  # make sure indexes pair with number of rows
        for row in global_rad.itertuples():
            utc_time = row.tijd
            radiation = float(row.gr)
            q_tot = self.solar_rad(float(utc_time), radiation, hcol, acol)
            global_rad.loc[(global_rad.tijd == utc_time), 'solar_rad']=q_tot
        return global_rad

    def get_meteo_data(self, show_graph=False):

        url = "https://data.meteoserver.nl/api/uurverwachting.php?lat=" + str(self.latitude) + \
              "&long=" + str(self.longitude) + "&key=" + self.meteoserver_key
        resp = get(url)
        # print (resp.text)
        json_object = json.loads(resp.text)
        data = json_object["data"]

        # for t in data:
        #  print(t["tijd"], t["tijd_nl"], t["gr"], t["temp"])
        # Use pandas.DataFrame.from_dict() to Convert JSON to DataFrame

        # Convert a List of dictionaries using from_records() method.
        df = pd.DataFrame.from_records(data)
        df = self.solar_rad_df(df)

        df1 = df[['tijd', 'tijd_nl', 'gr', 'temp', 'solar_rad']]
        print(df1)

        count =  0
        df_db = pd.DataFrame(columns=['time', 'code', 'value'])
        df1 = df1.reset_index()  # make sure indexes pair with number of rows
        for row in df1.itertuples():
            df_db.loc[df_db.shape[0]] = [row.tijd, 'gr', float(row.gr)]
            df_db.loc[df_db.shape[0]] = [row.tijd, 'temp', float(row.temp)]
            df_db.loc[df_db.shape[0]] = [row.tijd, 'solar_rad', float(row.solar_rad)]
            count += 1
            if count >= 48:
                break
        # print(df_db)

        self.db_da.savedata(df_db)
        graphs.make_graph_meteo(df1, file="../data/images/meteo" + datetime.datetime.now().strftime("%H%M") + ".png",
                                show=show_graph)

        '''
        url = "https://api.forecast.solar/estimate/watthours/"+str(self.latitude)+"/"+str(self.longitude)+"/45/5/5.5"
        resp = get(url)
        print (resp.text)
        json_object = json.loads(resp.text)
        data = json_object["result"]
        df_db = pd.DataFrame(columns = ['time', 'time_str', 'code', 'value'])
        last_hour = -1
        last_value = 0
        last_day = -1
        last_datetime_obj = None
        for time_str, pv_w in data.items():
            datetime_obj = dt.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            hour = datetime_obj.hour
            if hour == last_hour:
                hour = hour + 1
            day = datetime_obj.day
            if (day != last_day): # or (last_hour < hour-1):
                if last_day == -1:
                    for h in range(last_hour+1, hour):
                        time_h = dt.datetime(datetime_obj.year, datetime_obj.month, datetime_obj.day, h,0,0 )
                        time_utc = dt.datetime.timestamp(time_h) - 3600
                        df_db.loc[df_db.shape[0]] = [str(int(time_utc)), time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]
                else:
                    for h in range(last_hour + 1, 24):
                        time_h = dt.datetime(last_datetime_obj.year,last_datetime_obj.month,last_datetime_obj.day,h,0,0)
                        time_utc = dt.datetime.timestamp(time_h) - 3600
                        df_db.loc[df_db.shape[0]] = [str(int(time_utc)), time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]
                    for h in range(0, hour):
                        time_h = dt.datetime(datetime_obj.year, datetime_obj.month, datetime_obj.day, h, 0, 0)
                        time_utc = dt.datetime.timestamp(time_h) - 3600
                        df_db.loc[df_db.shape[0]] = [str(int(time_utc)), time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]
                    last_value = 0
            time_h = dt.datetime(datetime_obj.year, datetime_obj.month, datetime_obj.day, hour, 0, 0)
            time_utc = dt.datetime.timestamp(time_h) -3600
            df_db.loc[df_db.shape[0]] = [str(int(time_utc)), time_h.strftime("%Y-%m-%d %H:%M"), 'pv', pv_w - last_value]
            last_hour = hour
            last_value = pv_w
            last_day = day
            last_datetime_obj = datetime_obj
        for h in range(last_hour + 1, 24):
            time_h = dt.datetime(last_datetime_obj.year, last_datetime_obj.month, last_datetime_obj.day, h, 0, 0)
            time_utc = dt.datetime.timestamp(time_h) - 3600
            df_db.loc[df_db.shape[0]] = [str(int(time_utc)), time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]

        print(df_db)

#        graphs.make_graph_meteo(df_db, file = "../data/images/meteo" + datetime.datetime.now().strftime("%H%M") + ".png",
#                                show=show_graph)
        del df_db["time_str"]
        print(df_db)
        self.db_da.savedata(df_db)
        '''

    def calc_graaddagen(self, date : datetime.datetime=None, weighted : bool=False) -> float:
        """
        berekend gewogen met temperatuur grens van 16 oC
        :param date: de datum waarvoor de berekening wordt gevraagd
        als None: vandaag
        :param weighted : boolean, berekenen met (true) of zonder (false) weegfactor
        :return: berekende gewogen graaddagen
        """
        if date == None:
            date = datetime.datetime.combine(datetime.datetime.today(), datetime.datetime.min.time())
        date_utc = int(date.timestamp())
        sql_avg_temp = (
            "SELECT AVG(t1.`value`) avg_temp FROM "
                "(SELECT `time`, `value`,  from_unixtime(`time`) 'begin' "
                "FROM `values` , `variabel` "
                "WHERE `variabel`.`code` = 'temp' AND `values`.`variabel` = `variabel`.`id` AND time >= " + str(date_utc) + " "
                "ORDER BY `time` ASC LIMIT 24) t1 "
            )
        data = self.db_da.run_select_query(sql_avg_temp)
        avg_temp = float(data['avg_temp'].values[0])
        weight_factor = 1
        if weighted:
            mon = date.month
            if mon <= 2 or mon >= 11:
                weight_factor = 1.1
            elif mon >= 4 or mon <= 9:
                weight_factor = 0.9
        if avg_temp >= 16:
            result = 0
        else:
            result = weight_factor * (16 - avg_temp)
        return result

    def calc_solar_rad(self, solar_opt:dict, utc_time:int, global_rad:float)->float:
        '''
        :param solar_opt: definitie van paneel met
            tilt: helling tov plat vlak in graden, 0 = vlak (horizontaal), 90 = verticaal
            orienation: orientatie oost = -90, zuid = 0, west = 90 in graden
        :param utc_time: utc tijd in seconden
        :param global_rad: globale straling in J/cm2
        :return: alle straling op paneel J/cm2
        '''
        # tilt:
        # orientation: orientatie oost = -90, zuid = 0, west = 90 in graden
        tilt = solar_opt["tilt"]
        tilt = min(90, max(0, tilt))
        hcol = math.radians(tilt)
        orientation = solar_opt["orientation"]
        acol = math.radians(orientation)
        radiation = global_rad
        q_tot = self.solar_rad(float(utc_time), global_rad, hcol, acol)
        return q_tot

