from dao.prog.da_config import Config
import datetime


def get_weather_data():
    config = Config("../data/options.json")
    db_da = config.get_db_da()
    start_ts = datetime.datetime(year=2022, month=1, day=1).timestamp()
    end_ts = datetime.datetime(year=2025, month=10, day=10).timestamp()
    prognose_data = db_da.get_prognose_data(start=start_ts, end=end_ts, interval="1hour")
    print(prognose_data.to_string())
    prognose_data.to_pickle("../data/forecasts.dfp")


get_weather_data()