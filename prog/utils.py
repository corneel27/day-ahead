from dateutil import easter
import datetime
import bisect
import math
import json
import os
import sys
import pandas as pd
from day_ahead import DayAheadOpt
from requests import post


def is_laagtarief(dtime, switch_hour):
    jaar = dtime.year
    datum = datetime.datetime(dtime.year, dtime.month, dtime.day)
    if datum.weekday() >= 5:  # zaterdag en zondag
        return True
    if (dtime.hour < 7) or (dtime.hour >= switch_hour):  # door de week van 7 tot 21/23
        return True
    feestdagen = [datetime.datetime(jaar, 1, 1), datetime.datetime(jaar, 4, 27), datetime.datetime(jaar, 12, 25),
                  datetime.datetime(jaar, 12, 26)]
    pasen = easter.easter(jaar)
    feestdagen.append(pasen + datetime.timedelta(days=1))  # 2e paasdag
    feestdagen.append(pasen + datetime.timedelta(days=39))  # hemelvaart
    feestdagen.append(pasen + datetime.timedelta(days=50))  # 2e pinksterdag

    for day in feestdagen:
        if day == datum:  # dag is een feestdag
            return True
    return False


def calc_adjustment_heatcurve(price: float, price_avg: float, adjustment_factor, old_adjustment: float) -> float:
    """
    Berekent de aanpassing van de stooklijn
    formule: -0,5*(price-price_avg)*10/price_avg
    :param price: de actuele uurprijs
    :param price_avg: de dag gemiddelde prijs
    :param adjustment_factor: aanpassingsfactor in K/% bijv 0,4K per 10% = 0.04 K/%
    :param old_adjustment: huidige aanpassing
    :return: de berekende aanpassing
    """
    if price_avg == 0:
        adjustment = 0
    else:
        adjustment = round(- adjustment_factor * (price - price_avg) * 100 / price_avg, 1)
    # toename en afname maximeren op 10 x adjustment factor
    if adjustment >= old_adjustment:
        adjustment = min(adjustment, old_adjustment + adjustment_factor*10)
    else:
        adjustment = max(adjustment, old_adjustment - adjustment_factor*10)
    return round(adjustment,1)


def get_value_from_dict(dag: str, options: dict) -> float:
    """
    Selecteert uit een dict van datum/value paren de juiste value
    :param dag: string van de dag format yyyy-mm-dd
    :param options: dict van datum/value paren bijv {'2022-01-01': 0.002, '2023-03-01': 0.018}
    :return: de correcte value
    """
    o_list = list(options.keys())
    result = options.get(dag, options[o_list[bisect.bisect_left(o_list, dag) - 1]])
    return result


def get_tibber_data(day_ahead_opt: DayAheadOpt):
    def get_datetime_from_str(s):
        result = datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")  # "2022-09-01T01:00:00.000+02:00"
        return result

    url = day_ahead_opt.tibber_options["api url"]
    headers = {
        "Authorization": "Bearer " + day_ahead_opt.tibber_options["api_token"],
        "content-type": "application/json",
    }
    now_ts = latest_ts = math.ceil(datetime.datetime.now().timestamp() / 3600) * 3600
    arg_dt = None
    if len(sys.argv) > 2:
        arg_s = sys.argv[2]
        try:
            arg_dt = datetime.datetime.strptime(arg_s, "%Y-%m-%d").timestamp()
            latest_ts = arg_dt
        except:
            pass
    if (len(sys.argv) <= 2) or (arg_dt == None):
        for cat in ['cons', 'prod']:
            sql_latest_ts = (
                "SELECT t1.time, from_unixtime(t1.`time`) 'begin', t1.value "
                "FROM `values` t1, `variabel` v1 "
                "WHERE v1.`code` = '"+cat+"' and v1.id = t1.variabel and 1 <> "
                "(SELECT COUNT( *) "
                "FROM `values` t2, `variabel` v2 "
                "WHERE v2.`code` = '"+cat+"' AND v2.id = t2.variabel AND t1.time + 3600 = t2.time);")
            data = day_ahead_opt.db_da.run_select_query(sql_latest_ts)
            if len(data.index) == 0:
                latest = datetime.datetime.strptime(day_ahead_opt.prices_options["last invoice"], "%Y-%m-%d").timestamp()
            else:
                latest = data['time'].values[0]
            latest_ts = min(latest_ts, latest)
    count = math.ceil((now_ts - latest_ts)/3600)
    print("Tibber data present tot en met:", str(datetime.datetime.fromtimestamp(latest_ts)))
    if count < 24:
        print("Er worden geen data opgehaald")
        return
    query = '{ ' \
            '"query": ' \
            ' "{ ' \
            '   viewer { ' \
            '     homes { ' \
            '      production(resolution: HOURLY, last: '+str(count)+') { ' \
            '        nodes { ' \
            '          from ' \
            '          profit ' \
            '          production ' \
            '        } ' \
            '      } ' \
            '    consumption(resolution: HOURLY, last: '+str(count)+') { ' \
            '        nodes { ' \
            '          from ' \
            '          cost ' \
            '          consumption ' \
            '        } ' \
            '      } ' \
            '    } ' \
            '  } ' \
            '}" ' \
        '}'

    # print(query)
    resp = post(url, headers=headers, data=query)
    tibber_dict = json.loads(resp.text)
    if day_ahead_opt.debug:
        print(tibber_dict)
    production_nodes = tibber_dict['data']['viewer']['homes'][0]['production']['nodes']
    consumption_nodes = tibber_dict['data']['viewer']['homes'][0]['consumption']['nodes']
    tibber_df = pd.DataFrame(columns=['time', 'code', 'value'])
    code = "prod"
    for node in production_nodes:
        if not(node["production"] is None):
            time_stamp = str(int(get_datetime_from_str(node['from']).timestamp()))
            value = float(node["production"])
            print(node, time_stamp, value)
            tibber_df.loc[tibber_df.shape[0]] = [time_stamp, code, value]
    code = "cons"
    for node in consumption_nodes:
        if not (node["consumption"] is None):
            time_str = str(int(get_datetime_from_str(node['from']).timestamp()))
            value = float(node["consumption"])
            print(node, time_str, value)
            tibber_df.loc[tibber_df.shape[0]] = [time_str, code, value]
    print(tibber_df)
    day_ahead_opt.db_da.savedata(tibber_df)

'''
def calc_heatpump_usage
    (pl : [], needed : float) ->[]:
    """
    berekent inzet van de wp per uur
    :param pl: een list van de inkoop prijzen
    :param needed:  benodige Wh aan energie
    :return: een list van Wh in de betreffende uren
    """
    U = len(pl) # aantal uur
    pl_min = min(pl)
    sum_cost = 0
    max_low = U * 250
    usage = []
    if max_low >= needed:
        #alleen de goedkopere uren inzetten
    else:
        #alle uren minimum inzetten plus nog wat extra
        for u in range(U):
            sum_cost += pl[u]-pl_min
        extra_energy = needed - max_low
        energy_cost = sum_cost/extra_energy
        for u in range(U):
            usage.append(250+ (pl[u]-pl_min) * energy_cost)
'''

def make_data_path():
    if os.path.lexists("../data"):
        return
    else:
        os.symlink("/addons/test_da/data", "../data")