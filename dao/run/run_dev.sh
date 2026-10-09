#!/bin/bash

# Use this script to start the development environment for Day Ahead Optimizer.
#
# Options:
# --setup             # install system packages, setup venv, install pip dependencies and npm packages
# --migrate           # run migrations
# --flask-port=5001   # run flask on custom port

set -e

SETUP=false
MIGRATE=false
FLASK_PORT=5000

for arg in "$@"; do
  case "$arg" in
    --setup)
      SETUP=true
      ;;
    --migrate)
      MIGRATE=true
      ;;
    --flask-port=*)
      FLASK_PORT="${arg#--flask-port=}"
      if ! [[ "$FLASK_PORT" =~ ^[0-9]+$ ]] || [ "$FLASK_PORT" -lt 1 ] || [ "$FLASK_PORT" -gt 65535 ]; then
        echo "Invalid value for --flask-port: $FLASK_PORT"
        echo "Use: $0 [--setup] [--flask-port=5001]"
        exit 1
      fi
      ;;
    *)
      echo "Unknown argument: $arg"
      echo "Use: $0 [--setup] [--flask-port=5001]"
      exit 1
      ;;
  esac
done

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/venv/day_ahead"
VENV_PYTHON="${VENV_DIR}/bin/python"
DAO_DIR="${PROJECT_ROOT}/dao"
WEBSERVER_DIR="${DAO_DIR}/webserver"
DATA_DIR="${DAO_DIR}/data"
APT_PACKAGES="build-essential pkg-config libmariadb-dev python3-pip python3 python3-venv npm"
ZYPPER_PACKAGES="pkg-config libmariadb-devel python3-pip python3 npm python3-devel gcc make"

copy_config_if_missing() {
  if [ ! -f "${DATA_DIR}/options.json" ]; then
    echo "options.json missing; copy options_example.json"
    cp "${DATA_DIR}/options_example.json" "${DATA_DIR}/options.json"
  fi

  if [ ! -f "${DATA_DIR}/secrets.json" ]; then
    if [ -f "${DATA_DIR}/secrets_vb.json" ]; then
      echo "secrets.json missing; copy secrets_vb.json"
      cp "${DATA_DIR}/secrets_vb.json" "${DATA_DIR}/secrets.json"
    else
      echo "secrets.json missing; create empty secrets.json"
      printf '{}\n' > "${DATA_DIR}/secrets.json"
    fi
  fi
}

install_system_dependencies_if_available() {
  DEPS_INSTALLED=0
  if command -v apt >/dev/null 2>&1; then

    echo "apt found; install system dependencies"
    if [ "$(id -u)" -eq 0 ]; then
      apt install -y $APT_PACKAGES
      DEPS_INSTALLED=1
    elif command -v sudo >/dev/null 2>&1; then
      sudo apt install -y $APT_PACKAGES
      DEPS_INSTALLED=1
    else
      echo "apt is available, but script not executed as root and sudo not found."
      echo "Manually execute: apt install -y $APT_PACKAGES"
      exit 1
    fi
  fi

  if command -v zypper >/dev/null 2>&1; then

    echo "zypper found; install system dependencies"
    if [ "$(id -u)" -eq 0 ]; then
      zypper install -y $ZYPPER_PACKAGES
      DEPS_INSTALLED=1
    elif command -v sudo >/dev/null 2>&1; then
      sudo zypper install -y $ZYPPER_PACKAGES
      DEPS_INSTALLED=1
    else
      echo "zypper is available, but script not executed as root and sudo not found."
      echo "Manually execute: zypper install -y $ZYPPER_PACKAGES"
      exit 1
    fi
  fi

  if [ $DEPS_INSTALLED -eq 0 ]; then
    echo "no package manager found; installation of system dependencies skipped: $APT_PACKAGES"
  fi
}

# A venv holds absolute paths: its bin/python is a symlink to the interpreter it was
# created with. The directory therefore outlives the interpreter, and existing is not
# the same as working. Check that it actually runs before relying on it.
venv_is_usable() {
  [ -f "${VENV_DIR}/bin/activate" ] &&
    [ -x "$VENV_PYTHON" ] &&
    "$VENV_PYTHON" -c "" >/dev/null 2>&1
}

create_venv() {
  echo "Create Virtual environment in ${VENV_DIR}"
  if ! python3 -m venv "$VENV_DIR"; then
    echo "Creating the virtual environment failed."
    echo "On Debian/Ubuntu this needs the python3-venv package: sudo apt install -y python3-venv"
    exit 1
  fi
}

explain_broken_venv() {
  echo "The virtual environment in ${VENV_DIR} is not usable:"
  echo "its interpreter ${VENV_PYTHON} is missing or does not run."
  echo "Common causes: the system python3 was upgraded or removed, a previous setup was"
  echo "interrupted, or the project directory was copied from another machine (a venv"
  echo "contains absolute paths and cannot be moved). Recreating it is always safe."
}

# $1: "setup" to create or repair the venv, "run" to only report what is wrong.
ensure_venv() {
  if venv_is_usable; then
    return
  fi

  if [ ! -d "$VENV_DIR" ]; then
    if [ "$1" != "setup" ]; then
      echo "No venv found. Run: $0 --setup"
      exit 1
    fi
    create_venv
  elif [ ! -f "${VENV_DIR}/pyvenv.cfg" ]; then
    echo "${VENV_DIR} exists but is not a virtual environment."
    echo "Remove or rename it, then run: $0 --setup"
    exit 1
  else
    explain_broken_venv
    if [ "$1" != "setup" ]; then
      echo "Run: rm -rf '${VENV_DIR}' && $0 --setup"
      exit 1
    fi
    echo "Recreating it."
    rm -rf "$VENV_DIR"
    create_venv
  fi

  if ! venv_is_usable; then
    echo "The virtual environment in ${VENV_DIR} is still not usable; giving up."
    exit 1
  fi
}

if [ "$SETUP" = true ]; then
  install_system_dependencies_if_available

  ensure_venv setup

  # shellcheck source=/dev/null
  source "${VENV_DIR}/bin/activate"

  echo "pip upgraden"
  "$VENV_PYTHON" -m pip install --upgrade pip

  echo "Install python dependencies"
  cd "$DAO_DIR"
  "$VENV_PYTHON" -m pip install -r requirements.txt

  echo "Install node dependencies"
  cd "$WEBSERVER_DIR"
  npm install
else
  ensure_venv run

  # shellcheck source=/dev/null
  source "${VENV_DIR}/bin/activate"
fi

copy_config_if_missing

export PYTHONPATH="${PYTHONPATH}:${PROJECT_ROOT}:${PROJECT_ROOT}/lib:${PROJECT_ROOT}/prog"

if [ "$MIGRATE" = true ]; then
  echo "Migrating db"
  cd "${PROJECT_ROOT}/dao/prog"
  "$VENV_PYTHON" check_db.py
  cd "${PROJECT_ROOT}"
fi

export VITE_DEV=1
export FLASK_PORT="$FLASK_PORT"

# In case of manual mip install, these paths are used by the MIP solver.
#export PMIP_CBC_LIBRARY="${DAO_DIR}/prog/miplib/lib/libCbc.so"
#export LD_LIBRARY_PATH="${DAO_DIR}/prog/miplib/lib/${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

cd "$WEBSERVER_DIR"

cleanup() {
  if [ "$CLEANING_UP" = true ]; then
    return
  fi

  CLEANING_UP=true
  trap - EXIT INT TERM

  echo "Killing all processes..."

  if [ -n "${FLASK_PID:-}" ]; then
    kill -TERM -- "-$FLASK_PID" 2>/dev/null || true
  fi

  if [ -n "${VITE_PID:-}" ]; then
    kill -TERM -- "-$VITE_PID" 2>/dev/null || true
  fi

  sleep 2

  if [ -n "${FLASK_PID:-}" ]; then
    kill -KILL -- "-$FLASK_PID" 2>/dev/null || true
  fi

  if [ -n "${VITE_PID:-}" ]; then
    kill -KILL -- "-$VITE_PID" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Vite development server starten"
setsid bash -c "
  cd '$WEBSERVER_DIR'
  npm run vite-serve
" &
VITE_PID=$!

sleep 1

echo "Flask development server starten"
setsid bash -c "
  cd '$WEBSERVER_DIR'
  '$VENV_PYTHON' da_server.py --debug
" &
FLASK_PID=$!

sleep 2

sleep 2

echo "Flask PID: ${FLASK_PID}"
echo "Vite PID: ${VITE_PID}"

wait -n "$VITE_PID" "$FLASK_PID"

echo "Killing all processes..."
cleanup
wait