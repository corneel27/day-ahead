import datetime

from sqlalchemy.sql.coercions import expect_col_expression_collection

from dao.webserver.app import app
from flask import render_template, request
import fnmatch
import os
from subprocess import PIPE, run
import logging
from logging.handlers import TimedRotatingFileHandler
from dao.prog.da_config import Config
import dao.prog.da_report
from dao.prog.version import __version__

web_datapath = "static/data/"
app_datapath = "app/static/data/"
images_folder = os.path.join(web_datapath, 'images')
try:
    config = Config(app_datapath + "options.json")
except ValueError as ex:
    logging.error(app_datapath)
    logging.error(ex)
    config = None

logname = "dashboard.log"
handler = TimedRotatingFileHandler("../data/log/" + logname, when="midnight",
                                   backupCount=1 if config is None else
                                   config.get(["history", "save days"]))
handler.suffix = "%Y%m%d"
handler.setLevel(logging.INFO)
logging.basicConfig(level=logging.DEBUG, handlers=[handler],
                    format=f'%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

bewerkingen = {
    "calc_met_debug": {
        "name": "Optimaliseringsberekening met debug",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "debug",
            "calc"],
        "task": "calc_optimum",
        "file_name": "calc_debug"},
    "calc_zonder_debug": {
        "name": "Optimaliseringsberekening zonder debug",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "calc"],
        "task": "calc_optimum",
        "file_name": "calc"},
    "get_tibber": {
        "name": "Verbruiksgegevens bij Tibber ophalen",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "tibber"],
        "task": "get_tibber_data",
        "file_name": "tibber"},
    "get_meteo": {
        "name": "Meteoprognoses ophalen",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "meteo"],
        "task": "get_meteo_data",
        "file_name": "meteo"},
    "get_prices": {
        "name": "Day ahead prijzen ophalen",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "prices"],
        "task": "get_day_ahead_prices",
        "parameters":
            ["prijzen_start", "prijzen_tot"],
        "file_name": "prices",
    },
    "calc_baseloads": {
        "name": "Bereken de baseloads",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "calc_baseloads"],
        "task": "calc_baseloads",
        "file_name": "baseloads"},
}


def get_file_list(path: str, pattern: str) -> list:
    """
    get a time-ordered file list with name and modified time
    :parameter path: folder
    :parameter pattern: wildcards to search for
    """
    flist = []
    for f in os.listdir(path):
        if fnmatch.fnmatch(f, pattern):
            fullname = os.path.join(path, f)
            flist.append({"name": f, "time": os.path.getmtime(fullname)})
            # print(f, time.ctime(os.path.getmtime(f)))
    flist.sort(key=lambda x: x.get('time'), reverse=True)
    return flist


@app.route('/', methods=['POST', 'GET'])
def menu():
    lst = request.form.to_dict(flat=False)
    if "current_menu" in lst:
        current_menu = lst["current_menu"][0]
        if current_menu == "home":
            return home()
        elif current_menu == "run":
            return run_process()
        elif current_menu == "reports":
            return reports()
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
            return reports()
        elif "menu_settings" in lst:
            return settings()
        else:
            return home()


@app.route('/home', methods=['POST', 'GET'])
def home():
    subjects = ["balans"]
    views = ["grafiek", "tabel"]
    active_subject = "grid"
    active_view = "grafiek"
    active_time = None
    action = None
    if config is not None:
        battery_options = config.get(["battery"])
        for b in range(len(battery_options)):
            subjects.append(battery_options[b]["name"])
    if request.method == 'POST':
        # ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        lst = request.form.to_dict(flat=False)
        if "cur_subject" in lst:
            active_subject = lst["cur_subject"][0]
        if "cur_view" in lst:
            active_view = lst["cur_view"][0]
        if "subject" in lst:
            active_subject = lst["subject"][0]
        if "view" in lst:
            active_view = lst["view"][0]
        if "active_time" in lst:
            active_time = float(lst["active_time"][0])
        if "action" in lst:
            action = lst["action"][0]

    if active_view == "grafiek":
        active_map = "/images/"
        active_filter = "*.png"
    else:
        active_map = "/log/"
        active_filter = "*.log"
    flist = get_file_list(app_datapath + active_map, active_filter)
    index = 0
    if active_time:
        for i in range(len(flist)):
            if flist[i]["time"] == active_time:
                index = i
                break
    if action == "first":
        index = 0
    if action == "previous":
        index = max(0, index - 1)
    if action == "next":
        index = min(len(flist) - 1, index + 1)
    if action == "last":
        index = len(flist) - 1
    if action == "delete":
        os.remove(app_datapath + active_map + flist[index]["name"])
        flist = get_file_list(app_datapath + active_map, active_filter)
        index = min(len(flist) - 1, index)
    if len(flist) > 0:
        active_time = str(flist[index]["time"])
        if active_view == "grafiek":
            image = os.path.join(web_datapath + active_map, flist[index]["name"])
            tabel = None
        else:
            image = None
            with open(app_datapath + active_map + flist[index]["name"], 'r') as f:
                tabel = f.read()
    else:
        active_time = None
        image = None
        tabel = None

    return render_template('home.html', title='Optimization', active_menu="home",
                           subjects=subjects, views=views,
                           active_subject=active_subject,
                           active_view=active_view,
                           image=image, tabel=tabel,
                           active_time=active_time,
                           version=__version__)


@app.route('/run', methods=['POST', 'GET'])
def run_process():
    bewerking = ""
    current_bewerking = ""
    log_content = ""
    parameters = {}

    if request.method in ['POST', 'GET']:
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
            filename = ("../data/log/" + run_bewerking["file_name"] + "_" +
                        datetime.datetime.now().strftime("%Y-%m-%d__%H:%M:%S") + ".log")
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
                                param_value = dct[bewerkingen[bewerking]["parameters"][j]][0]
                                parameters[param_str] = param_value
                    break

    return render_template('run.html', title='Run', active_menu="run",
                           bewerkingen=bewerkingen, bewerking=bewerking,
                           current_bewerking=current_bewerking,
                           parameters=parameters,
                           log_content=log_content,
                           version=__version__)


@app.route('/reports', methods=['POST', 'GET'])
def reports():
    report = dao.prog.da_report.Report(app_datapath+"/options.json")
    subjects = ["grid", "balans"]
    active_subject = "grid"
    views = ["grafiek", "tabel"]
    active_view = "tabel"
    periode_options = report.periodes.keys()
    active_period = "vandaag"
    met_prognose = False
    if request.method in ['POST', 'GET']:
        # ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        lst = request.form.to_dict(flat=False)
        if "cur_subject" in lst:
            active_subject = lst["cur_subject"][0]
        if "cur_view" in lst:
            active_view = lst["cur_view"][0]
        if "cur_periode" in lst:
            active_period = lst["cur_periode"]
        if "subject" in lst:
            active_subject = lst["subject"][0]
        if "view" in lst:
            active_view = lst["view"][0]
        if "periode-select" in lst:
            active_period = lst["periode-select"][0]
        if "met_prognose" in lst:
            met_prognose = lst["met_prognose"][0]
    tot = None
    if (active_period == "vandaag" or
            active_period == "deze week" or
            active_period == "deze maand" or
            active_period == "dit contractjaar"):
        if not met_prognose:
            now = datetime.datetime.now()
            tot = datetime.datetime(now.year, now.month, now.day, now.hour)
    else:
        met_prognose = False
    active_interval = report.periodes[active_period]["interval"]
    if active_subject == "grid":
        report_df = report.get_grid_data(active_period, _tot=tot)
        filtered_df = report.calc_grid_columns(report_df, active_interval, active_view)
    else:
        report_df = report.get_energy_balance_data(active_period, _tot=tot)
        filtered_df = report.calc_balance_columns(report_df, active_interval, active_view)
    filtered_df.round(3)
    if active_view == "tabel":
        report_data = [filtered_df.to_html(index=False, justify="right", decimal=",",
                                           classes="data", border=0,
                                           float_format='{:.3f}'.format)]
    else:
        if active_subject == "grid":
            report_data = report.make_graph(filtered_df, active_period)
        else:
            report_data = report.make_graph(filtered_df, active_period,
                                            report.balance_graph_options)

    return render_template('report.html', title='Rapportage', active_menu="reports",
                           subjects=subjects, views=views, periode_options=periode_options,
                           active_period=active_period, met_prognose=met_prognose,
                           active_subject=active_subject,
                           active_view=active_view,
                           report_data=report_data,
                           version=__version__)


@app.route('/settings/<filename>', methods=['POST', 'GET'])
def settings():
    def get_file(fname):
        with open(fname, 'r') as file:
            return file.read()
    settngs = ["options", "secrets"]
    active_setting = "options"
    cur_setting = ""
    lst = request.form.to_dict(flat=False)
    if request.method in ['POST', 'GET']:
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
                        with open(filename_ext, 'w') as f:
                            f.write(updated_data)
                        message = 'JSON data updated successfully'
                    except Exception as err:
                        message = 'Error: ' + err.args[0]
                    options = updated_data
                if action == "cancel":
                    options = get_file(filename_ext)
        else:
            # Load initial JSON data from a file
            options = get_file(filename_ext)
    return render_template('settings.html', title='Instellingen', active_menu="settings",
                           settings=settngs, active_setting=active_setting, options_data=options,
                           message=message, version=__version__)


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


@app.route('/api/report/<string:fld>/<string:periode>', methods=['GET'])
def api_report(fld: str, periode: str):
    """
    Retourneert in json de data van
    :param fld: de code van de gevraagde data
    :param periode: de periode van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    cumulate = request.args.get('cumulate')
    expected = request.args.get('expected')
    report = dao.prog.da_report.Report(app_datapath+"/options.json")
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

    if expected is None:
        expected = False
    else:
        try:
            expected = int(expected)
            expected = expected == 1
        except ValueError:
            expected = False
    result = report.get_api_data(fld, periode, cumulate=cumulate, expected=expected)
    return result


@app.route('/api/run/<string:bewerking>', methods=['GET', 'POST'])
def run_api(bewerking: str):
    if bewerking in bewerkingen.keys():
        proc = run(bewerkingen[bewerking]["cmd"], capture_output=True, text=True)
        data = proc.stdout
        err = proc.stderr
        log_content = data + err
        filename = "../data/log/" + bewerkingen[bewerking]["file_name"] + "_" + \
                   datetime.datetime.now().strftime("%Y-%m-%d__%H:%M") + ".log"
        with open(filename, "w") as f:
            f.write(log_content)
        return render_template("api_run.html", log_content=log_content)
    else:
        return "Onbekende bewerking: " + bewerking
