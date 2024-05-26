"""
Het programma Day Ahead Optimalisatie kun je je energieverbruik en energiekosten optimaliseren als je gebruik maakt
van dynamische prijzen.
Zie verder: DOCS.md
"""
import datetime
import sys
import os
import fnmatch
import time
from requests import get
import json
import hassapi as hass
import pandas as pd
from subprocess import PIPE, run
# import utils
from utils import get_tibber_data, error_handling
from version import __version__
from da_config import Config
from da_meteo import Meteo
from da_prices import DaPrices
from db_manager import DBmanagerObj
import logging


class DaBase(hass.Hass):

    def __init__(self, file_name: str = None):
        self.file_name = file_name
        path = os.getcwd()
        new_path = "/".join(list(path.split('/')[0:-2]))
        sys.path.append(new_path)
        self.make_data_path()
        self.debug = False
        self.config = Config(self.file_name)
        log_level_str = self.config.get(["logging level"], None, "info")
        _log_level = getattr(logging, log_level_str.upper(), None)
        if not isinstance(_log_level, int):
            raise ValueError('Invalid log level: %s' % _log_level)
        self.log_level = _log_level
        logging.addLevelName(logging.DEBUG, 'debug')
        logging.addLevelName(logging.INFO, 'info')
        logging.addLevelName(logging.WARNING, 'waarschuwing')
        logging.addLevelName(logging.ERROR, 'fout')
        logging.addLevelName(logging.CRITICAL, 'kritiek')
        self.protocol_api = self.config.get(['homeassistant', 'protocol api'], default="http")
        self.ip_address = self.config.get(['homeassistant', 'ip adress'], default="supervisor")
        self.ip_port = self.config.get(['homeassistant', 'ip port'], default=None)
        if self.ip_port is None:
            self.hassurl = self.protocol_api + "://" + self.ip_address + "/core/"
        else:
            self.hassurl = self.protocol_api + "://" + self.ip_address + ":" + str(self.ip_port) + "/"
        self.hasstoken = self.config.get(['homeassistant', 'token'], default=os.environ.get("SUPERVISOR_TOKEN"))
        super().__init__(hassurl=self.hassurl, token=self.hasstoken)
        headers = {
            "Authorization": "Bearer " + self.hasstoken,
            "content-type": "application/json",
        }
        resp = get(self.hassurl + "api/config", headers=headers)
        resp_dict = json.loads(resp.text)
        # logging.debug(f"hass/api/config: {resp.text}")
        self.config.set("latitude", resp_dict['latitude'])
        self.config.set("longitude", resp_dict['longitude'])
        db_da_server = self.config.get(['database da', "server"], None, "core-mariadb")
        db_da_port = int(self.config.get(['database da', "port"], None, 3306))
        db_da_name = self.config.get(['database da', "database"], None, "day_ahead")
        db_da_user = self.config.get(['database da', "username"], None, "day_ahead")
        db_da_password = self.config.get(['database da', "password"])
        self.db_da = DBmanagerObj(db_name=db_da_name, db_server=db_da_server, db_port=db_da_port,
                                  db_user=db_da_user, db_password=db_da_password)
        db_ha_server = self.config.get(['database ha', "server"], None, "core-mariadb")
        db_ha_port = int(self.config.get(['database ha', "port"], None, 3306))
        db_ha_name = self.config.get(['database ha', "database"], None, "homeassistant")
        db_ha_user = self.config.get(['database ha', "username"], None, "day_ahead")
        db_ha_password = self.config.get(['database ha', "password"])
        self.db_ha = DBmanagerObj(db_name=db_ha_name, db_server=db_ha_server, db_port=db_ha_port,
                                  db_user=db_ha_user, db_password=db_ha_password)
        self.meteo = Meteo(self.config, self.db_da)
        self.solar = self.config.get(["solar"])
        self.prices = DaPrices(self.config, self.db_da)
        self.prices_options = self.config.get(["prices"])
        self.history_options = self.config.get(["history"])

        self.strategy = self.config.get(["strategy"])
        self.tibber_options = self.config.get(["tibber"], None, None)
        self.notification_entity = self.config.get(["notifications", "notification entity"], None, None)
        self.notification_opstarten = self.config.get(["notifications", "opstarten"], None, False)
        self.notification_berekening = self.config.get(["notifications", "berekening"], None, False)
        self.last_activity_entity = self.config.get(["notifications", "last activity entity"], None, None)
        self.set_last_activity()
        self.graphics_options = self.config.get(["graphics"])
        self.tasks = {
            "calc_optimum_met_debug": {
                "name": "Optimaliseringsberekening met debug",
                "cmd": [
                    "python3",
                    "../prog/day_ahead.py",
                    "debug",
                    "calc"],
                "object": "DaCalc",
                "function": "calc_optimum_met_debug"},
            "calc_optimum": {
                "name": "Optimaliseringsberekening zonder debug",
                "cmd": [
                    "python3",
                    "../prog/day_ahead.py",
                    "calc"],
                "function": "calc_optimum"},
            "tibber": {
                "name": "Verbruiksgegevens bij Tibber ophalen",
                "cmd": [
                    "python3",
                    "../prog/day_ahead.py",
                    "tibber"],
                "function": "get_tibber_data"},
            "meteo": {
                "name": "Meteoprognoses ophalen",
                "cmd": [
                    "python3",
                    "day_ahead.py",
                    "meteo"],
                "function": "get_meteo_data"},
            "prices": {
                "name": "Day ahead prijzen ophalen",
                "cmd": [
                    "python3",
                    "../prog/day_ahead.py",
                    "prices"],
                "function": "get_day_ahead_prices",
            },
            "calc_baseloads": {
                "name": "Bereken de baseloads",
                "cmd": [
                    "python3",
                    "../prog/day_ahead.py",
                    "calc_baseloads"],
                "function": "calc_baseloads"},
            "clean": {
                "name": "Bestanden opschonen",
                "cmd": [
                    "python3",
                    "../prog/day_ahead.py",
                    "clean_data"],
                "function": "clean_data"}
        }

    def start_logging(self):
        logging.debug(f"python pad:{sys.path}")
        logging.info(f"Day Ahead Optimalisering versie: {__version__}")
        logging.info(f"Day Ahead Optimalisering gestart op: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
        logging.debug(f"Locatie: latitude {str(self.config.get(['latitude']))} "
                      f"longitude: {str(self.config.get(['longitude']))}")

    @staticmethod
    def make_data_path():
        if os.path.lexists("../data"):
            return
        else:
            os.symlink("/config/dao_data", "../data")

    def set_last_activity(self):
        if self.last_activity_entity is not None:
            self.call_service("set_datetime", entity_id=self.last_activity_entity,
                              datetime=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def get_meteo_data(self, show_graph: bool = False):
        self.db_da.connect()
        self.meteo.get_meteo_data(show_graph)
        self.db_da.disconnect()

    @staticmethod
    def get_tibber_data():
        """
        """
        get_tibber_data()

    @staticmethod
    def consolidate_data():
        from da_report import Report
        report = Report()
        report.db_da.connect()
        report.db_ha.connect()
        report.consolidate_data()

    def get_day_ahead_prices(self):
        self.db_da.connect()
        self.prices.get_prices(self.config.get(["source day ahead"], self.prices_options, "nordpool"))
        self.db_da.disconnect()

    def get_consumption(self, start: datetime.datetime, until=datetime.datetime.now()):
        """
        Berekent consumption en production tussen start en until
        :param start: begindatum periode, meestal de ingangsdatum van het lopende contractjaar
        :param until: einddatum periode, meestal vandaag
        :return: een dict met consumption en production
        """
        # from da database

        sql = (
            "SELECT SUM(t1.`value`) as consumed, SUM(t2.`value`) as produced "
            "FROM `values` AS t1, `values` AS t2, `variabel`AS v1, `variabel` AS v2 "
            "WHERE (t1.`time`= t2.`time`) "
            "AND (v1.`code` ='cons')AND (v2.`code` = 'prod') "
            "AND (v1.id = t1.variabel) AND (v2.id = t2.variabel) "
            "AND t1.`time` >= UNIX_TIMESTAMP('" +
            start.strftime('%Y-%m-%d') + "') "
            "AND t1.`time` < UNIX_TIMESTAMP('" +
            until.strftime('%Y-%m-%d') + "');"
        )
        data = self.db_da.run_select_query(sql)
        if len(data.index) == 1:
            consumption = data['consumed'][0]
            production = data['produced'][0]
        else:
            consumption = 0
            production = 0

        # from home assistant database
        '''
        self.db_ha.connect()
        grid_sensors = ['sensor.grid_consumption_low', 'sensor.grid_consumption_high', 'sensor.grid_production_low',
                        'sensor.grid_production_high']
        today = datetime.datetime.utcnow().date()
        consumption = 0
        production = 0
        sql = "FLUSH TABLES"
        self.db_ha.run_sql(sql)
        for sensor in grid_sensors:
            sql = (
                    "(SELECT CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') moment, statistics.state "
                    "FROM `statistics`, `statistics_meta` "
                    "WHERE statistics_meta.`id` = statistics.`metadata_id` "
                    "AND statistics_meta.`statistic_id` = '" + sensor + "' "
                    "AND `state` IS NOT null "
                    "AND (CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') BETWEEN '" + start.strftime('%Y-%m-%d') + "' "
                        "AND '" + until.strftime('%Y-%m-%d %H:%M') + "') "
                    "ORDER BY `start_ts` ASC LIMIT 1) " 
                    "UNION "
                    "(SELECT CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') moment, statistics.state "
                    "FROM `statistics`, `statistics_meta` "
                    "WHERE statistics_meta.`id` = statistics.`metadata_id` "
                    "AND statistics_meta.`statistic_id` = '" + sensor + "' "
                    "AND `state` IS NOT null "                    
                    "AND (CONVERT_TZ(statistics.`start_ts`, 'GMT', 'CET') BETWEEN '" + start.strftime('%Y-%m-%d') + "' "
                        "AND '" + until.strftime('%Y-%m-%d %H:%M') + "') "
                    "ORDER BY `start_ts` DESC LIMIT 1); "
            )
            data = self.db_ha.run_select_query(sql)
            if len(data.index) == 2:
                value = data['state'][1] - data['state'][0]
                if 'consumption' in sensor:
                    consumption = consumption + value
                elif 'production' in sensor:
                    production = production + value

        self.db_ha.disconnect()
        '''
        result = {"consumption": consumption, "production": production}
        return result

    def save_df(self, tablename: str, tijd: list, df: pd.DataFrame):
        """
        Slaat de data in het dataframe op in de tabel "table"
        :param tablename: de naam van de tabel waarin de data worden opgeslagen
        :param tijd: de datum tijd van de rijen in het dataframe
        :param df: het dataframe met de code van de variabelen in de kolomheader
        :return: None
        """
        df_db = pd.DataFrame(columns=['time', 'code', 'value'])
        df = df.reset_index()
        columns = df.columns.values.tolist()[1:]
        for index in range(len(tijd)):
            utc = tijd[index].timestamp()
            for c in columns:
                db_row = [str(utc), c, float(df.loc[index, c])]
                df_db.loc[df_db.shape[0]] = db_row
        logging.debug('Save calculated data:\n{}'.format(df_db.to_string()))
        self.db_da.savedata(df_db, debug=False, tablename=tablename)
        return

    @staticmethod
    def get_calculated_baseload(weekday: int) -> list:
        """
        Haalt de berekende baseload op voor de weekdag.
        :param weekday: : 0 = maandag, 6 zondag
        :return: een lijst van eerder berekende baseload van 24uurvoor de betreffende dag
        """
        in_file = "../data/baseload/baseload_" + str(weekday) + ".json"
        with open(in_file, 'r') as f:
            result = json.load(f)
        return result

    def calc_da_avg(self):
        sql_avg = (
            "SELECT AVG(t1.`value`) avg_da FROM "
            "(SELECT `time`, `value`,  from_unixtime(`time`) 'begin' "
            "FROM `values` , `variabel` "
            "WHERE `variabel`.`code` = 'da' AND `values`.`variabel` = `variabel`.`id` "
            "ORDER BY `time` desc LIMIT 24) t1 "
        )
        data = self.db_da.run_select_query(sql_avg)
        result = float(data['avg_da'].values[0])
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
                    if (current_time - creation_time) >= self.config.get(["save days"], self.history_options, 7) * day:
                        os.remove(f)
                        logging.info(f"{f} removed")
            os.chdir(current_dir)
        clean_folder("../data/log", "*.log")
        clean_folder("../data/log", "dashboard.log.*")
        clean_folder("../data/images", "*.png")

    def calc_optimum_met_debug(self):
        from day_ahead import DaCalc
        dacalc = DaCalc(self.file_name)
        dacalc.debug = True
        dacalc.calc_optimum()

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

    def run_task_function(self, task, logfile: bool = False):
        # klass = globals()["class_name"]
        # instance = klass()

        # oude task
        if task not in self.tasks:
            return
        run_task = self.tasks[task]
        file_handler = None
        stream_handler = None
        logging.basicConfig(level=self.log_level,
                            format='%(asctime)s %(levelname)s: %(message)s',
                            datefmt='%Y-%m-%d_%H:%M:%S')
        if logfile:
            # old_stdout = sys.stdout
            logger = logging.getLogger()
            for handler in logger.handlers[:]:  # make a copy of the list
                logger.removeHandler(handler)
            file_handler = logging.FileHandler("../data/log/" + run_task["function"] + "_" +
                                               datetime.datetime.now().strftime("%Y-%m-%d_%H:%M") + ".log")
            file_handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d_%H:%M:%S')
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            stream_handler.setLevel(logging.INFO)
            logger.addHandler(stream_handler)
        self.start_logging()
        try:
            logging.info(f"Day Ahead Optimalisatie gestart: "
                         f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')} taak: {run_task['function']}")
            getattr(self, run_task["function"])()
            self.set_last_activity()
        except Exception as ex:
            logging.error(ex)
            logging.error(error_handling())
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
        filename = ("../data/log/" + run_task["function"] + "_" +
                    datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + ".log")
        with open(filename, "w") as f:
            f.write(log_content)

        '''
        # klass = globals()["class_name"]
        # instance = klass()

        # oude task
        if task not in self.tasks:
            return
        run_task = self.tasks[task]

        # old_stdout = sys.stdout
        # log_file = open("../data/log/" + run_task["task"] + "_" +
        #                datetime.datetime.now().strftime("%Y-%m-%d_%H-%M") + ".log", "w")
        # sys.stdout = log_file
        try:
            logging.info(f"Day Ahead Optimalisatie gestart: "
                         f"{datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S')} taak: {run_task['task']}")
            getattr(self, run_task["task"])()
            self.set_last_activity()
        except Exception as ex:
            logging.error(ex)
            logging.error(error_handling())
        # log_file.flush()
        # sys.stdout = old_stdout
        # log_file.close()
        '''
