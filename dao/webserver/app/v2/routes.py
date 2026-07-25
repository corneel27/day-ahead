import time, os, fnmatch, re, datetime, time, threading, json
from flask import Blueprint, render_template, request, redirect, url_for

from dao.prog.version import __version__
from subprocess import Popen, PIPE, run, STDOUT, DEVNULL
from pathlib import Path
from dao.prog.da_report import Report
from dao.prog.config.loader import ConfigurationLoader

v2 = Blueprint("v2", __name__)

@v2.context_processor
def inject_data():
    return {
        "version": __version__,
        "vite_tags": vite_tags("assets/main.js")
    }

# globals
app_datapath = "app/static/data/"

VITE_DEV_SERVER = "http://localhost:5173/static/build"
VITE_MANIFEST = Path("app/static/build/.vite/manifest.json")

def vite_tags(entry: str) -> str:
    if os.getenv("VITE_DEV") == "1":
        return f'<script type="module" src="{VITE_DEV_SERVER}/@vite/client"></script>' \
               f'<script type="module" src="{VITE_DEV_SERVER}/{entry}"></script>'

    if not VITE_MANIFEST.exists():
        raise RuntimeError("Vite manifest not found. Run 'npm run build' in the Vite server directory.")

    with VITE_MANIFEST.open() as f:
        manifest = json.load(f)

    asset = manifest[entry]

    tags = []

    for css in asset.get("css", []):
        href = url_for("static", filename=f"build/{css}")
        tags.append(f'<link rel="stylesheet" href="{href}">')

    src = url_for("static", filename=f'build/{asset["file"]}')
    tags.append(f'<script type="module" src="{src}"></script>')

    return "\n".join(tags)


def get_file_list_with_ts(path: str, pattern: str) -> list:
    """
    get a time-ordered file list with name and timestamp from filename
    :parameter path: folder
    :parameter pattern: wildcards to search for
    """
    flist = []
    for f in os.listdir(path):
        if fnmatch.fnmatch(f, pattern):
            # Extract timestamp from filename (e.g. calc_2026-02-17__08-45.png) because datetime picker works with
            # absolute timestamps and the file modification date might differ from the timestamp in the filename, which is the intended reference time for the user
            m = re.search(r"(\d{4}-\d{2}-\d{2})__(\d{2})[:-](\d{2})(?:[:-](\d{2}))?", f)
            if m:
                try:
                    seconds = m.group(4) or "00"
                    dt_str = f"{m.group(1)} {m.group(2)}:{m.group(3)}:{seconds}"
                    dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                    timestamp = dt.timestamp()  # Local time as epoch
                    flist.append({
                        "name": f,
                        "time": timestamp,
                    })
                except (ValueError, OSError):
                    # Fallback to mtime if filename parsing fails
                    fullname = os.path.join(path, f)
                    flist.append({
                        "name": f,
                        "time": int(os.path.getmtime(fullname)),
                    })

    flist.sort(key=lambda x: (x["time"], x["name"].lower()))
    return flist


def get_closest_index_from_list(flist: list, ts: float) -> int:
    return min(
        range(len(flist)),
        key=lambda i: abs(flist[i].get("time", 0) - ts)
    )


STATEFILE = "../data/task_state.json"
STALE_AFTER = 600

def save_run_state(state):
    # Write to tmp file and replace (atomic)
    # This prevents race condition between read and write
    state = {
        **state,
        "last_update": time.time(),
    }

    temp_file = STATEFILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_file, STATEFILE)


def get_run_state() -> dict:
    no_state = {
        "status": "idle",
        "task": None,
        "logfile": None,
        "started": None,
    }

    try:
        with open(STATEFILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        return no_state
    except (json.JSONDecodeError, OSError):
        return no_state

    last_update = state.get("last_update", 0)

    if (
        state.get("status") == "running"
        and time.time() - last_update > STALE_AFTER
    ):
        return no_state

    return state

def run_and_log(cmd, state):
    flist = get_file_list_with_ts(os.path.join(app_datapath, "log"),"*.log",)

    last_log_file = None
    if len(flist) > 0:
        last_log_file = app_datapath + "log/" + flist[-1]["name"]

    proc = Popen(
        cmd,
        stdout=DEVNULL,
        stderr=DEVNULL,
        text=True,
    )

    while proc.poll() is None:
        updated_state = get_run_state()

        if updated_state.get("status") == "cancelled":
            if state["logfile"] and os.path.exists(state["logfile"]):
                os.remove(state["logfile"])

            proc.kill()
            break

        if state["logfile"] is None:
            flist = get_file_list_with_ts(
                os.path.join(app_datapath, "log"),
                "*.log",
            )

            if flist:
                logfile = os.path.join(
                    app_datapath,
                    "log",
                    flist[-1]["name"],
                )

                if logfile != last_log_file:
                    state["logfile"] = logfile
                    save_run_state(state)

        elif state["logfile"] != updated_state.get("logfile"):
            if os.path.exists(state["logfile"]):
                os.remove(state["logfile"])

            proc.kill()
            break

        # Neem de actuele status over voordat de heartbeat geschreven wordt.
        state["status"] = updated_state.get("status", state["status"])

        if state["status"] == "running":
            save_run_state(state)

        time.sleep(1)

    proc.wait()

    updated_state = get_run_state()

    if updated_state["logfile"] == state["logfile"]:
        state["status"] = "done" if proc.returncode == 0 else "error"
        state["returncode"] = proc.returncode
        save_run_state(state)


def log_chart(datapath: str, pattern: str):
    #  By design; the get_file_list() is called over and over again to ensure an accurate reflection of the files
    flist = get_file_list_with_ts(app_datapath + datapath, pattern)
    last_index = len(flist) - 1
    if len(flist) == 0:
        return None

    show_index = request.args.get("i")
    if show_index is None:
        show_index = last_index
    else:
        show_index = int(show_index)

    show_index = max(0, min(show_index, last_index))

    rq_ts = request.args.get("ts")
    if rq_ts is not None:
        show_index = get_closest_index_from_list(flist, datetime.datetime.fromisoformat(rq_ts).timestamp())

    first_index = 0
    prev_index = max(0, show_index - 1)
    next_index = min(last_index, show_index + 1)
    ffprev_index = max(0,
                       get_closest_index_from_list(flist, flist[show_index]["time"] - (6 * 3600)))  # Subtract 6 hours
    ffnext_index = min(last_index,
                       get_closest_index_from_list(flist, flist[show_index]["time"] + (6 * 3600)))  # Add 6 hours
    show_ts = datetime.datetime.fromtimestamp(flist[show_index]["time"]).isoformat()

    return {
        "filename": flist[show_index]["name"],
        "first_index": first_index,
        "ffprev_index": ffprev_index,
        "prev_index": prev_index,
        "show_index": show_index,
        "next_index": next_index,
        "ffnext_index": ffnext_index,
        "last_index": last_index,
        "show_ts": show_ts,
    }


def get_solar_items_with_ml():
    loader = ConfigurationLoader(Path(app_datapath + "options.json"))
    config = loader.load_and_validate()
    if config is None:
        return {}

    solar_options = [
        *config.solar,
        *(
            solar_option
            for battery_option in config.battery
            for solar_option in battery_option.solar
        ),
    ]

    return {
        solar_option.name or "default": solar_option
        for solar_option in solar_options
        if solar_option.ml_prediction
    }


@v2.route("/")
@v2.route("/chart")
def chart():
    kwargs = log_chart("images/", "*.png")
    if kwargs is None:
        return render_template("v2/no-run.html", )

    kwargs["image"] = url_for('static', filename="data/images/" + kwargs["filename"])
    return render_template(
        "v2/chart.html",
        **kwargs
    )


@v2.route("/log")
def log():
    kwargs = log_chart("log/", "*.log")
    if kwargs is None:
        return render_template("v2/no-run.html", )

    log_file = app_datapath + "log/" + kwargs["filename"]
    with open(log_file, "r") as f:
        kwargs["logdata"] = f.read()

    return render_template(
        "v2/log.html",
        **kwargs
    )


@v2.route("/delete-file", methods=["POST"])
def delete_file():
    post_data = request.form.to_dict(flat=True)

    if post_data["confirm"] == "1" and re.match(r'^(images|log)/[^/]+\.(log|png)$', post_data["file"]):
        os.remove(app_datapath + post_data["file"])

    return redirect(url_for('v2.' + post_data["action"], i=post_data["show_index"]))


@v2.route("/run")
def run():
    return render_template("v2/run.html")

@v2.route("/run-cancel")
def run_cancel():
    try:
        state = get_run_state()
        state["status"] = "cancelled"
        save_run_state(state)
        return render_template("v2/run.html")
    except Exception as e:
        return "Error cancelling run: " + str(e), 500


@v2.route("/run-exec", methods=["POST"])
def run_exec():
    current_state = get_run_state()

    if current_state["status"] == "running":
        return "Process already running: " + current_state["task"], 500

    task = request.form.to_dict()["task"]

    cmd = None
    match task:
        case "optimize_debug":
            cmd = ["debug", "calc"]
        case "optimize_regular":
            cmd = ["calc"]
        case "calc_baseloads":
            cmd = ["calc_baseloads"]
        case "update_tibber":
            cmd = ["tibber"]
        case "update_meteo":
            cmd = ["meteo"]
        case "update_prices":
            cmd = ["prices"]
        case "train_ml":
            cmd = ["train"]

    if cmd is None:
        return "Invalid action", 500

    # Save the state synchronous to prevent race condition
    state = {
        "status": "running",
        "started": time.time(),
        "task": task,
        "returncode": None,
        "logfile": None,
    }
    save_run_state(state)

    cmd = ["python3", "../prog/day_ahead.py", *cmd]

    threading.Thread(
        target=run_and_log,
        args=(cmd, state),
        daemon=True
    ).start()

    return redirect(url_for('v2.run_status'))


@v2.route("/run-status", methods=["GET"])
def run_status():
    current_state = get_run_state()

    content = "No logfile available"
    started = None
    seconds_running = None
    status = current_state["status"]

    if status != "idle":
        started_timestamp = current_state.get("started")
        started = (
            datetime.datetime.fromtimestamp(started_timestamp)
            if started_timestamp is not None
            else None
        )

        last_update = (
            time.time()
            if status == "running"
            else current_state.get("last_update")
        )

        seconds_running = None
        if last_update is not None and started is not None:
            last_update = datetime.datetime.fromtimestamp(last_update)
            seconds_running = int((last_update - started).total_seconds())

        if current_state.get("logfile") is None:
            content = "No log data available yet"
        else:
            try:
                with open(current_state["logfile"], "r") as f:
                    content = f.read()
            except:
                content = "Could not read logfile"

    headers = {
        "HX-Push-Url": "false",
    }

    return render_template(
        "v2/run-status.html",
        run_status=current_state,
        started=started,
        seconds_running=seconds_running,
        content=content,
    ), headers


def reports_gen(subject: str, view: str, period: str, solar_item=None):
    report = Report(app_datapath + "/options.json")
    prognose = period in ["vandaag en morgen", "morgen", "today_with_forecast"]
    if period == "today_with_forecast":
        period = "vandaag"

    tot = None

    if not prognose:
        now = datetime.datetime.now()
        tot = report.periodes[period]["tot"]
        tot = min(tot, datetime.datetime(now.year, now.month, now.day, now.hour))

    interval = report.periodes[period]["interval"]

    if subject == "grid":
        report_df = report.get_grid_data(period, _tot=tot)
        report_df = report.calc_grid_columns(
            report_df, interval, view
        )
    elif subject == "balans":
        report_df, lastmoment = report.get_energy_balance_data(
            period, _tot=tot
        )
        report_df = report.calc_balance_columns(
            report_df, interval, view
        )
    # else:  # co2
    #     report_df = report.calc_co2_emission(
    #         period,
    #         _tot=tot,
    #         active_interval="uur",
    #         active_view=view,
    #     )
    elif subject == "save_cons":
        report_df = report.calc_saving_consumption(
            active_period=period,
            _tot=tot,
            active_interval=interval,
            active_view=view,
        )
    elif subject == "save_cost":
        report_df = report.calc_saving_consumption(
            active_period=period,
            _tot=tot,
            active_interval=interval,
            active_view=view,
        )
    elif subject == "solar":
        report_df = report.calc_solar_data(
            solar_item, datetime.date.today(), view
        )
    else:
        raise Exception("Invalid subject")

    report_df.round(3)

    if view == "tabel":
        report_data = [
            report_df.to_html(
                index=False,
                justify="right",
                decimal=",",
                classes="data",
                border=0,
                float_format="{:.3f}".format,
            )
        ]
    else:
        if subject == "grid":
            report_data = report.make_graph(report_df, period)
        elif subject == "balans":
            report_data = report.make_graph(
                report_df, period, report.balance_graph_options
            )
        # else:  # co2
        #     report_data = report.make_graph(
        #         report_df, period, report.co2_graph_options
        #     )
        elif subject == "save_cons":
            report_data = report.make_graph(
                report_df, period, report.saving_cons_graph_options
            )
        elif subject == "save_cost":
            report_data = report.make_graph(
                report_df, period, report.saving_cost_graph_options
            )
        elif subject == "solar":
            report_data = report.make_graph(
                report_df,
                "vandaag",
                _options=report.solar_graph_options,
            )
        else:
            raise Exception("Invalid subject")

    return report_data


@v2.route("/reports", methods=["GET"])
def reports():
    subject = request.args.get("subject", default="grid")
    view = request.args.get("view", default="tabel")
    period = request.args.get("period", default="vandaag")
    report_data = reports_gen(subject, view, period)
    return render_template(
        "v2/report.html",
        title="Reports",
        period=period,
        subject=subject,
        view=view,
        report_data=report_data,
        subject_options=[{"label": "Grid", "value": "grid"},
                         {"label": "Balance", "value": "balans"}]
    )


@v2.route("/savings", methods=["GET"])
def savings():
    subject = request.args.get("subject", default="save_cons")
    view = request.args.get("view", default="tabel")
    period = request.args.get("period", default="vandaag")
    report_data = reports_gen(subject, view, period)
    return render_template(
        "v2/report.html",
        title="Savings",
        period=period,
        subject=subject,
        view=view,
        report_data=report_data,
        subject_options=[{"label": "Consumption", "value": "save_cons"},
                         {"label": "Cost", "value": "save_cost"}]
    )


@v2.route("/solar")
def solar():
    solar_items = get_solar_items_with_ml()

    if len(solar_items) == 0:
        return render_template("v2/solar-not-found.html")

    subject = request.args.get("subject", default=next(iter(solar_items.keys())))
    view = request.args.get("view", default="grafiek")
    period = request.args.get("period", default="vandaag")

    report_data = reports_gen("solar", view, period, solar_item=solar_items[subject])
    return render_template(
        "v2/report.html",
        title="Solar",
        period=period,
        subject=subject,
        view=view,
        report_data=report_data,
        hide_period=True,
        subject_options=[
            {"label": key, "value": key}
            for key in solar_items.keys()
        ]
    )


@v2.route("/reports-v2", methods=["GET"])
def reportsv2():
    today = datetime.datetime.combine(
        datetime.date.today(),
        datetime.time.min
    )

    tomorrow = today + datetime.timedelta(days=1)
    start = request.args.get("start", default=today.isoformat())
    end = request.args.get("end", default=tomorrow.isoformat())
    fields = request.args.get("fields", default="prod,cons,cost,profit")
    aggregate = request.args.get("aggregate", default="hour")

    fields = fields.split(",")

    report = Report(app_datapath + "/options.json")
    vars = report.get_vars()

    return render_template(
        "v2/reports-v2.html",
        start=start,
        end=end,
        aggregate=aggregate,
        vars=vars,
        fields=fields,
    )


@v2.route("/config", methods=["GET", "POST"])
def config():
    path = app_datapath + "options.json"
    error = None
    success = None

    if request.method == "POST" and request.form.to_dict()["config"] is not None:
        try:
            newconfig = request.form.to_dict()["config"]
            # try loading json
            json.loads(newconfig)
            with open(path, "w") as f:
                f.write(newconfig)
            success = "Config updated successfully"
        except Exception as err:
            error = "Error: " + err.args[0]

    with open(path, "r") as file:
        content = file.read()

    return render_template(
        "v2/config.html",
        content=content,
        success=success,
        error=error,
    )


@v2.route("/secrets", methods=["GET", "POST"])
def secrets():
    path = app_datapath + "secrets.json"
    error = None
    success = None

    if request.method == "POST" and request.form.to_dict()["secrets"] is not None:
        try:
            newsecrets = request.form.to_dict()["secrets"]
            # try loading json
            json.loads(newsecrets)
            with open(path, "w") as f:
                f.write(newsecrets)
            success = "Secrets updated successfully"
        except Exception as err:
            error = "Error: " + err.args[0]

    with open(path, "r") as file:
        content = file.read()

    with open(path, "r") as file:
        content = file.read()

    return render_template(
        "v2/secrets.html",
        content=content,
        success=success,
        error=error,
    )
