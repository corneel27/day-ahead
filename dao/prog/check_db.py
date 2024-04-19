from db_manager import DBmanagerObj
from da_config import Config
import _version
import utils


class CheckDB:
    def __init__(self):
        self.config = Config("../data/options.json")
        self.version = _version.__version__
        self.last_version = None
        db_da_server = self.config.get(['database da', "server"], None, "core-mariadb")
        db_da_port = int(self.config.get(['database da', "port"], None, 3306))
        db_da_name = self.config.get(['database da', "database"], None, "day_ahead")
        db_da_user = self.config.get(['database da', "username"], None, "day_ahead")
        db_da_password = self.config.get(['database da', "password"])
        try:
            self.db_da = DBmanagerObj(db_name=db_da_name, db_server=db_da_server, db_port=db_da_port,
                                      db_user=db_da_user, db_password=db_da_password)
            self.db_da.connect()
        except Exception as ex:
            print(ex, "Check your credentials")

    def check_db_da(self):
        sql = "show tables like 'version';"
        df = self.db_da.run_select_query(sql)
        if len(df) == 0:  # version doen't exist
            self.last_version = "0.4.50"
            sql = "CREATE TABLE `version` ( \
                `id` INT(10) UNSIGNED NOT NULL AUTO_INCREMENT, \
                `moment` DATETIME NULL DEFAULT NULL, \
                `value` VARCHAR(20) NULL DEFAULT NULL COLLATE 'utf8mb4_unicode_ci', \
                PRIMARY KEY (`id`) USING BTREE, \
                UNIQUE INDEX `moment` (`moment`) USING BTREE, \
                UNIQUE INDEX `value` (`value`) USING BTREE ) \
                COLLATE='utf8mb4_unicode_ci' \
                ENGINE=InnoDB;"
            self.db_da.run_sql(sql)
            l_version = 470
        else:
            sql = "select * from `version` order by `moment` desc limit 1;"
            df = self.db_da.run_select_query(sql)
            self.last_version = df.iloc[0]["value"]
            l_version = utils.version_number(self.last_version)
        # nieuw record als er een nieuwe versie is

        n_version = utils.version_number(self.version)
        if l_version < n_version:
            sql = "INSERT INTO `version` (`moment`, `value`) VALUES (NOW(), '" + self.version + "');"
            self.db_da.run_sql(sql)

        if l_version <= 472:
            # check variabel
            sql = "show tables like 'variabel';"
            df = self.db_da.run_select_query(sql)
            if len(df) == 0:  # variabel doen't exist
                sql = "CREATE TABLE `variabel` ( \
                    `id` INT(10) UNSIGNED NOT NULL AUTO_INCREMENT, \
                    `code` CHAR(10) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci', \
                    `name` CHAR(50) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci', \
                    `dim` CHAR(10) NOT NULL DEFAULT '' COLLATE 'utf8mb4_general_ci', \
                    PRIMARY KEY (`id`) USING BTREE, UNIQUE INDEX `code` (`code`) USING BTREE, \
                    UNIQUE INDEX `name` (`name`) USING BTREE ) COLLATE='utf8mb4_unicode_ci' \
                    ENGINE=InnoDB \
                    AUTO_INCREMENT=1;"
                self.db_da.run_sql(sql)

                # insert records in variabel
                sql_insert = [
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (1, 'cons', 'Verbruik', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (2, 'prod', 'Productie', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (3, 'da', 'Tarief', 'euro/kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) "
                    "VALUES (4, 'gr', 'Globale straling', 'J/cm2'); ",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (5, 'temp', 'Temperatuur', '°C');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) "
                    "VALUES (6, 'solar_rad', 'PV radiation', 'J/cm2'); ",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (7, 'cost', 'cost', 'euro');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (8, 'profit', 'profit', 'euro');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (9, 'bat_in', 'Batterij in', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) "
                    "VALUES (10, 'bat_out', 'Batterij uit', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (11, 'base', 'Basislast', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (12, 'boil', 'Boiler', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (13, 'wp', 'Warmtepomp', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) "
                    "VALUES (14, 'ev', 'Elektrische auto', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) "
                    "VALUES (15, 'pv_ac', 'Zonne energie AC', 'kWh');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (16, 'soc', 'SoC', '%');",
                    "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) "
                    "VALUES (17, 'pv_dc', 'Zonne energie DC', 'kWh');"
                ]
                for i in range(len(sql_insert)):
                    self.db_da.run_sql(sql_insert[i])
                print("Table \"variabel\" met inhoud gecreeerd.")

                # table "values" maken
                sql = "CREATE TABLE IF NOT EXISTS `values` ( \
                    `id` BIGINT(20) UNSIGNED NOT NULL  AUTO_INCREMENT, \
                    `variabel` INT(10) UNSIGNED NOT NULL DEFAULT '0', \
                    `time` BIGINT(20) UNSIGNED NOT NULL DEFAULT '0', \
                    `value` FLOAT NULL DEFAULT NULL, \
                    PRIMARY KEY (`id`) USING BTREE, \
                    UNIQUE INDEX `variabel_time` (`variabel`, `time`) USING BTREE, \
                    INDEX `variabel` (`variabel`) USING BTREE, \
                    INDEX `time` (`time`) USING BTREE )  \
                    COLLATE='utf8mb4_unicode_ci' \
                    ENGINE=InnoDB \
                    AUTO_INCREMENT=1;"
                self.db_da.run_sql(sql)
                print("Table \"values\" gecreeerd.")

                # table "prognoses" maken
                sql = "CREATE TABLE IF NOT EXISTS `prognoses` (  \
                    `id` BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT, \
                    `variabel` INT(10) UNSIGNED NOT NULL DEFAULT '0', \
                    `time` BIGINT(20) UNSIGNED NOT NULL DEFAULT '0', \
                    `value` FLOAT NULL DEFAULT NULL, \
                    PRIMARY KEY (`id`) USING BTREE, \
                    UNIQUE INDEX `variabel_time` (`variabel`, `time`) USING BTREE, \
                    INDEX `variabel` (`variabel`) USING BTREE, \
                    INDEX `time` (`time`) USING BTREE ) \
                    COLLATE='utf8mb4_unicode_ci' \
                    ENGINE=InnoDB \
                    AUTO_INCREMENT=1;"
                self.db_da.run_sql(sql)
                print("Table \"prognoses\" gecreeerd.")

        if l_version < 20240307:
            sql_insert = [
                "INSERT INTO `variabel` (`id`, `code`, `name`, `dim`) VALUES (18, 'mach', 'Apparatuur', 'kWh');"
            ]
            for i in range(len(sql_insert)):
                self.db_da.run_sql(sql_insert[i])
            print("Table \"variabel\" geupdated.")


def main():
    checkdb = CheckDB()
    checkdb.check_db_da()
    checkdb.db_da.disconnect()


if __name__ == "__main__":
    main()
