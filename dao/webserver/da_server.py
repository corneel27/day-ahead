import os

if not os.path.lexists("app/static/data"):
    os.symlink("../data", "app/static/data")

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(port=port, host="0.0.0.0")
