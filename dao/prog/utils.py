
from calendar import month

from dateutil import easter
import datetime
import bisect
import math
import json
import os
import sys
import numpy as np
import pandas as pd
from requests import post
import logging
import traceback
from sqlalchemy import Table, select, and_
from dao.prog.version import __version__


def make_data_path():
    if os.path.lexists("../data"):
        return
    else:
        os.symlink("/config/dao_data", "../data")


def is_laagtarief(dtime, switch_hour):
    jaar = dtime.year
    datum = datetime.datetime(dtime.year, dtime.month, dtime.day)
    if datum.weekday() >= 5:  # zaterdag en zondag
        return True
    if (dtime.hour < 7) or (dtime.hour >= switch_hour):  # door de week van 7 tot 21/23
        return True
    feestdagen = [
        datetime.datetime(jaar, 1, 1),
        datetime.datetime(jaar, 4, 27),
        datetime.datetime(jaar, 12, 25),
        datetime.datetime(jaar, 12, 26),
    ]
    pasen = easter.easter(jaar)
    feestdagen.append(pasen + datetime.timedelta(days=1))  # 2e paasdag
    feestdagen.append(pasen + datetime.timedelta(days=39))  # hemelvaart
    feestdagen.append(pasen + datetime.timedelta(days=50))  # 2e pinksterdag

    for day in feestdagen:
        if day == datum:  # dag is een feestdag
            return True
    return False


def calc_adjustment_heatcurve(
    price_act: float, price_avg: float, adjustment_factor, old_adjustment: float
) -> float:
    """
    Calculate the adjustment of the heatcurve
    formule: -0,5*(price-price_avg)*10/price_avg
    :param price_act: the actual hourprice
    :param price_avg: the day average of the price
    :param adjustment_factor: factor in K/% for instance 0,4K per 10% = 0.04 K/%
    :param old_adjustment: current/old adjustment
    :return: the calculated adjustment
    """
    if price_avg == 0:
        adjustment = 0
    else:
        adjustment = round(
            -adjustment_factor * (price_act - price_avg) * 100 / price_avg, 1
        )
    # toename en afname maximeren op 10 x adjustment factor
    if adjustment >= old_adjustment:
        adjustment = min(adjustment, old_adjustment + adjustment_factor * 10)
    else:
        adjustment = max(adjustment, old_adjustment - adjustment_factor * 10)
    return round(adjustment, 1)


def get_value_from_dict(dag: str, options: dict) -> float:
    """
    Selecteert uit een dict van datum/value paren de juiste value
    :param dag: string van de dag format yyyy-mm-dd
    :param options: dict van datum/value paren bijv. {'2022-01-01': 0.002, '2023-03-01': 0.018}
    :return: de correcte value
    """
    o_list = list(options.keys())
    result = options.get(dag, options[o_list[bisect.bisect_left(o_list, dag) - 1]])
    return result


def convert_timestr(time_str: str, now_dt: datetime.datetime) -> datetime.datetime:
    result_hm = datetime.datetime.strptime(time_str, "%H:%M:%S")
    result = datetime.datetime(
        now_dt.year, now_dt.month, now_dt.day, result_hm.hour, result_hm.minute
    )
    return result


def get_tibber_data():
    from da_config import Config
    from db_manager import DBmanagerObj

    def get_datetime_from_str(s):
        # "2022-09-01T01:00:00.000+02:00"
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")

    # Generate the list of timestamps
    def generate_hourly_timestamps(start_gen: float, end_gen: float) -> list:
        all_hours = []
        current_ts = start_gen
        while current_ts <= end_gen:
            all_hours.append(current_ts)
            current_ts += 3600
        return all_hours

    config = Config("../data/options.json")
    tibber_options = config.get(["tibber"])
    url = config.get(["api url"], tibber_options, "https://api.tibber.com/v1-beta/gql")
    db_da = config.get_db_da()
    prices_options = config.get(["prices"])
    headers = {
        "Authorization": "Bearer " + tibber_options["api_token"],
        "content-type": "application/json",
    }
    now_ts = latest_ts = math.ceil(datetime.datetime.now().timestamp() / 3600) * 3600
    start_ts = None
    if len(sys.argv) > 2:
        # datetime start is given
        start_str = sys.argv[2]
        try:
            start_ts = datetime.datetime.strptime(start_str, "%Y-%m-%d").timestamp()
            timestamps = generate_hourly_timestamps(start_ts, now_ts)
            latest_ts = start_ts
        except Exception as ex:
            error_handling(ex)
            return

    # no starttime
    if (len(sys.argv) <= 2) or (start_ts is None):
        # search first missing
        start_ts = datetime.datetime.strptime(
            prices_options["last invoice"], "%Y-%m-%d"
        ).timestamp()
        timestamps = generate_hourly_timestamps(start_ts, now_ts)
        values_table = Table("values", db_da.metadata, autoload_with=db_da.engine)
        variabel_table = Table("variabel", db_da.metadata, autoload_with=db_da.engine)
        for code in ["cons", "prod"]:
            # Query the existing timestamps from the values table
            query = select(values_table.c.time).where(
                and_(
                    variabel_table.c.code == code,
                    variabel_table.c.id == values_table.c.variabel,
                    values_table.c.time.between(start_ts, now_ts),
                )
            )
            with db_da.engine.connect() as connection:
                existing_timestamps = {row[0] for row in connection.execute(query)}

            # Find missing timestamps by comparing the generated list with the existing timestamps
            missing_timestamps = [
                ts for ts in timestamps if ts not in existing_timestamps
            ]
            if len(missing_timestamps) == 0:
                latest = start_ts
            else:
                latest = missing_timestamps[0]
            latest_ts = min(latest_ts, latest)

    count = math.ceil((now_ts - latest_ts) / 3600)
    logging.info(
        f"Tibber data present tot en met: "
        f"{str(datetime.datetime.fromtimestamp(latest_ts - 3600))}"
    )
    if count < 24:
        logging.info("Er worden geen data opgehaald.")
        return

    query = (
        "{ "
        '"query": '
        ' "{ '
        "   viewer { "
        "     homes { "
        "      production(resolution: HOURLY, last: " + str(count) + ") { "
        "        nodes { "
        "          from "
        "          profit "
        "          production "
        "        } "
        "      } "
        "    consumption(resolution: HOURLY, last: " + str(count) + ") { "
        "        nodes { "
        "          from "
        "          cost "
        "          consumption "
        "        } "
        "      } "
        "    } "
        "  } "
        '}" '
        "}"
    )

    now = datetime.datetime.now()
    today_ts = datetime.datetime(
        year=now.year, month=now.month, day=now.day
    ).timestamp()
    logging.debug(query)
    resp = post(url, headers=headers, data=query)
    tibber_dict = json.loads(resp.text)
    production_nodes = tibber_dict["data"]["viewer"]["homes"][0]["production"]["nodes"]
    consumption_nodes = tibber_dict["data"]["viewer"]["homes"][0]["consumption"][
        "nodes"
    ]
    tibber_df = pd.DataFrame(columns=["time", "code", "value"])
    for node in production_nodes:
        timestamp = int(get_datetime_from_str(node["from"]).timestamp())
        if timestamp < today_ts:
            time_stamp = str(timestamp)
            if not (node["production"] is None):
                code = "prod"
                value = float(node["production"])
                logging.info(f"{node} {time_stamp} {value}")
                tibber_df.loc[tibber_df.shape[0]] = [time_stamp, code, value]
            if not (node["profit"] is None):
                code = "profit"
                value = float(node["profit"])
                logging.info(f"{node} {time_stamp} {value}")
                tibber_df.loc[tibber_df.shape[0]] = [time_stamp, code, value]

    for node in consumption_nodes:
        timestamp = int(get_datetime_from_str(node["from"]).timestamp())
        if timestamp < today_ts:
            time_stamp = str(timestamp)
            if not (node["consumption"] is None):
                code = "cons"
                value = float(node["consumption"])
                logging.info(f"{node} {time_stamp} {value}")
                tibber_df.loc[tibber_df.shape[0]] = [time_stamp, code, value]
            if not (node["cost"] is None):
                code = "cost"
                value = float(node["cost"])
                logging.info(f"{node} {time_stamp} {value}")
                tibber_df.loc[tibber_df.shape[0]] = [time_stamp, code, value]
    logging.info(
        f"Opgehaalde data bij Tibber (database records):"
        f"\n{tibber_df.to_string(index=False)}"
    )
    db_da.savedata(tibber_df)


def calc_uur_index(dt: datetime, tijd: list, interval: str) -> int:
    """
    Berekent van parameter dt de index in lijst uur
    :param dt: de datetime waarvan de index wordt gezocht
    :param tijd: lijst met datetime van begin van het betreffende interval
    :param interval: str "1hour" of "15min"
    :return: het indexnummer in de lijst
    """
    result_index = len(tijd)
    if (result_index == 0) or (dt < tijd[0]):
        return result_index
    if interval == "1hour":
        delta = 60
    else:
        delta = 15
    for u in range(len(tijd)):
        if dt < (tijd[u] + datetime.timedelta(minutes=delta)):
            result_index = u
            break
    return result_index


def get_version():
    return __version__


def version_number(version_str: str) -> int:
    lst = [x for x in version_str.split(".")]
    lst = lst[:3]
    lst.reverse()
    result = sum(int(x) * (100**i) for i, x in enumerate(lst))
    return result


def log_exc_plus():
    """
    Print the usual traceback information,
    """
    tb = sys.exc_info()[2]
    while 1:
        if not tb.tb_next:
            break
        tb = tb.tb_next
    stack = []
    f = tb.tb_frame
    while f:
        stack.append(f)
        f = f.f_back
    stack.reverse()
    traceback.print_exc()
    for frame in stack:
        logging.error(
            f"File: {frame.f_code.co_filename}, line {frame.f_lineno}, "
            f"in {frame.f_code.co_name}"
        )


def error_handling(ex):
    if logging.root.level == logging.DEBUG:
        logging.exception(ex)
    else:
        log_exc_plus()


def prnt_xy(x: list, y: list):
    for i in range(len(x)):
        print(f"{i} {x[i]}  {y[i]}")
    print()


def interpol_rows(
    row, new_row, old_val, field, interval, quantity, result_df
) -> pd.DataFrame:
    new_x = []
    calc_x = row["tijd"]
    end_x = new_row["tijd"]
    while calc_x < end_x:
        new_x.append(calc_x)
        calc_x += datetime.timedelta(minutes=interval)
    delta_x = (new_row["tijd"] - row["tijd"]).seconds * 2 / 60  # in minuten
    if old_val is None:
        delta_y = new_row[field] - row[field]
    else:
        delta_y = new_row[field] - old_val
    delta_x_ref = datetime.timedelta(minutes=(delta_x / 2 - interval) / 2)
    x_ref = row["tijd"] + delta_x_ref
    a = delta_y / (delta_x + delta_x_ref.seconds / 60)  # a = value/minuut
    # een andere offset zorgt voor een gelijke integraal

    factor = interval * 2 / delta_x if quantity else 1
    for x in new_x:
        if x_ref > x:
            d_x = x_ref - x
            d_x_min = -d_x.seconds / 60
        else:
            d_x = x - x_ref
            d_x_min = d_x.seconds / 60
        y = (row[field] + a * d_x_min) * factor
        result_df.loc[result_df.shape[0]] = [x, y]
    return result_df


def interpolate_old(
    # org_x: list[datetime.datetime],
    # org_y: list[float],
    # start_x: datetime.datetime,
    # end_x: datetime.datetime,
    org_df: pd.DataFrame,
    field: str,
    interval: int,
    quantity: bool = False,
) -> pd.DataFrame:
    result_df = pd.DataFrame(columns=["tijd", field])
    row = None
    old_val = None
    now_val = None
    for new_index, new_row in org_df.iterrows():
        if row is None:
            row = new_row
            continue
        old_val = now_val
        now_val = row[field]
        result_df = interpol_rows(
            row, new_row, old_val, field, interval, quantity, result_df
        )
        row = new_row
    delta_x = org_df.iloc[-1]["tijd"] - org_df.iloc[-2]["tijd"]
    new_row = pd.Series({"tijd": row["tijd"] + delta_x, field: row[field]})
    result_df = interpol_rows(
        row, new_row, old_val, field, interval, quantity, result_df
    )
    result_df.index = pd.to_datetime(result_df["tijd"])
    return result_df


def tst_interpolate():
    x = [datetime.datetime(year=2024, month=10, day=19, hour=hour) for hour in range(4)]
    y = [2, 3, 4, 3]
    df_dict = {"tijd": x, "temp": y}
    df_start = pd.DataFrame(df_dict)
    df_start.index = pd.to_datetime(df_start["tijd"])
    print(f"Start: \n {df_start.to_string()}\n")
    interval = 15
    result_df = interpolate(df_start, "temp", interval, quantity=True)
    print(f"\nResultaat: \n{result_df.to_string()}\n")
    # prnt_xy(result["tijd"], result["value"])


"""
# Voorbeeld: 1D interpolatie
points = [0, 1, 2, 3, 4]
all_interp = []
for i in range(1, len(points) - 2):
    segment = catmull_rom_spline(
        points[i - 1], points[i], points[i + 1], points[i + 2], n_points=5
    )
    all_interp.extend(segment.tolist())

print(all_interp)
"""


def interpolate_prognose_data():
    from da_config import Config
    from db_manager import DBmanagerObj

    config = Config("../data/options.json")
    db_da = config.get_db_da()
    start_ts = datetime.datetime(year=2024, month=11, day=12).timestamp()
    end_ts = datetime.datetime(year=2024, month=11, day=14).timestamp()
    prognose_data = db_da.get_prognose_data(start=start_ts, end=end_ts)
    print(prognose_data.to_string())


def interpolate(df: pd.DataFrame, field: str, quantity: bool = False) -> pd.DataFrame:
    """
    Interpoleert uurwaarden (gegeven op hele uren, feitelijk H:30) naar kwartierwaarden.
    Voor elk uurblok worden 4 kwartierwaarden berekend, zodanig dat het gemiddelde
    exact overeenkomt met de uurwaarde.

    Parameters
    ----------
    df: pd.DataFrame
        DataFrame met kolommen:
        - "tijd": datetime (op hele uren, bv. 09:00 betekent waarde voor 09:30)
        - field: float/int, uurwaarden
    field: str, name of the column
    quantity: bool, is it a quantity

    Returns
    -------
    pd.DataFrame
        DataFrame met kwartierwaarden in kolommen ["tijd", field]
    """

    result = []

    for i in range(len(df)):
        t_curr = df.loc[i, "tijd"]
        v_curr = df.loc[i, field]

        if i == 0:
            # eerste uurblok (lineair richting volgende)
            v_next = df.loc[i + 1, field]
            """
            q0 = v_curr
            q1 = (2 * v_curr + v_next) / 3
            q2 = (v_curr + 2 * v_next) / 3
            q3 = v_next
            """
            q0 = v_curr + (v_curr - v_next) * 0.50  # 09:00 dicht bij 09:30
            q1 = v_curr + (v_curr - v_next) * 0.25  # 9:15
            q2 = v_curr  # 09:30 → ongeveer uurwaarde
            q3 = v_curr + (v_next - v_curr) * 0.25  # 09:45 dicht bij 09:30

        elif i == len(df) - 1:
            # laatste uurblok (lineair vanaf vorige)
            v_prev = df.loc[i - 1, field]
            """
            q0 = v_prev
            q1 = (2 * v_prev + v_curr) / 3
            q2 = (v_prev + 2 * v_curr) / 3
            q3 = v_curr
            """
            q0 = v_curr + (v_prev - v_curr) * 0.50  # 09:00 dicht bij 09:30
            q1 = v_curr + (v_prev - v_curr) * 0.25  # 9:15
            q2 = v_curr  # 09:30 → ongeveer uurwaarde
            q3 = v_curr + (v_curr - v_prev) * 0.25  # 09:45 dicht bij 09:30
        else:
            # tussenliggende blokken met jouw formule
            v_prev = df.loc[i - 1, field]
            v_next = df.loc[i + 1, field]

            """
            q0 = v_prev + (v_curr - v_prev) * 0.75
            q1 = v_curr
            q2 = v_next + (v_curr - v_next) * 0.75
            q3 = (q0 + q1 + q2) / 3  # voorlopig
            """
            q0 = v_prev + (v_curr - v_prev) * 0.50  # 09:00 dicht bij 09:30
            q1 = v_prev + (v_curr - v_prev) * 0.75  # 9:15
            q2 = v_curr  # 09:30 → ongeveer uurwaarde
            q3 = v_next + (v_curr - v_next) * 0.75  # 09:45 dicht bij 09:30

        quarters = np.array([q0, q1, q2, q3], dtype=float)

        # correctie zodat gemiddelde exact gelijk is aan uurwaarde
        correction = v_curr - quarters.mean()
        quarters += correction
        if quantity:
            quarters = quarters / 4

        for k in range(4):
            result.append(
                {
                    "tijd": t_curr + datetime.timedelta(minutes=15 * k),
                    field: float(quarters[k]),
                }
            )
    result_df = pd.DataFrame(result)
    result_df.index = pd.to_datetime(result_df["tijd"])
    return result_df


def tst_interpolate_df():
    import pandas as pd
    import datetime

    data = pd.DataFrame(
        {
            "tijd": [
                datetime.datetime(2023, 1, 1, 9, 0),
                datetime.datetime(2023, 1, 1, 10, 0),
                datetime.datetime(2023, 1, 1, 11, 0),
                datetime.datetime(2023, 1, 1, 12, 0),
                datetime.datetime(2023, 1, 1, 13, 0),
            ],
            "value": [15, 17, 14, 18, 20],
        }
    )

    quarters = interpolate(data, "value", False)
    print(quarters)


# tst_interpolate_df()
# tst_interpolate()
# interpolate_prognose_data()
