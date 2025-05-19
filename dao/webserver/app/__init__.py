from flask import Flask
import sys
from dao.prog.da_config import Config

# sys.path.append("../")

app = Flask(__name__)

from dao.webserver.app.routes import *


#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
