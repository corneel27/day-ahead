import numpy
import pandas as pd
import datetime
import calendar
from dateutil.relativedelta import relativedelta
from prog.db_manager import DBmanagerObj
from prog.da_config import Config
from prog.utils import *

class Report ():
    periodes = {}

    def __init__(self):
        def create_dict(name, vanaf, tot, interval):
            return {name: {"vanaf": vanaf, "tot": tot, "interval": interval}}

        self.config = Config("../data/options.json")
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

        self.prices_options = self.config.get(["prices"])
        self.report_options = self.config.get(["report"])
        #vandaag
        now = datetime.datetime.now()
        vanaf = datetime.datetime(now.year,now.month,now.day)
        tot = vanaf + datetime.timedelta(days=1)
        interval = "uur"
        self.periodes.update(create_dict("vandaag", vanaf, tot, interval))
        #gisteren
        tot = vanaf
        vanaf += datetime.timedelta(days=-1)
        self.periodes.update(create_dict("gisteren", vanaf, tot, interval))
        #deze week
        tot = vanaf + datetime.timedelta(days=2)
        if tot.weekday() == 0:
            delta =7
        else:
            delta = tot.weekday()
        vanaf = tot + datetime.timedelta(days=- delta)
        self.periodes.update(create_dict("deze week", vanaf, tot, "dag"))
        #vorige week
        vanaf += datetime.timedelta(days=-7)
        tot = vanaf + datetime.timedelta(days=7)
        self.periodes.update(create_dict("vorige week", vanaf, tot, "dag"))
        #deze maand
        vanaf = datetime.datetime(now.year,now.month,1)
        tot = vanaf + relativedelta(months=1)
        self.periodes.update(create_dict("deze maand", vanaf, tot, "dag"))
        #vorige maand
        tot = vanaf
        vanaf += relativedelta(months=-1)
        self.periodes.update(create_dict("vorige maand", vanaf, tot, "dag"))
        #dit jaar
        vanaf = datetime.datetime(now.year,1,1)
        tot = datetime.datetime(now.year,now.month,now.day) + datetime.timedelta(days=1)
        self.periodes.update(create_dict("dit jaar", vanaf, tot, "maand"))
        #dit contractjaar
        vanaf = datetime.datetime.strptime(self.prices_options['last invoice'], "%Y-%m-%d")
        now = datetime.datetime.now()
        tot = datetime.datetime(now.year,now.month,now.day)
        tot = tot + datetime.timedelta(days=1)
        self.periodes.update(create_dict("dit contractjaar", vanaf, tot, "maand"))
        return

    def get_sensor_data(self, sensor: str, vanaf: datetime.datetime, tot: datetime.datetime, col_name:str) -> pd.DataFrame :
        """
        vanaf last_moment + datetime.timedelta(hours=-1)
        """
        sql = "SELECT FROM_UNIXTIME(t2.`start_ts`) 'tijd', " \
          "round(t2.state - t1.`state`,3) '" + col_name +"' " \
          "FROM `statistics` t1,`statistics` t2, `statistics_meta` " \
          "WHERE statistics_meta.`id` = t1.`metadata_id` AND statistics_meta.`id` = t2.`metadata_id` " \
          "AND statistics_meta.`statistic_id` = '" + sensor + "' " \
          "AND (t2.`start_ts` = t1.`start_ts` + 3600) " \
          "AND t1.`state` IS NOT null AND t2.`state` IS NOT null " \
          "AND FROM_UNIXTIME(t1.`start_ts`) BETWEEN '" + str(vanaf) + "' " \
          "AND '" + str(tot) + "' ORDER BY t1.`start_ts`;"
        # print(sql)
        df_sensor = self.db_ha.run_select_query(sql)
        #print(df_sensor)
        return df_sensor

    def copy_col_df(self, copy_from, copy_to, col_name):
        copy_to [col_name] = 0
        #copy_from = copy_from.reset_index()
        for row in copy_from.itertuples():
            copy_to.at[row.tijd, col_name] = copy_from.at[row.tijd, col_name]
        return copy_to

    def add_col_df(self, add_from, add_to, col_name):
        #add_from = add_from.reset_index()
        for row in add_from.itertuples():
            add_to.at[row.tijd, col_name] = add_to.at[row.tijd, col_name] + add_from.at[row.tijd, col_name]
        return add_to

    def recalc_df_ha(self, org_data_df : pd.DataFrame, interval:str) -> pd.DataFrame:
        """

        """
        fi_df = pd.DataFrame(columns=[interval, "vanaf", "tot", "consumed", "produced", "cost", "profit"])
        if len(org_data_df.index) == 0:
            return fi_df
        prices_options = self.config.get(["prices"])
        taxes_l_def = prices_options["energy taxes delivery"]  # eb + ode levering
        ol_l_def = prices_options["cost supplier delivery"]  # opslag kosten leverancier
        taxes_t_def = self.prices_options["energy taxes redelivery"]  # eb+ode teruglevering
        ol_t_def = self.prices_options["cost supplier redelivery"]
        btw_def = self.prices_options["vat"]
        #        report_df = report_df.reset_index()
        old_dagstr = ""
        for row in org_data_df.itertuples():
            if pd.isnull(row.tijd):
                continue
            dag_str = row.tijd.strftime("%Y-%m-%d")
            if dag_str != old_dagstr:
                ol_l = get_value_from_dict(dag_str, ol_l_def)
                ol_t = get_value_from_dict(dag_str, ol_t_def)
                taxes_l = get_value_from_dict(dag_str, taxes_l_def)
                taxes_t = get_value_from_dict(dag_str, taxes_t_def)
                btw = get_value_from_dict(dag_str, btw_def)
                old_dagstr = dag_str
            if interval == "uur":
                tijd_str = str(row.tijd)[10:16]
            elif interval == "dag":
                tijd_str = str(row.tijd)[0:10]
            else:
                tijd_str = str(row.tijd)[0:7]  # jaar maand
            col_1 = row.consumed
            col_2 = row.produced
            col_3 = (row.consumed * (row.price + taxes_l + ol_l)) * (1 + btw / 100)
            col_4 = (row.produced * (row.price + taxes_t + ol_t)) * (1 + btw / 100)
            fi_df.loc[fi_df.shape[0]] = [tijd_str, row.tijd, row.tijd + datetime.timedelta(hours=1), col_1, col_2, col_3, col_4]
        if interval != "uur":
            fi_df = fi_df.groupby([interval], as_index=False).agg({"vanaf": 'min', "tot" : 'max', "consumed": 'sum',
                                                               "produced": 'sum', "cost": 'sum', "profit": 'sum'})
        return fi_df

    def get_grid_data(self, periode:str, _vanaf=None, _tot=None):
        self.db_da.connect()
        periode_d= self.periodes[periode]
        vanaf = _vanaf if _vanaf else periode_d["vanaf"]
        tot = _tot if _tot else periode_d["tot"]
        interval = periode_d["interval"]
        '''
        sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
            "t1.`value` consumed,t2.`value` produced, t3.`value` price "\
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
            sql = "SELECT concat(year(from_unixtime(t1.`time`)),LPAD(MONTH(from_unixtime(t1.`time`)),3, ' ')) AS 'maand', " \
                "MIN(from_unixtime(t1.`time`)) AS 'vanaf', MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                "sum(t1.`value`) consumed,sum(t2.`value`) produced, sum(t3.`value`) cost, SUM(t4.`value`) profit  " \
                "FROM `values` AS t1, `values` AS t2, `values` AS t3,`values` AS t4,  " \
                "`variabel`AS v1, `variabel` AS v2, `variabel` AS v3, `variabel` AS v4  " \
                "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)AND (t1.`time`= t4.`time`)AND  " \
                "(v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'cost') AND (v4.`code` = 'profit') AND  " \
                "(v1.id = t1.variabel) AND (v2.id = t2.variabel) AND (v3.id = t3.variabel)AND (v4.id = t4.variabel) AND  " \
                "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') " \
                "GROUP BY maand;"
        elif interval == "dag":
            sql = "SELECT date(from_unixtime(t1.`time`)) AS 'dag', " \
                "MIN(from_unixtime(t1.`time`)) AS 'vanaf', MAX(from_unixtime(t1.`time`)) AS 'tot', " \
                "sum(t1.`value`) consumed,sum(t2.`value`) produced, sum(t3.`value`) cost, SUM(t4.`value`) profit  " \
                "FROM `values` AS t1, `values` AS t2, `values` AS t3,`values` AS t4,  " \
                "`variabel`AS v1, `variabel` AS v2, `variabel` AS v3, `variabel` AS v4  " \
                "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)AND (t1.`time`= t4.`time`)AND  " \
                "(v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'cost') AND (v4.`code` = 'profit') AND  " \
                "(v1.id = t1.variabel) AND (v2.id = t2.variabel) AND (v3.id = t3.variabel)AND (v4.id = t4.variabel) AND  " \
                "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') " \
                "GROUP BY dag;"
        else: #interval == "uur"
            sql = "SELECT from_unixtime(t1.`time`) AS 'uur', " \
                "from_unixtime(t1.`time`) AS 'vanaf', from_unixtime(t1.`time`) AS 'tot', " \
                "t1.`value` consumed, t2.`value` produced, t3.`value` cost, t4.`value` profit  " \
                "FROM `values` AS t1, `values` AS t2, `values` AS t3,`values` AS t4,  " \
                "`variabel`AS v1, `variabel` AS v2, `variabel` AS v3, `variabel` AS v4  " \
                "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)AND (t1.`time`= t4.`time`)AND  " \
                "(v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'cost') AND (v4.`code` = 'profit') AND  " \
                "(v1.id = t1.variabel) AND (v2.id = t2.variabel) AND (v3.id = t3.variabel)AND (v4.id = t4.variabel) AND  " \
                "t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"') ;"

        result = self.db_da.run_select_query(sql)
        result.index = pd.to_datetime(result["vanaf"])

        if result.shape[0] == 0:
            last_moment = vanaf #datetime.datetime.combine(vanaf, datetime.time(0,0)) - datetime.timedelta(hours=1)
        else:
            last_moment = result['tot'].iloc[-1] + datetime.timedelta(hours=1)
        if last_moment < tot:
            #get the prices:
            sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
                  " t1.`value` price " \
                  "FROM `values` AS t1,  `variabel` AS v1  " \
                  "WHERE v1.`code` ='da' " \
                  "AND v1.id = t1.variabel " \
                  "AND t1.`time` >= UNIX_TIMESTAMP('" + str(last_moment) + "') " \
                  "AND t1.`time` < UNIX_TIMESTAMP('" + str(tot) + "')"
            #print (sql)
            df_prices = self.db_da.run_select_query(sql)
            #print(df_prices)

            self.db_ha.connect()
            count = 0
            for sensor in self.report_options["entities grid consumption"]:
                if count==0:
                    df_ha = self.get_sensor_data(sensor, last_moment + datetime.timedelta(hours=-1), tot, "consumed")
                    df_ha.index = pd.to_datetime(df_ha["tijd"])
                else:
                    df_2 = self.get_sensor_data(sensor, last_moment + datetime.timedelta(hours=-1), tot, "consumed")
                    df_2.index = pd.to_datetime(df_2["tijd"])
                    df_ha = self.add_col_df(df_2, df_ha, "consumed")
                    #df_cons = df_cons.merge(df_2, on=['tijd']).set_index(['tijd']).sum(axis=1)
                count =+ 1
            count= 0
            for sensor in self.report_options["entities grid production"]:
                df_p = self.get_sensor_data(sensor, last_moment + datetime.timedelta(hours=-1), tot, "produced")
                df_p.index = pd.to_datetime(df_p["tijd"])
                if count == 0:
                    df_ha = self.copy_col_df(df_p, df_ha, "produced")
                else:
                    df_ha = self.add_col_df(df_p, df_ha, "produced")
                count =+ 1
            df_prices.index = pd.to_datetime(df_prices["tijd"])
            df_ha = self.copy_col_df(df_prices, df_ha, "price")
            df_ha = self.recalc_df_ha(df_ha, interval)

            result = pd.concat([result, df_ha])

        return result

    def get_last_day_month(self, input_dt:datetime):
        # Get the last day of the month from a given datetime
        res = calendar.monthrange(input_dt.year, input_dt.month)
        return res[1]
        
    def calc_columns(self, report_df, active_interval, active_view):
        first_col = active_interval.capitalize()
        #if active_subject == "verbruik":
        #    columns.extend(["Verbruik", "Productie", "Netto"])
        #    columns = [columns]
        #    columns.append(["", "kWh", "kWh", "kWh"])
        #else:  #kosten
        columns = [first_col, "Verbruik", "Productie", "Netto verbr.", "Kosten", "Opbrengst", "Netto kosten"]
        #columns.extend(ext_columns)
        fi_df = pd.DataFrame(columns=columns)
        if len(report_df.index) == 0:
            return fi_df
        prices_options = self.config.get(["prices"])
        taxes_l_def = prices_options["energy taxes delivery"]  # eb + ode levering
        ol_l_def = prices_options["cost supplier delivery"]  # opslag kosten leverancier
        taxes_t_def = self.prices_options["energy taxes redelivery"]  # eb+ode teruglevering
        ol_t_def = self.prices_options["cost supplier redelivery"]
        btw_def = self.prices_options["vat"]
#        report_df = report_df.reset_index()
        old_dagstr = ""
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
                tijd_str = str(row.vanaf)[0:7]  #jaar maand
            col_1 = row.consumed
            col_2 = row.produced
            col_3 = col_1 - col_2
            if math.isnan(row.cost) :
                col_4 = (row.consumed * (row.price + taxes_l + ol_l)) * (1 + btw / 100)
            else:
                col_4 = row.cost
            if math.isnan(row.profit):
                col_5 = (row.produced * (row.price + taxes_t + ol_t)) * (1 + btw / 100)
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

        #, "Tarief verbr.", "Tarief prod."
        #, "Tarief verbr.":'mean', "Tarief prod.":"mean"
        #fi_df.set_index([columns[0][0]])
        fi_df = fi_df.groupby([first_col], as_index=False).agg({"Verbruik":'sum', "Productie":'sum',
            "Netto verbr.":'sum', "Kosten":'sum', "Opbrengst":'sum', "Netto kosten":'sum'})
        fi_df['Tarief verbr.'] = fi_df.apply(lambda row: row.Kosten / row.Verbruik if row.Verbruik != 0.0 else row.Verbruik, axis = 1)
        fi_df['Tarief prod.'] = fi_df.apply(lambda row: row.Opbrengst / row.Productie if row.Productie != 0.0 else row.Productie, axis = 1)
        if active_view == "tabel":
            fi_df.loc["Total"] = fi_df.sum(axis=0, numeric_only=True)
            fi_df.at[fi_df.index[-1], first_col] = "Totaal"
            row = fi_df.iloc[-1]
            fi_df.at[fi_df.index[-1], "Tarief verbr."] = row.Kosten/row.Verbruik
            fi_df.at[fi_df.index[-1], "Tarief prod."] = row.Opbrengst/row.Productie
            #value = fi_df.iloc[-1][7]
            #fi_df.at[fi_df.index[-1], "Tarief"] = value / (len(fi_df.index)-1)

            #fi_df.loc[fi_df.shape[0]] = ["Totaal", col_1_tot, col_2_tot, col_3_tot, col_4_tot, col_5_tot, col_6_tot,
            #                         col_7_tot / count_tot]
            columns = fi_df.columns.values.tolist()
            #columns.append(["", "kWh", "kWh", "kWh", "eur", "eur", "eur", "eur/kWh",  "eur/kWh"])
            #columns = [columns,
            fi_df.columns = [columns, ["", "kWh", "kWh", "kWh", "eur", "eur", "eur", "eur/kWh",  "eur/kWh"]]
        fi_df = fi_df.round(3)
        return fi_df

    '''        
     def group_rows(self, report_df, active_interval, active_view):      
        col_1 = col_2 = col_3 = col_4 = col_5 = col_6 = col_7 = 0
        col_1_tot = col_2_tot = col_3_tot = col_4_tot = col_5_tot = col_6_tot = col_7_tot = 0
        col_1_subtot = col_2_subtot = col_3_subtot =col_4_subtot = col_5_subtot = col_6_subtot = col_7_subtot = 0
        count_tot = count_subtot = 0
        fi_df = pd.DataFrame(columns=columns)
        if len(report_df.index) == 0:
            return fi_df
        time_last_row = report_df['tijd'].iloc[-1]
        report_df = report_df.reset_index()
        for row in report_df.itertuples():
            if pd.isnull(row.tijd):
                continue
            dag_str = row.tijd.strftime("%Y-%m-%d")
            ol_l = get_value_from_dict(dag_str, ol_l_def)
            ol_t = get_value_from_dict(dag_str, ol_t_def)
            taxes_l = get_value_from_dict(dag_str, taxes_l_def)
            taxes_t = get_value_from_dict(dag_str, taxes_t_def)
            btw = get_value_from_dict(dag_str, btw_def)
            if active_interval=="uur":
                tijd_str = str(row.tijd)[10:16]
            elif active_interval=="dag":
                tijd_str = str(row.tijd)[0:10]
            else: 
                tijd_str = str(row.tijd)[0:7]  #jaar maand
            col_1 = row.consumed
            col_2 = row.produced
            col_3 = col_1 - col_2
            col_4 = (row.consumed * (row.price + taxes_l + ol_l)) * (1 + btw / 100)
            col_5 = (row.produced * (row.price + taxes_t + ol_t)) * (1 + btw / 100)
            col_6 = col_4 - col_5
            col_7 = (row.price + taxes_l + ol_l) * (1 + btw / 100)
            col_1_subtot += col_1
            col_2_subtot += col_2
            col_3_subtot += col_3
            col_4_subtot += col_4
            col_5_subtot += col_5
            col_6_subtot += col_6
            col_7_subtot += col_7
            count_subtot += 1
            if active_interval == "uur":
                fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1, col_2, col_3, col_4, col_5, col_6, col_7]
            else:
                if pd.isnull(row.tijd) or (row.tijd == time_last_row) or  \
                    (active_interval == "dag" and str(row.tijd)[11:16] == "23:00") or \
                    (active_interval == "maand" and str(row.tijd)[11:16] == "23:00" and row.tijd.day == self.get_last_day_month(row.tijd)):
                    #if active_subject == "verbruik":
                    #    fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1_subtot, col_2_subtot, col_3_subtot]
                    #else:
                    fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1_subtot, col_2_subtot, col_3_subtot,
                                                 col_4_subtot, col_5_subtot, col_6_subtot,
                                                 col_7_subtot/count_subtot]
                    col_1_tot += col_1_subtot
                    col_2_tot += col_2_subtot
                    col_3_tot += col_3_subtot
                    col_4_tot += col_4_subtot
                    col_5_tot += col_5_subtot
                    col_6_tot += col_6_subtot
                    col_7_tot += col_7_subtot
                    count_tot += count_subtot
                    col_1_subtot = col_2_subtot = col_3_subtot = col_4_subtot = col_5_subtot = col_6_subtot = col_7_subtot = 0
                    count_subtot = 0
        if count_subtot > 0:
            if active_interval != "uur":
                #if active_subject == "verbruik":
                #    fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1_subtot, col_2_subtot, col_3_subtot]
                #else:
                fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1_subtot, col_2_subtot, col_3_subtot, col_4_subtot,
                                             col_5_subtot, col_6_subtot, col_7_subtot / count_subtot]

            col_1_tot += col_1_subtot
            col_2_tot += col_2_subtot
            col_3_tot += col_3_subtot
            col_4_tot += col_4_subtot
            col_5_tot += col_5_subtot
            col_6_tot += col_6_subtot
            col_7_tot += col_7_subtot
            count_tot += count_subtot
        if active_view=="tabel":
            fi_df.loc[fi_df.shape[0]] = ["Totaal", col_1_tot, col_2_tot, col_3_tot, col_4_tot, col_5_tot, col_6_tot,
                                     col_7_tot/count_tot]
        fi_df = fi_df.round(3)
        return fi_df
        '''


report_def = Report()
#print (report_def.periodes)
df = report_def.get_grid_data("vandaag")
#print(df)
