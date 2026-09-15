"""JSON ``cases/*.json`` -> ``Scenario`` objects, with hand-rolled
validation (no ``jsonschema`` dependency — the shape is small and
``scenario validate`` in CI is the real gate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import KNOWN_EXPECT_KEYS, Scenario
from .vocabulary import VocabularyError, parse_start

_TOP_KEYS = {
    "id", "description", "start",
    "prices", "solar", "baseload", "temp", "heatpump_hours",
    "states", "config_patch", "options", "ev", "expect",
    "skip", "skip_reason",
}


class ScenarioLoadError(ValueError):
    """A cases file or one of its scenarios is malformed."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ScenarioLoadError(msg)


def parse_scenario(obj: dict, *, source_file: str = "") -> Scenario:
    _require(isinstance(obj, dict), f"scenario must be a JSON object, got {type(obj).__name__}")
    unknown = set(obj) - _TOP_KEYS
    _require(not unknown, f"unknown scenario key(s): {sorted(unknown)}")

    for k in ("id", "description", "start"):
        _require(k in obj and isinstance(obj[k], str) and obj[k],
                 f"scenario is missing required string field {k!r}")

    sid = obj["id"]
    try:
        parse_start(obj["start"])
    except VocabularyError as ex:
        raise ScenarioLoadError(f"[{sid}] {ex}") from ex

    prices = obj.get("prices", {})
    _require(isinstance(prices, dict) and "cons" in prices,
             f"[{sid}] prices must be an object with a 'cons' array")
    cons = prices["cons"]
    _require(isinstance(cons, list) and len(cons) >= 2
             and all(isinstance(x, (int, float)) for x in cons),
             f"[{sid}] prices.cons must be a list of >=2 numbers")
    prod = prices.get("prod")
    _require(prod is None or (isinstance(prod, list) and len(prod) == len(cons)),
             f"[{sid}] prices.prod, if given, must match prices.cons length ({len(cons)})")

    for arr_key in ("solar", "baseload", "temp"):
        v = obj.get(arr_key)
        _require(v is None or (isinstance(v, list) and all(isinstance(x, (int, float)) for x in v)),
                 f"[{sid}] {arr_key}, if given, must be a list of numbers")

    hph = obj.get("heatpump_hours", 0.0)
    _require(isinstance(hph, (int, float)), f"[{sid}] heatpump_hours must be a number")

    states = obj.get("states", {})
    _require(isinstance(states, dict), f"[{sid}] states must be an object")
    config_patch = obj.get("config_patch", {})
    _require(isinstance(config_patch, dict), f"[{sid}] config_patch must be an object")

    options = obj.get("options")
    _require(options is None or isinstance(options, str), f"[{sid}] options must be a string")

    ev = obj.get("ev")
    if ev is not None:
        _require(isinstance(ev, dict), f"[{sid}] ev must be an object")
        _require("target" in ev and isinstance(ev["target"], str) and ev["target"],
                  f"[{sid}] ev.target is required (e.g. 'golf', 'tesla')")
        other = ev.get("other")
        _require(other is None or isinstance(other, dict), f"[{sid}] ev.other must be an object")
        soc_plugin = ev.get("soc_plugin")
        _require(soc_plugin is None or (isinstance(soc_plugin, dict) and "name" in soc_plugin),
                  f"[{sid}] ev.soc_plugin must be an object with a 'name'")
        ready = ev.get("ready")
        _require(ready is None or isinstance(ready, (str, dict)),
                  f"[{sid}] ev.ready must be a string offset or a plugin object")
        other_ready = (other or {}).get("ready")
        _require(other_ready is None or isinstance(other_ready, (str, dict)),
                  f"[{sid}] ev.other.ready must be a string offset or a plugin object")

    expect = obj.get("expect", {})
    _require(isinstance(expect, dict), f"[{sid}] expect must be an object")
    unknown_expect = set(expect) - KNOWN_EXPECT_KEYS
    _require(not unknown_expect,
             f"[{sid}] unsupported expect key(s) {sorted(unknown_expect)}; "
             f"supported: {sorted(KNOWN_EXPECT_KEYS)} (the Tier A "
             f"invariants always run and are not listed here)")

    return Scenario(
        id=sid,
        description=obj["description"],
        start=obj["start"],
        prices_cons=[float(x) for x in cons],
        prices_prod=[float(x) for x in prod] if prod is not None else None,
        solar=[float(x) for x in obj["solar"]] if obj.get("solar") is not None else None,
        baseload=[float(x) for x in obj["baseload"]] if obj.get("baseload") is not None else None,
        temp=[float(x) for x in obj["temp"]] if obj.get("temp") is not None else None,
        heatpump_hours=float(hph),
        states={str(k): v for k, v in states.items()},
        config_patch=dict(config_patch),
        options=options,
        ev=dict(ev) if ev is not None else None,
        expect=dict(expect),
        skip=bool(obj.get("skip", False)),
        skip_reason=str(obj.get("skip_reason", "")),
        source_file=source_file,
    )


def load_cases_file(path: Path) -> list[Scenario]:
    try:
        raw = json.loads(Path(path).read_text())
    except json.JSONDecodeError as ex:
        raise ScenarioLoadError(f"{path.name}: invalid JSON — {ex}") from ex
    _require(isinstance(raw, list), f"{path.name}: top level must be a JSON array of scenarios")
    return [parse_scenario(obj, source_file=path.name) for obj in raw]


def load_cases_dir(cases_dir: Path) -> list[Scenario]:
    cases_dir = Path(cases_dir)
    scenarios: list[Scenario] = []
    for path in sorted(cases_dir.glob("*.json")):
        scenarios.extend(load_cases_file(path))
    seen: dict[str, str] = {}
    for s in scenarios:
        if s.id in seen:
            raise ScenarioLoadError(
                f"duplicate scenario id {s.id!r} (in {seen[s.id]} and {s.source_file})"
            )
        seen[s.id] = s.source_file
    return scenarios


# --- dotted-path config patching (salvaged from the untracked test_scenarios.py) ---

def set_dotted(tree: dict, path: str, value: Any) -> None:
    """Set ``a.b.c`` or ``a.b[0].c`` inside a nested dict/list structure —
    the sanitised-config shape. ``name[i]`` indexes a list."""
    parts: list = []
    for seg in path.split("."):
        while "[" in seg:
            head, rest = seg.split("[", 1)
            if head:
                parts.append(head)
            idx, seg = rest.split("]", 1)
            parts.append(int(idx))
            seg = seg.lstrip(".")
        if seg:
            parts.append(seg)
    node = tree
    for p in parts[:-1]:
        node = node[p]
    node[parts[-1]] = value
