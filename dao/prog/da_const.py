
tasks = {
    "calc_optimum_met_debug": {
        "name": "Optimaliseringsberekening met debug",
        "cmd": ["python3", "day_ahead.py", "debug", "calc"],
        "function": "calc_optimum_met_debug",
        "file_name": "calc_debug",
    },
    "calc_optimum": {
        "name": "Optimaliseringsberekening zonder debug",
        "cmd": ["python3", "day_ahead.py", "calc"],
        "object": "DaBase",
        "file_name": "calc",
    },
    "tibber": {
        "name": "Verbruiksgegevens bij Tibber ophalen",
        "cmd": ["python3", "day_ahead.py", "tibber"],
        "function": "get_tibber_data",
        "file_name": "tibber",
    },
    "meteo": {
        "name": "Meteoprognoses ophalen",
        "cmd": ["python3", "day_ahead.py", "meteo"],
        "function": "get_meteo_data",
        "file_name": "meteo",
    },
    "prices": {
        "name": "Day ahead prijzen ophalen",
        "cmd": ["python3", "day_ahead.py", "prices"],
        "function": "get_day_ahead_prices",
        "file_name": "prices",
    },
    "calc_baseloads": {
        "name": "Bereken de baseloads",
        "cmd": ["python3", "day_ahead.py", "calc_baseloads"],
        "function": "calc_baseloads",
        "file_name": "baseloads",
    },
    "clean": {
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
    # "consolidate": {
    #     "name": "Verbruik/productie consolideren",
    #     "cmd": ["python3", "day_ahead.py", "consolidate"],
    #     "function": "consolidate_data",
    #     "file_name": "consolidate",
    # },
    "predicted_prices": {
        "name": "Day ahead prijsvoorspelling ophalen",
        "cmd": ["python3", "../prog/day_ahead.py", "predicted_prices"],
        "function": "get_day_ahead_predicted_prices",
        "file_name": "pred_prices",
    },
}
