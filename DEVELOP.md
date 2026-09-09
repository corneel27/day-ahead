# Developer Guide for Day Ahead Optimizer

This guide will help developers set up their development environment, test changes locally, and contribute to the project.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setting Up Development Environment](#setting-up-development-environment)
- [Project Structure](#project-structure)
- [Running the Application Locally](#running-the-application-locally)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Making Contributions](#making-contributions)
- [Code Style and Best Practices](#code-style-and-best-practices)

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.10+** (the code uses PEP 604 union syntax, e.g. `int | None`)
- **Git** for version control
- **pip** (Python package installer)
- **npm** (Node Package Manager)
- A code editor (VS Code, PyCharm, etc.)

You also need access to a running Home Assistant instance:

- A **long-lived access token** (Profile -> Security -> Long-Lived Access Tokens).
  Outside the add-on there is no `SUPERVISOR_TOKEN`, so the token must be configured
  manually.
- Read access to the **Home Assistant recorder database** (the SQLite file
  `home-assistant_v2.db`, or the MariaDB/PostgreSQL server HA writes to).
  Without it every page that reads history (reports, savings, solar) fails; see
  [Troubleshooting](#troubleshooting).

---

## Setting Up Development Environment

### 1. Clone the Repository

First, clone the repository and navigate to the project directory:

```bash
git clone https://github.com/corneel27/day-ahead.git
cd day-ahead
```
Alternatively, you can use a fork to your own account.

### 2.1. Quick setup and run (limited support)

Supported on:
- Ubuntu/Debian (apt based)
- OpenSuse (zypper based)

This command will start the dev environment in the recommended mode as described [here](#running-the-application-locally).
Add the `--setup` argument to execute all steps below

```bash
chmod +x dao/run/run_dev.sh # Once
./dao/run/run_dev.sh --setup # Add --setup to install/update, only once
```

Optionally, define the flask port using `--flask-port=5001`

Use `--migrate` to create or upgrade the Day Ahead database (runs `dao/prog/check_db.py`).
This is required the first time you start with an empty `database da`:

```bash
./dao/run/run_dev.sh --setup --migrate
```

Note that the script:

- copies `options_example.json` to `options.json` and `secrets_vb.json` to
  `secrets.json` when those files do not exist yet. **The copied defaults do not
  work outside the add-on**: you still have to edit them, see
  [Set Up Configuration Files](#4-set-up-configuration-files).
- starts the Vite dev server and exports `VITE_DEV=1`, so the frontend assets are
  served by Vite on port 5173 instead of being read from a build. That port has to
  be reachable from your browser; see
  [Developing on a remote machine](#developing-on-a-remote-machine).

When error, see: [In case of error](#31-in-case-of-error)  
When successful, continue reading: [Project Structure](#project-structure)  

### 2.2. Create a Python Virtual Environment

Creating a virtual environment isolates your project dependencies from your system Python installation.

**On macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**On Windows:**
```bash
python3 -m venv .venv
.venv\Scripts\activate
```

You should see `(.venv)` in your terminal prompt, indicating the virtual environment is active.

### 3. Install Dependencies

Install all required packages from the requirements file:

```bash
pip install --upgrade pip
pip install -r dao/requirements.txt

cd dao/webserver
npm install 
```

#### 3.1 In case of error
In case you get an error like this: `This error typically indicates that MariaDB Connector/C, a dependency which must be preinstalled, is not found.`
* **Ubuntu**: `sudo apt install -y build-essential pkg-config libmariadb-dev`

In case you get an error like this: `ERROR: No matching distribution found for mip==1.16rc0` or equivalent you need to install manually.
* Edit dao/requirements.txt and remove the line with mip
* pip install -r dao/requirements.txt
* Install mip: tar -xzf dao/miplib_amd64.tar.gz -C dao/prog
* pip install --ignore-requires-python mip==1.16rc0
* export PMIP_CBC_LIBRARY=~/day-ahead/dao/prog/miplib/lib/libCbc.so
* export LD_LIBRARY_PATH=~/day-ahead/dao/prog/miplib/lib/

Repeat the two export statements under Option 1 below when starting up the environment a second time.

#### 3.2 Install in editable mode
If you're developing the package itself, you can also install it in editable mode:

```bash
pip install -e .
```

### 4. Set Up Configuration Files

The application requires configuration files in the `dao/data/` directory. Once these files are setup you can modify them through the web interface.

1. Copy the example configuration files:
   ```bash
   cp dao/data/options_example.json dao/data/options.json
   cp dao/data/secrets_vb.json dao/data/secrets.json
   ```

2. Edit `dao/data/secrets.json`. Any string in `options.json` written as
   `!secret <name>` is looked up here, for example the HA token and database
   passwords.

3. Edit the `homeassistant` section of `dao/data/options.json`. The defaults
   (`supervisor` as host, token from `SUPERVISOR_TOKEN`) only work inside the
   add-on container:

   ```json
   "homeassistant": {
     "host": "192.168.1.10",
     "ip port": 8123,
     "protocol api": "http",
     "token": "!secret ha_api_token"
   }
   ```

4. Edit the `database ha` section so it points to the recorder database of your
   Home Assistant instance.

   **SQLite** - the default `"db_path": "/homeassistant"` refers to the directory
   the add-on mounts (`homeassistant_config` in `dao/config.yaml`). That directory
   does not exist on a development machine, so set the real path:

   ```json
   "database ha": {
     "engine": "sqlite",
     "database": "home-assistant_v2.db",
     "db_path": "/absolute/path/to/homeassistant/config"
   }
   ```

   **MariaDB/MySQL or PostgreSQL** - the default server name `core-mariadb` only
   resolves inside the Home Assistant network. Use the address of the machine
   running the database and make sure the port is reachable:

   ```json
   "database ha": {
     "engine": "mysql",
     "server": "192.168.1.10",
     "port": 3306,
     "database": "homeassistant",
     "username": "homeassistant",
     "password": "!secret db_ha_password"
   }
   ```

5. Edit the `database da` section for the Day Ahead database itself. The default
   is a SQLite file in `dao/data`.

Points to be aware of:

- **Use absolute paths for `db_path`.** Relative paths are resolved against the
  current working directory, and that differs per entry point: the webserver runs
  from `dao/webserver`, the scheduler and calculations from `dao/prog`.
- **SQLite needs more than read access on the file.** Home Assistant runs its
  database in WAL mode, so the process also needs write access to the `-wal` and
  `-shm` files and to the directory containing them. For development a copy of
  `home-assistant_v2.db` is often more convenient (and safer) than the live file.
- **Restart the server after editing `options.json`.** The configuration is loaded
  once per process; `--debug` reloads on Python changes only, not on JSON changes.

### 5. Create the Day Ahead Database

The `database da` tables are created by a separate step. From the project root,
with the virtual environment active:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
cd dao/prog
python check_db.py
```

Or, when using the quick setup script: `./dao/run/run_dev.sh --migrate`.

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

#### Option 1: Run with Flask Development Server (Recommended for Development)

**Important:** The application must be run from the **webserver directory** with the PYTHONPATH set so Python can find the `dao` module.

From the project root (`day-ahead/`):

```bash
# Make sure you're in the project root directory
cd /path/to/day-ahead

# Activate your virtual environment if not already active
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate     # On Windows

# In case of manual mip install:
export PMIP_CBC_LIBRARY=~/day-ahead/dao/prog/miplib/lib/libCbc.so
export LD_LIBRARY_PATH=~/day-ahead/dao/prog/miplib/lib/

# Set PYTHONPATH and navigate to webserver directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
cd dao/webserver

# If you want to use the assets from the Vite dev server:
export VITE_DEV=1

# Run the Flask development server
python da_server.py --debug
```

The frontend assets have to come from somewhere: either set `VITE_DEV=1` and run
the Vite dev server alongside it, or run `npm run build` once. Without either, the
v2 pages raise `RuntimeError: Vite manifest not found`. See
[Build or serve the assets](#build-or-serve-the-assets).

The development server will start on `http://localhost:5000` by default. It binds
to `0.0.0.0`, so it is also reachable from other machines on your network.

**For macOS users:** Port 5000 is often used by the AirPlay Receiver service. To run on port 5001 instead, set the FLASK_PORT environment variable:

```bash
export FLASK_PORT=5001
```

Or disable AirPlay Receiver in System Settings → General → AirDrop & Handoff → AirPlay Receiver (turn off).

Then access the application at `http://localhost:5001/` instead of port 5000.

**With debug mode enabled, you get:**
- **Automatic reload** - Server restarts when code changes are detected
- **Interactive debugger** - Detailed error pages with stack traces and interactive console
- **Better error messages** - More informative error output

**Warning:** Never run with `debug=True` in production as it exposes security risks.

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
  DNS rebinding; IP addresses and `localhost` are always accepted.

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
unset VITE_DEV        # note: run_dev.sh always sets it, so start da_server.py directly
python da_server.py --debug
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
| `VITE_DEV_ALLOWED_HOSTS` | Vite | empty | Comma separated hostnames Vite accepts besides `localhost` and IP addresses. |
| `FLASK_PORT` | webserver | `5000` | Port of the Flask development server. |

#### Option 2: Run with Gunicorn (Production-like Environment)

For testing in a production-like environment:

```bash
# From the project root
cd dao/webserver
gunicorn -c gunicorn_config.py "app:app"
```

### Accessing the Web Interface

Once the server is running, open your browser and navigate to http://localhost:5000/

---

### Manual Testing Checklist

When testing changes, verify:

1. **Configuration Loading:** Settings are loaded correctly from JSON files
2. **Price Fetching:** Dynamic electricity prices are retrieved from APIs
3. **Weather Data:** Meteorological data is fetched and processed
4. **Optimization:** MIP solver runs without errors
5. **Web Interface:** All pages load and forms submit correctly
6. **Database Operations:** Data is stored and retrieved correctly
7. **Graph Generation:** Visualizations are generated properly

---

## Troubleshooting

### `RuntimeError: No database connection for Home Assistant`

The `database ha` section of `options.json` does not point to a reachable database.
The line logged just before the exception shows the path or server that was tried.
Common causes:

- `db_path` still contains the add-on default `/homeassistant`, which does not
  exist outside the container.
- A relative `db_path` resolved against an unexpected working directory.
- `server` still contains `core-mariadb`, which only resolves inside the Home
  Assistant network.
- The database file exists but the process cannot write the WAL sidecar files.

See [Set Up Configuration Files](#4-set-up-configuration-files). Restart the server
after changing `options.json`.

### `RuntimeError: No database connection for Day Ahead`

Same cause for the `database da` section, or the database has not been created yet;
see [Create the Day Ahead Database](#5-create-the-day-ahead-database).

### `RuntimeError: Vite manifest not found`

The assets have not been built and `VITE_DEV` is not set. Run `npm run build` in
`dao/webserver`, or start the Vite dev server and export `VITE_DEV=1`.

### The v2 interface loads without any styling

The browser cannot reach the Vite dev server on port 5173. Check the browser
console: connection errors point to a firewall or a tunnel that does not forward
the port, while `Blocked request. This host (...) is not allowed` means the
hostname has to be added to `VITE_DEV_ALLOWED_HOSTS`. See
[Developing on a remote machine](#developing-on-a-remote-machine).

### The interface is styled but the icons are missing

The page reaches the Vite dev server, but the address Vite advertises for its own
asset URLs does not resolve for your browser. This happens when tunneling: set
`VITE_DEV_HOST=localhost` before starting Vite.

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

   ```bash
   # Run the application locally (from project root)
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   cd dao/webserver
   python da_server.py
   
   # Run unit tests (from project root)
   cd dao/tests/prog
   python test_dao.py
   ```

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
