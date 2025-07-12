import datetime
import tzlocal

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
    text
)
import pandas as pd

#  from da_base import DaBase
#  sys.path.append("../")
from da_config import Config
from version import __version__
from utils import version_number


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
            print("Check your credentials")
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

            print('Table "variabel" met inhoud gecreeerd.')

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

            print('Table "values" gecreeerd.')
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
            print('Table "prognoses" gecreeerd.')

        if l_version < 20240307:
            record = [18, "mach", "Apparatuur", "kWh"]
            self.upsert_variabel(variabel_tabel, record)
            print('Table "variabel" geupdated.')

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
            print('Table "variabel" geupdated.')

        """
        if l_version < 20250700:
            # update variabel with records voor calculated pv_ac, pv_dc and corr. factors
            records_2025_7_0 = [
                [23, "pv_ac_0", "Zonne energie AC 1", "kWh"],
                [24, "pv_ac_1", "Zonne energie AC 2", "kWh"],
                [25, "pv_ac_2", "Zonne energie AC 3", "kWh"],
                [26, "pv_ac_3", "Zonne energie AC 4", "kWh"],
                [27, "pv_ac_4", "Zonne energie AC 5", "kWh"],
                [28, "pv_ac_5", "Zonne energie AC 6", "kWh"],
                [29, "pv_ac_6", "Zonne energie AC 7", "kWh"],
                [30, "pv_ac_7", "Zonne energie AC 8", "kWh"],
                [31, "pv_ac_8", "Zonne energie AC 9", "kWh"],
                [32, "pv_ac_9", "Zonne energie AC 10", "kWh"],

                [33, "pv_dc_0", "Zonne energie DC 1", "kWh"],
                [34, "pv_dc_1", "Zonne energie DC 2", "kWh"],
                [35, "pv_dc_2", "Zonne energie DC 3", "kWh"],
                [36, "pv_dc_3", "Zonne energie DC 4", "kWh"],
                [37, "pv_dc_4", "Zonne energie DC 5", "kWh"],
                [38, "pv_dc_5", "Zonne energie DC 6", "kWh"],
                [39, "pv_dc_6", "Zonne energie DC 7", "kWh"],
                [40, "pv_dc_7", "Zonne energie DC 8", "kWh"],
                [41, "pv_dc_8", "Zonne energie DC 9", "kWh"],
                [42, "pv_dc_9", "Zonne energie DC 10", "kWh"],

                [43, "cf_ac_0", "Correctie factor AC 1", "-"],
                [44, "cf_ac_1", "Correctie factor AC 2", "-"],
                [45, "cf_ac_2", "Correctie factor AC 3", "-"],
                [46, "cf_ac_3", "Correctie factor AC 4", "-"],
                [47, "cf_ac_4", "Correctie factor AC 5", "-"],
                [48, "cf_ac_5", "Correctie factor AC 6", "-"],
                [49, "cf_ac_6", "Correctie factor AC 7", "-"],
                [50, "cf_ac_7", "Correctie factor AC 8", "-"],
                [51, "cf_ac_8", "Correctie factor AC 9", "-"],
                [52, "cf_ac_9", "Correctie factor AC 10", "-"],

                [53, "cf_dc_0", "Correctie factor DC 1", "-"],
                [54, "cf_dc_1", "Correctie factor DC 2", "-"],
                [55, "cf_dc_2", "Correctie factor DC 3", "-"],
                [56, "cf_dc_3", "Correctie factor DC 4", "-"],
                [57, "cf_dc_4", "Correctie factor DC 5", "-"],
                [58, "cf_dc_5", "Correctie factor DC 6", "-"],
                [59, "cf_dc_6", "Correctie factor DC 7", "-"],
                [60, "cf_dc_7", "Correctie factor DC 8", "-"],
                [61, "cf_dc_8", "Correctie factor DC 9", "-"],
                [62, "cf_dc_9", "Correctie factor DC 10", "-"],
            ]
            for i in range(len(records_2025_7_0)):
                record = records_2025_7_0[i]
                self.upsert_variabel(variabel_tabel, record)
            print('Table "variabel" geupdated.')
        """

        # timezone in postgresql could be wrong, check and report
        if self.db_da.db_dialect == "postgresql":
            with self.db_da.engine.connect() as con:
                timezone = tzlocal.get_localzone_name()
                statement = text("SHOW TIMEZONE;")
                result = con.execute(statement)
                row = result.first()
                tz_db = row[0]
                if tz_db != timezone:
                    print(f'De timezone van de database "day_ahead" is "{tz_db}" en wijkt af van local timezone: {timezone}')
                    print("Update de timezone (zie DOCS.md)")

        if l_version < n_version:
            # update version number database
            moment = datetime.datetime.fromtimestamp(
                round(datetime.datetime.now().timestamp())
            )
            insert_query = insert(version_table).values(
                moment=moment, value=self.version
            )
            with self.engine.connect() as connection:
                connection.execute(insert_query)
                connection.commit()

def main():
    checkdb = CheckDB("../data/options.json")
    checkdb.update_db_da()


if __name__ == "__main__":
    main()
