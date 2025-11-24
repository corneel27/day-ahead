# Developer Guide for Day Ahead Optimizer

This guide will help developers set up their development environment, test changes locally, and contribute to the project.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setting Up Development Environment](#setting-up-development-environment)
- [Project Structure](#project-structure)
- [Running the Application Locally](#running-the-application-locally)
- [Testing](#testing)
- [Making Contributions](#making-contributions)
- [Code Style and Best Practices](#code-style-and-best-practices)

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.8+** (Python 3.9 or higher recommended)
- **Git** for version control
- **pip** (Python package installer)
- A code editor (VS Code, PyCharm, etc.)

---

## Setting Up Development Environment

### 1. Clone the Repository

First, clone the repository and navigate to the project directory:

```bash
git clone https://github.com/corneel27/day-ahead.git
cd day-ahead
```
Alternatively you can use a fork to your own account.

### 2. Create a Python Virtual Environment

Creating a virtual environment isolates your project dependencies from your system Python installation.

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt, indicating the virtual environment is active.

### 3. Install Dependencies

Install all required packages from the requirements file:

```bash
pip install --upgrade pip
pip install -r dao/requirements.txt
```

#### 3.1 In case of error
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
   ```

2. Edit `dao/data/options.json` to match your development environment settings.

3. If you need database credentials, create `dao/data/secrets.json` based on your database setup.

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
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows

# In case of manual mip install:
export PMIP_CBC_LIBRARY=~/day-ahead/dao/prog/miplib/lib/libCbc.so
export LD_LIBRARY_PATH=~/day-ahead/dao/prog/miplib/lib/

# Set PYTHONPATH and navigate to webserver directory
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
cd dao/webserver

# Set Flask to development mode
export FLASK_ENV=development
export FLASK_DEBUG=1

# Run the Flask development server
python da_server.py
```

The development server will start on `http://localhost:5000` by default.

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
