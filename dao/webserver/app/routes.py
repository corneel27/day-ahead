from . import app
from flask import redirect, url_for

@app.route("/", methods=["GET"])
def index():
    return redirect(url_for('v2.home'))