"""Pin the process timezone to UTC for scenario runs.

``freezegun.freeze_time`` treats its anchor as UTC and makes
``datetime.now()`` return that value naive. ``calc_optimum()`` then does
``int(start_dt.timestamp())`` and ``datetime.fromtimestamp(...)``, which use
the process-local timezone — so on a machine in a DST zone the anchor and
its round-trip disagree by the UTC offset (1-2 h), which shifts
``start_hour`` and corrupts interval alignment (seen in S1: a June scenario
tripped "Er ontbreken kwartierwaarden").

The addon container runs in a fixed timezone; the scenario harness pins UTC
so replays are identical everywhere. Import this module before importing
``day_ahead`` / constructing ``DaCalc``.
"""

from __future__ import annotations

import os
import time

if os.environ.get("TZ") != "UTC":
    os.environ["TZ"] = "UTC"
try:  # tzset is POSIX-only; Windows callers just skip the reset
    time.tzset()
except AttributeError:  # pragma: no cover
    pass
