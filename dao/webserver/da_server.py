import os
if not os.path.lexists("app/static/data"):
    os.symlink("../data", "app/static/data")

from app import app

if __name__ == '__main__':
    app.run(port=5000, host='0.0.0.0')
