import pandas as pd
from dao.lib.db_manager import DBmanagerObj
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


class DaPrices:
    EXTENSION_CODE = "da_ext"
    EXTENSION_RECORD_ID = 25
    EXTENSION_RECORD_NAME = "Tarief forecast extension"
    EXTENSION_RECORD_DIM = "euro/kWh"

    def __init__(self, config, db_da: DBmanagerObj, country: str = None, secrets: dict = None):
        self.config = config
        self.db_da = db_da
        self._secrets = secrets or {}
        self.interval = str(config.interval or "1hour").lower()
        self.country = country if country is not None else "NL"

    def _resolve_market_country(self, configured):
        if configured:
            return str(configured).strip().lower()
        mapping = {
            "NL": "nl",
            "BE": "be",
            "DE": "de",
            "FR": "fr",
            "AT": "at",
            "CZ": "cz",
            "DK1": "dk1",
            "DK2": "dk2",
            "NO1": "no1",
            "NO2": "no2",
            "NO3": "no3",
            "NO4": "no4",
            "NO5": "no5",
        }
        return mapping.get(str(self.country or "").upper(), "nl")

    def _forecast_extension_provider(self) -> str:
        provider = getattr(self.config.prices, "forecast_extension_provider", "none")
        return str(provider or "none").strip().lower()

    def _forecast_extension_hours(self) -> int:
        hours = getattr(self.config.prices, "forecast_extension_hours", 0)
        try:
            return max(0, min(168, int(hours)))
        except (TypeError, ValueError):
            return 0

    def _energypriceforecast_extension_country(self):
        configured = getattr(
            self.config.prices,
            "energypriceforecast_extension_country",
            None,
        )
        return self._resolve_market_country(configured)

    def _energypriceforecast_extension_api_url(self):
        configured = getattr(
            self.config.prices,
            "energypriceforecast_extension_api_url",
            None,
        )
        configured = str(configured or "").strip()
        if configured:
            return configured
        return "https://api.energypriceforecast.eu/api/v1/dao/prices"

    def _day_ahead_prediction_extension_url(self):
        configured = getattr(
            self.config.prices,
            "day_ahead_prediction_extension_url",
            None,
        )
        configured = str(configured or "").strip()
        if configured:
            return configured
        return (
            "https://raw.githubusercontent.com/"
            "corneel27/day-ahead-prediction/main/dap/data/prediction.json"
        )

    def _ensure_extension_code_available(self):
        self.db_da.ensure_variabel_record(
            record_id=self.EXTENSION_RECORD_ID,
            code=self.EXTENSION_CODE,
            name=self.EXTENSION_RECORD_NAME,
            dim=self.EXTENSION_RECORD_DIM,
        )

    def _build_energypriceforecast_df(
        self,
        *,
        start,
        end,
        api_url: str,
        country: str,
        code: str,
        forecast_only: bool = False,
        min_timestamp: int | None = None,
        max_timestamp: int | None = None,
        hours_override: int | None = None,
    ) -> pd.DataFrame:
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        end_ts = end.timestamp() if hasattr(end, "timestamp") else now_ts + 48 * 3600
        hours = hours_override if hours_override is not None else max(
            1, min(168, math.ceil((end_ts - now_ts) / 3600))
        )
        mode_suffix = "&mode=forecast_only" if forecast_only else ""
        url = f"{api_url}?country={country}&hours={hours}{mode_suffix}"
        resp = get(url, timeout=15)
        resp.raise_for_status()
        payload = json.loads(resp.text)
        entries = payload.get("entries") or []
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        for entry in entries:
            start_raw = str(entry.get("start") or "")
            end_raw = str(entry.get("end") or "")
            value = entry.get("value")
            if not start_raw:
                continue
            try:
                start_dt = datetime.datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                end_dt = (
                    datetime.datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
                    if end_raw
                    else start_dt + datetime.timedelta(hours=1)
                )
                value = float(value)
            except (TypeError, ValueError):
                continue
            timestamps: list[int]
            if self.interval == "15min" and end_dt > start_dt:
                quarter_count = max(1, int(round((end_dt - start_dt).total_seconds() / 900)))
                timestamps = [
                    int((start_dt + datetime.timedelta(minutes=15 * idx)).timestamp())
                    for idx in range(quarter_count)
                ]
            else:
                timestamps = [int(start_dt.timestamp())]
            for time_stamp in timestamps:
                if min_timestamp is not None and time_stamp <= min_timestamp:
                    continue
                if max_timestamp is not None and time_stamp >= max_timestamp:
                    continue
                df_db.loc[df_db.shape[0]] = [str(time_stamp), code, value]
        return df_db

    def _build_day_ahead_prediction_df(
        self,
        *,
        api_url: str,
        code: str,
        min_timestamp: int | None = None,
        max_timestamp: int | None = None,
    ) -> pd.DataFrame:
        resp = get(api_url, timeout=15)
        resp.raise_for_status()
        payload = json.loads(resp.text)
        entries = payload if isinstance(payload, list) else payload.get("entries") or []
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        for entry in entries:
            try:
                time_stamp = int(entry.get("time_ts"))
                value = float(entry.get("prediction"))
            except (TypeError, ValueError, AttributeError):
                continue
            if min_timestamp is not None and time_stamp <= min_timestamp:
                continue
            if max_timestamp is not None and time_stamp >= max_timestamp:
                continue
            if self.interval == "15min":
                for idx in range(4):
                    quarter_ts = time_stamp + idx * 900
                    if max_timestamp is not None and quarter_ts >= max_timestamp:
                        continue
                    df_db.loc[df_db.shape[0]] = [str(quarter_ts), code, value]
            else:
                df_db.loc[df_db.shape[0]] = [str(time_stamp), code, value]
        return df_db

    def get_price_forecast_extension(self):
        self._ensure_extension_code_available()
        provider = self._forecast_extension_provider()
        extension_hours = self._forecast_extension_hours()
        if provider == "none" or extension_hours <= 0:
            self.db_da.delete_code_range(
                self.EXTENSION_CODE,
                start=int(datetime.datetime.now().timestamp()),
            )
            logging.info("Geen day-ahead forecast-extensie geconfigureerd.")
            return
        official_source = str(self.config.prices.source_day_ahead or "").strip().lower()
        if official_source not in {"nordpool", "entsoe", "tibber", "easyenergy"}:
            logging.warning(
                "Forecast-extensie overgeslagen: source day ahead moet een officiele provider zijn."
            )
            return
        present = self.db_da.get_time_border_record("da")
        if present is None:
            logging.info(
                "Forecast-extensie overgeslagen: er is nog geen officiele day-ahead horizon aanwezig."
            )
            return
        resolution_seconds = 3600 if self.interval == "1hour" else 900
        official_last_ts = int(present.timestamp())
        extension_start_ts = official_last_ts + resolution_seconds
        now_ts = int(datetime.datetime.now().timestamp())
        if extension_start_ts <= now_ts:
            logging.info(
                "Forecast-extensie overgeslagen: officiele day-ahead horizon loopt niet verder dan nu."
            )
            return
        target_end_ts = extension_start_ts + extension_hours * 3600
        request_hours = max(
            1,
            min(168, math.ceil((target_end_ts - now_ts) / 3600)),
        )
        self.db_da.delete_code_range(self.EXTENSION_CODE, start=extension_start_ts)

        if provider == "energypriceforecast":
            api_url = self._energypriceforecast_extension_api_url()
            country = self._energypriceforecast_extension_country()
            df_db = self._build_energypriceforecast_df(
                start=datetime.datetime.fromtimestamp(extension_start_ts),
                end=datetime.datetime.fromtimestamp(target_end_ts),
                api_url=api_url,
                country=country,
                code=self.EXTENSION_CODE,
                forecast_only=True,
                min_timestamp=official_last_ts,
                max_timestamp=target_end_ts,
                hours_override=request_hours,
            )
            if df_db.empty:
                logging.info(
                    "Energy Price Forecast extensie: geen aanvullende slots beschikbaar (%s).",
                    country,
                )
                return
            logging.info(
                "Energy Price Forecast extensie (%s): %d slot(s) toegevoegd voorbij officiele horizon, +%d uur.",
                country,
                len(df_db),
                extension_hours,
            )
            self.db_da.savedata(df_db)
            return

        if provider == "dayaheadprediction":
            if str(self.country or "").strip().upper() != "NL":
                logging.warning(
                    "day-ahead-prediction extensie overgeslagen: provider ondersteunt momenteel alleen NL."
                )
                return
            api_url = self._day_ahead_prediction_extension_url()
            df_db = self._build_day_ahead_prediction_df(
                api_url=api_url,
                code=self.EXTENSION_CODE,
                min_timestamp=official_last_ts,
                max_timestamp=target_end_ts,
            )
            if df_db.empty:
                logging.info(
                    "day-ahead-prediction extensie: geen aanvullende slots beschikbaar."
                )
                return
            logging.info(
                "day-ahead-prediction extensie: %d slot(s) toegevoegd voorbij officiele horizon, +%d uur.",
                len(df_db),
                extension_hours,
            )
            self.db_da.savedata(df_db)
            return

        logging.warning("Onbekende forecast-extensie provider: %s", provider)

    def get_prices(
        self, source, _start: datetime.datetime = None, _end: datetime.datetime = None
    ):
        if self.interval == "1hour":
            resolution = 60
        else:
            resolution = 15
        now = datetime.datetime.now()
        # start
        if _start is None:
            if len(sys.argv) > 2:
                arg_s = sys.argv[2]
                start = datetime.datetime.strptime(arg_s, "%Y-%m-%d")
            else:
                start = pd.Timestamp(
                    year=now.year, month=now.month, day=now.day, tz="CET"
                )
        else:
            start = _start
        # end
        if _end is None:
            if len(sys.argv) > 3:
                arg_s = sys.argv[3]
                end = datetime.datetime.strptime(arg_s, "%Y-%m-%d")
            else:
                if now.hour < 12:
                    end = start + datetime.timedelta(days=1)
                else:
                    end = start + datetime.timedelta(days=2)
        else:
            end = _end

        if len(sys.argv) <= 2:
            present = self.db_da.get_time_border_record("da")
            if not (present is None):
                tz = pytz.timezone("CET")
                present = tz.normalize(tz.localize(present))
                if end.tzinfo is None:
                    end = tz.normalize(tz.localize(end))
                if present >= (end - datetime.timedelta(hours=1)):
                    logging.info(f"Day ahead data already present")
                    return

        # day-ahead market prices (€/MWh)
        if source.lower() == "entsoe":
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
                act_spot_prices = prices_spot.fetch(
                    areas=[self.country], end_date=end_date, resolution=resolution
                )
            except ConnectionError:
                logging.error(f"Geen data van Nordpool: tussen {start} en {end}")
                return
            except Exception as ex:
                logging.exception(ex)
                logging.error(f"Geen data van Nordpool: tussen {start} en {end}")
                return
            if act_spot_prices is None:
                logging.error(f"Geen data van Nordpool: tussen {start} en {end}")
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
                f"{end_date.strftime('%Y-%m-%d') if end_date else 'tomorrow'}"
                f" (source: nordpool, db-records): \n {df_db.to_string(index=False)}"
            )
            if len(df_db) < 24 and datetime.datetime.fromtimestamp(
                time_ts
            ) < datetime.datetime(
                end_date.year, end_date.month, end_date.day, end_date.hour
            ):
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
            self.db_da.savedata(df_db)
