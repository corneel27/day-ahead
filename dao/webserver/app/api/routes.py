import datetime
from flask import Blueprint, request
from subprocess import run as subprocess_run
from dao.prog.da_report import Report
from markupsafe import escape
from dao.prog.da_base import DaBase
from datetime import datetime
from zoneinfo import ZoneInfo


api = Blueprint("api", __name__)

# globals
app_datapath = "app/static/data/"

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


@api.route("/report/<string:fld>/<string:periode>", methods=["GET"])
def api_report(fld: str, periode: str):
    """
    Retourneert in json de data van
    :param fld: de code van de gevraagde data
    :param periode: de periode van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    cumulate = request.args.get("cumulate")
    cumulate = escape(cumulate)
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
    fld = str(escape(fld))
    periode = str(escape(periode))
    result = report.get_api_data(fld, periode, cumulate=cumulate)

    headers = {
        "Content-Type": "application/json",
    }
    return result, headers


@api.route("/run/<string:bewerking>", methods=["GET", "POST"])
def run_api(bewerking: str):
    if bewerking in bewerkingen.keys():
        proc = subprocess_run(bewerkingen[bewerking]["cmd"], capture_output=True, text=True)
        data = proc.stdout
        err = proc.stderr
        log_content = data + err
        filename = (
            "../data/log/"
            + bewerkingen[bewerking]["file_name"]
            + "_"
            + datetime.datetime.now().strftime("%Y-%m-%d__%H:%M:%S")
            + ".log"
        )
        with open(filename, "w") as f:
            f.write(log_content)

        headers = {
            "Content-Type": "plain/text",
        }
        return log_content, headers
    else:
        return "Onbekende bewerking: " + bewerking, 400


@api.route("/data/")
def data():
    """
    Retourneert in json de data
    :return: de gevraagde data in json formaat
    """
    data_report = Report()
    start = request.args.get('start')
    end = request.args.get('end')
    aggregate = request.args.get('aggregate')
    fields = request.args.get('fields')

    if fields:
        fields = fields.split(",")

    timezone_raw = request.args.get('timezone') if None else "Europe/Amsterdam"

    try:
        data = data_report.get_data(
            start=datetime.fromisoformat(start).replace(tzinfo=ZoneInfo(timezone_raw)),
            end=datetime.fromisoformat(end).replace(tzinfo=ZoneInfo(timezone_raw)),
            aggregate=aggregate,
            var_codes=fields,
        )

    except Exception as e:
        return {"error": str(e)}, 500

    def format_ts(dt, aggregate: str) -> str:
        if aggregate == "15min":
            return dt.strftime("%Y-%m-%d %H:%M")
        elif aggregate == "hour":
            return dt.strftime("%Y-%m-%d %H:00")
        else:
            return dt.strftime("%Y-%m-%d")

    data = [
        {**row, "ts": format_ts(row["ts"], aggregate)}
        for row in data
    ]

    return data

@api.route("/run/<string:task>")
def run(task: str):
    tasks = DaBase.generate_tasks()
    if task in tasks.keys():
        proc = subprocess_run(tasks[task]["cmd"], capture_output=True, text=True)
        data = proc.stdout
        err = proc.stderr
        log_content = data + err

        return log_content, {"Content-Type": "text/plain"}
    else:
        return "Unknown task: " + escape(task)


# @api.route("/data-sql-ha/")
# def data_sql_ha():
#     """
#     Retourneert in json de data
#     :return: de gevraagde data in json formaat
#     """
#     data_report = Report()
#     start = request.args.get('start')
#     end = request.args.get('end')
#     aggregate = request.args.get('aggregate')
#     fields = request.args.get('fields')
#
#     if fields:
#         fields = fields.split(",")
#
#     timezone_raw = request.args.get("timezone") if None else "Europe/Amsterdam"
#
#     query = data_report.get_ha_data_query(
#             start=datetime.fromisoformat(start).replace(tzinfo=ZoneInfo(timezone_raw)),
#             end=datetime.fromisoformat(end).replace(tzinfo=ZoneInfo(timezone_raw)),
#             var_codes=fields,
#             step=timedelta(days=1)
#         )
#
#     return str(query)