# Tier C baselines

One `<scenario_id>.json` per scenario, holding the blessed objective value
that scenario's solve is compared against. See
[`docs/testing.md`](../../../../docs/testing.md) §3 for how Tier C is
checked, and [`docs/writing-scenarios.md`](../../../../docs/writing-scenarios.md)
§4 for the `objective_within_baseline` key that opts a scenario in.

- Written **only** by `python -m dao.prog.da_debug scenario-bless <ids>`,
  never by a normal `scenario-run`.
- A run with no baseline present reports Tier C as `PENDING` (not a
  failure), so first-time setup is not all-red.
- On a regression the runner prints the old value, the new value and the
  delta; a human decides whether to re-bless.
- Regenerate whenever the solver / `mip` / `cbcbox` version changes or
  `options_example.json` changes shape — a baseline is only meaningful
  against a known solver on a known model.

Not every scenario has one: only those whose `expect` sets
`objective_within_baseline`.
