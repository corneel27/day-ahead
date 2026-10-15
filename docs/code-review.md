# Introducing CodeRabbit PR reviews

CodeRabbit adds an automated first review to pull requests targeting the
repository's default branch. Its purpose is to help maintainers find new bugs,
compatibility problems, security regressions and meaningful test gaps earlier,
without making contributors responsible for cleaning up an entire legacy file.

For example, changing one battery calculation should receive feedback about
that calculation and its effects. It should not produce a list of unrelated
old naming, typing or documentation problems elsewhere in the file. Conversely,
if a new caller exposes a bug in an unchanged helper, that regression remains
in scope because the PR creates the problematic behavior.

This is supplementary feedback. Existing CI proves the behavior covered by its
checks, and maintainers decide whether findings are valid and whether to merge.
AI feedback can miss defects or flag harmless code. The scope instructions are
guidance, not an enforced filter that guarantees every comment falls on a new
line. Reading surrounding code is necessary to understand the submitted change.

## What is included

[`.coderabbit.yaml`](../.coderabbit.yaml) is the version-controlled review policy.
Configuration changes go through the same PR process as other repository work.

| Choice | Purpose |
| --- | --- |
| English reviews, `chill` profile | Useful, concise feedback for contributors and maintainers. |
| Automatic reviews on ready PRs | Give contributors feedback before a maintainer starts reviewing. |
| Incremental reviews on new pushes | Review subsequent changes without intentionally restarting the full review each time. |
| No automatic pause after five commits | Continue checking updates during longer PR discussions, subject to service limits. |
| Skip draft PRs | Let contributors prepare their work before requesting automatic feedback. |
| Compare findings with the PR base | Report only problems introduced, activated or worsened by the PR; no legacy cleanup lists. |
| Dependency-bump guidance | Ask for a targeted regression test when a concrete behavior or compatibility risk lacks coverage. |
| Separate Ruff integration disabled | Keep the repository's pinned Ruff CI as the lint authority. |
| Docstring-coverage warning disabled | Avoid imposing a new coverage target on touched legacy code. |
| Summary in the walkthrough comment | Keep the author's PR description intact. |
| Label and reviewer suggestions/assignment disabled | Keep the rollout focused on review feedback. |
| Approval workflow and author-approval commands disabled | Preserve the existing independent review process. |
| Code-writing finishing touches and post-merge actions disabled | Maintainers apply reviewed fixes with GitHub-verified commits. |

CodeRabbit can still suggest code in comments. Applying a suggestion is a
separate maintainer/developer action; verify the resulting commit's signature
on GitHub. An existing LTS or dependency upgrade still needs its normal tests.

## Previous usage and deployment status

The introduction check found no existing CodeRabbit configuration or setup
documentation on `main`, no history for `.coderabbit.yaml` on `main`, and no
CodeRabbit activity in the inspected recent comments, reviews and checks.
This is therefore a new documented integration, rather than a change to an
observed existing review workflow. Those observations do not prove that the
GitHub App was never installed: only the owner can confirm its installation
and selected repositories in GitHub settings.

Adding this configuration does **not** install or authorize the app. Repository
configuration can be validated before activation; actual bot behavior requires
the administrator steps and live acceptance checks below.

## Administrator setup

`corneel27/day-ahead` belongs to the personal GitHub account `corneel27`.
Corneel must perform the app-installation step for that account; collaborator
Write access alone is insufficient. GitHub review and merge requirements also
remain in effect for the configuration PR.

1. Review and merge the introduction PR after its checks pass. This puts the
   documented policy on the default branch before normal automatic use.
2. In GitHub account **Settings → Applications → Installed GitHub Apps**, check
   whether CodeRabbit is already installed and whether `day-ahead` is selected.
   If it is absent, use the [official GitHub App](https://github.com/apps/coderabbitai)
   or [CodeRabbit setup](https://docs.coderabbit.ai/platforms/github-com).
3. Choose **Only select repositories**, select `corneel27/day-ahead`, inspect
   GitHub's requested permissions, then install/authorize or save. The app
   requests write permissions for features beyond reviews as well; disabling
   those features in YAML does not reduce the installed app's permissions.
4. In CodeRabbit, verify the repository is enabled and eligible for the
   [free public-repository offer](https://www.coderabbit.ai/oss). No paid add-on
   or usage-based continuation is needed for this rollout; leave those off.
   The service's fair-use/rate limits still apply.
5. Keep `.coderabbit.yaml` as the policy source rather than maintaining a
   different copy of its settings in the dashboard. Check that no global
   override replaces this policy. During installation, skip the optional
   immediate review until the effective configuration has been checked.
6. Keep current branch protections and required human reviews. Do not make
   CodeRabbit a required merge check during the initial rollout, enable its
   approval workflow, or grant it bypass access. Its feedback is advisory.
7. Complete the acceptance checks below, including a representative dependency
   PR. Record the PR links and whether the observed feedback matches the scope.

The GitHub App needs access to code, PRs and checks to analyze changes and post
reviews. Its requested workflow-write permission supports agent repair features;
ordinary reviews do not require changing this repository's workflow files.
The complete, current permission list is shown by GitHub during installation
and described in the official setup guide linked above.

## GitHub Actions and workflow changes

**No new Actions workflow, API key, repository secret or custom runner is
required for this hosted GitHub App integration.** No existing workflow needs
modification for the initial rollout. The app receives PR events directly and
publishes its own review/check; adding a second review action would duplicate it.

| Existing workflow | Role after introduction |
| --- | --- |
| `.github/workflows/lint.yml` | Continue running the pinned Ruff version and repository rules. |
| `.github/workflows/ci.yml` | Continue solver-free tests, application/database regressions and synthetic solver scenarios. |
| `.github/workflows/developer-tools.yml` | Continue Windows/Linux tooling and hook validation. |
| `.github/workflows/development-environment.yml` | Continue clean installation, application checks and browser regressions. |
| `.github/workflows/test_build.yaml` | Continue application image builds for amd64 and aarch64. |
| `.github/workflows/codeql.yml` | Continue GitHub's security analysis. |
| Documentation, Pages and release workflows | Continue their existing triggers and behavior. |

Do not increase any workflow's `GITHUB_TOKEN` permissions or add a
`pull_request_target` workflow for CodeRabbit. Fork PR reviews are handled by
the app; the existing CI retains its own fork/approval rules.

## Activation and acceptance checks

Repository-file/schema validation is separate from live service validation.
The following are administrator follow-ups, not checks completed merely by
merging the configuration:

- [ ] The app installation includes `corneel27/day-ahead`, and the public-repo
  offer is confirmed without paid add-ons.
- [ ] On a PR carrying the policy, comment `@coderabbitai configuration` and
  inspect the effective YAML: instructions, incremental reviews, draft setting,
  disabled Ruff/docstring gate and disabled code-writing features must match.
  For an older branch, ensure it carries the current policy before using it as
  the acceptance example. Do not assume an old PR has picked up the new settings.
- [ ] A new ready-for-review PR targeting the default branch receives an
  automatic review. Draft PRs are skipped until marked ready.
- [ ] A subsequent signed commit receives an incremental review. Confirm that
  existing reported findings are not needlessly repeated.
- [ ] On a small change in a legacy file, feedback stays tied to new or worsened
  problems. Unrelated old style, docstring and typing gaps are not listed.
- [ ] On a dependency PR, the review considers compatibility and missing
  behavior coverage, without demanding unrelated cleanup or superficial tests.
- [ ] Existing CI and human approval requirements still apply. No CodeRabbit
  auto-fix commit, approval, reviewer reassignment or label change is produced.

Use real, reviewable changes for acceptance; do not merge an intentionally
introduced defect just to demonstrate a bot finding. A single successful review
also does not prove the AI will always follow the scope instructions.

For an existing PR, request feedback with `@coderabbitai review` after checking
its configuration. This is an incremental request; `@coderabbitai full review`
explicitly starts a full review. Do not trigger the entire open PR backlog at
once during rollout.

## Handling noise and pausing reviews

Validate each finding against the actual change and its base branch. If a
comment is unrelated legacy debt, explain that it predates the PR, resolve it
as appropriate, and refine the instructions through a follow-up PR if it recurs.
Keep the first few reviews advisory and inspect their usefulness before changing
any merge requirements.

To pause one PR, use `@coderabbitai pause`; use `@coderabbitai resume` to resume.
To pause repository-wide, change `reviews.auto_review.enabled` to `false` through
a PR. For an immediate stop, the owner can remove this repository from the app's
GitHub installation or suspend/uninstall the app. Existing CI continues to run.

See the official [configuration reference](https://docs.coderabbit.ai/reference/configuration),
[configuration precedence](https://docs.coderabbit.ai/guides/configuration-overview)
and [automatic review controls](https://docs.coderabbit.ai/configuration/auto-review).
