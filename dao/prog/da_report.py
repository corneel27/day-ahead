import calendar
import datetime
import pandas as pd
import base64
from io import BytesIO
from dateutil.relativedelta import relativedelta
from dao.prog.db_manager import DBmanagerObj
from dao.prog.da_config import Config
from dao.prog.da_graph import GraphBuilder
import math
import json
import itertools
import logging


class Report:
    periodes = {}

    def __init__(self):
        self.config = Config("../data/options.json")
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

        self.prices_options = self.config.get(["prices"])
        # eb + ode levering
        self.taxes_l_def = self.prices_options["energy taxes delivery"]
        # opslag kosten leverancier
        self.ol_l_def = self.prices_options["cost supplier delivery"]
        # eb+ode teruglevering
        self.taxes_t_def = self.prices_options["energy taxes redelivery"]
        self.ol_t_def = self.prices_options["cost supplier redelivery"]
        self.btw_def = self.prices_options["vat"]
        #
        self.report_options = self.config.get(["report"])
        self.make_periodes()
        self.energy_balance_dict = {
            "cons":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "Verbruik",
                 "sensors": self.config.get(["entities grid consumption"], self.report_options, []),
                 "color": '#00bfff'
                 },
            "prod":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Productie",
                 "sensors": self.config.get(["entities grid production"], self.report_options, []),
                 "color": '#0080ff'
                 },
            "bat_out":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "Accu_uit",
                 "sensors": self.config.get(["entities battery production"], self.report_options, []),
                 "color": 'red'
                 },
            "bat_in":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Accu in",
                 "sensors": self.config.get(["entities battery consumption"], self.report_options, []),
                 "color": '#ff8000'
                 },
            "pv_ac":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "PV ac",
                 "sensors": self.config.get(["entities solar production ac"], self.report_options, []),
                 "color": 'green'
                 },
            "ev":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Elec. vehicle",
                 "sensors": self.config.get(["entities ev consumption"], self.report_options, []),
                 "color": 'yellow'
                 },

            "wp":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "WP",
                 "sensors": self.config.get(["entities wp consumption"], self.report_options, []),
                 "color": '#a32cc4'
                 },
            "boil":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Boiler",
                 "sensors": self.config.get(["entities boiler consumption"], self.report_options, []),
                 "color": '#e39ff6'
                 },
            "base":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Baseload",
                 "sensors": "calc",
                 "function": "calc_base",
                 "color": "#f1a603"
                 },
        }
        self.grid_dict = {
            "cons":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "Verbruik",
                 "sensors": self.config.get(["entities grid consumption"], self.report_options, []),
                 },
            "prod":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Productie",
                 "sensors": self.config.get(["entities grid production"], self.report_options, []),
                 },
            "cost":
                {"dim": "eur",
                 "sign": "neg",
                 "name": "Kosten",
                 "sensors": "calc",
                 "function": "calc_cost"
                 },
            "profit":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "Opbrengst",
                 "sensors": "calc",
                 "function": "calc_cost"
                 },
        }
        self.balance_graph_options = {
            "title": "Energiebalans",
            "style": self.config.get(['graphics', 'style']),
            "haxis": {
                "values": "#interval"
            },
            "vaxis": [{
                "title": "kWh"
            }],
            "series_keys": ["base", "wp", "boil", "ev", "bat_in", "prod", "pv_ac", "bat_out", "cons"],
            "series": [],
        }
        for key in self.balance_graph_options["series_keys"]:
            # key, serie in self.energy_balance_dict.items():
            serie = self.energy_balance_dict[key]
            serie["column"] = serie['name']
            serie["type"] = "stacked",
            serie["title"] = serie["name"]
            self.balance_graph_options["series"].append(serie)
        return

    def make_periodes(self):
        def create_dict(name, _vanaf, _tot, interval):
            return {name: {"vanaf": _vanaf, "tot": _tot, "interval": interval}}

        # vandaag
        now = datetime.datetime.now()
        vanaf = datetime.datetime(now.year, now.month, now.day)
        tot = vanaf + datetime.timedelta(days=1)
        self.periodes.update(create_dict("vandaag", vanaf, tot, interval="uur"))

        # morgen
        vanaf_m = tot
        tot_m = vanaf_m + datetime.timedelta(days=1)
        self.periodes.update(create_dict("morgen", vanaf_m, tot_m, interval="uur"))

        # vandaag en morgen
        self.periodes.update(create_dict("vandaag en morgen", vanaf, tot_m, interval="uur"))

        # gisteren
        tot_g = vanaf
        vanaf_g = vanaf + datetime.timedelta(days=-1)
        self.periodes.update(create_dict("gisteren", vanaf_g, tot_g, interval="uur"))

        # deze week
        delta = vanaf.weekday()
        vanaf = vanaf + datetime.timedelta(days=-delta)
        tot = vanaf + datetime.timedelta(days=7)
        self.periodes.update(create_dict("deze week", vanaf, tot, "dag"))

        # vorige week
        vanaf += datetime.timedelta(days=-7)
        tot = vanaf + datetime.timedelta(days=7)
        self.periodes.update(create_dict("vorige week", vanaf, tot, "dag"))

        # deze maand
        vanaf = datetime.datetime(now.year, now.month, 1)
        tot = vanaf + relativedelta(months=1)
        self.periodes.update(create_dict("deze maand", vanaf, tot, "dag"))

        # vorige maand
        tot = vanaf
        vanaf += relativedelta(months=-1)
        self.periodes.update(create_dict("vorige maand", vanaf, tot, "dag"))

        # dit jaar
        vanaf = datetime.datetime(now.year, 1, 1)
        tot = datetime.datetime(now.year, now.month, now.day) + datetime.timedelta(days=1)
        self.periodes.update(create_dict("dit jaar", vanaf, tot, "maand"))

        # vorig jaar
        tot = vanaf
        vanaf = datetime.datetime(vanaf.year - 1, 1, 1)
        self.periodes.update(create_dict("vorig jaar", vanaf, tot, "maand"))

        # dit contractjaar
        vanaf = datetime.datetime.strptime(
            self.prices_options['last invoice'], "%Y-%m-%d")
        now = datetime.datetime.now()
        tot = datetime.datetime(now.year, now.month, now.day)
        tot = tot + datetime.timedelta(days=1)
        self.periodes.update(create_dict("dit contractjaar", vanaf, tot, "maand"))

        # 365 dagen
        tot = tot_g
        vanaf = tot + datetime.timedelta(days=-365)
        self.periodes.update(create_dict("365 dagen", vanaf, tot, "maand"))

        '''
        # laatste 12 maanden
        tot = datetime.datetime(now.year, now.month, 1)
        vanaf = datetime.datetime(now.year-1, now.month, 1)
        self.periodes.update(create_dict("laatste 12 mnd", vanaf, tot, "uur"))
        '''
        return

    def get_sensor_data(self, sensor: str, vanaf: datetime.datetime, tot: datetime.datetime,
                        col_name: str, agg: str = "uur") -> pd.DataFrame:
        if agg == "uur":
            sql = "SELECT FROM_UNIXTIME(t2.`start_ts`) 'tijd', " \
                  "FROM_UNIXTIME(t2.`start_ts`) 'tot', " \
              "round(greatest(t2.`state` - t1.`state`, 0),3) '" + col_name + "' " \
              "FROM `statistics` t1,`statistics` t2, `statistics_meta` " \
              "WHERE statistics_meta.`id` = t1.`metadata_id` AND statistics_meta.`id` = t2.`metadata_id` " \
              "AND statistics_meta.`statistic_id` = '" + sensor + "' " \
              "AND (t2.`start_ts` = t1.`start_ts` + 3600) " \
              "AND t1.`state` IS NOT null AND t2.`state` IS NOT null " \
              "AND t1.`start_ts` >= UNIX_TIMESTAMP('" + str(vanaf) + "') - 3600 " \
              "AND t1.`start_ts` < UNIX_TIMESTAMP('" + str(tot) + "') - 3600 " \
              "ORDER BY t1.`start_ts`;"
        elif agg == "maand":
            sql = "SELECT concat(year(from_unixtime(t2.`start_ts`)), "\
                "LPAD(MONTH(from_unixtime(t2.`start_ts`)),3, ' ')) AS 'maand', " \
                "date_format(from_unixtime(t2.`start_ts`),'%Y-%m-01 00:00:00') AS 'tijd', " \
                "MAX(FROM_UNIXTIME(t2.`start_ts`)) 'tot', " \
                "ROUND(sum(greatest(t2.`state` - t1.`state`, 0)),3) '" + col_name + "' " \
                "FROM `statistics` t1,`statistics` t2, `statistics_meta` " \
                "WHERE statistics_meta.`id` = t1.`metadata_id` AND statistics_meta.`id` = t2.`metadata_id` " \
                "AND statistics_meta.`statistic_id` = '" + sensor + "' " \
                "AND (t2.`start_ts` = t1.`start_ts` + 3600) " \
                "AND t1.`state` IS NOT null AND t2.`state` IS NOT null " \
                "AND t1.`start_ts` >= UNIX_TIMESTAMP('" + str(vanaf) + "') - 3600 " \
                "AND t1.`start_ts` < UNIX_TIMESTAMP('" + str(tot) + "') - 3600 " \
                "GROUP BY maand;"
        else:  # agg == "dag":
            sql = "SELECT date(from_unixtime(t2.`start_ts`)) AS 'dag', " \
                "date_format(from_unixtime(t2.`start_ts`),'%Y-%m-%d 00:00:00') AS 'tijd', " \
                "MAX(FROM_UNIXTIME(t2.`start_ts`)) AS 'tot', " \
                "ROUND(sum(greatest(t2.`state` - t1.`state`, 0)),3) '" + col_name + "' " \
                "FROM `statistics` t1,`statistics` t2, `statistics_meta` " \
                "WHERE statistics_meta.`id` = t1.`metadata_id` AND statistics_meta.`id` = t2.`metadata_id` " \
                "AND statistics_meta.`statistic_id` = '" + sensor + "' " \
                "AND (t2.`start_ts` = t1.`start_ts` + 3600) " \
                "AND t1.`state` IS NOT null AND t2.`state` IS NOT null " \
                "AND t1.`start_ts` >= UNIX_TIMESTAMP('" + str(vanaf) + "') - 3600 " \
                "AND t1.`start_ts` < UNIX_TIMESTAMP('" + str(tot) + "') - 3600  "\
                "GROUP BY dag;"
        # print(sql)
        df = self.db_ha.run_select_query(sql)
        # print(df_sensor)
        return df

    @staticmethod
    def copy_col_df(copy_from: pd.DataFrame, copy_to: pd.DataFrame, col_name: str) -> pd.DataFrame:
        """
        kopieert kolom "col_name" van copy_from naar copy_to,
        :param copy_from:
        :param copy_to:
        :param col_name:
        :return: de ingevuld copy_to
        """
        copy_to[col_name] = 0
        # copy_from = copy_from.reset_index()
        for row in copy_from.itertuples():
            copy_to.at[row.tijd, col_name] = copy_from.at[row.tijd, col_name]
        return copy_to

    @staticmethod
    def add_col_df(add_from: pd.DataFrame, add_to: pd.DataFrame, col_name_from: str, col_name_to: str = None,
                   negation: bool = False) -> pd.DataFrame:
        # add_from = add_from.reset_index()
        if add_from is None:
            return add_to
        factor = -1 if negation else +1
        if col_name_to is None:
            col_name_to = col_name_from
        # if negation:
        #    add_to[col_name_to] = add_to[col_name_to] - add_from[col_name_from]
        # else:
        #    add_to[col_name_to] =add_to[col_name_to] + add_from[col_name_from]
        for row in add_from.itertuples():
            add_to.at[row.tijd, col_name_to] = (
                    add_to.at[row.tijd, col_name_to] + factor * add_from.at[row.tijd, col_name_from])
        return add_to

    def get_latest_present(self, code: str) -> datetime.datetime:
        """
        :param code: de code van de variabele
        :return: datetime van het laatste record
        """
        sql = "SELECT `time`, `variabel`.`id`, `value` \
                FROM `values` , `variabel`  \
                WHERE `variabel`.`code` = '" + code + "'  \
                AND `values`.`variabel` = `variabel`.`id`  \
                ORDER BY `time` DESC  \
                LIMIT 1;"
        data = self.db_da.run_select_query(sql)
        if len(data) == 1:
            result = datetime.datetime.fromtimestamp(data['time'].values[0])
        else:
            result = datetime.datetime(year=2020, month=1, day=1)
        return result

    def get_sensor_sum(self, sensor_list: list, vanaf: datetime.datetime,
                       tot: datetime.datetime, col_name: str) -> pd.DataFrame:
        """
        berekent een dataframe met sum van de waarden van de sensoren in de list
        :param sensor_list: een list of strings met de entiteiten van de sensoren
        :param vanaf: berekenen vanaf
        :param tot: berekenen tot
        :param col_name: string naam van de kolom
        :return: het dataframe met de sum
        """
        counter = 0
        result = None
        for sensor in sensor_list:
            df = self.get_sensor_data(sensor, vanaf, tot, col_name)
            df.index = pd.to_datetime(df["tijd"])
            if counter == 0:
                result = df
            else:
                result = self.add_col_df(df, result, col_name)
            counter = + 1
        return result

    def calc_cost(self, vanaf: datetime.datetime, tot: datetime.datetime) -> pd.DataFrame:
        cons_df = self.get_sensor_sum(self.grid_dict["cons"]["sensors"], vanaf, tot, "cons")
        prod_df = self.get_sensor_sum(self.grid_dict["prod"]["sensors"], vanaf, tot, "prod")
        da_df = self.get_price_data(vanaf, tot)
        da_df.index = pd.to_datetime(da_df["time"])
        data = self.copy_col_df(cons_df, da_df, "cons")
        data = self.copy_col_df(prod_df, data, "prod")
        result = pd.DataFrame(columns=['time', 'code', 'value'])
        for row in data.itertuples():
            cost = row.cons * row.da_cons
            db_row = [str(int(row.time.timestamp())), "cost", cost]
            result.loc[result.shape[0]] = db_row
            profit = row.prod * row.da_prod
            db_row = [str(int(row.time.timestamp())), "profit", profit]
            result.loc[result.shape[0]] = db_row
            print(result)
        return data

    def consolidate_data(self, _start=None, _end=None) -> None:
        if _end is None:
            now = datetime.datetime.now()
            tot = datetime.datetime(now.year, now.month, now.day)
        else:
            tot = _end
        for code, categorie in itertools.chain(self.grid_dict.items(), self.energy_balance_dict.items()):
            if _start is None:
                start = self.get_latest_present(code) + datetime.timedelta(hours=1)
            else:
                start = _start
            if categorie["sensors"] == "calc":
                function = categorie["function"]
                data = getattr(self, function)(start, tot, code)
                continue
            else:
                data = self.get_sensor_sum(categorie["sensors"], start, tot, code)
                if data is None:
                    continue
                df_db = pd.DataFrame(columns=['time', 'code', 'value'])
                data = data.rename(columns={code: "value"})
            for row in data.itertuples():
                db_row = [str(int(row.tijd.timestamp())), code, float(row.value)]
                # print(db_row)
                df_db.loc[df_db.shape[0]] = db_row
            print(df_db)
            # self.db_da.savedata(df_db, debug=False, tablename="values")
        return

    def recalc_df_ha(self, org_data_df: pd.DataFrame, interval: str) -> pd.DataFrame:
        from dao.prog.utils import get_value_from_dict
        fi_df = pd.DataFrame(
            columns=[interval, "vanaf", "tot", "consumption", "production", "cost", "profit", "datasoort"])
        if len(org_data_df.index) == 0:
            return fi_df
        old_dagstr = ""
        taxes_l = 0
        taxes_t = 0
        ol_l = 0
        ol_t = 0
        btw = 0
        for row in org_data_df.itertuples():
            if pd.isnull(row.tijd):
                continue
            if not isinstance(row.tijd, datetime.datetime):
                print(row)
            dag_str = row.tijd.strftime("%Y-%m-%d")
            if dag_str != old_dagstr:
                ol_l = get_value_from_dict(dag_str, self.ol_l_def)
                ol_t = get_value_from_dict(dag_str, self.ol_t_def)
                taxes_l = get_value_from_dict(dag_str, self.taxes_l_def)
                taxes_t = get_value_from_dict(dag_str, self.taxes_t_def)
                btw = get_value_from_dict(dag_str, self.btw_def)
                old_dagstr = dag_str
            if interval == "uur":
                tijd_str = str(row.tijd)[10:16]
            elif interval == "dag":
                tijd_str = str(row.tijd)[0:10]
            else:
                tijd_str = str(row.tijd)[0:7]  # jaar maand
            col_1 = row.consumption
            col_2 = row.production
            col_3 = (row.consumption * (row.price + taxes_l + ol_l)) * (1 + btw / 100)
            col_4 = (row.production * (row.price + taxes_t + ol_t)) * (1 + btw / 100)
            col_5 = row.datasoort
            fi_df.loc[fi_df.shape[0]] = [tijd_str, row.tijd, row.tijd +
                                         datetime.timedelta(hours=1), col_1, col_2, col_3, col_4, col_5]
        if interval != "uur":
            fi_df = fi_df.groupby([interval], as_index=False).agg({"vanaf": 'min', "tot": 'max', "consumption": 'sum',
                                                                   "production": 'sum', "cost": 'sum', "profit": 'sum'})
        return fi_df

    def aggregate_balance_df(self, df: pd.DataFrame, interval: str):
        df = df.rename(columns={"tijd": "vanaf"})
        df["tot"] = df["vanaf"]
        tot_values = df.pop("tot")
        df.insert(1, "tot", tot_values)
        datasoort_values = df.pop("datasoort")
        df.insert(2, "datasoort", datasoort_values)
        columns = [interval] + df.columns.tolist()
        result = pd.DataFrame(columns=columns)
        for row in df.itertuples():
            if interval == "uur":
                tijd_str = str(row.vanaf)[10:16]
            elif interval == "dag":
                tijd_str = str(row.vanaf)[0:10]
            else:
                tijd_str = str(row.vanaf)[0:7]  # jaar maand
            result.loc[result.shape[0]] = [tijd_str, row.vanaf, row.vanaf + datetime.timedelta(hours=1), row.datasoort,
                                           row.cons, row.prod, row.bat_out, row.bat_in, row.pv_ac, row.ev, row.wp,
                                           row.boil, row.base]

        if interval != "uur":
            agg_dict = {"vanaf": 'min'}
            for key, categorie in self.energy_balance_dict.items():
                agg_dict[key] = 'sum'
            result = result.groupby([interval], as_index=False).agg(agg_dict)

        return result

    def calc_base(self, df: pd.DataFrame) -> pd.DataFrame:
        base_load = []
        for row in df.itertuples():
            base_load.append(row.cons - row.prod + row.bat_out - row.bat_in + row.pv_ac - row.ev - row.wp - row.boil)
        result = df.assign(base=base_load)
        return result

    def get_energy_balance_data(self, periode, _vanaf=None, _tot=None):
        self.db_da.connect()
        self.db_ha.connect()
        periode_d = self.periodes[periode]
        vanaf = _vanaf if _vanaf else periode_d["vanaf"]
        tot = _tot if _tot else periode_d["tot"]
        interval = periode_d["interval"]
        result = pd.DataFrame(columns=[interval, "tijd"])
        last_realised_moment = datetime.datetime.fromtimestamp(math.floor(datetime.datetime.now().timestamp()/3600)*3600)
        moment = vanaf
        while moment < tot:
            if interval == "maand":
                old_moment = datetime.datetime(moment.year, moment.month, day=1)
            else:
                old_moment = moment
            moment_str = str(moment)
            if interval == "uur":
                if periode == "laatste 12 mnd":
                    tijd_str = moment_str
                else:
                    tijd_str = moment_str[10:16]
                moment = moment + datetime.timedelta(hours=1)
            elif interval == "dag":
                tijd_str = moment_str[0:10]
                moment = moment + datetime.timedelta(days=1)
            else:
                tijd_str = moment_str[0:7]  # jaar maand
                moment = old_moment + relativedelta(months=1)
            result.loc[result.shape[0]] = [tijd_str, old_moment]
        result.index = pd.to_datetime(result["tijd"])

        for key, categorie in self.energy_balance_dict.items():
            result[key] = 0
            if interval == "maand":
                sql = "SELECT concat(year(from_unixtime(t1.`time`)),LPAD(MONTH(from_unixtime(t1.`time`)),3, ' ')) "\
                      "AS 'maand', " \
                    "date_format(from_unixtime(t1.`time`),'%Y-%m-01 00:00:00') AS 'tijd', " \
                    "MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                    "sum(t1.`value`) " + key + " " \
                    "FROM `values` AS t1, `variabel`AS v1  " \
                    "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                    "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') " \
                    "GROUP BY maand;"
            elif interval == "dag":
                sql = "SELECT date(from_unixtime(t1.`time`)) AS 'dag', " \
                    "date_format(from_unixtime(t1.`time`),'%Y-%m-%d 00:00:00') AS 'tijd', " \
                    "MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                    "sum(t1.`value`) " + key + " " \
                    "FROM `values` AS t1, `variabel`AS v1  " \
                    "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                    "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') " \
                    "GROUP BY dag;"
            else:  # interval == "uur"
                sql = "SELECT from_unixtime(t1.`time`) AS 'uur', " \
                  "from_unixtime(t1.`time`) AS 'tijd', from_unixtime(t1.`time`) AS 'tot', " \
                  "t1.`value` '" + key + "' " \
                  "FROM `values` AS t1, `variabel`AS v1  " \
                  "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                  "t1.`time`>= UNIX_TIMESTAMP('" + str(vanaf) + "') AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "');"
            # print(sql)
            code_result = self.db_da.run_select_query(sql)
            code_result.index = pd.to_datetime(code_result["tijd"])
            #self.add_col_df(code_result, result, key)
            code_result.rename(columns={key: "temp"})
            result = pd.concat([result, code_result["temp"]], axis=0)
            result.assign(key = key +"temp")

            if code_result.shape[0] == 0:
                # datetime.datetime.combine(vanaf, datetime.time(0,0)) - datetime.timedelta(hours=1)
                last_moment = vanaf
            else:
                last_moment = code_result['tot'].iloc[-1] + datetime.timedelta(hours=1)
            if last_moment < tot:
                ha_result = None
                if categorie["sensors"] == "calc":
                    function = categorie["function"]
                    ha_result = getattr(self, function)(result)
                else:
                    for sensor in categorie["sensors"]:
                        ha_result = self.get_sensor_data(sensor, last_moment, tot, key, interval)
                        ha_result.index = pd.to_datetime(ha_result["tijd"])
                        result = self.add_col_df(ha_result, result, key)
                if ha_result is not None and len(ha_result) > 0:
                    if categorie["sensors"] == "calc":
                        now = datetime.datetime.now()
                        last_moment = max(datetime.datetime(now.year, now.month, now.day, now.hour), vanaf)
                    else:
                        last_moment = ha_result['tot'].iloc[-1] + datetime.timedelta(hours=1)
                else:
                    last_moment = vanaf

            if last_moment < last_realised_moment:
                last_moment = last_realised_moment
            if last_moment < tot:
                if interval == "maand":
                    sql = "SELECT concat(year(from_unixtime(t1.`time`)), LPAD(MONTH(from_unixtime(t1.`time`)),3, ' ')) " \
                          "AS 'maand', " \
                          "date_format(from_unixtime(t1.`time`),'%Y-%m-01 00:00:00') AS 'tijd', " \
                          "MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                          "sum(t1.`value`) " + key + " " \
                          "FROM `prognoses` AS t1, `variabel`AS v1  " \
                          "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                          "t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + ("') AND " 
                          "t1.`time` < UNIX_TIMESTAMP('") + str(tot) + "') " \
                          "GROUP BY maand;"
                elif interval == "dag":
                    sql = "SELECT date(from_unixtime(t1.`time`)) AS 'dag', " \
                          "date_format(from_unixtime(t1.`time`),'%Y-%m-%d 00:00:00') AS 'tijd', " \
                          "MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                          "sum(t1.`value`) " + key + " " \
                          "FROM `prognoses` AS t1, `variabel`AS v1  " \
                          "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                          "t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + ("') AND " 
                          "t1.`time` < UNIX_TIMESTAMP('") + str(tot) + "') " \
                          "GROUP BY dag;"
                else:  # interval == "uur"
                    sql = "SELECT from_unixtime(t1.`time`) AS 'uur', " \
                          "from_unixtime(t1.`time`) AS 'tijd', from_unixtime(t1.`time`) AS 'tot', " \
                          "t1.`value` '" + key + "' " \
                          "FROM `prognoses` AS t1, `variabel`AS v1  " \
                          "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                          "t1.`time`>= UNIX_TIMESTAMP('" + str(last_moment) + ("') AND " 
                          "t1.`time` < UNIX_TIMESTAMP('") + str(tot) + "');"
                    '''
                    sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
                          " t1.`value` '" + key + "' " \
                          "FROM `prognoses` AS t1,  `variabel` AS v1  " \
                          "WHERE v1.`code` ='" + key + "' " \
                          "AND v1.id = t1.variabel " \
                          "AND t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + "') " \
                          "AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "');"
                    '''
                prog_result = self.db_da.run_select_query(sql)
                prog_result.index = pd.to_datetime(prog_result["tijd"])
                if len(prog_result) > 0:
                    self.add_col_df(prog_result, result, key)
            if categorie["sensors"] == "calc":
                function = categorie["function"]
                result = getattr(self, function)(result)
#        result = self.aggregate_balance_df(result, interval)
        return result

    def get_grid_data(self, periode: str, _vanaf=None, _tot=None):
        """
        Haalt de grid data: consumptie. productie, cost, profit op de drie tabellen:
        db_da: values tibber data
        aangevuld met
        db_ha: sensoren Home Assistant tot het laatste uur
        voor prognoses (expected):
        db_da: progoses
        :param periode: dus een van alle gedefinieerde perioden: vandaag, gisteren enz
        :param _vanaf: als != None dan geldt dit als begintijdstip en overrullt begintijdstip van periode
        :param _tot: als  != None dan hier het eindtijdstip 
        :return: een dataframe met de gevraagde griddata
        """
        self.db_da.connect()
        self.db_ha.connect()
        periode_d = self.periodes[periode]
        vanaf = _vanaf if _vanaf else periode_d["vanaf"]
        tot = _tot if _tot else periode_d["tot"]
        interval = periode_d["interval"]
        '''
        sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
            "t1.`value` consumption,t2.`value` production, t3.`value` price "\
            "FROM `values` AS t1, `values` AS t2, `values` AS t3, `variabel`AS v1, `variabel` AS v2, `variabel` AS v3 "\
            "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)" \
            "AND (v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'da') " \
            "AND (v1.id = t1.variabel) AND (v2.id = t2.variabel) AND (v3.id = t3.variabel)" \
            "AND t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"')"
        result = self.db_da.run_select_query(sql)
        result.index = pd.to_datetime(result["tijd"])

        #cost and profit
        sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
            "t1.`value` cost,t2.`value` profit "\
            "FROM `values` AS t1, `values` AS t2, `variabel`AS v1, `variabel` AS v2 "\
            "WHERE (t1.`time`= t2.`time`) " \
            "AND (v1.`code` ='cost')AND (v2.`code` = 'profit') " \
            "AND (v1.id = t1.variabel) AND (v2.id = t2.variabel) " \
            "AND t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"')"
        df_fin = self.db_da.run_select_query(sql)
        df_fin.index = pd.to_datetime(df_fin["tijd"])
        result["cost"]=df_fin["cost"]
        result["profit"] = df_fin["profit"]
        '''
        if interval == "maand":
            sql = "SELECT concat(year(from_unixtime(t1.`time`)),LPAD(MONTH(from_unixtime(t1.`time`)),3, ' ')) " \
                  "AS 'maand', " \
                  "MIN(from_unixtime(t1.`time`)) AS 'vanaf', MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                  "sum(t1.`value`) consumption, sum(t2.`value`) production, sum(t3.`value`) cost, " \
                  " SUM(t4.`value`) profit," \
                  " 'recorded' as 'datasoort' " \
                  "FROM `values` AS t1, `values` AS t2, `values` AS t3,`values` AS t4,  " \
                  "`variabel`AS v1, `variabel` AS v2, `variabel` AS v3, `variabel` AS v4  " \
                  "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)AND (t1.`time`= t4.`time`)AND  " \
                  "(v1.`code` ='cons')AND (v2.`code` = 'prod') AND " \
                  "(v3.`code` = 'cost') AND (v4.`code` = 'profit') AND " \
                  "(v1.id = t1.variabel) AND (v2.id = t2.variabel) AND " \
                  "(v3.id = t3.variabel)AND (v4.id = t4.variabel) AND  " \
                  "t1.`time` >= UNIX_TIMESTAMP('" + str(vanaf) + "') AND " \
                  "t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "') " \
                  "GROUP BY maand;"
        elif interval == "dag":
            sql = "SELECT date(from_unixtime(t1.`time`)) AS 'dag', " \
                  "MIN(from_unixtime(t1.`time`)) AS 'vanaf', MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                  "sum(t1.`value`) consumption,sum(t2.`value`) production, " \
                  "sum(t3.`value`) cost, SUM(t4.`value`) profit,  " \
                  " 'recorded' as 'datasoort' " \
                  "FROM `values` AS t1, `values` AS t2, `values` AS t3,`values` AS t4,  " \
                  "`variabel`AS v1, `variabel` AS v2, `variabel` AS v3, `variabel` AS v4  " \
                  "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)AND (t1.`time`= t4.`time`)AND  " \
                  "(v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'cost') AND "\
                  "(v4.`code` = 'profit') AND  " \
                  "(v1.id = t1.variabel) AND (v2.id = t2.variabel) AND " \
                  "(v3.id = t3.variabel)AND (v4.id = t4.variabel) AND  " \
                  "t1.`time` >= UNIX_TIMESTAMP('" + str(vanaf) + "') AND " \
                  "t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "') " \
                  "GROUP BY dag;"
        else:  # interval == "uur"
            sql = "SELECT from_unixtime(t1.`time`) AS 'uur', " \
                  "from_unixtime(t1.`time`) AS 'vanaf', from_unixtime(t1.`time`) AS 'tot', " \
                  "t1.`value` consumption, t2.`value` production, t3.`value` cost, t4.`value` profit,  " \
                  " 'recorded' as 'datasoort' " \
                  "FROM `values` AS t1, `values` AS t2, `values` AS t3,`values` AS t4,  " \
                  "`variabel`AS v1, `variabel` AS v2, `variabel` AS v3, `variabel` AS v4  " \
                  "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)AND (t1.`time`= t4.`time`)AND  " \
                  "(v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'cost') AND " \
                  "(v4.`code` = 'profit') AND  " \
                  "(v1.id = t1.variabel) AND (v2.id = t2.variabel) AND (v3.id = t3.variabel) AND " \
                  "(v4.id = t4.variabel) AND  " \
                  "t1.`time` >= UNIX_TIMESTAMP('" + str(vanaf) + \
                  "') AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "') ;"

        result = self.db_da.run_select_query(sql)
        result.index = pd.to_datetime(result["vanaf"])

        # aanvullende prijzen ophalen
        if result.shape[0] == 0:
            # datetime.datetime.combine(vanaf, datetime.time(0,0)) - datetime.timedelta(hours=1)
            last_moment = vanaf
        else:
            last_moment = result['tot'].iloc[-1] + datetime.timedelta(hours=1)
        if last_moment < tot:
            # get the prices:
            sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
                  " t1.`value` price " \
                  "FROM `values` AS t1,  `variabel` AS v1  " \
                  "WHERE v1.`code` ='da' " \
                  "AND v1.id = t1.variabel " \
                  "AND t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + "') " \
                  "AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "')"
            # print (sql)
            df_prices = self.db_da.run_select_query(sql)
            # print(df_prices)

            # data uit ha ophalen
            self.db_ha.connect()
            count = 0
            df_ha = pd.DataFrame()
            for sensor in self.report_options["entities grid consumption"]:
                if count == 0:
                    df_ha = self.get_sensor_data(sensor, last_moment, tot, "consumption")
                    df_ha.index = pd.to_datetime(df_ha["tijd"])
                else:
                    df_2 = self.get_sensor_data(sensor, last_moment, tot, "consumption")
                    df_2.index = pd.to_datetime(df_2["tijd"])
                    df_ha = self.add_col_df(df_2, df_ha, "consumption")
                    # df_cons = df_cons.merge(df_2, on=['tijd']).set_index(['tijd']).sum(axis=1)
                count = + 1
            count = 0
            for sensor in self.report_options["entities grid production"]:
                df_p = self.get_sensor_data(sensor, last_moment, tot, "production")
                df_p.index = pd.to_datetime(df_p["tijd"])
                if count == 0:
                    df_ha = self.copy_col_df(df_p, df_ha, "production")
                else:
                    df_ha = self.add_col_df(df_p, df_ha, "production")
                count = + 1
            if len(df_ha) > 0:
                last_moment = df_ha['tijd'].iloc[-1] + datetime.timedelta(hours=1)
                df_ha['datasoort'] = "recorded"
            else:
                last_moment = vanaf

            if last_moment < tot:
                # get consumption:
                sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
                      " t1.`value` consumption " \
                      "FROM `prognoses` AS t1,  `variabel` AS v1  " \
                      "WHERE v1.`code` ='cons' " \
                      "AND v1.id = t1.variabel " \
                      "AND t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + "') " \
                      "AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "');"
                df_prog = self.db_da.run_select_query(sql)
                df_prog.index = pd.to_datetime(df_prog["tijd"])
                # df_ha = self.copy_col_df(df_prog, df_ha, "consumption")
                # get production
                sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
                      " t1.`value` production " \
                      "FROM `prognoses` AS t1,  `variabel` AS v1  " \
                      "WHERE v1.`code` ='prod' " \
                      "AND v1.id = t1.variabel " \
                      "AND t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + "') " \
                      "AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "');"
                df_prod = self.db_da.run_select_query(sql)
                df_prod.index = pd.to_datetime(df_prod["tijd"])
                df_prog = self.copy_col_df(df_prod, df_prog, "production")
                df_prog["datasoort"] = "expected"
                df_ha = pd.concat([df_ha, df_prog])

            df_prices.index = pd.to_datetime(df_prices["tijd"])
            df_ha = self.copy_col_df(df_prices, df_ha, "price")
            df_ha = self.copy_col_df(df_prices, df_ha, "tijd")
            df_ha = self.recalc_df_ha(df_ha, interval)

            result = pd.concat([result, df_ha])
            result["netto_consumption"] = result["consumption"] - result["production"]
            result["netto_const"] = result["cost"] - result["profit"]

        return result

    @staticmethod
    def get_last_day_month(input_dt: datetime):
        # Get the last day of the month from a given datetime
        res = calendar.monthrange(input_dt.year, input_dt.month)
        return res[1]

    def calc_grid_columns(self, report_df, active_interval, active_view, active_period):
        from dao.prog.utils import get_value_from_dict
        first_col = active_interval.capitalize()
        # if active_subject == "verbruik":
        #    columns.extend(["Verbruik", "Productie", "Netto"])
        #    columns = [columns]
        #    columns.append(["", "kWh", "kWh", "kWh"])
        # else:  #kosten
        columns = [first_col, "Verbruik", "Productie",
                   "Netto verbr.", "Kosten", "Opbrengst", "Netto kosten"]
        # columns.extend(ext_columns)
        fi_df = pd.DataFrame(columns=columns)
        if len(report_df.index) == 0:
            return fi_df
        prices_options = self.config.get(["prices"])
        # eb + ode levering
        taxes_l_def = prices_options["energy taxes delivery"]
        # opslag kosten leverancier
        ol_l_def = prices_options["cost supplier delivery"]
        # eb+ode teruglevering
        taxes_t_def = self.prices_options["energy taxes redelivery"]
        ol_t_def = self.prices_options["cost supplier redelivery"]
        btw_def = self.prices_options["vat"]
        #        report_df = report_df.reset_index()
        old_dagstr = ""
        taxes_l = 0
        taxes_t = 0
        ol_l = 0
        ol_t = 0
        btw = 0
        for row in report_df.itertuples():
            if pd.isnull(row.vanaf):
                continue
            dag_str = row.vanaf.strftime("%Y-%m-%d")
            if dag_str != old_dagstr:
                ol_l = get_value_from_dict(dag_str, ol_l_def)
                ol_t = get_value_from_dict(dag_str, ol_t_def)
                taxes_l = get_value_from_dict(dag_str, taxes_l_def)
                taxes_t = get_value_from_dict(dag_str, taxes_t_def)
                btw = get_value_from_dict(dag_str, btw_def)
                old_dagstr = dag_str
            if active_interval == "uur":
                if active_period == "laatste 12 mnd":
                    tijd_str = str(row.vanaf)
                else:
                    tijd_str = str(row.vanaf)[10:16]
            elif active_interval == "dag":
                tijd_str = str(row.vanaf)[0:10]
            else:
                tijd_str = str(row.vanaf)[0:7]  # jaar maand
            col_1 = row.consumption
            col_2 = row.production
            col_3 = col_1 - col_2
            if math.isnan(row.cost):
                col_4 = (row.consumption * (row.price + taxes_l + ol_l)) * (1 + btw / 100)
            else:
                col_4 = row.cost
            if math.isnan(row.profit):
                col_5 = (row.production * (row.price + taxes_t + ol_t)) * (1 + btw / 100)
            else:
                col_5 = row.profit
            col_6 = col_4 - col_5
            '''
            #col_7 = (row.price + taxes_l + ol_l) * (1 + btw / 100)
            if col_1:
                col_7 = col_4/col_1
            else:
                col_7 = numpy.nan
            if col_2:
                col_8 = col_5/col_2
            else:
                col_8 = numpy.nan
            '''
            fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1, col_2, col_3, col_4, col_5, col_6]

        # , "Tarief verbr.", "Tarief prod."
        # , "Tarief verbr.":'mean', "Tarief prod.":"mean"
        # fi_df.set_index([columns[0][0]])
        if active_interval != "uur":
            fi_df = fi_df.groupby([first_col], as_index=False).agg({"Verbruik": 'sum', "Productie": 'sum',
                                                                    "Netto verbr.": 'sum', "Kosten": 'sum',
                                                                    "Opbrengst": 'sum', "Netto kosten": 'sum'})
        fi_df['Tarief verbr.'] = fi_df.apply(
            lambda rw: rw.Kosten / rw.Verbruik if rw.Verbruik != 0.0 else rw.Verbruik, axis=1)
        fi_df['Tarief prod.'] = fi_df.apply(
            lambda rw: rw.Opbrengst / rw.Productie if rw.Productie != 0.0 else rw.Productie, axis=1)
        if active_view == "tabel":
            fi_df.loc["Total"] = fi_df.sum(axis=0, numeric_only=True)
            fi_df.at[fi_df.index[-1], first_col] = "Totaal"
            row = fi_df.iloc[-1]
            fi_df.at[fi_df.index[-1], "Tarief verbr."] = row.Kosten / row.Verbruik
            fi_df.at[fi_df.index[-1], "Tarief prod."] = row.Opbrengst / row.Productie
            # value = fi_df.iloc[-1][7]
            # fi_df.at[fi_df.index[-1], "Tarief"] = value / (len(fi_df.index)-1)

            # fi_df.loc[fi_df.shape[0]] = ["Totaal", col_1_tot, col_2_tot, col_3_tot, col_4_tot, col_5_tot, col_6_tot,
            #                         col_7_tot / count_tot]
            columns = fi_df.columns.values.tolist()
            # columns.append(["", "kWh", "kWh", "kWh", "eur", "eur", "eur", "eur/kWh",  "eur/kWh"])
            # columns = [columns,
            fi_df.columns = [columns, ["", "kWh", "kWh", "kWh",
                                       "eur", "eur", "eur", "eur/kWh", "eur/kWh"]]
        fi_df = fi_df.round(3)
        return fi_df

    def calc_balance_columns(self, report_df, active_interval, active_view):
        first_col = active_interval.capitalize()
        #report_df = report_df.drop('vanaf', axis=1)
        report_df.style.format('{:.3f}')
        report_df = report_df.drop('tijd', axis=1)
        #report_df =  report_df.drop('datasoort', axis=1)
        key_columns = report_df.columns.values.tolist()[1:]
        columns_1 = [first_col]
        columns_2 = [""]
        for key in key_columns:
            columns_1 = columns_1 + [self.energy_balance_dict[key]["name"]]
            columns_2 = columns_2 + [self.energy_balance_dict[key]["dim"]]
        if active_view == "tabel":
            report_df.loc["Total"] = report_df.sum(axis=0, numeric_only=True)
            report_df.at["Total", active_interval] = "Totaal"
            columns = [columns_1, columns_2]
            report_df.columns = columns
        else:
            report_df.columns = columns_1

        return report_df

    #------------------------------------------------
    def get_sensor_week_data(self, sensor: str, weekday: int, vanaf: datetime.datetime,
                             col_name: str) -> pd.DataFrame:
        sql = "SELECT FROM_UNIXTIME(t2.`start_ts`) 'tijd', GREATEST(0, round(t2.state - t1.`state`,3)) '" + col_name + "', \
            WEEKDAY(FROM_UNIXTIME(t2.`start_ts`))  'weekdag', \
            HOUR(FROM_UNIXTIME(t2.`start_ts`)) 'uur' \
            FROM `statistics` t1,`statistics` t2, `statistics_meta`  \
            WHERE statistics_meta.`id` = t1.`metadata_id` AND statistics_meta.`id` = t2.`metadata_id`   \
            AND statistics_meta.`statistic_id` = '" + sensor + "'  \
            AND (t2.`start_ts` = t1.`start_ts` + 3600)   \
            AND t1.`state` IS NOT null AND t2.`state` IS NOT null   \
            AND t1.`start_ts` >= UNIX_TIMESTAMP('" + str(vanaf) + "') - 3600  \
            AND  WEEKDAY(FROM_UNIXTIME(t2.`start_ts`))= " + str(weekday) + " \
            ORDER BY t1.`start_ts`;"
        df = self.db_ha.run_select_query(sql)
        return df

    def get_sensor_week_sum(self, sensor_list: list, weekday: int, vanaf: datetime.datetime,
                            col_name: str) -> pd.DataFrame:
        counter = 0
        result = None
        for sensor in sensor_list:
            df = self.get_sensor_week_data(sensor, weekday, vanaf, col_name)
            df.index = pd.to_datetime(df["tijd"])
            if counter == 0:
                result = df
            else:
                result[col_name] = result[col_name] + df[col_name]
                #result = Report.add_col_df(df, result, col_name)
            counter = + 1
        return result

    def calc_weekday_baseload(self, wd: int) -> list:
        """
        :param wd : weekdag 0= maandag, 6 = zondag
        :return: de berekende basislast voor die dag
        """
        result = []
        config = Config("../data/options.json")

        calc_periode = config.get(["baseload calc periode"], None, 56)
        calc_start = datetime.datetime.combine((datetime.datetime.now() - datetime.timedelta(days=calc_periode)).date(),
                                               datetime.time())

        grid_consumption = self.get_sensor_week_sum(config.get(['report', "entities grid consumption"]), wd,
                                               calc_start,
                                               "grid_consumption")
        grid_production = self.get_sensor_week_sum(config.get(['report', "entities grid production"]), wd, calc_start,
                                              "grid_production")
        solar_production = self.get_sensor_week_sum(config.get(['report', "entities solar production ac"]), wd,
                                               calc_start, "solar_production")
        ev_consumption = self.get_sensor_week_sum(config.get(['report', "entities ev consumption"]), wd, calc_start,
                                             "ev_consumption")
        wp_consumption = self.get_sensor_week_sum(config.get(['report', "entities wp consumption"]), wd, calc_start,
                                             "wp_consumption")
        boiler_consumption = self.get_sensor_week_sum(config.get(['report', "entities boiler consumption"]), wd,
                                                 calc_start, "boiler_consumption")
        battery_consumption = self.get_sensor_week_sum(config.get(['report', "entities battery consumption"]), wd,
                                                  calc_start, "battery_consumption")
        battery_production = self.get_sensor_week_sum(config.get(['report', "entities battery production"]), wd,
                                                 calc_start, "battery_production")

        # baseload = grid_consumption - grid_production + solar_production - ev_consumption - wp_consumption - battery_consumption + battery_production
        # baseload = grid_consumption
        grid_consumption = grid_consumption.rename(columns={'grid_consumption': 'baseload'})
        # baseload - grid_production
        result = Report.add_col_df(grid_production, grid_consumption, "grid_production", "baseload", True)
        # baseload + solar_production
        result = Report.add_col_df(solar_production, result, "solar_production", "baseload")
        # baseload - ev_consumption
        result = Report.add_col_df(ev_consumption, result, "ev_consumption", "baseload", True)
        # baseload - wp_consumption
        result = Report.add_col_df(wp_consumption, result, "wp_consumption", "baseload", True)
        # baseload - boiler_consumption
        result = Report.add_col_df(boiler_consumption, result, "boiler_consumption", "baseload", True)
        # baseload - battery_consumption
        result = Report.add_col_df(battery_consumption, result, "battery_consumption", "baseload", True)
        # baseload - battery_production
        result = Report.add_col_df(battery_production, result, "battery_production", "baseload")

        result = result.groupby("uur", as_index=False).agg({"tijd": 'min', "weekdag": 'mean', "baseload": 'mean'})
        result.baseload = result.baseload.round(3)
        result = result['baseload'].values.tolist()
        return result

    def calc_save_baseloads(self):
        self.db_ha.connect()
        for weekday in range (7):
            baseload = self.calc_weekday_baseload(weekday)
            logging.info(f"baseload voor weekdag {weekday} :")
            bl_str = ""
            for x in baseload:
                bl_str += str(x) + " "
            logging.info(bl_str)
            out_file = "../data/baseload/baseload_" + str(weekday) +".json"
            with open(out_file, 'w') as f:
                print(json.dumps(baseload, indent=2), file=f)
        return

    #------------------------------------------------


    def get_field_data(self, field: str, periode: str):
        period = self.periodes[periode]
        self.db_ha.connect()
        if not (field in self.energy_balance_dict):
            result = None
            return result
        categorie = self.energy_balance_dict[field]
        df = self.db_da.getColumnData('values', field, start=period["vanaf"], end=period["tot"])
        df.index = pd.to_datetime(df["time"])
        df = df.rename(columns={"value": field})
        df["datasoort"] = "recorded"

        df_ha_result = pd.DataFrame()
        if len(df) > 0:
            last_moment = df['time'].iloc[-1] + datetime.timedelta(hours=1)
        else:
            last_moment = self.periodes[periode]["vanaf"]
        if last_moment < self.periodes[periode]["tot"]:
            count = 0
            for sensor in categorie["sensors"]:
                df_ha = self.get_sensor_data(sensor, last_moment, period["tot"], field)
                df_ha.index = pd.to_datetime(df_ha["tijd"])
                if count == 0:
                    df_ha_result = df_ha
                else:
                    df_ha_result = self.add_col_df(df_ha, df_ha_result, field)
                count += 1
            df_ha_result['datasoort'] = 'recorded'
            df_ha_result = df_ha_result.rename(columns={"tijd": "time"})
            if len(df_ha_result) > 0:
                last_moment = df_ha_result['time'].iloc[-1] + datetime.timedelta(hours=1)
            df_ha_result['time'] = df_ha_result['time'].apply(lambda x: x.strftime("%Y-%m-%d %H:%M"))

        if last_moment < self.periodes[periode]["tot"]:
            df_prog = self.db_da.getColumnData('prognoses', field, start=last_moment, end=period["tot"])
            df_prog.index = pd.to_datetime(df_prog["time"])
            df_prog = df_prog.rename(columns={"value": field})
            df_prog['datasoort'] = 'expected'
            df_uur = pd.concat([df_ha_result, df_prog])
        else:
            df_uur = df_ha_result
        df = pd.concat([df, df_uur])
        return df

    def get_price_data(self, start, end):
        from dao.prog.utils import get_value_from_dict
        df_da = self.db_da.getColumnData('values', "da", start=start, end=end)
        old_dagstr = ""
        taxes_l = 0
        taxes_t = 0
        ol_l = 0
        ol_t = 0
        btw = 0
        columns = ["time", "da_ex", "da_cons", 'da_prod', "datasoort"]
        df = pd.DataFrame(columns=columns)
        for row in df_da.itertuples():
            if pd.isnull(row.time):
                continue
            dag_str = row.time[:10]
            if dag_str != old_dagstr:
                ol_l = get_value_from_dict(dag_str, self.ol_l_def)
                ol_t = get_value_from_dict(dag_str, self.ol_t_def)
                taxes_l = get_value_from_dict(dag_str, self.taxes_l_def)
                taxes_t = get_value_from_dict(dag_str, self.taxes_t_def)
                btw = get_value_from_dict(dag_str, self.btw_def)
                old_dagstr = dag_str
            da_cons = (row.value + taxes_l + ol_l) * (1 + btw / 100)
            da_prod = (row.value + taxes_t + ol_t) * (1 + btw / 100)
            df.loc[df.shape[0]] = [datetime.datetime.strptime(row.time,"%Y-%m-%d %H:%M"), row.value, da_cons, da_prod, row.datasoort]
        return df

    def get_api_data(self, field: str, periode: str, cumulate: bool = False):
        self.db_da.connect()
        periode = periode.replace("_", " ")
        grid_fields = ["consumption", "production", "netto_consumption", "cost", "profit", "netto_cost"]
        df = pd.DataFrame()
        if field in ["grid"] + grid_fields:  # grid data
            df_grid = self.get_grid_data(periode)
            df_grid['time'] = df_grid['vanaf'].apply(lambda x: pd.to_datetime(x).strftime("%Y-%m-%d %H:%M"))
            if field in grid_fields:
                df = df_grid[['time', field, "datasoort"]].copy()
                if cumulate:
                    df[field] = df_grid[field].cumsum()
                df.rename({field: 'value'}, axis=1, inplace=True)
            if field == "grid":
                df = df_grid[['time', 'datasoort'] + grid_fields].copy()
                if cumulate:
                    for field in grid_fields:
                        df[field] = df[field].cumsum()
        elif field == 'da':
            df = self.get_price_data(self.periodes[periode]["vanaf"], self.periodes[periode]["tot"])
        else:
            if not (field in self.energy_balance_dict):
                result = '{"message":"Failed"}'
                return result
            df = self.get_field_data(field, periode)

        history_df = df[df['datasoort'] == 'recorded']
        history_df = history_df.drop('datasoort', axis=1)
        history_json = history_df.to_json(orient='records')
        expected_df = df[df['datasoort'] == 'expected']
        expected_df = expected_df.drop('datasoort', axis=1)
        expected_json = expected_df.to_json(orient='records')
        result = '{ "message":"Success", "recorded": ' + history_json + ', "expected" : ' + expected_json + ' }'
        return result

    def make_graph(self, df, period, _options=None):
        if _options:
            options = _options
        else:
            options = {
                "title": "Grafiek verbruik",
                "style": self.config.get(["graphics", "style"]),
                 "vaxis": [{
                    "title": "kWh"
                    },
                    {"title": "euro"
                     }
                ],
                "series": [{"column": "Verbruik",
                            "title": "Verbruik",
                            "type": "stacked",
                            "color": '#00bfff'
                            },
                           {"column": "Productie",
                            "title": "Productie",
                            "negativ": "true",
                            "type": "stacked",
                            "color": 'green'
                            },
                           {"column": "Kosten",
                            "label": "Kosten",
                            "type": "stacked",
                            "color": 'red',
                            "vaxis": "right"
                            },
                           {"column": "Opbrengst",
                            "label": "Opbrengst",
                            "negativ": "true",
                            "type": "stacked",
                            "color": '#ff8000',
                            "vaxis": "right"
                            },
                           ]
            }
        options["haxis"]= {
            "values": self.periodes[period]["interval"].capitalize(),
            "title": self.periodes[period]["interval"] + " van " + period
        }

        gb = GraphBuilder()
        fig = gb.build(df, options, False)
        buf = BytesIO()
        fig.savefig(buf, format="png")
        # Embed the result in the html output.
        report_data = base64.b64encode(buf.getbuffer()).decode("ascii")
        return report_data
