from flask import Flask

# sys.path.append("../")

app = Flask(__name__)
app.secret_key = "secret_cookie_key"

from . import routes
from .v2.routes import v2
from .v2.api.routes import api

app.register_blueprint(v2, name="v2", url_prefix="/v2")
app.register_blueprint(api, name="api", url_prefix="/v2/api")

#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
