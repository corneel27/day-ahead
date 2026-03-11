from dao.lib.config.loader import ConfigurationLoader
from dao.lib.config.db_connections import make_db_da
from pathlib import Path
import datetime


def get_weather_data():
    loader = ConfigurationLoader(Path("../data/options.json"))
    config = loader.load_and_validate()
    db_da = make_db_da(config, loader.secrets)
    start_ts = datetime.datetime(year=2022, month=1, day=1).timestamp()
    end_ts = datetime.datetime(year=2025, month=10, day=10).timestamp()
    prognose_data = db_da.get_prognose_data(
        start=start_ts, end=end_ts, interval="1hour"
    )
    print(prognose_data.to_string())
    prognose_data.to_pickle("../data/forecasts.dfp")


get_weather_data()
