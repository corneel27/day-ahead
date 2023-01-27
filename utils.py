from dateutil import easter
import datetime

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

def calc_adjustment_heatcurve(price:float, price_avg:float, adjustment_factor, old_adjustment: float) -> float:
    """
    berekent de aanpassing van de stooklijn
    formule: -0,5*(price-price_avg)*10/price_avg
    :param price: de actuele uurprijs
    :param price_avg: de dag gemiddelde prijs
    :adjustment_factor: aanpassingsfactor in K/% bijv 0,4K per 10% = 0.04 K/%
    :old_adjustment: huidige aanpassing
    :return:
    """
    if price_avg == 0:
        adjustment = 0
    else:
        adjustment = round(-adjustment_factor * (price - price_avg) *100/ price_avg, 1)
    # toename en afname maximeren op 0,5K
    if adjustment >= old_adjustment:
        adjustment = min(adjustment, old_adjustment + adjustment_factor*10)
    else:
        adjustment = max(adjustment, old_adjustment - adjustment_factor*10)
    return adjustment
