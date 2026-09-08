"""The sanitised ``options_example.json`` config every scenario builds on.

``dao/data/options_example.json`` is the source of truth (the plan's
decision — "the test scenario uses that file as options"). Two edits are
unavoidable before it validates / replays:

* its ``scheduler`` section is malformed and it carries no
  ``config_version`` — ``calc_optimum()`` never reads ``.scheduler``, so it
  is dropped and ``config_version: 2`` is set;
* ``homeassistant.hasstoken`` is ``None`` there, which makes ``hassapi``'s
  constructor raise ``KeyError('HASS_TOKEN')`` — replay never calls Home
  Assistant, so a dummy token string is injected.

``solar[*].ml_prediction`` is forced ``False`` so solar production comes
from the scenario's own array (via the ``calc_solar_predictions`` patch in
``runner.py``) rather than a trained model file.

Loaded through a disposable temp copy so ``ConfigurationLoader``'s in-place
migration rewrite never touches the repo file.
"""

from __future__ import annotations

import copy
import json
import tempfile
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
OPTIONS_EXAMPLE = _REPO_ROOT / "dao" / "data" / "options_example.json"

DUMMY_HASS_TOKEN = "replay-dummy-token"


@lru_cache(maxsize=1)
def _sanitised_options_example() -> dict:
    from dao.prog.config.loader import ConfigurationLoader
    from dao.prog.da_debug import _sanitize_config

    raw = json.loads(OPTIONS_EXAMPLE.read_text())
    raw.pop("scheduler", None)
    raw.setdefault("config_version", 2)

    tmp_dir = Path(tempfile.mkdtemp(prefix="dao-scenario-cfg-"))
    tmp = tmp_dir / "options.json"
    tmp.write_text(json.dumps(raw))
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
