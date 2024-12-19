from da_config import Config
import pandas as pd
from db_manager import DBmanagerObj
from entsoe import EntsoePandasClient
import datetime
import sys
from requests import get, post
from nordpool.elspot import Prices
import pytz
import json
import math
import pprint as pp
import logging
from sqlalchemy import Table, select, and_


class DaPrices:
    def __init__(self, config: Config, db_da: DBmanagerObj):
        self.config = config
        self.db_da = db_da

    def get_time_latest_record(self, code: str) -> datetime.datetime:
        """
        Zoekt de tijd op van het laatst aanwezige record van "code"
        :param code: de code van het record
        :return: datum en tijd van het laatst aanwezige record
        """
        """
        query = ("SELECT from_unixtime(`time`) tijd, `value` "
                 "FROM `values`, `variabel` "
                 "WHERE `variabel`.`code` = '" + code +
                 "'  and `values`.`variabel` = `variabel`.`id` "
                 "ORDER BY `time` desc LIMIT 1")
        """
        # Reflect existing tables from the database
        with self.db_da.engine.connect() as connection:
            values_table = Table(
                "values", self.db_da.metadata, autoload_with=connection
            )
            variabel_table = Table(
                "variabel", self.db_da.metadata, autoload_with=connection
            )

        # Construct the query
        query = (
            select(
                self.db_da.from_unixtime(values_table.c.time).label("tijd"),
                values_table.c.value,
            )
            .where(
                and_(
                    variabel_table.c.code == code,
                    values_table.c.variabel == variabel_table.c.id,
                )
            )
            .order_by(values_table.c.time.desc())
            .limit(1)
        )

        # Execute the query and fetch the result
        with self.db_da.engine.connect() as connection:
            result = connection.execute(query)
            result = result.scalar()
            if type(result) is str:
                result = datetime.datetime.strptime(result, "%Y-%m-%d %H:%M:%S")
        return result

    def get_prices(self, source):
        now = datetime.datetime.now()
        # start
        if len(sys.argv) > 2:
            arg_s = sys.argv[2]
            start = datetime.datetime.strptime(arg_s, "%Y-%m-%d")
        else:
            start = pd.Timestamp(year=now.year, month=now.month, day=now.day, tz="CET")
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
            present = self.get_time_latest_record("da")
            if not (present is None):
                tz = pytz.timezone("CET")
                present = tz.normalize(tz.localize(present))
                if present >= (end - datetime.timedelta(hours=1)):
                    logging.info(f"Day ahead data already present")
                    return

        # day-ahead market prices (€/MWh)
        if source.lower() == "entsoe":
            start = pd.Timestamp(
                year=start.year, month=start.month, day=start.day, tz="CET"
            )
            end = pd.Timestamp(year=end.year, month=end.month, day=end.day, tz="CET")
            api_key = self.config.get(["prices", "entsoe-api-key"])
            client = EntsoePandasClient(api_key=api_key)
            da_prices = pd.DataFrame()
            try:
                da_prices = client.query_day_ahead_prices("NL", start=start, end=end)
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
                self.db_da.savedata(df_db)
                end_dt = datetime.datetime(end.year, end.month, end.day, 23)
                last_time_dt = datetime.datetime.fromtimestamp(last_time)
                if last_time_dt < end_dt:
                    if len(df_db) == 0:
                        logging.error(f"Geen data van Entsoe tot en met {end_dt}")
                    else:
                        logging.warning(
                            f"Geen data van Entsoe tussen {last_time_dt} en {end_dt}"
                        )

        if source.lower() == "nordpool":
            # ophalen bij Nordpool
            prices_spot = Prices()
            if len(sys.argv) <= 2:
                end_date = None
            else:
                end_date = start
            try:
                hourly_prices_spot = prices_spot.hourly(areas=["NL"], end_date=end_date)
            except ConnectionError:
                logging.error(f"Geen data van Nordpool: tussen {start} en {end}")
                return
            except Exception as ex:
                logging.exception(ex)
                logging.error(f"Geen data van Nordpool: tussen {start} en {end}")
                return

            hourly_values = hourly_prices_spot["areas"]["NL"]["values"]
            s = pp.pformat(hourly_values, indent=2)
            logging.info(f"Day ahead prijzen van Nordpool:\n {s}")
            df_db = pd.DataFrame(columns=["time", "code", "value"])
            for hourly_value in hourly_values:
                time_dt = hourly_value["start"]
                time_ts = time_dt.timestamp()
                value = hourly_value["value"]
                if value == float("inf"):
                    continue
                else:
                    value = value / 1000
                df_db.loc[df_db.shape[0]] = [str(time_ts), "da", value]
            logging.debug(
                f"Day ahead prices for "
                f"{end_date.strftime('%Y-%m-%d') if end_date else 'tomorrow'}"
                f" (source: nordpool, db-records): \n {df_db.to_string(index=False)}"
            )
            if len(df_db) < 24:
                logging.warning(
                    f"Retrieve of day ahead prices for "
                    f"{end_date.strftime('%Y-%m-%d') if end_date else 'tomorrow'} "
                    f"failed"
                )
            self.db_da.savedata(df_db)

        if source.lower() == "easyenergy":
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

            logging.debug(
                f"Day ahead prijzen (source: easy energy, db-records): \n "
                f"{df_db.to_string(index=False)}"
            )
            self.db_da.savedata(df_db)

        if source.lower() == "tibber":
            now_ts = datetime.datetime.now().timestamp()
            get_ts = start.timestamp()
            count = 1 + math.ceil((now_ts - get_ts) / 3600)
            query = (
                "{ "
                '"query": '
                ' "{ '
                "  viewer { "
                "    homes { "
                "      currentSubscription { "
                "        priceInfo { "
                "          today { "
                "            energy "
                "            startsAt "
                "          } "
                "          tomorrow { "
                "            energy "
                "            startsAt "
                "          } "
                "          range(resolution: HOURLY, last: " + str(count) + ") { "
                "            nodes { "
                "              energy "
                "              startsAt "
                "            } "
                "          } "
                "        } "
                "      } "
                "    } "
                "  } "
                '}" '
                "}"
            )

            logging.debug(query)
            tibber_options = self.config.get(["tibber"])
            url = self.config.get(
                ["api url"], tibber_options, "https://api.tibber.com/v1-beta/gql"
            )
            headers = {
                "Authorization": "Bearer " + tibber_options["api_token"],
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
            ]["priceInfo"]["range"]["nodes"]
            df_db = pd.DataFrame(columns=["time", "code", "value"])
            for lst in [today_nodes, tomorrow_nodes, range_nodes]:
                for node in lst:
                    dt = datetime.datetime.strptime(
                        node["startsAt"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    time_stamp = dt.timestamp()
                    value = float(node["energy"])
                    logging.info(f"{node} {dt} {time_stamp} {value}")
                    df_db.loc[df_db.shape[0]] = [time_stamp, "da", value]
            logging.debug(
                f"Day ahead prijzen (source: tibber, db-records): \n "
                f"{df_db.to_string(index=False)}"
            )
            self.db_da.savedata(df_db)

        if source.lower() == "tibber":
            now_ts = datetime.datetime.now().timestamp()
            get_ts = start.timestamp()
            count = 1 + math.ceil((now_ts - get_ts) / 3600)
            count_str = str(count)
            query = (
                "{ "
                '"query": '
                ' "{ '
                "  viewer { "
                "    homes { "
                "      currentSubscription { "
                "        priceInfo { "
                "          today { "
                "            energy "
                "            startsAt "
                "          } "
                "          tomorrow { "
                "            energy "
                "            startsAt "
                "          } "
                "          range(resolution: HOURLY, last: " + count_str + ") { "
                "            nodes { "
                "              energy "
                "              startsAt "
                "            } "
                "          } "
                "        } "
                "      } "
                "    } "
                "  } "
                '}" '
                "}"
            )

            logging.debug(query)
            tibber_options = self.config.get(["tibber"])
            url = self.config.get(
                ["api url"], tibber_options, "https://api.tibber.com/v1-beta/gql"
            )
            headers = {
                "Authorization": "Bearer " + tibber_options["api_token"],
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
            ]["priceInfo"]["range"]["nodes"]
            df_db = pd.DataFrame(columns=["time", "code", "value"])
            for lst in [today_nodes, tomorrow_nodes, range_nodes]:
                for node in lst:
                    dt = datetime.datetime.strptime(
                        node["startsAt"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    time_stamp = str(int(dt.timestamp()))
                    value = float(node["energy"])
                    logging.info(f"{node} {dt} {time_stamp} {value}")
                    df_db.loc[df_db.shape[0]] = [time_stamp, "da", value]
            logging.debug(
                f"Day ahead prijzen (source: tibber, db-records): \n "
                f"{df_db.to_string(index=False)}"
            )
            self.db_da.savedata(df_db)
