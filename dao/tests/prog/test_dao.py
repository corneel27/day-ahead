import datetime
import pandas as pd
import logging
import sys

sys.path.append("../../../dao/prog")
import dao.prog.da_report
import dao.prog.day_ahead


def test_get_grid_data_sqlite():
    report = dao.prog.da_report.Report(file_name="../data/options_sqlite.json")
    for day in [datetime.datetime(2024, 7, 9), datetime.datetime(2024, 7, 10)]:
        vanaf = day  # datetime.datetime(2024, 7, 9)
        tot = day + datetime.timedelta(days=1)  # datetime.datetime(2024, 7, 10)

        df_ha = report.get_grid_data(
            periode="", _vanaf=vanaf, _tot=tot, _interval="uur", _source="ha"
        )
        df_ha = report.calc_grid_columns(df_ha, "uur", "tabel")
        print(
            f"Eigen meterstanden op {day.strftime('%Y-%m-%d')}:\n{df_ha.to_string(index=False)}"
        )
        df_da = report.get_grid_data(
            periode="", _vanaf=vanaf, _tot=tot, _interval="uur", _source="da"
        )
        df_da = report.calc_grid_columns(df_da, "uur", "tabel")
        print(
            f"Verbruiken gecorrigeerd door Tibber op {day.strftime('%Y-%m-%d')}:\n"
            f"{df_da.to_string(index=False)}"
        )
        # print(df_ha.equals(df_da))


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


def test_da_calc():
    start_logging()
    # da_calc = dao.prog.day_ahead.DaCalc(file_name="../data/options_mysql.json")
    da_calc = dao.prog.day_ahead.DaCalc(file_name="../data/options_hetzerha.json")
    da_calc.calc_optimum(
        _start_dt=datetime.datetime(year=2025, month=1, day=26, hour=19, minute=0),
        _start_soc=30.0,
    )
    """
    da_calc.calc_optimum(
        _start_dt=datetime.datetime(year=2024, month=9, day=21, hour=14, minute=0),
        _start_soc=35.0,
    )
    # da_calc.calc_optimum(_start_soc=67.2)
    """


def get_grid_data(
    engine: str,
    source: str,
    vanaf: datetime.datetime,
    tot: datetime.datetime = None,
    interval: str = "uur",
) -> tuple:
    file_name = "../data/options_" + engine + ".json"
    report = dao.prog.da_report.Report(file_name)
    if tot is None:
        tot = vanaf + datetime.timedelta(days=1)
    df = report.get_grid_data(
        periode="", _vanaf=vanaf, _tot=tot, _interval=interval, _source=source
    )
    df = report.calc_grid_columns(df, interval, "tabel")
    row = df.iloc[-1]
    netto_consumption = row.Verbruik[0] - row.Productie[0]
    netto_kosten = row.Kosten[0] - row.Opbrengst[0]
    return df, netto_consumption, netto_kosten


def test_grid_reporting():
    engines = ["mysql", "sqlite", "postgresql"]
    sources = ["da", "ha"]
    result = [
        pd.DataFrame(columns=["engine", "netto_consumption", "netto_cost"]),
        pd.DataFrame(columns=["engine", "netto_consumption", "netto_cost"]),
    ]
    for engine in engines:
        for s in range(len(sources)):
            vanaf = datetime.datetime(2024, 8, 13)
            df, netto_consumption, netto_cost = get_grid_data(engine, sources[s], vanaf)
            print(
                f"Result from source:{sources[s]} engine:{engine} :\n{df.to_string(index=False)}"
            )
            result[s].loc[result[s].shape[0]] = [engine, netto_consumption, netto_cost]
    print(f"Result from DA:\n{result[0].to_string(index=False)}")
    print(f"Result from HA:\n{result[1].to_string(index=False)}")


def test_report_start_periode():
    file_name = "../data/options_mysql.json"
    report = dao.prog.da_report.Report(
        file_name, _now=datetime.datetime(year=2022, month=7, day=1)
    )
    df = report.get_grid_data(periode="vorige maand")
    df = report.calc_grid_columns(df, "dag", "tabel")
    print(f"Result test start periode:\n{df.to_string(index=False)}")


def test_main():
    test_get_grid_data_sqlite()


if __name__ == "__main__":
    test_main()
