from flask import Flask
import sys
app = Flask(__name__)

sys.path.append("../")
from webserver.app import routes

#app.run(debug=True, port=5000, host='0.0.0.0')
app.run(port=5000, host='0.0.0.0')