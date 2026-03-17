import datetime

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
    and_,
    delete,
    literal_column,
)
import pandas as pd

#  from da_base import DaBase
#  sys.path.append("../")
from dao.lib.da_config import Config
from version import __version__
from utils import version_number


class CheckDAPDB:
    def __init__(self, file_name: str | None = None):
        self.file_name = file_name
        self.config = Config(self.file_name)
        self.version = __version__
        self.last_version = None
        self.db_da = self.config.get_db_da(key="database_dap", check_create=True)
        self.engine = self.db_da.engine

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

    def get_all_var_data(
        self,
        tablename: str,
        column_name: str,
    ):
        """
        Retourneert een dataframe
        :param tablename: de naam van de tabel "prognoses" of "values"
        :param column_name: de code van het veld
        :return:
        """

        variabel_table = Table(
            "variabel", self.db_da.metadata, autoload_with=self.engine
        )
        values_table = Table(tablename, self.db_da.metadata, autoload_with=self.engine)
        query = select(
            values_table.c.time.label("time"),
            literal_column("'" + column_name + "'").label("code"),
            values_table.c.value.label("value"),
        ).where(
            and_(
                variabel_table.c.code == column_name,
                values_table.c.variabel == variabel_table.c.id,
            )
        )
        query = query.order_by("time")

        with self.engine.connect() as connection:
            df = pd.read_sql(query, connection)
        return df

    def delete_all_var_data(
        self,
        tablename: str,
        variabel_id: int,
    ):
        values_table = Table(tablename, self.db_da.metadata, autoload_with=self.engine)
        delete_stmt = delete(values_table).where(
            values_table.c.variabel == variabel_id,
        )
        with self.engine.connect() as connection:
            connection.execute(delete_stmt)
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
        l_version = 20251201

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
            Column("code", String(15), unique=True, nullable=False),
            Column("name", String(50), unique=True, nullable=False),
            Column("dim", String(10), nullable=False),
            sqlite_autoincrement=True,  # Ensure SQLite uses AUTOINCREMENT
        )

        if l_version <= 20260101:
            # check variabel
            # Create the version table (if not exists)
            variabel_tabel.create(self.engine)
            records = [
                [1, "cons", "Verbruik", "MWh"],
                [2, "prod_zon", "Productie zon", "MWh"],
                [3, "prod_wind", "Productie wind (land)", "MWh"],
                [4, "prod_zeewind", "Productie wind (zee)", "MWh"],
                [5, "da", "Day Ahead prijs epex", "euro/kWh"],
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
    checkdb = CheckDAPDB("data/options_dap.json")
    checkdb.update_db_da()


if __name__ == "__main__":
    main()
