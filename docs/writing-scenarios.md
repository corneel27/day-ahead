# Writing a scenario

A scenario is one JSON object in `dao/prog/scenarios/cases/*.json`. It holds
an hourly price array, optional solar, baseload and temperature arrays, a few
Home Assistant entity overrides, and a list of expectations. The runner turns
it into a synthetic snapshot and solves it hermetically (no database, no Home
Assistant, no wall clock). Then it checks the expectations.

This page is the field reference and the `expect` vocabulary. To run a
scenario, see [`testing.md`](testing.md). For how the pieces fit together, see
[`scenario-suite-architecture.md`](scenario-suite-architecture.md).

## 1. The minimal scenario

```json
{
  "id": "my-first-scenario",
  "description": "One line explaining what this proves",
  "start": "2026-01-14 00:00",
  "prices": { "cons": [0.22, 0.22, /* ...22 more hourly values... */] },
  "expect": { "solved": true }
}
```

`id` must be unique across the whole corpus. The loader checks this across
files, not only within one file. `start` is the frozen-clock anchor, in the
format `"YYYY-MM-DD HH:MM"`. It must fall on a 15-minute boundary (`07:00`,
`07:15`, not `07:07`), because every array is indexed from it. The horizon is
the number of hours in `prices.cons`. No separate horizon field exists.

## 2. Fields and their defaults

| Field | Default when omitted | Notes |
|---|---|---|
| `prices.cons` | *(required)* | €/kWh import, one value per hour |
| `prices.prod` | equals `prices.cons` | €/kWh export. Real feed-in tariffs are usually well under the import price. If the battery must prefer *storing* solar over *exporting* it, set this lower than `cons` (see §6) |
| `solar` | all zero | total house PV in kW, one value per hour (equal to kWh per hour slot). Split across the configured PV arrays by installed-capacity share |
| `baseload` | flat 0.25 kW | hourly kW. Real households have an evening bump. Set it explicitly if the battery or grid needs demand to discharge into (§6) |
| `temp` | flat 6.0 °C | hourly outside temperature. Feeds the heat pump's degree-days demand calculation (§7) and `prog_data.temp` |
| `heatpump_hours` | `0` | heat-pump run-hours history. With the config in `options_example.json` no scenario can reach it: `entity_heat_produced` is not configured, so day_ahead.py short-circuits before it calls `get_heatpump_run_hours` |
| `states` | `{}` | entity id → value, layered on top of the 28 entities in `scenarios/base_states.json` |
| `config_patch` | `{}` | dotted path → value, applied to the sanitised base config (§5) |
| `options` | `"options_example"` | or `"options_2ev"` for the two-EV cases |
| `ev` | *(none)* | EV shorthand block. The 24 cases in `cases/ev.json` show the full vocabulary, which this page does not cover |
| `expect` | `{}` | see §4 |

Every hourly array is upsampled ×4 onto the model's 15-minute grid. Always
write scenarios in hours, whatever the solver's own `interval` config says. An
array shorter than the horizon is a load-time error that says how many more
values it needs. A longer array is silently truncated.

## 3. A worked example

This is `price-negative-window` (`cases/price.json`), built the way you would
build a new scenario.

**Intent:** negative midday prices should make the battery hoard energy.

**First cut:**

```json
{
  "id": "price-negative-window",
  "start": "2026-01-14 00:00",
  "prices": { "cons": [/* ...flat 0.20, four hours of -0.06, flat 0.22... */] },
  "states": { "sensor.ess_battery_soc": "30" },
  "expect": { "solved": true, "battery_charges_during": { "start": "11:00", "end": "15:00", "min_kwh": 4.0 } }
}
```

`scenario-run price-negative-window --log` passed. The per-interval dispatch
(see the debugging tip in §8) showed a problem, though. The battery charged
and discharged in alternating 15-minute intervals through the window instead
of climbing steadily. This is the DC-side simultaneity looseness described in
[`testing.md`](testing.md) §3. Four straight hours of a flat, strongly
negative price form a plateau, where alternating dispatch costs exactly the
same as a clean charge.

**The fix was to the scenario, not the code.** A milder dip with some
variation (`-0.01, -0.03, -0.03, -0.01` instead of four times `-0.06`) gave
the solver a real gradient. The oscillation disappeared, and the battery
charged steadily from 21 % up to the 98 % cap. The lesson: a flat run of
several identical negative prices attracts plateaus. Vary the prices slightly
or keep negative blocks short.

**Picking the threshold.** The clean version charges 23.2 kWh into the
window. `min_kwh: 4.0` would have passed with either dispatch, so it checks
nothing. The committed version uses `min_kwh: 15.0`, about two-thirds of the
observed value. That is far enough below normal solver noise to stay stable,
and high enough to fail on a real regression, for example a change that halves
the battery's usable charge window. Read the real number off a passing run
before you pick a threshold. A threshold guessed low "to be safe" tests
nothing.

**Landing it.** Run `scenario-bless price-negative-window`. Then run
`scenario-run` twice more and confirm that the objective is byte-identical
both times.

## 4. The `expect` vocabulary

### Always on, never listed in `expect`

The **Tier A structural invariants** run on every scenario. You cannot turn
them off. They check:

- the success line and a real solution (the same check as `solved`)
- no AC-side simultaneous charge and discharge
- SOS2 adjacency on every stage curve
- every variable within its declared bounds
- SoC within limits
- at most one real EV charge stage per interval

[`testing.md`](testing.md) §3 explains why they are separate from the Tier B
case checks.

The **setup checks** also run automatically, whenever their own precondition
holds, in their own registry (`@setup_check`, `run_setup_checks()` — see
[`scenario-suite-architecture.md`](scenario-suite-architecture.md) §6). A
failure here means the scenario tests nothing, not that the behaviour is
wrong, so the report gives it a line of its own:

- **`overrides_were_read`** runs when the scenario has `states` overrides or
  an `ev` block. It fails if an override names an entity that the solve never
  read. This catches a misspelled or unconfigured entity id with a clear
  failure, not a confusing one further downstream.
- **`setup_echo_matches`** and **`no_duty_slivers`** run for `ev` scenarios.

### Tier B, case checks: keys you put in `expect`

| Key | Value shape | Reads | Semantics |
|---|---|---|---|
| `solved` | `bool` (default `true`) | log success line + a solution | |
| `objective_within_baseline` | `bool` (default `true` if a baseline exists, else `PENDING`) | `baselines/<id>.json` | Tier C, see testing.md §3 |
| `battery_charges_during` | `{"start": "HH:MM", "end": "HH:MM", "min_kwh": N}` | `dc_to_bat` | total kWh charged in the clock-time window ≥ `min_kwh` |
| `battery_discharges_during` | same shape, `min_kwh` | `dc_from_bat` | total kWh discharged in the window ≥ `min_kwh` |
| `battery_flat_during` | `{"start", "end", "max_kwh": N}` | both | combined charge and discharge activity in the window ≤ `max_kwh` |
| `heatpump_runs` | `{"start", "end", "runs": bool}` (`runs` default `true`) | `p_hp` | heat pump's summed power in the window is `>1 W` iff `runs` |
| `machine_runs_in_window` | `{"machine": "name", "start", "end", "runs": bool}` | `c_ma_u` | the named machine's consumption in the window is `>0` iff `runs` |
| `scheduled` / `other_scheduled` | `bool` | parsed EV log | EV-specific, see `cases/ev.json` |
| `reason_contains` | `str` | parsed EV log | substring of day_ahead.py's own Dutch reasoning |
| `partial_at_least` | `int` | parsed EV log | EV-specific |
| `min_duty_guard` / `wished_level_clipped` | `bool` | parsed EV log | EV-specific |

A window's `start` and `end` are plain clock times (`"HH:MM"`), resolved
against the scenario's own `start`. If `end` is at or before `start`, it rolls
to the next day. So `{"start": "00:00", "end": "00:00"}` means the whole
horizon, not an empty window. `heatpump-cold-day-runs` and
`battery-flat-no-incentive` use this to check the full day without computing
the clock time of the horizon's end.

The `machine` value is matched case-insensitively against
`config["machines"][*].name` (`"wasmachine"` and `"vaatwasser"` in
`options_example.json`). A numeric index also works. A name that does not
resolve fails with a message that lists the configured machines. It is never
a silent no-op.

**Old `min_kwh` on `heatpump_runs`.** Earlier versions of `heatpump_runs`
also required an undocumented `min_kwh` key to be falsy before they accepted
"the heat pump never ran because there was no heat demand". The minimal
`{"runs": false, "start": ..., "end": ...}` reported a false `FAIL`.
`expectations.py` no longer does this. If old scenario JSON or a bug report
mentions `min_kwh` on `heatpump_runs`, ignore it. The key never had an effect.

### Picking a window and a threshold

Every directional check is deliberately loose: "at least N kWh went in during
this window", never "0.834 kWh at interval 47". The model has plateaus of
alternative optima (§3 above and testing.md §3). An exact-schedule assertion
fails after a harmless solver, version or config change as often as after a
real regression. Make the setup (prices, states, config) unambiguous about
what should happen, then assert loosely that it did.

## 5. `config_patch`

`config_patch` maps a dotted path to a value. It applies to the **sanitised**
base config, not to the raw JSON file on disk. This is the same dict that
`base_config()` builds by loading `options_example.json` through the real
`ConfigurationLoader`. Two things cause most mistakes:

- **Keys are the Pydantic field names (snake_case), not the keys of the raw
  JSON.** The raw file says `"upper limit"`. The sanitised config, and so your
  `config_patch` path, uses `upper_limit`. To check a field name, run
  `python -c "from dao.prog.scenarios.base_config import base_config; print(base_config()['battery'][0].keys())"`.
- **Some fields wrap an HA entity or a literal, not a bare value.**
  `battery[0].upper_limit` is `{"value": 98}`, not `98`, because in the real
  config the field can also point at an HA entity. Patch
  `"battery[0].upper_limit.value"`, not `"battery[0].upper_limit"`. Plain
  fields such as `capacity` (`28.0`, a bare float) have no wrapper. If you are
  unsure, print the sanitised dict first.

`battery-small-capacity-charges` (`cases/battery.json`) is a worked example.
`{"battery[0].capacity": 6.0}` shrinks a 28 kWh battery to 6 kWh. The scenario
reuses the price shape of `price-negative-window` to show the same charging
behavior on a smaller asset.

## 6. `prices.prod` and `baseload`: set them when the scenario needs them

Two defaults are convenient, but they can remove the incentive that a scenario
is meant to test.

- If `prices.prod` stays at its default (`prices.cons`), storing solar and
  exporting it are worth the same before round-trip losses and cycle cost.
  After those costs, exporting immediately wins, and a "sunny bell should
  charge the battery" scenario shows no charging. `solar-bell-flat-prices`
  sets `prices.prod` to a flat `0.05` against a `0.30` `cons`, so storing
  clearly beats exporting. That is also closer to a real feed-in tariff gap.
- If `baseload` stays at its flat 0.25 kW default, local demand may be too
  low for a "discharges into an evening spike" scenario to produce a number
  worth asserting. `solar-bell-evening-spike` raises `baseload` to 1.2 kW for
  the three spike hours (cooking, lights, TV), so the discharge has somewhere
  to go. The first cut of that scenario, with the 0.25 kW default, discharged
  only about 0.78 kWh into the 3-hour window, because that was all the local
  demand there was.

## 7. Heat pump scenarios

`options_example.json` has `heating.heater_present: true`, but day_ahead.py
considers the heat pump only when `binary_sensor.heatpump_heating` reads
`"on"`. `base_states.json` defaults it to `"off"`, which matches every
scenario written before S4. To exercise the heat pump, set:

```json
"states": { "binary_sensor.heatpump_heating": "on" }
```

Demand comes from **degree-days**: `(16 − avg_outside_temp) × weight_factor ×
degree_days_factor`. It is zero, and the heat pump is forced off, whenever
`avg_outside_temp ≥ 16 °C`. The average is the mean of the scenario's own
`temp` array. It reaches the solve through the `avg_temperature` snapshot
channel in `da_debug.py`. The architecture doc (§5) explains why the channel
lives there and not in a scenario-suite patch. The same channel also makes real
`da_debug capture` and `replay` work for an installation with a heat pump.

Set `temp` clearly below or above 16 °C, depending on the branch you want to
test. `heatpump-cold-day-runs` uses a flat `-5.0`. `heatpump-mild-day-idle`
uses a flat `18.0`.

**A second requirement: the heating-curve offset entity.** With the heat pump
enabled and running, the write-back after the solve in day_ahead.py reads
`input_number.stooklijn_verschuiving_day_ahead`, the heating-curve calibration
offset that `options_example.json` configures. This entity was missing from
`base_states.json` until a scenario first reached this point. It is there now,
which makes 28 entities, up from 27.

If you add a heating or machine config field to `options_example.json` and a
heat pump scenario then raises `SnapshotMiss: entity 'X' is not present`, the
cause is the same. Add the entity to `base_states.json` with a neutral value,
as the other 28 were added.

## 8. Debugging a scenario that does not do what you expect

- `scenario-show <id>` confirms the resolved inputs before you spend solver
  time.
- `scenario-run <id> --log` writes the combined Python and CBC log. Search it
  for the Dutch reasoning lines from day_ahead.py.
- To see the per-interval dispatch (SoC, charge and discharge flows, machine
  on and off) and not only the verdict, write a short throwaway script. It
  loads the scenario, calls `runner.run_scenario`, and inspects
  `mv.items("dc_to_bat")` and similar. The case-check helpers in
  `expectations.py` (`_battery_flow_kwh`, `_window_range`) and
  `ModelView.items(container)` are the building blocks that the checks
  themselves use. This is how every threshold in the corpus was chosen (see
  §3).
- If a `states` entry seems to do nothing, check whether `overrides_were_read`
  failed. A failure means the solve never read the entity you overrode. The
  usual cause is a typo, or an entity that is not wired to the asset you
  think it configures.

## 9. Adding a case file

The suite picks up any `dao/prog/scenarios/cases/*.json` file automatically.
No registration list exists. Follow the shape of the existing files: a
top-level JSON array of scenario objects. After you add a file, run
`scenario-validate`. It catches a duplicate id or a malformed field in
milliseconds, with no solve.
