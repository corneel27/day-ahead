import os

if not os.path.lexists("app/static/data"):
    os.symlink("../data", "app/static/data")

from app import app

if __name__ == "__main__":
    # Enable CORS for development (Vite dev server runs on different port)
    from flask_cors import CORS
    CORS(app, resources={
        r"/api/v2/*": {
            "origins": ["http://localhost:5173", "http://127.0.0.1:5173"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "X-HA-Host", "X-HA-Port", "X-HA-Protocol", "X-HA-Token"],
        }
    })
    print("Development mode: CORS enabled for /api/v2/* endpoints")
    
    port = int(os.environ.get("FLASK_PORT", 5000))
    app.run(port=port, host="0.0.0.0")
