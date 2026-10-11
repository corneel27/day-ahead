from flask import Flask


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

from . import routes
from .v1.routes import app as v1
from .v2.routes import v2
from .api.routes import api

app.register_blueprint(v1, name="v1", url_prefix="/v1")
app.register_blueprint(v2, name="v2", url_prefix="/v2")
app.register_blueprint(api, name="api", url_prefix="/api")

#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
