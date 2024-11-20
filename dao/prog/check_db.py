import sys
import datetime
import logging
from sqlalchemy import (
    Table,
    Column,
    Integer,
    DateTime,
    String,
    BigInteger,
    Float,
    ForeignKey,
    UniqueConstraint,
    select,
    desc,
    insert,
    update,
)
import pandas as pd
#  from da_base import DaBase
#  sys.path.append("../")
from da_config import Config
from version import __version__
from utils import version_number, error_handling
from db_manager import DBmanagerObj


class CheckDB:
    def __init__(self, file_name: str | None = None):
        # super().__init__(file_name)
        self.file_name = file_name
        self.config = Config(self.file_name)
        self.version = __version__
        self.last_version = None
        self.db_da = self.config.get_db_da(check_create=True)
        self.engine = self.db_da.engine
        """
        db_da_engine = self.config.get(["database da", "engine"], None, "mysql")
        if db_da_engine == "sqlite":
            db_da_name = self.config.get(
                ["database da", "database"], None, "day_ahead.db"
            )
        else:
            db_da_name = self.config.get(["database da", "database"], None, "day_ahead")
        db_da_server = self.config.get(["database da", "server"], None, "core-mariadb")
        db_da_port = int(self.config.get(["database da", "port"], None, 0))
        db_da_user = self.config.get(["database da", "username"], None, "day_ahead")
        db_da_path = self.config.get(["database da", "db_path"], None, "../data")
        db_da_password = self.config.get(["database da", "password"])
        db_da_time_zone = self.config.get(["time_zone"])
        self.db_url = DBmanagerObj.db_url(
            db_dialect=db_da_engine,
            db_name=db_da_name,
            db_server=db_da_server,
            db_user=db_da_user,
            db_password=db_da_password,
            db_port=db_da_port,
            db_path=db_da_path,
        )
        if not sqlalchemy_utils.database_exists(self.db_url):
            sqlalchemy_utils.create_database(self.db_url)
        try:
            self.db_da = DBmanagerObj(
                db_dialect=db_da_engine,
                db_name=db_da_name,
                db_server=db_da_server,
                db_user=db_da_user,
                db_password=db_da_password,
                db_port=db_da_port,
                db_path=db_da_path,
                db_time_zone=db_da_time_zone,
            )
            self.engine = self.db_da.engine
        except Exception as ex:
            error_handling(ex)
            logging.error("Check your credentials")
        """

    def upsert_variabel(self, variabel_table, record):
        select_variabel = select(variabel_table.c.id).where(
            variabel_table.c.id == record[0]
        )
        with self.engine.connect() as connection:
            variabel_result = connection.execute(select_variabel).first()
        if variabel_result:
            query = (
                update(variabel_table)
                .where(variabel_table.c.id == record[0])
                .values(code=record[1], name=record[2], dim=record[3])
            )
        else:
            query = insert(variabel_table).values(
                id=record[0], code=record[1], name=record[2], dim=record[3]
            )
        with self.engine.connect() as connection:
            connection.execute(query)
            connection.commit()
        return

    def update_db_da(self):
        # Defining the Engine
        # Create the Metadata Object
        metadata = self.db_da.metadata
        # Define the version table
        version_table = Table(
            "version",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("moment", DateTime, unique=True),
            Column("value", String(20), unique=True),
        )
        # Create the version table (if not exists)
        metadata.create_all(self.engine)
        l_version = 470

        query = select(version_table.c.moment, version_table.c.value).order_by(
            desc(version_table.c.moment)
        )
        with self.engine.connect() as connection:
            rows = pd.read_sql(query, connection)
        if len(rows) >= 1:
            self.last_version = rows.iloc[0]["value"]
            l_version = version_number(self.last_version)
        n_version = version_number(self.version)

        if l_version < n_version:
            moment = datetime.datetime.fromtimestamp(
                round(datetime.datetime.now().timestamp())
            )
            insert_query = insert(version_table).values(
                moment=moment, value=self.version
            )
            with self.engine.connect() as connection:
                connection.execute(insert_query)
                connection.commit()

        variabel_tabel = Table(
            "variabel",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("code", String(10), unique=True, nullable=False),
            Column("name", String(50), unique=True, nullable=False),
            Column("dim", String(10), nullable=False),
            sqlite_autoincrement=True,  # Ensure SQLite uses AUTOINCREMENT
        )

        if l_version <= 472:
            # check variabel
            # Create the version table (if not exists)
            variabel_tabel.create(self.engine)
            records = [
                [1, "cons", "Verbruik", "kWh"],
                [2, "prod", "Productie", "kWh"],
                [3, "da", "Tarief", "euro/kWh"],
                [4, "gr", "Globale straling", "J/cm2"],
                [5, "temp", "Temperatuur", "°C"],
                [6, "solar_rad", "PV radiation", "J/cm2"],
                [7, "cost", "cost", "euro"],
                [8, "profit", "profit", "euro"],
                [9, "bat_in", "Batterij in", "kWh"],
                [10, "bat_out", "Batterij uit", "kWh"],
                [11, "base", "Basislast", "kWh"],
                [12, "boil", "Boiler", "kWh"],
                [13, "wp", "Warmtepomp", "kWh"],
                [14, "ev", "Elektrische auto", "kWh"],
                [15, "pv_ac", "Zonne energie AC", "kWh"],
                [16, "soc", "SoC", "%"],
                [17, "pv_dc", "Zonne energie DC", "kWh"],
            ]

            for i in range(len(records)):
                record = records[i]
                self.upsert_variabel(variabel_tabel, record)

            logging.info('Table "variabel" met inhoud gecreeerd.')

            # table "values" maken
            values_tabel = Table(
                "values",
                metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
                Column(
                    "variabel",
                    Integer,
                    ForeignKey("variabel.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                Column("time", BigInteger, nullable=False),
                Column("value", Float),
                UniqueConstraint("variabel", "time"),
                sqlite_autoincrement=True,  # Ensure SQLite uses AUTOINCREMENT
            )
            values_tabel.create(self.engine)

            logging.info('Table "values" gecreeerd.')
            prognoses_tabel = Table(
                "prognoses",
                metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
                Column(
                    "variabel",
                    Integer,
                    ForeignKey("variabel.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                Column("time", BigInteger, nullable=False),
                Column("value", Float),
                UniqueConstraint("variabel", "time"),
                sqlite_autoincrement=True,  # Ensure SQLite uses AUTOINCREMENT
            )
            prognoses_tabel.create(self.engine)
            logging.info('Table "prognoses" gecreeerd.')

        if l_version < 20240307:
            record = [18, "mach", "Apparatuur", "kWh"]
            self.upsert_variabel(variabel_tabel, record)
            logging.info('Table "variabel" geupdated.')

        if l_version < 20240805:
            records_2024_8_5 = [
                [16, "soc", "SoC", "%"],
                [19, "soc_0", "SoC 1", "%"],
                [20, "soc_1", "SoC 2", "%"],
                [21, "soc_2", "SoC 3", "%"],
                [22, "soc_3", "SoC 4", "%"],
            ]
            for i in range(len(records_2024_8_5)):
                record = records_2024_8_5[i]
                self.upsert_variabel(variabel_tabel, record)
            logging.info('Table "variabel" geupdated.')


def main():
    checkdb = CheckDB("../data/options.json")
    checkdb.update_db_da()


if __name__ == "__main__":
    main()
