import os
import argparse

if not os.path.lexists("app/static/data"):
    os.symlink("../data", "app/static/data")

from app import app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Start Flask in debug mode")
    args = parser.parse_args()

    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(port=port, host="0.0.0.0", debug=args.debug, use_reloader=args.debug)
