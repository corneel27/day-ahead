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

Fill in actual results as the rollout proceeds. Local lint success does not imply
that solver or route tests passed, and synthetic scenarios do not verify live
device behavior. No live deployment is part of this rollout.

## References

- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)
- [Rule selection and safe fixes](https://docs.astral.sh/ruff/linter/)
