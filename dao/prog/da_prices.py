from da_config import Config
import pandas as pd
from db_manager import DBmanagerObj
from entsoe import EntsoePandasClient
import datetime
import sys
from requests import get
from nordpool.elspot import Prices
import pytz
import json
import pprint as pp
import logging


class DaPrices:
    def __init__(self, config: Config, db_da: DBmanagerObj):
        self.config = config
        self.db_da = db_da

    def get_prices(self, source):
        now = datetime.datetime.now()
        # start
        if len(sys.argv) > 2:
            arg_s = sys.argv[2]
            start = datetime.datetime.strptime(arg_s, "%Y-%m-%d")
        else:
            start = pd.Timestamp(
                year=now.year, month=now.month, day=now.day, tz='CET')
        # end
        if len(sys.argv) > 3:
            arg_s = sys.argv[3]
            end = datetime.datetime.strptime(arg_s, "%Y-%m-%d")
        else:
            if now.hour < 12:
                end = start + datetime.timedelta(days=1)
            else:
                end = start + datetime.timedelta(days=2)

        if len(sys.argv) <= 2:
            present = self.db_da.get_time_latest_record("da")
            if not (present is None):
                tz = pytz.timezone("CET")
                present = tz.normalize(tz.localize(present))
                if present >= (end - datetime.timedelta(hours=1)):
                    logging.info(f"Day ahead data already present")
                    return

        # day-ahead market prices (€/MWh)
        if source.lower() == "entsoe":
            start = pd.Timestamp(
                year=start.year, month=start.month, day=start.day, tz='CET')
            end = pd.Timestamp(year=end.year, month=end.month,
                               day=end.day, tz='CET')
            api_key = self.config.get(["prices", "entsoe-api-key"])
            client = EntsoePandasClient(api_key=api_key)
            da_prices = pd.DataFrame()
            try:
                da_prices = client.query_day_ahead_prices(
                    'NL', start=start, end=end)
            except Exception as ex:
                logging.error(ex)
                logging.error(f"Geen data van Entsoe: tussen {start} en {end}")
            if len(da_prices.index) > 0:
                df_db = pd.DataFrame(columns=['time', 'code', 'value'])
                da_prices = da_prices.reset_index()  # make sure indexes pair with number of rows
                logging.info(f"Day ahead prijzen van Entsoe: \n{da_prices.to_string(index=False)}")
                for row in da_prices.itertuples():
                    last_time = int(datetime.datetime.timestamp(row[1]))
                    df_db.loc[df_db.shape[0]] = [str(last_time), 'da', row[2] / 1000]
                logging.debug(f"Day ahead prijzen (db-records): \n{df_db.to_string(index=False)}")
                self.db_da.savedata(df_db)

        if source.lower() == "nordpool":
            # ophalen bij Nordpool
            prices_spot = Prices()
            if len(sys.argv) <= 2:
                end_date = None
            else:
                end_date = start
            hourly_prices_spot = prices_spot.hourly(areas=['NL'], end_date=end_date)
            hourly_values = hourly_prices_spot['areas']['NL']['values']
            s = pp.pformat(hourly_values,indent=2)
            logging.info(f"Day ahead prijzen van Nordpool:\n {s}")
            df_db = pd.DataFrame(columns=['time', 'code', 'value'])
            for hourly_value in hourly_values:
                time_dt = hourly_value['start']
                time_ts = time_dt.timestamp()
                value = hourly_value['value']
                if value == float('inf'):
                    continue
                else:
                    value = value / 1000
                df_db.loc[df_db.shape[0]] = [str(time_ts), 'da', value]
            logging.debug(f"Day ahead prices for {end_date.strftime('%Y-%m-%d') if end_date else 'tomorrow'}"
                          f" (db-records): \n {df_db.to_string(index=False)}")
            if len(df_db) < 24:
                logging.warning(f"Retrieve of day ahead prices for "
                                f"{end_date.strftime('%Y-%m-%d') if end_date else 'tomorrow'} failed")
            self.db_da.savedata(df_db)

        if source.lower() == "easyenergy":
            # ophalen bij EasyEnergy
            # 2022-06-25T00:00:00
            startstr = start.strftime('%Y-%m-%dT%H:%M:%S')
            endstr = end.strftime('%Y-%m-%dT%H:%M:%S')
            url = "https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs?startTimestamp=" + \
                startstr + "&endTimestamp=" + endstr
            resp = get(url)
            logging.debug (resp.text)
            json_object = json.loads(resp.text)
            df = pd.DataFrame.from_records(json_object)
            logging.info(f"Day ahead prijzen van Easyenergy:\n {df.to_string(index=False)}")
            # datetime.datetime.strptime('Tue Jun 22 12:10:20 2010 EST', '%a %b %d %H:%M:%S %Y %Z')
            df_db = pd.DataFrame(columns=['time', 'code', 'value'])
            df = df.reset_index()  # make sure indexes pair with number of rows
            for row in df.itertuples():
                dtime = str(
                    int(datetime.datetime.fromisoformat(row.Timestamp).timestamp()))
                df_db.loc[df_db.shape[0]] = [dtime, 'da', row.TariffReturn]

            logging.debug(f"Day ahead prijzen (db-records): \n {df_db.to_string(index=False)}")
            self.db_da.savedata(df_db)
