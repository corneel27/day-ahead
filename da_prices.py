from da_config import Config
import pandas as pd
from db_manager import DBmanagerObj
from entsoe import EntsoePandasClient
import datetime
from nordpool.elspot import Prices
import pytz

class DA_Prices:
    def __init__(self, config: Config, db_da: DBmanagerObj):
        self.config = config
        self.db_da = db_da

    def get_prices(self):
        now = datetime.datetime.now()
        start = pd.Timestamp(year=now.year, month=now.month, day=now.day, tz='CET')
        if now.hour < 12:
            end = start + datetime.timedelta(days=1)
        else:
            end = start + datetime.timedelta(days=2)

        present = self.db_da.get_time_latest_record("da")
        tz = pytz.timezone("CET")
        present = tz.normalize(tz.localize(present))
        if present >= (end - datetime.timedelta(hours=1)):
            print('Day ahead data already present')
            return

        # day-ahead market prices (€/MWh)
        client = EntsoePandasClient(api_key=self.config.get(["entsoe-api-key"]))
        da_prices = pd.DataFrame()
        last_time = 0
        try:
            da_prices = client.query_day_ahead_prices('NL', start=start, end=end)
        except Exception as e:
            print(f"Geen data van Entsoe: tussen {start} en {end}")
        if len(da_prices.index) > 0:
            df_db = pd.DataFrame(columns=['time', 'code', 'value'])
            da_prices = da_prices.reset_index()  # make sure indexes pair with number of rows
            for row in da_prices.itertuples():
                last_time = int(datetime.datetime.timestamp(row[1]))
                df_db.loc[df_db.shape[0]] = [str(last_time), 'da', row[2] / 1000]
            print(df_db)
            self.db_da.savedata(df_db)

        if last_time < (end.to_pydatetime().timestamp() - 7200):
            # ophalen bij Nordpool
            prices_spot = Prices()
            hourly_prices_spot = prices_spot.hourly(areas=['NL'])
            hourly_values = hourly_prices_spot['areas']['NL']['values']
            print(hourly_values)
            df_db = pd.DataFrame(columns=['time', 'code', 'value'])
            for hourly_value in hourly_values:
                time_dt = hourly_value['start']
                time_ts = time_dt.timestamp()
                value = float(hourly_value['value'])
                df_db.loc[df_db.shape[0]] = [str(time_ts), 'da', value / 1000]
            print(df_db)
            self.db_da.savedata(df_db)

        '''
            # ophalen bij EasyEnergy
            # 2022-06-25T00:00:00
            startstr = start.strftime('%Y-%m-%dT%H:%M:%S')
            endstr = end.strftime('%Y-%m-%dT%H:%M:%S')
            url = "https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs?startTimestamp=" + startstr + "&endTimestamp=" + endstr
            resp = get(url)
            # print (resp.text)
            json_object = json.loads(resp.text)
            df = pd.DataFrame.from_records(json_object)
            print(df)
            # datetime.datetime.strptime('Tue Jun 22 12:10:20 2010 EST', '%a %b %d %H:%M:%S %Y %Z')
            df_db = pd.DataFrame(columns=['time', 'code', 'value'])
            df = df.reset_index()  # make sure indexes pair with number of rows
            for row in df.itertuples():
                dtime = str(int(datetime.datetime.fromisoformat(row.Timestamp).timestamp()))
                df_db.loc[df_db.shape[0]] = [dtime, 'da', row.TariffReturn]
    
            # print (df_db)
            self.db_da.savedata(df_db)
        '''

