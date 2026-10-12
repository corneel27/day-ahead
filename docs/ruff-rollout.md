# Ruff introduction plan

## Objective and scope

Introduce a reproducible Python lint gate on `chore/introduce-ruff`, based on
`main` at `9be7c2fea7bd923f12e4d0420d2a0f367cc126ad`. Keep changes reviewable
in separate commits. Do not change solver objectives, scenario baselines,
release versions, dependencies used by the add-on, or live Home Assistant data.

The initial gate covers all repository Python sources, including the tracked
tests that are currently matched by `.gitignore`. Select `E4`, `E7`, `E9`, `F`,
`I`, `UP`, and `B` explicitly, target Python 3.12, and pin Ruff to 0.16.10.
Avoid changing the rule set automatically when Ruff defaults change.

## Steps and acceptance criteria

1. **Record the plan and baseline.** Inspect repository instructions, workflows,
   supported Python version, and test isolation. Baseline: 94 Python files,
   511 diagnostics under the selected rules, 452 diagnostics with a fix that
   Ruff classifies as safe. These are lint findings, not a count of runtime bugs.
2. **Configure and perform mechanical cleanup.** Add `ruff.toml` and a separate
   pinned lint requirements file. Apply safe fixes only, inspect the diff for
   import side effects and runtime annotation changes, and keep this separate
   from manual behavior fixes. Do not use `--unsafe-fixes`.
3. **Review remaining findings and verify behavior.** Fix actual defects with
   targeted regression coverage. Make intentional behavior explicit (for example
   truncating `zip`), and use narrowly scoped, explained suppressions for required
   startup imports and framework patterns. Do not add a blanket legacy baseline
   or weaken the rules to hide remaining findings. Run configuration, scenario,
   query, EV schedule/harness, and isolated web route tests where supported.
   Compare failures against the unchanged base before attributing them to Ruff.
4. **Enable the gate and document contributor commands.** Add an independent
   GitHub Actions lint workflow for pushes and pull requests; it must not need
   the solver/database dependencies. Verify `ruff check .` exits successfully,
   confirm tracked test discovery, publish the branch and a draft pull request,
   and inspect the GitHub lint and existing scenario checks on the final commit.

## Follow-up: formatter

Full `ruff format` enforcement is deliberately a separate follow-up. The initial
measurement would reformat 87 of 94 files; keeping that churn out of the lint
introduction makes upstream merges and review easier. If adopted later, use one
mechanical formatting commit, rerun the behavioral tests, and then enable
`ruff format --check .`. Do not enable a knowingly failing formatter gate now.

## Verification record

- The configuration and cleanup are committed separately from reviewed fixes
  and CI wiring. The branch is available as [draft PR #1](https://github.com/patrickvorgers/day-ahead/pull/1).
- Ruff 0.16.10 passes with zero diagnostics. Discovery includes all 96 tracked
  Python files (the 94 original files plus two new regression modules); the
  additional discovered TOML file is not counted as Python. An undefined-name
  probe under the test path is rejected with `F821` and exit 1.
- Eight database-consumption and charging-schedule tests pass locally. The new
  per-call end-time test fails against the unchanged base method while the
  explicit-end test passes, demonstrating that it detects the original defect.
- GitHub checked the initial implementation at `10bbf50`: scenario validation
  passed, 12 solver-free tests passed (40 solve cases skipped in that unit job),
  and the separate solver job passed all 40 cases. The expanded regression gate
  found two pre-existing boiler round-trip failures, with 115 passes and 18
  optional MariaDB skips. Lint, model documentation and CodeQL were green.
- Both boiler failures reproduce in the unchanged base with the same Pydantic
  2.13.5 version: the default COP bypasses validation and remains a raw float,
  which the FlexFloat serializer cannot serialize. A separate fix enables
  validation of that single field's existing `3.0` default. Existing round-trip
  tests and an added default-value test now pass (77 model tests locally).
  The Windows model-only comparison bypassed the package initializer that
  eagerly imports the POSIX loader; model validation and serialization were
  real. It does not verify file locking, loader I/O or the full Linux stack.
- Final-head Linux results, including the rerun after the COP fix, are available
  in the PR's checks. Those checks run the real package initialization without
  the Windows comparison workaround. Optional MariaDB cases require a dedicated
  disposable database and remain skipped when it is not configured.

No live installation was used. The legacy live-data test script and EV harness
were not executed; the 40 hermetic scenarios cover EV planning instead. Loader
and example-file legacy tests are not newly gated by this rollout; configuration
coverage comes from scenario validation and the model/migration/round-trip tests.
Full formatting and making **Ruff lint** a required branch-protection check are
follow-ups; adding the workflow itself does not change repository protection.

## References

- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)
- [Rule selection and safe fixes](https://docs.astral.sh/ruff/linter/)
