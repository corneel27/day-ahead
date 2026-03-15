import datetime
import sys
import os
import fnmatch
import time
import pytz
import warnings
from dataclasses import dataclass
from requests import get
import json
import hassapi as hass
import pandas as pd
from subprocess import PIPE, run
import logging
from logging import Handler
from sqlalchemy import Table, select, func, and_

# from dao.prog.solar_predictor import SolarPredictor
from dao.prog.utils import get_tibber_data, error_handling
from dao.prog.version import __version__
from pathlib import Path
from dao.prog.config.loader import ConfigurationLoader
from dao.lib.db_connections import make_db_da, make_db_ha
from dao.lib.da_meteo import Meteo
from dao.lib.da_prices import DaPrices
from dao.prog.utils import interpolate

# from db_manager import DBmanagerObj
from typing import Union
from hassapi.models import StateList


@dataclass
class HAContext:
    """Runtime values fetched from Home Assistant on start-up.

    These are not part of the static configuration in options.json and must
    never be written back to disk.  Pass instances of this dataclass to any
    collaborator that needs location or timezone information.
    """
    latitude: float
    longitude: float
    time_zone: str
    country: str


class NotificationHandler(Handler):
    def __init__(self, _hass: hass.Hass, _entity=None):
        """
        Initialize the handler.
        """
        Handler.__init__(self)
        self.hass = _hass
        self.entity = _entity
        self.count = 0

    def emit(self, record):
        if self.entity and record.levelno >= logging.WARNING and self.count == 0:
            if record.levelno >= logging.ERROR:
                self.count += 1
            msg = self.format(record)
            msg = msg.partition("\n")[0]
            self.hass.set_value(self.entity, msg)


class DaBase(hass.Hass):
    _config = None
    _loader = None
    def __init__(self, file_name: str = None):
        self.file_name = file_name
        path = os.getcwd()
        new_path = "/".join(list(path.split("/")[0:-2]))
        if new_path not in sys.path:
            sys.path.append(new_path)
        self.make_data_path()
        self.debug = False
        self.tasks = self.generate_tasks()
        self.log_level = logging.INFO
        self.notification_entity = None
        self.ha_context: HAContext | None = None
        logging.basicConfig(
            level=self.log_level,
            format="%(asctime)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        logging.getLogger().setLevel(self.log_level)
        if DaBase._config is None:
            try:
                self.loader = ConfigurationLoader(Path(self.file_name) if self.file_name else Path("../data/options.json"))
                self.config = self.loader.load_and_validate()
                DaBase._config = self.config
                DaBase._loader = self.loader
            except FileNotFoundError as e:
                logging.error(f"Configuratiebestand niet gevonden: {e}")
                self.config = None
                return
            except (ValueError, RuntimeError) as e:
                logging.error(f"Configuratie kon niet worden geladen: {e}")
                self.config = None
                return
        else:
            self.config = DaBase._config
            self.loader = DaBase._loader
        log_level_str = (self.config.logging_level or "info")
        _log_level = getattr(logging, log_level_str.upper(), None)
        if not isinstance(_log_level, int):
            raise ValueError("Invalid log level: %s" % _log_level)
        self.log_level = _log_level
        logging.addLevelName(logging.DEBUG, "debug")
        logging.addLevelName(logging.INFO, "info")
        logging.addLevelName(logging.WARNING, "waarschuwing")
        logging.addLevelName(logging.ERROR, "fout")
        logging.addLevelName(logging.CRITICAL, "kritiek")
        logging.getLogger().setLevel(self.log_level)
        ha = self.config.homeassistant
        self.protocol_api = ha.protocol_api
        self.ip_address = ha.ip_address

        self.ip_port = ha.ip_port
        if self.ip_port is None:
            self.hassurl = self.protocol_api + "://" + self.ip_address + "/core/"
        else:
            self.hassurl = (
                self.protocol_api
                + "://"
                + self.ip_address
                + ":"
                + str(self.ip_port)
                + "/"
            )
        _tok = ha.hasstoken
        if _tok is None:
            self.hasstoken = os.environ.get("SUPERVISOR_TOKEN")
        else:
            self.hasstoken = _tok.resolve(self.loader.secrets)
        super().__init__(hassurl=self.hassurl, token=self.hasstoken)
        headers = {
            "Authorization": "Bearer " + self.hasstoken,
            "content-type": "application/json",
        }
        resp = get(self.hassurl + "api/config", headers=headers)
        resp_dict = json.loads(resp.text)
        logging.debug(f"hass/api/config: {resp.text}")
        self.ha_context = HAContext(
            latitude=resp_dict["latitude"],
            longitude=resp_dict["longitude"],
            time_zone=resp_dict["time_zone"],
            country=resp_dict["country"] or "NL",
        )
        self.time_zone = self.ha_context.time_zone
        self.db_da = make_db_da(self.config, self.loader.secrets)
        self.db_ha = make_db_ha(self.config, self.loader.secrets)
        self.meteo = Meteo(
            self.config, self.db_da,
            latitude=self.ha_context.latitude,
            longitude=self.ha_context.longitude,
            secrets=self.loader.secrets,
        )
        if self.ha_context.country == "NL":
            self.knmi_station = self.meteo.which_station()
        self.solar = self.config.solar
        self.interval = self.config.interval
        self.interval_s = 3600 if self.interval == "1hour" else 900

        self.prices = DaPrices(self.config, self.db_da, country=self.ha_context.country, secrets=self.loader.secrets)
        self.prices_options = self.config.prices
        # eb + ode levering
        self.taxes_l_def = self.prices_options.energy_taxes_consumption if self.prices_options else None
        # opslag kosten leverancier
        self.ol_l_def = self.prices_options.cost_supplier_consumption if self.prices_options else None
        # eb+ode teruglevering
        self.taxes_t_def = self.prices_options.energy_taxes_production if self.prices_options else None
        self.ol_t_def = self.prices_options.cost_supplier_production if self.prices_options else None
        self.btw_l_def = self.prices_options.vat_consumption if self.prices_options else None
        self.btw_t_def = self.prices_options.vat_production if self.prices_options else self.btw_l_def
        self.salderen = self.prices_options.tax_refund if self.prices_options else True

        self.history_options = self.config.history
        self.strategy = self.config.strategy.resolve(
            lambda eid: self.get_state(eid).state, target_type=str
        )
        self.tibber_options = self.config.tibber
        notif = self.config.notifications
        self.notification_entity = notif.notification_entity
        self.notification_opstarten = notif.opstarten
        self.notification_berekening = notif.berekening
        self.last_activity_entity = notif.last_activity_entity
        self.set_last_activity()
        self.graphics_options = self.config.graphics
        self.db_da.log_pool_status()
        warnings.simplefilter("ignore", ResourceWarning)

    def set_value(self, entity_id: str, value: Union[int, float, str]) -> StateList:
        try:
            result = super().set_value(entity_id, value)
            state = self.get_state(entity_id).state
            if isinstance(value, (int, float)):
                if round(float(state), 5) != round(float(value), 5):
                    raise ValueError
            else:
                if state != value:
                    raise ValueError
        except Exception:
            logging.error(f"Fout bij schrijven naar {entity_id}, waarde {value}")
            # error_handling(ex)
            raise
        return result

    @staticmethod
    def generate_tasks():
        tasks = {
            "calc_optimum_met_debug": {
                "name": "Optimaliseringsberekening met debug",
                "cmd": ["python3", "../prog/day_ahead.py", "debug", "calc"],
                "object": "DaCalc",
                "function": "calc_optimum_met_debug",
                "file_name": "calc_debug",
            },
            "calc_optimum": {
                "name": "Optimaliseringsberekening zonder debug",
                "cmd": ["python3", "../prog/day_ahead.py", "calc"],
                "object": "DaBase",
                "function": "calc_optimum",
                "file_name": "calc",
            },
            "tibber": {
                "name": "Verbruiksgegevens bij Tibber ophalen",
                "cmd": ["python3", "../prog/day_ahead.py", "tibber"],
                "function": "get_tibber_data",
                "file_name": "tibber",
            },
            "meteo": {
                "name": "Meteoprognoses ophalen",
                "cmd": ["python3", "day_ahead.py", "meteo"],
                "function": "get_meteo_data",
                "file_name": "meteo",
            },
            "prices": {
                "name": "Day ahead prijzen ophalen",
                "cmd": ["python3", "../prog/day_ahead.py", "prices"],
                "function": "get_day_ahead_prices",
                "file_name": "prices",
            },
            "calc_baseloads": {
                "name": "Bereken de baseloads",
                "cmd": ["python3", "../prog/day_ahead.py", "calc_baseloads"],
                "function": "calc_baseloads",
                "file_name": "baseloads",
            },
            "clean": {
                "name": "Bestanden opschonen",
                "cmd": ["python3", "../prog/day_ahead.py", "clean_data"],
                "function": "clean_data",
                "file_name": "clean",
            },
            "train_ml_predictions": {
                "name": "ML modellen trainen",
                "cmd": ["python3", "../prog/day_ahead.py", "train"],
                "function": "train_ml_predictions",
                "file_name": "train",
            },
            "consolidate": {
                "name": "Verbruik/productie consolideren",
                "cmd": ["python3", "../prog/day_ahead.py", "consolidate"],
                "function": "consolidate_data",
                "file_name": "consolidate",
            },
        }
        return tasks

    def start_logging(self):
        logging.debug(f"python pad:{sys.path}")
        logging.info(f"Day Ahead Optimalisering versie: {__version__}")
        logging.info(
            f"Day Ahead Optimalisering gestart op: "
            f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )
        if self.config is not None and self.ha_context is not None:
            logging.debug(
                f"Locatie: latitude {str(self.ha_context.latitude)} "
                f"longitude: {str(self.ha_context.longitude)}"
            )

    @staticmethod
    def make_data_path():
        if os.path.lexists("../data"):
            return
        else:
            os.symlink("/config/dao_data", "../data")

    def set_last_activity(self):
        if self.last_activity_entity is not None:
            self.call_service(
                "set_datetime",
                entity_id=self.last_activity_entity,
                datetime=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

    def get_meteo_data(self, show_graph: bool = False):
        self.meteo.get_meteo_data(show_graph)

    @staticmethod
    def get_tibber_data():
        get_tibber_data()

    @staticmethod
    def consolidate_data():
        from da_report import Report

        report = Report()
        start_dt = None
        if len(sys.argv) > 2:
            # datetime start is given
            start_str = sys.argv[2]
            try:
                start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d")
            except Exception as ex:
                error_handling(ex)
                return
        report.consolidate_data(start_dt)

    def get_day_ahead_prices(self):
        source = self.prices_options.source_day_ahead if self.prices_options else "nordpool"
        self.prices.get_prices(source)

    def save_df(self, tablename: str, tijd: list, df: pd.DataFrame):
        """
        Slaat de data in het dataframe op in de tabel "table"
        :param tablename: de naam van de tabel waarin de data worden opgeslagen
        :param tijd: de datum tijd van de rijen in het dataframe
        :param df: het dataframe met de code van de variabelen in de kolomheader
        :return: None
        """
        df_db = pd.DataFrame(columns=["time", "code", "value"])
        df = df.reset_index(drop=True)
        columns = df.columns.values.tolist()[1:]
        tz = pytz.timezone(self.time_zone)
        for index in range(min(len(tijd), len(df))):
            dt = pd.to_datetime(tijd[index])
            dt = tz.localize(dt)
            utc = int(dt.timestamp())
            for c in columns:
                db_row = [str(utc), c, float(df.loc[index, c])]
                df_db.loc[df_db.shape[0]] = db_row
        logging.debug("Save calculated data:\n{}".format(df_db.to_string()))
        self.db_da.savedata(df_db, tablename=tablename)
        return

    @staticmethod
    def get_calculated_baseload(weekday: int) -> list:
        """
        Haalt de berekende baseload op voor de weekdag.
        :param weekday: : 0 = maandag, 6 zondag
        :return: een lijst van eerder berekende baseload van 24uurvoor de betreffende dag
        """
        in_file = "../data/baseload/baseload_" + str(weekday) + ".json"
        with open(in_file, "r") as f:
            result = json.load(f)
        return result

    def calc_prod_solar(
        self, solar_opt: dict, act_time: int, act_gr: float, hour_fraction: float
    ):
        """
        berekent de productie van een string
        :param solar_opt: dict met alle instellingen van de string
        :param act_time: timestamp in utc seconden van het moment
        :param act_gr: de globale straling
        :param hour_fraction: de uurfractie
        :return: de productie in kWh
        """
        if solar_opt.strings:
            prod = 0
            str_num = len(solar_opt.strings)
            for str_s in range(str_num):
                prod_str = (
                    self.meteo.calc_solar_rad(
                        solar_opt.strings[str_s],
                        act_time,
                        act_gr,
                    )
                    * solar_opt.strings[str_s].yield_factor
                    * hour_fraction
                )
                prod += prod_str
        else:
            prod = (
                self.meteo.calc_solar_rad(solar_opt, act_time, act_gr)
                * solar_opt.yield_factor
                * hour_fraction
            )
        max_power = solar_opt.max_power
        if max_power is not None:
            prod = min(prod, max_power)
        return prod

    def calc_da_avg(self) -> float:
        """
        calculates the average of the last '24' hour values of the day ahead prices
        :return: the calculated average
        """
        # old sql query
        """
        sql_avg = (
        "SELECT AVG(t1.`value`) avg_da FROM "
        "(SELECT `time`, `value`,  from_unixtime(`time`) 'begin' "
        "FROM `values` , `variabel` "
        "WHERE `variabel`.`code` = 'da' AND `values`.`variabel` = `variabel`.`id` "
        "ORDER BY `time` desc LIMIT 24) t1 "
        )
        """
        # Reflect existing tables from the database
        values_table = Table(
            "values", self.db_da.metadata, autoload_with=self.db_da.engine
        )
        variabel_table = Table(
            "variabel", self.db_da.metadata, autoload_with=self.db_da.engine
        )

        # Construct the inner query
        inner_query = (
            select(
                values_table.c.time,
                values_table.c.value,
                self.db_da.from_unixtime(values_table.c.time).label("begin"),
            )
            .where(
                and_(
                    variabel_table.c.code == "da",
                    values_table.c.variabel == variabel_table.c.id,
                )
            )
            .order_by(values_table.c.time.desc())
            .limit(24)
            .alias("t1")
        )

        # Construct the outer query
        outer_query = select(func.avg(inner_query.c.value).label("avg_da"))

        # Execute the query and fetch the result
        with self.db_da.engine.connect() as connection:
            query_str = str(inner_query.compile(connection))
            logging.debug(f"inner query p_avg: {query_str}")
            query_str = str(outer_query.compile(connection))
            logging.debug(f"outer query p_avg: {query_str}")
            result = connection.execute(outer_query)
            return result.scalar()

    # TODO: _get_option and the set_entity_*/get_entity_state helpers below are
    #   generic HA interaction utilities that don't belong on DaBase. Consider
    #   extracting them into a dedicated HAEntityHelper class (or mixin) that
    #   wraps the hass.Hass API, so DaBase stays focused on config/orchestration.

    @staticmethod
    def _get_option(key: str, options, default=None):
        """Get a value from a dict or Pydantic model by key (snake_case or original)."""
        if options is None:
            return default
        if isinstance(options, dict):
            return options.get(key, default)
        snake_key = key.replace(' ', '_').replace('-', '_')
        val = getattr(options, snake_key, None)
        if val is None:
            val = getattr(options, key, None)
        return val if val is not None else default

    def set_entity_value(
        self, entity_key: str, options, value: int | float | str
    ):
        entity_id = self._get_option(entity_key, options)
        if entity_id is not None:
            self.set_value(entity_id, value)

    def set_entity_option(
        self, entity_key: str, options, value: int | float | str
    ):
        entity_id = self._get_option(entity_key, options)
        if entity_id is not None:
            self.select_option(entity_id, value)

    def set_entity_state(
        self, entity_key: str, options, value: int | float | str
    ):
        entity_id = self._get_option(entity_key, options)
        if entity_id is not None:
            self.set_state(entity_id, value)

    def get_entity_state(
        self, entity_key: str, options
    ) -> int | float | str | None:
        entity_id = self._get_option(entity_key, options)
        if entity_id is not None:
            result = self.get_state(entity_id).state
        else:
            result = None
        return result

    def clean_data(self):
        """
        takes care for cleaning folders data/log and data/images
        """

        def clean_folder(folder: str, pattern: str):
            current_time = time.time()
            day = 24 * 60 * 60
            logging.info(f"Start removing files in {folder} with pattern {pattern}")
            current_dir = os.getcwd()
            os.chdir(os.path.join(os.getcwd(), folder))
            list_files = os.listdir()
            for f in list_files:
                if fnmatch.fnmatch(f, pattern):
                    creation_time = os.path.getctime(f)
                    save_days = self.history_options.save_days
                    if (current_time - creation_time) >= save_days * day:
                        os.remove(f)
                        logging.info(f"{f} removed")
            os.chdir(current_dir)

        clean_folder("../data/log", "*.log")
        clean_folder("../data/log", "dashboard.log.*")
        clean_folder("../data/images", "*.png")

    def calc_optimum_met_debug(self):
        from day_ahead import DaCalc

        dacalc = DaCalc(self.file_name)
        # dacalc = DaCalc("../data/tst_options/options_mirabis.json")
        dacalc.debug = True
        dacalc.calc_optimum()
        # dacalc.calc_optimum(_start_dt=datetime.datetime(2025, 9, 28, 21, minute=0), _start_soc=50)

    def calc_optimum(self):
        from day_ahead import DaCalc

        dacalc = DaCalc(self.file_name)
        dacalc.debug = False
        dacalc.calc_optimum()

    @staticmethod
    def calc_baseloads():
        from da_report import Report

        report = Report()
        report.calc_save_baseloads()

    def calc_solar_predictions(
        self,
        solar_option: dict,
        vanaf: datetime.datetime,
        tot: datetime.datetime,
        interval: str = None,
        _ml_prediction: bool = None,
    ) -> pd.DataFrame:
        """
        berekent de solar production
        :param solar_option: dict van de solar-device
        :param vanaf: datetime start
        :param tot: datetime tot
        :param interval: 15"min of 1 hour of None, als None wordt self.interval genomen
        :param _ml_prediction: boolean default None(= from config)
        :return:
        """
        from dao.prog.solar_predictor import SolarPredictor

        if _ml_prediction is None:
            ml_prediction = solar_option.ml_prediction
        else:
            ml_prediction = _ml_prediction
        if interval is None:
            interval = self.interval
            interval_s = self.interval_s
        else:
            interval_s = 900 if interval == "15min" else 3600
        solar_name = solar_option.name.replace(" ", "_").replace("-", "_")
        if ml_prediction:
            solar_predictor = SolarPredictor()
            try:
                solar_prog = solar_predictor.predict_solar_device(
                    solar_option, vanaf, tot
                )
                if solar_prog.isnull().any().any():
                    logging.warning(
                        f"NaN-waarden aangetroffen in voorspelling van {solar_name}"
                        f"Deze zijn op '0' gezet"
                    )
                    solar_prog.fillna(0, inplace=True)
            except FileNotFoundError as ex:
                logging.warning(ex)
                logging.info(
                    f"Voor {solar_option.name} is geen model "
                    f"en dus wordt DAO-predictor gebruikt"
                )

                result = self.calc_solar_predictions(
                    solar_option, vanaf, tot, interval=interval, _ml_prediction=False
                )
                if _ml_prediction:
                    result["prediction"] = pd.NA
                return result
            solar_prog["tijd"] = pd.to_datetime(solar_prog["date_time"])
            if interval == "15min":
                solar_prog = interpolate(solar_prog, "prediction", quantity=True)
            while (
                len(solar_prog) > 0
                and solar_prog["tijd"].iloc[0].tz_localize(None) < vanaf
            ):
                solar_prog = solar_prog.iloc[1:]
        else:
            solar_prog = pd.DataFrame(columns=["tijd", "prediction"])
            start_ts = datetime.datetime(
                year=vanaf.year, month=vanaf.month, day=vanaf.day, hour=vanaf.hour
            ).timestamp()
            prog_data = self.db_da.get_prognose_data(
                start=start_ts, end=tot.timestamp(), interval=interval
            )
            prog_data.index = pd.to_datetime(prog_data["tijd"])
            while len(prog_data) > 0 and prog_data.iloc[0]["tijd"] < vanaf:
                prog_data = prog_data.iloc[1:]
            index = 0
            for row in prog_data.itertuples():
                h_frac = interval_s / 3600
                prod = self.calc_prod_solar(
                    solar_option, row.time, row.glob_rad, h_frac
                )
                prod = round(prod, 3)
                solar_prog.loc[solar_prog.shape[0]] = [row.tijd, prod]
        solar_prog.reset_index(drop=True, inplace=True)
        return solar_prog

    @staticmethod
    def train_ml_predictions():
        from dao.prog.solar_predictor import SolarPredictor

        solar_predictor = SolarPredictor()
        solar_predictor.run_train()

    def run_task_function(self, task, logfile: bool = True):
        # klass = globals()["class_name"]
        # instance = klass()

        # oude task
        if task not in self.tasks:
            return
        run_task = self.tasks[task]
        file_handler = None
        stream_handler = None
        logger = logging.getLogger()
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        if logfile:
            # old_stdout = sys.stdout
            for handler in logger.handlers[:]:  # make a copy of the list
                logger.removeHandler(handler)
            file_name = (
                "../data/log/"
                + run_task["file_name"]
                + "_"
                + datetime.datetime.now().strftime("%Y-%m-%d__%H:%M")
                + ".log"
            )

            file_handler = logging.FileHandler(file_name)
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            stream_handler.setLevel(self.log_level)
            logger.addHandler(stream_handler)
        if self.notification_entity is not None:
            notification_handler = NotificationHandler(
                _hass=super(), _entity=self.notification_entity
            )
            notification_handler.setFormatter(formatter)
            logger.addHandler(notification_handler)
        self.start_logging()
        try:
            logging.info(
                f"Day Ahead Optimalisatie gestart: "
                f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')} "
                f"taak: {run_task['function']}"
            )
            self.db_da.log_pool_status()
            getattr(self, run_task["function"])()
            self.set_last_activity()
            self.db_da.log_pool_status()
        except Exception:
            logging.exception("Er is een fout opgetreden, zie de fout-tracering")
            raise

        if logfile:
            file_handler.flush()
            file_handler.close()
            stream_handler.close()

    def run_task_cmd(self, task):
        if task not in self.tasks:
            logging.error(f"Onbekende taak: {task}")
            return
        run_task = self.tasks[task]
        cmd = run_task["cmd"]
        proc = run(cmd, stdout=PIPE, stderr=PIPE)
        data = proc.stdout.decode()
        err = proc.stderr.decode()
        log_content = data + err
        filename = (
            "../data/log/"
            + run_task["file_name"]
            + "_"
            + datetime.datetime.now().strftime("%Y-%m-%d__%H:%M:%S")
            + ".log"
        )
        with open(filename, "w") as f:
            f.write(log_content)

        """
        # klass = globals()["class_name"]
        # instance = klass()

        # oude task
        if task not in self.tasks:
            return
        run_task = self.tasks[task]

        # old_stdout = sys.stdout
        # log_file = open("../data/log/" + run_task["file_name"] + "_" +
        #                datetime.datetime.now().strftime("%Y-%m-%d_%H-%M") + ".log", "w")
        # sys.stdout = log_file
        try:
            logging.info(f"Day Ahead Optimalisatie gestart: "
                         f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')} "
                         f" taak: {run_task['task']}")
            getattr(self, run_task["task"])()
            self.set_last_activity()
        except Exception as ex:
            logging.error(ex)
            logging.error(error_handling())
        # log_file.flush()
        # sys.stdout = old_stdout
        # log_file.close()
        """
