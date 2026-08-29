"""
Snapshot capture and hermetic replay for ``DaCalc.calc_optimum()``.

See ``dao_debug_replay_ci_architecture_v2.md`` sections 2.1 and 2.2 for the
design this implements. In short: ``calc_optimum()`` crosses several
external-state boundaries (database, Home Assistant REST, the wall clock,
the on-disk config) before and during a solve. This module patches those
boundaries at the class/module level — never touching ``day_ahead.py``
itself beyond the two additive hooks already landed there — so that a run
can either be recorded to a fixture file (``RecordingIO``) or replayed
hermetically from one (``ReplayIO``), with no live Home Assistant and no
database connection required for the latter.

Usage::

    with RecordingIO(out_dir="../data/debug_snapshots") as rec:
        dacalc = DaCalc("../data/options.json")
        dacalc.calc_optimum()
    print(rec.snapshot_path)

    with ReplayIO(rec.snapshot_path):
        dacalc = DaCalc("../data/options.json")  # never touches disk/DB/HA
        dacalc.calc_optimum()

Both classes are context managers that must be entered *before* any
``DaBase``-family object (``DaCalc``, ``Report``) is constructed, since some
of the channels they patch (config, strategy resolution, the HA REST call in
the constructor) are read inside ``DaBase.__init__`` itself.

The input cut-set (§2.1), the snapshot format (§2.2), the variable registry
(§2.3) and ``dump_interval`` (§2.5) are all implemented here. ``RecordingIO``
and ``ReplayIO`` do not depend on the registry or ``dump_interval`` — those
are only wired together by the ``dump`` CLI command, which replays a
snapshot to get a solved model plus its registry and then prints what the
solver knew about one interval.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

try:
    import mip
except ImportError:  # pragma: no cover - mip is a hard project dependency,
    mip = None  # but da_debug.py should still be importable without it.

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SCHEMA_MIN_SUPPORTED = 1

REDACTED_SECRET = "<redacted:SecretStr>"


class SnapshotMiss(RuntimeError):
    """Raised by ReplayIO when a replayed run asks for input the snapshot
    does not have. Never caught internally — a stale or incomplete fixture
    must fail loudly, not silently fall back to live/default behaviour."""


# ---------------------------------------------------------------------------
# Config sanitisation / reconstruction (A0 Q9 / §2.2)
# ---------------------------------------------------------------------------


# Zet een pydantic-configwaarde recursief om naar JSON-veilige data en 
# vervangt elk SecretStr-veld door een redactiemarkering, zodat geheimen nooit in een snapshot belanden.
def _sanitize_config_value(value: Any) -> Any:
    """Recursively convert a pydantic config object graph into a
    JSON-safe structure, dropping every ``SecretStr`` field by type.

    Walks the live object graph (not a ``model_dump()`` result) because
    ``SecretStr`` has no custom pydantic serializer, so a dump would already
    have coerced it to a plain ``str`` and lost the type identity needed to
    tell a secret field apart from an ordinary one.
    """
    from dao.prog.config.models.base import SecretStr
    from pydantic import BaseModel
    from enum import Enum

    if isinstance(value, SecretStr):
        return REDACTED_SECRET
    if isinstance(value, BaseModel):
        return {
            name: _sanitize_config_value(getattr(value, name))
            for name in type(value).model_fields
        }
    if isinstance(value, dict):
        return {str(k): _sanitize_config_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_config_value(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # Best-effort fallback for anything unforeseen; never raise here, a
    # capture failure must not abort the real run.
    return str(value)


# Kleine wrapper rond _sanitize_config_value voor het hele configobject, 
# apart gehouden zodat het aanroeppunt een eigen naam heeft.
def _sanitize_config(config: Any) -> dict:
    return _sanitize_config_value(config)


# Bouwt uit een gesaneerde snapshot-dict weer een gevalideerd pydantic-configobject, 
# nodig om DaBase te kunnen construeren zonder een echte options.json.
def _rehydrate_config(sanitized: dict):
    """Reconstruct a validated pydantic config object from a sanitised
    snapshot dict. ``SecretStr`` fields come back as the literal
    ``REDACTED_SECRET`` marker string, which is harmless: everything that
    reads a secret during replay (only ``hasstoken``/``meteoserver_key`` via
    ``.resolve()`` inside ``DaBase.__init__``) treats an unresolvable value
    as a plain literal and returns it as-is; nothing that needs a *working*
    secret is reachable during a patched replay (price/HP-hours lookups are
    replaced wholesale before they would ever call out with one)."""
    from dao.prog.config.loader import VERSION_MODELS, CURRENT_VERSION

    version = sanitized.get("config_version", CURRENT_VERSION)
    model_class = VERSION_MODELS.get(version, VERSION_MODELS[CURRENT_VERSION])
    return model_class(**sanitized)


# Berekent een sha256-hash over de gesaneerde config, 
# gebruikt om drift tussen een snapshot en de actuele config te detecteren.
def _config_hash(sanitized: dict) -> str:
    blob = json.dumps(sanitized, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


# Weigert de snapshot te schrijven als een echte geheime waarde uit secrets.json 
# letterlijk in de inhoud voorkomt; vangt lekken die de typecontrole mist.
def _assert_no_secret_leak(blob: str, secret_values: list[str]) -> None:
    """Defence in depth alongside type-based exclusion (§2.2): a raw key
    pasted into options.json instead of a ``!secret`` reference never
    becomes a ``SecretStr`` the sanitiser can catch by type, but it *is* a
    value that also lives in secrets.json — this catches that case."""
    leaked = [v for v in secret_values if v and v in blob]
    if leaked:
        raise RuntimeError(
            f"Refusing to write snapshot: {len(leaked)} secret value(s) "
            f"from secrets.json appear in the sanitised snapshot content. "
            f"This should be impossible after type-based SecretStr "
            f"redaction and indicates either a new secret-bearing field "
            f"that isn't SecretStr-typed, or a secret value that also "
            f"happens to appear literally in non-secret config/data."
        )


# ---------------------------------------------------------------------------
# DataFrame <-> JSON payload (§2.2)
# ---------------------------------------------------------------------------


# Serialiseert een DataFrame naar JSON met expliciete dtypes en index-type,
# want standaard-JSON rondt floats af en kent geen datetime-index.
def _dataframe_to_payload(df: pd.DataFrame) -> dict:
    return {
        "data": df.to_json(orient="split", date_format="iso", double_precision=15),
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "index_name": df.index.name,
        "index_is_datetime": isinstance(df.index, pd.DatetimeIndex),
    }


# Herstelt een DataFrame exact uit een payload: dtypes terugzetten 
# en de index alleen naar datetime converteren als die dat origineel ook was.
def _dataframe_from_payload(payload: dict) -> pd.DataFrame:
    df = pd.read_json(io.StringIO(payload["data"]), orient="split")
    for col, dtype in payload.get("dtypes", {}).items():
        if col not in df.columns:
            continue
        try:
            if dtype.startswith("datetime64"):
                df[col] = pd.to_datetime(df[col])
            else:
                df[col] = df[col].astype(dtype)
        except (TypeError, ValueError) as ex:
            logger.warning("Kon dtype %s van kolom %s niet herstellen: %s", dtype, col, ex)
    # Only coerce the index to datetime if it genuinely was one — blindly
    # doing this for every non-empty frame (the original bug) silently
    # corrupted plain integer/RangeIndex frames, e.g. solar_predictions'
    # results, which have no datetime index at all.
    if payload.get("index_is_datetime"):
        df.index = pd.to_datetime(df.index)
    df.index.name = payload.get("index_name")
    return df


# Maakt een stabiele, JSON-veilige sleutel van functieargumenten, 
# nodig om meerdere opnames van dezelfde aanroep (per weekdag, per entity) uit elkaar te houden.
def _call_key(args: tuple, kwargs: dict) -> str:
    """Stable, JSON-safe key for a recorded call, used where a channel can
    legitimately be invoked more than once with different arguments
    (``get_calculated_baseload(weekday)``, ``get_heatpump_run_hours(entity)``)."""
    return json.dumps([list(args), sorted(kwargs.items())], default=str, sort_keys=True)


# ---------------------------------------------------------------------------
# Lightweight stand-ins used only during replay
# ---------------------------------------------------------------------------


class _FakeState:
    """Minimal stand-in for whatever hassapi's ``get_state()`` normally
    returns. Every call site in day_ahead.py/da_base.py only ever reads
    ``.state`` off the result (verified by grep) so nothing else is
    implemented."""

    __slots__ = ("state",)

    # Bewaart alleen de state-string; dat is het enige dat aanroepers van get_state() ooit uitlezen.
    def __init__(self, state: str):
        self.state = state


class _FakeHttpResponse:
    """Stand-in for a ``requests.Response``. Serves two distinct real call
    sites during replay: the raw ``get(hassurl + "api/config")`` in
    ``DaBase.__init__`` (reads only ``.text``), and — discovered by actually
    running a hermetic construction against the real ``hassapi`` package,
    not just reading it — ``hass.Hass.__init__`` itself, via
    ``BaseClient._assert_api_running()``, which does its own independent
    ``requests.get("<hassurl>/")`` health check and reads ``.ok``/``.json()``
    on the result. Supporting all three keeps both call sites served by one
    small stand-in."""

    __slots__ = ("_payload", "text", "ok", "status_code")

    # Bouwt een minimale requests.Response-imitatie met .text/.ok/.status_code, 
    # nodig om zowel da_base.py's eigen HA-aanroep als hassapi's interne verzoek te kunnen bedienen.
    def __init__(self, payload: dict):
        self._payload = payload
        self.text = json.dumps(payload)
        self.ok = True
        self.status_code = 200

    # Geeft de payload terug zoals requests.Response.json() dat zou doen, 
    # want hassapi's interne verwerking roept dit aan.
    def json(self):
        return self._payload


class _FakeDbManager:
    """Stand-in for the ``DBmanagerObj`` singleton ``make_db_da``/
    ``make_db_ha`` normally return. Serves the one channel calc_optimum()
    calls directly (``get_prognose_data``); everything else raises loudly
    rather than silently returning something DB-shaped, since a call
    reaching here that isn't one of the two known methods means the input
    cut-set (§1) is incomplete and a new channel needs a real patch."""

    # Onthoudt de opgeslagen prognosedata en een label voor duidelijke foutmeldingen.
    def __init__(self, prog_data: Optional[pd.DataFrame], label: str):
        self._prog_data = prog_data
        self._label = label

    # Levert de opgeslagen prognosedata terug in plaats van een echte databasequery uit te voeren.
    def get_prognose_data(self, start=None, end=None, interval="1hour"):
        if self._prog_data is None:
            raise SnapshotMiss(
                f"ReplayIO ({self._label}): prog_data not present in snapshot"
            )
        return self._prog_data.copy()

    # Doet niets; bestaat alleen omdat DaBase.__init__ dit aanroept en anders een AttributeError zou geven.
    def log_pool_status(self):
        return None

    # Laat elke niet-nagebouwde databaseaanroep direct hard falen, 
    # zodat een ongedekt kanaal opvalt in plaats van stilzwijgend een verkeerd resultaat te geven.
    def __getattr__(self, name):
        raise SnapshotMiss(
            f"ReplayIO ({self._label}): db_da/db_ha.{name}() was called, but "
            f"ReplayIO only serves get_prognose_data()/log_pool_status(). "
            f"This means a channel outside the documented input cut-set "
            f"(architecture doc §1) was reached during replay."
        )


class _FakeLoader:
    """Stand-in for ``ConfigurationLoader`` used only to satisfy
    ``self.loader.secrets`` during replay. Always empty: no real secrets are
    ever needed for a replayed run (see ``_rehydrate_config``)."""

    secrets: dict = {}


# ---------------------------------------------------------------------------
# Patch bookkeeping shared by RecordingIO and ReplayIO
# ---------------------------------------------------------------------------


class _PatchList:
    """Tracks class/module attribute overrides so they can be reverted
    exactly, including the case where the attribute didn't exist directly on
    the target before (e.g. ``DaBase.get_state`` is inherited from
    ``hass.Hass``, not defined on ``DaBase`` itself) — restoring must
    ``delattr`` in that case, not set back a value that was never really
    there, or the shadow would survive patch removal."""

    # Start met een lege lijst van toegepaste patches.
    def __init__(self):
        self._entries: list[tuple[Any, str, bool, Any]] = []

    # Vervangt een attribuut en onthoudt de oorspronkelijke waarde (of het ontbreken ervan), 
    # nodig om later exact te kunnen herstellen.
    def set(self, target: Any, name: str, new_value: Any) -> None:
        had_attr = name in vars(target)
        old_value = vars(target).get(name)
        self._entries.append((target, name, had_attr, old_value))
        setattr(target, name, new_value)

    # Zet alle patches in omgekeerde volgorde terug, inclusief delattr voor attributen die er origineel niet waren, 
    # zoals een geërfde methode.
    def restore(self) -> None:
        for target, name, had_attr, old_value in reversed(self._entries):
            try:
                if had_attr:
                    setattr(target, name, old_value)
                else:
                    delattr(target, name)
            except AttributeError:
                logger.warning("Kon patch op %s.%s niet ongedaan maken", target, name)
        self._entries.clear()


# Importeert alle te patchen klassen via hetzelfde dotted pad als day_ahead.py zelf, 
# anders ontstaat een tweede, ongepatchte kopie van de module.
def _import_targets():
    """All patch targets, imported via the exact same dotted path
    day_ahead.py itself uses. This matters: importing e.g. ``da_report``
    (bare) instead of ``dao.prog.da_report`` would create a *second* module
    object under a different ``sys.modules`` key, with its own distinct
    ``Report`` class — patching that copy would silently do nothing to the
    class day_ahead.py actually constructs (A0 Q2)."""
    from dao.prog.da_base import DaBase
    from dao.prog.da_report import Report
    from dao.lib.db_manager import DBmanagerObj
    from dao.prog.solar_predictor import SolarPredictor
    import dao.prog.da_base as da_base_module

    return DaBase, Report, DBmanagerObj, SolarPredictor, da_base_module


# ---------------------------------------------------------------------------
# Write-primitive no-ops, shared by ReplayIO (always) and RecordingIO's
# opt-in debug mode (§ "capture --debug"). Suppressing at these primitives
# rather than chasing call sites is the same principle used for every read
# channel above: the boundary is the stable thing, the call sites are not.
# ---------------------------------------------------------------------------


# Bouwt een set_value-vervanger die niets doet, gebruikt om HA-writes te onderdrukken tijdens replay en debug-capture.
def _make_noop_set_value(label: str):
    # Logt de onderdrukte write en geeft None terug in plaats van echt naar HA te schrijven.
    def _noop_set_value(instance, entity_id, value):
        logger.debug("%s: onderdrukt write set_value(%s, %s)", label, entity_id, value)
        return None

    return _noop_set_value


# Zelfde principe als _make_noop_set_value, maar voor call_service.
def _make_noop_call_service(label: str):
    # Onderdrukt een service-aanroep naar HA.
    def _noop_call_service(instance, *args, **kwargs):
        logger.debug("%s: onderdrukt write call_service%s %s", label, args, kwargs)
        return None

    return _noop_call_service


# Onderdrukt het wegschrijven van de PNG-afbeelding die day_ahead.py ongeacht debug-modus altijd maakt.
def _make_noop_savefig(label: str):
    # Doet niets in plaats van een bestand op schijf te zetten.
    def _noop_savefig(*args, **kwargs):
        logger.debug("%s: onderdrukt write plt.savefig%s", label, args)
        return None

    return _noop_savefig


# ---------------------------------------------------------------------------
# Solved-model capture, shared by RecordingIO (always) and ReplayIO (so a
# replay produces its own *.result.json too — otherwise there is nothing to
# `diff` a replay's objective/gap/status against, live or from a capture).
# ---------------------------------------------------------------------------


# Omwikkelt day_ahead.py's fd-omleiding zodat de CBC-solverlog altijd wordt vastgelegd, 
# ook als self.debug uit staat.
def _install_cbc_log_capture(patches: "_PatchList", day_ahead_module, target) -> None:
    """Wraps day_ahead.py's fd-redirecting ``_capture_native_stdout()`` so
    the CBC solve text lands in ``target._cbc_log_chunks`` unconditionally —
    day_ahead.py only *logs* it when ``self.debug or log_level <= DEBUG``,
    but the text itself is always produced regardless. Preserves the real
    redirection exactly; ``native`` is read only after the real
    implementation's own ``finally`` has already populated it."""
    import contextlib

    original = day_ahead_module._capture_native_stdout

    @contextlib.contextmanager
    # Roept de echte fd-omleiding aan en leest het logresultaat pas uit nadat 
    # de originele implementatie het heeft gevuld.
    def _wrapped_capture_native_stdout():
        with original() as native:
            yield native
        target._cbc_log_chunks.append(native.get("cbc_log", ""))

    patches.set(day_ahead_module, "_capture_native_stdout", _wrapped_capture_native_stdout)


# Onthoudt een referentie naar het opgeloste mip.Model na elke optimize()-aanroep, want buiten calc_optimum() is dat model anders nergens meer te zien.
def _install_model_capture(patches: "_PatchList", target) -> None:
    """Records a reference to the ``mip.Model`` instance after each
    ``optimize()`` call, so objective/status/gap are readable afterward —
    without this, nothing outside ``calc_optimum()`` can see the solved
    model at all, since it's a local variable there."""
    if mip is None:
        return
    original_optimize = mip.Model.optimize

    # Voert de echte solve uit en bewaart daarna het modelobject.
    def _wrapped_optimize(model_self, *args, **kwargs):
        status = original_optimize(model_self, *args, **kwargs)
        target._model = model_self
        return status

    patches.set(mip.Model, "optimize", _wrapped_optimize)


# Zet een opgelost model om naar een result-dict, gedeeld door RecordingIO en ReplayIO zodat beide dezelfde vorm opleveren om te diffen.
def _build_result_dict(model, cbc_log_chunks: list[str], extra_meta: dict) -> Optional[dict]:
    if model is None:
        return None
    try:
        return {
            "meta": {
                "dao_version": _dao_version(),
                "solver": getattr(model, "solver_name", None),
                "mip_version": getattr(mip, "__version__", None) if mip else None,
                **extra_meta,
            },
            "objective_value": model.objective_value,
            "objective_bound": model.objective_bound,
            "status": getattr(model.status, "name", str(model.status)),
            "num_solutions": model.num_solutions,
            "num_cols": model.num_cols,
            "num_rows": model.num_rows,
            "gap": model.gap,
            "cbc_log": "\n".join(cbc_log_chunks) if cbc_log_chunks else None,
            "note": (
                "Per-interval dispatch and SoC trajectory are not captured "
                "in this result file — objective/status/gap only. Use the "
                "`dump` CLI command (architecture doc §2.5) against the "
                "snapshot to see what a solved model knew about a specific "
                "interval; that needs a live re-solve via ReplayIO and "
                "isn't something a static result file can hold."
            ),
        }
    except Exception:
        logger.exception("Kon solve-resultaat niet opbouwen")
        return None


# ---------------------------------------------------------------------------
# RecordingIO
# ---------------------------------------------------------------------------


class RecordingIO:
    """Passthrough + record. Every patched call still goes to the real
    implementation and returns the real result unmodified — recording must
    never change what a run does or computes (only ``ReplayIO`` suppresses
    or fakes anything) — *unless* ``debug=True`` is passed, which is an
    explicit, opt-in departure from that rule for exactly one purpose: so
    capturing repeatedly while iterating on this tooling doesn't keep
    pushing real settings to a real battery/EV/HA setup. It mirrors
    day_ahead.py's own `calc_optimum_met_debug()` (``self.debug = True``
    before solving, which gates most writes) plus, on top of that, the
    same write-primitive no-ops ``ReplayIO`` always applies — because
    `self.debug` alone does *not* gate everything: `self.notify(...)` and
    one `set_value(entity_avg_temp, ...)` call are unconditional regardless
    of the flag (architecture doc §1.2). Reads still happen for real and
    are still captured; only the write side is suppressed.

    ``png`` is a separate switch, independent of ``debug``: day_ahead.py
    writes a chart PNG unconditionally regardless of ``self.debug``, and
    it's a plain local file (no HA/DB involved), so whether to write it
    isn't tied to whether writes elsewhere are suppressed. Defaults to
    ``False`` — off by default, since most capture runs don't need one and
    it's one more file per run — pass ``png=True`` to keep it.

    On exit, writes a snapshot fixture capturing everything read,
    best-effort: a capture failure is logged and swallowed, never allowed
    to turn a successful production run into a failed one."""

    # Zet alle capture-buffers en instellingen klaar vóórdat er iets gepatcht wordt.
    def __init__(
        self,
        out_dir: str | Path = "../data/debug_snapshots",
        *,
        label: str = None,
        debug: bool = False,
        png: bool = False,
    ):
        self.out_dir = Path(out_dir)
        self.label = label
        self._debug = debug
        self._png = png
        self._patches = _PatchList()
        self._primary = None  # first DaBase-family instance constructed
        self._price_data: Optional[pd.DataFrame] = None
        self._price_data_args: Optional[dict] = None
        self._prog_data: Optional[pd.DataFrame] = None
        self._ha_states: dict[str, str] = {}
        self._baseload: dict[str, list] = {}
        self._heatpump_run_hours: dict[str, float] = {}
        self._solar_predictions: dict[str, pd.DataFrame] = {}
        self._captured_at = dt.datetime.now()
        self._model = None  # last mip.Model.optimize() was called on
        self._cbc_log_chunks: list[str] = []
        self.snapshot_path: Optional[Path] = None
        self.result_path: Optional[Path] = None

    # -- context manager -----------------------------------------------

    # Installeert de patches bij het binnengaan van de with-blok.
    def __enter__(self) -> "RecordingIO":
        self._install_patches()
        return self

    # Schrijft de snapshot (best effort) en herstelt daarna altijd de patches, ook als het schrijven zelf mislukt.
    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self._write_snapshot(exc)
        except Exception:
            logger.exception(
                "Snapshot capture mislukt; de berekening zelf is hierdoor niet beïnvloed"
            )
        finally:
            self._patches.restore()
        return False  # never suppress the real run's own exception

    # -- patch installation ----------------------------------------------

    # Zet alle class- en module-patches voor deze opnamesessie neer; dekt samen alle kanalen uit sectie 1 van het ontwerp.
    def _install_patches(self) -> None:
        DaBase, Report, DBmanagerObj, SolarPredictor, _da_base_module = _import_targets()

        original_init = DaBase.__init__

        # Onthoudt de eerst geconstrueerde DaBase-instantie en zet, alleen bij debug-capture, self.debug en de write-onderdrukking aan.
        def _wrapped_init(instance, *args, **kwargs):
            original_init(instance, *args, **kwargs)
            if instance.config is not None:
                if self._debug:
                    instance.debug = True
                if self._primary is None:
                    self._primary = instance

        self._patches.set(DaBase, "__init__", _wrapped_init)

        if self._debug:
            label = f"RecordingIO(debug, {self.out_dir})"
            self._patches.set(DaBase, "set_value", _make_noop_set_value(label))
            self._patches.set(DaBase, "call_service", _make_noop_call_service(label))

        # Independent of --debug: day_ahead.py writes a PNG chart
        # unconditionally, regardless of self.debug. Off by default here —
        # a capture/replay session usually doesn't need one and it's one
        # more file cluttering ../data/images per run — but it's a plain
        # local file write with no HA/DB implications, so turning it on
        # doesn't need debug mode too.
        if not self._png:
            import matplotlib.pyplot as plt

            self._patches.set(
                plt, "savefig", _make_noop_savefig(f"RecordingIO({self.out_dir})")
            )

        original_get_state = DaBase.get_state

        # Roept de echte get_state aan en legt de teruggegeven state vast onder de entity-id.
        def _wrapped_get_state(instance, entity_id, *args, **kwargs):
            result = original_get_state(instance, entity_id, *args, **kwargs)
            try:
                self._ha_states[entity_id] = result.state
            except AttributeError:
                pass
            return result

        self._patches.set(DaBase, "get_state", _wrapped_get_state)

        original_baseload = DaBase.get_calculated_baseload

        # Roept de echte baseload-opzoeking aan en onthoudt het resultaat per weekdag.
        def _wrapped_baseload(instance, weekday, *args, **kwargs):
            result = original_baseload(weekday, *args, **kwargs)
            self._baseload[str(int(weekday))] = result
            return result

        self._patches.set(DaBase, "get_calculated_baseload", _wrapped_baseload)

        original_get_price_data = Report.get_price_data

        # Roept Report.get_price_data echt aan en bewaart het teruggegeven DataFrame.
        def _wrapped_get_price_data(instance, start, end=None, interval="1hour"):
            result = original_get_price_data(instance, start, end=end, interval=interval)
            self._price_data = result
            self._price_data_args = {
                "start": str(start),
                "end": str(end),
                "interval": interval,
            }
            return result

        self._patches.set(Report, "get_price_data", _wrapped_get_price_data)

        original_hp_hours = Report.get_heatpump_run_hours

        # Roept get_heatpump_run_hours echt aan en onthoudt het resultaat per argumentcombinatie.
        def _wrapped_hp_hours(instance, *args, **kwargs):
            result = original_hp_hours(instance, *args, **kwargs)
            self._heatpump_run_hours[_call_key(args, kwargs)] = result
            return result

        self._patches.set(Report, "get_heatpump_run_hours", _wrapped_hp_hours)

        original_get_prognose_data = DBmanagerObj.get_prognose_data

        # Roept de echte prognosedata-query aan en bewaart het resultaat.
        def _wrapped_get_prognose_data(instance, start=None, end=None, interval="1hour"):
            result = original_get_prognose_data(instance, start=start, end=end, interval=interval)
            self._prog_data = result
            return result

        self._patches.set(DBmanagerObj, "get_prognose_data", _wrapped_get_prognose_data)

        # Not in the original input cut-set (architecture doc §1): found by
        # actually running a real config with a solar device configured for
        # ML prediction. calc_optimum() -> DaBase.calc_solar_predictions()
        # -> SolarPredictor.predict_solar_device() does its own DB reads
        # (get_time_border_record, get_column_data) that DBmanagerObj's
        # patch above never sees, because those calls only happen inside
        # this method — patched wholesale, same principle as
        # Report.get_price_data, rather than trying to fake the two
        # DB primitives generically.
        original_predict_solar_device = SolarPredictor.predict_solar_device

        # Roept de echte ML-zonnevoorspelling aan en bewaart het resultaat per paneelnaam, niet per tijdvenster, want dat laatste kan meer drift geven dan bedoeld.
        def _wrapped_predict_solar_device(instance, solar_option, start, end):
            result = original_predict_solar_device(instance, solar_option, start, end)
            # Keyed by device name only, not (start, end): those two are
            # themselves derived from calc_optimum()'s own internal
            # dt.datetime.now() call, which fires strictly later than (and
            # therefore can drift from) RecordingIO's own captured_at
            # timestamp — a live run's DB/HA setup alone can take long
            # enough to cross an interval boundary between the two. There
            # is only ever one legitimate (start, end) window per device
            # per snapshot anyway, so the name alone is both sufficient
            # and immune to that drift. Found by an actual capture/replay
            # round trip against a live config, not by reasoning about it.
            key = _call_key((getattr(solar_option, "name", None),), {})
            self._solar_predictions[key] = result
            return result

        self._patches.set(SolarPredictor, "predict_solar_device", _wrapped_predict_solar_device)

        # Re-anchor _captured_at to the moment calc_optimum() is actually
        # invoked, not construction time. The __init__ default (set before
        # DaCalc()'s own real DB/HA setup even starts) is exactly the gap
        # that produced the solar_predictions key drift above — the more
        # of that setup elapses before the timestamp is taken, the further
        # meta.captured_at (and hence the frozen replay clock) drifts from
        # what calc_optimum()'s own internal `dt.datetime.now()` actually
        # returns a few lines into the real method. This patch narrows that
        # gap to essentially the wrapper call overhead.
        try:
            from dao.prog.day_ahead import DaCalc
            import dao.prog.day_ahead as day_ahead_module

            original_calc_optimum = DaCalc.calc_optimum

            # Zet captured_at pas op het moment dat calc_optimum() echt start in plaats van bij constructie, om klokdrift tussen opname en replay te beperken.
            def _wrapped_calc_optimum(instance, *args, **kwargs):
                self._captured_at = dt.datetime.now()
                return original_calc_optimum(instance, *args, **kwargs)

            self._patches.set(DaCalc, "calc_optimum", _wrapped_calc_optimum)
            _install_cbc_log_capture(self._patches, day_ahead_module, self)
        except ImportError:
            logger.warning(
                "RecordingIO: kon day_ahead niet importeren; captured_at "
                "blijft op het constructie-tijdstip staan en het CBC-log "
                "wordt niet vastgelegd"
            )

        _install_model_capture(self._patches, self)

    # -- snapshot writing --------------------------------------------------

    # Bouwt en schrijft het snapshot-bestand met alle vastgelegde kanalen, inclusief de geheimencontrole vlak vóór het schrijven.
    def _write_snapshot(self, exc: Optional[BaseException]) -> None:
        if self._primary is None:
            logger.warning(
                "RecordingIO: geen DaBase-instantie geconstrueerd binnen de "
                "context; er is niets om vast te leggen"
            )
            return

        sanitized_config = _sanitize_config(self._primary.config)
        secret_values = list(
            (getattr(self._primary, "loader", None) or _FakeLoader()).secrets.values()
        )

        meta = {
            "schema_version": SCHEMA_VERSION,
            "schema_min_supported": SCHEMA_MIN_SUPPORTED,
            "captured_at": self._captured_at.isoformat(),
            "interval": getattr(self._primary, "interval", None),
            "solver_threads": getattr(self._primary, "_solver_threads", -1),
            "strategy": getattr(self._primary, "strategy", None),
            "dao_version": _dao_version(),
            "git_sha": _git_sha(),
            "mip_version": getattr(mip, "__version__", None) if mip else None,
            "python_version": sys.version.split()[0],
            "config_hash": _config_hash(sanitized_config),
            "file_name": getattr(self._primary, "file_name", None),
            "exception": f"{type(exc).__name__}: {exc}" if exc is not None else None,
        }

        ha_context = None
        if getattr(self._primary, "ha_context", None) is not None:
            hc = self._primary.ha_context
            ha_context = {
                "latitude": hc.latitude,
                "longitude": hc.longitude,
                "time_zone": hc.time_zone,
                "country": hc.country,
            }

        snapshot = {
            "meta": meta,
            "ha_context": ha_context,
            "price_data": _dataframe_to_payload(self._price_data)
            if self._price_data is not None
            else None,
            "price_data_args": self._price_data_args,
            "prog_data": _dataframe_to_payload(self._prog_data)
            if self._prog_data is not None
            else None,
            "ha_states": self._ha_states,
            "baseload": self._baseload,
            "heatpump_run_hours": self._heatpump_run_hours,
            "solar_predictions": {
                key: _dataframe_to_payload(df) for key, df in self._solar_predictions.items()
            },
            "config": sanitized_config,
        }

        blob = json.dumps(snapshot, default=str)
        _assert_no_secret_leak(blob, secret_values)

        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = self._captured_at.strftime("%Y-%m-%dT%H%M")
        suffix = f"_{self.label}" if self.label else ""
        base_name = f"calc_{stamp}{suffix}"
        self.snapshot_path = self.out_dir / f"{base_name}.json"
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            f.write(blob)
        logger.info("Debug snapshot geschreven: %s", self.snapshot_path)

        self._write_result(base_name)

    # Schrijft het bijbehorende *.result.json, alleen als er ook daadwerkelijk gesolved is.
    def _write_result(self, base_name: str) -> None:
        result = _build_result_dict(
            self._model,
            self._cbc_log_chunks,
            {"captured_at": self._captured_at.isoformat()},
        )
        if result is None:
            return
        self.result_path = self.out_dir / f"{base_name}.result.json"
        with open(self.result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, default=str)
        logger.info("Debug result geschreven: %s", self.result_path)


# Leest de addon-versie uit dao/prog/version.py, nodig om een snapshot te kunnen koppelen aan de code die hem produceerde.
def _dao_version() -> Optional[str]:
    try:
        from dao.prog.version import __version__

        return __version__
    except Exception:
        return None


# Leest de huidige git-commit als optioneel extra herkenningspunt voor ontwikkelbuilds.
def _git_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).resolve().parent,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# ReplayIO
# ---------------------------------------------------------------------------


class ReplayIO:
    """Serves every input channel from a loaded snapshot and suppresses
    every write primitive, so a ``DaCalc(...).calc_optimum()`` run inside
    this context needs no Home Assistant and no database connection, and
    writes nothing back to either. Any input not present in the snapshot
    raises ``SnapshotMiss`` naming what was missing, rather than silently
    falling back to a default or to live state. The one exception is the
    chart PNG, gated separately by ``png`` (default ``False``, since it's
    a plain local file with no HA/DB implications) rather than folded into
    the always-on write suppression."""

    # Laadt de snapshot, controleert schemaversie en dao-versie, en zet alle read-only databronnen klaar voor gebruik tijdens replay.
    def __init__(
        self,
        snapshot: str | Path | dict,
        *,
        solver_threads: Optional[int] = None,
        png: bool = False,
    ):
        """``solver_threads=None`` (the default) replays with the same
        thread count the captured run itself used (``meta.solver_threads``,
        normally ``-1`` — all cores, same as any ordinary day_ahead.py run),
        so solve time stays representative of a real run and isn't
        dominated by single-threaded CBC's much slower search. Single-
        threaded CBC is also not just slower: found by comparing an actual
        capture/replay pair, it can genuinely fail to reach the same
        objective within day_ahead.py's fixed `model.max_nodes = 1500` —
        multi-threaded CBC explores far more of the tree per second of
        wall time, so the same node budget buys much less search with one
        thread. That makes forcing threads=1 unconditionally actively
        misleading for "is this still fast / did the answer change"
        checks, which is the common case.

        Pass an explicit ``solver_threads`` value to override — ``1`` for
        bit-for-bit reproducibility (accepting the slower, possibly
        node-capped solve as the price of eliminating multi-threaded CBC's
        branching nondeterminism), or any other count to see how the solve
        behaves at that thread count, e.g. to compare against the captured
        run's own timing."""
        self._solver_threads_override = solver_threads
        self._png = png
        self._source = str(snapshot) if not isinstance(snapshot, dict) else "<dict>"
        if isinstance(snapshot, dict):
            self._snapshot = snapshot
        else:
            with open(snapshot, "r", encoding="utf-8") as f:
                self._snapshot = json.load(f)
        self._patches = _PatchList()
        self._primary = None
        self._reads: set[str] = set()
        self._freeze = None  # freezegun handle, set in _install_patches
        self._model = None  # last mip.Model.optimize() was called on
        self._cbc_log_chunks: list[str] = []

        meta = self._snapshot.get("meta", {})
        self._recorded_solver_threads = meta.get("solver_threads", -1)
        schema_version = meta.get("schema_version", 0)
        if schema_version < SCHEMA_MIN_SUPPORTED:
            raise SnapshotMiss(
                f"ReplayIO: snapshot schema_version {schema_version} is older "
                f"than the minimum supported ({SCHEMA_MIN_SUPPORTED}); "
                f"this fixture predates the current snapshot format."
            )
        snapshot_version = meta.get("dao_version")
        current_version = _dao_version()
        if snapshot_version and current_version and snapshot_version != current_version:
            logger.warning(
                "ReplayIO: snapshot was captured with dao_version %s, "
                "replaying with %s — results may not be comparable",
                snapshot_version,
                current_version,
            )

        self._price_data = (
            _dataframe_from_payload(self._snapshot["price_data"])
            if self._snapshot.get("price_data") is not None
            else None
        )
        self._prog_data = (
            _dataframe_from_payload(self._snapshot["prog_data"])
            if self._snapshot.get("prog_data") is not None
            else None
        )
        self._ha_states: dict[str, str] = self._snapshot.get("ha_states", {})
        self._baseload: dict[str, list] = self._snapshot.get("baseload", {})
        self._heatpump_run_hours: dict[str, float] = self._snapshot.get(
            "heatpump_run_hours", {}
        )
        self._solar_predictions: dict[str, pd.DataFrame] = {
            key: _dataframe_from_payload(payload)
            for key, payload in self._snapshot.get("solar_predictions", {}).items()
        }
        self._ha_context = self._snapshot.get("ha_context")
        self._config_dict = self._snapshot.get("config")

    @property
    # Geeft de entity's terug die tijdens de replay daadwerkelijk zijn opgevraagd, om een ongebruikte override op te kunnen sporen.
    def reads(self) -> set[str]:
        """Entity ids actually read via ``get_state`` during the replayed
        run — lets a caller detect a scenario override nothing consulted
        (architecture doc §8.3)."""
        return set(self._reads)

    @property
    # Geeft de meta-sectie van de snapshot terug.
    def meta(self) -> dict:
        return dict(self._snapshot.get("meta", {}))

    # Zet het opgeloste replaymodel om naar dezelfde vorm als een capture-resultaat, zodat replay-uitkomsten te diffen zijn tegen een capture of een andere replay.
    def build_result(self) -> Optional[dict]:
        """The replayed run's own objective/status/gap/cbc_log, in the same
        shape as a capture's ``*.result.json`` — so it can be compared
        against one with ``diff``, or against another replay run at a
        different thread count. Returns ``None`` if the replay never
        reached ``model.optimize()`` (e.g. it errored out on missing data
        first). Must be called after the ``with`` block exits, or at least
        after ``calc_optimum()`` returns — there's nothing to build before
        that."""
        threads_used = (
            self._recorded_solver_threads
            if self._solver_threads_override is None
            else self._solver_threads_override
        )
        return _build_result_dict(
            self._model,
            self._cbc_log_chunks,
            {
                "replayed_at": dt.datetime.now().isoformat(),
                "source_snapshot": self._source,
                "solver_threads": threads_used,
            },
        )

    # -- context manager -----------------------------------------------

    # Installeert de patches bij het binnengaan van de with-blok.
    def __enter__(self) -> "ReplayIO":
        self._install_patches()
        return self

    # Stopt de bevroren klok en herstelt de patches bij het verlaten van de with-blok.
    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._freeze is not None:
            self._freeze.stop()
            self._freeze = None
        self._patches.restore()
        return False

    # -- patch installation ----------------------------------------------

    # Zet alle class- en module-patches voor deze replaysessie neer: config, reads, writes en de klok.
    def _install_patches(self) -> None:
        DaBase, Report, DBmanagerObj, SolarPredictor, da_base_module = _import_targets()

        if self._config_dict is None:
            raise SnapshotMiss(
                f"ReplayIO ({self._source}): snapshot has no 'config' field; "
                f"cannot replay without a config to construct DaBase from."
            )
        rehydrated_config = _rehydrate_config(self._config_dict)
        self._patches.set(DaBase, "_config", rehydrated_config)
        self._patches.set(DaBase, "_loader", _FakeLoader())

        # Same capture as RecordingIO, for the same reason: without this,
        # a replay produces no *.result.json at all, so there is nothing
        # to `diff` its objective/gap/status against — not the source
        # capture, not another replay at a different thread count.
        try:
            import dao.prog.day_ahead as day_ahead_module

            _install_cbc_log_capture(self._patches, day_ahead_module, self)
        except ImportError:
            logger.warning(
                "ReplayIO: kon day_ahead niet importeren; het CBC-log "
                "wordt niet vastgelegd"
            )
        _install_model_capture(self._patches, self)

        original_init = DaBase.__init__

        # Dwingt debug-modus en het gekozen aantal threads af op elke geconstrueerde instantie, ongeacht wie hem aanmaakt.
        def _wrapped_init(instance, *args, **kwargs):
            original_init(instance, *args, **kwargs)
            if instance.config is not None:
                instance.debug = True
                instance._solver_threads = (
                    self._recorded_solver_threads
                    if self._solver_threads_override is None
                    else self._solver_threads_override
                )
                if self._primary is None:
                    self._primary = instance

        self._patches.set(DaBase, "__init__", _wrapped_init)

        # Levert de opgeslagen state terug en faalt hard als de gevraagde entity niet in de snapshot zit.
        def _replay_get_state(instance, entity_id, *args, **kwargs):
            self._reads.add(entity_id)
            if entity_id not in self._ha_states:
                raise SnapshotMiss(
                    f"ReplayIO ({self._source}): entity '{entity_id}' is not "
                    f"present in the snapshot's ha_states — either the "
                    f"fixture is stale or a scenario override is missing."
                )
            return _FakeState(self._ha_states[entity_id])

        self._patches.set(DaBase, "get_state", _replay_get_state)

        # Levert de opgeslagen baseload terug voor de gevraagde weekdag en faalt hard als die ontbreekt.
        def _replay_baseload(instance, weekday, *args, **kwargs):
            key = str(int(weekday))
            if key not in self._baseload:
                raise SnapshotMiss(
                    f"ReplayIO ({self._source}): baseload for weekday {key} "
                    f"is not present in the snapshot."
                )
            return self._baseload[key]

        self._patches.set(DaBase, "get_calculated_baseload", _replay_baseload)

        # Levert de opgeslagen prijsdata terug in plaats van een databasequery uit te voeren.
        def _replay_get_price_data(instance, start, end=None, interval="1hour"):
            if self._price_data is None:
                raise SnapshotMiss(
                    f"ReplayIO ({self._source}): snapshot has no price_data."
                )
            return self._price_data.copy()

        self._patches.set(Report, "get_price_data", _replay_get_price_data)

        # Levert het opgeslagen resultaat terug per argumentcombinatie en faalt hard als die ontbreekt.
        def _replay_hp_hours(instance, *args, **kwargs):
            key = _call_key(args, kwargs)
            if key not in self._heatpump_run_hours:
                raise SnapshotMiss(
                    f"ReplayIO ({self._source}): get_heatpump_run_hours"
                    f"{tuple(args)} is not present in the snapshot "
                    f"(looked up as key {key})."
                )
            return self._heatpump_run_hours[key]

        self._patches.set(Report, "get_heatpump_run_hours", _replay_hp_hours)

        # Levert de opgeslagen zonnevoorspelling terug op paneelnaam, ongevoelig voor een afwijkend tijdvenster.
        def _replay_predict_solar_device(instance, solar_option, start, end):
            # Keyed by device name only — see the matching comment on the
            # RecordingIO side for why (start, end) is deliberately excluded.
            key = _call_key((getattr(solar_option, "name", None),), {})
            if key not in self._solar_predictions:
                raise SnapshotMiss(
                    f"ReplayIO ({self._source}): predict_solar_device for "
                    f"{getattr(solar_option, 'name', '?')!r} is not present "
                    f"in the snapshot (looked up as key {key})."
                )
            return self._solar_predictions[key].copy()

        self._patches.set(SolarPredictor, "predict_solar_device", _replay_predict_solar_device)

        fake_db = _FakeDbManager(self._prog_data, self._source)
        self._patches.set(da_base_module, "make_db_da", lambda *a, **k: fake_db)
        self._patches.set(da_base_module, "make_db_ha", lambda *a, **k: fake_db)

        ha_context = self._ha_context or {
            "latitude": 0.0,
            "longitude": 0.0,
            "time_zone": "UTC",
            "country": "NL",
        }
        self._patches.set(
            da_base_module, "get", lambda *a, **k: _FakeHttpResponse(ha_context)
        )

        # hass.Hass.__init__ (from the hassapi package DaBase subclasses)
        # does its own independent reachability check via a bare
        # `requests.get(...)` inside hassapi.client.base — a call site
        # da_base.py has no seam for at all, distinct from the explicit
        # `get(hassurl + "api/config")` above. Patching the `requests`
        # module's own `get` attribute reaches it, since hassapi does
        # `import requests` (a shared module reference) rather than
        # `from requests import get` (a copied one, which is why da_base.py
        # needed its own separate patch just above).
        import requests

        self._patches.set(
            requests,
            "get",
            lambda *a, **k: _FakeHttpResponse({"message": "API running."}),
        )

        label = f"ReplayIO ({self._source})"
        self._patches.set(DaBase, "set_value", _make_noop_set_value(label))
        self._patches.set(DaBase, "call_service", _make_noop_call_service(label))

        # Independent of the (always-on) HA write suppression above: the
        # PNG is a plain local file, not an HA/DB write, so whether to
        # keep it is its own switch. Off by default — see `png` on
        # __init__.
        if not self._png:
            import matplotlib.pyplot as plt

            self._patches.set(plt, "savefig", _make_noop_savefig(label))

        try:
            import freezegun

            captured_at = self._snapshot.get("meta", {}).get("captured_at")
            if captured_at:
                # tick=True: the clock still starts anchored at captured_at
                # (so calc_optimum()'s date/weekday-dependent reads land at
                # the intended moment — replay's DB/HA reads are all faked,
                # so there's no real setup latency to drift across an
                # interval boundary before they fire), but it advances in
                # real time from there rather than staying frozen solid.
                # Without tick, freezegun also freezes time.perf_counter()/
                # time.monotonic() — found by a user reporting "Rekentijd:
                # 0.00 sec" on every replay, since day_ahead.py measures
                # solve time with time.perf_counter(), and a fully static
                # clock makes any two reads of it identical by construction.
                self._freeze = freezegun.freeze_time(captured_at, tick=True)
                self._freeze.start()
        except ImportError:
            logger.warning(
                "ReplayIO: freezegun is niet beschikbaar; de wall-clock wordt "
                "niet bevroren tijdens deze replay"
            )


# ---------------------------------------------------------------------------
# Variable registry (A1's hook 1, §2.3) and dump_interval (A3, §2.5)
# ---------------------------------------------------------------------------
#
# day_ahead.py's calc_optimum() already calls build_var_registry(locals())
# just before model.optimize() when self._debug_capture_vars is set (the
# hook A1 landed). Nothing here is reachable from an ordinary run: the flag
# defaults to unset, and everything below is only ever driven by the `dump`
# CLI command or by tests that build a synthetic mip.Model directly.


class VarRegistryError(RuntimeError):
    """Raised when the registry contains a container with no SHAPES entry
    and no SHAPES_IGNORE entry — i.e. calc_optimum() grew a new variable
    family that dump_interval was never taught the axis layout of. This is
    meant to fail loudly (§2.5's "completeness assertion") rather than
    silently omit the new container from every future dump."""


# Bouwt {var.idx: (containernaam, indextuple)} uit calc_optimum()'s eigen
# locals() vlak vóór model.optimize(); loopt alleen door lists/tuples, dus
# DataFrames, configobjecten en losse scalars worden vanzelf overgeslagen.
def build_var_registry(local_vars: dict) -> dict[int, tuple[str, tuple]]:
    """§2.3: ``{var.idx: (container_name, index_tuple)}`` built from
    ``calc_optimum()``'s own ``locals()`` just before ``model.optimize()``.

    Only walks values that are themselves ``list``/``tuple`` at the top
    level, then recurses through nested lists/tuples looking for ``mip.Var``
    leaves. This is deliberate, not incidental: mip never names variables
    (0 of 81 ``add_var`` call sites in day_ahead.py pass ``name=``, per the
    architecture doc's §0.7 finding 1), so there is nothing to key on but
    the Python container structure — and restricting the walk to
    list/tuple means DataFrames, pydantic config objects, and plain scalar
    locals are dead ends rather than needing an exclude list. Keyed by
    ``var.idx`` rather than the ``Var`` object itself, because
    ``mip.Var.__eq__`` returns a ``LinExpr`` rather than a bool and
    ``var.idx`` is unique per model regardless (architecture doc §2.3).
    """
    registry: dict[int, tuple[str, tuple]] = {}
    if mip is None:
        return registry

    # Loopt recursief door een (geneste) list/tuple en registreert elke
    # Var-leaf onder zijn containernaam en indexpad.
    def _walk(name: str, value, path: tuple) -> None:
        if isinstance(value, mip.Var):
            registry[value.idx] = (name, path)
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                _walk(name, item, path + (i,))
        # Everything else (DataFrame, dict, pydantic model, float, str,
        # None, ...) is neither a Var nor a container to recurse into.

    for name, value in local_vars.items():
        if isinstance(value, (list, tuple)):
            _walk(name, value, ())
    return registry


# Declaratieve as-indeling per containernaam: welke Python-loopvariabele
# hoort bij welke positie in de geneste lijst. "u" is het interval-as,
# "u_boundary" is dezelfde as maar met lengte U+1 (SoC-grenzen). Geschreven
# tegen de huidige day_ahead.py door de model-bouwsectie te lezen, niet
# afgeleid uit de namen — zie de architectuurdoc §2.5 voor het voorbeeld dat
# dit uitbreidt.
SHAPES: dict[str, tuple[str, ...]] = {
    # solar (top-level AC-coupled arrays, independent of any battery)
    "pv_ac": ("s", "u"),
    "pv_ac_on_off": ("s", "u"),
    # battery — DC-coupled solar feeding this battery specifically
    "pv_dc_on_off": ("b", "pvdc", "u"),
    "pv_prod_dc_sum": ("b", "u"),
    # battery — AC<->DC, both curves are SOS2 (§2.5); the commented
    # on/off-without-SOS alternatives never execute, so they never appear
    # in locals() and need no entry here
    "ac_to_dc": ("b", "u"),
    "ac_to_dc_on": ("b", "u"),
    "ac_to_dc_w": ("b", "u", "cs"),  # SOS2 weight, charge
    "ac_from_dc": ("b", "u"),
    "ac_from_dc_on": ("b", "u"),
    "ac_from_dc_w": ("b", "u", "ds"),  # SOS2 weight, discharge
    "dc_from_ac": ("b", "u"),
    "dc_to_ac": ("b", "u"),
    "dc_from_bat": ("b", "u"),
    "dc_to_bat": ("b", "u"),
    "soc": ("b", "u_boundary"),
    "soc_low": ("b", "u_boundary"),
    "soc_mid": ("b", "u_boundary"),
    "cycle_cost": ("b",),
    "penalty_cost": ("b",),
    # boiler (single, not indexed by asset)
    "boiler_on": ("u",),
    "boiler_st": ("u",),
    "boiler_temp": ("u_boundary",),
    "c_b": ("u",),
    # ev — note stage_* is [e][ecs][u] (stage before interval), while every
    # other per-ev container is [e][u]; a transposed index here would
    # produce plausible-looking wrong numbers (architecture doc §8.5)
    "stage_consumption": ("e", "ecs", "u"),
    "stage_factor": ("e", "ecs", "u"),
    "stage_on": ("e", "ecs", "u"),
    "c_ev": ("e", "u"),
    "p_ev": ("e", "u"),
    "ev_accu_in": ("e", "u"),
    "ev_soc_kwh": ("e", "u"),
    "ev_is_on": ("e", "u"),
    "ev_is_off": ("e", "u"),
    "ev_is_partial": ("e", "u"),
    "ev_boundary_stop": ("e", "u"),
    "ev_partial_sum": ("e",),
    "ev_boundary_sum": ("e",),
    "ev_start_stops_sum": ("e",),
    "ev_delta_soc": ("e", "u"),
    "low_soc_penalty_int": ("e", "u"),
    "low_soc_penalty": ("e",),
    "switch_cost": ("e",),
    # grid
    "c_l": ("u",),
    "c_t": ("u",),
    "c_l_on": ("u",),
    "c_t_on": ("u",),
    # heat pump — mutually exclusive per run depending on
    # heating_options.adjustment: "on/off" builds hp_bl_on/hp_start_index,
    # "power"/"heating curve" builds p_hp/hp_s_w (third active add_sos() —
    # architecture doc §11, A0 Q7). Note p_hp is [s][u] while its own
    # SOS2 weight hp_s_w is [u][s] — transposed relative to each other,
    # same class of trap as the EV stage arrays above.
    "c_hp": ("u",),
    "hp_on": ("u",),
    "h_hp": ("u",),
    "hp_bl_on": ("blk", "u"),
    "hp_start_index": ("blk",),
    "p_hp": ("s_hp", "u"),
    "hp_s_w": ("u", "s_hp"),  # SOS2 weight, heat pump
    # machines
    "ma_start": ("m", "kw"),
    "c_ma_kw": ("m", "kw"),
    "c_ma_u": ("m", "u"),
}

# Containers that legitimately produce Var leaves but are deliberately not
# part of a per-interval dump (currently none — every container that shows
# up in the registry has a SHAPES entry above). Kept as a real set, not a
# comment, so _assert_shapes_complete has somewhere to point a genuinely
# non-interval container without that container silently vanishing from
# every dump.
SHAPES_IGNORE: frozenset[str] = frozenset()

# Grouping used only for dump_interval's human-readable output — which
# heading a container's values print under. Purely cosmetic: an unlisted
# container still passes _assert_shapes_complete as long as it's in SHAPES,
# it just prints under "other".
FAMILY: dict[str, str] = {
    "pv_ac": "solar",
    "pv_ac_on_off": "solar",
    "pv_dc_on_off": "battery",
    "pv_prod_dc_sum": "battery",
    "ac_to_dc": "battery",
    "ac_to_dc_on": "battery",
    "ac_to_dc_w": "battery",
    "ac_from_dc": "battery",
    "ac_from_dc_on": "battery",
    "ac_from_dc_w": "battery",
    "dc_from_ac": "battery",
    "dc_to_ac": "battery",
    "dc_from_bat": "battery",
    "dc_to_bat": "battery",
    "soc": "battery",
    "soc_low": "battery",
    "soc_mid": "battery",
    "cycle_cost": "battery",
    "penalty_cost": "battery",
    "boiler_on": "boiler",
    "boiler_st": "boiler",
    "boiler_temp": "boiler",
    "c_b": "boiler",
    "stage_consumption": "ev",
    "stage_factor": "ev",
    "stage_on": "ev",
    "c_ev": "ev",
    "p_ev": "ev",
    "ev_accu_in": "ev",
    "ev_soc_kwh": "ev",
    "ev_is_on": "ev",
    "ev_is_off": "ev",
    "ev_is_partial": "ev",
    "ev_boundary_stop": "ev",
    "ev_partial_sum": "ev",
    "ev_boundary_sum": "ev",
    "ev_start_stops_sum": "ev",
    "ev_delta_soc": "ev",
    "low_soc_penalty_int": "ev",
    "low_soc_penalty": "ev",
    "switch_cost": "ev",
    "c_l": "grid",
    "c_t": "grid",
    "c_l_on": "grid",
    "c_t_on": "grid",
    "c_hp": "heatpump",
    "hp_on": "heatpump",
    "h_hp": "heatpump",
    "hp_bl_on": "heatpump",
    "hp_start_index": "heatpump",
    "p_hp": "heatpump",
    "hp_s_w": "heatpump",
    "ma_start": "machine",
    "c_ma_kw": "machine",
    "c_ma_u": "machine",
}

# Asset-index axes that get their own sub-heading in the text render
# ("battery 0", "ev 1", ...) when they are a container's leading axis.
_ASSET_AXES = ("b", "e", "m")


# Faalt hard, met de namen van de onbekende containers, zodra de registry
# een containernaam bevat die niet in SHAPES of SHAPES_IGNORE voorkomt —
# dit is de "voeg een container toe zonder SHAPES bij te werken" val uit de
# A3-testparagraaf.
def _assert_shapes_complete(registry: dict) -> None:
    names = {name for name, _ in registry.values()}
    unknown = sorted(names - set(SHAPES) - SHAPES_IGNORE)
    if unknown:
        raise VarRegistryError(
            f"{len(unknown)} variable container(s) have no SHAPES entry "
            f"and are not on SHAPES_IGNORE: {', '.join(unknown)}. "
            f"calc_optimum() grew a new variable family; add its axis "
            f"layout to SHAPES (or to SHAPES_IGNORE if it's deliberately "
            f"not interval-addressable) in da_debug.py before dump can "
            f"cover it."
        )


# Groepeert de registry per containernaam, nodig omdat build_var_registry
# zelf per var.idx sleutelt en dump_interval juist per container wil kunnen
# selecteren.
def _group_by_container(registry: dict) -> dict[str, list[tuple[tuple, int]]]:
    groups: dict[str, list[tuple[tuple, int]]] = {}
    for var_idx, (name, idx_tuple) in registry.items():
        groups.setdefault(name, []).append((idx_tuple, var_idx))
    return groups


# Zoekt de interval-as van een SHAPES-vorm op: positie plus of het de
# U+1-grensvariant (soc-achtig) is. Geeft None als de container geen
# interval-as heeft (bv. cycle_cost, alleen per batterij).
def _interval_axis(shape: tuple[str, ...]) -> Optional[tuple[int, bool]]:
    if "u_boundary" in shape:
        return shape.index("u_boundary"), True
    if "u" in shape:
        return shape.index("u"), False
    return None


# Selecteert uit een containers items alleen de indextuples waarvan de
# interval-as in `wanted` zit; geeft (indextuple, var_idx)-paren terug.
def _select_at(entries: list[tuple[tuple, int]], axis_pos: int, wanted: set[int]):
    return [(idx, vidx) for idx, vidx in entries if idx[axis_pos] in wanted]


# Bouwt eenmalig var.idx -> [constraint-index, ...] en cachet dat op het
# model, zodat meerdere dump_interval-aanroepen tegen hetzelfde opgeloste
# model de O(aantal constraints)-kost maar één keer betalen (§2.5, gemeten
# 10ms bij 2304 constraints).
def _inverse_var_constraint_index(model) -> dict[int, list[int]]:
    cached = getattr(model, "_debug_inv_index", None)
    if cached is not None:
        return cached
    inv: dict[int, list[int]] = {}
    for ci, c in enumerate(model.constrs):
        for v in c.expr.expr:
            inv.setdefault(v.idx, []).append(ci)
    try:
        model._debug_inv_index = inv
    except Exception:  # pragma: no cover - mip.Model has no __slots__ today
        pass
    return inv


# Berekent (activity, rhs) van een constraint rechtstreeks uit coëfficiënten
# en opgeloste waarden, in plaats van op het teken van c.slack te vertrouwen
# — c.expr.const is de negatieve RHS [geverifieerd tegen een echt mip-model].
def _constraint_activity(c) -> tuple[float, float]:
    activity = sum(coef * v.x for v, coef in c.expr.expr.items())
    rhs = -c.expr.const
    return activity, rhs


# Een constraint is bindend als de activity binnen tolerantie gelijk is aan
# de rhs.
def _is_binding(c, tol: float = 1e-6) -> bool:
    activity, rhs = _constraint_activity(c)
    return abs(activity - rhs) < tol


# Vertaalt een Var naar zijn leesbare label via de registry, of naar
# var(idx) als de Var niet geregistreerd is (bv. de kale cost/delivery-
# variabelen, die nooit in een list/tuple zaten en dus geen registry-entry
# hebben — build_var_registry loopt bewust alleen door containers).
def label_for_var(var, registry: dict) -> str:
    entry = registry.get(var.idx)
    if entry is None:
        return f"var({var.idx})"
    name, idx = entry
    return name + "".join(f"[{i}]" for i in idx)


_SENSE_SYMBOLS = {"<": "<=", ">": ">=", "=": "="}


# Rendert een constraint met registry-labels in plaats van var(N)/constr(N),
# bv. "ac_to_dc[0][14] - 0.95*dc_from_ac[0][14] = 0".
def render_constraint(c, registry: dict) -> str:
    terms = sorted(
        ((coef, label_for_var(v, registry)) for v, coef in c.expr.expr.items()),
        key=lambda t: t[1],
    )
    pieces: list[str] = []
    for coef, label in terms:
        magnitude = abs(coef)
        coef_str = "" if abs(magnitude - 1) < 1e-12 else f"{magnitude:g}*"
        term = f"{coef_str}{label}"
        if not pieces:
            pieces.append(f"-{term}" if coef < 0 else term)
        else:
            pieces.append(f"- {term}" if coef < 0 else f"+ {term}")
    lhs = " ".join(pieces) if pieces else "0"
    rhs = -c.expr.const + 0.0  # normalises -0.0 to 0.0 so it doesn't print as "-0"
    sense = _SENSE_SYMBOLS.get(c.expr.sense, c.expr.sense)
    return f"{lhs} {sense} {rhs:g}"


# Elke actieve SOS2-curve in het model: (label, gewichtscontainer, as-naam
# van de trap, container met de al-geïnterpoleerde waarde). python-mip
# biedt geen manier om SOS-sets na add_sos() terug op te vragen, dus dit kan
# alleen uit de gewichtsvariabelen zelf komen, niet uit constraint-inspectie
# (§2.5). Drie sites, zie A0 Q7 / architectuurdoc §11: batterij laden,
# batterij ontladen, warmtepomp (alleen aanwezig bij adjustment "power" /
# "heating curve" — de "on/off"-tak gebruikt hp_bl_on zonder SOS2).
_SOS2_CURVES = (
    ("battery charge", "ac_to_dc_w", "cs", "ac_to_dc"),
    ("battery discharge", "ac_from_dc_w", "ds", "ac_from_dc"),
    ("heat pump", "hp_s_w", "s_hp", "h_hp"),
)


# Bouwt voor elke aanwezige SOS2-curve een rapport op interval u: welke
# trappen actief zijn, of ze aangrenzend zijn, en de al-geïnterpoleerde
# waarde uit de bijbehorende vermogenscontainer.
def _sos2_reports(model, registry: dict, u: int) -> list[dict]:
    by_container = _group_by_container(registry)
    reports: list[dict] = []
    for label, weight_name, stage_axis, power_name in _SOS2_CURVES:
        entries = by_container.get(weight_name)
        if not entries:
            continue  # this run didn't build this curve (e.g. hp on/off mode)
        shape = SHAPES[weight_name]
        u_pos = shape.index("u")
        stage_pos = shape.index(stage_axis)

        groups: dict[tuple, dict[int, int]] = {}
        for idx_tuple, var_idx in entries:
            if idx_tuple[u_pos] != u:
                continue
            rest = tuple(
                v for pos, v in enumerate(idx_tuple) if pos not in (u_pos, stage_pos)
            )
            groups.setdefault(rest, {})[idx_tuple[stage_pos]] = var_idx

        power_by_key: dict[tuple, int] = {}
        power_shape = SHAPES.get(power_name) if power_name else None
        if power_name and power_shape and "u" in power_shape:
            p_u_pos = power_shape.index("u")
            for idx_tuple, var_idx in by_container.get(power_name, []):
                if idx_tuple[p_u_pos] != u:
                    continue
                rest = tuple(v for pos, v in enumerate(idx_tuple) if pos != p_u_pos)
                power_by_key[rest] = var_idx

        for rest, stage_map in sorted(groups.items()):
            stages = sorted(stage_map.items())
            values = [(s, model.vars[vidx].x) for s, vidx in stages]
            nonzero = [(s, v) for s, v in values if abs(v) > 1e-9]
            indices = [s for s, _ in nonzero]
            if len(indices) <= 1:
                adjacent = True
            elif len(indices) == 2:
                adjacent = indices[1] - indices[0] == 1
            else:
                adjacent = False
            interp_idx = power_by_key.get(rest)
            reports.append(
                {
                    "curve": label,
                    "asset": rest,
                    "weights": values,
                    "active_stages": nonzero,
                    "adjacent": adjacent,
                    "interpolated": model.vars[interp_idx].x
                    if interp_idx is not None
                    else None,
                }
            )
    return reports


# Bouwt de sectiesleutel voor de tekstuitvoer: "battery 0", "ev 1", of
# gewoon "boiler"/"grid" als de container geen asset-as heeft. Neemt de
# echte indexwaarde uit idx_tuple, niet de as-naam — anders zouden batterij
# 0 en batterij 1 onder dezelfde sleutel samenvloeien.
def _section_key(name: str, shape: tuple[str, ...], idx_tuple: tuple) -> str:
    family = FAMILY.get(name, "other")
    if shape and shape[0] in _ASSET_AXES:
        return f"{family} {idx_tuple[0]}"
    return family


# Kernfunctie van A3 (§2.5): alles wat het opgeloste model wist over
# interval u — elke variabele met leesbaar label, welke constraints
# bindend zijn, en de SOS2-status van elke aanwezige piecewise-curve.
# Geeft een structuur terug (geen platte tekst) zodat zowel de tekst- als
# de --json-weergave van de CLI op dezelfde data werken.
def dump_interval(model, registry: dict, u: int, *, header: Optional[dict] = None) -> dict:
    """Everything the solved model knew about interval ``u``: every
    registered variable touching it, which constraints on it are actually
    binding, and the SOS2 active-stage/adjacency state for every piecewise
    curve present in this run. Raises ``VarRegistryError`` if the registry
    contains a container ``SHAPES`` doesn't know about (§2.5's completeness
    assertion — a silent gap here is worse than a loud failure, since it
    would just quietly omit part of the model from every dump)."""
    _assert_shapes_complete(registry)
    by_container = _group_by_container(registry)

    sections: dict[str, list[dict]] = {}
    touched_vars: set[int] = set()
    for name, entries in by_container.items():
        shape = SHAPES[name]
        axis = _interval_axis(shape)
        if axis is None:
            continue  # no interval axis at all (e.g. cycle_cost[b])
        axis_pos, is_boundary = axis
        wanted = {u, u + 1} if is_boundary else {u}
        matches = _select_at(entries, axis_pos, wanted)
        for idx_tuple, var_idx in matches:
            touched_vars.add(var_idx)
            section_key = _section_key(name, shape, idx_tuple)
            sections.setdefault(section_key, []).append(
                {
                    "label": name + "".join(f"[{i}]" for i in idx_tuple),
                    "container": name,
                    "index": idx_tuple,
                    "value": model.vars[var_idx].x,
                    "is_boundary_partner": is_boundary and idx_tuple[axis_pos] == u + 1,
                }
            )
    for entries in sections.values():
        entries.sort(key=lambda e: e["label"])

    sos2 = _sos2_reports(model, registry, u)

    inv = _inverse_var_constraint_index(model)
    constraint_ids = sorted({ci for vidx in touched_vars for ci in inv.get(vidx, [])})
    binding_constraints = [
        {"index": ci, "text": render_constraint(model.constrs[ci], registry)}
        for ci in constraint_ids
        if _is_binding(model.constrs[ci])
    ]

    # Reduced-detail neighbour context (§2.5 / A3 testing): SoC and
    # top-level charge/discharge only, no on/off flags, no SOS2, no
    # constraints — just enough to see the trend across the interval.
    context_names = ("soc", "ac_to_dc", "ac_from_dc", "c_hp", "c_ev", "c_b")
    context: dict[str, dict[str, list[dict]]] = {}
    for neighbour in (u - 1, u + 1):
        if neighbour < 0:
            continue
        neighbour_sections: dict[str, list[dict]] = {}
        for name in context_names:
            entries = by_container.get(name)
            if not entries:
                continue
            shape = SHAPES[name]
            axis = _interval_axis(shape)
            if axis is None:
                continue
            axis_pos, _is_boundary = axis
            matches = _select_at(entries, axis_pos, {neighbour})
            for idx_tuple, var_idx in matches:
                section_key = _section_key(name, shape, idx_tuple)
                neighbour_sections.setdefault(section_key, []).append(
                    {
                        "label": name + "".join(f"[{i}]" for i in idx_tuple),
                        "value": model.vars[var_idx].x,
                    }
                )
        if neighbour_sections:
            for entries in neighbour_sections.values():
                entries.sort(key=lambda e: e["label"])
            context[str(neighbour)] = neighbour_sections

    return {
        "interval": u,
        "header": dict(header) if header else {},
        "sections": sections,
        "sos2": sos2,
        "binding_constraints": binding_constraints,
        "context": context,
    }


# Formatteert de structuur van dump_interval() als leesbare platte tekst
# voor stdout; --json op de CLI gebruikt de structuur direct.
def _format_dump_text(data: dict) -> str:
    lines: list[str] = []
    header_bits = [f"interval {data['interval']}"]
    for k, v in data.get("header", {}).items():
        if v is not None:
            header_bits.append(str(v))
    lines.append("  ".join(header_bits))

    for section_name in sorted(data["sections"]):
        entries = data["sections"][section_name]
        lines.append(f"  {section_name}")
        for e in entries:
            arrow = " (boundary)" if e.get("is_boundary_partner") else ""
            lines.append(f"    {e['label']:<28} {e['value']:.4f}{arrow}")

    if data["sos2"]:
        lines.append("  SOS2 curves")
        for r in data["sos2"]:
            asset = f" {r['asset']}" if r["asset"] else ""
            stages = ", ".join(f"stage {s} (w={v:.4f})" for s, v in r["active_stages"])
            if not stages:
                stages = "no active stage"
            flag = "ok" if r["adjacent"] else "NON-ADJACENT — solver-correctness signal"
            interp = f"  interpolated={r['interpolated']:.4f}" if r["interpolated"] is not None else ""
            lines.append(f"    {r['curve']}{asset}: {stages}  [adjacent: {flag}]{interp}")

    lines.append(f"  binding constraints ({len(data['binding_constraints'])})")
    for bc in data["binding_constraints"]:
        lines.append(f"    {bc['text']}")

    for neighbour, sections in data.get("context", {}).items():
        if not sections:
            continue
        lines.append(f"  context u={neighbour}")
        for section_name in sorted(sections):
            for e in sections[section_name]:
                lines.append(f"    {e['label']:<28} {e['value']:.4f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI (A6, §13)
# ---------------------------------------------------------------------------
#
# `python -m dao.prog.da_debug <command>` — run from anywhere the `dao`
# package is importable from (typically the repository root); paths are
# resolved absolutely from --data-dir at startup and never from cwd.

EXIT_OK = 0
EXIT_ASSERTION_FAILED = 1
EXIT_USAGE = 2
EXIT_SOLVER_FAILURE = 3
EXIT_SNAPSHOT_MISS = 4
EXIT_HERMETICITY_VIOLATION = 5


class UsageError(Exception):
    """A CLI-level usage problem: bad arguments, missing file, malformed
    ``--state``. Distinct from ``SnapshotMiss`` (a fixture is missing data)
    and ``HermeticityViolation`` (replay reached for the network) — each
    maps to its own exit code in ``main()``."""


class HermeticityViolation(RuntimeError):
    """Raised when a replayed run reaches for the network while ``--offline``
    (the default for ``replay``) is in effect. §13.2: this is what turns
    "the operator happened to be on the right machine" into something the
    tool itself proves on every run."""


# Geeft de map van dit bestand terug, basis voor alle padresolutie zonder afhankelijkheid van de werkmap.
def _module_dir() -> Path:
    return Path(__file__).resolve().parent


# Zet dao/prog op sys.path zodat day_ahead.py's eigen kale import van utils blijft werken, ook wanneer dit bestand als module wordt aangeroepen.
def _ensure_day_ahead_importable() -> None:
    """day_ahead.py does `from utils import (...)` — a bare import that only
    resolves when dao/prog itself is on sys.path. That's true when it's run
    as a script from that directory (the addon's own invocation style), but
    not when it's reached via the dotted `dao.prog.day_ahead` import this
    CLI uses when invoked as `python -m dao.prog.da_debug` from elsewhere.
    Found by actually running `replay` from the repo root, not by reading
    the import — exactly the class of gap static reading misses."""
    module_dir = str(_module_dir())
    if module_dir not in sys.path:
        sys.path.append(module_dir)


# Standaard datamap, gelijk aan de ../data-conventie die day_ahead.py zelf ook gebruikt.
def _default_data_dir() -> Path:
    return (_module_dir() / ".." / "data").resolve()


# Kiest --data-dir als die is opgegeven, anders de standaardmap.
def _resolve_data_dir(args: argparse.Namespace) -> Path:
    if getattr(args, "data_dir", None):
        return Path(args.data_dir).resolve()
    return _default_data_dir()


# Zoekt een snapshotbestand op: een pad met map laat het met rust, een kale bestandsnaam wordt tegen debug_snapshots/ geresolved.
def _resolve_snapshot_arg(data_dir: Path, given: str) -> Path:
    """A bare filename resolves against ``<data-dir>/debug_snapshots/``;
    anything that already exists, is absolute, or has path separators is
    used as given."""
    p = Path(given)
    if p.exists() or p.is_absolute() or len(p.parts) > 1:
        return p.resolve()
    return (data_dir / "debug_snapshots" / given).resolve()


# Leest en parseert een snapshot-JSON-bestand, met een duidelijke fout als het niet bestaat.
def _load_snapshot_file(path: Path) -> dict:
    if not path.exists():
        raise UsageError(f"Snapshot not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Kiest op één plek tussen JSON- en tekstuitvoer, zodat elk commando dezelfde --json-afhandeling deelt.
def _emit(args: argparse.Namespace, data: dict, render) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, default=str, sort_keys=True))
    else:
        render(data)


# Geeft een korte 'rijenxkolommen'-samenvatting van een DataFrame-payload, voor gebruik in inspect.
def _df_payload_shape(payload: Optional[dict]) -> str:
    if not payload:
        return "none"
    try:
        rows = len(json.loads(payload["data"]).get("data", []))
        cols = len(payload.get("dtypes", {}))
        return f"{rows}x{cols}"
    except Exception:
        return "unknown"


# Telt hoeveel velden in een configboom als geheim zijn geredigeerd, voor een snelle controle in inspect.
def _count_redacted(value: Any) -> int:
    """Count REDACTED_SECRET markers anywhere in a sanitised config tree."""
    if isinstance(value, str):
        return 1 if value == REDACTED_SECRET else 0
    if isinstance(value, dict):
        return sum(_count_redacted(v) for v in value.values())
    if isinstance(value, list):
        return sum(_count_redacted(v) for v in value)
    return 0


# Doorloopt een gerehydrateerde config en meldt elk SecretStr-veld dat niet de redactiemarkering bevat; kern van verify's geheimencontrole.
def _find_unredacted_secrets(value: Any, path: str = "") -> list[str]:
    """Walk a *rehydrated* (live pydantic object graph, not a dict) config
    and report the dotted path of every SecretStr field that is not exactly
    REDACTED_SECRET — i.e. a real or planted credential. Mirrors
    ``_sanitize_config_value``'s traversal but checks rather than redacts."""
    from dao.prog.config.models.base import SecretStr
    from pydantic import BaseModel

    found: list[str] = []
    if isinstance(value, SecretStr):
        if str(value) != REDACTED_SECRET:
            found.append(path or "<root>")
        return found
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            child = f"{path}.{name}" if path else name
            found.extend(_find_unredacted_secrets(getattr(value, name), child))
        return found
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{path}.{k}" if path else str(k)
            found.extend(_find_unredacted_secrets(v, child))
        return found
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            found.extend(_find_unredacted_secrets(v, f"{path}[{i}]"))
        return found
    return found


# Laadt een live options.json via een wegwerpkopie (nooit het origineel) en vergelijkt de confighash met die van de snapshot.
def _check_config_drift(config_path_str: str, stored_hash: Optional[str]) -> dict:
    """§13.4: copy-then-load. Never opens the real config file for writing,
    and asserts (not just assumes) that it comes out byte-identical."""
    import shutil
    import tempfile

    config_path = Path(config_path_str).resolve()
    if not config_path.exists():
        raise UsageError(f"Config not found: {config_path}")
    secrets_path = config_path.parent / "secrets.json"

    before_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_config = Path(tmp) / config_path.name
        shutil.copy2(config_path, tmp_config)
        if secrets_path.exists():
            shutil.copy2(secrets_path, Path(tmp) / "secrets.json")

        from dao.prog.config.loader import ConfigurationLoader

        loader = ConfigurationLoader(tmp_config)
        live_config = loader.load_and_validate()
        live_hash = _config_hash(_sanitize_config(live_config))

    after_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    if before_hash != after_hash:
        # Should be structurally impossible — we only ever load the temp
        # copy — so this is an assertion, not a warning.
        raise RuntimeError(
            f"BUG: {config_path} changed on disk during a supposedly "
            f"copy-then-load verify pass"
        )

    return {
        "live_config_hash": live_hash,
        "differs": stored_hash is not None and live_hash != stored_hash,
    }


# Patcht socket.connect(_ex) zodat elk netwerkgebruik tijdens replay direct met een duidelijke fout stopt in plaats van stil te slagen.
def _offline_guard():
    """Patch socket.socket.connect/connect_ex to raise. Returns a handle
    for _offline_unguard(). See HermeticityViolation."""
    import socket

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    # Blokkeert een connect-poging en meldt welk adres erbij hoorde.
    def _blocked_connect(self, address, *a, **k):
        raise HermeticityViolation(
            f"Network access blocked under --offline: "
            f"socket.socket.connect({address!r})"
        )

    # Zelfde blokkade als _blocked_connect, voor de _ex-variant.
    def _blocked_connect_ex(self, address, *a, **k):
        raise HermeticityViolation(
            f"Network access blocked under --offline: "
            f"socket.socket.connect_ex({address!r})"
        )

    socket.socket.connect = _blocked_connect
    socket.socket.connect_ex = _blocked_connect_ex
    return socket, original_connect, original_connect_ex


# Zet de originele socket-methodes terug na afloop van de replay.
def _offline_unguard(saved) -> None:
    socket_module, original_connect, original_connect_ex = saved
    socket_module.socket.connect = original_connect
    socket_module.socket.connect_ex = original_connect_ex


# -- commands -----------------------------------------------------------


# Voert een echte calc_optimum()-run uit binnen RecordingIO en schrijft de snapshot en het resultaat weg.
def cmd_capture(args: argparse.Namespace, data_dir: Path) -> int:
    config_path = Path(args.config).resolve() if args.config else data_dir / "options.json"
    if not config_path.exists():
        raise UsageError(f"Config not found: {config_path}")
    out_dir = Path(args.out_dir).resolve() if args.out_dir else data_dir / "debug_snapshots"

    _ensure_day_ahead_importable()
    from dao.prog.day_ahead import DaCalc

    kwargs = {}
    if args.start_dt:
        kwargs["_start_dt"] = dt.datetime.fromisoformat(args.start_dt)
    if args.start_soc is not None:
        kwargs["_start_soc"] = args.start_soc
    if args.start_ev_soc is not None:
        kwargs["_start_ev_soc"] = args.start_ev_soc

    rec = RecordingIO(out_dir=out_dir, label=args.label, debug=args.debug, png=args.png)
    error = None
    result = None
    with rec:
        dacalc = DaCalc(str(config_path))
        try:
            result = dacalc.calc_optimum(**kwargs)
        except Exception as ex:  # noqa: BLE001 - reported below, not swallowed
            error = ex

    data = {
        "snapshot": str(rec.snapshot_path) if rec.snapshot_path else None,
        "result": str(rec.result_path) if rec.result_path else None,
        "error": f"{type(error).__name__}: {error}" if error is not None else None,
        "debug": bool(args.debug),
        "png": bool(args.png),
    }

    # Toont het capture-resultaat leesbaar op het scherm.
    def render(d):
        print(f"snapshot: {d['snapshot']}" if d["snapshot"] else "capture: nothing written (see log)")
        if d["result"]:
            print(f"result:   {d['result']}")
        print(
            f"debug:    {d['debug']}"
            + ("" if d["debug"] else " (this run wrote real settings to HA/DB — pass --debug to suppress that)")
        )
        print(f"png:      {d['png']}" + ("" if d["png"] else " (pass --png to keep the chart)"))
        if d["error"]:
            print(f"error during calc_optimum(): {d['error']}")

    _emit(args, data, render)

    if error is not None or result is None:
        return EXIT_SOLVER_FAILURE
    return EXIT_OK


# Speelt een snapshot hermetisch af binnen ReplayIO en schrijft het replay-resultaat weg.
def cmd_replay(args: argparse.Namespace, data_dir: Path) -> int:
    snapshot_path = _resolve_snapshot_arg(data_dir, args.snapshot)
    if not snapshot_path.exists():
        raise UsageError(f"Snapshot not found: {snapshot_path}")

    _ensure_day_ahead_importable()
    from dao.prog.day_ahead import DaCalc

    guard = _offline_guard() if args.offline else None
    try:
        with ReplayIO(snapshot_path, solver_threads=args.threads, png=args.png) as replay:
            file_name = str(snapshot_path)
            dacalc = DaCalc(file_name)
            # calc_optimum()'s return value is not a usable success signal —
            # see the matching comment in cmd_dump: it returns None
            # unconditionally, on success and on every failure path alike.
            # The solved model's own num_solutions, captured by ReplayIO's
            # mip.Model.optimize() wrapper, is what actually tells success
            # from failure below.
            dacalc.calc_optimum()
        reads = sorted(replay.reads)
        result_dict = replay.build_result()
        solved = replay._model is not None and replay._model.num_solutions > 0
    finally:
        if guard is not None:
            _offline_unguard(guard)

    result_path = None
    if result_dict is not None:
        if args.out_result:
            result_path = Path(args.out_result).resolve()
        else:
            result_path = snapshot_path.parent / (
                f"{snapshot_path.stem}.replay-threads{args.threads}.result.json"
            )
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, default=str)

    data = {
        "snapshot": str(snapshot_path),
        "result": str(result_path) if result_path else None,
        "reads": reads,
        "offline": bool(args.offline),
        "threads": args.threads,
        "png": bool(args.png),
    }

    # Toont het replay-resultaat leesbaar op het scherm.
    def render(d):
        print(f"replayed: {d['snapshot']}")
        print(f"offline:  {d['offline']}")
        print(f"threads:  {d['threads']}" + (" (all cores — pass --threads 1 for reproducibility)" if d["threads"] == -1 else ""))
        print(f"png:      {d['png']}" + ("" if d["png"] else " (pass --png to keep the chart)"))
        print(f"entities read: {len(d['reads'])}")
        print(f"result:   {d['result']}" if d["result"] else "result:   not written (solve never reached model.optimize())")

    _emit(args, data, render)
    return EXIT_OK if solved else EXIT_SOLVER_FAILURE


# Toont een samenvatting van een snapshot en eventueel resultaat, zonder de solver te draaien.
def cmd_inspect(args: argparse.Namespace, data_dir: Path) -> int:
    snapshot_path = _resolve_snapshot_arg(data_dir, args.snapshot)
    snapshot = _load_snapshot_file(snapshot_path)
    meta = snapshot.get("meta", {})

    result_path = snapshot_path.parent / (snapshot_path.stem + ".result.json")
    result = None
    if result_path.exists():
        with open(result_path, "r", encoding="utf-8") as f:
            result = json.load(f)

    data = {
        "path": str(snapshot_path),
        "meta": meta,
        "ha_states_count": len(snapshot.get("ha_states", {})),
        "price_data_shape": _df_payload_shape(snapshot.get("price_data")),
        "prog_data_shape": _df_payload_shape(snapshot.get("prog_data")),
        "baseload_days": len(snapshot.get("baseload", {})),
        "heatpump_run_hours_count": len(snapshot.get("heatpump_run_hours", {})),
        "secrets_redacted": _count_redacted(snapshot.get("config") or {}),
        "result": result,
    }

    # Formatteert de samenvatting voor tekstweergave.
    def render(d):
        m = d["meta"]
        print(f"dao {m.get('dao_version')} | mip {m.get('mip_version')} | schema {m.get('schema_version')}")
        print(f"captured  {m.get('captured_at')}   interval {m.get('interval')}   strategy {m.get('strategy')}")
        print(
            f"ha_states {d['ha_states_count']} entities | "
            f"price_data {d['price_data_shape']} | "
            f"prog_data {d['prog_data_shape']} | "
            f"baseload {d['baseload_days']} day(s) | "
            f"hp_run_hours {d['heatpump_run_hours_count']}"
        )
        print(f"config    secrets: {d['secrets_redacted']} redacted")
        if d["result"]:
            r = d["result"]
            print(
                f"result    objective {r.get('objective_value')}  "
                f"status {r.get('status')}  gap {r.get('gap')}"
            )
            cbc_log = r.get("cbc_log")
            if cbc_log:
                lines = cbc_log.count("\n") + 1
                partial = "Exiting on maximum nodes" in cbc_log
                flag = " — PARTIAL SEARCH, node cap hit, not proven optimal" if partial else ""
                print(f"cbc_log   {lines} lines captured{flag} (full text in the .result.json)")
            else:
                print("cbc_log   not captured (older snapshot, or model.optimize() never ran)")
        else:
            print("result    (no .result.json next to this snapshot)")

    _emit(args, data, render)
    return EXIT_OK


# Controleert schemaversie, confighash, geheimenlekken en optioneel configdrift; de integriteitscheck voor een snapshot.
def cmd_verify(args: argparse.Namespace, data_dir: Path) -> int:
    snapshot_path = _resolve_snapshot_arg(data_dir, args.snapshot)
    snapshot = _load_snapshot_file(snapshot_path)
    meta = snapshot.get("meta", {})
    problems: list[str] = []

    schema_version = meta.get("schema_version", 0)
    if schema_version < SCHEMA_MIN_SUPPORTED:
        problems.append(
            f"schema_version {schema_version} is older than minimum "
            f"supported {SCHEMA_MIN_SUPPORTED}"
        )

    config = snapshot.get("config")
    if config is None:
        problems.append("snapshot has no 'config' field")
    else:
        try:
            rehydrated = _rehydrate_config(config)
        except Exception as ex:
            problems.append(f"config does not reconstruct: {ex}")
            rehydrated = None
        if rehydrated is not None:
            leaked_fields = _find_unredacted_secrets(rehydrated)
            if leaked_fields:
                problems.append(
                    f"{len(leaked_fields)} SecretStr field(s) not redacted: "
                    f"{', '.join(leaked_fields)}"
                )
            recomputed_hash = _config_hash(_sanitize_config(rehydrated))
            stored_hash = meta.get("config_hash")
            if stored_hash and recomputed_hash != stored_hash:
                problems.append(
                    f"config_hash mismatch: stored {stored_hash}, "
                    f"recomputed {recomputed_hash} (snapshot may have been "
                    f"hand-edited)"
                )

    if args.secrets:
        secrets_path = Path(args.secrets).resolve()
        if not secrets_path.exists():
            raise UsageError(f"Secrets file not found: {secrets_path}")
        with open(secrets_path, "r", encoding="utf-8") as f:
            secret_values = list(json.load(f).values())
        blob = json.dumps(snapshot, default=str)
        leaked_values = [v for v in secret_values if v and v in blob]
        if leaked_values:
            problems.append(
                f"{len(leaked_values)} value(s) from {secrets_path} appear "
                f"literally in the snapshot"
            )

    drift = None
    if args.config:
        drift = _check_config_drift(args.config, meta.get("config_hash"))
        if drift.get("differs"):
            problems.append(
                f"live config at {args.config} has drifted from this "
                f"snapshot's config (hash differs)"
            )

    data = {"path": str(snapshot_path), "ok": not problems, "problems": problems, "config_drift": drift}

    # Toont OK of FAILED plus de gevonden problemen.
    def render(d):
        print(("OK: " if d["ok"] else "FAILED: ") + d["path"])
        for p in d["problems"]:
            print(f"  - {p}")

    _emit(args, data, render)
    return EXIT_OK if not problems else EXIT_ASSERTION_FAILED


# Vergelijkt twee snapshots of twee resultaatbestanden en toont precies welke velden verschillen.
def cmd_diff(args: argparse.Namespace, data_dir: Path) -> int:
    first_path = _resolve_snapshot_arg(data_dir, args.first)
    second_path = _resolve_snapshot_arg(data_dir, args.second)
    first = _load_snapshot_file(first_path)
    second = _load_snapshot_file(second_path)

    is_result = "objective_value" in first and "objective_value" in second
    changes: dict = {}

    if is_result:
        # Nested under "fields" (not merged flat into `changes`) so this
        # branch produces the same two-level {section: {field: {first,
        # second}}} shape the snapshot branch below does — render() below
        # relies on that uniformity. Never actually exercised until now:
        # every prior test compared a result file to itself, which
        # short-circuits on the empty-changes path before render() ever
        # walks a real entry.
        field_changes = {
            key: {"first": first.get(key), "second": second.get(key)}
            for key in ("objective_value", "objective_bound", "status", "gap", "num_solutions")
            if first.get(key) != second.get(key)
        }
        if field_changes:
            changes["fields"] = field_changes
    else:
        first_states = first.get("ha_states", {})
        second_states = second.get("ha_states", {})
        state_changes = {
            key: {"first": first_states.get(key), "second": second_states.get(key)}
            for key in sorted(set(first_states) | set(second_states))
            if first_states.get(key) != second_states.get(key)
        }
        if state_changes:
            changes["ha_states"] = state_changes

        first_meta = first.get("meta", {})
        second_meta = second.get("meta", {})
        meta_changes = {
            key: {"first": first_meta.get(key), "second": second_meta.get(key)}
            for key in sorted(set(first_meta) | set(second_meta))
            if first_meta.get(key) != second_meta.get(key)
        }
        if meta_changes:
            changes["meta"] = meta_changes

    data = {
        "first": str(first_path),
        "second": str(second_path),
        "kind": "result" if is_result else "snapshot",
        "changes": changes,
    }

    # Toont de gevonden verschillen per sectie.
    def render(d):
        if not d["changes"]:
            print("no differences")
            return
        for section, section_changes in d["changes"].items():
            print(f"{section}:")
            for k, v in section_changes.items():
                print(f"  {k}: {v['first']!r} -> {v['second']!r}")

    _emit(args, data, render)
    return EXIT_OK


# Maakt een nieuwe snapshot met overschreven entity-waarden, zonder de solver te draaien.
def cmd_set(args: argparse.Namespace, data_dir: Path) -> int:
    if not args.state:
        raise UsageError("set requires at least one --state entity_id=value")
    source_path = _resolve_snapshot_arg(data_dir, args.snapshot)
    snapshot = _load_snapshot_file(source_path)

    ha_states = dict(snapshot.get("ha_states", {}))
    applied = {}
    for item in args.state:
        if "=" not in item:
            raise UsageError(f"--state must be entity_id=value, got: {item!r}")
        entity_id, value = item.split("=", 1)
        ha_states[entity_id] = value
        applied[entity_id] = value
    snapshot["ha_states"] = ha_states

    meta = dict(snapshot.get("meta", {}))
    meta["derived_from"] = str(source_path)
    meta["derived_overrides"] = applied
    snapshot["meta"] = meta

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, default=str)

    data = {"out": str(out_path), "applied": applied}

    # Toont welke waarden zijn toegepast.
    def render(d):
        print(f"wrote: {d['out']}")
        for k, v in d["applied"].items():
            print(f"  {k} = {v}")

    _emit(args, data, render)
    return EXIT_OK


# Best-effort (tijdstip, prijs-levering, prijs-teruglevering) voor de dump-
# header; faalt nooit — geeft (None, None, None) bij twijfel in plaats van
# een mogelijk verkeerde prijs te tonen. Rondt captured_at af op de
# intervalgrens en zoekt de dichtstbijzijnde rij in het opgenomen
# price_data (niet prog_data — dat laatste krijgt da_cons/da_prod pas
# tijdens calc_optimum() zelf, dus de opgenomen kopie heeft die kolommen
# nog niet).
def _lookup_price_at_interval(
    replay: "ReplayIO", meta: dict, u: int
) -> tuple[Optional[dt.datetime], Optional[float], Optional[float]]:
    try:
        captured_at = meta.get("captured_at")
        interval_str = meta.get("interval")
        price_data = getattr(replay, "_price_data", None)
        if not captured_at or not interval_str or price_data is None:
            return None, None, None
        if "time" not in price_data.columns:
            return None, None, None
        interval_s = 3600 if interval_str == "1hour" else 900
        start = dt.datetime.fromisoformat(captured_at)
        if interval_s == 3600:
            rounded = start.replace(minute=0, second=0, microsecond=0)
        else:
            rounded = start.replace(
                minute=(start.minute // 15) * 15, second=0, microsecond=0
            )
        target = rounded + dt.timedelta(seconds=interval_s * u)
        times = pd.to_datetime(price_data["time"]).dt.tz_localize(None)
        deltas = (times - target.replace(tzinfo=None)).abs()
        pos = int(deltas.values.argmin())
        if deltas.iloc[pos] > dt.timedelta(seconds=interval_s / 2):
            return None, None, None
        row = price_data.iloc[pos]
        da_cons = float(row["da_cons"]) if "da_cons" in price_data.columns else None
        da_prod = float(row["da_prod"]) if "da_prod" in price_data.columns else None
        return target, da_cons, da_prod
    except Exception:  # noqa: BLE001 - header enrichment only, never fatal
        return None, None, None


# Zoekt de hoogste interval-index die daadwerkelijk in de registry
# voorkomt, om --interval tegen een zinnig bereik te kunnen valideren
# zonder dat de CLI U apart hoeft te kennen.
def _max_known_interval(registry: dict) -> int:
    max_u = -1
    for _var_idx, (name, idx_tuple) in registry.items():
        shape = SHAPES.get(name)
        if not shape:
            continue
        if "u" in shape:
            max_u = max(max_u, idx_tuple[shape.index("u")])
        elif "u_boundary" in shape:
            max_u = max(max_u, idx_tuple[shape.index("u_boundary")] - 1)
    return max_u


# Speelt een snapshot af met _debug_capture_vars aan, zodat A1's hook in
# day_ahead.py de variabele-registry opbouwt, en dumpt daarna interval
# --interval: alles wat het opgeloste model erover wist.
def cmd_dump(args: argparse.Namespace, data_dir: Path) -> int:
    if not args.snapshot:
        raise UsageError("dump requires --snapshot PATH")
    if args.interval is None:
        raise UsageError("dump requires --interval N")

    snapshot_path = _resolve_snapshot_arg(data_dir, args.snapshot)
    if not snapshot_path.exists():
        raise UsageError(f"Snapshot not found: {snapshot_path}")

    _ensure_day_ahead_importable()
    from dao.prog.day_ahead import DaCalc

    guard = _offline_guard() if args.offline else None
    try:
        with ReplayIO(snapshot_path, solver_threads=args.threads) as replay:
            dacalc = DaCalc(str(snapshot_path))
            dacalc._debug_capture_vars = True
            # calc_optimum() always returns None — on success and on every
            # failure path alike (day_ahead.py's own final line is an
            # unconditional `return None`; it communicates outcome via
            # self/notify/logging, not a return value). So the return value
            # here is not a usable success signal; the solved model's own
            # num_solutions/status, captured separately below via
            # ReplayIO's mip.Model.optimize() wrapper, is.
            dacalc.calc_optimum()
        model = replay._model
        registry = getattr(dacalc, "_debug_vars", None)
        meta = replay.meta
    finally:
        if guard is not None:
            _offline_unguard(guard)

    if model is None:
        raise UsageError(
            "replay never reached model.optimize() — nothing to dump "
            "(check the replay's own log output above for why)"
        )
    if getattr(model, "num_solutions", 0) == 0:
        raise UsageError(
            f"replay's model has no solution (status="
            f"{getattr(model.status, 'name', model.status)}) — nothing to dump"
        )
    if not registry:
        raise UsageError(
            "no variable registry was captured: day_ahead.py's hook imports "
            "'da_debug' as a bare module name, which only resolves once "
            "dao/prog is on sys.path — that should already be arranged by "
            "this CLI, so this points at a real problem, not a missing flag"
        )

    max_u = _max_known_interval(registry)
    if max_u >= 0 and not (0 <= args.interval <= max_u):
        raise UsageError(
            f"--interval {args.interval} is out of range for this run "
            f"(intervals 0..{max_u})"
        )

    timestamp, da_cons, da_prod = _lookup_price_at_interval(replay, meta, args.interval)
    header = {
        "dao_version": meta.get("dao_version"),
        "solver": getattr(model, "solver_name", None),
        "snapshot": str(snapshot_path),
    }
    if timestamp is not None:
        header["timestamp"] = timestamp.isoformat(sep=" ", timespec="minutes")
    if da_cons is not None:
        header["price_cons"] = round(da_cons, 4)
    if da_prod is not None:
        header["price_prod"] = round(da_prod, 4)

    data = dump_interval(model, registry, args.interval, header=header)
    _emit(args, data, lambda d: print(_format_dump_text(d)))
    return EXIT_OK


# Interne zelftest voor precies het scenario dat DaBase.get_state raakt: een geërfde, niet-eigen methode moet na restore weer via de klasse-hiërarchie lopen.
def _patch_list_restore_check() -> None:
    """The scenario that matters most: an attribute inherited via MRO
    (never owned by the class itself, like DaBase.get_state on hass.Hass)
    must be un-shadowed by delattr, not overwritten with a stale value."""

    class Base:
        # Triviale testmethode zonder eigen betekenis, alleen om patch en restore op te kunnen testen.
        def greet(self):
            return "base"

    class Owner(Base):
        pass

    patches = _PatchList()
    patches.set(Owner, "greet", lambda self: "patched")
    if Owner().greet() != "patched":
        raise AssertionError("patch did not apply")
    patches.restore()
    if "greet" in vars(Owner):
        raise AssertionError("inherited attribute was not correctly un-shadowed")
    if Owner().greet() != "base":
        raise AssertionError("patch did not restore correctly")


# Bouwt een klein maar structureel representatief 1-batterij/2-interval
# SOS2-laad/ontlaadmodel (dezelfde vorm als day_ahead.py's echte battery-
# sectie: ac_to_dc_w/ac_from_dc_w als SOS2-gewichten, soc als U+1-grens),
# lost het op, en geeft (model, registry) terug — gebruikt door meerdere
# A3-zelftests zodat die niet elk hun eigen kopie van de modelopbouw nodig
# hebben.
def _build_synthetic_sos2_model():
    from mip import Model, xsum, BINARY, CONTINUOUS, maximize

    B, U, CS, DS = 1, 2, 2, 2
    ac_to_dc_samples = [[0.0, 5.0]]
    dc_from_ac_samples = [[0.0, 4.5]]
    ac_from_dc_samples = [[0.0, 3.0]]
    dc_to_ac_samples = [[0.0, 3.3]]

    model = Model()
    ac_to_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=5) for _ in range(U)] for _ in range(B)]
    ac_to_dc_on = [[model.add_var(var_type=BINARY) for _ in range(U)] for _ in range(B)]
    ac_to_dc_w = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=1) for _ in range(CS)] for _ in range(U)] for _ in range(B)]
    ac_from_dc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=3) for _ in range(U)] for _ in range(B)]
    ac_from_dc_on = [[model.add_var(var_type=BINARY) for _ in range(U)] for _ in range(B)]
    ac_from_dc_w = [[[model.add_var(var_type=CONTINUOUS, lb=0, ub=1) for _ in range(DS)] for _ in range(U)] for _ in range(B)]
    dc_from_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=4.5) for _ in range(U)] for _ in range(B)]
    dc_to_ac = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=3.3) for _ in range(U)] for _ in range(B)]
    dc_from_bat = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=3.3) for _ in range(U)] for _ in range(B)]
    dc_to_bat = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=4.5) for _ in range(U)] for _ in range(B)]
    soc = [[model.add_var(var_type=CONTINUOUS, lb=0, ub=100) for _ in range(U + 1)] for _ in range(B)]

    for b in range(B):
        model += soc[b][0] == 50
        for u in range(U):
            model += xsum(ac_to_dc_w[b][u][cs] for cs in range(CS)) == 1
            model += xsum(ac_to_dc_w[b][u][cs] * ac_to_dc_samples[b][cs] for cs in range(CS)) == ac_to_dc[b][u]
            model += xsum(ac_to_dc_w[b][u][cs] * dc_from_ac_samples[b][cs] for cs in range(CS)) == dc_from_ac[b][u]
            model.add_sos([(ac_to_dc_w[b][u][cs], ac_to_dc_samples[b][cs]) for cs in range(CS)], 2)

            model += xsum(ac_from_dc_w[b][u][ds] for ds in range(DS)) <= 1
            model += xsum(ac_from_dc_w[b][u][ds] * ac_from_dc_samples[b][ds] for ds in range(DS)) == ac_from_dc[b][u]
            model += xsum(ac_from_dc_w[b][u][ds] * dc_to_ac_samples[b][ds] for ds in range(DS)) == dc_to_ac[b][u]
            model.add_sos([(ac_from_dc_w[b][u][ds], ac_from_dc_samples[b][ds]) for ds in range(DS)], 2)

            model += dc_from_ac[b][u] <= ac_to_dc_on[b][u] * 5
            model += ac_from_dc[b][u] <= ac_from_dc_on[b][u] * 3
            model += ac_to_dc_on[b][u] + ac_from_dc_on[b][u] <= 1

            model += dc_from_ac[b][u] + dc_from_bat[b][u] == dc_to_ac[b][u] + dc_to_bat[b][u]
            model += soc[b][u + 1] == soc[b][u] + dc_to_bat[b][u] - dc_from_bat[b][u]

    # Force interval 1 idle so a dump of it is a small, quiet contrast to
    # interval 0's forced full-power charge (mirrors the "idle interval ->
    # short binding-constraint list" check from the A3 testing section).
    model += dc_to_bat[0][1] == 0
    model += dc_from_bat[0][1] == 0
    model.objective = maximize(dc_to_bat[0][0])
    model.verbose = 0
    model.optimize()

    registry = build_var_registry(locals())
    return model, registry


# Draait alle offline zelftests van da_debug.py, zonder dat daar een live stack voor nodig is.
def cmd_selftest(args: argparse.Namespace, data_dir: Path) -> int:
    checks: list[dict] = []

    # Voert één zelftest uit en registreert of die geslaagd of mislukt is.
    def check(name, fn):
        try:
            fn()
            checks.append({"name": name, "ok": True, "error": None})
        except Exception as ex:  # noqa: BLE001 - reported, not raised
            checks.append({"name": name, "ok": False, "error": str(ex)})

    # Controleert dat een DataFrame exact wordt teruggelezen na _dataframe_to_payload gevolgd door _dataframe_from_payload.
    def _dataframe_roundtrip():
        df = pd.DataFrame(
            {
                "time": [dt.datetime(2026, 1, 1, 0, 0), dt.datetime(2026, 1, 1, 0, 15)],
                "value": [1.5, 2.5],
                "label": ["a", "b"],
            }
        )
        df.index = pd.to_datetime(df["time"])
        restored = _dataframe_from_payload(_dataframe_to_payload(df))
        if not restored.reset_index(drop=True).equals(df.reset_index(drop=True)):
            raise AssertionError("DataFrame did not round-trip exactly")

    # Controleert dat _call_key stabiel is voor gelijke argumenten en verschillend voor ongelijke.
    def _call_key_stability():
        k1, k2, k3 = _call_key(("a",), {}), _call_key(("a",), {}), _call_key(("b",), {})
        if k1 != k2 or k1 == k3:
            raise AssertionError("_call_key is not stable/discriminating")

    # Controleert dat _config_hash ordeonafhankelijk is en verschilt bij een andere waarde.
    def _config_hash_determinism():
        a = _config_hash({"x": 1, "y": [1, 2]})
        b = _config_hash({"y": [1, 2], "x": 1})
        c = _config_hash({"x": 2, "y": [1, 2]})
        if a != b or a == c:
            raise AssertionError("_config_hash is not order-independent/discriminating")

    # Controleert dat de geheimenlek-check afgaat op een geplant geheim en niets doet bij schone data.
    def _secret_leak_gate():
        try:
            _assert_no_secret_leak('{"x": "leak-me"}', ["leak-me"])
        except RuntimeError:
            pass
        else:
            raise AssertionError("leak gate did not fire on a planted secret")
        _assert_no_secret_leak('{"x": "clean"}', ["leak-me"])  # must not raise

    # Bouwt uit een geneste synthetische structuur de registry op en
    # controleert dat een bekende Var op het juiste containernaam+indexpad
    # terugkomt — dit is waar registry-bugs echt zitten (A1 Testing #2).
    def _var_registry_nested_containers():
        if mip is None:
            return  # mip not installed: nothing to test against
        model = mip.Model()
        flat = [model.add_var(var_type=mip.CONTINUOUS) for _ in range(2)]
        nested = [
            [[model.add_var(var_type=mip.BINARY) for _k in range(2)] for _j in range(2)]
            for _i in range(2)
        ]
        not_a_container = 3.14  # must be skipped, not walked
        registry = build_var_registry(locals())
        if registry.get(flat[1].idx) != ("flat", (1,)):
            raise AssertionError("flat container entry missing or wrong")
        if registry.get(nested[1][0][1].idx) != ("nested", (1, 0, 1)):
            raise AssertionError("nested container entry missing or wrong index path")
        if len(registry) != len(flat) + 8:  # 2 + 2*2*2
            raise AssertionError(f"unexpected registry size {len(registry)}")

    # Controleert dat de volledigheidscontrole afgaat op een containernaam
    # die niet in SHAPES/SHAPES_IGNORE staat (A3 Testing: "add a container
    # without updating SHAPES").
    def _shapes_completeness_fires_on_unknown_container():
        bad_registry = {0: ("mystery_container_nobody_declared", (0,))}
        try:
            _assert_shapes_complete(bad_registry)
        except VarRegistryError:
            pass
        else:
            raise AssertionError("completeness assertion did not fire on an unknown container")
        _assert_shapes_complete({0: ("soc", (0, 0))})  # must not raise on a known one

    # End-to-end: los het synthetische SOS2-model op en controleer dat
    # dump_interval op de dwangmatig ladende interval de juiste vermogens,
    # soc-in/out, en een aangrenzende actieve SOS2-trap teruggeeft, en dat
    # de gerenderde binding constraints geen "var(N)"-fallback bevatten
    # (d.w.z. dat elke variabele daadwerkelijk een registry-label kreeg).
    def _dump_interval_charging_interval():
        if mip is None:
            return
        model, registry = _build_synthetic_sos2_model()
        data = dump_interval(model, registry, 0, header={"dao_version": "selftest"})
        by_label = {e["label"]: e["value"] for e in data["sections"]["battery 0"]}
        if abs(by_label["ac_to_dc[0][0]"] - 5.0) > 1e-6:
            raise AssertionError("charging interval did not reach full charge power")
        if abs(by_label["soc[0][0]"] - 50.0) > 1e-6 or abs(by_label["soc[0][1]"] - 54.5) > 1e-6:
            raise AssertionError("soc in/out did not match the forced charge")
        charge_curve = next(r for r in data["sos2"] if r["curve"] == "battery charge")
        if not charge_curve["adjacent"] or not charge_curve["active_stages"]:
            raise AssertionError("SOS2 charge curve should report one adjacent active stage")
        if abs(charge_curve["interpolated"] - by_label["ac_to_dc[0][0]"]) > 1e-6:
            raise AssertionError("SOS2 interpolated power should equal ac_to_dc[0][0]")
        if not data["binding_constraints"]:
            raise AssertionError("a forced-charge interval should have binding constraints")
        if any("var(" in bc["text"] for bc in data["binding_constraints"]):
            raise AssertionError("a binding constraint fell back to var(N) — a registered var wasn't labelled")
        if "-0" in _format_dump_text(data):
            raise AssertionError("rendered output contains a stray -0 (negative-zero formatting bug)")

    # Idle interval (dwongen tot 0 laden/ontladen): moet nog steeds netjes
    # dumpen zonder te crashen, en zonder een van de over-matching
    # symptomen (een lege binding-constraint-lijst zou juist verdacht zijn
    # geweest — hier moet de energie-balans/soc-koppeling nog steeds
    # binding zijn).
    def _dump_interval_idle_interval():
        if mip is None:
            return
        model, registry = _build_synthetic_sos2_model()
        data = dump_interval(model, registry, 1)
        by_label = {e["label"]: e["value"] for e in data["sections"]["battery 0"]}
        if abs(by_label["ac_to_dc[0][1]"]) > 1e-6 or abs(by_label["ac_from_dc[0][1]"]) > 1e-6:
            raise AssertionError("forced-idle interval should show zero flow")
        if not data["context"].get("0"):
            raise AssertionError("interval 1 should carry reduced context for its u=0 neighbour")

    for name, fn in [
        ("dataframe_roundtrip", _dataframe_roundtrip),
        ("call_key_stability", _call_key_stability),
        ("config_hash_determinism", _config_hash_determinism),
        ("secret_leak_gate", _secret_leak_gate),
        ("patch_list_restore", _patch_list_restore_check),
        ("var_registry_nested_containers", _var_registry_nested_containers),
        ("shapes_completeness_fires_on_unknown_container", _shapes_completeness_fires_on_unknown_container),
        ("dump_interval_charging_interval", _dump_interval_charging_interval),
        ("dump_interval_idle_interval", _dump_interval_idle_interval),
    ]:
        check(name, fn)

    ok = all(c["ok"] for c in checks)
    data = {"ok": ok, "checks": checks}

    # Toont per zelftest of die geslaagd is.
    def render(d):
        for c in d["checks"]:
            status = "ok" if c["ok"] else "FAIL"
            suffix = f": {c['error']}" if c["error"] else ""
            print(f"[{status}] {c['name']}{suffix}")
        print("selftest:", "PASS" if d["ok"] else "FAIL")

    _emit(args, data, render)
    return EXIT_OK if ok else EXIT_ASSERTION_FAILED


# -- argument parsing / entry point --------------------------------------


# Bouwt de gedeelde --data-dir/--json-opties, herbruikt door elk subcommando zodat de vlag zowel vóór als na het subcommando werkt.
def _common_parser() -> argparse.ArgumentParser:
    """--data-dir and --json need to work whether given before or after the
    subcommand name (`da_debug --json capture` and `da_debug capture --json`
    are both natural to type) — a plain top-level-only argument only accepts
    the former. Sharing this parent with every subparser accepts both."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir",
        default=None,
        help="Base data directory (default: <module dir>/../data, matching "
        "day_ahead.py's own convention). All other paths resolve from here.",
    )
    common.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    return common


# Bouwt de volledige CLI op met alle subcommando's en hun eigen opties.
def build_arg_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="python -m dao.prog.da_debug",
        description=(
            "Capture, replay, and inspect calc_optimum() debug snapshots. "
            "See dao_debug_replay_ci_architecture_v2.md for the design."
        ),
    )
    # --data-dir/--json are attached only to the subparsers (below), not
    # here. argparse's subparser namespace merge overwrites a top-level
    # flag's value with the subparser's own (unset) default for the same
    # dest, so attaching the same parent to both levels would silently
    # discard `da_debug --json capture` while `da_debug capture --json`
    # worked — better to support one position correctly than both flakily.

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("capture", parents=[common], help="Run a real optimisation; write snapshot + result.")
    p.add_argument(
        "--config",
        default=None,
        help="Path to options.json (default: <data-dir>/options.json). "
        "capture loads this directly, like an unwrapped run would — "
        "including any in-place config migration ConfigurationLoader "
        "performs. It is the only da_debug command that touches your real "
        "config file; every other command that reads a config does so via "
        "a disposable copy.",
    )
    p.add_argument("--out-dir", default=None, help="Where to write the snapshot (default: <data-dir>/debug_snapshots).")
    p.add_argument("--label", default=None, help="Optional label suffix for the snapshot filename.")
    p.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Same idea as day_ahead.py's own debug mode "
        "(calc_optimum_met_debug): sets self.debug = True before solving, "
        "which gates most writes, plus suppresses the few that aren't "
        "gated by that flag (self.notify(), one set_value() call — "
        "architecture doc §1.2). All reads still happen for real and are "
        "still captured. Use this while iterating so repeated captures "
        "don't keep pushing real settings to HA/DB. Unrelated to --png "
        "(see below) — that's controlled separately.",
    )
    p.add_argument(
        "--png",
        action="store_true",
        default=False,
        help="Keep the chart PNG day_ahead.py writes unconditionally to "
        "../data/images (regardless of --debug). Off by default — most "
        "capture runs don't need one and it's one more file per run — "
        "but a chart can help spot dispatch patterns a table doesn't.",
    )
    p.add_argument("--start-dt", default=None, help="ISO datetime, forwarded to calc_optimum(_start_dt=...).")
    p.add_argument("--start-soc", type=float, default=None)
    p.add_argument("--start-ev-soc", type=float, default=None)

    p = sub.add_parser("replay", parents=[common], help="Re-solve from a snapshot; needs no live HA/DB.")
    p.add_argument("snapshot", help="Snapshot file (bare filename resolves against <data-dir>/debug_snapshots/).")
    p.add_argument("--offline", dest="offline", action="store_true", default=True, help="Block all network access during replay (default).")
    p.add_argument("--allow-network", dest="offline", action="store_false", help="Disable the network block (escape hatch).")
    p.add_argument(
        "--png",
        action="store_true",
        default=False,
        help="Keep the chart PNG day_ahead.py writes unconditionally to "
        "../data/images. Off by default, same reasoning as capture --png.",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=-1,
        metavar="N",
        help="CBC thread count for the replayed solve (mip.Model.threads "
        "semantics: -1 = all cores, N = exactly N threads). Default -1. "
        "Use --threads 1 for bit-for-bit reproducibility — slower, and can "
        "hit day_ahead.py's fixed node cap (1500) before proving "
        "optimality on larger models, since single-threaded CBC explores "
        "far less of the tree per second than multi-threaded does. Any "
        "other value lets you compare solve time/quality across thread "
        "counts directly.",
    )
    p.add_argument(
        "--out-result",
        default=None,
        metavar="PATH",
        help="Where to write this replay's *.result.json (default: next "
        "to the snapshot, named <snapshot>.replay-threads<N>.result.json — "
        "distinct from the capture's own <snapshot>.result.json, and "
        "distinct per thread count so replays at different --threads "
        "don't overwrite each other). Compare with `diff`.",
    )

    p = sub.add_parser("inspect", parents=[common], help="Print snapshot meta and a content summary; no solve.")
    p.add_argument("snapshot")

    p = sub.add_parser("verify", parents=[common], help="Schema version, config hash, secret scan, integrity.")
    p.add_argument("snapshot")
    p.add_argument("--config", default=None, help="Optionally compare against a live options.json (copy-then-load; never mutates it).")
    p.add_argument("--secrets", default=None, help="Optionally scan the snapshot for literal secret values from this secrets.json.")

    p = sub.add_parser("diff", parents=[common], help="Compare two snapshots (inputs) or two .result.json files.")
    p.add_argument("first")
    p.add_argument("second")

    p = sub.add_parser("set", parents=[common], help="Derive a new snapshot with overridden entity state(s).")
    p.add_argument("snapshot")
    p.add_argument("--state", action="append", default=[], metavar="entity_id=value", help="Repeatable.")
    p.add_argument("--out", required=True)

    p = sub.add_parser("dump", parents=[common], help="Replay a snapshot and print everything the solved model knew about one interval.")
    p.add_argument("--snapshot", default=None, required=True)
    p.add_argument("--interval", type=int, default=None, required=True, metavar="U")
    p.add_argument("--offline", dest="offline", action="store_true", default=True, help="Block all network access during the replay this needs (default).")
    p.add_argument("--allow-network", dest="offline", action="store_false", help="Disable the network block (escape hatch).")
    p.add_argument(
        "--threads",
        type=int,
        default=-1,
        metavar="N",
        help="CBC thread count for the replay dump reads from (same semantics as `replay --threads`). Default -1.",
    )

    sub.add_parser("selftest", parents=[common], help="Run da_debug's own offline checks.")

    return parser


_COMMANDS = {
    "capture": cmd_capture,
    "replay": cmd_replay,
    "inspect": cmd_inspect,
    "verify": cmd_verify,
    "diff": cmd_diff,
    "set": cmd_set,
    "dump": cmd_dump,
    "selftest": cmd_selftest,
}


# Toont een fout consistent in tekst of JSON, met traceback, vlak vóór de bijbehorende exitcode wordt teruggegeven.
def _print_error(args: argparse.Namespace, kind: str, ex: Exception) -> None:
    import traceback

    if getattr(args, "json", False):
        print(json.dumps({"error": kind, "message": str(ex)}, default=str))
    else:
        print(f"{kind}: {ex}", file=sys.stderr)
    traceback.print_exc()


# Entry point: parseert de argumenten, kiest het commando en vertaalt uitzonderingen naar de juiste exitcode.
def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    data_dir = _resolve_data_dir(args)

    handler = _COMMANDS[args.command]
    try:
        return handler(args, data_dir)
    except SnapshotMiss as ex:
        _print_error(args, "snapshot-miss", ex)
        return EXIT_SNAPSHOT_MISS
    except HermeticityViolation as ex:
        _print_error(args, "hermeticity-violation", ex)
        return EXIT_HERMETICITY_VIOLATION
    except UsageError as ex:
        _print_error(args, "usage-error", ex)
        return EXIT_USAGE
    except VarRegistryError as ex:
        _print_error(args, "assertion-failed", ex)
        return EXIT_ASSERTION_FAILED


if __name__ == "__main__":
    sys.exit(main())
