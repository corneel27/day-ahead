from flask import Blueprint, render_template, request, redirect, url_for
from markupsafe import escape
from dao.prog.da_report import Report
from subprocess import run as subprocess_run
from dao.prog.da_base import DaBase
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

api = Blueprint("api", __name__)

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


@api.route("/data-sql-ha/")
def data_sql_ha():
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

    query = data_report.get_ha_data_query(
            start=datetime.fromisoformat(start).replace(tzinfo=ZoneInfo(timezone_raw)),
            end=datetime.fromisoformat(end).replace(tzinfo=ZoneInfo(timezone_raw)),
            var_codes=fields,
            step=timedelta(days=1)
        )

    return str(query)