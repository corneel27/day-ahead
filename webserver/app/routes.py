import datetime
import glob
import os
from webserver.app import app
from flask import render_template, request, jsonify, Response
import json, fnmatch
import os
from  subprocess import Popen, PIPE, run
import logging
from datetime import date
from logging.handlers import TimedRotatingFileHandler
from prog.da_config import Config
import prog.da_report

web_datapath = "static/data/"
app_datapath = "app/static/data/"
images_folder = os.path.join(web_datapath, 'images')
config = Config(app_datapath + "options.json")

logname = "dashboard.log"
handler = TimedRotatingFileHandler("../data/log/" + logname, when="midnight",
                                   backupCount=config.get(["history", "save days"]))
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
        "task": "calc_optimum"},
    "calc_zonder_debug": {
        "name": "Optimaliseringsberekening zonder debug",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "calc"],
        "task": "calc_optimum"},
    "get_tibber": {
        "name": "Verbruiksgegevens bij Tibber ophalen",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "tibber"],
        "task": "get_tibber_data"},
    "get_meteo": {
        "name": "Meteoprognoses ophalen",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "meteo"],
        "task": "get_meteo_data"},
    "get_prices": {
        "name": "Day ahead prijzen ophalen",
        "cmd": [
            "python3",
            "../prog/day_ahead.py",
            "prices"],
        "task": "get_day_ahead_prices"},
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


@app.route('/settings/<filename>', methods=['POST', 'GET'])
def settings(filename):
    def get_file(fname):
        with open(fname, 'r') as f:
            return f.read()
    message = None
    filename_ext = app_datapath + filename + ".json"
    if request.method == 'POST':
        updated_data = request.form["codeinput"]
        action = request.form["action"]
        if action == "update":
            try:
                json_data = json.loads(updated_data)
                # Update the JSON data
                with open(filename_ext, 'w') as f:
                    f.write(updated_data)
                message = 'JSON data updated successfully'
            except Exception as err:
                message = 'Error: ' + err.args[0]
            options = updated_data
        if action == 'cancel':
           options = get_file(filename_ext)
    else:
        # Load initial JSON data from a file
        options = get_file(filename_ext)
    return render_template('settings.html', title='Instellingen', options_data=options, message=message)


@app.route('/', methods=['POST', 'GET'])
@app.route('/home', methods=['POST', 'GET'])
def home():
    subjects = ["grid"]
    views = ["grafiek", "tabel"]
    active_subject = "grid"
    active_view = "grafiek"
    active_time = None
    action = None
    battery_options = config.get(["battery"])
    for b in range(len(battery_options)):
        subjects.append(battery_options[b]["name"])
    if request.method == 'POST':
        # ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        list = request.form.to_dict(flat=False)
        if "cur_subject" in list:
            active_subject = list["cur_subject"][0]
        if "cur_view" in list:
            active_view = list["cur_view"][0]
        if "subject" in list:
            active_subject = list["subject"][0]
        if "view" in list:
            active_view = list["view"][0]
        if "active_time" in list:
            active_time = float(list["active_time"][0])
        if "action" in list:
            action = list["action"][0]

    if active_view == "grafiek":
        active_map = "/images/"
        active_filter = "optimum*.png"
    else:
        active_map = "/log/"
        active_filter = "calc_optimum*.log"
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
    active_time = str(flist[index]["time"])
    if active_view == "grafiek":
        image = os.path.join(web_datapath + active_map, flist[index]["name"])
        tabel = None
    else:
        image = None
        with open(app_datapath + active_map + flist[index]["name"], 'r') as f:
            tabel = f.read()

    return render_template('home.html', title='Optimalisering', subjects=subjects, views=views,
                           active_subject=active_subject, active_view=active_view, image=image, tabel=tabel,
                           active_time=active_time)


@app.route('/reports', methods=['POST', 'GET'])
def reports():
    report = prog.da_report.Report()
    subjects = ["grid", "distribution"]
    active_subject = "grid"
    views = ["grafiek", "tabel"]
    active_view = "tabel"
    periode_options = report.periodes.keys()
    active_period = "vandaag"
    met_prognose = False
    if request.method in ['POST', 'GET']:
        # ImmutableMultiDict([('cur_subject', 'Accu2'), ('subject', 'Accu1')])
        list = request.form.to_dict(flat=False)
        if "cur_subject" in list:
            active_subject = list["cur_subject"][0]
        if "cur_view" in list:
            active_view = list["cur_view"][0]
        if "cur_periode" in list:
            active_period = list["cur_periode"]
        if "subject" in list:
            active_subject = list["subject"][0]
        if "view" in list:
            active_view = list["view"][0]
        if "periode-select" in list:
            active_period = list["periode-select"][0]
        if "met_prognose" in list:
            met_prognose = list["met_prognose"][0]
    tot = None
    if (active_period == "vandaag" or active_period == "deze week" or active_period == "deze maand" or
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
        report_df = report.get_distribution_data(active_period, _tot=tot)
    filtered_df.round(1)
    if active_view == "tabel":
        report_data = [filtered_df.to_html(index=False, justify="right", decimal=",", classes="data", border=0)]
    else:
        report_data = report.make_graph(filtered_df, active_period, None)

    return render_template('report.html', title='Rapportage', subjects=subjects, views=views,
                           periode_options=periode_options, active_period=active_period, met_prognose=met_prognose,
                           active_subject=active_subject, active_view=active_view, report_data=report_data)


@app.route('/api/prognose/<string:fld>', methods=['GET'])
def api_prognose(fld: str):
    """
    retourneert in json de data van
    :param fld: de code van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    report = prog.da_report.Report()
    start = request.args.get('start')
    end = request.args.get('end')
    data = report.get_api_data(fld, prognose=True, start=start, end=end)
    return jsonify({'data': data})


@app.route('/api/report/<string:fld>/<string:periode>', methods=['GET'])
def api_report(fld: str, periode: str):
    """
    retourneert in json de data van
    :param fld: de code van de gevraagde data
    :param periode: de periode van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    cumulate = request.args.get('cumulate')
    report = prog.da_report.Report()
    # start = request.args.get('start')
    # end = request.args.get('end')
    try:
        cumulate = int(cumulate)
        cumulate = cumulate == 1
    except:
        cumulate = False
    result = report.get_api_data(fld, periode, cumulate=cumulate)
    return result

import codecs
@app.route('/api/run/<string:bewerking>', methods=['GET','POST'])
def run_api(bewerking: str):
    if bewerking in bewerkingen.keys():
        proc = run(bewerkingen[bewerking]["cmd"], capture_output=True, text=True)
        data =  proc.stdout
        err = proc.stderr
        log_content = data + err
        filename = "../data/log/" + bewerkingen[bewerking]["task"] + \
                   datetime.datetime.now().strftime("%H%M") + ".log"
        with open(filename, "w") as f:
            f.write(log_content)
        return render_template("api_run.html", log_content=log_content)
    else:
        return "Onbekende bewerking: "+ bewerking

@app.route('/run', methods=['POST', 'GET'])
def run_process():
    bewerking = ""
    current_bewerking = ""
    log_content = ""

    if request.method in ['POST', 'GET']:
        dict = request.form.to_dict(flat=False)
        if "current_bewerking" in dict:
            current_bewerking = dict["current_bewerking"][0]
            bewerking = ""
            proc = run(bewerkingen[current_bewerking]["cmd"], stdout=PIPE, stderr=PIPE)
            data = proc.stdout.decode()
            err = proc.stderr.decode()
            log_content = data + err
            filename = "../data/log/" + bewerkingen[current_bewerking]["task"] +\
                        datetime.datetime.now().strftime("%H%M") + ".log"
            with open(filename, "w") as f:
                f.write(log_content)
        else:
            if len(dict) == 1 :
                bewerking = list(dict.keys())[0]

    return render_template('run.html', title='Run', bewerkingen=bewerkingen, bewerking=bewerking,
                           current_bewerking=current_bewerking, log_content=log_content)

