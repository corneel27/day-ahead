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
| CI | Independent **Ruff lint** job on pushes and pull requests | Required on the fork's main; configure the actual upstream merge target separately | Automated feedback becomes merge protection |
| Formatting | Ruff is available; repository-wide formatting is not yet adopted | Apply the default formatter settings, format the code, add a CI check | Consistent layout and less style-review effort |
| Developer tools | VS Code feedback and safe fixes on save, repeatable setup, pinned lint hook, local tasks and a published, verified fork-URL start page | Enable upstream publication; add formatting on save and a formatter hook during Stage 3 | Easier onboarding, earlier feedback and fewer avoidable CI failures |

## Stage 1 — Establish the lint foundation

**Status: completed.**

`ruff.toml` holds our shared configuration. The version is pinned in
`requirements-lint.txt` only. Developer tools derive an ignored `.ruff.toml` version guard from that pin; the local hook and editor use the same installation.
The Python target must match the supported application version. Ruff is a
development dependency, separate from the add-on runtime. See these files for
the current version and settings.

The following custom rule selection describes the implemented baseline. It will
be replaced by Ruff's standard stable selection in Stage 4.

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

## Stage 2 — Provide early developer feedback

**Status: lint support and browser onboarding are implemented, published and verified on the fork. Upstream publication remains. Formatter integration will follow Stage 3.**

Developers install the recommended Python and Ruff extensions and run the **Development: Set up Ruff** VS Code task. A repeatable cross-platform setup installs pinned tools in a dedicated environment, prepares the lint hook and checks the repository. Existing application environments and custom hook settings are preserved. See `DEVELOP.md` for installation, migration and troubleshooting.

Complete the new-developer start with a small browser page, following Home Assistant's approach:

1. The developer enters their fork URL and clicks **Open**.
2. VS Code clones the fork in a Docker volume and automatically prepares the development environment, extensions and Ruff tools.
3. The developer presses **F5** to start the web preview, with Ruff feedback and tests available immediately.

The fork-URL input page and its optional GitHub Pages workflow are implemented. Verification on the fork covered browser handoff, a clean Docker-volume installation, workspace trust, automatic extension installation, Ruff diagnostics and safe fixes on save, test discovery and F5 debugging with a working breakpoint. Enable publication on the upstream repository and update the page links when adopting it there. Keep publication settings, the detailed start procedure and the direct VS Code alternative in `DEVELOP.md`.

VS Code reports findings while editing and applies safe lint fixes and import organization on explicit save and Auto Save on focus/window change. The editor and local tasks use the pinned Ruff executable and shared filesystem configuration. The commit hook catches remaining findings before committing; CI remains the full-repository gate.

Workspace version monitoring reports missing or outdated tools when the folder opens and after a version change is pulled. A running editor server stops after a required-version change, and local checks and commits reject stale installations. Dependabot proposes weekly updates to the single Ruff pin; developers refresh their environment with the setup task and restart Ruff. Automatic workspace tasks must first be allowed in VS Code.

**Completion criteria:** setup succeeds from a clean checkout and can be repeated in an existing checkout; the Ruff language server, local CLI and hook agree on representative findings; safe fixes are applied before commit and an unresolved finding blocks the commit. Windows and Linux installation checks run in CI. Verify the VS Code save workflow using the developer guide when changing editor settings.

The browser onboarding is complete when a new developer can enter a fork URL on the published page, click **Open**, wait for automatic setup and press **F5**, with working Ruff feedback and tests and no manual installation commands.

**What this adds:** developers receive feedback during editing and saving, before the commit and CI checks. Adding later lint rules requires no separate editor rollout.

Formatter automation is completed with Stage 3: enable formatting on save and add the pinned formatter hook only when the repository formatting baseline and CI check are ready.

## Stage 3 — Adopt default formatting

**Status: pending.**

### 3.1 — Assess the formatting diff

Use Ruff's default formatter settings and measure the diff on the current code. Review the scope and upstream merge impact. This step uses the formatter only; it does not apply lint fixes or rewrite application logic.

**Completion criteria:** the formatting scope is understood and the settings match the pinned version's defaults.

### 3.2 — Apply and verify formatting

Run `ruff format .` and commit the formatting as one separate mechanical change. Inspect the diff and run the existing lint gate and relevant scenario and regression checks. Keep import cleanup, modernization and behavioral fixes in separate commits.

**Completion criteria:** `ruff format --check .` passes across all maintained Python files, the existing lint gate passes, and verification finds no behavior changes.

### 3.3 — Enforce formatting in CI

Enable Ruff formatting on save in VS Code and add the pinned `ruff-format` pre-commit hook. Add `ruff format --check .` as a separate CI check with a clear, stable name. Verify that a formatting violation fails the check and that formatted code passes.

**Completion criteria:** CI reports formatting independently of lint and checks all maintained Python files.

**What this adds:** consistent layout and automatic detection of formatting drift, with a mechanical diff that can be reviewed independently of code changes.

## Stage 4 — Adopt standard stable lint rules

**Status: the first local-simplification batch is enabled; the remaining standard lint rules are pending. This track can progress independently of formatting.**

See [the batch plan](ruff-batch-proposal.md) for the rule groups, implementation status and verification results. Each batch activates its rules in the shared configuration together with its corrections and acceptance checks.

### 4.1 — Assess standard-rule findings

Compare the current configuration with the standard stable defaults of the pinned Ruff version using a temporary assessment configuration. Keep the existing CI gate while collecting and classifying findings. Identify import cleanup, code modernization, possible behavioral defects and justified exceptions.

**Completion criteria:** findings are grouped into reviewable batches, with the required verification identified for each batch.

### 4.2 — Resolve findings in reviewable batches

- Review import cleanup for side effects and required initialization order before committing it.
- Keep code modernization separate from import cleanup and formatting; check supported Python versions and runtime uses of annotations or APIs.
- Address behavioral fixes individually with relevant regression coverage. Preserve scenario baselines unless a behavior change is explicitly reviewed.
- Keep exceptions narrow and explain the behavior they preserve. Treat any intermediate rule selection as temporary.

Apply safe fixes selectively and inspect their diffs. Run the existing lint gate after each batch and the tests appropriate to the affected behavior. Any adopted formatter check must continue to pass.

Activate each batch's rules in the shared `ruff.toml` in the same pull request as its corrections. VS Code, pre-commit and CI must adopt the rules together. Keep intermediate selections explicit until Stage 4.3; do not enable rules with unresolved findings unless the exceptions are narrow and justified.

**Completion criteria:** each batch is independently reviewed and verified, and all findings under the standard rules are resolved or narrowly justified.

### 4.3 — Activate the standard lint rules

Remove the custom `lint.select` and unnecessary lint overrides once the standard checks pass across the repository. Retain version pinning, the supported Python target, source-discovery settings and justified exceptions. Verify that local and CI checks use the same standard stable selection.

**Completion criteria:** `ruff check .` passes under the pinned version's standard stable rules for all maintained Python files, with relevant behavioral checks passing and necessary overrides explained.

**What this adds:** adoption of Ruff's supported defaults through manageable changes, with code rewrites and behavior fixes visible to reviewers.

## Acceptance criteria for every Ruff adoption pull request

Use this checklist for each formatting or lint adoption pull request. Record the results in its description, including the rule codes, affected files, checks performed and any justified exceptions. Mark a criterion as not applicable only with an explanation.

- [ ] The pull request identifies the adopted rules or formatter behavior and enables them in the shared configuration in the same change as the corrections. There are no separate editor-only rule selections.
- [ ] VS Code's actual Ruff server, the pre-commit launcher and CI use the version pinned in `requirements-lint.txt`. Compare effective settings for the same representative files: enabled rules, ignores, per-file exceptions, Python target and relevant formatter settings must agree. The generated `.ruff.toml` may add the version guard while extending the shared configuration.
- [ ] Isolated fixtures exercise representative violations of every newly adopted rule group. The editor reports the expected rule codes, the hook recognizes the violations, and the Ruff command used by CI reports the same codes. If the hook applies a safe correction, verify the corrected file and its successful recheck instead of expecting an identical diagnostic after correction. Keep these fixtures outside the maintained application sources.
- [ ] A real VS Code session shows the new diagnostics. When a safe fix is available, saving applies the expected correction; manual correction clears the remaining diagnostic. For formatting adoption, verify formatting on save, the formatter hook and `ruff format --check` against the same fixture.
- [ ] Corrected fixtures pass through all three integrations. Existing lint and any adopted formatting checks pass across all maintained Python sources and tests, including files that were not changed in the pull request. Confirm source discovery has not silently excluded maintained files.
- [ ] Relevant regression and scenario checks pass. Review behavior-sensitive changes separately from mechanical fixes, and preserve scenario baselines unless an intentional behavior change has been explicitly reviewed.
- [ ] Version, effective-settings and CLI/hook fixture checks are automated and reproducible. Record real-editor verification separately from command-line or language-server verification; do not report simulated editor checks as a successful VS Code save test.

Pre-commit normally checks changed files and can apply fixes; CI checks the complete repository without modifying it. Compare versions, configuration and rule behavior rather than requiring identical file scope or output. Isolated negative tests must assert the expected failure; they do not require leaving a failing CI run on the pull request.

## Stage 5 — Require checks before merging

**Status: lint and development checks are implemented in CI; required merge checks must be configured by the repository maintainer. Formatting enforcement remains pending.**

Require Ruff lint, both scenario jobs, both Windows/Linux developer-tool jobs and clean-install from GitHub Actions before merging. See the developer guide for the check names and clean-checkout manual acceptance checklist. Repository protection is configured in GitHub settings; merging the workflow files does not enable it. Maintainers choose any review requirements and intentional bypass policy.

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
