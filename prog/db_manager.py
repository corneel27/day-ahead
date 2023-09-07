import pandas as pd
import mysql.connector
import numpy as np
import datetime


class DBmanagerObj(object):
    """
    Database manager class.
    """

    def __init__(self, db_name,
                 db_server=None, db_user=None, db_password=None,
                 db_port=None, unix_socket=None, charset='utf8mb4'):
        """
        Initializes a DBManager object
        Args:
            db_name      :Name of the DB
            db_server    :Server (mysql only)
            db_user      :User (mysql only)
            db_password  :Password (mysql only)
            db_port      :port(mysql via TCP only) Necessary if not 3306
            unix_socket  :socket for local connectivity. If available, connection
                          is slightly faster than through TCP. 
            charset      :Codificación a utilizar por defecto en la conexión
        """

        # Store paths to the main project folders and files
        self.dbname = db_name
        self.server = db_server
        self.user = db_user
        self.password = db_password
        self.port = db_port
        self.unix_socket = unix_socket
        self.charset = charset

        # Other class variables
        self.dbON = False    # Will switch to True when the db is connected.
        # Connector to database
        self._conn = None
        # Cursor of the database
        self._c = None

    def connect(self):
        # Try connection
        try:
            if self.unix_socket:
                self._conn = mysql.connector.connect(host=self.server,
                                                     user=self.user, passwd=self.password,
                                                     db=self.dbname, auth_plugin='mysql_native_password')
                # unix_socket=unix_socket, charset=charset)
            elif self.port:
                self._conn = mysql.connector.connect(host=self.server,
                                                     user=self.user, passwd=self.password, port=self.port,
                                                     db=self.dbname, auth_plugin='mysql_native_password')
                # port=self.port, charset=charset)
            else:
                self._conn = mysql.connector.connect(host=self.server,
                                                     user=self.user, passwd=self.password,
                                                     db=self.dbname, charset=self.charset, auth_plugin='mysql_native_password')
            self._c = self._conn.cursor()
            print('MySQL database connection successful. Default database:', self.dbname)
            self.dbON = True
            # self._conn.set_character_set('utf8')
        except Exception as e:
            print("---- Error connecting to the database")
            raise e
        return

    def disconnect(self):
        self.__del__()

    def __del__(self):
        """
        When destroying the object, it is necessary to commit changes
        in the database and close the connection
        """

        try:
            self._c.close()
            if self._conn.is_connected():
                self._conn.commit()
                self._conn.close()
        except:
            pass  # print("---- Error closing database")

        return

    """def setConnCharset(self, charsetcode):
        self._conn.set_character_set(charsetcode)
        return
    """

    def readDBtable(self, tablename, limit=None, selectOptions=None,
                    filterOptions=None, orderOptions=None):
        """
        Read data from a table in the database can choose to read only some
        specific fields
        Args:
            tablename    :  Table to read from
            selectOptions:  string with fields that will be retrieved
                            (e.g. 'REFERENCIA, Resumen')
            filterOptions:  string with filtering options for the SQL query
                            (e.g., 'UNESCO_cd=23')
            orderOptions:   string with field that will be used for sorting the
                            results of the query
                            (e.g, 'Cconv')
            limit:          The maximum number of records to retrieve
        """

        sqlQuery = 'SELECT '
        if selectOptions:
            sqlQuery += selectOptions
        else:
            sqlQuery += '*'

        sqlQuery += ' FROM ' + tablename + ' '

        if filterOptions:
            sqlQuery += ' WHERE ' + filterOptions

        if orderOptions:
            sqlQuery += ' ORDER BY ' + orderOptions

        if limit:
            sqlQuery += ' LIMIT ' + str(limit)

        sqlQuery += ';'

        try:
            # This is to update the connection to changes by other
            # processes.
            self._conn.commit()

            # Return the pandas dataframe. Note that numbers in text format
            # are not converted to
            return pd.read_sql(sqlQuery, con=self._conn,
                               coerce_float=False)

        except Exception as E:
            print(str(E))
            print('Error in query:', sqlQuery)
            return

    def getTableNames(self):
        """
        Returns a list with the names of all tables in the database
        """
        sqlcmd = ("SELECT table_name FROM INFORMATION_SCHEMA.TABLES " +
                  "WHERE table_schema='" + self.dbname + "'")
        self._c.execute(sqlcmd)
        tbnames = [el[0] for el in self._c.fetchall()]
        return tbnames

    def getColumnNames(self, table_name):
        sql = "SHOW `columns` FROM `" + table_name+"`;"
        self._c.execute(sql)
        col_names = [el[0] for el in self._c.fetchall()]
        return col_names

    def setField(self, tablename, keyflds, valueflds, values):
        """
        Update records of a DB table
        Args:
            tablename:  Table that will be modified
            keyflds:    list with the column names that will be used as key
                        (e.g. 'REFERENCIA')
            valueflds:  list with the names of the columns that will be updated
                        (e.g., 'Lemas')
            values:     A list of tuples in the format
                            (key1value, key2value, ..fld1value, )
                        (e.g., [('Ref1', 'gen celula'),
                                ('Ref2', 'big_data, algorithm')])
        """

        # Auxiliary function to circularly shift a tuple one position to the
        # left
        def circ_left_shift(tup):
            ls = list(tup[1:]) + [tup[0]]
            return tuple(ls)

        # Make sure valueflds is a list, and not a single string
        if not isinstance(valueflds, (list,)):
            valueflds = [valueflds]

        # Make sure keyflds is a list, and not a single string
        if not isinstance(keyflds, (list,)):
            keyflds = [keyflds]

        # To allow for column names that have spaces
        valueflds = list(map(lambda x: '`'+x+'`', valueflds))

        ncol_keys = len(keyflds)
        ncol_values = len(valueflds)

        if (len(values[0]) == ncol_keys + ncol_values):
            # Make sure the tablename is valid
            if tablename in self.getTableNames():

                # # Update DB entries one by one.
                # # WARNING: THIS VERSION MAY NOT WORK PROPERLY IF v
                # #          HAS A STRING CONTAINING "".
                # for v in values:
                #     sqlcmd = ('UPDATE ' + tablename + ' SET ' +
                #               ', '.join(['{0} ="{1}"'.format(f, v[i + 1])
                #                          for i, f in enumerate(valueflds)]) +
                #               ' WHERE {0}="{1}"'.format(keyfld, v[0]))
                #     self._c.execute(sqlcmd)

                # This is the old version: it might not have the problem of
                # the above version, but did not work properly with sqlite.
                # Make sure we have a list of tuples; necessary for mysql

                # Put key value last in the tuples
                for i in range(len(keyflds)):
                    values = list(map(circ_left_shift, values))

                sqlcmd = 'UPDATE ' + tablename + ' SET '
                sqlcmd += ', '.join([el+'=%s' for el in valueflds])
                sqlcmd += ' WHERE '
                sqlcmd += 'AND '.join([el+'=%s' for el in keyflds])
                self._c.executemany(sqlcmd, values)

                # Commit changes
                self._conn.commit()

            else:
                print('Error udpating table values: The table does not exist')
        else:
            print('Error updating table values: number of columns mismatch')

        return

    def upsert(self, tablename, keyflds, df, robust=True):
        """
        Update records of a DB table with the values in the df
        This function implements the following additional functionality:
        * If there are columns in df that are not in the SQL table,
          columns will be added
        * New records will be created in the table if there are rows
          in the dataframe without an entry already in the table. For this,
          keyfld indicates which is the column that will be used as an
          index
        Args:
            tablename:  Table that will be modified
            keyflds:     string with the column name that will be used as key
                        (e.g. 'REFERENCIA')
            df:         Dataframe that we wish to save in table tablename
            robust:     If False, verifications are skipped
                        (for a faster execution)
        """

        # Make sure keyflds is a list, and not a single string
        if not isinstance(keyflds, (list,)):
            keyflds = [keyflds]

        # Check that table exists and keyfld exists both in the Table and the
        # Dataframe
        if robust:
            if tablename in self.getTableNames():
                for keyfld in keyflds:
                    if not ((keyfld in df.columns) and
                       (keyfld in self.getColumnNames(tablename))):
                        print("Upsert function failed: Key field does not exist",
                              "in the selected table and/or dataframe")
                        return
            else:
                print('Upsert function failed: Table does not exist')
                return

        # Reorder dataframe to make sure that the key fields goes first
        for keyfld in keyflds:
            flds = [keyfld] + [x for x in df.columns if x != keyfld]
            df = df[flds]

        if robust:
            # Create new columns if necessary
            for clname in df.columns:
                if clname not in self.getColumnNames(tablename):
                    if df[clname].dtypes == np.float64:
                        self.addTableColumn(tablename, clname, 'DOUBLE')
                    else:
                        if df[clname].dtypes == np.int64:
                            self.addTableColumn(tablename, clname, 'INTEGER')
                        else:
                            self.addTableColumn(tablename, clname, 'TEXT')

        # Check which values are already in the table, and split
        # the dataframe into records that need to be updated, and
        # records that need to be inserted
        keyintable = self.readDBtable(tablename, limit=None,
                                      selectOptions=', '.join(keyflds))
        keyintable = keyintable[keyfld].tolist()
        values = [tuple(x) for x in df.values]
        values_insert = list(filter(lambda x: x[0] not in keyintable, values))
        values_update = list(filter(lambda x: x[0] in keyintable, values))

        if len(values_update):
            self.setField(tablename, keyfld, df.columns[1:].tolist(),
                          values_update)
        if len(values_insert):
            self.insertInTable(tablename, df.columns.tolist(), values_insert)

        return

    def savedata(self, df, debug=False):
        """
        save data in dateframe,
        id exist then update else insert
        Args:
            df:         Dataframe that we wish to save in table tablename
               columns  
               code	string
               calculated datetime, 0 if realised
               time	timestamp in sec
               value	float
            debug: print queries, don't execute
        """
        df = df.reset_index()  # make sure indexes pair with number of rows
        for index, dfrow in df.iterrows():
            # pprint(dfrow)
            code = dfrow['code']
            time = dfrow['time']
            value = dfrow['value']
            if not (type(value) == int or type(value) == float):
                continue
            if value == float('inf'):
                continue
            query = "SELECT `id` FROM `variabel` where code = '" + code + "';"
            if debug:
                print(query)
            self._c.execute(query)
            rows = self._c.fetchall()
            if len(rows) == 1:
                # record is present
                variabel_id = rows[0][0]
            query = "SELECT `values`.`id` FROM `values` WHERE " \
                    "`values`.`variabel` = " + \
                str(variabel_id) + " and `time` = '" + time + "';"
            if debug:
                print(query)
            self._c.execute(query)
            rows = self._c.fetchall()
            if len(rows) == 1:
                # record is present
                id = rows[0][0]
                query = 'UPDATE `values` SET `value` = %s WHERE id= %s;'
                if debug:
                    print(query)
                self._c.execute(query, (value, id))
                self._conn.commit()
            else:
                # make new record
                query = "INSERT INTO `values` (variabel, time, value) VALUES (%s, %s, %s);"
                val = (str(variabel_id), time, value)
                if debug:
                    print(query, val)
                else:
                    self._c.execute(query, val)
                    self._conn.commit()

    def getPrognoseData(self, start, end):
        sqlQuery = "SELECT FROM_UNIXTIME(t1.`time`) AS tijd,t1.`time`,  t0.`value` 'temp', " \
                   "t1.`value` 'glob_rad', t2.`value` 'pv_rad', t3.`value` 'da_price' " \
                   "FROM `values` AS t1, `values` AS t2, `values` AS t3, `values` AS t0, variabel AS v1, variabel AS v2, " \
                   "variabel AS v3, variabel AS v0 " \
                   "WHERE (t1.`time`= t2.`time`) AND (t1.`variabel` = v1.id AND v1.`code` = 'gr') AND " \
                   "(t2.`variabel` = v2.id AND v2.code = 'solar_rad') " \
                   "AND t3.`time`= t1.`time` AND t3.`variabel`= v3.id AND v3.code ='da' AND " \
                   "t0.`time` = t1.`time` AND t0.`variabel`= v0.id AND v0.`code`= 'temp' " \
                   "and t1.`time` >= " + str(start)
        if (end != None):
            sqlQuery += " and t1.`time` < " + str(end)
        sqlQuery += " ORDER BY t1.`time`;"
        self._conn.commit()

        # Return the pandas dataframe. Note that numbers in text format are not converted
        return pd.read_sql(sqlQuery, con=self._conn, coerce_float=False)

    def getColumnPrognoseData(self, column, start, end):
        sqlQuery = "SELECT `time`, `value` from prognose " \
                   "where `code` = '" + column + "' and time >= " + \
            str(start) + " and time < " + str(end) + ";"
        # print (sqlQuery)
        self._conn.commit()
        return pd.read_sql(sqlQuery, con=self._conn, coerce_float=False)

    def run_select_query(self, sql):
        self._conn.commit()
        self._c.execute(sql)
        rows = self._c.fetchall()
        columns = [i[0] for i in self._c.description]
        df = pd.DataFrame(columns=columns)
        for row in rows:
            df.loc[df.shape[0]] = [value for value in row]
        return df

    def run_sql(self, sql):
        self._conn.commit()
        self._conn.cmd_query(sql)

    def get_time_latest_record(self, code: str) -> datetime.datetime:
        query = ("SELECT from_unixtime(`time`) tijd, `value` "
                 "FROM `values`, `variabel` "
                 "WHERE `variabel`.`code` = '" + code +
                 "'  and `values`.`variabel` = `variabel`.`id` "
                 "ORDER BY `time` desc LIMIT 1")
        df = self.run_select_query(query)
        df = df.reset_index()  # make sure indexes pair with number of rows
        result = None
        for row in df.itertuples():
            result = row.tijd
        return result
