import datetime
import pandas as pd
import logging
import sys

sys.path.append("../../../dao/prog")
import dao.prog.da_report
import dao.prog.day_ahead


def start_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.info(
        f"Testen Day Ahead Optimalisatie gestart: "
        f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
    )


def debug_da_calc():
    start_logging()
    # da_calc = dao.prog.day_ahead.DaCalc(file_name="../data/options_mysql.json")

    da_calc = dao.prog.day_ahead.DaCalc(file_name="../data/options_hetzerha.json")
    da_calc.calc_optimum(
        _start_dt=datetime.datetime(year=2025, month=2, day=11, hour=9, minute=0),
        _start_soc=0.0,
    )


if __name__ == "__main__":
    debug_da_calc()
