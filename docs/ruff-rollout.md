# Plan for full Ruff support

## Goal

We want Python quality checks to be part of our normal development workflow:
feedback while editing, consistent local fixes, and the same checks on every
pull request. Lint and formatting failures should be resolved before merging,
and upgrades should follow a repeatable review process.

We want to adopt Ruff's standard stable lint rules and settings for the pinned
version, together with its default formatter settings. We will let Ruff supply
these defaults rather than maintain a custom rule selection or formatting style.
Version pinning keeps the adopted defaults reproducible.

Repository-specific configuration will be limited to necessary details such as
the supported Python version, source discovery and narrowly justified exceptions.
The current explicit rule selection is the completed introduction baseline;
moving to the standard defaults is still planned work.

For this repository, full Ruff support means a shared pinned configuration,
linting and formatting of all maintained Python sources and tests, documented
editor and pre-commit integration, and required CI checks supported by behavioral
tests.

We will introduce this in stages to keep review and upstream updates manageable.
The lint foundation is implemented. The remaining stages align it with Ruff's
standard defaults and add formatting, local tooling and required merge checks.

Formatting and lint adoption are separate tracks with separate commits and completion criteria. Formatting can be completed while lint findings are still being resolved. Group lint changes by their review and verification needs: import cleanup, code modernization and behavioral fixes each get their own batches.

## Definition of complete adoption

Ruff adoption is complete when all five stages are delivered on the target repository's default branch and:

- All maintained Python sources and tests pass `ruff check .` and `ruff format --check .` using Ruff's standard stable rules and default formatter settings.
- Local tools, pre-commit hooks and CI use the same pinned version and shared configuration, with documented reasons for necessary repository-specific settings.
- A new contributor can follow `DEVELOP.md` to set up the tools and reproduce the CI checks.
- Both lint and formatting are required merge checks, and a deliberate violation has demonstrated that the normal pull request workflow blocks merging until it is fixed.
- Relevant scenario and regression tests pass after the adoption changes.

Update this roadmap and the developer guide when completing a stage.

## Current status

| Area | Implemented now | Remaining work | Developer benefit |
| --- | --- | --- | --- |
| Shared configuration | Pinned Ruff version, Python target, custom explicit rules, separate lint requirements | Adopt standard stable rules/settings while retaining necessary repository details | Reproducible checks with less custom configuration |
| Lint coverage | All tracked Python files included in the existing lint gate | Resolve findings under Ruff's standard rules and maintain coverage | Common mistakes are detected using Ruff's supported defaults |
| CI | Independent **Ruff lint** job on pushes and pull requests | Require lint before merging | Automated feedback becomes merge protection |
| Formatting | Ruff is available; repository-wide formatting is not yet adopted | Apply the default formatter settings, format the code, add a CI check | Consistent layout and less style-review effort |
| Developer tools | Installation and lint commands documented in `DEVELOP.md` | Add editor guidance and pinned pre-commit hooks | Earlier feedback and fewer avoidable CI failures |

## Stage 1 — Establish the lint foundation

**Status: completed.**

`ruff.toml` holds our shared configuration. The version is pinned in
`requirements-lint.txt` and `required-version`; both must be updated together.
The Python target must match the supported application version. Ruff is a
development dependency, separate from the add-on runtime. See these files for
the current version and settings.

The following custom rule selection describes the implemented baseline. It will
be replaced by Ruff's standard stable selection in Stage 3.

| Rules | Purpose |
| --- | --- |
| `E4`, `E7`, `E9` | Import conventions, problematic statements and syntax errors |
| `F` | Undefined names, unused imports and other Pyflakes findings |
| `I` | Consistent import ordering |
| `UP` | Modern Python constructs for the supported version |
| `B` | Common mistakes and risky patterns detected by Bugbear |

We review lint findings for behavioral defects and add regression coverage when
fixes change application behavior. Safe automatic fixes still require diff
review. Exceptions must explain the behavior they preserve; for example, Flask
route-registration imports must run after the application is initialized.

**Completion criteria:** all maintained Python files are covered, the selected
lint rules pass, and the cleanup is verified by green behavioral checks.
These criteria are met for the lint foundation.

**What this adds:** automated detection of common Python mistakes, cleaner
imports and a reproducible starting point for the next stages.

## Stage 2 — Adopt default formatting

**Status: pending.**

### 2.1 — Assess the formatting diff

Use Ruff's default formatter settings and measure the diff on the current code. Review the scope and upstream merge impact. This step uses the formatter only; it does not apply lint fixes or rewrite application logic.

**Completion criteria:** the formatting scope is understood and the settings match the pinned version's defaults.

### 2.2 — Apply and verify formatting

Run `ruff format .` and commit the formatting as one separate mechanical change. Inspect the diff and run the existing lint gate and relevant scenario and regression checks. Keep import cleanup, modernization and behavioral fixes in separate commits.

**Completion criteria:** `ruff format --check .` passes across all maintained Python files, the existing lint gate passes, and verification finds no behavior changes.

### 2.3 — Enforce formatting in CI

Add `ruff format --check .` as a separate CI check with a clear, stable name. Verify that a formatting violation fails the check and that formatted code passes.

**Completion criteria:** CI reports formatting independently of lint and checks all maintained Python files.

**What this adds:** consistent layout and automatic detection of formatting drift, with a mechanical diff that can be reviewed independently of code changes.

## Stage 3 — Adopt standard stable lint rules

**Status: pending. This track can progress independently of formatting.**

### 3.1 — Assess standard-rule findings

Compare the current configuration with the standard stable defaults of the pinned Ruff version using a temporary assessment configuration. Keep the existing CI gate while collecting and classifying findings. Identify import cleanup, code modernization, possible behavioral defects and justified exceptions.

**Completion criteria:** findings are grouped into reviewable batches, with the required verification identified for each batch.

### 3.2 — Resolve findings in reviewable batches

- Review import cleanup for side effects and required initialization order before committing it.
- Keep code modernization separate from import cleanup and formatting; check supported Python versions and runtime uses of annotations or APIs.
- Address behavioral fixes individually with relevant regression coverage. Preserve scenario baselines unless a behavior change is explicitly reviewed.
- Keep exceptions narrow and explain the behavior they preserve. Treat any intermediate rule selection as temporary.

Apply safe fixes selectively and inspect their diffs. Run the existing lint gate after each batch and the tests appropriate to the affected behavior. Any adopted formatter check must continue to pass.

**Completion criteria:** each batch is independently reviewed and verified, and all findings under the standard rules are resolved or narrowly justified.

### 3.3 — Activate the standard lint rules

Remove the custom `lint.select` and unnecessary lint overrides once the standard checks pass across the repository. Retain version pinning, the supported Python target, source-discovery settings and justified exceptions. Verify that local and CI checks use the same standard stable selection.

**Completion criteria:** `ruff check .` passes under the pinned version's standard stable rules for all maintained Python files, with relevant behavioral checks passing and necessary overrides explained.

**What this adds:** adoption of Ruff's supported defaults through manageable changes, with code rewrites and behavior fixes visible to reviewers.

## Stage 4 — Integrate local developer tools

**Status: lint commands are documented; editor guidance and hooks are pending.**

1. Document editor setup for lint feedback and formatting using the repository
   configuration and pinned version.
2. Add `.pre-commit-config.yaml` with pinned Ruff lint and formatter hooks.
3. Document hook installation and full-repository local checks.
4. Verify that editor, hook and CI results agree on representative files.

Safe fixes can be applied locally, followed by diff review and relevant tests.
Behavioral changes require explicit review and regression coverage.

**Completion criteria:** a new contributor can follow the developer guide to
install the tools, receive editor feedback and reproduce CI results.

**What this adds:** developers catch and fix issues before pushing, reducing
avoidable CI failures and review turnaround.

## Stage 5 — Require checks before merging

**Status: lint runs automatically; required merge checks are pending.**

1. Configure the repository ruleset or branch protection to require **Ruff lint**
   for pull requests, using the existing CI check name.
2. After formatter adoption, require its formatting check as well.
3. Verify the settings with a temporary pull request containing a deliberate
   violation, then correct it and confirm the checks pass.
4. Document the check names and any intentional maintainer bypass policy.

**Completion criteria:** a failing required Ruff check prevents merging through
the normal contributor workflow.

**What this adds:** the clean baseline becomes an enforced convention with the
same protection for every contributor.

## References

- [Developer guide](../DEVELOP.md)
- [Scenario testing guide](testing.md)
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)
- [Ruff linting and fix safety](https://docs.astral.sh/ruff/linter/)
- [Ruff formatter](https://docs.astral.sh/ruff/formatter/)
- [Ruff integrations](https://docs.astral.sh/ruff/integrations/)
