# Developer Guide for Day Ahead Optimizer

This guide will help developers set up their development environment, test changes locally, and contribute to the project.

## Table of Contents

- [VS Code quick start](#vs-code-quick-start-recommended)
- [Prerequisites](#prerequisites)
- [Setting Up Development Environment](#setting-up-development-environment)
- [Project Structure](#project-structure)
- [Running the Application Locally](#running-the-application-locally)
- [Testing](#testing)
- [Making Contributions](#making-contributions)
- [Code Style and Best Practices](#code-style-and-best-practices)

---

## VS Code quick start (recommended)

Install Git, Docker (Docker Desktop on Windows/macOS) and VS Code with the **Dev Containers** extension. On Windows, enable Docker Desktop's Linux containers/WSL 2 backend. Docker must be running; host Python and Node installations are not needed for this route.

1. Clone your fork and open the repository root in VS Code.
2. Choose **Dev Containers: Reopen in Container**. The container provides Python 3.13, Node 22 and native database build dependencies. Its first-time setup creates `.venv`, installs application/test dependencies, builds frontend assets, and installs the shared Ruff tools and commit hooks in `.venv-tools`.
3. Select `.venv/bin/python` with **Python: Select Interpreter** if an existing workspace selection overrides the default. Run **Ruff: Restart Server** and allow automatic tasks in this trusted folder for the Ruff version watcher.
4. Press **F5** with **Day Ahead: web preview** selected. Open `http://localhost:5000`. The debugger builds frontend assets first and supports Python and Jinja breakpoints.
5. For the calculation core, select **Day Ahead: debug synthetic scenario** and press **F5** to run one scenario with breakpoints. Open **Testing** for isolated unit/regression tests, or run **Tests: Solve all synthetic scenarios** from **Terminal > Run Task** for the solver corpus.

The preview uses `.local/web-data` with example options, empty secrets and empty image/log directories. Setup preserves existing preview edits and never copies credentials from `dao/data`. It is an empty web preview, not a simulated production dashboard: reports and live tasks require a separately configured installation. Synthetic scenarios exercise planning independently of Home Assistant and databases. Existing `dao/data` files are not changed by setup.

After pulling dependency changes, run **Development: Set up environment**. Changes to the container image require **Dev Containers: Rebuild Container**. Setup is repeatable; restart Ruff after tooling changes. Do not reuse a Windows `.venv` inside Linux: use a separate Linux checkout or explicitly recreate that environment. Existing hooks are preserved according to the Ruff setup instructions below.

For frontend live reload, start **Development: Frontend live reload**, then add `"VITE_DEV": "1"` to a personal copy of the web debug configuration. Port 5173 is forwarded alongside Flask. The default F5 configuration uses built assets and needs no second server.

**Native Linux/WSL alternative:** install Python 3.12+ (3.13 matches the container), Node 22.12+, Git, a compiler, pkg-config and MariaDB development libraries. From the repository root run `python3 scripts/setup_environment.py`, then open VS Code and select `.venv/bin/python`. On Debian/Ubuntu the native libraries can be installed with `sudo apt-get install build-essential pkg-config libmariadb-dev`. Application support is Linux/WSL; the separate Ruff-only setup also supports native Windows.

### Automatic installation verification

The **Development environment** workflow builds the actual Dockerfile, runs the same setup used by the Dev Container from a clean checkout, checks Python dependency integrity and Ruff version, validates scenarios, renders the real web preview with built frontend assets, repeats setup, then runs isolated regression tests and all synthetic scenarios. It runs on pushes, pull requests, and weekly to catch changed base images or dependency resolution even without a code change. Dependency upgrade PRs therefore exercise the complete installation route.

Locally, run **Development: Verify environment** for the smoke checks. CI verifies the installation and application startup; extension installation, actual VS Code interactions, breakpoint stopping and browser appearance still require a manual clean-checkout check.

## Prerequisites

Choose one application development route:

| Route | Requirements | Support |
| --- | --- | --- |
| Dev Container (recommended) | Git, Docker with Linux containers, VS Code and Dev Containers | Linux application environment; Docker Desktop hosts on Windows/macOS |
| Native Linux/WSL | Python 3.12+ with venv/pip, Node 22.12+, Git, compiler, pkg-config and MariaDB development libraries | Same setup and checks as the container; Python 3.13 matches the container |
| Ruff only | Git and Python 3.12+ | Windows and Linux tooling are checked in CI; this does not install the application or solver |

Native Windows/macOS application installation is not part of the supported setup. Use the Linux Dev Container on those hosts. macOS Ruff tooling is not covered by the current CI matrix.

## Setting Up Development Environment

### Shared application setup on Linux/WSL

Clone your fork and work from the repository root. On Debian/Ubuntu, install the native build prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libmariadb-dev python3-venv
```

Install Python 3.12+ and Node 22.12+ using your distribution or their supported installation methods; check their versions before continuing. Other Linux distributions need equivalent compiler and MariaDB development packages.

Run the same setup and verification used inside the Dev Container:

```bash
python3 scripts/setup_environment.py
.venv/bin/python scripts/verify_environment.py
```

Setup creates the application/test environment in `.venv`, builds frontend assets with `npm ci`, prepares the isolated preview and installs Ruff/hooks in `.venv-tools`. Select `.venv/bin/python` in VS Code. Repeat setup after dependency changes; it preserves existing preview files. Do not share a virtual environment between Windows and Linux checkouts.

For Ruff-only work, use the [Ruff setup instructions](#set-up-automatic-feedback-in-vs-code) below. For application or solver work, use the complete setup above.

### Existing installations and the legacy launcher

`dao/run/run_dev.sh` remains a legacy alternative for an already configured installation. It uses `venv/day_ahead`, prepares files in `dao/data` and starts Vite alongside Flask. Its `--setup` route does not provide the shared developer-tool installation and clean-install verification. New contributors should use the Dev Container or shared Linux/WSL setup above.

Do not mix those environments in one development session. Keep the legacy route for existing workflows until it can be migrated separately.

### Installation troubleshooting

If MariaDB Connector/C or mysqlclient cannot build, check the compiler, pkg-config and MariaDB development libraries. Use the pinned `mip` and `cbcbox` from `dao/requirements.txt`; the old manual `mip==1.16rc0` workaround and custom solver-library overrides are obsolete for the supported setup.

Do not remove dependencies or override Python compatibility to force installation. Use the Dev Container and report the failing setup step, operating system and Python/Node versions.

---

## Project Structure

```
day-ahead/
├── dao/                          # Main application directory
│   ├── prog/                     # Core application logic
│   │   ├── day_ahead.py          # Main entry point
│   │   ├── da_config.py          # Configuration management
│   │   ├── da_prices.py          # Price fetching logic
│   │   ├── da_meteo.py           # Weather data integration
│   │   ├── da_scheduler.py       # Optimization scheduler
│   │   ├── da_report.py          # Reporting functionality
│   │   ├── da_graph.py           # Graph generation
│   │   ├── db_manager.py         # Database management
│   │   └── utils.py              # Utility functions
│   ├── webserver/                # Flask web application
│   │   ├── da_server.py          # Flask server entry point
│   │   ├── gunicorn_config.py    # Production server config
│   │   └── app/                  # Flask application package
│   │       ├── __init__.py       # Flask app initialization
│   │       ├── routes.py         # Web routes/endpoints
│   │       ├── static/           # Static assets (CSS, JS)
│   │       └── templates/        # HTML templates
│   ├── data/                     # Runtime data and configuration
│   ├── tests/                    # Test files
│   └── requirements.txt          # Python dependencies
├── setup.py                      # Package setup configuration
└── README.md                     # User documentation
```

---

## Running the Application Locally

### Running the Flask Web Server

The Day Ahead Optimizer includes a Flask-based web interface for configuration and visualization.

#### Start the isolated preview

In VS Code, select **Day Ahead: web preview** and press **F5**. This builds assets and starts Flask inside the selected Linux environment. The UI and solver run as processes inside the Dev Container; no second application container is started. The development image includes extra tooling and does not replace production-image validation.

For a terminal-only start, after shared setup, run from the repository root:

```bash
source .venv/bin/activate
export PYTHONPATH="$(pwd):$(pwd)/dao/prog"
export DAO_WEB_DATA_DIR="$(pwd)/.local/web-data"
export MPLBACKEND=Agg
export TZ=UTC
unset VITE_DEV
cd dao/webserver
python -m flask --app app run --host 127.0.0.1 --port 5000
```

For a remote container, F5 binds Flask to all container interfaces and the Dev Container forwards port 5000. If the host port is occupied, select another forwarded local port in VS Code's **Ports** view.

#### Debug one calculation scenario

Select **Day Ahead: debug synthetic scenario** and press **F5**. Enter one scenario ID; the default is `battery-flat-no-incentive`. List available IDs from the repository root:

```bash
PYTHONPATH=.:dao/prog .venv/bin/python -m dao.prog.da_debug scenario-list
```

Set a breakpoint in `dao/prog/scenarios/runner.py` inside `run_scenario`, or in `dao/prog/day_ahead.py` inside `calc_optimum`. The launch runs one synthetic scenario with one solver thread, captures logs and writes a report under `dao/data/scenario_reports`. It needs no Home Assistant or database credentials. Continue execution to inspect the scenario's PASS/FAIL result. It does not update scenario baselines.

Use **Day Ahead: debug test** through the Testing view to debug an individual isolated test. Use **Tests: Solve all synthetic scenarios** for the full solver corpus.

#### Build or serve the assets

If you want to change or update the stylesheets or js dependencies, it is recommended to run 
the Vite server. Mind setting the VITE_DEV env in the step when starting the Python server.

```bash
cd dao/webserver
npm run vite-serve
```

If you just want to work on the Python codebase, you can build the assets:

```bash
cd dao/webserver
npm run build
```

#### Developing on a remote machine

Running the code on a server, NAS or VM and opening the web interface from your
laptop works without extra configuration: the page requests the Vite assets from
the same host you typed in the address bar, and Vite advertises its own address
for anything it generates itself (the icon fonts, for instance).

What you do have to arrange:

- **Port 5173 must be reachable** from your browser. Vite listens on all
  interfaces, but the firewall of the development machine has to allow it.
- **When you use a hostname** instead of an IP address, add it to
  `VITE_DEV_ALLOWED_HOSTS`. Vite rejects unknown `Host` headers to protect against
  DNS rebinding, and only sends the CORS headers that let the page read the assets
  to known origins. IP addresses and `localhost` are always accepted.

  ```bash
  export VITE_DEV_ALLOWED_HOSTS=dao.local
  ```

- **When you tunnel the port over SSH**, the page is served on `localhost` and the
  auto-detected Vite address is the LAN address of the server, which the browser
  may not be able to reach. Pin both sides to `localhost`:

  ```bash
  ssh -L 5000:localhost:5000 -L 5173:localhost:5173 user@dev-machine
  export VITE_DEV_HOST=localhost   # for the Vite server
  ```

If you only work on the Python code, skip the Vite server entirely: build the
assets once and start the webserver without `VITE_DEV`.

```bash
cd dao/webserver
npm run build
unset VITE_DEV
python -m flask --app app run --host 127.0.0.1 --port 5000
```

You lose hot reloading of stylesheets, which does not matter when only touching
Python.

#### Frontend environment variables

| Variable | Used by | Default | Purpose |
| --- | --- | --- | --- |
| `VITE_DEV` | webserver | unset | When `1`, load the assets from the Vite dev server instead of from `app/static/build`. |
| `VITE_DEV_PORT` | webserver, Vite | `5173` | Port of the Vite dev server. |
| `VITE_DEV_SERVER` | webserver | derived from the request | Pin the base URL the browser uses for the assets, for example `http://127.0.0.1:5173` behind a proxy. |
| `VITE_DEV_HOST` | Vite | first non-internal IPv4 | Address Vite advertises in the asset URLs it generates. |
| `VITE_DEV_ALLOWED_HOSTS` | Vite | empty | Comma separated hostnames Vite accepts, both as `Host` header and as the origin allowed to fetch the assets, besides `localhost` and IP addresses. |
| `FLASK_PORT` | webserver | `5000` | Port of the Flask development server. |


### Working with a configured installation

The isolated preview and synthetic scenarios are the default development workflow. Live price/weather APIs, Home Assistant tasks, database operations and populated reports require a separately configured installation.

Use [dao/DOCS.md](dao/DOCS.md) for application settings. Keep live credentials and data outside the disposable preview, select configuration paths deliberately, and use a dedicated test installation for changes that can write to Home Assistant or databases. The legacy `test_dao.py` and EV harness can access live data and are excluded from the isolated test commands below.

## Testing

From the repository root in the container or native Linux/WSL environment:

```bash
.venv/bin/python scripts/develop.py check
.venv/bin/python -m pytest -c pytest-dev.ini -q
PYTHONPATH=.:dao/prog TZ=UTC MPLBACKEND=Agg .venv/bin/python -m dao.prog.da_debug scenario-run --report
```

The pytest selection contains isolated unit/regression tests. Solver cases skipped there are exercised by the separate scenario command. Optional MariaDB cases require a dedicated disposable database and are currently skipped without it. See [docs/testing.md](docs/testing.md) for detailed test scope and results.

### Manual clean-checkout acceptance

Perform this check when changing setup, editor settings or debugger configuration. CI cannot demonstrate actual VS Code interaction or visible breakpoint stops.

- [ ] Open a fresh clone of the change branch with no pre-existing virtual environments in **Dev Containers: Reopen in Container**; allow setup to finish.
- [ ] Select `.venv/bin/python`, restart Ruff and allow the folder-open watcher. Confirm Ruff diagnostics appear in a temporary Python file, then remove the file.
- [ ] Launch **Day Ahead: web preview** with F5, open forwarded port 5000 and check the configuration/chart pages and built frontend assets.
- [ ] Set a Python route breakpoint and refresh the page; confirm the debugger stops, then continue.
- [ ] Launch **Day Ahead: debug synthetic scenario** with the default ID. Confirm a breakpoint inside `run_scenario` or `calc_optimum` stops; inspect variables, continue and confirm one passing scenario/report.
- [ ] Run **Tests: Isolated unit and regression tests**, **Tests: Solve all synthetic scenarios** and **Ruff: Check all Python files**.
- [ ] Repeat **Development: Set up environment** and **Development: Verify environment**. Confirm preview edits are preserved and startup still succeeds.

Record commit SHA, host OS/architecture, Docker/VS Code versions, results and any failure in the PR. An unchecked item is pending manual validation, not evidence of success.

### Required checks before merge

A maintainer must configure the target repository's `main` ruleset or branch protection to require a pull request and these existing GitHub Actions check names:

- `Ruff lint`
- `Scenario suite (unit)`
- `Scenario suite (solve)`
- `Developer setup (ubuntu-latest)`
- `Developer setup (windows-latest)`
- `clean-install` (Development environment workflow)

As of 2026-10-13, the active **Main required development checks** ruleset on `patrickvorgers/day-ahead` targets `main` and requires all six checks above from GitHub Actions. It requires a PR with zero mandatory review approvals, has no bypass actors, and blocks force pushes/deletion of `main`. A deliberate undefined-name violation in [temporary PR #2](https://github.com/patrickvorgers/day-ahead/pull/2) failed the required Ruff check and disabled normal merging. The clean-checkout VS Code checklist above still needs manual execution.

These are repository settings, not enabled by committing this guide. Confirm the settings on the actual merge target, including the upstream repository if contributing from a fork. This change does not add a formatting requirement; formatter adoption is a separate rollout.

Verify enforcement on a disposable PR branch: add an undefined-name lint violation, confirm `Ruff lint` fails and normal merging is blocked, then remove the violation and confirm all required checks pass. Record any maintainer bypass policy and the verification result; do not merge the violation.

---

## Making Contributions

### Branching Strategy

This project uses the following branching model:

- `main` - Main development
- `feature/*` - Feature branches
- `bugfix/*` - Bug fix branches
- `hotfix/*` - Urgent production fixes

### Creating a Pull Request

1. **Fork the Repository** (if you're an external contributor)

   Click the "Fork" button on GitHub to create your own copy of the repository.

2. **Create a Feature Branch**

   Always create a new branch for your changes:

   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/your-feature-name
   ```

   Use descriptive branch names:
   - `feature/add-solaredge-integration`
   - `bugfix/fix-price-calculation`
   - `docs/update-installation-guide`

3. **Make Your Changes**

   - Write clear, readable code
   - Follow existing code style and conventions
   - Add comments for complex logic
   - Update documentation if needed

4. **Test Your Changes**

   Run the isolated [testing commands](#testing) from the repository root. Run the manual acceptance checklist when changing the development environment. Use a separately configured test installation for live integration checks.

5. **Commit Your Changes**

   Write clear, descriptive commit messages:

   ```bash
   git add .
   git commit -m "Add feature: integration with SolarEdge API"
   ```

   Good commit message examples:
   - `Fix: Correct battery SoC calculation overflow`
   - `Feature: Add support for PostgreSQL database`
   - `Docs: Update installation instructions for Raspberry Pi`
   - `Refactor: Simplify price calculation logic`

   The title of your commit should finish the sentence: This commit will ...
   Example: 'This commit will ... add support for postgresql database ...'

6. **Push to Your Fork**

   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create the Pull Request**

   - Go to the original repository on GitHub
   - Click "Pull Requests" → "New Pull Request"
   - Select your fork and branch
   - Fill in the PR template:

   **Title:** Clear, concise description (e.g., "Add SolarEdge API integration")

   **Description:**
   ```markdown
   ## Description
   Brief description of what this PR does and why.

   ## Changes Made
   - List key changes
   - Include any breaking changes
   - Note any new dependencies

   ## Testing
   - Describe how you tested these changes
   - List any test cases added

   ## Related Issues
   Closes #123
   ```

8. **Respond to Review Feedback**

   - Address reviewer comments
   - Make requested changes in new commits
   - Push updates to the same branch (they'll appear in the PR automatically)

9. **Keep Your Branch Updated**

   If the main branch changes while your PR is open:

   ```bash
   git checkout main
   git pull origin main
   git checkout feature/your-feature-name
   git rebase main
   git push --force-with-lease
   ```

### Pull Request Checklist

Before submitting your PR, ensure:

- [ ] Code follows project conventions
- [ ] All tests pass
- [ ] New features include tests
- [ ] Documentation is updated
- [ ] Commit messages are clear
- [ ] No unnecessary files are included (check `.gitignore`)
- [ ] Changes are based on the latest `main` branch

---

## Code Style and Best Practices

### Python lint checks

#### Set up automatic feedback in VS Code

Open the repository root in VS Code and install the recommended **Python** and **Ruff** extensions from the Extensions view (`@recommended`). Select an installed Python 3.12 or newer with **Python: Select Interpreter**, then choose **Terminal > Run Task > Development: Set up Ruff**. After setup, run **Ruff: Restart Server** from the Command Palette. In a remote workspace, install the extensions in that workspace's extension host.

The same setup works for a new checkout or an existing development environment. It creates a dedicated `.venv-tools` directory, installs `requirements-dev.txt`, prepares and installs the commit hook, and runs the full lint check. It can be rerun after pulling tool upgrades. It leaves the application environment and selected application interpreter intact. Internet access is required for the initial tool and hook installation; subsequent checks use the installed tools.

Without VS Code, run the same procedure from the repository root:

```bash
python scripts/develop.py setup
```

Use `python3` on systems where `python` is unavailable, or `py -3.13` on Windows when that is your installed interpreter. Setup reads the minimum version from `ruff.toml` rather than requiring a particular launcher. On Debian, install the matching `python3-venv` package if virtual-environment creation is unavailable.

While editing, Ruff reports lint findings in the editor and Problems view. Saving a Python file explicitly, or using Auto Save on focus/window change, applies Ruff's safe fixes and import organization. Findings such as undefined names still require a manual fix. Review automatic changes and run tests for affected behavior before committing. VS Code skips these save actions for timed Auto Save (`afterDelay`); use Save or select `onFocusChange`/`onWindowChange` if you want automatic fixes. Live lint feedback remains available while typing. Formatting on save is disabled until the separate formatting rollout is complete; explicit **Format Document** remains available through Ruff.

VS Code uses a version-checked Ruff launcher from `.venv-tools`, independently of the application interpreter. Both Windows and Unix executable paths are included. The filesystem configuration takes precedence over editor rule settings. `requirements-lint.txt` is the single maintained Ruff version pin. Setup and version checks derive an ignored `.ruff.toml` that extends the shared `ruff.toml` and enforces that version, including when the extension falls back to another Ruff executable. Do not edit the generated file. An existing personal `.ruff.toml` is preserved: resolve that configuration conflict before enabling this setup.

When opening the repository, allow **automatic tasks in this trusted folder** when VS Code asks, or use **Tasks: Manage Automatic Tasks in Folder**. **Development: Watch Ruff version** checks the installation immediately and continues watching the requirements pin and installed executable. Its dedicated terminal reports missing or stale tools with the commands needed to repair them. The same warning appears in **Problems** under **Ruff setup** and is cleared when the installation matches again. This requires the Python extension and a selected Python 3.12+ interpreter. The task can also be started manually; without permission for automatic tasks, it does not start on its own.

After a pull changes the Ruff pin, the watcher updates the generated version guard and reports the mismatch within its two-second polling interval. The editor launcher also stops an already-running Ruff server when the required version changes. Local lint tasks and all commits, including commits without Python changes, stop until the installed version matches. Nothing is installed automatically. Run **Development: Set up Ruff**, followed by **Ruff: Restart Server**; the watcher reports readiness once the environment is current. Inspect **Output > Ruff** for editor server failures or the launcher path. Before the first successful setup or workspace check, the extension may still use its normal executable fallback; install the tools before relying on its feedback.

The following tasks are available through **Terminal > Run Task**:

| Task | Result |
| --- | --- |
| Development: Set up Ruff | Install or refresh tools and activate the commit hook |
| Development: Watch Ruff version | Check at workspace opening and report version changes during the session |
| Development: Check Ruff version | Check the installation once and show repair instructions if needed |
| Ruff: Check all Python files | Check the complete repository using the same configuration as CI |
| Ruff: Apply safe fixes to all Python files | Apply safe lint fixes; review the diff afterwards |
| Ruff: Run commit hooks on all files | Run the fixing hook across tracked Python files |

The commit hook checks staged Python files, including tracked tests despite the legacy `.gitignore`. If it fixes a file, the commit stops: inspect the diff, stage the corrected file and commit again. Remaining findings also block the commit. CI checks the complete repository, including files not touched by the commit.

For an existing checkout, keep any personal workspace settings and merge the Ruff entries if necessary. Disable competing Python fix-on-save actions if they cause conflicting edits. Setup uses pre-commit's migration mode to preserve existing custom hooks; it does not use `--overwrite`. If `core.hooksPath` is configured, setup stops with an explanation instead of changing it. Integrate pre-commit with that hook manager, or run local checks manually. Use `pre-commit uninstall` through the tool environment to restore a migrated hook.

To verify the editor installation, create a temporary Python file containing `import os` and `print(missing_name)`. Ruff should show `F401` and `F821`; saving removes the unused import and leaves the undefined name visible. Fix the name, delete the temporary file and run **Ruff: Check all Python files**. This checks the same rules that CI uses, with editor fixes occurring earlier.

#### Run lint without editor integration

From the repository root, install the pinned development-only linter and run:

```bash
python -m pip install -r requirements-lint.txt
python scripts/develop.py ci-check
```

`ruff.toml` explicitly enables syntax/import checks, Pyflakes, import ordering,
Python upgrades and Bugbear (`E4`, `E7`, `E9`, `F`, `I`, `UP`, `B`). It targets
Python 3.12 and includes the tracked tests despite the legacy `.gitignore`.
The **Ruff lint** GitHub Actions job runs independently of the solver stack on
every push and pull request. It reports failures rather than modifying code.

To apply safe fixes locally, use `ruff check --fix .`, inspect the diff, then
rerun relevant tests. Do not use `--unsafe-fixes` for routine cleanup. Intentional
startup imports need a narrow suppression with an explanation; do not suppress
whole files or rule families to make the check pass. `zip(..., strict=False)`
preserves existing truncation; use `strict=True` when equal lengths are validated.

Dependabot checks Ruff and pre-commit in the repository root weekly. A Ruff upgrade changes only the pin in `requirements-lint.txt`; the editor, local hook and CI derive their required version from it. Review release notes, changes to standard defaults and new diagnostics, then run lint, formatting once adopted, and relevant behavioral tests before merging the upgrade. Rerun developer setup after pulling a tooling update and restart the editor's Ruff server. Ruff is not an add-on runtime dependency.
Full-repository `ruff format` enforcement is a separate
follow-up to avoid a large formatting diff during this rollout; see
[`docs/ruff-rollout.md`](docs/ruff-rollout.md).

For behavioral verification on Linux, follow [`docs/testing.md`](docs/testing.md).
The scenario workflow also runs isolated configuration-model, SQLite query,
charging-schedule, KNMI-default and web route regression tests. Optional MariaDB
cases skip unless a dedicated disposable test database is configured. The legacy
`test_dao.py` and EV harness can access a live installation and are not part of
this isolated CI command.

### Python Style Guide

- Follow [PEP 8](https://pep8.org/) style guidelines
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100-120 characters
- Use meaningful variable and function names

### Code Organization

- Keep functions small and focused (single responsibility)
- Add docstrings to modules, classes, and functions
- Use type hints where appropriate
- Handle exceptions gracefully

### Example:

```python
def calculate_battery_soc(
    current_soc: float,
    charge_power: float,
    duration: float,
    battery_capacity: float
) -> float:
    """
    Calculate the State of Charge (SoC) of the battery after charging/discharging.
    
    Args:
        current_soc: Current state of charge (0.0 - 1.0)
        charge_power: Charging power in kW (negative for discharging)
        duration: Duration in hours
        battery_capacity: Total battery capacity in kWh
    
    Returns:
        New state of charge (0.0 - 1.0)
    
    Raises:
        ValueError: If inputs are out of valid range
    """
    if not 0 <= current_soc <= 1:
        raise ValueError(f"Invalid SoC: {current_soc}")
    
    energy_change = charge_power * duration
    new_soc = current_soc + (energy_change / battery_capacity)
    
    return max(0.0, min(1.0, new_soc))
```

### Logging

Use the logging module instead of print statements:

```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate log levels
logger.debug("Detailed diagnostic information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
logger.exception("Exception with traceback")
```

### Configuration

- Never commit sensitive data (API keys, passwords, etc.)
- Use configuration files (JSON) for settings
- Keep example configurations in the repository
- Document all configuration options

---

## Getting Help

If you need assistance:

- Check existing [Issues](https://github.com/corneel27/day-ahead/issues) on GitHub
- Review the [DOCS.md](dao/DOCS.md) for user documentation
- Create a new issue with:
  - Clear description of the problem
  - Steps to reproduce
  - Expected vs actual behavior
  - Your environment details (OS, Python version, etc.)

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE.txt](LICENSE.txt) for details.

---

## Acknowledgments

Thank you for contributing to the Day Ahead Optimizer project! Your contributions help improve energy optimization for all users.
