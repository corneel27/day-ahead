
import calendar
from dateutil.relativedelta import relativedelta
from prog.db_manager import DBmanagerObj
from prog.da_config import Config
from prog.utils import *
from prog.da_graph import GraphBuilder
import base64
from io import BytesIO


class Report:
    periodes = {}

    def __init__(self):
        self.config = Config("../data/options.json")
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
        self.categorie_distr = {
            "cons":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "Verbruik",
                 "sensors": self.report_options["entities grid consumption"],
                 },
            "prod":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Productie",
                 "sensors": self.report_options["entities grid production"],
                 },
            "bat_out":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "Accu_uit",
                 "sensors": ["sensor.ess_grid_consumption"]
                 },
            "bat_in":
                {"dim": "kWh",
                 "sign": "neg",
                 "name": "Accu in",
                 "sensors": ["sensor.ess_grid_production"]
                 },
            "pv_ac":
                {"dim": "kWh",
                 "sign": "pos",
                 "name": "PV ac",
                 "sensors": ["sensor.solaredge_woning_ac_energy_kwh", "sensor.solaredge_garage_ac_energy_kwh_2"]
                 },
            "wp":
                {"dim": "kWh",
                 "sign": "neg",
                 "//code": ["wp", "boiler"],
                 "name": "WP",
                 "sensors": ["sensor.youless_meterstand"]
                 },
            "base":
                {"dim": "kWh",
                 "sign": "neg",
                 "code": "Overig",
                 "sensors": ["Verbruik", "Production", "Accu uit", "Accu in", "PV ac", "WP"],
                 },
        }

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
        return

    def get_sensor_data(self, sensor: str, vanaf: datetime.datetime, tot: datetime.datetime,
                        col_name: str) -> pd.DataFrame:
        """
        Vanaf last_moment + datetime.timedelta(hours=-1)
        """
        # sql = "SET time_zone='CET';"
        # self.db_ha.run_sql(sql)
        # vanaf_ts = int(vanaf.timestamp())
        # tot_ts = int(tot.timestamp()-7200)
        sql = "SELECT FROM_UNIXTIME(t2.`start_ts`) 'tijd', " \
              "round(t2.state - t1.`state`,3) '" + col_name + "' " \
              "FROM `statistics` t1,`statistics` t2, `statistics_meta` " \
              "WHERE statistics_meta.`id` = t1.`metadata_id` AND statistics_meta.`id` = t2.`metadata_id` " \
              "AND statistics_meta.`statistic_id` = '" + sensor + "' " \
              "AND (t2.`start_ts` = t1.`start_ts` + 3600) " \
              "AND t1.`state` IS NOT null AND t2.`state` IS NOT null " \
              "AND t1.`start_ts` >= UNIX_TIMESTAMP('" + str(vanaf) + "') - 3600 " \
              "AND t1.`start_ts` < UNIX_TIMESTAMP('" + str(tot) + "') - 3600 " \
              "ORDER BY t1.`start_ts`;"
        #            "AND FROM_UNIXTIME(t1.`start_ts`) BETWEEN '" + str(vanaf) + "' " \
        #            "AND '" + str(tot) + "' ORDER BY t1.`start_ts`;"
        #            "AND t1.`start_ts` < " + str(tot_ts) + " ORDER BY t1.`start_ts`;"
        print(sql)
        df = self.db_ha.run_select_query(sql)
        # print(df_sensor)
        return df

    @staticmethod
    def copy_col_df(copy_from, copy_to, col_name):
        copy_to[col_name] = 0
        # copy_from = copy_from.reset_index()
        for row in copy_from.itertuples():
            copy_to.at[row.tijd, col_name] = copy_from.at[row.tijd, col_name]
        return copy_to

    @staticmethod
    def add_col_df(add_from, add_to, col_name):
        # add_from = add_from.reset_index()
        for row in add_from.itertuples():
            add_to.at[row.tijd, col_name] = add_to.at[row.tijd, col_name] + add_from.at[row.tijd, col_name]
        return add_to

    def recalc_df_ha(self, org_data_df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """

        """
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

    def aggregate_df(self, result: pd.DataFrame, interval: str):
        result.rename(columns={"tijd": "vanaf"})
        result["tot"] = result["vanaf"]
        columns = [interval] + result.columns

        agg_dict = {"vanaf": 'min', "tot": 'max'}
        for key, categorie in self.categorie_distr.items():
            agg_dict[key] = 'sum'
        # TODO nog afmaken
        return result

    def get_distribution_data(self, periode, _vanaf=None, _tot=None):
        self.db_da.connect()
        self.db_ha.connect()
        periode_d = self.periodes[periode]
        vanaf = _vanaf if _vanaf else periode_d["vanaf"]
        tot = _tot if _tot else periode_d["tot"]
        interval = periode_d["interval"]
        cat_count = 0
        result = pd.DataFrame()
        for key, categorie in self.categorie_distr.items():
            '''
            if interval == "maand":
                sql = "SELECT concat(year(from_unixtime(t1.`time`)),LPAD(MONTH(from_unixtime(t1.`time`)),3, ' ')) "\
                      "AS 'maand', " \
                    "MIN(from_unixtime(t1.`time`)) AS 'vanaf', MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                    "sum(t1.`value`) " + key + ", " \
                    " 'recorded' as 'datasoort' " \
                    "FROM `values` AS t1, `variabel`AS v1  " \
                    "WHERE (v1.`code` = '" + code +"') AND (v1.id = t1.variabel) AND  " \
                    "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') " \
                    "GROUP BY maand;"
            elif interval == "dag":
                sql = "SELECT date(from_unixtime(t1.`time`)) AS 'dag', " \
                    "MIN(from_unixtime(t1.`time`)) AS 'vanaf', MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                    "sum(t1.`value`) " + key + ", " \
                    " 'recorded' as 'datasoort' " \
                    "FROM `values` AS t1, `variabel`AS v1  " \
                    "WHERE (v1.`code` = '" + code +"') AND (v1.id = t1.variabel) AND  " \
                    "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') " \
                    "GROUP BY dag;"
            else:  # interval == "uur"
            '''
            sql = "SELECT from_unixtime(t1.`time`) AS 'tijd', " \
                  "t1.`value` " + categorie["name"] + ", " \
                  " 'recorded' as 'datasoort' " \
                  "FROM `values` AS t1, `variabel`AS v1  " \
                  "WHERE (v1.`code` = '" + key + "') AND (v1.id = t1.variabel) AND  " \
                  "t1.`time`>= UNIX_TIMESTAMP('" + str(vanaf) + "') AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "');"
            print(sql)
            code_result = self.db_da.run_select_query(sql)
            code_result.index = pd.to_datetime(code_result["vanaf"])
            if cat_count == 0:
                result = code_result
            else:
                self.copy_col_df(code_result, result, key)

            if code_result.shape[0] == 0:
                # datetime.datetime.combine(vanaf, datetime.time(0,0)) - datetime.timedelta(hours=1)
                last_moment = vanaf
            else:
                last_moment = code_result['tot'].iloc[-1] + datetime.timedelta(hours=1)
            if last_moment < tot:
                result_ha = pd.DataFrame()
                sensor_count = 0
                for sensor in categorie["sensors"]:
                    if sensor_count == 0:
                        result_ha = self.get_sensor_data(sensor, last_moment, tot, key)
                        result_ha.index = pd.to_datetime(result_ha["tijd"])
                    else:
                        df_2 = self.get_sensor_data(sensor, last_moment, tot, key)
                        df_2.index = pd.to_datetime(df_2["tijd"])
                        result_ha = self.add_col_df(df_2, result_ha, key)
                    sensor_count = + 1
                if cat_count == 0:
                    result_ha['datasoort'] = "recorded"
                    result = pd.concat([result, result_ha])
                else:
                    self.copy_col_df(result_ha, result, key)
                if len(result_ha) > 0:
                    last_moment = result_ha['tijd'].iloc[-1] + datetime.timedelta(hours=1)
                else:
                    last_moment = vanaf

            if last_moment < tot:
                sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
                      " t1.`value` " + categorie["name"] + " " \
                      "FROM `prognoses` AS t1,  `variabel` AS v1  " \
                      "WHERE v1.`code` ='" + key + "' " \
                      "AND v1.id = t1.variabel " \
                      "AND t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + "') " \
                      "AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "');"
                df_prog = self.db_da.run_select_query(sql)
                df_prog.index = pd.to_datetime(df_prog["tijd"])
                # df_prog = self.copy_col_df(df_prod, df_prog, "production")
                if cat_count == 0:
                    df_prog["datasoort"] = "expected"
                    result = pd.concat([result, df_prog])
                else:
                    self.copy_col_df(df_prog, result, key)

            cat_count += 1
            result = self.aggregate_df(result, interval)
        return result

    def get_grid_data(self, periode: str, _vanaf=None, _tot=None, datasoort: str | None = None):
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
        :param datasoort: 
            recorded: alleen gerealiseerd (dus uiterlijk tot en met het voorlaatste uur)
            expected: alleen geprognotiseerd/berekend dus vanaf het huidige uur
            all = None: alle data zowel recorded als expected
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
                  "sum(t1.`value`) consumption,sum(t2.`value`) production, sum(t3.`value`) cost, " \
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

    def calc_grid_columns(self, report_df, active_interval, active_view):
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

    def get_field_data(self, field: str, periode: str):
        period = self.periodes[periode]
        self.db_ha.connect()
        if not (field in self.categorie_distr):
            result = None
            return result
        categorie = self.categorie_distr[field]
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
            df_da = self.db_da.getColumnData('values', field,
                                             start=self.periodes[periode]["vanaf"], end=self.periodes[periode]["tot"])
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
                df.loc[df.shape[0]] = [row.time, row.value, da_cons, da_prod, row.datasoort]
        else:
            if not (field in self.categorie_distr):
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
                "haxis": {
                    "values": self.periodes[period]["interval"].capitalize(),
                    "title": self.periodes[period]["interval"] + " van " + period
                },
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
        gb = GraphBuilder()
        fig = gb.build(df, options, False)
        buf = BytesIO()
        fig.savefig(buf, format="png")
        # Embed the result in the html output.
        report_data = base64.b64encode(buf.getbuffer()).decode("ascii")
        return report_data
