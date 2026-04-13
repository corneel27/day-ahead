from flask import Flask

# sys.path.append("../")

app = Flask(__name__)
app.secret_key = 'secret_cookie_key' 

from dao.webserver.app.routes import *


#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
