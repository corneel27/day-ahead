"""The sanitised base config every scenario builds on.

dao/data/options_example.json (name "options_example", the default) is the
source of truth for the single-EV corpus. It is kept current as features
land, carries "config_version": 2, and validates as a ConfigurationV2 on its
own, with no migration needed. options_2ev.json (name "options_2ev"), a
sibling of this file, is the same config plus a second EV, a Tesla, for the
two-car and Tesla-targeting EV cases that ask for it through the scenario's
"options" field. Either way the runner loads it through the real
ConfigurationLoader on a disposable temp copy, since ConfigurationLoader
opens the file r+ and would rewrite it in place if a future version ever
needed migrating.

Two run-time-only adjustments apply to the sanitised dict, never to the
file on disk. homeassistant.hasstoken gets a dummy string, because it is
None in the example and would make hassapi's constructor raise
KeyError('HASS_TOKEN'); replay never calls Home Assistant, so the dummy
value is never used for anything real. solar[*].ml_prediction is forced
False so solar production comes from the scenario's own array, through the
calc_solar_predictions patch in runner.py, rather than from a trained model
file.
"""

from __future__ import annotations

import copy
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

_DAO_DATA = Path(__file__).resolve().parents[3] / "dao" / "data"
_PACKAGE_DIR = Path(__file__).resolve().parent

OPTIONS_EXAMPLE = _DAO_DATA / "options_example.json"
OPTIONS_2EV = _PACKAGE_DIR / "options_2ev.json"

OPTIONS_SOURCES = {
    "options_example": OPTIONS_EXAMPLE,
    "options_2ev": OPTIONS_2EV,
}

DUMMY_HASS_TOKEN = "replay-dummy-token"


@lru_cache(maxsize=None)
def _sanitised_options(name: str) -> dict:
    from dao.prog.config.loader import ConfigurationLoader
    from dao.prog.da_debug import _sanitize_config

    try:
        source = OPTIONS_SOURCES[name]
    except KeyError:
        raise KeyError(
            f"unknown scenario options source {name!r}; known: {sorted(OPTIONS_SOURCES)}"
        ) from None

    tmp = Path(tempfile.mkdtemp(prefix="dao-scenario-cfg-")) / "options.json"
    shutil.copy(source, tmp)
    config_model = ConfigurationLoader(tmp).load_and_validate()

    san = _sanitize_config(config_model)
    san.setdefault("homeassistant", {})["hasstoken"] = DUMMY_HASS_TOKEN
    for sol in san.get("solar", []) or []:
        if isinstance(sol, dict):
            sol["ml_prediction"] = False
    for bat in san.get("battery", []) or []:
        for sol in bat.get("solar", []) or []:
            if isinstance(sol, dict):
                sol["ml_prediction"] = False
    return san


def base_config(name: str = "options_example") -> dict:
    """A fresh deep copy of the sanitised named config, ready for
    per-scenario config_patch mutation. name is a scenario's own "options"
    field (default "options_example")."""
    return copy.deepcopy(_sanitised_options(name))
