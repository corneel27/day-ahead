import os

from flask import Flask, abort, request, send_from_directory


class IngressMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        ingress_path = environ.get("HTTP_X_INGRESS_PATH", "").rstrip("/")

        if ingress_path:
            environ["SCRIPT_NAME"] = ingress_path

        return self.app(environ, start_response)


# sys.path.append("../")

app = Flask(__name__)
app.secret_key = "secret_cookie_key"
app.wsgi_app = IngressMiddleware(app.wsgi_app)
app.config["DAO_WEB_PREVIEW"] = bool(os.environ.get("DAO_WEB_DATA_DIR"))


@app.before_request
def isolate_preview_tasks():
    """Keep live task processes and shared task state outside the preview."""
    if not app.config["DAO_WEB_PREVIEW"]:
        return None
    task_endpoints = {
        "v1.run_process", "v1.status", "v1.show_log",
        "v2.tasks", "v2.task_exec", "v2.task_cancel", "v2.task_state",
        "api.run_api",
    }
    if (
        request.endpoint in task_endpoints
        or "current_bewerking" in request.form
        or "menu_run" in request.form
        or request.form.get("current_menu") == "run"
    ):
        return (
            ("Live tasks are unavailable in the isolated web preview. "
            "Use the synthetic scenario debugger to develop the calculation core."),
            403,
            {"Content-Type": "text/plain; charset=utf-8"},
        )
    return None


# The development preview keeps its configuration and output outside dao/data.
if os.environ.get("DAO_WEB_DATA_DIR"):
    @app.route("/static/data/<path:filename>")
    def development_data(filename):
        if filename.split("/", 1)[0] not in ("images", "log"):
            abort(404)
        return send_from_directory(os.environ["DAO_WEB_DATA_DIR"], filename)

# Initialize the app before importing modules that register routes.
# isort: off
from . import routes as routes  # noqa: E402
from .v1.routes import app as v1  # noqa: E402
from .v2.routes import v2  # noqa: E402
from .api.routes import api  # noqa: E402
# isort: on

app.register_blueprint(v1, name="v1", url_prefix="/v1")
app.register_blueprint(v2, name="v2", url_prefix="/v2")
app.register_blueprint(api, name="api", url_prefix="/api")

#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
