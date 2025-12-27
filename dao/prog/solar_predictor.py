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
from typing import Optional, Union, Dict, Any
import datetime as dt
import logging
import knmi
import copy
import math

# ML imports
from xgboost import XGBRegressor
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from scipy import stats

from dao.prog.da_base import DaBase

warnings.filterwarnings("ignore")


def create_features(df: pd.DataFrame) -> pd.DataFrame:
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
    return df


class SolarPredictor(DaBase):
    """
    A comprehensive solar production prediction system using XGBoost.

    This class handles data preprocessing, outlier detection, feature engineering,
    model training, and prediction for hourly solar production forecasting.
    """

    def __init__(
        self,
        solar_name: str = "",
        solar_capacity: float = 5,
        random_state: int = 42,
        # max_hourly_production: Optional[Dict[int, float]] = None,
    ):
        """
        Initialize the SolarPredictor.

        Args:
            random_state: Random state for reproducible results
            max_hourly_production: Optional dictionary mapping hour (0-23) to maximum
                                 expected kWh production for physics-based outlier detection.
                                 If None, uses physics-based constraints for a typical 5kW system at 52°N.
                                 For better accuracy, use create_physics_based_constraints()
                                 with your actual system capacity and location.
        """
        super().__init__(file_name="../data/options.json")
        self.solar_name = solar_name
        self.solar_capacity = solar_capacity
        self.latitude = self.config.get(["latitude"], None, 52)
        self.longitude = self.config.get(["longitude"], None, 5.1)

        self.random_state = random_state
        self.model = None
        self.feature_columns = [
            "temperature",
            "irradiance",
            "day_of_week",
            "hour",
            "quarter",
            "month",
            "season",
        ]
        self.is_trained = False
        self.training_stats = {}
        self.solar_entities = []
        """
        # Set default physics-based constraints for typical residential system
        # Uses 5kW system at 45°N latitude (mid-latitude) as reasonable default
        self.max_hourly_production =(
            self.create_physics_based_constraints(
                solar_capacity,
                system_efficiency=0.8,
                conservative_factor=1.2
            )
        )
        """

    def create_physics_based_constraints(
        self,
        system_capacity_kw: float,
        system_efficiency: float = 0.8,
        conservative_factor: float = 1.2,
    ) -> Dict[int, float]:
        """
        Create physics-based maximum hourly production constraints based on solar system capacity.

        This calculates theoretical maximum production for each hour based on:
        - System peak capacity (kWp)
        - Solar elevation angles throughout the day
        - System efficiency (inverter losses, temperature derating, etc.)
        - Conservative safety factor for outlier detection

        Args:
            system_capacity_kw: Solar system peak capacity in kW (e.g., 6.5 for 6.5kWp system)
            self.latitude: Installation latitude in degrees (affects sun angles)
                     Examples: 52.0 (Netherlands), 40.7 (New York), 34.0 (Los Angeles)
            self.longitude : deviation from meridian
            system_efficiency: Overall system efficiency (0.0-1.0)
                              Typical: 0.75-0.85 (accounts for inverter losses, temperature, dust, etc.)
            conservative_factor: Safety multiplier for outlier detection (>1.0)
                               Higher = more lenient outlier detection
                               1.2 = 20% above theoretical maximum

        Returns:
            Dictionary mapping hour (0-23) to maximum expected production (kWh)

        Example:
            # For a 8kWp system in Netherlands (52°N latitude)
            constraints = SolarPredictor.create_physics_based_constraints(
                system_capacity_kw=8.0,
                system_efficiency=0.8,
                conservative_factor=1.2
            )
            predictor = SolarPredictor(max_hourly_production=constraints)
        """

        # Solar declination angle (simplified for summer solstice - maximum sun elevation)
        # This gives us the most conservative (highest possible) estimates
        declination = 23.45  # degrees, summer solstice

        constraints = {}

        for hour in range(24):
            # uren zijn in utc
            # noon = noon_utc - longitude/15
            # Solar hour angle (longitude = solar noon, ±15° per hour)
            hour_angle = 15.0 * (hour - 12 - self.longitude/15)

            # Calculate solar elevation angle
            lat_rad = math.radians(self.latitude)
            dec_rad = math.radians(declination)
            hour_rad = math.radians(hour_angle)

            elevation_rad = math.asin(
                math.sin(lat_rad) * math.sin(dec_rad)
                + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(hour_rad)
            )
            elevation_deg = math.degrees(elevation_rad)

            if elevation_deg <= 0:
                # Sun is below horizon
                max_production = 0.05  # Small threshold for measurement noise
            else:
                # Calculate relative irradiance based on sun elevation
                # At 90° (zenith), max irradiance ≈ 1000 W/m²
                # Use sine function to approximate atmospheric losses at low angles
                relative_irradiance = math.sin(elevation_rad)

                # Apply additional atmospheric losses for low sun angles
                if elevation_deg < 15:
                    # Significant atmospheric losses near horizon
                    relative_irradiance *= (elevation_deg / 15.0) ** 0.5

                # Calculate theoretical maximum production for this hour
                # Max kWh = System_kW × Relative_Irradiance × Efficiency × 1_hour
                theoretical_max = (
                    system_capacity_kw * relative_irradiance * system_efficiency
                )

                # Apply conservative factor for outlier detection
                max_production = theoretical_max * conservative_factor

            constraints[hour] = max(0.05, max_production)  # Minimum threshold for noise
        self.max_hourly_production = constraints
        return

    def _load_and_process_weather_data(
        self, weather_data: Union[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        Load and process weather data.

        Args:
            weather_data: Path to CSV file or pandas DataFrame

        Returns:
            Processed weather DataFrame with features
        """
        if isinstance(weather_data, str):
            if not os.path.exists(weather_data):
                raise FileNotFoundError(f"Weather data file not found: {weather_data}")
            weather_df = pd.read_csv(weather_data)
        else:
            weather_df = weather_data.copy()

        # Ensure datetime column exists
        if "datetime" in weather_df.columns:
            weather_df["datetime"] = pd.to_datetime(weather_df["datetime"])
            weather_df = weather_df.set_index("datetime")
        elif not isinstance(weather_df.index, pd.DatetimeIndex):
            raise ValueError(
                "Weather data must have a 'datetime' column or DatetimeIndex"
            )

        # Validate required columns
        # required_cols = ['temperature', 'irradiance']
        # missing_cols = [col for col in required_cols if col not in weather_df.columns]
        # if missing_cols:
        #     raise ValueError(f"Weather data missing required columns: {missing_cols}")

        # Create features
        return create_features(weather_df)

    def _load_and_process_solar_data(
        self, solar_data: Union[str, pd.DataFrame]
    ) -> pd.DataFrame:
        """
        Load and process solar production data.

        Args:
            solar_data: Path to CSV file or pandas DataFrame

        Returns:
            Processed solar DataFrame
        """
        if isinstance(solar_data, str):
            if not os.path.exists(solar_data):
                raise FileNotFoundError(f"Solar data file not found: {solar_data}")
            solar_df = pd.read_csv(solar_data)
        else:
            solar_df = solar_data.copy()

        # Process datetime index
        if "datetime" in solar_df.columns:
            solar_df["datetime"] = pd.to_datetime(solar_df["datetime"])
            solar_df = solar_df.set_index("datetime")
        elif not isinstance(solar_df.index, pd.DatetimeIndex):
            raise ValueError(
                "Solar data must have a 'datetime' column or DatetimeIndex"
            )

        # Ensure solar_kwh column exists
        if "solar_kwh" not in solar_df.columns:
            raise ValueError("Solar data must contain 'solar_kwh' column")

        # Remove negative values
        solar_df = solar_df[solar_df["solar_kwh"] >= 0]

        # Resample to hourly if needed
        if len(solar_df) > 0:
            solar_df = solar_df[["solar_kwh"]].resample("h").sum()

        return solar_df

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
        return final_clean_data

    def train(
        self,
        weather_data: Union[str, pd.DataFrame],
        solar_data: Union[str, pd.DataFrame],
        model_save_path: str,
        test_size: float = 0.2,
        remove_outliers: bool = True,
        tune_hyperparameters: bool = True,
    ) -> Dict[str, Any]:
        """
        Train the solar prediction model.

        Args:
            weather_data: Path to weather CSV or DataFrame with columns:
                         ['datetime', 'temperature', 'irradiance']
            solar_data: Path to solar CSV or DataFrame with columns:
                       ['datetime', 'solar_kwh']
            model_save_path: Path where to save the trained model
            test_size: Fraction of data to use for testing
            remove_outliers: Whether to apply outlier detection
            tune_hyperparameters: Whether to perform hyperparameter tuning

        Returns:
            Dictionary with training statistics
        """
        logging.info(f"Starting solar prediction model for {self.solar_name} training...")

        # Load and process data
        logging.info("Loading and processing data...")
        weather_features = self._load_and_process_weather_data(weather_data)
        solar_df = self._load_and_process_solar_data(solar_data)

        # Merge datasets
        logging.info("Merging weather and solar data...")
        # Align timezone information
        if weather_features.index.tz is None:
            weather_features.index = weather_features.index.tz_localize(
                "UTC", ambiguous="NaT"
            )
        if solar_df.index.tz is None:
            solar_df.index = solar_df.index.tz_localize("UTC", ambiguous="NaT")

        weather_features = weather_features.dropna()
        solar_df = solar_df.dropna()

        merged_data = weather_features.join(solar_df, how="inner")
        merged_data = merged_data.dropna()

        logging.info(f"Merged dataset: {len(merged_data)} records")
        logging.info(f"Date range: {merged_data.index.min()} to {merged_data.index.max()}")

        # Outlier detection
        if remove_outliers:
            merged_data = self._detect_outliers(merged_data)
            logging.info(f"Clean dataset: {len(merged_data)} records")

        # Prepare features and target
        X = merged_data[self.feature_columns].copy()
        y = merged_data["solar_kwh"].copy()

        # Remove any remaining NaN values
        mask = ~(X.isnull().any(axis=1) | y.isnull())
        X = X[mask]
        y = y[mask]

        # Chronological split (important for time series)
        split_idx = int((1 - test_size) * len(X))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        logging.info(f"Training samples: {len(X_train)}")
        logging.info(f"Testing samples: {len(X_test)}")

        # Model training
        if tune_hyperparameters:
            logging.info("Tuning hyperparameters...")
            param_grid = {
                "n_estimators": [100, 200, 300],
                "max_depth": [3, 4, 6],
                "learning_rate": [0.05, 0.1, 0.15],
                "subsample": [0.8, 0.9],
            }

            # Use subset for faster grid search
            subset_size = min(5000, len(X_train))
            X_train_subset = X_train.iloc[:subset_size]
            y_train_subset = y_train.iloc[:subset_size]

            grid_search = GridSearchCV(
                estimator=XGBRegressor(
                    random_state=self.random_state, objective="reg:squarederror"
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

        # Train final model
        logging.info("Training final model...")
        self.model = XGBRegressor(
            **best_params, random_state=self.random_state, objective="reg:squarederror"
        )
        self.model.fit(X_train, y_train)

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
            os.path.dirname(model_save_path)
            if os.path.dirname(model_save_path)
            else ".",
            exist_ok=True,
        )
        joblib.dump(self.model, model_save_path)
        self.is_trained = True

        logging.info(f"Model training van {self.solar_name} complete")
        logging.info(f"Model saved to: {model_save_path}")
        logging.info(f"Training MAE: {train_mae:.4f} kWh")
        logging.info(f"Testing MAE: {test_mae:.4f} kWh")
        logging.info(f"Training R²: {train_r2:.4f}")
        logging.info(f"Testing R²: {test_r2:.4f}")
        logging.info("Sorted features:")
        importance = self.training_stats["feature_importance"]
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        for i, (feature, score) in enumerate(sorted_features):
            logging.info(f"  {i + 1}. {feature}: {score:.3f}")
        return self.training_stats

    def predict(
        self, weather_data: Union[Dict[str, float], pd.DataFrame]
    ) -> Union[float, np.ndarray]:
        """
        Make predictions using the trained model.

        Args:
            weather_data: Either a dictionary with single prediction data or DataFrame with multiple predictions
                        For single prediction (dict), required keys: temperature, irradiance, datetime
                        For batch prediction (DataFrame), required columns: temperature, irradiance, datetime

        Returns:
            Predicted solar production in kWh
        """
        if not self.is_trained or self.model is None:
            raise ValueError(
                "Model must be trained before making predictions. Call train() first."
            )

        if isinstance(weather_data, dict):
            # Single prediction - convert to DataFrame and process
            if "datetime" not in weather_data:
                raise ValueError("Single prediction requires 'datetime' key")

            # Create single-row DataFrame
            single_df = pd.DataFrame([weather_data])
            single_df["datetime"] = pd.to_datetime(single_df["datetime"])
            single_df = single_df.set_index("datetime")

            # Process through feature engineering
            processed_df = create_features(single_df)

            # Extract features and make prediction
            features = processed_df[self.feature_columns].iloc[0:1]
            prediction = self.model.predict(features)[0]
            return max(0, prediction)  # Ensure non-negative

        else:
            # Multiple predictions
            if not isinstance(weather_data, pd.DataFrame):
                raise ValueError(
                    "weather_data must be a dictionary or pandas DataFrame"
                )

            # Process weather data using the standard method
            weather_data = self._load_and_process_weather_data(weather_data)

            # Select required features
            featured_df = weather_data[self.feature_columns]
            prediction = self.model.predict(featured_df)
            prediction = np.maximum(0, prediction)  # Ensure non-negative
            result = pd.DataFrame( {"date_time": featured_df.index, "prediction" :prediction} )
            result["date_time"] = result["date_time"].dt.tz_convert(self.time_zone)
            return result

    # @classmethod
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

    def import_weatherdata(self, filename: str):
        """
        get the weatherdata from a local file.
        You get this file from KNMI site: https://www.daggegevens.knmi.nl/klimatologie/uurgegevens
        Place the file in addon_config/prediction/meteo
        When you call "train models", the files in thismap are imported and deleted

        :param filename: the path and the filename
        :return:
        """
        count = 0
        with open(filename) as file:
            while line := file.readline():
                if "# STN," in line:
                    break
                count += 1
        df = pd.read_csv(filename, skiprows=count)
        """
        STN,YYYYMMDD,HH,   FH,    T,    Q 
        275,20220101,    1,   50,  119,    0
        275,20220101,    2,   50,  117,    0
        
        YYYYMMDD,HH:dag einde uur in utc -> HH-1 begin uur utc
        T         : Temperatuur (in 0.1 graden Celsius) -> temp /10
        Q         : Globale straling (in J/cm2) -> gr -
        """
        df = df.rename(columns={"    T": "temp", "    Q": "gr"})
        save_df = pd.DataFrame(columns=["time", "code", "value"])
        for row in df.itertuples():
            year = int(str(row.YYYYMMDD)[0:4])
            month = int(str(row.YYYYMMDD)[4:6])
            day = int(str(row.YYYYMMDD)[6:8])
            hour = row.HH - 1
            dati = dt.datetime(year, month, day, hour, tzinfo=dt.timezone.utc)
            utc = int(dati.timestamp())
            save_df.loc[save_df.shape[0]] = [utc, "temp", row.temp / 10]
            save_df.loc[save_df.shape[0]] = [utc, "gr", row.gr]
        self.db_da.savedata(save_df, tablename="values")
        os.remove(filename)
        return

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

        latest_record = self.db_da.get_time_latest_record("gr")
        if latest_record is None:  # er zijn nog geen data
            latest_dt = start
            logging.info(f"Er zijn nog geen knmi-data aanwezig")
        else:
            latest_dt = latest_record
            logging.info(f"Er zijn knmi-data aanwezig tot {latest_dt}")
        if latest_dt >= end:
            logging.info(f"Er worden geen knmi-data opgehaald")
            return

        knmi_df = knmi.get_hour_data_dataframe(
                [self.knmi_station], start=latest_dt, end=end, variables=["T", "Q"]
            )
        if len(knmi_df) == 0:
            logging.info(f"Er zijn geen aanvullende knmi-data beschikbaar")
            return

        knmi_df["utc"] = knmi_df.index
        knmi_eerste = pd.to_datetime(knmi_df["utc"].iloc[0]).tz_localize(self.time_zone)
        knmi_laatste = pd.to_datetime(knmi_df["utc"].iloc[-1]).tz_localize(self.time_zone)
        logging.info(f"Er zijn data van het KNMI binnengekomen vanaf {knmi_eerste} tot en met "
                     f"{knmi_laatste}")
        knmi_df = knmi_df.rename(columns={"T": "temp", "Q": "gr"})
        knmi_df["utc"] = pd.to_datetime(
            knmi_df["utc"], utc=True
        )  # , format='%Y-%m-%d %H:%M:%S')
        save_df = pd.DataFrame(columns=["time", "code", "value"])
        for row in knmi_df.itertuples():
            utc = int(row.utc.timestamp())
            save_df.loc[save_df.shape[0]] = [utc, "temp", row.temp / 10]
            save_df.loc[save_df.shape[0]] = [utc, "gr", row.gr]
        self.db_da.savedata(save_df, tablename="values")
        return

    def get_weatherdata(
        self, start: dt.datetime, end: dt.datetime | None = None, prognose: bool = False
    ) -> pd.DataFrame:
        """
        vult database aan met ontbrekende data
        load weather_data from dao-database
        :param start: begindatum laden vanaf
        :param end: einddatum if None: tot gisteren 00:00
        :param prognose: boolean, False: meetdata ophalen
            True: prognoses ophalen
        :return: dataframe with weatherdata
        """
        # haal ontbrekende data op bij knmi

        if end is None:
            end = dt.datetime(start.year+1, start.month, start.day)
        if not prognose:
            # knmi data evt aanvullen
            self.import_knmi_df(start, end)

        if prognose:
            table_name = "prognoses"
        else:
            table_name = "values"
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
            columns={
                "utc": "datetime",
                "gr": "irradiance",
                "temp": "temperature"
            }
        )
        return weather_data

    def get_solar_data(self, start: dt.datetime, entities: list) -> pd.DataFrame:
        """
        haalt solardata op uit HA database
        :param start: begindatum
        :param entities: list van sensoren van ha
        :return:
        """
        from dao.prog.da_report import Report

        report = Report()
        tot = dt.datetime(start.year + 1, start.month, start.day)
        count = 0
        df_solar = pd.DataFrame()
        for sensor in entities:
            df_sensor = report.get_sensor_data(
                sensor, col_name="solar_kwh", vanaf=start, tot=tot, agg="uur"
            )
            if count == 0:
                df_solar = df_sensor
            else:
                report.add_col_df(df_sensor, df_solar, "solar_kwh")
            count += 1
        df_solar["utc"] = pd.to_datetime(df_solar["utc"], unit="s", utc=True)
        df_solar = df_solar.set_index(df_solar["utc"])
        df_solar = df_solar.rename(columns={"utc": "datetime"})
        return df_solar

    def train_solar_option(self, weather_data:pd.DataFrame, solar_option:Dict, start:dt.datetime):
        self.solar_name = self.config.get(["name"], solar_option, "default")
        self.solar_entities = self.config.get(["entities sensors"], solar_option, [])
        if not self.solar_entities:
            raise ValueError(
                f"No entities configured in your solar-option of {self.solar_name}"
            )
        self.solar_capacity = self.config.get(["capacity"], solar_option, 5.0)
        self.create_physics_based_constraints(self.solar_capacity)
        solar_data = self.get_solar_data(start=start, entities=self.solar_entities)
        self.train(
            weather_data,
            solar_data,
            "../data/prediction/models/" + self.solar_name + ".pkl",
        )

    def run_train(self, start: dt.datetime = None):
        """
        traint alle gedefinieerde ml-objecten
        :param start: optionele begindatum om te trainen, anders een jaar geleden
        :return:
        """
        if start is None:
            now = dt.datetime.now()
            start = dt.datetime(year=now.year - 1, month=now.month, day=now.day)
        weather_data = self.get_weatherdata(start=start)
        solar_options = self.config.get(["solar"], None, None)
        for solar_option in solar_options:
            if self.config.get(["ml_prediction"], solar_option, "False").lower() == "true":
                self.train_solar_option(weather_data, solar_option, start)
        batteries = self.config.get(["battery"], None, None)
        for battery in batteries:
            solar_options = self.config.get(["solar"], battery, None)
            for solar_option in solar_options:
                if self.config.get(["ml_prediction"], solar_option, "False").lower() == "true":
                    self.train_solar_option(weather_data, solar_option, start)

    def predict_solar_device(
        self, solar_name:str, start: dt.datetime, end: dt.datetime
    ) -> pd.DataFrame:
        """
        berekent de voorspelling voor een pv-installatie
        :param solar_name, de naam van de installatie
        :param start: start-tijdstip voorspelling
        :param end: eind-tijdstip voorspelling
        :return: dataframe met berekende voorspellingen per uur
        """
        # self.solar_name = self.solar_name = self.config.get(["name"], solar_option, "default")
        file_name = "../data/prediction/models/" + solar_name + ".pkl"
        if os.path.isfile(file_name):
            self.load_model(file_name)
        else:
            raise FileNotFoundError(
                f"Er is geen model aanwezig voor {self.solar_name},svp eerst trainen."
            )
        weather_data = self.get_weatherdata(start, end, prognose=True)
        prediction = self.predict(weather_data)
        logging.info(f"ML prediction {solar_name}\n{prediction}")
        return prediction

    def test_solar_predictor(self, start, end):
        solar_options = self.config.get(["solar"], None, None)
        for solar_option in solar_options:
            if self.config.get(["ml_prediction"], solar_option, "False").lower() == "true":
                self.predict_solar_device(solar_option["name"], start, end)
        batteries = self.config.get(["battery"], None, None)
        for battery in batteries:
            solar_options = self.config.get(["solar"], battery, None)
            for solar_option in solar_options:
                if self.config.get(["ml_prediction"], solar_option, "False").lower() == "true":
                    self.predict_solar_device(solar_option["name"], start, end)

def main():
    arg = sys.argv[1]
    solar_predictor = SolarPredictor("")
    if arg.lower() == "train":
        solar_predictor.run_train()
    if arg.lower() == "predict":
        solar_predictor.test_solar_predictor(
            start=dt.datetime(year=2025, month=12, day=21),
            end=dt.datetime(year=2025, month=12, day=23),
        )



if __name__ == "__main__":
    main()
