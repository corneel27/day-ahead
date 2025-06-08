from dao.prog.utils import get_value_from_dict
from dao.prog.da_config import Config
import pandas as pd
import asteval
import datetime


class Test_Formule:
    def __init__(self, file_name: str = "../data/options.json"):
        self.config = Config(file_name)
        self.db_da = self.config.get_db_da()
        self.db_ha = self.config.get_db_ha()
        self.prices_options = self.config.get(["prices"])
        # eb + ode levering
        self.taxes_l_def = self.prices_options["energy taxes consumption"]
        # opslag kosten leverancier
        self.ol_l_def = self.prices_options["cost supplier consumption"]
        # eb+ode teruglevering
        self.taxes_t_def = self.prices_options["energy taxes production"]
        self.ol_t_def = self.prices_options["cost supplier production"]
        self.btw_def = self.prices_options["vat consumption"]

    def get_price_data_old_style(self, start, end):
        df_da = self.db_da.get_column_data("values", "da", start=start, end=end)
        old_dagstr = ""
        taxes_l = 0
        taxes_t = 0
        ol_l = 0
        ol_t = 0
        btw = 0
        columns = ["time", "da_ex", "da_cons", "da_prod", "datasoort"]
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
            df.loc[df.shape[0]] = [
                datetime.datetime.strptime(row.time, "%Y-%m-%d %H:%M"),
                row.value,
                da_cons,
                da_prod,
                row.datasoort,
            ]
        print(df)
        return df

    def get_price_data_new_style(self, start, end):
        df_da = self.db_da.get_column_data("values", "da", start=start, end=end)
        old_dagstr = ""
        taxes_l = 0
        taxes_t = 0
        ol_l = 0
        ol_t = 0
        btw = 0
        columns = ["time", "da_ex", "da_cons", "da_prod", "datasoort"]
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
            df.loc[df.shape[0]] = [
                datetime.datetime.strptime(row.time, "%Y-%m-%d %H:%M"),
                row.value,
                da_cons,
                da_prod,
                row.datasoort,
            ]
        return df

    def tst_1(self, start: datetime.datetime, end: datetime.datetime):
        df_da = self.db_da.get_column_data("values", "da", start=start, end=end)
        old_symboles = {}
        columns = ["time", "da_ex", "da_cons", "da_prod", "datasoort"]
        df = pd.DataFrame(columns=columns)
        user_symbols = {}
        old_dagstr = ""
        formule_da_cons = "(da_ex + energy_taxes_consumption + cost_supplier_consumption) * (1 + vat_consumption/100)"
        formule_da_prod = "(da_ex + energy_taxes_production + cost_supplier_production) * (1 + vat_production/100) + (hour>=8) * (hour<=18) * (da_ex>0) * da_ex * 0.1"
        # formule_da_prod = "(hour>=8) * (hour<18) * (da_ex>0) * da_ex * 0.1"
        for row in df_da.itertuples():
            if pd.isnull(row.time):
                continue
            dag_str = row.time[:10]
            hour_str = row.time[11:13]
            hour = int(hour_str)
            user_symbols['hour'] = hour
            if dag_str != old_dagstr:
                for key, sub_dict in self.prices_options.items():
                    key = key.replace(" ", "_")
                    if key == "formule_da_cons":
                        formule_da_cons = get_value_from_dict(dag_str, sub_dict)
                    elif key == "formule_da_prod":
                        formule_da_prod = get_value_from_dict(dag_str, sub_dict)
                    if type(sub_dict).__name__ in ["float", "int"]:
                        user_symbols[key] = sub_dict
                    elif type(sub_dict).__name__ == "str":
                        pass
                    else:
                        value = get_value_from_dict(dag_str, sub_dict)
                        user_symbols[key] = value
            da_ex = row.value
            user_symbols["da_ex"] = da_ex
            user_symbols["da_cons"] = 0
            aeval = asteval.Interpreter(user_symbols=user_symbols)
            aeval.eval("da_cons=" + formule_da_cons)
            da_cons = aeval.symtable["da_cons"]
            da_prod = aeval.eval(formule_da_prod)
            df.loc[df.shape[0]] = [
                datetime.datetime.strptime(row.time, "%Y-%m-%d %H:%M"),
                da_ex,
                da_cons,
                da_prod,
                row.datasoort,
            ]
        print(df)
        return df


def main():
    tst_formule = Test_Formule()
    # df = tst_formule.get_price_data(datetime.datetime(2025,4,18), datetime.datetime(2025,4,21))
    # print(df)
    import time

    start_time = time.time()
    # your code
    elapsed_time = time.time() - start_time
    tst_formule.tst_1(datetime.datetime(2025, 5, 20), datetime.datetime(2025, 5, 22))
    elapsed_time = time.time() - start_time
    print(elapsed_time)
    start_time = time.time()
    tst_formule.get_price_data_old_style(
        datetime.datetime(2025, 5, 20), datetime.datetime(2025, 5, 21)
    )
    elapsed_time = time.time() - start_time
    print(elapsed_time)


main()
