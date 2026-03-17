"""
Solar Production Prediction Module

This module provides functionality to train XGBoost models for predicting
hourly solar production based on weather data and historical solar output.
"""

import pandas as pd
import numpy as np
import joblib
import os
import sys
import warnings
from typing import Union, Dict, Any
import datetime as dt
import logging
import copy
import json
import requests

from da_config import Config
from dao.lib.da_prices import DaPrices

# ML imports
from xgboost import XGBRegressor
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from scipy import stats


warnings.filterwarnings("ignore")

# constants
API_URL = "https://api.ned.nl/v1/utilizations"
CONF_FORECAST_HOURS = 120
# NED API Data Types
DATA_TYPE_WIND_ONSHORE = 1
DATA_TYPE_SOLAR = 2
DATA_TYPE_WIND_OFFSHORE = 51
DATA_TYPE_CONSUMPTION = 59

# NED API Classifications
CLASSIFICATION_FORECAST = 1
CLASSIFICATION_CURRENT = 2

# NED API Activities
ACTIVITY_PRODUCTION = 1
ACTIVITY_CONSUMPTION = 2

# NED API Granularity
GRANULARITY_HOURLY = 5
GRANULARITY_TIMEZONE_CET = 1

# Sensor definitions
DATA_TYPES = {
    "wind_onshore": {
        "name": "NED Forecast Wind Onshore",
        "icon": "mdi:wind-turbine",
        "type_id": DATA_TYPE_WIND_ONSHORE,
        "activity": ACTIVITY_PRODUCTION,
        "unit": "MW",
        "code": "prod_wind",
    },
    "wind_offshore": {
        "name": "NED Forecast Wind Offshore",
        "icon": "mdi:wind-turbine",
        "type_id": DATA_TYPE_WIND_OFFSHORE,
        "activity": ACTIVITY_PRODUCTION,
        "unit": "MW",
        "code": "prod_zeewind",
    },
    "solar": {
        "name": "NED Forecast Solar",
        "icon": "mdi:solar-power",
        "type_id": DATA_TYPE_SOLAR,
        "activity": ACTIVITY_PRODUCTION,
        "unit": "MW",
        "code": "prod_zon",
    },
    "consumption": {
        "name": "NED Forecast Consumption",
        "icon": "mdi:transmission-tower",
        "type_id": DATA_TYPE_CONSUMPTION,
        "activity": ACTIVITY_CONSUMPTION,
        "unit": "MW",
        "code": "cons",
    },
}

"""
"lng_price": {
    "name": "Aardgas prijs",
    "icon": "mdi:transmission-tower",
    "type_id": DATA_TYPE_CONSUMPTION,
    "activity": ACTIVITY_CONSUMPTION,
    "unit": "euro/m3",
    "code": "da_gas",
},
"""


class DAPredictor:
    """
    A comprehensive solar production prediction system using XGBoost.

    This class handles data preprocessing, outlier detection, feature engineering,
    model training, and prediction for hourly solar production forecasting.
    """

    def __init__(self, random_state: int = 42, file_name: str = None):
        """
        Initialize the DaPredictor.
        """
        self.file_name = file_name
        self.random_state = random_state
        self.model_save_path = "data/da_prediction.pkl"
        self.model = None
        self.log_level = logging.INFO
        logging.getLogger().setLevel(self.log_level)
        logging.basicConfig(
            level=self.log_level,
            format="%(asctime)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.feature_columns = [
            "day_of_week",
            "hour",
            "quarter",
            "month",
            "season",
            "week_nr",
        ]
        self.is_trained = False
        self.training_stats = {}
        self.forecast_hours: int = 96
        self.config = Config(file_name, secrets_file_name="../data/secrets.json")
        self.config.interval = "1hour"
        self.ned_nl_api_key = self.config.get(["ned_nl", "api_token"], None, None)
        self.db_da = self.config.get_db_da("database_dap")

    def _fetch_ned_nl_data(
        self,
        type_id: int,
        activity: int,
        classification: int,
        db_code: str,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ) -> pd.DataFrame:
        """
        Haalt data op ij ned.nl en slaat op in database
        :param type_id:
        :param activity:
        :param classification:
        :param start_date:
        :param end_date:
        :return:
        """
        url = API_URL
        # url = "https://api.ned.nl/v1/utilizations"
        headers = {
            "X-AUTH-TOKEN": self.ned_nl_api_key,
            "accept": "application/ld+json",
        }

        params = {
            "point": 0,
            "type": type_id,
            "granularity": GRANULARITY_HOURLY,
            "granularitytimezone": GRANULARITY_TIMEZONE_CET,
            "classification": classification,
            "activity": activity,
            "validfrom[after]": start_date.strftime("%Y-%m-%d"),
            "validfrom[strictly_before]": end_date.strftime("%Y-%m-%d"),
        }
        """
        Point: 0 - Netherlands
        Type: 2 - Solar
        Granularity 3 - 10 min 
        Timezone 1 - UTC 
        Classification 2 – current 
        Activity 1 - providing 
        Validfromstrictlybefore 2020-11-17  
        Validfromafter  2020-11-16
        """

        try:
            response = requests.get(
                url, headers=headers, params=params, allow_redirects=False
            )
            if response.status_code == 401:
                raise ValueError("Invalid API key")
            if response.status_code == 403:
                raise ValueError("API access forbidden - check your API key")

            if response.status_code != 200:
                error_text = response.text
                logging.error(
                    "NED API returned status %s for type %s: %s",
                    response.status_code,
                    type_id,
                    error_text,
                )
                return []

            data = json.loads(response.text)
            records = data.get("hydra:member", [])

            if not records:
                logging.warning("No data returned for type %s", type_id)
                return []

            save_df = pd.DataFrame(columns=["time", "tijd", "code", "value"])
            for record in records:
                tijd = pd.to_datetime(record["validfrom"])
                time = pd.Timestamp(tijd).timestamp()
                time = str(round(time))
                row = [time, tijd, db_code, record["volume"] / 1000.0]
                save_df.loc[save_df.shape[0]] = row

            table = (
                "values" if classification == CLASSIFICATION_CURRENT else "prognoses"
            )
            self.db_da.savedata(save_df, table)
            return tijd

        except ConnectionError as ex:
            logging.exception("Unexpected error fetching data for type %s", type_id)
            return None

    def update_data(self, classification: int, tot: dt.datetime = None):
        if tot is None:
            if classification == CLASSIFICATION_CURRENT:
                tot = dt.date.today()
            else:
                tot = dt.date.today() + dt.timedelta(days=7)

        for key, data in DATA_TYPES.items():
            # laatste record
            if classification == CLASSIFICATION_CURRENT:
                table = "values"
                latest_record = self.db_da.get_time_border_record(
                    data["code"], latest=True, table_name=table
                )
            else:
                table = "prognoses"
                latest_record = dt.datetime.now() - dt.timedelta(days=1)
            if latest_record is None:
                if classification == CLASSIFICATION_CURRENT:
                    latest_record = dt.datetime(year=2025, month=1, day=1)
                else:
                    latest_record = dt.datetime.now() - dt.timedelta(days=1)
            logging.info(
                f"Data van {data['code']} {classification=} aanwezig tot en met {latest_record}"
            )
            first_date = (latest_record + dt.timedelta(days=1)).date()
            while first_date < tot:
                latest_record = self._fetch_ned_nl_data(
                    data["type_id"],
                    data["activity"],
                    classification,
                    data["code"],
                    first_date,
                    tot,
                )
                if (
                    pd.Timestamp(latest_record).timestamp()
                    < pd.Timestamp(first_date).timestamp()
                ):
                    break
                logging.info(
                    f"Data ned.nl opgehaald {data['code']} {classification=} vanaf {first_date} "
                    f"tot en met {latest_record}"
                )
                first_date = (latest_record + dt.timedelta(days=1)).date()

    def import_knmi_df(self, start: dt.datetime, end: dt.datetime):
        """
        haalt data op bij knmi en slaat deze op in dao-database
        :param start: begin-datum waarvan data aanwezig moeten zijn
        :parame end: datum tot data aanwezig meten zijn
        :return:
        """
        """
        # import and delete meteo-files
        meteo_files = []
        map = "../data/prediction/meteo/"
        for f in os.listdir(map):
            if not f ==".keep" and os.path.isfile(map+f):
                meteo_files.append(map+f)
        for meteo_file in meteo_files:
            self.import_weatherdata(meteo_file)
        """
        # get dataframe with knmi-py
        # datetime of latest data-reord
        logging.info(
            f"KNMI-weerstation: {self.knmi_station} {knmi.stations[int(self.knmi_station)].name}"
        )
        first_dt = self.db_da.get_time_border_record("gr", latest=False)
        latest_dt = self.db_da.get_time_border_record("gr", latest=True)
        if latest_dt is None:  # er zijn nog geen data
            logging.info(f"Er zijn nog geen knmi-data aanwezig")
            self.get_and_save_knmi_data(start, end)
            first_dt = self.db_da.get_time_border_record("gr", latest=False)
            latest_dt = self.db_da.get_time_border_record("gr", latest=True)
        else:
            logging.info(f"Er zijn knmi-data aanwezig vanaf {first_dt} tot {latest_dt}")
        if first_dt <= start and latest_dt >= end:
            logging.info(f"Er worden geen knmi-data opgehaald")
            return None
        if first_dt > start:
            self.get_and_save_knmi_data(start, first_dt)
        if latest_dt < end:
            self.get_and_save_knmi_data(latest_dt, end)
        return None

    def get_weatherdata(
        self, start: dt.datetime, end: dt.datetime | None = None, prognose: bool = False
    ) -> pd.DataFrame:
        """
        vult database aan met ontbrekende data
        load ned_nl_data from dao-database
        :param start: begindatum laden vanaf
        :param end: einddatum if None: tot gisteren 00:00
        :param prognose: boolean, False: meetdata ophalen
            True: prognoses ophalen
        :return: dataframe with weatherdata
        """
        # haal ontbrekende data op bij knmi

        if end is None:
            end = dt.datetime.now()
        if not prognose:
            # knmi data evt aanvullen
            self.import_knmi_df(start, end)

        if prognose:
            table_name = "prognoses"
        else:
            table_name = "values"
        start = dt.datetime(start.year, start.month, start.day, start.hour)
        # get weather-dataframe from database
        weather_data = pd.DataFrame(columns=["utc", "gr", "temp"])
        for weather_item in weather_data.columns[1:]:
            df_item = self.db_da.get_column_data(
                table_name, weather_item, start=start, end=end
            )
            if len(weather_data) == 0:
                weather_data["utc"] = df_item["utc"]
            weather_data[weather_item] = df_item["value"]
        weather_data["utc"] = pd.to_datetime(weather_data["utc"], unit="s", utc=True)
        weather_data = weather_data.set_index(weather_data["utc"])
        weather_data = weather_data.rename(
            columns={"utc": "datetime", "gr": "irradiance", "temp": "temperature"}
        )
        return weather_data

    def import_ned_nl_files(
        self,
    ):
        files = {
            "2025_zon": {
                "file_name": "zon-2025-uur-data.csv",
                "dap_code": "prod_zon",
                "data_type": DATA_TYPE_SOLAR,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2026_zon": {
                "file_name": "zon-2026-uur-data.csv",
                "dap_code": "prod_zon",
                "data_type": DATA_TYPE_SOLAR,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2025_wind": {
                "file_name": "wind-2025-uur-data.csv",
                "dap_code": "prod_wind",
                "data_type": DATA_TYPE_WIND_ONSHORE,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2026_wind": {
                "file_name": "wind-2026-uur-data.csv",
                "dap_code": "prod_wind",
                "data_type": DATA_TYPE_WIND_ONSHORE,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2025_zeewind": {
                "file_name": "zeewind-2025-uur-data.csv",
                "dap_code": "prod_zeewind",
                "data_type": DATA_TYPE_WIND_OFFSHORE,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2026_zeewind": {
                "file_name": "zeewind-2026-uur-data.csv",
                "dap_code": "prod_zeewind",
                "data_type": DATA_TYPE_WIND_OFFSHORE,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2025_prod": {
                "file_name": "electriciteitsmix-2025-uur-data.csv",
                "dap_code": "prod_totaal",
                "data_type": DATA_TYPE_CONSUMPTION,
                "classification": CLASSIFICATION_CURRENT,
            },
            "2026_prod": {
                "file_name": "electriciteitsmix-2026-uur-data.csv",
                "dap_code": "prod_totaal",
                "data_type": DATA_TYPE_CONSUMPTION,
                "classification": CLASSIFICATION_CURRENT,
            },
        }
        for key, file_data in files.items():
            csv_data = pd.read_csv("../data/" + file_data["file_name"])
            csv_df = csv_data.filter(
                ["validfrom (UTC)", "volume (kWh)", "clasification"]
            )
            csv_df.rename(
                {"validfrom (UTC)": "datetime", "volume (kWh)": "value"},
                axis=1,
                inplace=True,
            )
            csv_df["time"] = pd.to_datetime(csv_df["datetime"]).astype(int) / 10**6
            csv_df["time"] = csv_df["time"].astype(int).astype(str)
            csv_df["code"] = file_data["dap_code"]
            csv_df["value"] = csv_df["value"] / 1000
            table_name = (
                "values"
                if file_data["classification"] == CLASSIFICATION_CURRENT
                else "prognoses"
            )
            self.db_da.savedata(csv_df, table_name)
        return None

    def import_gas_prijzen(self):
        csv_data = pd.read_csv("../data/dynamische_gasprijzen.csv", delimiter=";")
        df = pd.DataFrame(columns=["time", "tijd", "code", "value"])
        for row in csv_data.itertuples():
            value = float(row.prijs_excl_belastingen.replace(",", "."))
            datum = pd.to_datetime(row.datum)
            for uur in range(24):
                tijd = datum + dt.timedelta(hours=uur)
                time = str(int(tijd.timestamp()))
                values = [time, tijd, "da_gas", value]
                df.loc[df.shape[0]] = values
        self.db_da.savedata(df, "values")

    def fetch_recent_ned_nl_data(
        self, classification: int, start: dt.datetime, end: dt.datetime
    ) -> pd.DataFrame:
        files = {
            "zon": {
                "dap_code": "prod_zon",
                "data_type": DATA_TYPE_SOLAR,
                "classification": CLASSIFICATION_CURRENT,
            },
            "wind": {
                "dap_code": "prod_wind",
                "data_type": DATA_TYPE_WIND_ONSHORE,
                "classification": CLASSIFICATION_CURRENT,
            },
            "zeewind": {
                "dap_code": "prod_zeewind",
                "data_type": DATA_TYPE_WIND_OFFSHORE,
                "classification": CLASSIFICATION_CURRENT,
            },
            "prod": {
                "dap_code": "prod_totaal",
                "data_type": DATA_TYPE_CONSUMPTION,
                "classification": CLASSIFICATION_CURRENT,
            },
        }

        count = 0
        start_utc = pd.to_datetime(start, utc=True)
        end_utc = pd.to_datetime(end, utc=True)
        for key, data_type in DATA_TYPES.items():
            csv_df = pd.DataFrame()
            if classification == CLASSIFICATION_CURRENT:
                if "file_name" in data_type:
                    csv_data = pd.read_csv(data_type["file_name"])
                    csv_df = csv_data.filter(["validfrom (UTC)", "volume (kWh)"])
                    csv_df.rename(
                        {"validfrom (UTC)": "datetime", "volume (kWh)": key},
                        axis=1,
                        inplace=True,
                    )
                    csv_df["datetime"] = pd.to_datetime(csv_df["datetime"], utc=True)
                    csv_df = csv_df[csv_df["datetime"] >= start_utc]
                    csv_df = csv_df[csv_df["datetime"] <= end_utc]
                    if len(csv_df) > 0:
                        start = max(start_utc, csv_df["datetime"].iloc[-1])
                        csv_df = csv_df.set_index(csv_df["datetime"], drop=False)
                else:
                    start = start_utc
                    csv_df = pd.DataFrame()
            fetch_count = 0
            start = start_utc
            while start < end_utc:
                start_date = start.strftime("%Y-%m-%d")
                end_date = end.strftime("%Y-%m-%d")
                if end_date <= start_date:
                    break
                data_slice = self._fetch_ned_nl_data(
                    key,
                    data_type["type_id"],
                    data_type["activity"],
                    classification,
                    start_date,
                    end_date,
                )
                if len(data_slice) > 0:
                    start = pd.to_datetime(data_slice["datetime"].iloc[-1]).tz_convert(
                        "CET"
                    ) + dt.timedelta(hours=1)
                else:
                    break
                if fetch_count == 0:
                    data = data_slice
                else:
                    data = pd.concat([data, data_slice])
                fetch_count += 1
            if len(csv_df) > 0:
                data = pd.concat([csv_df, data])
            if count == 0:
                result = data
            else:
                data.drop_duplicates(inplace=True)
                result[key] = data[key]
            count += 1
        return result

    def updata_gasprices(self):
        url = "https://enever.nl/apiv3/gasprijs_laatste30dagen.php?token=3762b807802f28b4fb1dafeda4340c35"
        """
        {
          "status": "true",
          "data": [
            {
              "datum": "2026-02-21T06:00:00+01:00",
              "prijsEGSI": "0.307337",
              "prijsEOD": "0.299780",
              "prijsANWB": "1.157788",
              .....
              "prijsZP": "1.178678"
            },
            {
              "datum": "2026-02-20T06:00:00+01:00",
              "prijsEGSI": "0.323671",
              "prijsEOD": "0.320250",
              "prijsANWB": "1.177553",
              .....
"""
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data["status"] == "true":
                df = pd.DataFrame(columns=["time", "tijd", "code", "value"])
                for record in data["data"]:
                    datum = pd.to_datetime(record["datum"])
                    value = float(record["prijsEGSI"])
                    for uur in range(24):
                        tijd = datum + dt.timedelta(hours=uur)
                        time = str(int(tijd.timestamp()))
                        values = [time, tijd, "da_gas", value]
                        df.loc[df.shape[0]] = values
                self.db_da.savedata(df, "values")

    def update_prices(self, start: dt.datetime):
        da_prices = DaPrices(self.config, self.db_da)
        da_prices.get_prices("nordpool", _start=start)

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Perform feature engineering on a time-indexed DataFrame for energy modeling.

        This function generates time-based and weather-related features from
        the input DataFrame, which is assumed to have a DatetimeIndex and
        columns for 'temperature' and 'irradiance'. It also computes derived
        performance metrics for solar energy.

        Parameters
        ----------
        df : pandas.DataFrame
            Input DataFrame with at least the following columns:
            - 'temperature' : float, ambient temperature in °C
            - 'irradiance' : float, solar irradiance in J/cm²/h
            The DataFrame index must be a pandas.DatetimeIndex.

        Returns
        -------
        pandas.DataFrame
            A new DataFrame with the following additional columns:
            - 'day_of_week' : int, day of the week (0=Monday, 6=Sunday)
            - 'hour' : int, hour of the day (0–23)
            - 'quarter' : int, quarter of the year (1–4)
            - 'month' : int, month of the year (1–12)
            - 'season' : int, mapped season (0=winter, 1=spring, 2=summer, 3=autumn)
            - weeknr: int

        """
        df = copy.deepcopy(df)
        df["day_of_week"] = df.index.dayofweek
        df["hour"] = df.index.hour
        df["quarter"] = df.index.quarter
        df["month"] = df.index.month
        df["season"] = df.index.month.map(
            {
                12: 0,
                1: 0,
                2: 0,  # winter
                3: 1,
                4: 1,
                5: 1,  # spring
                6: 2,
                7: 2,
                8: 2,  # summer
                9: 3,
                10: 3,
                11: 3,  # autumn
            }
        )
        df["week_nr"] = df.index.isocalendar().week
        df["time"] = pd.to_datetime(df.index)
        df.drop("time", axis=1, inplace=True)
        logging.debug(f"Data with all features\n{df.to_string()}")
        self.feature_columns = df.columns
        return df

    def get_ned_nl_data(self, classification, start, end):
        count = 0
        table_name = (
            "values" if classification == CLASSIFICATION_CURRENT else "prognoses"
        )
        for key, data in DATA_TYPES.items():
            df_data = self.db_da.get_column_data(table_name, data["code"], start, end)
            if count == 0:
                result_df = df_data
                result_df.rename(columns={"value": data["code"]}, inplace=True)
            else:
                result_df[data["code"]] = df_data["value"]
            count += 1
        result_df["utc"] = pd.to_datetime(result_df["utc"], unit="s", utc=True)
        result_df = result_df.set_index(result_df["utc"])
        result_df.rename(columns={"utc": "datetime"}, inplace=True)
        result_df.drop(["uur", "time", "datasoort"], axis=1, inplace=True)
        return result_df

    def _load_and_process_ned_nl_data(self, ned_nl_data: pd.DataFrame) -> pd.DataFrame:
        """
        Load and process ned_nl data.

        Args:
            ned_nl_data: Path to CSV file or pandas DataFrame

        Returns:
            Processed weather DataFrame with features
        """
        ned_nl_df = ned_nl_data.copy()

        # Ensure datetime column exists
        if "datetime" in ned_nl_df.columns:
            ned_nl_df["datetime"] = pd.to_datetime(ned_nl_df["datetime"])
            ned_nl_df = ned_nl_df.set_index("datetime")
        elif not isinstance(ned_nl_df.index, pd.DatetimeIndex):
            raise ValueError(
                "Weather data must have a 'datetime' column or DatetimeIndex"
            )

        # Validate required columns
        # required_cols = ['temperature', 'irradiance']
        # missing_cols = [col for col in required_cols if col not in weather_df.columns]
        # if missing_cols:
        #     raise ValueError(f"Weather data missing required columns: {missing_cols}")

        # Create features
        return self._create_features(ned_nl_df)

    def _load_and_process_da_data(self, da_data: pd.DataFrame) -> pd.DataFrame:
        """
        Load and process solar production data.

        Args:
            da_data: pandas DataFrame

        Returns:
            Processed da DataFrame
        """
        da_df = da_data.copy()

        # Process datetime index
        if "datetime" in da_df.columns:
            da_df["datetime"] = pd.to_datetime(da_df["datetime"])
            da_df = da_df.set_index("datetime")
        elif not isinstance(da_df.index, pd.DatetimeIndex):
            raise ValueError("DA data must have a 'datetime' column or DatetimeIndex")

        # Ensure solar_kwh column exists
        if "da" not in da_df.columns:
            raise ValueError("DA data must contain 'da' column")

        return da_df

    def _detect_outliers(self, merged_data: pd.DataFrame) -> pd.DataFrame:
        """
        Comprehensive outlier detection for solar production data.

        Uses a three-method approach to identify and remove outliers:

        1. **Statistical outliers**: Z-score > 3 (values more than 3 standard deviations from mean)
        2. **IQR outliers**: Values outside Q1 - 1.5*IQR or Q3 + 1.5*IQR range
        3. **Physics-based outliers**: Values exceeding theoretical maximum production by hour

        A data point is flagged as an outlier only if detected by 2+ methods,
        reducing false positives while catching genuine anomalies.

        Additionally applies seasonal context outlier detection based on the
        correlation between solar production and irradiance within season-hour groups.

        Args:
            merged_data: Merged weather and solar data

        Returns:
            Clean data with outliers removed
        """
        logging.info("Detecting outliers...")
        original_size = len(merged_data)

        # 1. Context-aware outlier detection by hour
        outlier_mask = pd.Series(False, index=merged_data.index)

        for hour in range(24):
            hour_data = merged_data[merged_data["hour"] == hour]
            if len(hour_data) < 10:
                continue

            solar_values = hour_data["solar_kwh"]

            # Statistical outliers (Z-score > 3)
            z_scores = np.abs(stats.zscore(solar_values))
            statistical_outliers = z_scores > 3

            # IQR method
            Q1 = solar_values.quantile(0.25)
            Q3 = solar_values.quantile(0.75)
            IQR = Q3 - Q1
            iqr_outliers = (solar_values < (Q1 - 1.5 * IQR)) | (
                solar_values > (Q3 + 1.5 * IQR)
            )

            # Physics-based constraints: Maximum reasonable solar production by hour
            # These values represent theoretical upper bounds for a typical residential
            # solar installation (4-6kW system) under ideal conditions.
            #
            # Logic:
            # - Night hours (20-05): Virtually no production (0.1 kWh max for measurement noise)
            # - Dawn/Dusk (6, 19): Low production as sun is at low angles
            # - Morning ramp (7-9): Increasing production as sun rises
            # - Peak hours (10-14): Maximum production when sun is highest
            # - Afternoon decline (15-18): Decreasing as sun sets
            #
            # Note: These are conservative estimates and may need adjustment for:
            # - Larger installations (scale proportionally)
            # - Different latitudes (seasonal variation)
            # - Local climate conditions

            # Use configurable physics-based constraints
            physics_outliers = solar_values > self.max_hourly_production.get(hour, 5.5)

            # Combine methods (outlier if flagged by 2+ methods)
            combined_outliers = (
                statistical_outliers.astype(int)
                + iqr_outliers.astype(int)
                + physics_outliers.astype(int)
            ) >= 2

            outlier_mask.loc[hour_data.index] = combined_outliers

        # 2. Seasonal context outlier detection
        seasonal_outlier_mask = pd.Series(False, index=merged_data.index)
        clean_data = merged_data[~outlier_mask]

        for season in clean_data["season"].unique():
            for hour in range(6, 20):  # Daylight hours only
                mask = (clean_data["season"] == season) & (clean_data["hour"] == hour)
                season_hour_data = clean_data[mask]

                if len(season_hour_data) < 20:
                    continue

                if season_hour_data["irradiance"].std() > 0:
                    irradiance_corr = season_hour_data["solar_kwh"].corr(
                        season_hour_data["irradiance"]
                    )

                    if irradiance_corr > 0.5:
                        # Use direct irradiance vs solar production ratio for outlier detection
                        irradiance_ratio = season_hour_data["solar_kwh"] / (
                            season_hour_data["irradiance"] + 1e-6
                        )
                        Q1 = irradiance_ratio.quantile(0.25)
                        Q3 = irradiance_ratio.quantile(0.75)
                        IQR = Q3 - Q1
                        ratio_outliers = (irradiance_ratio < (Q1 - 2.0 * IQR)) | (
                            irradiance_ratio > (Q3 + 2.0 * IQR)
                        )
                        seasonal_outlier_mask.loc[season_hour_data.index] = (
                            ratio_outliers
                        )

        # Apply outlier removal
        final_clean_data = clean_data[~seasonal_outlier_mask]

        outliers_removed = original_size - len(final_clean_data)
        if outliers_removed > 0:
            logging.info(
                f"Outliers removed: {outliers_removed} "
                f"({outliers_removed / original_size * 100:.1f}%)"
            )
            if self.log_level >= logging.DEBUG:
                outliers = merged_data[~merged_data.isin(final_clean_data).all(axis=1)]
                logging.debug(f"Detectted outliers:\n{outliers.to_string()}")
        return final_clean_data

    def train_model(
        self,
        feature_data: pd.DataFrame | None,
        da_data: pd.DataFrame,
        test_size: float = 0.0,
        remove_outliers: bool = False,
        tune_hyperparameters: bool = True,
    ) -> Dict[str, Any]:
        """
        Train the solar prediction model.

        Args:
            feature_data: DataFrame with columns:
                         ['datetime', sev types]
            da_data: DataFrame with columns:
                       ['datetime', 'da']
            test_size: Fraction of data to use for testing
            remove_outliers: Whether to apply outlier detection
            tune_hyperparameters: Whether to perform hyperparameter tuning

        Returns:
            Dictionary with training statistics
        """
        logging.info(f"Starting da prediction model da-prices training...")

        # Load and process data
        logging.info("Loading and processing data...")
        ned_nl_df = self._load_and_process_ned_nl_data(feature_data)
        da_df = self._load_and_process_da_data(da_data)

        # Merge datasets
        logging.info("Merging ned_nl and da data...")
        # Align timezone information
        start_ts = ned_nl_df.index[0].timestamp()
        if ned_nl_df.index.tz is None:
            ned_nl_df.index = ned_nl_df.index.tz_localize("UTC", ambiguous="NaT")
        if da_df.index.tz is None:
            da_df.index = da_df.index.tz_localize("UTC", ambiguous="NaT")

        ned_nl_df = ned_nl_df.dropna()
        da_df = da_df.dropna()

        # historic weighting
        def weight(val):
            wf = (val.timestamp() - start_ts) / (30 * 24 * 60)
            return 1  # wf

        ned_nl_df["weight"] = ned_nl_df.index.to_series().apply(weight)

        merged_data = ned_nl_df.join(da_df, how="inner")
        merged_data = merged_data.dropna()

        logging.info(f"Merged dataset: {len(merged_data)} records")
        logging.info(
            f"Date range: {merged_data.index.min()} to {merged_data.index.max()}"
        )

        # Outlier detection
        if remove_outliers:
            merged_data = self._detect_outliers(merged_data)
            logging.info(f"Clean dataset: {len(merged_data)} records")

        # Prepare features and target
        X = merged_data[self.feature_columns].copy()
        y = merged_data["da"].copy()
        X["weight"] = X.index.to_series().apply(weight)

        # Remove any remaining NaN values
        mask = ~(X.isnull().any(axis=1) | y.isnull())
        X = X[mask]
        y = y[mask]

        split_idx = int((1 - test_size) * len(X))
        if test_size != 0.0:
            X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
            y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        else:
            X_train = X
            y_train = y
            X_test = X
            y_test = y

        weight_factors = X_train["weight"]
        X_train.drop("weight", axis=1, inplace=True)

        logging.debug(f"Training samples: {len(X_train)}")
        logging.debug(f"Testing samples: {len(X_test)}")

        tune_hyperparameters = (
            self.config.get(
                ["xgboost", "tune_hyperparameters"], None, f"{tune_hyperparameters}"
            ).lower()
            == "true"
        )

        logging.info(f"Tune hyperparameters: {tune_hyperparameters}")
        # Model training
        if tune_hyperparameters:
            logging.info("Tuning hyperparameters...")
            param_grid = {
                "n_estimators": [100, 200, 300],
                "max_depth": [3, 4, 6],
                "learning_rate": [0.05, 0.1, 0.15],
                "subsample": [0.8, 0.9],
            }
            param_grid = self.config.get(["xgboost", "param_grid"], None, param_grid)
            logging.info(f"Parameter grid: {param_grid}")

            # Use subset for faster grid search
            subset_size = min(5000, len(X_train))
            X_train_subset = X_train.iloc[:subset_size]
            y_train_subset = y_train.iloc[:subset_size]
            wf_train_subset = weight_factors.iloc[:subset_size]

            grid_search = GridSearchCV(
                estimator=XGBRegressor(
                    random_state=self.random_state,
                    objective="reg:squarederror",
                    weight_factors=wf_train_subset,
                ),
                param_grid=param_grid,
                cv=3,
                scoring="neg_mean_absolute_error",
                n_jobs=-1,
            )

            grid_search.fit(X_train_subset, y_train_subset)
            best_params = grid_search.best_params_
            logging.info(f"Best parameters: {best_params}")
        else:
            # Use default parameters
            best_params = {
                "n_estimators": 200,
                "max_depth": 6,
                "learning_rate": 0.1,
                "subsample": 0.8,
            }
            best_params = self.config.get(["xgboost", "parameters"], None, best_params)

        # Train final model
        logging.info("Training final model...")
        logging.info(f"Parameters: {best_params}")
        self.model = XGBRegressor(
            **best_params,
            random_state=self.random_state,
            objective="reg:squarederror",
        )
        self.model.fit(X_train, y_train, sample_weight=weight_factors)

        # Evaluate model
        y_train_pred = self.model.predict(X_train)
        y_test_pred = self.model.predict(X_test)

        # Calculate metrics
        train_mae = mean_absolute_error(y_train, y_train_pred)
        test_mae = mean_absolute_error(y_test, y_test_pred)
        train_r2 = r2_score(y_train, y_train_pred)
        test_r2 = r2_score(y_test, y_test_pred)
        train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
        test_rmse = np.sqrt(mean_squared_error(y_test, y_test_pred))

        # Store training statistics
        self.training_stats = {
            "train_mae": train_mae,
            "test_mae": test_mae,
            "train_r2": train_r2,
            "test_r2": test_r2,
            "train_rmse": train_rmse,
            "test_rmse": test_rmse,
            "training_samples": len(X_train),
            "testing_samples": len(X_test),
            "feature_importance": dict(
                zip(self.feature_columns, self.model.feature_importances_)
            ),
            "mean_target": y.mean(),
            "std_target": y.std(),
            "best_params": best_params if tune_hyperparameters else "default",
        }

        # Save model
        os.makedirs(
            os.path.dirname(self.model_save_path)
            if os.path.dirname(self.model_save_path)
            else ".",
            exist_ok=True,
        )
        joblib.dump(self.model, self.model_save_path)
        self.is_trained = True

        logging.info(f"Model training van da-prediction complete")
        logging.info(f"Model saved to: {self.model_save_path}")
        logging.info(f"Training MAE: {train_mae:.4f} eur/kWh")
        logging.info(f"Testing MAE: {test_mae:.4f} eur/kWh")
        logging.info(f"Training R²: {train_r2:.4f}")
        logging.info(f"Testing R²: {test_r2:.4f}")
        logging.info("Sorted features:")
        importance = self.training_stats["feature_importance"]
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        for i, (feature, score) in enumerate(sorted_features):
            logging.info(f"  {i + 1}. {feature}: {score:.3f}")
        return self.training_stats

    def predict(
        self, ned_nl_data: Union[Dict[str, float], pd.DataFrame]
    ) -> Union[float, np.ndarray]:
        """
        Make predictions using the trained model.

        Args:
            ned_nl_data: Either a dictionary with single prediction data or DataFrame with multiple predictions
                        For single prediction (dict), required keys: temperature, irradiance, datetime
                        For batch prediction (DataFrame), required columns: temperature, irradiance, datetime

        Returns:
            Predicted solar production in kWh
        """
        if not self.is_trained or self.model is None:
            raise ValueError(
                "Model must be trained before making predictions. Call train() first."
            )

        if isinstance(ned_nl_data, dict):
            # Single prediction - convert to DataFrame and process
            if "datetime" not in ned_nl_data:
                raise ValueError("Single prediction requires 'datetime' key")

            # Create single-row DataFrame
            single_df = pd.DataFrame([ned_nl_data])
            single_df["datetime"] = pd.to_datetime(single_df["datetime"])
            single_df = single_df.set_index("datetime")

            # Process through feature engineering
            processed_df = self._create_features(single_df)

            # Extract features and make prediction
            features = processed_df[self.feature_columns].iloc[0:1]
            prediction = self.model.predict(features)[0]
            return max(0, prediction)  # Ensure non-negative

        else:
            # Multiple predictions
            if not isinstance(ned_nl_data, pd.DataFrame):
                raise ValueError("ned_nl_data must be a dictionary or pandas DataFrame")

            # Process weather data using the standard method
            ned_nl_data = self._load_and_process_ned_nl_data(ned_nl_data)

            # Select required features
            featured_df = ned_nl_data[self.feature_columns]
            if len(featured_df) == 0:
                prediction = []
            else:
                prediction = self.model.predict(featured_df)
            prediction = np.maximum(0, prediction)  # Ensure non-negative
            result = pd.DataFrame(
                {"date_time": featured_df.index, "prediction": prediction}
            )
            result.set_index("date_time", inplace=True, drop=False)
            return result

    def load_model(self, model_path: str):  # -> 'SolarPredictor':
        """
        Load a trained model from disk.

        Args:
            model_path: Path to the saved model file

        Returns:
            None # SolarPredictor instance with loaded model
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # predictor = cls()
        self.model = joblib.load(model_path)
        self.is_trained = True

        return None

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance from the trained model.

        Returns:
            Dictionary mapping feature names to importance scores
        """
        if not self.is_trained or self.model is None:
            raise ValueError("Model must be trained before getting feature importance")

        return dict(zip(self.feature_columns, self.model.feature_importances_))

    def get_da_data(
        self, classification: int, start: dt.datetime, end: dt.datetime
    ) -> pd.DataFrame:
        """
        haalt da_data op uit DAO database
        :param start: begindatum
        :param entities: list van sensoren van ha
        :return:
        """

        if classification == CLASSIFICATION_FORECAST:
            table_name = "prognoses"
        else:
            table_name = "values"
        result_df = self.db_da.get_column_data(
            table_name, "da", start, end, agg_func="avg"
        )
        result_df["utc"] = pd.to_datetime(result_df["utc"], unit="s", utc=True)
        result_df = result_df.set_index(result_df["utc"])
        result_df = result_df.rename(columns={"utc": "datetime", "value": "da"})
        result_df.drop(["uur", "time", "datasoort"], axis=1, inplace=True)
        return result_df

    def calc_netto_fossile(self, ned_nl_df: pd.DataFrame) -> pd.DataFrame:
        result = ned_nl_df.copy()
        result["fossile"] = (
            ned_nl_df["cons"]
            - ned_nl_df["prod_wind"]
            - ned_nl_df["prod_zeewind"]
            - ned_nl_df["prod_zon"]
        )
        return result

    def run_train(self):
        """
        traint alle gedefinieerde ml-objecten
        :param start: optionele begindatum om te trainen, anders een jaar geleden
        :return:
        """
        classification = CLASSIFICATION_CURRENT
        now = dt.datetime.today()

        end = now
        start = end - dt.timedelta(days=180)
        """
        start = now
        end = now + dt.timedelta(days=6)
        
        start_date = start.strftime("%Y-%m-%d")
        end_date = end.strftime("%Y-%m-%d")
        
        if start is None:
                start = now
            if end is None:
                end = now + dt.timedelta(hours=self.forecast_hours)
        else:
            if end is None:

            if start is None:
                start = end - dt.timedelta(days=365)
        start_date = start.strftime("%Y-%m-%d")
        end_date = end.strftime("%Y-%m-%d")
        """

        ned_nl_df = self.get_ned_nl_data(
            classification=classification,
            start=start,
            end=end,
        )
        ned_nl_df = self.calc_netto_fossile(ned_nl_df)

        da_df = self.get_da_data(
            classification,
            start=start,
            end=end,
        )
        self.train_model(ned_nl_df, da_df)

    def predict_da_price(self, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
        """
        berekent de voorspelling voor een pv-installatie
        :param start: start-tijdstip voorspelling
        :param end: eind-tijdstip voorspelling
        :return: dataframe met berekende voorspellingen per uur
        """

        if os.path.isfile(self.model_save_path):
            self.load_model(model_path=self.model_save_path)
        else:
            raise FileNotFoundError(
                f"Er is geen model aanwezig voor {self.solar_name},svp eerst trainen."
            )
        # latest_dt = self.db_da.get_time_border_record("gr", latest=True, table_name="prognoses")
        # prognose = latest_dt < end
        ned_nl_data = self.get_ned_nl_data(
            classification=CLASSIFICATION_FORECAST, start=start, end=end
        )
        ned_nl_data = self.calc_netto_fossile(ned_nl_data)

        prediction = self.predict(ned_nl_data)
        # prediction["datetime"] = prediction["date_time"].apply(lambda x: x - dt.timedelta(seconds=1))
        # prediction["datetime"] = prediction["datetime"].tz_localize(GRANULARITY_TIMEZONE_CET)
        ned_nl_data["da_prediction"] = prediction["prediction"]
        prediction_df = ned_nl_data
        da_data = self.get_da_data(
            classification=CLASSIFICATION_CURRENT, start=start, end=end
        )
        prediction_df["da_epex"] = da_data["da"]
        logging.debug(f"ML prediction: \n{prediction_df.to_string()}")
        logging.info(prediction)
        return prediction, prediction_df

    def show_prediction(self, start, end):
        prediction, result_df = self.predict_da_price(start, end)
        from dao.lib.da_graph import GraphBuilder

        result_df["time"] = pd.to_datetime(result_df.index).tz_convert(
            tz="Europe/Amsterdam"
        )
        result_df.reset_index(drop=True, inplace=True)
        uur = []
        year = 0
        for row in result_df.itertuples():
            moment = row.time
            if moment.hour == 0:
                if moment.year != year:
                    uur.append(moment.strftime("%Y-%m-%d %H"))
                    year = moment.year
                    month = moment.month
                else:
                    if moment.month != month:
                        uur.append(moment.strftime("%Y-%m-%d %H"))
                        month = moment.month
                    else:
                        uur.append(moment.strftime("%Y-%m-%d %H"))
            elif moment.hour % 6 == 0:
                uur.append(moment.hour)
            else:
                uur.append(None)
        result_df["uur"] = uur
        style = self.config.get(["graphics", "style"], None, "")
        graph_options = {
            "title": f"Prognose day_ahead prijzen vanaf {start.strftime('%Y-%m-%d %H:%M')}",
            "style": style,
            "haxis": {"values": "uur", "title": "uren"},
            "graphs": [
                {
                    "vaxis": [{"title": "MWh"}],
                    "series": [
                        {
                            "column": "cons",
                            "name": "Verbruik",
                            "type": "bar",
                            "color": "yellow",
                            "width": 1,
                        },
                        {
                            "column": "prod_wind",
                            "name": "Wind op land",
                            "type": "stacked",
                            "color": "#00bfff",
                            "width": 1,
                        },
                        {
                            "column": "prod_zeewind",
                            "name": "Wind op zee",
                            "type": "stacked",
                            "color": "blue",
                            "width": 1,
                        },
                        {
                            "column": "prod_zon",
                            "name": "Zon",
                            "type": "stacked",
                            "color": "orange",
                            "width": 1,
                        },
                    ],
                },
                {
                    "vaxis": [{"title": "eur/kwh", "format": "%.2f"}],
                    "series": [
                        {
                            "column": "da_prediction",
                            "name": "DA voorspelling",
                            "type": "step",
                            "color": "purple",
                        },
                        {
                            "column": "da_epex",
                            "name": "DA epex",
                            "type": "step",
                            "color": "green",
                        },
                    ],
                },
            ],
        }
        g_builder = GraphBuilder()
        plot = g_builder.build(result_df, graph_options)
        now = dt.datetime.now()
        plot.savefig(
            f"../data/images/da_prediction_{now.strftime('%Y-%m-%d %H:%M')}.png"
        )
        return plot


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
    else:
        arg = None
    if len(sys.argv) > 2:
        arg2 = sys.argv[2]
        start_dt = dt.datetime.strptime(arg2, "%Y-%m-%d")
    else:
        start_dt = dt.date.today()
    if len(sys.argv) > 3:
        arg3 = sys.argv[3]
        end_dt = dt.datetime.strptime(arg3, "%Y-%m-%d")
    else:
        end_dt = start_dt + dt.timedelta(days=7)
    da_predictor = DAPredictor(file_name="data/options_dap.json")
    if arg.lower() == "train":
        da_predictor.run_train()
    if arg.lower() == "predict":
        da_predictor.show_prediction(
            start=start_dt,
            end=end_dt,
        )
    if arg.lower() == "import":
        # da_predictor.import_ned_nl_files()
        da_predictor.import_gas_prijzen()
    if arg.lower() == "update":
        da_predictor.update_data(classification=CLASSIFICATION_CURRENT)
        da_predictor.update_data(classification=CLASSIFICATION_FORECAST)
        da_predictor.updata_gasprices()
        da_predictor.update_prices(
            dt.datetime(start_dt.year, start_dt.month, start_dt.day)
            + dt.timedelta(days=1)
        )
        da_predictor.run_train()
        da_predictor.show_prediction(start=start_dt, end=end_dt)
    if arg.lower() == "show":
        da_predictor.show_prediction(start=start_dt, end=end_dt)
    if arg.lower() == "prices":
        da_predictor.update_prices(start_dt)


if __name__ == "__main__":
    main()
