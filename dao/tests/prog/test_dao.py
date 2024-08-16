import unittest
import datetime
import sys

import pandas as pd

sys.path.append("../../prog")
import dao.prog.da_report
import dao.prog.day_ahead
import logging


class TestReports(unittest.TestCase):

    def t_est_get_grid_data_sqlite(self):
        report = dao.prog.da_report.Report(file_name="../data/options_sqlite.json")
        for day in [datetime.datetime(2024, 7, 9), datetime.datetime(2024, 7, 10)]:
            vanaf = day  # datetime.datetime(2024, 7, 9)
            tot = day + datetime.timedelta(days=1)  # datetime.datetime(2024, 7, 10)

            df_ha = report.get_grid_data(periode='', _vanaf=vanaf, _tot=tot, _interval="uur", _source="ha")
            df_ha = report.calc_grid_columns(df_ha, "uur", "tabel")
            print(f"Eigen meterstanden op {day.strftime('%Y-%m-%d')}:\n{df_ha.to_string(index=False)}")
            df_da = report.get_grid_data(periode='', _vanaf=vanaf, _tot=tot, _interval="uur", _source="da")
            df_da = report.calc_grid_columns(df_da, "uur", "tabel")
            print(f"Verbruiken gecorrigeerd door Tibber op {day.strftime('%Y-%m-%d')}:\n{df_da.to_string(index=False)}")
            # print(df_ha.equals(df_da))

    def start_logging(self):
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s %(levelname)s: %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
        logging.info(f"Testen Day Ahead Optimalisatie gestart: "
                     f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")

    def get_da_calc(self):
        self.start_logging()
        da_calc = dao.prog.day_ahead.DaCalc(file_name="../data/options_george.json")
        da_calc.calc_optimum(_start_dt=datetime.datetime(year=2024, month=7, day=28, hour=15, minute=0),
                             _start_soc=67.2)
        # da_calc.calc_optimum(_start_soc=67.2)

    def get_grid_data(self, engine:str, source:str, vanaf:datetime.datetime, tot:datetime.datetime=None,
                      interval:str="uur")->tuple:
        file_name = "../data/options_" + engine + ".json"
        report = dao.prog.da_report.Report(file_name)
        if tot is None:
            tot = vanaf + datetime.timedelta(days=1)
        df = report.get_grid_data(periode='', _vanaf=vanaf, _tot=tot, _interval=interval, _source=source)
        df = report.calc_grid_columns(df, interval, "tabel")
        row = df.iloc[-1]
        netto_consumption = row.Verbruik[0] - row.Productie[0]
        netto_kosten = row.Kosten[0] - row.Opbrengst[0]
        return df, netto_consumption, netto_kosten

    def test_grid_reporting(self):
        self.engines = ["mysql", "sqlite", "postgresql"]
        self.sources = ["da", "ha"]
        result = []
        result.append(pd.DataFrame(columns=["engine", "netto_consumption", "netto_cost"]))
        result.append(pd.DataFrame(columns=["engine", "netto_consumption", "netto_cost"]))
        for engine in self.engines:
            for s in range(len(self.sources)):
                vanaf = datetime.datetime(2024, 8, 9)
                df, netto_consumption, netto_cost = self.get_grid_data(engine, self.sources[s], vanaf)
                print(f"Result from source:{self.sources[s]} engine:{engine} :\n{df.to_string(index=False)}")
                result[s].loc[result[s].shape[0]] = [engine, netto_consumption, netto_cost]
        print(f"Result from DA:\n{result[0].to_string(index=False)}")
        print(f"Result from HA:\n{result[1].to_string(index=False)}")



if __name__ == '__main__':
    unittest.main()
