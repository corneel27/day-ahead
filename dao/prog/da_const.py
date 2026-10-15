
tasks: dict[str, dict[str, str | list[str]]] = {
    "calc_optimum_met_debug": {
        "name": "Optimaliseringsberekening met debug",
        "cmd": ["python3", "day_ahead.py", "debug", "calc"],
        "object": "DaCalc",
        "function": "calc_optimum_met_debug",
        "file_name": "calc_debug",
    },
    "calc_optimum": {
        "name": "Optimaliseringsberekening zonder debug",
        "cmd": ["python3", "day_ahead.py", "calc"],
        "object": "DaBase",
        "function": "calc_optimum",
        "file_name": "calc",
    },
    "get_tibber_data": {
        "name": "Verbruiksgegevens bij Tibber ophalen",
        "cmd": ["python3", "day_ahead.py", "tibber"],
        "function": "get_tibber_data",
        "file_name": "tibber",
    },
    "get_meteo_data": {
        "name": "Meteoprognoses ophalen",
        "cmd": ["python3", "day_ahead.py", "meteo"],
        "function": "get_meteo_data",
        "file_name": "meteo",
    },
    "get_day_ahead_prices": {
        "name": "Day ahead prijzen ophalen",
        "cmd": ["python3", "day_ahead.py", "prices"],
        "function": "get_day_ahead_prices",
        "file_name": "prices",
    },
    "get_predicted_prices": {
        "name": "Day ahead prijsvoorspelling ophalen",
        "cmd": ["python3", "day_ahead.py", "get_predicted_prices"],
        "function": "get_predicted_prices",
        "file_name": "pred_prices",
    },
    "calc_baseloads": {
        "name": "Bereken de baseloads",
        "cmd": ["python3", "day_ahead.py", "calc_baseloads"],
        "function": "calc_baseloads",
        "file_name": "baseloads",
    },
    "clean_data": {
        "name": "Bestanden opschonen",
        "cmd": ["python3", "day_ahead.py", "clean_data"],
        "function": "clean_data",
        "file_name": "clean",
    },
    "train_ml_predictions": {
        "name": "ML modellen trainen",
        "cmd": ["python3", "day_ahead.py", "train"],
        "function": "train_ml_predictions",
        "file_name": "train",
    },
    "consolidate": {
        "name": "Verbruik/productie consolideren",
        "cmd": ["python3", "day_ahead.py", "consolidate"],
        "function": "consolidate_data",
        "file_name": "consolidate",
    },
}
