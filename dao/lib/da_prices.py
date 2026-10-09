import pandas as pd
from dao.lib.db_manager import DBmanagerObj
from entsoe import EntsoePandasClient
import datetime
from requests import get, post
from nordpool.elspot import Prices as NordpoolPrices
import pytz
import json
import math
import pprint as pp
import logging


class DaPrices:
    def __init__(
        self, config,
            db_da: DBmanagerObj,
            country: str = None,
            secrets: dict = None,
            time_zone: str = "CET"
    ):
        self.config = config
        self.db_da = db_da
        self._secrets = secrets or {}
        self.interval = str(config.interval or "1hour").lower()
        self.country = country if country is not None else "NL"
        self.time_zone = time_zone if time_zone is not None else "CET"

    def get_prices(
        self, source, _start: datetime.datetime|None = None, _end: datetime.datetime|None = None
    ):
        if self.interval == "1hour":
            resolution = 60
        else:
            resolution = 15
        now = datetime.datetime.now()
        # start
        if _start is None:
            start = pd.Timestamp(
                year=now.year, month=now.month, day=now.day, tz="CET"
            )
        else:
            start = _start
        # end
        if _end is None:
            end = pd.Timestamp(
                year=now.year, month=now.month, day=now.day, tz="CET"
            )
            if now.hour < 12:
                end = end + datetime.timedelta(days=1)
            else:
                end = end + datetime.timedelta(days=2)
        else:
            end = _end

        tz = pytz.timezone("CET")
        if start.tzinfo is None:
            start = tz.normalize(tz.localize(start))

        if end.tzinfo is None:
            end = tz.normalize(tz.localize(end))

        present = self.db_da.get_time_border_record("da")
        if not (present is None) and _start is None:
            present = tz.normalize(tz.localize(present))
            present = present + datetime.timedelta(minutes=resolution)
            start = max(present, start)

            if present >= (end - datetime.timedelta(hours=1)):
                logging.info(f"Spot prices already present")
                return

        logging.debug(f"Day ahead tarieven ophalen voor {start} tot {end}")

        # For providers that only return data for one date, we need to check
        # what dates are already present and fetch only missing ones
        if source.lower() == "nordpool":
            df_db = None

            # Process each day in the range separately
            current_date = start
            while current_date < end:
                # Create a date range for one day (end of current day)
                current_end = current_date + datetime.timedelta(days=1)

                try:
                    # Fetch data for this specific day
                    if source.lower() == "nordpool":
                        daily_df = self._get_prices_nordpool(resolution, current_date)

                    if daily_df is not None and len(daily_df) > 0:
                        if df_db is None:
                            df_db = daily_df
                        else:
                            df_db = pd.concat([df_db, daily_df], ignore_index=True)

                except Exception as ex:
                    logging.error(f"Error fetching data for {current_date.date()}: {ex}")

                current_date = current_end

            # Save all the fetched data at once
            if df_db is not None and len(df_db) > 0:
                self.db_da.savedata(df_db)

        else:
            # For other sources that support range queries
            df_db = None
            # day-ahead market prices (€/MWh)
            if source.lower() == "entsoe":
                df_db = self._get_prices_entsoe(start, end)

            if source.lower() == "easyenergy":
                df_db = self._get_prices_easyenergy(start, end)

            if source.lower() == "tibber":
                df_db = self._get_prices_tibber(start)

            if df_db is not None:
                self.db_da.savedata(df_db)

    def _get_prices_entsoe(self, start, end):
        start = pd.Timestamp(
            year=start.year, month=start.month, day=start.day, tz="CET"
        )
        end = pd.Timestamp(year=end.year, month=end.month, day=end.day, tz="CET")
        _ak = self.config.prices.entsoe_api_key
        api_key = _ak.resolve(self._secrets) if _ak is not None else None
        client = EntsoePandasClient(api_key=api_key)
        da_prices = pd.DataFrame()
        try:
            da_prices = client.query_day_ahead_prices(
                self.country, start=start, end=end
            )
        except Exception as ex:
            logging.error(ex)
            logging.error(f"Geen data van Entsoe: tussen {start} en {end}")
        if len(da_prices.index) > 0:
            df_db = pd.DataFrame(columns=["time", "code", "value"])
            da_prices = (
                da_prices.reset_index()
            )  # make sure indexes pair with number of rows
            logging.info(
                f"Day ahead prijzen van Entsoe: \n{da_prices.to_string(index=False)}"
            )
            last_time = start
            for row in da_prices.itertuples():
                last_time = int(datetime.datetime.timestamp(row[1]))
                df_db.loc[df_db.shape[0]] = [str(last_time), "da", row[2] / 1000]
            logging.debug(
                f"Day ahead prijzen (source: entsoe, db-records): \n"
                f"{df_db.to_string(index=False)}"
            )

            end_dt = datetime.datetime(end.year, end.month, end.day, 23)
            last_time_dt = datetime.datetime.fromtimestamp(last_time)
            if last_time_dt < end_dt:
                if len(df_db) == 0:
                    logging.error(f"Geen data van Entsoe tot en met {end_dt}")
                else:
                    logging.warning(
                        f"Geen data van Entsoe tussen {last_time_dt} en {end_dt}"
                    )

            return df_db

    def _get_prices_tibber(self, date):
        now_ts = datetime.datetime.now().timestamp()
        get_ts = date.timestamp()
        count = 1 + math.ceil((now_ts - get_ts) / 3600)
        if self.interval == "1hour":
            resolution = "HOURLY"
        else:
            resolution = "QUARTER_HOURLY"
            count = count * 4
            if count > 674:
                count = 674
                logging.warning(
                    "Je kunt met Tibber maximaal 7 dagen terug opvragen"
                )
        count = max(1, min(674, count))
        query = (
                "{ "
                '"query": '
                ' "{ '
                "  viewer { "
                "    homes { "
                "      currentSubscription { "
                "        priceInfo(resolution: " + resolution + "){ "
                                                                "          today { "
                                                                "            energy "
                                                                "            startsAt "
                                                                "          } "
                                                                "          tomorrow { "
                                                                "            energy "
                                                                "            startsAt "
                                                                "          } "
                                                                "        } "
                                                                "        priceInfoRange(resolution: "
                + resolution
                + ", last: "
                + str(count)
                + ") { "
                  "          nodes { "
                  "            energy "
                  "            startsAt "
                  "          } "
                  "        } "
                  "      } "
                  "    } "
                  "  } "
                  '}" '
                  "}"
        )

        logging.debug(query)
        _tibber = self.config.tibber
        _tok = _tibber.api_token
        api_token = _tok.resolve(self._secrets)
        url = _tibber.api_url or "https://api.tibber.com/v1-beta/gql"
        headers = {
            "Authorization": "Bearer " + api_token,
            "content-type": "application/json",
        }
        resp = post(url, headers=headers, data=query)
        tibber_dict = json.loads(resp.text)
        today_nodes = tibber_dict["data"]["viewer"]["homes"][0][
            "currentSubscription"
        ]["priceInfo"]["today"]
        tomorrow_nodes = tibber_dict["data"]["viewer"]["homes"][0][
            "currentSubscription"
        ]["priceInfo"]["tomorrow"]
        range_nodes = tibber_dict["data"]["viewer"]["homes"][0][
            "currentSubscription"
        ]["priceInfoRange"]["nodes"]
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        for lst in [today_nodes, tomorrow_nodes, range_nodes]:
            for node in lst:
                dt = datetime.datetime.strptime(
                    node["startsAt"], "%Y-%m-%dT%H:%M:%S.%f%z"
                )
                time_stamp = int(dt.timestamp())
                value = float(node["energy"])
                logging.info(f"{node} {dt} {time_stamp} {value}")
                df_db.loc[df_db.shape[0]] = [time_stamp, "da", value]
        logging.debug(
            f"Day ahead prijzen (source: tibber, db-records): \n "
            f"{df_db.to_string(index=False)}"
        )
        return df_db

    def _get_prices_easyenergy(self, start, end):
        # ophalen bij EasyEnergy
        # 2022-06-25T00:00:00
        startstr = start.strftime("%Y-%m-%dT%H:%M:%S")
        endstr = end.strftime("%Y-%m-%dT%H:%M:%S")
        url = (
                "https://mijn.easyenergy.com/nl/api/tariff/getapxtariffs?startTimestamp="
                + startstr
                + "&endTimestamp="
                + endstr
        )
        resp = get(url)
        logging.debug(resp.text)
        json_object = json.loads(resp.text)
        df = pd.DataFrame.from_records(json_object)
        logging.info(
            f"Day ahead prijzen van Easyenergy:\n {df.to_string(index=False)}"
        )
        # datetime.datetime.strptime('Tue Jun 22 12:10:20 2010 EST', '%a %b %d %H:%M:%S %Y %Z')
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        df = df.reset_index()  # make sure indexes pair with number of rows
        for row in df.itertuples():
            dtime = str(
                int(datetime.datetime.fromisoformat(row.Timestamp).timestamp())
            )
            df_db.loc[df_db.shape[0]] = [dtime, "da", row.TariffReturn]

        return df_db

    def _get_prices_nordpool(self, resolution, date):

        # ophalen bij Nordpool
        prices_spot = NordpoolPrices()

        try:
            act_spot_prices = prices_spot.fetch(
                areas=[self.country], end_date=date, resolution=resolution
            )
        except Exception as ex:
            logging.exception(ex)
            logging.error(f"Fout bij ophalen data van Nordpool voor {date}")
            return
        if act_spot_prices is None:
            logging.error(f"Geen data van Nordpool voor {date}")
            return

        act_values = act_spot_prices["areas"][self.country]["values"]
        s = pp.pformat(act_values, indent=2)
        logging.info(f"Day ahead prijzen van Nordpool:\n {s}")
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        for act_value in act_values:
            time_dt = act_value["start"]
            time_ts = int(time_dt.timestamp())
            value = act_value["value"]
            if value == float("inf"):
                continue
            else:
                value = value / 1000
            df_db.loc[df_db.shape[0]] = [str(time_ts), "da", value]
        logging.debug(
            f"Day ahead prices for "
            f"{date.strftime('%Y-%m-%d') if date else 'tomorrow'}"
            f" (source: nordpool, db-records): \n {df_db.to_string(index=False)}"
        )
        if df_db.empty:
            logging.warning(
                f"Retrieve of day ahead prices for "
                f"{date.strftime('%Y-%m-%d') if date else 'tomorrow'} "
                f"failed"
            )
        return df_db

    def extract_data_epexpredictor(self,
                                   data:dict,
                                   know_at:datetime.datetime,
                                   new_horizon:datetime.datetime
                                   )->pd.DataFrame:
        """
        :param data:
        {
        "knownUntil":"2026-09-21T23:45:00+02:00",
        "prices": [
            {
              "startsAt": "2026-09-16T23:45:00+02:00",
              "total": 16.851
            },
            {
              "startsAt": "2026-09-17T00:00:00+02:00",
              "total": 19.944
            },
            {
              "startsAt": "2026-09-17T00:15:00+02:00",
              "total": 18.678
            },
            ....
        ]
        :param know_at: laatste record met day ahead prijzen
        :param new_horizon: ophalen tot en met new horizon
        :return: dataframe with code, time, value
        """
        rows = data.get("prices")
        df_db = pd.DataFrame(columns=["time", "tijd", "code", "value"])
        for row in rows:
            dt = datetime.datetime.strptime(row["startsAt"], "%Y-%m-%dT%H:%M:%S%f%z")
            if dt > know_at and dt <= new_horizon:
                time_stamp = int(dt.timestamp())
                value = float(row["total"])/100
                logging.info(f"{row} {dt} {time_stamp} {value}")
                df_db.loc[df_db.shape[0]] = [time_stamp, dt, "da", value]
        return df_db

    def extract_data_energypriceforecast_eu(self,
                                            data:dict,
                                            know_at:datetime.datetime,
                                            new_horizon:datetime.datetime
                                            )->pd.DataFrame:
        """
        {
          "api_version": "v1",
          "country": "NL",
          "currency": "EUR",
          "entries": [
            {
              "end": "2026-09-21T21:15:00Z",
              "source": "day_ahead",
              "start": "2026-09-21T21:00:00Z",
              "value": 0.19836
            },
            {
              "end": "2026-09-21T21:30:00Z",
              "source": "day_ahead",
              "start": "2026-09-21T21:15:00Z",
              "value": 0.18462
            },

        """
        rows = data.get('entries')
        df_db = pd.DataFrame(columns=["time", "tijd", "code", "value"])
        tz = pytz.timezone(self.time_zone)
        for row in rows:
            utc_dt_str = row["start"].replace("Z", "+00:00")
            utc_dt = datetime.datetime.fromisoformat(utc_dt_str)
            dt = utc_dt.astimezone(tz)   # tz.localize(dt)
            if dt > know_at and dt <= new_horizon:
                time_stamp = int(dt.timestamp())
                value = float(row["value"])
                logging.info(f"{row} {dt} {time_stamp} {value}")
                df_db.loc[df_db.shape[0]] = [time_stamp, dt, "da", value]
        return df_db

    def extract_data_dap(self,
                         data:dict,
                         know_at:datetime.datetime,
                         new_horizon:datetime.datetime
                         )->pd.DataFrame:
        """
        :param data:
        [
          {
            "time": "2026-09-22 00:00:00+02:00",
            "time_ts": 1790028000,
            "prediction": 0.1701457947
          },
          {
            "time": "2026-09-22 01:00:00+02:00",
            "time_ts": 1790031600,
            "prediction": 0.1664741486
          },
          {
            "time": "2026-09-22 02:00:00+02:00",
            "time_ts": 1790035200,
            "prediction": 0.1623867005
          },
        ....
        """
        df = pd.DataFrame.from_records(data)
        df["time"] = pd.to_datetime(df["time"])
        df = df.loc[df['time'] > know_at]
        df = df.loc[df['time'] <= new_horizon]
        df.rename(columns={"time":"time_dt", "time_ts":"time", "prediction":"value"}, inplace=True)
        df["code"] = "da"
        return df


    def get_predicted_prices(self):
        source = self.config.prices.prediction.source
        api_url = self.config.prices.prediction.api
        extension = 96
        if extension == 0:
            logging.warning("predicted horizon extension is 0, no predicted prices are returned")
            return
        known_at = self.db_da.get_time_border_record("da").astimezone()
        new_horizon = known_at + datetime.timedelta(hours=extension)
        now = datetime.datetime.now().astimezone()
        fetch_hours = math.ceil((new_horizon - now).total_seconds()/3600)
        api_url= api_url.replace("<hours>", str(fetch_hours))
        api_url= api_url.replace("<region>", self.country)
        resp = get(api_url)
        if resp.status_code != 200:
            logging.error(f"No data from {source} off predict prices, "
                          f"statuscode: {resp.status_code},"
                          f"message: {resp.text}")
            return resp.status_code
        logging.debug(resp.text)
        json_object = json.loads(resp.text)
        extract_data_f = "extract_data_"+source
        df_db = getattr(self, extract_data_f)(json_object, known_at, new_horizon)
        logging.info(
            f"Day ahead prediction prijzen (source: {source}, db-records): \n "
            f"{df_db.to_string(index=False)}"
        )
        self.db_da.savedata(df_db, tablename="prognoses")
        return 0

    def get_price_prediction(self, source:str="dap"):
        if source.lower() == "dap":
            url = (f"https://raw.githubusercontent.com/corneel27/day-ahead-prediction/main/dap/data/prediction.json")
            resp = get(url)
            logging.debug(resp.text)
            json_object = json.loads(resp.text)
            df = pd.DataFrame.from_records(json_object)
            df.rename(columns={"time":"time_dt", "time_ts":"time", "prediction":"value"}, inplace=True)
            df["code"] = "da"
            # save
            print(df.to_string(index=False))
            self.db_da.savedata(df, "prognoses")
