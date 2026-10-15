from flask import redirect, url_for

from . import app


@app.route("/", methods=["GET"])
def index():
    return redirect(url_for('v2.chart'))