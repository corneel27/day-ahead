"""Capture -> replay round trip for da_debug.

A real ``calc_optimum()`` runs under ``RecordingIO``; the snapshot it writes
is then replayed with ``ReplayIO``. The replay must see the same solar
forecasts and reach the same objective as the recorded run.

The "live" side is a synthetic scenario snapshot served by ``ReplayIO``
(prices, meteo, HA states), plus a fake ML solar predictor whose output
depends on the window it is asked for. With a horizon extension,
``calc_optimum()`` asks for every solar device twice (fixed part, predicted
part), so a recorder that keeps one frame per device fails here.

The round trip needs the solver: skipped unless ``DAO_RUN_SCENARIOS`` is set
and ``mip`` is importable, like the scenario solve tests.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[3]
_PROG_DIR = _REPO_ROOT / "dao" / "prog"
for _p in (str(_REPO_ROOT), str(_PROG_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _solver_ready() -> bool:
    if os.environ.get("DAO_RUN_SCENARIOS", "").strip() in ("", "0", "false"):
        return False
    try:
        import mip  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


_SOLVER = pytest.mark.skipif(
    not _solver_ready(),
    reason="set DAO_RUN_SCENARIOS=1 (and install mip) to run the capture/replay round trip",
)

SCENARIO_ID = "extension-96h-predicted-dip"


# Nep-ML-voorspelling: uurwaarden die van het gevraagde venster en het paneel afhangen.
def _fake_predict_solar_device(instance, solar_option, start, end):
    """Hourly frame shaped like SolarPredictor.predict_solar_device's result
    (tz-aware ``date_time``, ``prediction`` in kWh). The value depends on the
    absolute hour and the device, so a frame served for the wrong window or
    the wrong device gives different numbers."""
    import pandas as pd

    hours = pd.date_range(
        pd.Timestamp(start).floor("h"), pd.Timestamp(end), freq="h", inclusive="left"
    )
    offset = (sum(map(ord, solar_option.name)) % 7) / 10
    # Afgerond op 3 decimalen: cos(±pi/2) geeft 6e-17 in plaats van 0, en zo'n
    # bijna-nul opwekking maakt het model voor CBC infeasible.
    values = [
        round(0.2 * max(0.0, math.cos((h.hour - 13) / 6 * math.pi / 2)) * (1.0 + offset + h.day / 10), 3)
        for h in hours
    ]
    return pd.DataFrame(
        {
            "date_time": hours.tz_localize("Europe/Amsterdam"),
            "prediction": pd.Series(values, dtype="float32"),
        }
    )


# Laat de "live" kant de meteodata via DBmanagerObj.get_prognose_data leveren, zoals een echt systeem.
def _install_live_db(live) -> None:
    """ReplayIO serves meteo data through its own _FakeDbManager, which is
    no DBmanagerObj, so a RecordingIO on top would never see those calls.
    On a real system db_da is a DBmanagerObj; this gives the live side one,
    whose get_prognose_data serves the scenario's meteo calls."""
    import dao.prog.da_base as da_base_module
    from dao.lib.db_manager import DBmanagerObj
    from dao.prog import da_debug

    fake = da_debug._FakeDbManager(live._prog_calls, "live")

    class _LiveDb(DBmanagerObj):
        def __init__(self):  # geen echte databaseverbinding
            pass

        def log_pool_status(self):
            return None

        def __getattr__(self, name):
            return getattr(fake, name)

    def _get_prognose_data(instance, start=None, end=None, interval="1hour"):
        return fake.get_prognose_data(start=start, end=end, interval=interval)

    db = _LiveDb()
    live._patches.set(DBmanagerObj, "get_prognose_data", _get_prognose_data)
    live._patches.set(da_base_module, "make_db_da", lambda *a, **k: db)
    live._patches.set(da_base_module, "make_db_ha", lambda *a, **k: db)


# Legt elke uitkomst van calc_solar_predictions vast, zodat opname en replay te vergelijken zijn.
def _spy_calc_solar_predictions(original, seen: list):
    def spy(self, solar_option, vanaf, tot, interval=None, _ml_prediction=None):
        result = original(
            self, solar_option, vanaf, tot, interval=interval, _ml_prediction=_ml_prediction
        )
        seen.append((solar_option.name, interval, result["prediction"].astype(float).round(6).tolist()))
        return result

    return spy


def _scenario_snapshot():
    from dao.prog.scenarios import load
    from dao.prog.scenarios.build_snapshot import build_config, build_snapshot

    (scenario,) = load([SCENARIO_ID])
    config = build_config(scenario)
    # base_config zet ml_prediction uit voor de scenario's; hier juist aan.
    for sol in config.get("solar", []):
        sol["ml_prediction"] = True
    for bat in config.get("battery", []):
        for sol in bat.get("solar", []):
            sol["ml_prediction"] = True
    return scenario, build_snapshot(scenario, config=config)


def test_payload_keeps_timezone():
    """to_json writes tz-aware times as UTC; the stored zone must come back,
    or the ML solar forecast shifts by the UTC offset on replay."""
    import pandas as pd

    from dao.prog import da_debug

    frame = pd.DataFrame(
        {
            "date_time": pd.date_range("2026-10-24 13:00", periods=3, freq="h", tz="Europe/Amsterdam"),
            "tijd": pd.date_range("2026-10-24 13:00", periods=3, freq="h"),
            "prediction": pd.Series([0.1, 0.2, 0.3], dtype="float32"),
        }
    )
    restored = da_debug._dataframe_from_payload(da_debug._dataframe_to_payload(frame))
    assert str(restored["date_time"].dt.tz) == "Europe/Amsterdam"
    assert restored["date_time"].tolist() == frame["date_time"].tolist()
    assert restored["tijd"].dt.tz is None
    assert restored["tijd"].tolist() == frame["tijd"].tolist()


@_SOLVER
def test_capture_then_replay_reproduces_the_run(tmp_path):
    from dao.prog import da_debug

    da_debug._ensure_day_ahead_importable()
    from dao.prog.da_base import DaBase
    from dao.prog.day_ahead import DaCalc
    from dao.prog.scenarios.vocabulary import parse_start
    from dao.prog.solar_predictor import SolarPredictor

    scenario, live_snapshot = _scenario_snapshot()
    options = tmp_path / "options.json"
    options.write_text("{}")
    original_calc_solar = DaBase.calc_solar_predictions

    # 1. "Live" run, recorded.
    seen_live: list = []
    with da_debug.ReplayIO(live_snapshot, solver_threads=1) as live:
        _install_live_db(live)
        live._patches.set(SolarPredictor, "predict_solar_device", _fake_predict_solar_device)
        live._patches.set(
            DaBase, "calc_solar_predictions", _spy_calc_solar_predictions(original_calc_solar, seen_live)
        )
        with da_debug.RecordingIO(out_dir=tmp_path / "snapshots") as rec:
            DaCalc(str(options)).calc_optimum(_start_dt=parse_start(scenario.start))
        live_model = live._model
    assert live_model is not None and live_model.num_solutions > 0, "recorded run did not solve"
    assert rec.snapshot_path is not None and rec.snapshot_path.exists()

    # Drie panelen, elk twee vensters (vast deel en voorspeld deel).
    assert len(seen_live) == 6, seen_live

    # 2. Replay of the recorded snapshot, with nothing patched in by the test
    #    except the spy: every input must come from the snapshot.
    seen_replay: list = []
    with da_debug.ReplayIO(rec.snapshot_path, solver_threads=1) as replay:
        replay._patches.set(
            DaBase, "calc_solar_predictions", _spy_calc_solar_predictions(original_calc_solar, seen_replay)
        )
        DaCalc(str(options)).calc_optimum()
        replay_model = replay._model
    assert replay_model is not None and replay_model.num_solutions > 0, "replay did not solve"

    assert seen_replay == seen_live, "replay served different solar forecasts than the recorded run"
    assert (replay_model.num_cols, replay_model.num_rows) == (live_model.num_cols, live_model.num_rows)
    assert replay_model.objective_value == pytest.approx(live_model.objective_value, abs=1e-6)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
