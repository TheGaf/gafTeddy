import json
import os

def load_config(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    path = os.path.abspath(path)
    with open(path, "r") as f:
        cfg = json.load(f)
    cfg["_path"] = path
    return cfg

def save_config(path, config):
    with open(path, "w") as f:
        json.dump(config, f, indent=2)