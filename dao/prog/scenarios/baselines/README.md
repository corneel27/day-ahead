# Tier B baselines

One `<scenario_id>.json` per scenario, holding the blessed objective value
that scenario's solve is compared against.

- Written **only** by `python -m dao.prog.da_debug scenario-bless <ids>`,
  never by a normal `scenario-run`.
- A run with no baseline present reports Tier B as `PENDING` (not a
  failure), so first-time setup is not all-red.
- On a regression the runner prints the old value, the new value and the
  delta; a human decides whether to re-bless.
- Regenerate whenever the solver / `mip` / `cbcbox` version changes or
  `options_example.json` changes shape — a baseline is only meaningful
  against a known solver on a known model.

Empty until session **S2** adds Tier B.
