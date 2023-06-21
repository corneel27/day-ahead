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
        self.report_options = self.config.get(["report"])
        #vandaag
        now = datetime.datetime.now()
        vanaf = datetime.datetime(now.year,now.month,now.day)
        tot = vanaf + datetime.timedelta(days=1)
        interval = "uur"
        self.periodes.update(create_dict("vandaag", vanaf, tot, interval))
        #gisteren
        tot = vanaf
        vanaf = vanaf + datetime.timedelta(days=-1)
        self.periodes.update(create_dict("gisteren", vanaf, tot, interval))
        #deze week
        tot = vanaf + datetime.timedelta(days=2)
        if tot.weekday() == 0:
            delta =7
        else:
            delta = tot.weekday()
        vanaf = tot + datetime.timedelta(days= - delta)
        self.periodes.update(create_dict("deze week", vanaf, tot, "dag"))
        #vorige week
        vanaf = vanaf + datetime.timedelta(days = -7)
        tot = vanaf + datetime.timedelta(days = 7)
        self.periodes.update(create_dict("vorige week", vanaf, tot, "dag"))
        #deze maand
        vanaf = datetime.datetime(now.year,now.month,1)
        tot = vanaf + relativedelta(months=1)
        self.periodes.update(create_dict("deze maand", vanaf, tot, "dag"))
        #vorige maand
        tot = vanaf
        vanaf = vanaf + relativedelta(months=-1)
        self.periodes.update(create_dict("vorige maand", vanaf, tot, "dag"))
        #dit jaar
        vanaf = datetime.datetime(now.year,1,1)
        tot = datetime.datetime(now.year,now.month,now.day) + datetime.timedelta(days=1)
        self.periodes.update(create_dict("dit jaar", vanaf, tot, "maand"))
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

    def get_grid_data(self, periode:str, _vanaf=None, _tot=None):
        periode_d= self.periodes[periode]
        vanaf = _vanaf if _vanaf else periode_d["vanaf"]
        tot = _tot if _tot else periode_d["tot"]
        #btw_def = self.prices_options["vat"]
        sql = "SELECT from_unixtime(t1.`time`) tijd,  " \
            "t1.`value` consumed,t2.`value` produced, t3.`value` price "\
            "FROM `values` AS t1, `values` AS t2, `values` AS t3, `variabel`AS v1, `variabel` AS v2, `variabel` AS v3 "\
            "WHERE (t1.`time`= t2.`time`) AND (t1.`time`= t3.`time`)" \
            "AND (v1.`code` ='cons')AND (v2.`code` = 'prod') AND (v3.`code` = 'da') " \
            "AND (v1.id = t1.variabel) AND (v2.id = t2.variabel) AND (v3.id = t3.variabel)" \
            "AND t1.`time` >= UNIX_TIMESTAMP('"+str(vanaf)+"') AND t1.`time` < UNIX_TIMESTAMP('"+str(tot)+"')"

        self.db_da.connect()
        result = self.db_da.run_select_query(sql)
        if result.shape[0] == 0:
            last_moment = vanaf #datetime.datetime.combine(vanaf, datetime.time(0,0)) - datetime.timedelta(hours=1)
        else:
            last_moment = result['tijd'].iloc[-1] + datetime.timedelta(hours=1)
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
                    df_result = self.get_sensor_data(sensor, last_moment + datetime.timedelta(hours=-1), tot, "consumed")
                    df_result.index = pd.to_datetime(df_result["tijd"])
                else:
                    df_2 = self.get_sensor_data(sensor, last_moment + datetime.timedelta(hours=-1), tot, "consumed")
                    df_2.index = pd.to_datetime(df_2["tijd"])
                    df_result = self.add_col_df(df_2, df_result, "consumed")
                    #df_cons = df_cons.merge(df_2, on=['tijd']).set_index(['tijd']).sum(axis=1)
                count =+ 1
            count= 0
            for sensor in self.report_options["entities grid production"]:
                df_p = self.get_sensor_data(sensor, last_moment + datetime.timedelta(hours=-1), tot, "produced")
                df_p.index = pd.to_datetime(df_p["tijd"])
                if count == 0:
                    df_result = self.copy_col_df(df_p, df_result, "produced")
                else:
                    df_result = self.add_col_df(df_p, df_result, "produced")
                count =+ 1
            df_prices.index = pd.to_datetime(df_prices["tijd"])
            df_result= self.copy_col_df(df_prices, df_result, "price")
            result = pd.concat([result, df_result])

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
        columns = [first_col, "Verbruik", "Productie", "Netto verbr.", "Kosten", "Opbrengst", "Netto kosten", "Tarief"]
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
        report_df = report_df.reset_index()
        old_dagstr = ""
        for row in report_df.itertuples():
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
            fi_df.loc[fi_df.shape[0]] = [tijd_str, col_1, col_2, col_3, col_4, col_5, col_6, col_7]

        #fi_df.set_index([columns[0][0]])
        fi_df = fi_df.groupby([first_col], as_index=False).agg({"Verbruik":'sum', "Productie":'sum',
            "Netto verbr.":'sum', "Kosten":'sum', "Opbrengst":'sum', "Netto kosten":'sum', "Tarief":'mean'})
        if active_view == "tabel":
            fi_df.loc["Total"] = fi_df.sum(axis=0, numeric_only=True)
            fi_df.at[fi_df.index[-1], first_col] = "Totaal"
            #value = fi_df.iloc[-1][7]
            #fi_df.at[fi_df.index[-1], "Tarief"] = value / (len(fi_df.index)-1)

            #fi_df.loc[fi_df.shape[0]] = ["Totaal", col_1_tot, col_2_tot, col_3_tot, col_4_tot, col_5_tot, col_6_tot,
            #                         col_7_tot / count_tot]
            columns = [columns]
            columns.append(["", "kWh", "kWh", "kWh", "eur", "eur", "eur", "eur/kWh"])
            fi_df.columns = columns
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
