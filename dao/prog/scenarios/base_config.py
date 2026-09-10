"""The sanitised ``options_example.json`` config every scenario builds on.

``dao/data/options_example.json`` is the source of truth — it is kept
current as features land, carries ``"config_version": 2``, and validates as
a ``ConfigurationV2`` on its own (no migration). The runner loads it through
the real ``ConfigurationLoader`` on a disposable temp copy (defensive:
``ConfigurationLoader`` opens the file ``r+`` and would rewrite it if a
future version ever needed migrating).

Two run-time-only adjustments, applied to the sanitised dict, never to the
file on disk:

* ``homeassistant.hasstoken`` gets a dummy string — it is ``None`` in the
  example, which makes ``hassapi``'s constructor raise
  ``KeyError('HASS_TOKEN')``; replay never calls Home Assistant;
* ``solar[*].ml_prediction`` is forced ``False`` so solar production comes
  from the scenario's own array (via the ``calc_solar_predictions`` patch
  in ``runner.py``) rather than a trained model file.
"""

from __future__ import annotations

import copy
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

OPTIONS_EXAMPLE = Path(__file__).resolve().parents[3] / "dao" / "data" / "options_example.json"

DUMMY_HASS_TOKEN = "replay-dummy-token"


@lru_cache(maxsize=1)
def _sanitised_options_example() -> dict:
    from dao.prog.config.loader import ConfigurationLoader
    from dao.prog.da_debug import _sanitize_config

    tmp = Path(tempfile.mkdtemp(prefix="dao-scenario-cfg-")) / "options.json"
    shutil.copy(OPTIONS_EXAMPLE, tmp)
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


def base_config() -> dict:
    """A fresh deep copy of the sanitised ``options_example`` config, ready
    for per-scenario ``config_patch`` mutation."""
    return copy.deepcopy(_sanitised_options_example())
