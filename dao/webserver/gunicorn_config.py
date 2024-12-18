import sys

sys.path.append("../../")
from dao.prog.da_config import get_config

app_datapath = "app/static/data/"
port = get_config(app_datapath + "options.json", ["dashboard", "port"], 5000)
workers = 2
bind = f"0.0.0.0:{port}"
forwarded_allow_ips = "*"
secure_scheme_headers = {"X-Forwarded-Proto": "https"}
timeout = 60
