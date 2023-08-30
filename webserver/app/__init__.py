from flask import Flask
import sys
import os
import logging
from datetime import date
from logging.handlers import TimedRotatingFileHandler

app = Flask(__name__)

sys.path.append("../")

logname = "dashboard.log"
handler = TimedRotatingFileHandler("../data/log/" + logname, when = "midnight", backupCount=10)
handler.suffix = "%Y%m%d"
handler.setLevel(logging.INFO)
logging.basicConfig(level = logging.DEBUG, handlers = [handler], format = f'%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

from webserver.app import routes

#app.run(debug=True, port=5000, host='0.0.0.0')
app.run(port = 5000, host = '0.0.0.0')