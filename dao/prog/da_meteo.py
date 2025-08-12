import datetime
import json
import math
import logging
import pandas as pd
import pytz
import ephem
from requests import get
import matplotlib.pyplot as plt
from dao.prog.da_graph import GraphBuilder
from dao.prog.da_config import Config
from dao.prog.db_manager import DBmanagerObj
from sqlalchemy import Table, select, func, and_


# noinspection PyUnresolvedReferences
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
    def direct_radiation_factor(
        hcol: float, acol: float, hzon: float, azon: float
    ) -> float:
        """
        berekent de omrekenfacor van directe zon straling op het collectorvlak
        alle parameters in radialen
        :param hcol: helling van de collector: 0 = horizontaal, 0.5 pi verticaal
        :param acol: azimuth van de collector: 0 = zuid, -0,5 pi = oost, +0,5 pi = west
        :param hzon: hoogte van de zon, 0 = horizontaal, 0.5 pi verticaal
        :param azon: azimuth van de zon 0 = zuid, -0,5 pi = oost, +0,5 pi = west
        :return: de omrekenfactor
        """
        if hzon <= 0:
            return 0
        else:
            return max(
                0.0,
                (
                    math.cos(hcol) * math.sin(hzon)
                    + math.sin(hcol) * math.cos(hzon) * math.cos(acol - azon)
                ),
            ) / math.sin(hzon)

    def sun_position(self, utc_time):
        """
        Berekent postie van de zon op tijdstip 'time' op coordinaten noorderbreedte en oosterlengte
        :param utc_time: timestamp in utc seconds
        :return: een array met positie van de zon hoogte(h) (elevatie) en azimuth(A) in radialen
        """
        # param nb: latitude: noorderbreed in graden
        # param ol: longitude: oosterlengte in graden
        """
        # oude methode

        jd = (float(utc_time) / 86400.0) + 2440587.5
        delta_j = jd - 2451545  # J - J2000
        m_deg = (357.5291 + 0.98560028 * delta_j) % 360  # in graden
        m_rad = math.radians(m_deg)  # in radialen
        c_aarde = 1.9148 * math.sin(m_rad) + 0.02 * math.sin(2 * m_rad) + \
            0.0003 * math.sin(3 * m_rad)  # in graden
        c_aarde = math.degrees(c_aarde)
        lamda_zon_deg = (m_deg + 102.9372 + c_aarde + 180) % 360  # in graden
        lamda_zon_rad = math.radians(lamda_zon_deg)

        alfa_zon = lamda_zon_deg - 2.468 * math.sin(2 * lamda_zon_rad) + 0.053 * math.sin(
            4 * lamda_zon_rad) - 0.0014 * math.sin(6 * lamda_zon_rad)  # in graden
        delta_zon = 22.8008 * math.sin(lamda_zon_rad) + 0.5999 * pow(math.sin(lamda_zon_rad), 3) 
                    + 0.0493 * pow(math.sin(lamda_zon_rad), 5)
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
                          + math.cos(noorder_breedte_rad) * math.cos(delta_zon_rad) * 
                          math.cos(h_rad))
        a_rad = math.atan2(math.sin(h_rad),
                           math.cos(h_rad) * math.sin(noorder_breedte_rad) - 
                           math.tan(delta_zon_rad) * math.cos(noorder_breedte_rad))  
                           # links of rechts van zuid
        result = {'h': h_rad, 'A': a_rad}

        # tot hier oude methode
        """
        # vanaf hier nieuwe methode
        """
   
        Declinatie en uurhoek
        De in de afbeelding over deklinatie en uurhoek getekende hoeken zoals u en d leggen 
        de stralingsrichting vast. 
        Op iedere datum geldt: d = constant. Deze constante kan op de n- de dag van het jaar 
        met grote nauwkeurigheid 
        worden berekend met behulp van formule 1:
        d = 23,44° sin {360°(284 + n)/365} (1)
        Eveneens op iedere datum geldt, dat:
        u = t x 15° (2)
        met t gelijk aan de tijd in uren volgens Z.T. Met gehulp van (1) en (2) kan nu de 
        stralingsrichting worden 
        gevonden op ieder gewenst tijdstip op iedere gewenste datum.

        Azimut en zonshoogte
        De stralingsrichting is ook vast te leggen met behulp van de hoeken a en h. Zie de figuur 
        over Azimut en  
        zonshoogte. In appendix A is afgeleid, hoe deze hoeken kunnen worden geschreven als functie 
        van de zojuist 
        genoemde hoeken u en d. Het blijkt handiger om h te schrijven als functie van u en d en 
        om a te schrijven als 
        functie van u, d en h. Gevonden wordt:
        h = arcsin (sin ф sin d – cos ф cos d cos u) (3)
        a = arcsin { (cos d sin u) / cos h } (4)
        De hoek ф is gelijk aan de breedtegraad van de plaats op aarde, waar a en h moeten 
        worden bepaald. 
        De waarden, die a en h aannemen, zijn nu dus plaatsafhankelijk. 
        """
        """
        dt = datetime.datetime.fromtimestamp(utc_time)
        dt_start = datetime.datetime(dt.year,1,1)
        dif = dt - dt_start
        n = dif.days
        d = math.radians(23.44 *  math.sin(math.radians(360*(284 + n) / 365))) # declinatie 
        in radialen
        dtz = datetime.datetime.fromtimestamp(utc_time, tz=pytz.utc)
        t = dtz.hour
        u = t * math.radians(15) #uurhoek in radialen
        br = math.radians(self.latitude) # breedtegraad
        h = math.asin(math.sin(br) * math.sin(d) - math.cos(br) * math.cos(d) * math.cos(u))
        a = math.asin((math.cos(d) * math.sin(u)) / math.cos(h))
        h_degrees = math.degrees(h)
        a_degrees = math.degrees(a)
        result = {'d': math.degrees(d), 'u': math.degrees(u), 'h': h, 'A': a}
        """

        observer = ephem.Observer()
        observer.lat = math.radians(self.latitude)  # breedtegraad
        observer.lon = math.radians(self.longitude)
        dtz = datetime.datetime.fromtimestamp(utc_time, tz=pytz.utc)
        observer.date = dtz.strftime("%Y-%m-%d %H:%M:%S.%f")  # '2023-09-19 12:00:00'
        sun = ephem.Sun(observer)
        result = {"h": sun.alt * 1.0, "A": (sun.az + math.pi) % (2 * math.pi)}
        return result

    def get_dif_rad_factor(self, utc_time):
        # een half uur verder voor berekenen van gem zonpositie in dat uur.
        cor_utc_time = float(utc_time) + 1800
        # 52 graden noorderbreedte, 5 graden oosterlengte
        sunpos = self.sun_position(cor_utc_time)
        sun_h = sunpos["h"]  # hoogte boven horizon in rad
        if sun_h > 0:
            # maximale theoretische straling op hor vlak
            value = 360 * 1.37 * math.sin(sun_h)
        else:
            value = 0.0
        return value

    def solar_rad(
        self, utc_time: float, radiation: float, h_col: float, a_col: float
    ) -> float:
        """
        :param utc_time: utc tijd in sec
        :param radiation: globale straling in J/cm²
        :param h_col: hoogte van de collector in radialen
        :param a_col: azimuth van de collector in radialen
        :return: de straling (direct en diffuus) in J/cm² op het vlak van de collector
        """
        if radiation <= 0:
            q_tot = 0
        elif radiation <= 5:
            q_tot = radiation
        else:
            sun_pos = self.sun_position(utc_time)
            dir_rad_factor = min(
                2.0,
                self.direct_radiation_factor(h_col, a_col, sun_pos["h"], sun_pos["A"]),
            )

            # maximale straling op horz.vlak
            q_oz = self.get_dif_rad_factor(utc_time)

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
        # tilt: helling t.o.v. plat vlak in graden
        # orientation: orientatie oost = -90, zuid = 0, west = 90 in graden
        # zoekt de eerste de beste pv installatie op
        solar = None
        if len(self.solar) > 0:
            solar = self.solar[0]
            if "strings" in solar:
                solar = solar["strings"][0]
        else:
            for b in range(len(self.bat)):
                if len(self.bat[b]["solar"]) > 0:
                    solar = self.bat[b]["solar"][0]
                    if "strings" in solar:
                        solar = solar["strings"][0]
                    break
        if solar is None:
            tilt = 45
            orientation = 0
        else:
            tilt = solar["tilt"]
            orientation = solar["orientation"]
        tilt = min(90, max(0, tilt))
        hcol = math.radians(tilt)
        acol = math.radians(orientation)
        global_rad["solar_rad"] = ""  # new column empty
        # make sure indexes pair with number of rows
        global_rad = global_rad.reset_index()
        for row in global_rad.itertuples():
            utc_time = row.tijd
            radiation = float(row.gr)
            q_tot = self.solar_rad(int(utc_time) - 3600, radiation, hcol, acol)
            global_rad.loc[(global_rad.tijd == utc_time), "solar_rad"] = q_tot
        return global_rad

    def make_graph_meteo(self, df, file=None, show=False):
        df["uur"] = df["tijd_nl"].apply(lambda x: x[11:13])
        meteo_options = {
            "title": f"Opgehaalde meteodata vanaf {df.iloc[0, 2]}",
            "style": self.config.get(["graphics", "style"]),
            "graphs": [
                {
                    "vaxis": [{"title": "J/cm2"}, {"title": "°C"}],
                    "align_zeros": "True",
                    "series": [
                        {
                            "column": "gr",
                            "title": "Globale straling",
                            "type": "stacked",
                            "color": "blue",
                        },
                        {
                            "column": "temp",
                            "title": "Temperatuur",
                            "type": "line",
                            "color": "green",
                            "vaxis": "right",
                        },
                    ],
                }
            ],
            "haxis": {"values": "uur", "title": "uur"},
        }

        gb = GraphBuilder()
        plot = gb.build(df, meteo_options, show=show)
        if file is not None:
            plot.savefig(file)
        """
        plt.figure(figsize=(15, 10))
        df["gr"] = pd.to_numeric(df["gr"])
        x_axis = np.arange(len(df["tijd_nl"].values))
        plt.bar(x_axis - 0.1, df["gr"].values, width=0.7, label="global rad")
        # plt.bar(x_axis + 0.1, df["solar_rad"].values, width=0.2, label="netto rad")
        plt.xticks(x_axis + 0.1, df["tijd_nl"].values, rotation=45)
        if file is not None:
            plt.savefig(file)
        if show:
            plt.show()
        plt.close("all")
        return
        """

    def get_from_meteoserver(self, model: str) -> pd.DataFrame:
        parameters = (
            "?lat="
            + str(self.latitude)
            + "&long="
            + str(self.longitude)
            + "&key="
            + self.meteoserver_key
        )
        count = 0
        max_count = 1
        data = {}
        if model == "harmonie":
            url = "https://data.meteoserver.nl/api/uurverwachting.php"
        else:
            url = "https://data.meteoserver.nl/api/uurverwachting_gfs.php"
        while count <= max_count:
            resp = get(url + parameters)
            logging.debug(resp.text)
            json_object = {}
            try:
                json_object = json.loads(resp.text)
            except Exception as ex:
                logging.info(ex)
            if "data" in json_object:
                data = json_object["data"]
                break
            count += 1

        if count > max_count :
            return pd.DataFrame()

        df = pd.DataFrame.from_records(data)
        df = self.solar_rad_df(df)
        df1 = df[["tijd", "tijd_nl", "gr", "temp", "solar_rad"]]
        logging.info(f"Meteo data {model}: \n{df1.to_string(index=True)}")
        logging.info(f"Aantal meteorecords {model}: {len(df1)}")
        return df1

    def get_meteo_data(self, show_graph=False):
        df1 = self.get_from_meteoserver("harmonie")
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        count = len(df1)
        if count == 0:
            logging.error("No harmonie-data recieved from meteoserver")
        else:
            df1 = df1.reset_index()  # make sure indexes pair with number of rows
            for row in df1.itertuples():
                df_db.loc[df_db.shape[0]] = [
                    str(int(row.tijd)),
                    "gr",
                    float(row.gr),
                ]
                df_db.loc[df_db.shape[0]] = [
                    str(int(row.tijd)),
                    "temp",
                    float(row.temp),
                ]
                df_db.loc[df_db.shape[0]] = [
                    str(int(row.tijd)),
                    "solar_rad",
                    float(row.solar_rad),
                ]
        df2 = pd.DataFrame()
        if count < 96:
            df2 = self.get_from_meteoserver("gfs")
            len_df2 = len(df2)
            if len_df2 == 0:
                logging.error("No gfs-data recieved from meteoserver")
            else:
                for row in df2[count:].itertuples():
                    df_db.loc[df_db.shape[0]] = [
                        str(int(row.tijd)),
                        "gr",
                        float(row.gr),
                    ]
                    df_db.loc[df_db.shape[0]] = [
                        str(int(row.tijd)),
                        "temp",
                        float(row.temp),
                    ]
                    df_db.loc[df_db.shape[0]] = [
                        str(int(row.tijd)),
                        "solar_rad",
                        float(row.solar_rad),
                    ]
                    count += 1
                    if count >= 96:
                        break

        df_tostring = df_db
        df_tostring["tijd"] = df_tostring["time"].apply(
            lambda x: datetime.datetime.fromtimestamp(int(x)).strftime("%Y-%m-%d %H:%M")
        )
        logging.debug(f"Meteo data records \n{df_tostring.to_string(index=False)}")

        self.db_da.savedata(df_db)
        if len(df1) > 0:
            if len(df2) > len(df1):
                df_gr = pd.concat([df1, df2[len(df1):96]])
            else:
                df_gr = df1
        else:
            df_gr = df2[:96]

        if len(df_gr) > 0:
            style = self.config.get(["graphics", "style"], None, "default")
            plt.style.use(style)
            self.make_graph_meteo(
                df_gr,
                file="../data/images/meteo_"
                + datetime.datetime.now().strftime("%Y-%m-%d__%H-%M")
                + ".png",
                show=show_graph,
            )

        """
        url = "https://api.forecast.solar/estimate/watthours/"+str(self.latitude)+"/"
                +str(self.longitude)+"/45/5/5.5"
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
                        time_h = dt.datetime(datetime_obj.year, datetime_obj.month, 
                        datetime_obj.day, h,0,0 )
                        time_utc = dt.datetime.timestamp(time_h) - 3600
                        df_db.loc[df_db.shape[0]] = [str(int(time_utc)), 
                        time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]
                else:
                    for h in range(last_hour + 1, 24):
                        time_h = dt.datetime(last_datetime_obj.year,last_datetime_obj.month,
                        last_datetime_obj.day,h,0,0)
                        time_utc = dt.datetime.timestamp(time_h) - 3600
                        df_db.loc[df_db.shape[0]] = [str(int(time_utc)), 
                        time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]
                    for h in range(0, hour):
                        time_h = dt.datetime(datetime_obj.year, datetime_obj.month, 
                        datetime_obj.day, h, 0, 0)
                        time_utc = dt.datetime.timestamp(time_h) - 3600
                        df_db.loc[df_db.shape[0]] = [str(int(time_utc)), 
                        time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]
                    last_value = 0
            time_h = dt.datetime(datetime_obj.year, datetime_obj.month, d
            atetime_obj.day, hour, 0, 0)
            time_utc = dt.datetime.timestamp(time_h) -3600
            df_db.loc[df_db.shape[0]] = [str(int(time_utc)), time_h.strftime("%Y-%m-%d %H:%M"), 
            'pv', pv_w - last_value]
            last_hour = hour
            last_value = pv_w
            last_day = day
            last_datetime_obj = datetime_obj
        for h in range(last_hour + 1, 24):
            time_h = dt.datetime(last_datetime_obj.year, last_datetime_obj.month, 
            last_datetime_obj.day, h, 0, 0)
            time_utc = dt.datetime.timestamp(time_h) - 3600
            df_db.loc[df_db.shape[0]] = [str(int(time_utc)), 
            time_h.strftime("%Y-%m-%d %H:%M"), 'pv', 0]

        print(df_db)

        graphs.make_graph_meteo(df_db, file = "../data/images/meteo" + 
                                              datetime.datetime.now().strftime("%H%M") + 
                                             ".png", show=show_graph)
                               
        del df_db["time_str"]
        print(df_db)
        self.db_da.savedata(df_db)
        """

    def get_avg_temperature(self, date: datetime.datetime = None) -> float:
        """
        Berekent gewogen met temperatuur grens van 16 oC
        :param date: de datum waarvoor de berekening wordt gevraagd
        als None: vandaag
        :return: berekende gewogen graaddagen
        """
        if date is None:
            date = datetime.datetime.combine(
                datetime.datetime.today(), datetime.datetime.min.time()
            )
        date_utc = int(date.timestamp())

        # Reflect existing tables from the database
        values_table = Table(
            "values", self.db_da.metadata, autoload_with=self.db_da.engine
        )
        variabel_table = Table(
            "variabel", self.db_da.metadata, autoload_with=self.db_da.engine
        )

        # Construct the inner query
        inner_query = (
            select(
                values_table.c.time,
                values_table.c.value,
                self.db_da.from_unixtime(values_table.c.time).label("begin"),
            )
            .where(
                and_(
                    variabel_table.c.code == "temp",
                    values_table.c.variabel == variabel_table.c.id,
                    values_table.c.time >= date_utc,
                )
            )
            .order_by(values_table.c.time.asc())
            .limit(24)
            .alias("t1")
        )

        # Construct the outer query
        outer_query = select(func.avg(inner_query.c.value).label("avg_temp"))

        # Execute the query and fetch the result
        with self.db_da.engine.connect() as connection:
            result = connection.execute(outer_query)
            avg_temp = result.scalar()
        """
        sql_avg_temp = (
            "SELECT AVG(t1.`value`) avg_temp FROM "
            "(SELECT `time`, `value`,  from_unixtime(`time`) 'begin' "
            "FROM `values` , `variabel` "
            "WHERE `variabel`.`code` = 'temp' 
                AND `values`.`variabel` = `variabel`.`id` 
                AND time >= " + str(date_utc) + " "
            "ORDER BY `time` ASC LIMIT 24) t1 "
        )
        data = self.db_da.run_select_query(sql_avg_temp)
        avg_temp = float(data['avg_temp'].values[0])
        """
        return avg_temp

    def calc_graaddagen(
        self,
        date: datetime.datetime = None,
        avg_temp: float | None = None,
        weighted: bool = False,
    ) -> float:
        """
        Berekent graaddagen met temperatuur grens van 16 oC
        :param date: de datum waarvoor de berekening wordt gevraagd
                    als None: vandaag
        :param avg_temp: de gemiddelde temperatuur, default None
        :param weighted: boolean, gewogen als true, default false
        :return: berekende eventueel gewogen graaddagen
        """
        if date is None:
            date = datetime.datetime.combine(
                datetime.datetime.today(), datetime.datetime.min.time()
            )
        if avg_temp is None:
            avg_temp = self.get_avg_temperature(date)
        weight_factor = 1
        if weighted:
            mon = date.month
            if mon <= 2 or mon >= 11:
                weight_factor = 1.1
            elif 4 <= mon <= 9:
                weight_factor = 0.8
        if avg_temp >= 16:
            result = 0
        else:
            result = weight_factor * (16 - avg_temp)
        return result

    def calc_solar_rad(
        self, solar_opt: dict, utc_time: int, global_rad: float
    ) -> float:
        """
        :param solar_opt: definitie van paneel met
            tilt: helling t.o.v. plat vlak in graden, 0 = vlak (horizontaal), 90 = verticaal
            orienation: orientatie oost = -90, zuid = 0, west = 90 in graden
        :param utc_time: utc tijd in seconden
        :param global_rad: globale straling in J/cm²
        :return: alle straling op paneel J/cm²
        """
        # tilt:
        # orientation: orientatie oost = -90, zuid = 0, west = 90 in graden
        tilt = solar_opt["tilt"]
        tilt = min(90, max(0, tilt))
        hcol = math.radians(tilt)
        orientation = solar_opt["orientation"]
        acol = math.radians(orientation)
        q_tot = self.solar_rad(float(utc_time), global_rad, hcol, acol)
        return q_tot
