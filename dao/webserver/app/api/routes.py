from datetime import datetime
from flask import Blueprint, current_app, request
from subprocess import run as subprocess_run
from dao.prog.da_report import Report
from markupsafe import escape
from dao.prog.da_const import tasks
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

api = Blueprint("api", __name__)

# globals
app_datapath = "app/static/data/"
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROG_DIR = BASE_DIR / "prog"


@api.route("/report/<string:fld>/<string:periode>", methods=["GET"])
def api_report(fld: str, periode: str):
    """
    Retourneert in json de data van
    :param fld: de code van de gevraagde data
    :param periode: de periode van de gevraagde data
    :return: de gevraagde data in json formaat
    """
    cumulate = request.args.get("cumulate", type=int)
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


@api.route("/run/<string:task>", methods=["GET", "POST"])
def run_api(task: str):
    if task in tasks.keys():
        proc = subprocess_run(
            tasks[task]["cmd"],
            cwd=PROG_DIR,
            capture_output=True,
            text=True
        )
        data = proc.stdout
        err = proc.stderr
        log_content = data + err
        filename = (
                "../data/log/"
                + tasks[task]["file_name"]
                + "_"
                + datetime.now().strftime("%Y-%m-%d__%H:%M:%S")
                + ".log"
        )
        with open(filename, "w") as f:
            f.write(log_content)

        headers = {
            "Content-Type": "text/plain",
        }
        return log_content, headers
    else:
        return (
            "Onbekende bewerking: " + str(escape(task)),
            400,
            {"Content-Type": "text/plain; charset=utf-8"},
        )


@api.route("/data/")
def data():
    """
    Retourneert in json de data
    :return: de gevraagde data in json formaat
    """
    start = request.args.get('start', )
    end = request.args.get('end')
    aggregate = request.args.get('aggregate')
    fields = request.args.get('fields')

    if aggregate not in {"15min", "hour", "day", "week", "month"}:
        return {"error": "Ongeldig aggregate interval"}, 400

    if fields:
        fields = fields.split(",")

    timezone_raw = request.args.get('timezone', 'Europe/Amsterdam')

    try:
        timezone = ZoneInfo(timezone_raw)
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        start_dt = (
            start_dt.replace(tzinfo=timezone)
            if start_dt.tzinfo is None else start_dt.astimezone(timezone)
        )
        end_dt = (
            end_dt.replace(tzinfo=timezone)
            if end_dt.tzinfo is None else end_dt.astimezone(timezone)
        )
        if end_dt <= start_dt:
            raise ValueError("End must follow start")
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return {"error": "Ongeldige start, end of timezone"}, 400

    try:
        data_report = Report()
        data = data_report.get_data(
            start=start_dt,
            end=end_dt,
            aggregate=aggregate,
            var_codes=fields,
        )

    except Exception:
        current_app.logger.exception("Failed to retrieve API data")
        return {"error": "Gegevens konden niet worden opgehaald"}, 500

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
