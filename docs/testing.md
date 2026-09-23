# Running the scenario suite

This page explains how to run the scenario suite. To write a scenario, see
[`writing-scenarios.md`](writing-scenarios.md). For how the pipeline fits
together, see [`scenario-suite-architecture.md`](scenario-suite-architecture.md).
Read it if a command here does something you do not expect. All commands
below were run against this repository. The output is pasted verbatim, except
that `No secrets file found` lines and absolute-path prefixes are removed.

## 1. Environment

The suite needs the real solver stack: `mip`, `cbcbox`, `pandas`, `pydantic`,
`freezegun`, and others. No venv is bundled, so build one:

```bash
python3 -m venv .venv-scenarios
.venv-scenarios/bin/python -m pip install --upgrade pip
.venv-scenarios/bin/python -m pip install \
  "mip==1.17.6" "cbcbox==2.929" pandas pydantic pydantic-settings pytz requests \
  hassapi python-dateutil freezegun sqlalchemy sqlalchemy-utils ephem \
  beautifulsoup4 matplotlib scikit-learn knmi-py entsoe-py nordpool xgboost
```

**`cbcbox` must be exactly `2.929`.** Version `2.935` aborts with SIGABRT
(glibc heap corruption) on this model. The `mip` version and everything else
are the same, so the `cbcbox` patch version alone causes it.
`dao/requirements.txt` already pins `2.929`. If you see
`ERROR while running Cbc. Signal SIGABRT caught`, run `pip show cbcbox` first.

Every command below assumes:

```bash
export PYTHONPATH="$(pwd):$(pwd)/dao/prog"
export TZ=UTC   # belt-and-suspenders; _env.py pins this in-process too
```

`da_debug.py` imports `pandas` at module level, so even `scenario-validate`
needs it. The CLI has no dependency-free subset. Only the pytest unit tests
that do not solve anything are light on dependencies (see §4).

## 2. The commands

All five commands run under `python -m dao.prog.da_debug`. Each accepts
`--data-dir` (default: `<repo>/dao/data`) and `--json` (machine-readable
output instead of the human-readable render). Both come from the shared
`_common_parser`.

### `scenario-list`

Lists every scenario in `dao/prog/scenarios/cases/*.json`. It does not solve.

```
$ python -m dao.prog.da_debug scenario-list
...
heatpump-cold-day-runs  24h  Heat pump enabled, zero solar, a cold flat -5C day - real heat demand, so it runs
heatpump-mild-day-idle  24h  Heat pump enabled but a mild 18C day - no heat demand (degree-days clamp to 0), so it never runs
machine-tight-window-must-run  24h  Vaatwasser (2h eco program) given a window that exactly fits it - it must run there even though cheaper hours exist outside the window
...
price-negative-window  24h  Negative midday prices, no PV - battery hoards the free energy
...

38 scenario(s).
```

### `scenario-show <id>`

Prints the resolved inputs and the full `expect` block of one scenario. It
does not solve, so use it to check what a scenario asks for before you spend
solver time on it.

```
$ python -m dao.prog.da_debug scenario-show price-negative-window
price-negative-window  —  Negative midday prices, no PV - battery hoards the free energy
  source     price.json
  start      2026-01-14 00:00   horizon 24 h
  prices.cons [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, -0.01, -0.03, -0.03, -0.01, 0.22, 0.22, 0.22, 0.22, 0.22, 0.22, 0.22, 0.22, 0.22]
  solar      (none — all zero)
  options    options_example (default)
  states
    sensor.ess_battery_soc = 30
  expect     {'solved': True, 'objective_within_baseline': True, 'battery_charges_during': {'start': '11:00', 'end': '15:00', 'min_kwh': 15.0}}  (+ the Tier A invariants, always)
  baseline   -3.283599  (/home/joost/Documents/Projects/day_ahead/day-ahead/dao/prog/scenarios/baselines/price-negative-window.json)
```

The `baseline` line appears only when the scenario has
`objective_within_baseline` in its `expect`. Most of the 24 EV cases do not,
so they show no such line. In the same way, `states` and `config_patch` print
only when they are not empty. Before the first `scenario-bless`, the line
reads `none yet — reports PENDING until 'scenario-bless <id>'` instead of a
number. The number is the last blessed value, not a live check.
`scenario-show` never solves, so it cannot tell you whether the scenario
passes Tier C now. It only shows what the scenario would be compared against.

An unknown id is a `UsageError` (exit 2), not a stack trace:

```
$ python -m dao.prog.da_debug scenario-show nope
usage-error: "unknown scenario id(s): ['nope']"
```

### `scenario-validate`

Checks that the corpus loads (unique ids, every field well-formed) and that
`base_states.json` parses. It also checks that `options_example.json` (and
`options_2ev.json`, if any scenario asks for it) builds through the real
`ConfigurationLoader`. It does **not** solve. CI runs this fast,
dependency-light gate on every push.

```
$ python -m dao.prog.da_debug scenario-validate
scenarios   38  (loaded, ids unique)
base_states 28 entities
validate: PASS
```

It fails in two ways, with different exit codes:

- **The corpus does not load** (duplicate id, malformed JSON, unknown key).
  A `ScenarioLoadError` is wrapped as `UsageError` and the exit code is **2**:

  ```
  $ python -m dao.prog.da_debug scenario-validate
  usage-error: scenario corpus does not load: duplicate scenario id 's1-flat' (in _demo_bad.json and example.json)
  ```

- **The corpus loads, but something behind it is broken.** Either
  `base_states.json` is not valid JSON, or `options_example.json` fails schema
  validation. The command prints a `PROBLEM` line and `validate: FAIL`, and
  exits **1** (`EXIT_ASSERTION_FAILED`):

  ```
  scenarios   38  (loaded, ids unique)
  base_states 0 entities
    PROBLEM: base_states.json: Expecting value: line 1 column 1 (char 0)
  validate: FAIL
  ```

### `scenario-run [ids...]`

Builds the synthetic snapshot for each scenario (all scenarios if you give no
ids) and solves it hermetically. It then runs Tier A, the setup checks, the
scenario's own `expect` case checks (Tier B), and the Tier C objective
baseline.

```
$ python -m dao.prog.da_debug scenario-run price-negative-window heatpump-cold-day-runs
[PASS] price-negative-window: Negative midday prices, no PV - battery hoards the free energy   objective -3.283599   solve 0.72s / 22 nodes / gap 0.00088063105
[PASS] heatpump-cold-day-runs: Heat pump enabled, zero solar, a cold flat -5C day - real heat demand, so it runs   objective 5.804758   solve 0.41s / 26 nodes / gap -6.2172489e-15

2/2 passed.
```

Solve time and node count are CBC's own search statistics. They vary a little
between runs and machines. The **objective** must be reproducible, and it is.

A failing case check names the exact number it saw. The next output comes
from raising `min_kwh` of `price-negative-window` to an unreachable `999.0`
for one run. That was a one-off edit, reverted right after, and it is not in
the committed scenario:

```
$ python -m dao.prog.da_debug scenario-run price-negative-window
[FAIL] price-negative-window: Negative midday prices, no PV - battery hoards the free energy   objective -3.283599   solve 0.73s / 22 nodes / gap 0.00088063105
        - [Tier B] battery_charges_during: 23.183 kWh charged in 11:00-15:00, wanted >= 999.0

0/1 passed.
needs a look: ['price-negative-window']
```

Flags:

- `--threads N`: passes `N` to the solver (`mip.Model.threads`; `-1` uses all
  cores). The default is `1`. A blessed baseline only means something if a
  re-run gives the same objective, and multi-threaded CBC does not guarantee
  that.
- `--log`: writes the combined Python and CBC log to
  `<data-dir>/scenario_reports/<id>.log` and prints the path. Use it to find
  out why a scenario fails (for example, day_ahead.py's own Dutch reasoning
  lines).
- `--png`: keeps the dispatch chart from day_ahead.py instead of discarding it.
- `--report`: writes a Markdown and CSV summary
  (`scenario_report_<timestamp>.md/.csv` and a `_latest` copy) through
  `reporting.write_reports`. CI publishes this to the job summary.
- `--json`: machine-readable output, used by CI and scripts. Without it you
  get the human-readable render shown above.

Exit code: `0` if every selected scenario is `PASS` or `SKIP`, otherwise
`EXIT_ASSERTION_FAILED` (`1`).

### `scenario-bless <id>...`

Writes (or overwrites) the Tier C baseline for the given scenario ids.
`scenario-run` never does this on its own (see §3 for the reason). The
command refuses to bless a scenario that does not currently `PASS`.

```
$ python -m dao.prog.da_debug scenario-bless price-negative-window
blessed price-negative-window: objective -3.283599 -> dao/prog/scenarios/baselines/price-negative-window.json
```

## 3. The assertion groups

Five groups of check run against a solved scenario, in this order: Tier A,
the setup checks, Tier B, Tier C, Tier D. Each means something different
when it fails, which is why they are kept apart instead of folded into one
pass/fail number.

**Tier A: structural invariants.** These hold for any optimal solution of
this model:

- The success line is present and a solution exists.
- No battery charges and discharges on the AC side in the same interval.
- Every active SOS2 weight pair is a single stage or two adjacent stages.
- Every variable stays inside its declared bounds.
- SoC stays inside its limits.
- An EV never runs two real charge stages in the same interval.

Tier A runs on **every** scenario and never appears in `expect`. A failure
means the model is broken. The invariants must hold even for a scenario with
no assertion of its own. They read the solved model through `ModelView`
(registry indices) and never read Dutch log text, so rewording a log message
does not break them.

**Setup checks: no letter.** `overrides_were_read` runs whenever a scenario's
`states` (literal or EV-derived) is not empty; `setup_echo_matches` and
`no_duty_slivers` run whenever the scenario has an `ev` block. Like Tier A,
none of them take an `expect` key, and an author cannot switch one off. A
failure means the scenario tests nothing — the override you set was never
read, or the log echo does not match what you asked for — which is a
different claim from "the model is broken" or "the behaviour is wrong". The
report gives them their own line for that reason. See
[`writing-scenarios.md`](writing-scenarios.md) §4.

**Tier B: `expect` case checks.** These state what a specific scenario is
for: "the battery charges during this window", "the heat pump runs", "this EV
gets scheduled". They are directional and loose on purpose. A failure means
the behaviour or the expectation is wrong. For the full catalogue, and for
why they check "at least 2 kWh went in" and not "0.834 kWh at interval 47",
see [`writing-scenarios.md`](writing-scenarios.md) §4.

The suite avoids exact-dispatch assertions everywhere. The underlying MIP has
plateaus of alternative optima: several schedules with the same or nearly the
same cost. A tight assertion on which interval something happened would fail
after a harmless change to the solver version, the thread count, or an
unrelated part of the config, with no real regression. A looser check on
economic behavior is easier to maintain and catches real bugs just as well.

**Tier C: `objective_within_baseline`.** Compares the solved objective with a
committed `baselines/<id>.json`, within the `max_gap` tolerance. It has three
states:

- `PENDING`: no baseline yet. This is not a failure, so a new scenario does
  not start red.
- `PASS`.
- `FAIL`: prints the old value, the new value, and the delta.

`scenario-run` only reads baselines. Only `scenario-bless`, run by a person,
writes one. A blessed baseline claims that this objective is the correct cost
for this scenario, not just a cost that one solve produced. That is a
judgement about the model's behavior, and a passing test run must not make it
about itself. If `scenario-run` blessed on green, a regression that moved the
objective the wrong way and still solved would rebaseline itself. Tier C would
then check nothing. `objective_within_baseline` is dispatched through the
same registry as the Tier B case checks, which is an implementation detail —
it is still Tier C.

**Tier D: observations, never fail.** Tier D records one known open item, and
nothing else today. The DC-side `dc_to_bat` and `dc_from_bat` pair (the
battery's charge and discharge power on the DC side) is **not** constrained
to be mutually exclusive in the current model. Tier A does check the
AC-coupled pair. Under a flat, strongly negative price, the solver can charge
and discharge in alternating intervals instead of charging steadily up to the
limit, and in practice it does. Both dispatches cost the same, so Tier A
correctly does not fail. This is a looseness in the model, not a wrong
answer. A four-hour flat `-0.06` block in the S4 corpus reproduced it.
[`writing-scenarios.md`](writing-scenarios.md) describes it in the gotchas
section, with advice on how to avoid it by accident.

The suite counts this case and does not fail it. To close it, someone must
change the constraints in `day_ahead.py`. That is out of scope here: the suite
only adds `da_debug.py` command handlers (§7 of `dao_scenario_suite_plan.md`).
It is also not settled whether the pair should be constrained at all.

## 4. Pytest wrapper (what CI runs)

`dao/tests/prog/test_scenarios.py` is a thin pytest wrapper. It has two parts:

- Solver-free unit tests for the loader, the vocabulary, and the plugin
  registry. These always run and take well under a second.
- One `test_scenario[<id>]` per corpus entry. Each calls the same
  `run_scenario()` as the CLI. It is skipped unless `mip` can be imported
  **and** `DAO_RUN_SCENARIOS=1` is set.

A machine without the solver still gets useful coverage.

```
$ pytest dao/tests/prog/test_scenarios.py -q                       # no solver needed
............ssssssssssssssssssssssssssssssssssssss                    [100%]
12 passed, 38 skipped in 0.07s

$ DAO_RUN_SCENARIOS=1 pytest dao/tests/prog/test_scenarios.py -q   # full solve, needs mip/cbcbox
..................................................                    [100%]
50 passed in 124.91s
```

The 38 skips are the `test_scenario[<id>]` tests for the 38 corpus
scenarios. The `_SKIP` reason names the fix: `set DAO_RUN_SCENARIOS=1`.

## 5. CI (`.github/workflows/ci.yml`)

Both jobs run on `[push, pull_request]`:

- **`unit`** installs `pytest pydantic pydantic-settings pandas`. `pandas` is
  needed because `da_debug.py` imports it at module level, although
  `scenario-validate` never uses a DataFrame. The job then runs
  `scenario-validate` and the solver-free pytest units. It takes under a
  minute.
- **`scenarios`** installs `dao/requirements.txt`, which pins
  `cbcbox==2.929`. **Do not loosen this pin in CI.** The job then runs
  `scenario-run --report`, with `timeout-minutes: 15` as a guard against a
  stuck solve. This job is the gate. It applies the same `PASS`-or-`SKIP`
  check as pytest's `test_scenario`, and it does more than report. CI
  publishes the Markdown report to the job summary. It uploads the whole
  `dao/data/scenario_reports/` directory as an artifact whether or not the job
  passes.

To reproduce the `scenarios` job locally:

```bash
pip install -r dao/requirements.txt
TZ=UTC python -m dao.prog.da_debug scenario-run --report
```

## 6. Adding a scenario to the corpus

1. Write the JSON (see [`writing-scenarios.md`](writing-scenarios.md)) in the
   matching `cases/*.json` file, or in a new file. The suite picks up any
   `.json` file under `cases/` automatically. No registration step exists.
2. Run `scenario-show <id>` to check the resolved inputs before you spend
   solver time.
3. Run `scenario-run <id> --log`. If `expect` is not yet satisfied, read the
   log. Change the scenario setup (price shape, starting SoC, window), not the
   assertion threshold, until the behavior is what you intended. Then pick a
   threshold safely below the observed value.
4. When the scenario `PASS`es and the objective looks sane, run
   `scenario-bless <id>` to write its Tier C baseline. Commit the baseline.
5. Run the full suite twice (`scenario-run`). Before you commit, confirm that
   the objective is byte-identical both times. A scenario whose objective is
   not reproducible with `--threads 1` makes Tier C flaky for everyone after
   you.
