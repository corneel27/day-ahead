import unittest
import datetime
import sys
sys.path.append("../prog")
import dao.prog.da_report
import dao.prog.day_ahead
import logging



class TestReports(unittest.TestCase):

    def t_st_get_grid_data(self):
        report = dao.prog.da_report.Report()
        for day in [datetime.datetime(2024, 7, 9), datetime.datetime(2024, 7, 10)]:
            vanaf = day # datetime.datetime(2024, 7, 9)
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

    def test_da_calc(self):
        self.start_logging()
        da_calc = dao.prog.day_ahead.DaCalc(file_name="../data/options_george.json")
        da_calc.calc_optimum(_start_dt=datetime.datetime(year=2024, month=7, day=28, hour=15, minute=0), _start_soc=67.2)
        # da_calc.calc_optimum(_start_soc=67.2)


if __name__ == '__main__':
    unittest.main()
