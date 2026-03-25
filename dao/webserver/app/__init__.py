from flask import Flask

# sys.path.append("../")

app = Flask(__name__)
app.secret_key = 'secret_cookie_key' 

# Import existing routes (old API)
from dao.webserver.app.routes import *

# Register API v2 Blueprint
from dao.webserver.app.api_v2 import api_v2_bp
app.register_blueprint(api_v2_bp, url_prefix='/api/v2')


#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
