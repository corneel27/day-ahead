import pandas as pd
import numpy as np
import datetime
from sqlalchemy import (
    create_engine,
    Table,
    MetaData,
    select,
    insert,
    update,
    func,
    and_,
    text,
    TIMESTAMP,
)
import sqlalchemy_utils
import os
import logging

# import utils as utils


class DBmanagerObj(object):
    """
    Database manager class.
    """

    def __init__(
        self,
        db_dialect: str,
        db_name: str,
        db_server=None,
        db_user=None,
        db_password=None,
        db_port=None,
        db_path=None,
        db_time_zone: str = "Europe/Amsterdam",
    ):
        """
        Initializes a DBManager object
        Args:
            db_dialect   :Dialect: mysql(=mariadb), sqlite, postgresql
            db_name      :Name of the DB
            db_server    :Server (mysql only)
            db_user      :User (mysql only)
            db_password  :Password (mysql only)
            db_port      :port(mysql via TCP only) Necessary if not 3306
            db_path      :path if sqlite db (sqlite only)
            db_time_zone :time_zone (postgresql only)
        """

        self.db_dialect = db_dialect
        self.db_name = db_name
        self.server = db_server
        self.user = db_user
        self.password = db_password
        self.port = db_port
        self.db_path = db_path
        self.TARGET_TIMEZONE = db_time_zone
        if self.db_dialect == "mysql":
            self.engine = create_engine(
                f"mysql+pymysql://{self.user}:{self.password}@"
                f"{self.server}/{self.db_name}",
                pool_recycle=3600,
                pool_pre_ping=True,
            )
        elif self.db_dialect == "postgresql":
            self.engine = create_engine(
                f"postgresql+psycopg2://{self.user}:{self.password}@"
                f"{self.server}/{self.db_name}"
            )
            with self.engine.connect() as connection:
                connection.execute(text(f"SET timezone = '{self.TARGET_TIMEZONE}';"))
        else:  # sqlite3
            if self.db_path is None:
                self.db_path = "../data"
            # abs_db_path = os.path.abspath(self.db_path) # ../data
            # self.dbname = "home-assistant_v2.db"
            # self.engine = create_engine(f'sqlite:////{abs_db_path}/{self.db_name}')
            self.engine = create_engine(f"sqlite:///{self.db_path}/{self.db_name}")
        if self.db_dialect == "sqlite":
            logging.debug(
                f"Dialect: {self.db_dialect}, database: {self.db_name}, db_path: {self.db_path}"
            )
        else:
            logging.debug(
                f"Dialect: {self.db_dialect}, database: {self.db_name}, server: {self.server}"
            )
        db_url = self.db_url(
            db_dialect=self.db_dialect,
            db_name=self.db_name,
            db_server=self.server,
            db_user=self.user,
            db_password=self.password,
            db_port=self.port,
            db_path=self.db_path,
        )
        if not sqlalchemy_utils.database_exists(db_url):
            raise ConnectionAbortedError
        self.metadata = MetaData()

    @staticmethod
    def db_url(
        db_dialect: str,
        db_name: str,
        db_server=None,
        db_user=None,
        db_password=None,
        db_port=0,
        db_path=None,
    ) -> str:
        if db_dialect == "mysql":
            if db_port == 0:
                result = (
                    f"mysql+pymysql://{db_user}:{db_password}@{db_server}/{db_name}"
                )
            else:
                result = f"mysql+pymysql://{db_user}:{db_password}@{db_server}:{db_port}/{db_name}"
        elif db_dialect == "postgresql":
            if db_port == 0:
                result = f"postgresql+psycopg2://{db_user}:{db_password}@{db_server}/{db_name}"
            else:
                result = (
                    f"postgresql+psycopg2://{db_user}:{db_password}@{db_server}:"
                    f"{db_port}/{db_name}"
                )
        else:  # sqlite3
            if db_path is None:
                db_path = "../data"
            abs_db_path = os.path.abspath(db_path)
            result = f"sqlite:////{abs_db_path}/{db_name}"
        logging.debug(f"db_url: {result}")
        return result

    def log_pool_status(self):
        from inspect import currentframe, getframeinfo

        cf = currentframe()
        cf = cf.f_back
        filename = getframeinfo(cf).filename
        lineno = getframeinfo(cf).lineno
        logging.debug(
            f"Connection status {self.engine.pool.status()} at line "
            f"{lineno} in {filename}"
        )

    # Custom function to handle from_unixtime
    def from_unixtime(self, column):
        if self.db_dialect == "sqlite":
            return func.datetime(column, "unixepoch", "localtime")
        elif self.db_dialect == "postgresql":
            return func.to_char(func.to_timestamp(column), "YYYY-MM-DD HH24:MI:SS")
        else:  # mysql/mariadb
            return func.from_unixtime(column)

    # Custom function to handle UNIX_TIMESTAMP
    def unix_timestamp(self, date_str):
        if self.db_dialect == "sqlite":
            return func.strftime("%s", date_str, "utc")
        elif self.db_dialect == "postgresql":
            return func.extract(
                "epoch",
                func.timezone(self.TARGET_TIMEZONE, func.cast(date_str, TIMESTAMP)),
            )
        else:  # mysql/mariadb
            return func.unix_timestamp(date_str)

    def month(self, column) -> func:
        if self.db_dialect == "sqlite":
            return func.strftime(
                "%Y-%m", func.datetime(column, "unixepoch", "localtime")
            )
        elif self.db_dialect == "postgresql":
            return func.to_char(func.to_timestamp(column), "YYYY-MM")
        else:  # mysql/mariadb
            return func.concat(
                func.year(func.from_unixtime(column)),
                "-",
                func.lpad(func.month(func.from_unixtime(column)), 2, "0"),
            )

    def day(self, column) -> func:
        if self.db_dialect == "sqlite":
            return func.strftime(
                "%Y-%m-%d", func.datetime(column, "unixepoch", "localtime")
            )
        elif self.db_dialect == "postgresql":
            return func.to_char(func.to_timestamp(column), "YYYY-MM-DD")
        else:  # mysql/mariadb
            return func.date(func.from_unixtime(column))

    def hour(self, column) -> func:
        if self.db_dialect == "sqlite":
            return func.strftime(
                "%H:%M", func.datetime(column, "unixepoch", "localtime")
            )
        elif self.db_dialect == "postgresql":
            return func.to_char(func.to_timestamp(column), "HH24:MI")
        else:  # mysql/mariadb
            return func.time_format(func.time(func.from_unixtime(column)), "%H:%i")

    def savedata(self, df: pd.DataFrame, tablename: str = "values"):
        """
        save data in dateframe,
        if id exist then update else insert
        Args:
            df: Dataframe that we wish to save in table tablename
               columns
               code	string
               calculated datetime, 0 if realised
               time	timestamp in sec
               value	float
            tablename: values or prognoses
        """
        logging.debug(f"Opslaan dataframe:\n{df.to_string()}")
        self.log_pool_status()

        # with self.engine.connect() as connection:
        connection = self.engine.connect()
        try:
            self.log_pool_status()
            # Reflect existing tables from the database
            values_table = Table(tablename, self.metadata, autoload_with=self.engine)
            variabel_table = Table("variabel", self.metadata, autoload_with=self.engine)
            df = df.reset_index()  # make sure indexes pair with number of rows
            df["tijd"] = df["time"].apply(
                lambda x: datetime.datetime.fromtimestamp(int(float(x))).strftime(
                    "%Y-%m-%d %H:%M"
                )
            )
            for index, dfrow in df.iterrows():
                logging.debug(
                    f"Save record: {dfrow['tijd']} {dfrow['code']} "
                    f"{dfrow['time']} {dfrow['value']}"
                )
                code = dfrow["code"]
                time = dfrow["time"]
                value = dfrow["value"]
                if not isinstance(value, (int, float)):
                    continue
                if value == float("inf"):
                    continue

                # Get the variabel_id
                select_variabel = select(variabel_table.c.id).where(
                    variabel_table.c.code == code
                )
                variabel_result = connection.execute(select_variabel).first()
                if variabel_result:
                    variabel_id = variabel_result[0]
                else:
                    logging.error(f"Onbekende code opslaan data: {code}")
                    continue

                # Query to check if the record exists
                select_value = select(values_table.c.id).where(
                    (values_table.c.variabel == variabel_id)
                    & (values_table.c.time == time)
                )
                value_result = connection.execute(select_value).first()
                if value_result:
                    # Update existing record
                    value_id = value_result[0]
                    update_value = (
                        update(values_table)
                        .values(value=value)
                        .where(values_table.c.id == value_id)
                    )
                    connection.execute(update_value)
                else:
                    # Record does not exist, perform insert
                    insert_value = insert(values_table).values(
                        variabel=variabel_id, time=time, value=value
                    )
                    connection.execute(insert_value)
            connection.commit()
        finally:
            self.log_pool_status()
            connection.close()
        self.log_pool_status()

    def get_prognose_field(self, field: str, start, end=None, interval="hour"):
        values_table = Table("values", self.metadata, autoload_with=self.engine)
        t1 = values_table.alias("t1")
        variabel_table = Table("variabel", self.metadata, autoload_with=self.engine)
        v1 = variabel_table.alias("v1")
        # Build the SQLAlchemy query
        query = select(
            t1.c.time.label("time"),
            self.from_unixtime(t1.c.time).label("tijd"),
            t1.c.value.label(field),
        ).where(
            and_(
                t1.c.variabel == v1.c.id,
                v1.c.code == field,
                t1.c.time
                >= start,  # self.unix_timestamp(start.strftime('%Y-%m-%d %H:%M:%S'))
            )
        )
        if end is not None:
            query = query.where(
                t1.c.time < self.unix_timestamp(end.strftime("%Y-%m-%d %H:%M:%S"))
            )
        else:
            start_dt = datetime.datetime.fromtimestamp(start)
            if start_dt.hour < 13:
                num_days = 1
            else:
                num_days = 2
            end_dt = start_dt + datetime.timedelta(days=num_days)
            end_dt = datetime.datetime(end_dt.year, end_dt.month, end_dt.day)
            end_ts = end_dt.timestamp()
            query = query.where(
                t1.c.time < self.unix_timestamp(end_dt.strftime("%Y-%m-%d %H:%M:%S"))
            )

        query = query.order_by(t1.c.time)

        # Execute the query and fetch the result into a pandas DataFrame
        with self.engine.connect() as connection:
            result = connection.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        df["tijd"] = pd.to_datetime(df["tijd"])
        return df

    def get_prognose_data(self, start, end=None, interval="hour"):
        values_table = Table("values", self.metadata, autoload_with=self.engine)
        variabel_table = Table("variabel", self.metadata, autoload_with=self.engine)
        if interval == "hour":
            # Aliases for the values table
            t1 = values_table.alias("t1")
            t2 = values_table.alias("t2")
            t3 = values_table.alias("t3")
            t0 = values_table.alias("t0")

            # Aliases for the variabel table
            v1 = variabel_table.alias("v1")
            v2 = variabel_table.alias("v2")
            v3 = variabel_table.alias("v3")
            v0 = variabel_table.alias("v0")

            # Build the SQLAlchemy query
            query = select(
                t1.c.time.label("time"),
                self.from_unixtime(t1.c.time).label("tijd"),
                t0.c.value.label("temp"),
                t1.c.value.label("glob_rad"),
                t2.c.value.label("pv_rad"),
                t3.c.value.label("da_price"),
            ).where(
                and_(
                    t1.c.time == t2.c.time,
                    t1.c.time == t3.c.time,
                    t1.c.time == t0.c.time,
                    t1.c.variabel == v1.c.id,
                    v1.c.code == "gr",
                    t2.c.variabel == v2.c.id,
                    v2.c.code == "solar_rad",
                    t3.c.variabel == v3.c.id,
                    v3.c.code == "da",
                    t0.c.variabel == v0.c.id,
                    v0.c.code == "temp",
                    t1.c.time
                    >= start,  # self.unix_timestamp(start.strftime('%Y-%m-%d %H:%M:%S'))
                )
            )
            if end is not None:
                query = query.where(
                    t1.c.time < end  # self.unix_timestamp(end.strftime("%Y-%m-%d %H:%M:%S"))
                )
            else:
                start_dt = datetime.datetime.fromtimestamp(start)
                if start_dt.hour < 13:
                    num_days = 1
                else:
                    num_days = 2
                end_dt = start_dt + datetime.timedelta(days=num_days)
                end_dt = datetime.datetime(end_dt.year, end_dt.month, end_dt.day)
                end_ts = end_dt.timestamp()
                query = query.where(
                    t1.c.time < self.unix_timestamp(end_dt.strftime("%Y-%m-%d %H:%M:%S"))
                )

            query = query.order_by(t1.c.time)

            # Execute the query and fetch the result into a pandas DataFrame
            with self.engine.connect() as connection:
                result = connection.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            df["tijd"] = pd.to_datetime(df["tijd"])
            return df
        # else: #  interval == "kwartier"

    def get_column_data(
        self,
        tablename: str,
        column_name: str,
        start: datetime.datetime = None,
        end: datetime.datetime = None,
    ):
        """
        Retourneert een dataframe
        :param tablename: de naam van de tabel "prognoses" of "values"
        :param column_name: de code van het veld
        :param start: eerste uur, als deze "None" dan vanaf vandaag
        :param end: tot het laatste uur, als deze "None: dan tot alle aanwezige data
        :return:
        """
        if start is None:
            start = datetime.datetime.now()
        start = start.strftime("%Y-%m-%d %H:%M")
        if end is not None:
            end = end.strftime("%Y-%m-%d %H:%M")
        """
        #  old style sql query
        sqlQuery = (
            "SELECT `time`, `value` " \
            "FROM `variabel`, `" + tablename + "` " \
            "WHERE `variabel`.`code` = '" + column_name + "' " \
            "AND `variabel`.`id` = `" + table + "`.`variabel` " \
            "AND `time` >= UNIX_TIMESTAMP('" + start + "') "
            )
        if end:
            sqlQuery += "AND `time` < UNIX_TIMESTAMP('" + end + "') "
        sqlQuery += "ORDER BY `time`;"
        # print (sqlQuery)
        """
        variabel_table = Table("variabel", self.metadata, autoload_with=self.engine)
        values_table = Table(tablename, self.metadata, autoload_with=self.engine)
        query = select(values_table.c.time, values_table.c.value).where(
            and_(
                variabel_table.c.code == column_name,
                values_table.c.variabel == variabel_table.c.id,
                values_table.c.time >= self.unix_timestamp(start),
            )
        )
        if end is not None:
            query = query.where(values_table.c.time < self.unix_timestamp(end))
        query = query.order_by(values_table.c.time)

        with self.engine.connect() as connection:
            result = connection.execute(query)
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        now_ts = datetime.datetime.now().timestamp()
        df["datasoort"] = np.where(df["time"] <= now_ts, "recorded", "expected")
        df["time"] = df["time"].apply(
            lambda x: datetime.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M")
        )
        return df

    def get_consumption(self, start: datetime.datetime, end=datetime.datetime.now()):
        """
        retourneert een dataframe met consumption en production in periode vanaf start tot until
        :param start: start moment
        :param end: eindmoment , default nu
        :return: dataframe
        """
        values_table = Table("values", self.metadata, autoload_with=self.engine)
        # Aliases for the values table
        t1 = values_table.alias("t1")
        t2 = values_table.alias("t2")

        variabel_table = Table("variabel", self.metadata, autoload_with=self.engine)
        # Aliases for the variabel table
        v1 = variabel_table.alias("v1")
        v2 = variabel_table.alias("v2")

        # Build the SQLAlchemy query
        query = select(
            func.sum(t1.c.value).label("consumed"),
            func.sum(t2.c.value).label("produced"),
        ).where(
            and_(
                t1.c.time == t2.c.time,
                t1.c.variabel == v1.c.id,
                v1.c.code == "cons",
                t2.c.variabel == v2.c.id,
                v2.c.code == "prod",
                t1.c.time >= self.unix_timestamp(start.strftime("%Y-%m-%d %H:%M:%S")),
                t1.c.time < self.unix_timestamp(end.strftime("%Y-%m-%d %H:%M:%S")),
            )
        )

        with self.engine.connect() as connection:
            result = connection.execute(query)

        data = pd.DataFrame(result.fetchall(), columns=result.keys())
        if len(data.index) == 1:
            consumption = data["consumed"][0]
            production = data["produced"][0]
        else:
            consumption = 0
            production = 0

        result = {"consumption": consumption, "production": production}
        return result
