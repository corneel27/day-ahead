"""
Bonus op teruglevering binnen een dagelijks tijdvenster,
bijv. de Zonneplan Zonnebonus: 10% over (marktprijs + 0,02) van zonsopkomst tot zonsondergang.
"""

import bisect
import datetime
import math

import ephem

from dao.prog.config.models.pricing import ProductionBonusConfig

# KNMI De Bilt, referentie voor zonsopkomst/-ondergang in Nederland
NL_CENTER = (52.101, 5.177)


class ProductionBonus:
    def __init__(
        self, config: ProductionBonusConfig, latitude: float, longitude: float
    ):
        self.config = config
        if config.sun_location == "nl_center":
            latitude, longitude = NL_CENTER
        self.latitude = latitude
        self.longitude = longitude
        self._days = sorted(config.percentage.keys())
        self._windows: dict[datetime.date, tuple[float, float]] = {}

    def percentage(self, day: datetime.date) -> float:
        """Bonuspercentage op dag; 0 voor de eerste datum."""
        day_str = day.strftime("%Y-%m-%d")
        index = bisect.bisect_right(self._days, day_str)
        if index == 0:
            return 0.0
        return self.config.percentage[self._days[index - 1]]

    def _sun_window(self, day: datetime.date) -> tuple[float, float]:
        observer = ephem.Observer()
        observer.lat = math.radians(self.latitude)
        observer.lon = math.radians(self.longitude)
        # officiele definitie: bovenrand zon op de horizon, refractie 34'
        observer.pressure = 0
        observer.horizon = "-0:34"
        local_noon = datetime.datetime(day.year, day.month, day.day, 12).timestamp()
        observer.date = ephem.Date(
            datetime.datetime.fromtimestamp(local_noon, datetime.timezone.utc).replace(
                tzinfo=None
            )
        )
        sun = ephem.Sun()
        try:
            rising = observer.previous_rising(sun).datetime()
            setting = observer.next_setting(sun).datetime()
        except ephem.AlwaysUpError:
            return local_noon - 12 * 3600, local_noon + 12 * 3600
        except ephem.NeverUpError:
            return local_noon, local_noon
        return (
            rising.replace(tzinfo=datetime.timezone.utc).timestamp(),
            setting.replace(tzinfo=datetime.timezone.utc).timestamp(),
        )

    def _fixed_window(self, day: datetime.date) -> tuple[float, float]:
        def local_ts(hhmm: str) -> float:
            t = datetime.datetime.strptime(hhmm, "%H:%M")
            return datetime.datetime(
                day.year, day.month, day.day, t.hour, t.minute
            ).timestamp()

        return local_ts(self.config.start), local_ts(self.config.end)

    def window(self, day: datetime.date) -> tuple[float, float]:
        """Begin en eind (unix timestamps) van het bonusvenster op lokale dag."""
        if day not in self._windows:
            if self.config.window == "sun":
                self._windows[day] = self._sun_window(day)
            else:
                self._windows[day] = self._fixed_window(day)
        return self._windows[day]

    def fraction(self, start_ts: float, duration_s: float) -> float:
        """Deel (0..1) van het interval dat binnen het bonusvenster valt."""
        if duration_s <= 0:
            return 0.0
        end_ts = start_ts + duration_s
        day = datetime.datetime.fromtimestamp(start_ts).date()
        overlap = 0.0
        # een interval kan over middernacht lopen
        for d in (day, day + datetime.timedelta(days=1)):
            w_start, w_end = self.window(d)
            overlap += max(0.0, min(end_ts, w_end) - max(start_ts, w_start))
        return min(1.0, overlap / duration_s)

    def bonus(
        self,
        start_ts: float,
        duration_s: float,
        market_price: float,
        supplier_cost: float,
    ) -> float:
        """Bonus in euro/kWh (excl. belastingen en btw) voor een interval."""
        day = datetime.datetime.fromtimestamp(start_ts).date()
        percentage = self.percentage(day)
        if percentage == 0:
            return 0.0
        base = market_price
        if self.config.include_supplier_cost:
            base += supplier_cost
        if self.config.only_positive_price and base <= 0:
            return 0.0
        return base * percentage / 100 * self.fraction(start_ts, duration_s)

    def eligible_kwh(
        self,
        start_ts: float,
        duration_s: float,
        kwh: float,
        market_price: float,
        supplier_cost: float,
    ) -> float:
        """Deel van de teruglevering (kWh) in een interval dat bonus krijgt."""
        if kwh <= 0:
            return 0.0
        if self.bonus(start_ts, duration_s, market_price, supplier_cost) <= 0:
            return 0.0
        return kwh * self.fraction(start_ts, duration_s)


def interval_durations(timestamps: list[float], max_s: float = 3600) -> list[float]:
    """Duur (s) van elk interval, afgeleid uit de afstand tot het volgende tijdstip."""
    result = []
    for i, ts in enumerate(timestamps):
        if i + 1 < len(timestamps):
            duration = timestamps[i + 1] - ts
        elif i > 0:
            duration = ts - timestamps[i - 1]
        else:
            duration = max_s
        result.append(min(duration, max_s))
    return result


def split_quarters(
    start_ts: float, duration_s: float, kwh: float, step_s: float = 900
) -> list[tuple[float, float, float]]:
    """
    Verdeelt een interval gelijkmatig over kwartieren
    :return: list van (begin, duur, kWh); een interval van een kwartier of korter blijft heel
    """
    count = max(1, round(duration_s / step_s))
    if count == 1:
        return [(start_ts, duration_s, kwh)]
    part = duration_s / count
    return [(start_ts + i * part, part, kwh / count) for i in range(count)]


class AnnualCapUsage:
    """Cumulatieve teruglevering met bonus binnen een kalenderjaar."""

    def __init__(self, end_timestamps: list[float], eligible_kwh: list[float]):
        self._ends = end_timestamps
        self._cumulative = []
        total = 0.0
        for kwh in eligible_kwh:
            total += kwh
            self._cumulative.append(total)

    def used_before(self, ts: float) -> float:
        """Verbruikte bonus-kWh van intervallen die op of voor ts eindigen."""
        index = bisect.bisect_right(self._ends, ts)
        if index == 0:
            return 0.0
        return self._cumulative[index - 1]
