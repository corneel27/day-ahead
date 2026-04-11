import collections
import datetime
import re


# from sqlalchemy.sql.coercions import expect_col_expression_collection

from dao.webserver.app import app
from flask import render_template, request, session as flask_session
import fnmatch
import os
from subprocess import PIPE, run
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from dao.prog.config.loader import ConfigurationLoader
from dao.prog.da_report import Report
from dao.prog.version import __version__

web_datapath = "static/data/"
app_datapath = "app/static/data/"
images_folder = os.path.join(web_datapath, "images")
config = None

# Introduced previous_time and active_view as global variables
# This is used to enable switching between "grafiek" and "tabel" and retaining the (closest) timestamp
previous_time = None 
active_view = "grafiek"

def create_config():
    global config
    try:
        loader = ConfigurationLoader(Path(app_datapath + "options.json"))
        config = loader.load_and_validate()
    except (ValueError, RuntimeError) as ex:
        logging.error(app_datapath)
        logging.error(ex)
        config = None


logname = "dashboard.log"

browse = {}

views = {
    "tabel": {"name": "Tabel", "icon": "tabel.png"},
    "grafiek": {"name": "Grafiek", "icon": "grafiek.png"},
}

actions = {
    "first": {"icon": "first.png"},
    "prev": {"icon": "prev.png"},
    "next": {"icon": "next.png"},
    "last": {"ison": "last.png"},
}

periods = {
    "list": [
        "vandaag",
        "morgen",
        "vandaag en morgen",
        "gisteren",
        "deze week",
        "vorige week",
        "deze maand",
        "vorige maand",
        "dit jaar",
        "vorig jaar",
        "dit contractjaar",
        "365 dagen",
    ],
    "prognose": ["vandaag", "deze week", "deze maand", "dit jaar", "dit contractjaar"],
}

web_menu = {
    "home": {
        "name": "Home",
        "submenu": {},
        "views": views,
        "actions": actions,
        "function": "home",
    },
    "run": {
        "name": "Run",
    },
    "reports": {
        "name": "Reports",
        "submenu": {
            "grid": {
                "name": "Grid",
                "views": views,
                "periods": periods,
                "calculate": "calc_grid",
            },
            "balans": {"name": "Balans", "views": views, "periods": periods},
            "co2": {"name": "CO2", "views": views, "periods": periods.copy()},
        },
    },
    "savings": {
        "name": "Savings",
        "submenu": {
            "consumption": {
                "name": "Verbruik",
                "views": views,
                "periods": periods,
                "calculate": "calc_saving_consumption",
                "graph_options": "saving_cons_graph_options",
            },
            "cost": {
                "name": "Kosten",
                "views": views,
                "periods": periods,
                "calculate": "calc_saving_cost",
                "graph_options": "saving_cost_graph_options",
            },
            "co2": {
                "name": "CO2-emissie",
                "views": views,
                "periods": periods.copy(),
                "calculate": "calc_saving_co2",
                "graph_options": "saving_co2_graph_options",
            },
        },
    },
    "solar": {
        "name": "Solar",
        "submenu": {
            "items": {},
            "views": views,
            "actions": actions,
        },
    },
    "settings": {
        "name": "Config",
        "submenu": {
            "options": {"name": "Options", "views": "json-editor"},
            "secrets": {"name": "Secrets", "views": "json-editor"},
        },
    },
}

solar_web_menu = {
    "solar": {
        "name": "Solar",
        "submenu": {
            "items": {},
            "views": views,
            "actions": actions,
        },
    },
}


def generate_solar_items():
    global web_menu
    solar_options = config.solar if config else []
    battery_options = config.battery if config else []
    for battery_option in battery_options:
        for sol_opt in battery_option.solar:
            solar_options.append(sol_opt)
    result = {}
    for solar_option in solar_options:
        if solar_option.ml_prediction:
            key = solar_option.name or "default"
            result[key] = solar_option
    if len(result) == 0:
        if "solar" in web_menu.keys():
            del web_menu["solar"]
    else:
        if not "solar" in web_menu.keys():
            web_menu.update(solar_web_menu)
            key_order = ("home", "run", "reports", "savings", "solar", "settings")
            web_menu = collections.OrderedDict((k, web_menu[k]) for k in key_order)
    return result


def get_web_menu_items():
    items = {}
    for key, value in web_menu.items():
        items[key] = value["name"]
    return items


web_menu_items = {}
solar_items = {}


def check_web_menu_items():
    global solar_items, web_menu_items
    create_config()
    solar_items = generate_solar_items()
    if len(solar_items) > 0 and "solar" in web_menu.keys():
        web_menu["solar"]["submenu"]["items"] = solar_items
    web_menu_items = get_web_menu_items()


check_web_menu_items()

_save_days = config.history.save_days if config is not None else 7
handler = TimedRotatingFileHandler(
    "../data/log/" + logname,
    when="midnight",
    backupCount=_save_days,
)
handler.suffix = "%Y%m%d"
handler.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[handler],
    format=f"%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s",
)

if config is not None:
    sensor_co2_intensity = config.report.co2_intensity_sensor if config and config.report else None
else:
    sensor_co2_intensity = None

if sensor_co2_intensity is None:
    del web_menu["reports"]["submenu"]["co2"]
    del web_menu["savings"]["submenu"]["co2"]
else:
    web_menu["reports"]["submenu"]["co2"]["periods"]["prognose"] = []
    web_menu["reports"]["submenu"]["co2"]["periods"]["list"] = periods["list"].copy()
    web_menu["reports"]["submenu"]["co2"]["periods"]["list"].remove("vandaag en morgen")
    web_menu["reports"]["submenu"]["co2"]["periods"]["list"].remove("morgen")
    web_menu["savings"]["submenu"]["co2"]["periods"]["prognose"] = []
    web_menu["savings"]["submenu"]["co2"]["periods"]["list"] = periods["list"].copy()
    web_menu["savings"]["submenu"]["co2"]["periods"]["list"].remove("vandaag en morgen")
    web_menu["savings"]["submenu"]["co2"]["periods"]["list"].remove("morgen")

bewerkingen = {
    "calc_met_debug": {
        "name": "Optimaliseringsberekening met debug",
        "cmd": ["python3", "../prog/day_ahead.py", "debug", "calc"],
        "task": "calc_optimum",
        "file_name": "calc_debug",
    },
    "calc_zonder_debug": {
        "name": "Optimaliseringsberekening zonder debug",
        "cmd": ["python3", "../prog/day_ahead.py", "calc"],
        "task": "calc_optimum",
        "file_name": "calc",
    },
    "get_tibber": {
        "name": "Verbruiksgegevens bij Tibber ophalen",
        "cmd": ["python3", "../prog/day_ahead.py", "tibber"],
        "task": "get_tibber_data",
        "file_name": "tibber",
    },
    "get_meteo": {
        "name": "Meteoprognoses ophalen",
        "cmd": ["python3", "../prog/day_ahead.py", "meteo"],
        "task": "get_meteo_data",
        "file_name": "meteo",
    },
    "get_prices": {
        "name": "Day ahead prijzen ophalen",
        "cmd": ["python3", "../prog/day_ahead.py", "prices"],
        "task": "get_day_ahead_prices",
        "parameters": ["prijzen_start", "prijzen_tot"],
        "file_name": "prices",
    },
    "calc_baseloads": {
        "name": "Bereken de baseloads",
        "cmd": ["python3", "../prog/day_ahead.py", "calc_baseloads"],
        "task": "calc_baseloads",
        "file_name": "baseloads",
    },
    "train_ml_predictions": {
        "name": "ML modellen trainen",
        "cmd": ["python3", "../prog/day_ahead.py", "train"],
        "function": "train_ml_predictions",
        "file_name": "train",
    },
}


def get_file_list(path: str, pattern: str) -> list:
    """
    get a time-ordered file list with name and timestamp from filename
    :parameter path: folder
    :parameter pattern: wildcards to search for
    """
    flist = []
    for f in os.listdir(path):
        if fnmatch.fnmatch(f, pattern):
            # Extract timestamp from filename (e.g. calc_2026-02-17__08-45.png) because datetime picker works with
            # absolut timestamps and then file modification date might differ from the timestamp in the filename, which is the intended reference time for the user  
            m = re.search(r'(\d{4}-\d{2}-\d{2})__(\d{2})(:|\-)(\d{2})', f)
            if m:
                try:
                    dt_str = f"{m.group(1)} {m.group(2)}:{m.group(4)}"
                    dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    timestamp = dt.timestamp()  # Local time as epoch
                    flist.append({"name": f, "time": timestamp})
                except (ValueError, OSError):
                    # Fallback to mtime if filename parsing fails
                    fullname = os.path.join(path, f)
                    flist.append({"name": f, "time": os.path.getmtime(fullname)})
            else:
                # Fallback to mtime if no timestamp in filename
                fullname = os.path.join(path, f)
                flist.append({"name": f, "time": os.path.getmtime(fullname)})
    flist.sort(key=lambda x: x.get("time"), reverse=True)
    return flist


@app.route("/", methods=["POST", "GET"])
def menu():
    # check_web_menu_items()
    lst = request.form.to_dict(flat=False)
    if "current_menu" in lst:
        current_menu = lst["current_menu"][0]
        if current_menu == "home":
            return home()
        elif current_menu == "run":
            return run_process()
        elif current_menu == "reports" or current_menu == "savings":
            return reports(current_menu)
        elif current_menu == "solar" and "solar" in web_menu_items.keys():
            return solar()
        elif current_menu == "settings":
            return settings()
        else:
            return home()
    else:
        if "menu_home" in lst:
            return home()
        elif "menu_run" in lst:
            return run_process()
        elif "menu_reports" in lst:
            return reports("reports")
        elif "menu_savings" in lst:
            return reports("savings")
        elif "menu_solar" in lst:
            return solar()
        elif "menu_settings" in lst:
            return settings()
        else:
            return home()


@app.route("/home", methods=["POST", "GET"])
def home():
    subjects = ["balans"]
    views = ["grafiek", "tabel"]
    cur_subject = "grid"
    active_subject = "grid"
    cur_view = "grafiek"
    #global active_view 
    global previous_time
    active_time = None
    action = None
    confirm_delete = False
    #get active_view from session if available, otherwise use the default value; 
    #this is to enable switching between grafiek and tabel while retaining the active time  
    active_view = flask_session.get('active_view', 'grafiek')

    if config is not None:
        battery_options = config.battery
        for b in range(len(battery_options)):
            subjects.append(battery_options[b].name)
    if request.method == "POST":
        # ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        lst = request.form.to_dict(flat=False)
        # print('Home:', lst)
        if "cur_subject" in lst:
        #   active_subject = lst["cur_subject"][0]
            cur_subject = lst["cur_subject"][0]
        if "cur_view" in lst:
        #   active_view = lst["cur_view"][0]
            cur_view = lst["cur_view"][0]
        if "subject" in lst:
            active_subject = lst["subject"][0]
        if "view" in lst:
            active_view = lst["view"][0]
            flask_session['active_view'] = active_view #update session with the new active_view
        if "active_time" in lst:
            # Ignore active_time from POST if switching between grafiek & table; keep the active_time from the previous call from session.
            if cur_view != active_view:
                active_time = flask_session.get('active_time')
            else:
                active_time = float(lst["active_time"][0])
        if "action" in lst:
            action = lst["action"][0]
        if "file_delete" in lst:
            confirm_delete = lst["file_delete"][0] == "delete"

#  Every mouse click on Home page calls the home() function
#  By design; the get_file_list() is called over and over again to ensure an accurate reflection of the files
#  Files might have been added/removed since last call
    
    if active_view == "grafiek":
        active_map = "/images/"
        active_filter = "*.png"
    else:
        active_map = "/log/"
        active_filter = "*.log"
        
    flist = get_file_list(app_datapath + active_map, active_filter)
    index = 0
    
    if active_time:
        # Find index in the current flist with timestamp closest to active_time (possibly from other flist)
        # The timestamp between e.g. calc_2026-02-17__08-45.png & calc_2026-02-17__08-45.log are NOT identical
        # The intent is to be able to switch between grafiek and table while keeping the active time
        active_time = float(active_time)
        diff_time = active_time # high intialization value
        for i in range(len(flist)):
            if abs(flist[i]["time"] - active_time) < diff_time:
                diff_time = abs(flist[i]["time"] - active_time)
                index = i
    # Ensure index is within valid range
    index = max(0, min(index, len(flist) - 1))

    if action == "first":
        index = 0
    if action == "previous":
        index = max(0, index - 1)
    if action == "next":
        index = min(len(flist) - 1, index + 1)
    if action == "last":
        index = len(flist) - 1
        
    if action in ["fast_forward", "fast_reverse"]:
        if type( active_time ) != float:
            active_time = float(active_time)
        if action == "fast_forward":
            target_time = active_time - (6 * 3600) # Add 6 hours
        if action == "fast_reverse":
            target_time = active_time + (6 * 3600) # Subtract 6 hours
        diff_time = active_time # high intialization value
        for i in range(len(flist)):
            if abs(flist[i]["time"] - target_time) < diff_time:
               diff_time = abs(flist[i]["time"] - target_time)
               index = i
        
    if action == "delete" and confirm_delete:
        os.remove(app_datapath + active_map + flist[index]["name"])
        flist = get_file_list(app_datapath + active_map, active_filter)
        index = min(len(flist) - 1, index)


    if len(flist) > 0:
        # print('Active index:', index )
        # print(flist[index]["name"], datetime.datetime.fromtimestamp(flist[index]["time"]))
        active_time = str(flist[index]["time"])
        if active_view == "grafiek":
            image = os.path.join(web_datapath + active_map, flist[index]["name"])
            tabel = None
        else:
            image = None
            with open(app_datapath + active_map + flist[index]["name"], "r") as f:
                tabel = f.read()
    else:
        active_time = None
        image = None
        tabel = None
        
# Remember this active time in global variable
    #previous_time = active_time
    flask_session['active_time'] = active_time #Store active_time in session to enable switching between grafiek and tabel while retaining the active time  

    flatpickr_times = [datetime.datetime.fromtimestamp(f["time"]).strftime('%Y-%m-%d %H:%M') for f in flist]
    flatpickr_default_ts = float(active_time) if active_time else None
    flatpickr_default = datetime.datetime.fromtimestamp(float(active_time)).strftime('%Y-%m-%d %H:%M') if active_time else ''

    return render_template(
        "home.html",
        title="Optimization",
        active_menu_list=web_menu_items,
        active_menu="home",
        subjects=subjects,
        views=views,
        active_subject=active_subject,
        active_view=active_view,
        image=image,
        tabel=tabel,
        active_time=active_time,
        flatpickr_times=flatpickr_times,
        flatpickr_default_ts=flatpickr_default_ts,
        flatpickr_default=flatpickr_default,
        version=__version__,
    )


@app.route("/run", methods=["POST", "GET"])
def run_process():
    bewerking = ""
    current_bewerking = ""
    log_content = ""
    parameters = {}

    if request.method in ["POST", "GET"]:
        dct = request.form.to_dict(flat=False)
        if "current_bewerking" in dct:
            current_bewerking = dct["current_bewerking"][0]
            run_bewerking = bewerkingen[current_bewerking]
            extra_parameters = []
            if "parameters" in run_bewerking:
                for j in range(len(run_bewerking["parameters"])):
                    if run_bewerking["parameters"][j] in dct:
                        param_value = dct[run_bewerking["parameters"][j]][0]
                        if len(param_value) > 0:
                            extra_parameters.append(param_value)
            cmd = run_bewerking["cmd"] + extra_parameters
            bewerking = ""
            proc = run(cmd, stdout=PIPE, stderr=PIPE)
            data = proc.stdout.decode()
            err = proc.stderr.decode()
            log_content = data + err
            filename = (
                "../data/log/"
                + run_bewerking["file_name"]
                + "_"
                + datetime.datetime.now().strftime("%Y-%m-%d__%H:%M:%S")
                + ".log"
            )
            with open(filename, "w") as f:
                f.write(log_content)
        else:
            for i in range(len(dct.keys())):
                bew = list(dct.keys())[i]
                if bew in bewerkingen:
                    bewerking = bew
                    if "parameters" in bewerkingen[bewerking]:
                        for j in range(len(bewerkingen[bewerking]["parameters"])):
                            if bewerkingen[bewerking]["parameters"][j] in dct:
                                param_str = bewerkingen[bewerking]["parameters"][j]
                                param_value = dct[
                                    bewerkingen[bewerking]["parameters"][j]
                                ][0]
                                parameters[param_str] = param_value
                    break

    return render_template(
        "run.html",
        title="Run",
        active_menu_list=web_menu_items,
        active_menu="run",
        bewerkingen=bewerkingen,
        bewerking=bewerking,
        current_bewerking=current_bewerking,
        parameters=parameters,
        log_content=log_content,
        version=__version__,
    )


@app.route("/reports", methods=["POST", "GET"])
def reports(active_menu: str):
    report = Report(app_datapath + "/options.json")
    menu_dict = web_menu[active_menu]
    title = menu_dict["name"]
    subjects_lst = list(menu_dict["submenu"].keys())
    active_subject = subjects_lst[0]
    views_lst = list(menu_dict["submenu"][active_subject]["views"].keys())
    active_view = views_lst[0]
    period_lst = menu_dict["submenu"][active_subject]["periods"]["list"]
    active_period = period_lst[0]
    show_prognose = False
    met_prognose = False
    if request.method in ["POST", "GET"]:
        # ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        lst = request.form.to_dict(flat=False)
        if "cur_subject" in lst:
            active_subject = lst["cur_subject"][0]
            if active_subject not in subjects_lst:
                active_subject = subjects_lst[0]
        if "cur_view" in lst:
            active_view = lst["cur_view"][0]
        if "cur_periode" in lst:
            active_period = lst["cur_periode"]
        if "subject" in lst:
            active_subject = lst["subject"][0]
            period_lst = menu_dict["submenu"][active_subject]["periods"]["list"]
        if "view" in lst:
            active_view = lst["view"][0]
        if "periode-select" in lst:
            active_period = lst["periode-select"][0]
        if not (active_period in period_lst):
            active_period = period_lst[0]
        if "met_prognose" in lst:
            met_prognose = lst["met_prognose"][0]
    tot = None
    if active_period in menu_dict["submenu"][active_subject]["periods"]["prognose"]:
        show_prognose = True
    else:
        show_prognose = False
        met_prognose = False
    if not met_prognose:
        now = datetime.datetime.now()
        tot = report.periodes[active_period]["tot"]
        if (
            active_period in menu_dict["submenu"][active_subject]["periods"]["prognose"]
            or menu_dict["submenu"][active_subject]["periods"]["prognose"] == []
        ):
            tot = min(tot, datetime.datetime(now.year, now.month, now.day, now.hour))
    views_lst = list(menu_dict["submenu"][active_subject]["views"].keys())
    period_lst = menu_dict["submenu"][active_subject]["periods"]["list"]
    active_interval = report.periodes[active_period]["interval"]
    if active_menu == "reports":
        if active_subject == "grid":
            report_df = report.get_grid_data(active_period, _tot=tot)
            report_df = report.calc_grid_columns(
                report_df, active_interval, active_view
            )
        elif active_subject == "balans":
            report_df, lastmoment = report.get_energy_balance_data(
                active_period, _tot=tot
            )
            report_df = report.calc_balance_columns(
                report_df, active_interval, active_view
            )
        else:  # co2
            report_df = report.calc_co2_emission(
                active_period,
                _tot=tot,
                active_interval=active_interval,
                active_view=active_view,
            )
        report_df.round(3)
    else:  # savings
        calc_function = getattr(
            report, menu_dict["submenu"][active_subject]["calculate"]
        )
        report_df = calc_function(
            active_period,
            _tot=tot,
            active_interval=active_interval,
            active_view=active_view,
        )
    if active_view == "tabel":
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
        if active_menu == "reports":
            if active_subject == "grid":
                report_data = report.make_graph(report_df, active_period)
            elif active_subject == "balans":
                report_data = report.make_graph(
                    report_df, active_period, report.balance_graph_options
                )
            else:  # co2
                report_data = report.make_graph(
                    report_df, active_period, report.co2_graph_options
                )
        else:  # "savings"
            graph_options = getattr(
                report, menu_dict["submenu"][active_subject]["graph_options"]
            )
            report_data = report.make_graph(report_df, active_period, graph_options)
    return render_template(
        "report.html",
        title=title,
        active_menu_list=web_menu_items,
        active_menu=active_menu,
        subjects=subjects_lst,
        views=views_lst,
        periode_options=period_lst,
        active_period=active_period,
        show_prognose=show_prognose,
        met_prognose=met_prognose,
        active_subject=active_subject,
        active_view=active_view,
        report_data=report_data,
        version=__version__,
    )


@app.route("/solar", methods=["POST", "GET"])
def solar():
    report = Report(app_datapath + "/options.json")
    menu_dict = web_menu["solar"]
    title = menu_dict["name"]
    subjects_lst = list(menu_dict["submenu"]["items"].keys())
    active_subject = subjects_lst[0]
    views_lst = list(menu_dict["submenu"]["views"].keys())
    active_view = views_lst[0]
    active_date = datetime.date.today()

    if request.method in ["POST", "GET"]:
        lst = request.form.to_dict(flat=False)
        if "cur_subject" in lst:
            active_subject = lst["cur_subject"][0]
            if active_subject not in subjects_lst:
                active_subject = subjects_lst[0]
        if "cur_view" in lst:
            active_view = lst["cur_view"][0]
        if "subject" in lst:
            active_subject = lst["subject"][0]
        if "view" in lst:
            active_view = lst["view"][0]
        if "active_date" in lst:
            active_date = datetime.datetime.strptime(
                lst["active_date"][0], "%Y-%m-%d"
            ).date()
        if "action" in lst:
            action = lst["action"][0]
            if action == "previous":
                active_date -= datetime.timedelta(days=1)
            else:
                active_date += datetime.timedelta(days=1)
    report_df = report.calc_solar_data(
        solar_items[active_subject], active_date, active_view
    )
    report_df.round(3)
    if active_view == "tabel":
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
        report_data = report.make_graph(
            report_df,
            "vandaag",
            _options=report.solar_graph_options,
            _title=f"Solar production {active_date.strftime('%Y-%m-%d')}",
        )
    return render_template(
        "solar.html",
        title=title,
        active_menu_list=web_menu_items,
        active_menu="solar",
        subjects=subjects_lst,
        views=views_lst,
        active_subject=active_subject,
        active_view=active_view,
        active_date=active_date,
        report_data=report_data,
        version=__version__,
    )


@app.route("/settings/<filename>", methods=["POST", "GET"])
def settings():
    def get_file(fname):
        with open(fname, "r") as file:
            return file.read()

    settngs = ["options", "secrets"]
    active_setting = "options"
    cur_setting = ""
    lst = request.form.to_dict(flat=False)
    if request.method in ["POST", "GET"]:
        if "cur_setting" in lst:
            active_setting = lst["cur_setting"][0]
            cur_setting = active_setting
        if "setting" in lst:
            active_setting = lst["setting"][0]
    message = None
    filename_ext = app_datapath + active_setting + ".json"

    options = None
    if (cur_setting != active_setting) or ("setting" in lst):
        options = get_file(filename_ext)
    else:
        lst = request.form.to_dict(flat=False)
        if "codeinput" in lst:
            updated_data = request.form["codeinput"]
            if "action" in lst:
                action = request.form["action"]
                if action == "update":
                    try:
                        # json_data = json.loads(updated_data)
                        # Update the JSON data
                        with open(filename_ext, "w") as f:
                            f.write(updated_data)
                        message = "JSON data updated successfully"
                        check_web_menu_items()
                    except Exception as err:
                        message = "Error: " + err.args[0]
                    options = updated_data
                if action == "cancel":
                    options = get_file(filename_ext)
        else:
            # Load initial JSON data from a file
            options = get_file(filename_ext)
    return render_template(
        "settings.html",
        title="Instellingen",
        active_menu_list=web_menu_items,
        active_menu="settings",
        settings=settngs,
        active_setting=active_setting,
        options_data=options,
        message=message,
        version=__version__,
    )


'''
@app.route('/api/prognose/<string:fld>', methods=['GET'])
def api_prognose(fld: str):
    """
    retourneert in json de data van
    :param fld: de code van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    report = dao.prog.da_report.Report()
    start = request.args.get('start')
    end = request.args.get('end')
    data = report.get_api_data(fld, prognose=True, start=start, end=end)
    return jsonify({'data': data})
'''


@app.route("/api/report/<string:fld>/<string:periode>", methods=["GET"])
def api_report(fld: str, periode: str):
    """
    Retourneert in json de data van
    :param fld: de code van de gevraagde data
    :param periode: de periode van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    cumulate = request.args.get("cumulate")
    report = Report(app_datapath + "/options.json")
    # start = request.args.get('start')
    # end = request.args.get('end')
    if cumulate is None:
        cumulate = False
    else:
        try:
            cumulate = int(cumulate)
            cumulate = cumulate == 1
        except ValueError:
            cumulate = False
    result = report.get_api_data(fld, periode, cumulate=cumulate)
    return result


@app.route("/api/run/<string:bewerking>", methods=["GET", "POST"])
def run_api(bewerking: str):
    if bewerking in bewerkingen.keys():
        proc = run(bewerkingen[bewerking]["cmd"], capture_output=True, text=True)
        data = proc.stdout
        err = proc.stderr
        log_content = data + err
        filename = (
            "../data/log/"
            + bewerkingen[bewerking]["file_name"]
            + "_"
            + datetime.datetime.now().strftime("%Y-%m-%d__%H:%M")
            + ".log"
        )
        with open(filename, "w") as f:
            f.write(log_content)
        return render_template(
            "api_run.html",
            log_content=log_content,
            version=__version__,
            active_menu_list=web_menu_items,
        )
    else:
        return "Onbekende bewerking: " + bewerking
