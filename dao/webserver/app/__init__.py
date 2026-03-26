from flask import Flask, send_from_directory
import os

# sys.path.append("../")

app = Flask(__name__)
app.secret_key = 'secret_cookie_key' 

# Import existing routes (old API)
from dao.webserver.app.routes import *

# Register API v2 Blueprint (only if not already registered)
from dao.webserver.app.api_v2 import api_v2_bp
if 'api_v2' not in app.blueprints:
    app.register_blueprint(api_v2_bp, url_prefix='/api/v2')

# Serve the new Config UI (React frontend) - only register once
if '/config' not in [rule.rule for rule in app.url_map.iter_rules()]:
    @app.route('/config')
    @app.route('/config/')
    def config_ui():
        """Serve the React config UI index.html"""
        static_folder = os.path.join(app.root_path, 'static', 'config-ui')
        return send_from_directory(static_folder, 'index.html')

    @app.route('/config/<path:path>')
    def config_ui_assets(path):
        """Serve static assets for the config UI (JS, CSS, etc.)"""
        static_folder = os.path.join(app.root_path, 'static', 'config-ui')
        return send_from_directory(static_folder, path)


#  if __name__ == '__main__':
#      app.run()
#  app.run(port=5000, host='0.0.0.0')
#  if __name__ == '__main__':
#      app.run(port=5000, host='0.0.0.0')
