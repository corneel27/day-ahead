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
editor and pre-commit integration, required CI checks, and an actively maintained
rule set supported by behavioral tests.

We will introduce this in stages to keep review and upstream updates manageable.
The lint foundation is implemented. The remaining stages align it with Ruff's
standard defaults and add formatting, local tooling, required merge checks and
a maintenance process.

## Current status

| Area | Implemented now | Remaining work | Developer benefit |
| --- | --- | --- | --- |
| Shared configuration | Ruff 0.16.10, Python 3.12 target, custom explicit rules, separate lint requirements | Adopt standard stable rules/settings while retaining necessary repository details | Reproducible checks with less custom configuration |
| Lint coverage | All tracked Python files included; zero findings under the current custom rules | Resolve findings under Ruff's standard rules and maintain the clean baseline | Common mistakes are detected using Ruff's supported defaults |
| CI | Independent **Ruff lint** job on pushes and pull requests | Require lint before merging | Automated feedback becomes merge protection |
| Formatting | Ruff is available; repository-wide formatting is not yet adopted | Apply the default formatter settings, format the code, add a CI check | Consistent layout and less style-review effort |
| Developer tools | Installation and lint commands documented in `DEVELOP.md` | Add editor guidance and pinned pre-commit hooks | Earlier feedback and fewer avoidable CI failures |
| Behavioral verification | Scenario and isolated regression checks are green for the foundation | Keep them green during later stages | Cleanup is checked against application behavior |
| Maintenance | Version and current rule selection are explicit | Define upgrade cadence, ownership and review of changes to standard defaults | Tooling improvements remain predictable |

## Stage 1 — Establish the lint foundation

**Status: completed.**

We have added `ruff.toml` and pinned Ruff to 0.16.10 in both
`requirements-lint.txt` and `required-version`. The configuration targets Python
3.12. Ruff is a development dependency, separate from the add-on runtime.

The following custom rule selection describes the implemented baseline. It will
be replaced by Ruff's standard stable selection in Stage 2.

| Rules | Purpose |
| --- | --- |
| `E4`, `E7`, `E9` | Import conventions, problematic statements and syntax errors |
| `F` | Undefined names, unused imports and other Pyflakes findings |
| `I` | Consistent import ordering |
| `UP` | Modern Python constructs for the supported version |
| `B` | Common mistakes and risky patterns detected by Bugbear |

We applied safe fixes and reviewed the remaining findings manually. Required
Flask startup imports retain their execution order with explained exceptions.
Existing truncating `zip` calls preserve their behavior; validated equal-length
inputs use `strict=True`.

The review fixed an undefined SQLAlchemy `Table` import, defaults that leaked
state or captured the time at import, and a pre-existing boiler COP serialization
defect exposed by the expanded tests. These fixes have regression coverage.

**Completion criteria:** all maintained Python files are covered, the selected
lint rules pass, and the cleanup is verified by green behavioral checks.
These criteria are met for the lint foundation.

**What this adds:** automated detection of common Python mistakes, cleaner
imports and a reproducible starting point for the next stages.

## Stage 2 — Adopt standard Ruff rules, settings and formatting

**Status: pending.**

1. Compare the current configuration with the standard stable defaults of the
   pinned Ruff version. Remove the custom `lint.select` and unnecessary overrides;
   retain only the version pin and justified repository-specific settings.
2. Run the standard lint rules, review any new findings, resolve them with safe
   fixes or reviewed changes, and rerun the relevant behavioral tests.
3. Use the default formatter settings: an 88-character line length, double quotes
   and four-space indentation. Let Ruff provide these values rather than
   duplicating them as custom overrides.
4. Measure the formatting diff on the current code. The initial assessment would
   change 87 of 94 Python files; remeasure before applying it.
5. Run `ruff format .` and commit the formatting as one separate mechanical change.
6. Review the diff and rerun lint, scenario and isolated regression checks.
7. Add `ruff format --check .` to CI with a clear, stable check name.

**Completion criteria:** the standard stable rules and default formatter settings
are in use; `ruff check .` and `ruff format --check .` pass for all maintained
Python files, with behavioral tests still green. Any remaining repository-specific
configuration has a documented reason.

**What this adds:** a standard configuration that contributors recognize, less
custom configuration to maintain, consistent layout and automatic detection of
lint and formatting drift. One formatting commit keeps review and upstream
merges manageable.

## Stage 3 — Integrate local developer tools

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

## Stage 4 — Require checks before merging

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

## Stage 5 — Maintain adoption of Ruff's standard defaults

**Status: version pinning is implemented; the maintenance process is pending.**

1. Review release notes when proposing an upgrade. Update both version pins and,
   once available, hook pins in the same pull request.
2. Run lint and formatting with the proposed version, review changed diagnostics
   and fixes, and rerun relevant behavioral checks.
3. Review changes to Ruff's standard stable rules and settings during each upgrade.
   Adopt the new defaults deliberately after resolving findings and verifying
   behavior; keep additional custom rules outside the standard adoption plan.
4. Keep exceptions narrow, explained and periodically reviewed.
5. Document upgrade cadence and ownership in the developer guide.

**Completion criteria:** upgrades and rule additions have a clear review path,
consistent versions across tools, and green lint, formatting and behavioral checks.

**What this adds:** code quality keeps improving while development-tool changes
remain predictable for contributors.

## Evidence for the completed foundation

The initial assessment found 511 diagnostics across 94 Python files under the
selected rules. Those findings included style and modernization suggestions as
well as actual defects; the number is not a count of runtime bugs.

The initial lint foundation was verified with:

- Zero Ruff findings across all 96 tracked Python files.
- An undefined-name probe correctly rejected with `F821` and exit 1.
- Scenario validation and 12 solver-free unit tests passing.
- All 40 solver scenarios passing against the existing baselines.
- 118 isolated Linux regression tests passing; 18 optional MariaDB cases skipped
  because a disposable test database was not configured.
- Successful model-documentation, CodeQL, amd64 and aarch64 build checks.

The end-time regression failed against the original method and passed after
the fix. Boiler serialization failures also reproduced on the unchanged base
with Pydantic 2.13.5 before their separate fix.

Later stages must be verified on their own commits. Our CI uses isolated data
and synthetic scenarios; live-installation scripts and the live EV harness are
outside this verification. Scenario and regression tests remain responsible for
verifying planning, queries and configuration behavior alongside Ruff.

## References

- [Developer guide](../DEVELOP.md)
- [Scenario testing guide](testing.md)
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)
- [Ruff linting and fix safety](https://docs.astral.sh/ruff/linter/)
- [Ruff formatter](https://docs.astral.sh/ruff/formatter/)
- [Ruff integrations](https://docs.astral.sh/ruff/integrations/)
