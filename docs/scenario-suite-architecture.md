# The scenario suite: how it works

## 1. Why this exists

`da_debug.py` started from a question that keeps coming back on Tweakers: "DAO does
X and I expected Y." The answer is always "post your log", and then an argument
follows about whether charging or discharging at time *t* was profitable.

`python da_debug.py capture` writes a full snapshot as JSON: prices, solar, HA
settings, everything the solver used for that run. Someone else runs `python
da_debug.py replay <snapshot>` and must reach exactly the same outcome, provided
`threads=1`, because a multithreaded solve is not deterministic. That makes the
argument reproducible.

`dump interval` is the other half. The output is still rough, but it prints every
value and constraint that mattered for one interval. Then you can see why the
battery did what it did. DAO does not think, which is what some users assume. DAO
calculates, and it can show the calculation.

The scenario suite came out of that. If I can capture and replay, I can also write
a scenario and replay it. Building a snapshot by hand turned out to be a lot of
work, and the machinery that grew out of it is what this page describes.

`dao/prog/scenarios/` is a declarative test suite for `DaCalc.calc_optimum()`, the
MIP solve at the core of `day_ahead.py`. Each scenario is a small JSON file: a
price curve, optionally a solar or temperature curve, a few Home Assistant entity
overrides, and a list of expectations. A runner turns the JSON into a fully
synthetic snapshot, a plain Python dict with the same shape as the ones that
`capture` produces from a real run, and replays it through the real, unmodified
`day_ahead.py` solve. Every database call, Home Assistant call and wall-clock read
is patched out. The solver itself is never mocked. The actual `mip`/CBC solve runs
on the actual constraint model every time.

To write a scenario, see [`writing-scenarios.md`](writing-scenarios.md). To run the suite, see
[`testing.md`](testing.md). This page describes the machinery underneath both.
Section 7 lists what the suite does not do.

At the moment of writing this document the scenario suite covers the following tests:

* Tier A: runs always 38/38 scenarios
* Tier B: tests 47 *check instances* across 34 scenarios.
* Tier C: Measures 14/38 scenarios

This results in the following tests:

* 3 basic (flat prices, no pv; cheap overnight; clear solar day)
* 2 price (negative window, evening spike)
* 24 EV
* 2 battery
* 2 solar
* 3 machines
* 2 heatpump

Use python da_debug.py scenario-list to get an overview of all implemented scenarios.


## 2. Design principles

**Synthetic, not captured.** Earlier tooling (`test_ev_harness_v6.py` and an
abandoned v1.0 of this suite) used captured fixtures: a snapshot of a real solve's
inputs, saved to a file. Capturing needs a live Home Assistant and database, so a
new test case became an operational task. This suite builds the snapshot dict in
Python from the JSON. Anyone can add a scenario with a text editor and no
infrastructure.

**One config, patched per scenario.** Every scenario starts from the committed
`dao/data/options_example.json`. The real `ConfigurationLoader` loads it, so the
schema check is the same as for a production config. A scenario-specific
`config_patch` covers any difference. The project keeps `options_example.json`
current as features land, and the add-on ships it as its own example. A scenario
therefore runs against the config shape of a real installation, which a bespoke
mock config per test would not give.

**Hermetic and deterministic.** A replay by someone else has to reach your number,
so the solve runs single-threaded by default. freezegun freezes the process clock,
`TZ=UTC` is pinned before `day_ahead` is imported (`_env.py`, see §4), and every
I/O channel is patched. The same scenario run twice must give a byte-identical
objective. Tier C (§6) is meaningless without this.

**`day_ahead.py` is never touched. `da_debug.py` only grows.** The suite must not
change `day_ahead.py`. To find out whether a PR touched the solver, a reviewer
checks the diff of that one file.

`da_debug.py` follows a different rule. It owns every `RecordingIO` and `ReplayIO`
channel (§5). The suite may *add* a channel there when a scenario reaches a DB or
HA call that nothing serves yet, as anyone extending real capture and replay would.
The `avg_temperature` channel in §5 is an example. The suite never changes the
behavior of an existing channel. It also never adds code to `da_debug.py` that only
makes sense for a synthetic scenario. That code goes in `runner.py` (§5 explains
where the line falls).

**Five groups of assertion, kept separate.** A structural invariant that holds for
any optimal solution, the intent of one scenario, and the claim that an exact
objective value is correct are three different claims, and a broken scenario is not
a claim about `day_ahead.py` at all. If they are mixed, the invariants need tuning
per scenario, or a scenario check stands in for a structural guarantee that it
cannot give. §6 covers this. 

## 3. End-to-end pipeline

One scenario, from JSON file to result:

1. **`loader.py`** parses one `cases/*.json` file into a list of `Scenario`
   dataclass instances (`model.py`). The validation is hand-written, with no
   `jsonschema` dependency. The shape is small enough that `scenario-validate` in
   CI is the real gate. An unknown top-level key or an unknown `expect` key is a
   hard error at load time.
2. **`base_config.build_config(scenario)`** loads `options_example.json` (or
   `options_2ev.json`) through the real `ConfigurationLoader`. It works on a
   **disposable temp copy**. The loader opens its file `r+` and would rewrite it in
   place if a config migration were ever needed, so the committed file is never
   touched. Two runtime-only adjustments apply to the loaded dict, never to the
   file:
   - `homeassistant.hasstoken` gets a dummy string. It is `None` in the example,
     which would make the `hassapi` constructor raise.
   - Every `solar[*].ml_prediction` is forced to `false`, so solar production comes
     from the scenario's own array and not from a trained model file.

   The scenario's `config_patch` (dotted path → value) is applied on top.
3. **`build_snapshot.resolve_ev(scenario, config)`** runs only if the scenario has
   an `ev` block. It expands the EV shorthand into concrete HA states and config
   patches, and mutates `config` in place for settings such as
   `ev.remove_stop_entity`. It returns the result separately, so the synthetic
   states and the post-solve EV checks (§6) share one resolved input. This page
   does not cover it further. See `ev.py` and the cases in `cases/ev.json`.
4. **`build_snapshot.build_snapshot(scenario, config, ev_states)`** builds the dict
   that `ReplayIO` replays:
   - price and prog DataFrames on the 15-minute grid, upsampled ×4 from the
     scenario's hourly arrays
   - `ha_states`: `base_states.json` merged with the scenario's `states` and any
     EV-expanded states
   - a fixed baseload dict
   - an `avg_temperature` channel (§5) for the heat pump's degree-days calculation
   - `ha_context`, with a fixed NL lat/lon. A scenario cannot override this part of
     the dict.
5. **`runner.run_scenario()`** opens `da_debug.ReplayIO(snapshot,
   solver_threads=1)` and adds one patch on top of `ReplayIO`'s own (§5). It then
   builds the real `DaCalc` and calls `calc_optimum(_start_dt=start)` inside a
   captured root logger. This is the actual solve, with the same MIP model and the
   same `mip`/CBC as a production run.
6. **Assertions** run against the result: the Tier A invariants always, then the
   setup checks whose precondition holds, then the Tier B case checks from
   `expect`, then the Tier C objective baseline (§6). The result is one
   `runner.ScenarioResult`: PASS, FAIL, INFEASIBLE, ERROR or SKIP.

## 4. File layout

```
dao/prog/da_debug.py             scenario CLI command handlers (list/show/validate/run/bless),
                                  lazy imports, so the package pulls in no pandas or mip;
                                  owns every RecordingIO/ReplayIO channel (§5)
dao/prog/scenarios/
  __init__.py                    load_all(), load(ids), the package's only public surface
  _env.py                        pins TZ=UTC before day_ahead is imported
  model.py                       the Scenario dataclass, KNOWN_EXPECT_KEYS
  loader.py                      JSON to Scenario, id uniqueness, set_dotted()
  vocabulary.py                  start parsing, hourly to 15-min upsample, window times
  base_config.py                 loads and sanitises options_example.json / options_2ev.json
  build_snapshot.py              Scenario to the synthetic ReplayIO dict
  runner.py                      run_scenario(), the solve plus the one extra patch (§5)
  modelview.py                   registry-indexed read access to the solved model
  expectations.py                Tier A invariants, the setup-check and case-check registries
  baseline.py                    Tier C objective baseline: load, write, compare
  parsing.py                     parse_ev_log, parse_solve_stats
  reporting.py                   Markdown and CSV report writer
  ev.py                          the `ev` block to states and config_patch
  plugins.py                     the @plugin registry (EV ready-time/SoC helpers)
  base_states.json               the entities options_example.json needs to solve at all
  options_2ev.json               options_example.json plus a second EV
  cases/*.json                   the corpus, one file per topic
  baselines/<id>.json            Tier C objective baselines, written by scenario-bless
dao/tests/prog/test_scenarios.py pytest wrapper, solver-free units plus gated solves
.github/workflows/ci.yml         unit job and scenarios job
docs/writing-scenarios.md        how to author a scenario
docs/testing.md                  how to run the suite
docs/scenario-suite-architecture.md   this document
```

## 5. The seams beyond `ReplayIO`'s own channels

`da_debug.ReplayIO` and `RecordingIO` already exist and back `da_debug capture` and
`replay`. They handle every DB, HA and network call that day_ahead.py makes, in one
of two ways:

- They serve the call from the snapshot dict (`price_data`, `prog_data`,
  `baseload`, `ha_states`, `config`, `ha_context`).
- They wrap the one leaf method that makes the call (`get_heatpump_run_hours`,
  `predict_solar_device`). `RecordingIO` calls the real implementation and records
  the result under a call key. `ReplayIO` serves the recording back. If a
  replay-time call was not captured, `ReplayIO` raises a `SnapshotMiss` that names
  the call.

This suite added one channel of this kind. The scenario runner adds one patch of
its own, for the one thing that only a synthetic scenario needs.

### `Meteo.get_avg_temperature`: a `da_debug.py` channel (`"avg_temperature"`)

Once the heat pump is enabled, day_ahead.py always calls
`self.meteo.calc_graaddagen(weighted=True)` in the heating block to get
degree-days. That method calls `Meteo.get_avg_temperature()`, which runs a live
SQLAlchemy query on the `prognoses` and `variabel` tables of the DA database. This
call is the same kind as `get_heatpump_run_hours` and `predict_solar_device`, which
already have channels, but it had none.

No scenario before had enabled the heat pump (it defaults to `"off"` in
`base_states.json`), and no real capture had exercised the path either.

The first fix patched `Meteo.get_avg_temperature` in `runner.py`. That made the
scenario suite work, but a real installation with a heat pump still crashed.
`da_debug capture` and `replay` never go through `runner.py`. The current fix
mirrors `get_heatpump_run_hours`:

- `RecordingIO` wraps `Meteo.get_avg_temperature`, calls the real implementation,
  and records the result under `_call_key(args, kwargs)`. The call can happen twice
  (once for "today" and once for "tomorrow" on a horizon longer than a day), so it
  uses the same keying as `get_heatpump_run_hours` and `get_calculated_baseload`.
- `ReplayIO` serves that recording back. If a replay-time call was not captured, it
  raises a `SnapshotMiss` that names the call. A real fixture captured before this
  fix, or a capture that never ran the heat pump, fails as loudly as any other
  under-captured channel.
- `build_snapshot.py` fills the same channel for a synthetic scenario
  (`_avg_temperature_channel()`, next to `_heatpump_hours_channel()`). It uses the
  mean of the scenario's own `temp` array, because no real capture exists to draw
  from. `runner.py` has no patch for this any more. `ReplayIO` serves the channel in
  the same way for a synthetic snapshot as for a real one.

### `DaBase.calc_solar_predictions`: a patch in `runner.py`

day_ahead.py normally calls a trained ML model to predict the production of each
solar array. `predict_solar_device`, the ML call one level below
`calc_solar_predictions`, already has a `da_debug.py` channel
(`solar_predictions`, recorded and replayed like the heat-pump channel). So real
capture and replay of a solar installation worked before this suite existed.

A synthetic scenario has no trained model file and no real capture that could have
recorded one. `options_example.json` sets `solar[*].ml_prediction: false` (§3),
which stops day_ahead.py from loading a model file. `runner.py`'s `_solar_patch`
replaces `calc_solar_predictions` itself. It returns the scenario's own `solar`
array, split across the configured PV arrays by installed-capacity share. This
patch belongs in `runner.py` because the scenario invents the PV production. No
recorded value exists that a real capture could have supplied.

The runner registers the patch right after `ReplayIO`'s own context manager opens:

```python
with da_debug.ReplayIO(snapshot, solver_threads=threads, png=keep_png) as replay:
    replay._patches.set(DaBase, "calc_solar_predictions", _solar_patch(scenario))
    dacalc = DaCalc(str(tmp_opts))
    dacalc.calc_optimum(_start_dt=start)
```

### Where the line falls

Add a channel to `da_debug.py` when a real capture could contain the value. Patch
in `runner.py` when the scenario invents data that a real installation could never
record. If a future scenario reaches a channel that `ReplayIO` does not serve, it
fails as the heat-pump gap did: a `SnapshotMiss` that names the missing call, never
a silent wrong answer. §8 describes how to close such a gap.

## 6. The assertion model

Five groups of check run against a solved scenario. They are kept apart because a
failure in each means something different:

- **Tier A, invariants:** always on, the author cannot disable them. A failure
  means the model is broken.
- **Setup checks:** run when their precondition holds. A failure means the
  scenario tests nothing.
- **Tier B, case checks:** author-selected. A failure means the behaviour or the
  expectation is wrong.
- **Tier C, objective baseline:** a failure means the number moved, which may be
  correct and needs a person to bless it.
- **Tier D, observations:** never fail.

The letters rank what a failure says about `day_ahead.py`. The setup checks have no
letter because they say nothing about `day_ahead.py`. Their subject is the
scenario.

**Tier A, invariants: `expectations.TIER_A_INVARIANTS`.** `Solved`,
`NoSimultaneousChargeDischarge`, `Sos2Adjacent`, `VarBoundsRespected`,
`SocWithinLimits`, `EvSingleRealStagePerInterval`, `EvChargeNonNegative`. Each
reads the solved model through `ModelView`, a thin registry-indexed view
(`by_container[name][index] -> var_idx`). `ModelView` is built from the same
variable registry that the debug-capture hook of `da_debug` produces. No check
parses log text. Tier A runs on every scenario and never appears in `expect`. A
scenario author cannot turn it off or weaken it. These are properties that the
model itself must satisfy for any optimum, whatever a scenario is trying to show.

**Tier B, case checks: `expectations._CASE_CHECKS`.** A `dict[str, Callable]`, filled by a
`@case_check("key")` decorator, with one function per `expect` key.
`run_case_checks()` dispatches to them. To add a key to the vocabulary, write a
function and decorate it. Also add the key to `model.KNOWN_EXPECT_KEYS`, because
the loader validates against that set. The dispatch mechanism and `runner.py` need
no change. Most checks read `ModelView`. The EV checks read the output of
`parsing.parse_ev_log`, because a scheduling decision, and day_ahead.py's Dutch
reasoning string for it, is not a model variable.

**Tier C, objective baseline: `objective_within_baseline`.** It compares the
objective with `baselines/<id>.json` and returns PASS, FAIL or PENDING
(`baseline.py`). A passing run never writes a baseline. Only `scenario-bless`, run
by a person, does. `testing.md` §3 gives the reasoning. It is dispatched through
the case-check registry, which is an implementation detail and not a statement
about which group it belongs to.

**Setup checks.** `overrides_were_read` fails if the overrides of a scenario
(`states`, or derived from `ev`) name an entity that the solve never read with
`get_state`. This is the SETUP_MISMATCH class of bug. For `ev` scenarios,
`setup_echo_matches` and `no_duty_slivers` also run. Each check runs whenever its
precondition holds (`states` is not empty, or an `ev` block exists), with no
`expect` key needed, and an author cannot skip one by leaving it out of `expect`.
They have their own registry (`@setup_check`, `run_setup_checks()`) and their own
field in `ScenarioResult`, so a report separates "this scenario tests nothing" from
"this behaviour is wrong". The two failures send a reader to different files.

A failed setup check does not stop the run: the Tier B case checks still execute against the same solve, and the report shows both the scenario's own "Setup checks: FAIL" line, and the case-check results next to it.

**Tier D, observations.** Never a failure. Today this is a place in the prose,
not a runtime check: nothing in the code computes or writes an observation
during a run, and `ScenarioResult` has no field for one. The DC-side
simultaneity case in §7 is the only entry, and this document is its only
record. If an actual per-run recording mechanism gets built, this section
should say what it writes and where a reader finds it — until then, "Tier D"
names an empty category, not a check that runs.

## 7. Known limitations and open items

**DC-side charge and discharge simultaneity is not constrained.** The Tier A check
`NoSimultaneousChargeDischarge` covers only the AC-coupled pair (`ac_to_dc_on` and
`ac_from_dc_on`). The DC-side pair `dc_to_bat` and `dc_from_bat` has no exclusivity
constraint in the current model. Under some price shapes (a flat, strongly negative
run of several hours), the solver can reach an equally optimal alternating dispatch
instead of a clean, steady one. Both dispatches cost the same, so Tier A correctly
does not fail here. By the taxonomy in §6 this is Tier D: a known, deliberate
looseness that the suite does not assert on. Nothing currently writes a per-run
record of it — this paragraph is the record. See `testing.md` §3. To close it,
someone must change the battery formulation in `day_ahead.py`, which is outside
the scope of this suite.

**`machine_runs_in_window` has no notion of shared capacity.** The check tests each
machine on its own. Neither the model nor the suite constrains the total
simultaneous household load. The "two machines competing for the same cheap slot"
scenario (`machines.json`) therefore shows that the solver handles two independent
scheduling problems in one solve. It does not show a resolved resource conflict. If
`day_ahead.py` gains a shared-capacity constraint across loads, this scenario must
change to exercise it.

**`heatpump_hours` and `get_heatpump_run_hours` are unreachable.**
`options_example.json` configures no `entity_heat_produced`. When that entity is
absent, `day_ahead.py` sets `run_hours = -1` before it calls
`report.get_heatpump_run_hours()`. The scenario field and its snapshot channel
(`build_snapshot._heatpump_hours_channel`) exist and work, but nothing in the
current config reaches them. This is not a bug. The code stays unused until
`options_example.json` configures that entity.

**`prices.prod` defaults to `prices.cons`.** This is a convenience, not a claim
about real tariffs, which usually pay less for export than they charge for import
(see `writing-scenarios.md` §6). A scenario that needs the gap sets it explicitly.
The default stays, because many scenarios (any that is not about export) are
simpler without it.

**`base_states.json` and `options_2ev.json` are agent-written, not taken from a
real installation.** The values in `base_states.json` (SoC levels, boiler
setpoints, machine programs, the heating-curve offset) are whatever made
`options_example.json` solve. They were found step by step: run a trivial scenario,
then add each entity that `ReplayIO` reported as missing. The Tesla in
`options_2ev.json` (capacity, charge curve, instant-charge entity ids) is a
constructed second EV, not a real car. Both fixtures only need to be internally
consistent, not realistic. Do not read either as documentation of what values a
real installation should use.

## 8. Extending the suite

- **A new scenario or case file:** see `writing-scenarios.md`. No registration step
  exists. The suite picks up any `cases/*.json` file.
- **A new `expect` key:** add it to `model.KNOWN_EXPECT_KEYS`. Write a
  `@case_check("key")` function in `expectations.py` that reads either `ModelView`
  or the parsed EV log. Document the value shape in `writing-scenarios.md` §4.
- **A scenario that needs a channel that nothing serves:** the failure is a
  `SnapshotMiss` that names what was called and on which object. The heat-pump gap
  in §5 is the template. Choose the fix by cause:
  - *A missing entity in `ha_states`:* add it to `base_states.json` with a neutral
    value. The file grows only when a scenario reaches a new part of the config,
    which is rare.
  - *A real method that touches HA or the DB:* add a `da_debug.py` channel.
    1. Add a `RecordingIO` wrap that calls the real implementation and records the
       result under `_call_key`.
    2. Add a matching `ReplayIO` serve that raises `SnapshotMiss` on a miss. Both
       mirror `get_heatpump_run_hours`.
    3. Fill the channel from `build_snapshot.py` for the synthetic case
       (`_avg_temperature_channel` is the template).

    This also fixes real `da_debug capture` and `replay`, not only the scenario
    suite, which is worth the extra file.
  - *Data that the scenario invents, with no real-capture equivalent:* patch in
    `runner.py` (`_solar_patch` is the template). A real installation could never
    have recorded this data.
- **Running and CI:** see `testing.md`.
