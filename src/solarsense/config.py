import hashlib
import json
import os
import secrets
from pathlib import Path

SEED = 42
LABELS = ["normal", "open_circuit", "short_circuit", "partial_shading", "soiling", "inverter_fault"]
SCHEMA_VERSION = 1
FEATURE_VERSION = "electrical-v1"
STATIONS = [
    {"id": "roof-east", "name": "East roof", "rated_power_w": 400.0, "rated_voltage_v": 36.0},
    {"id": "roof-west", "name": "West roof", "rated_power_w": 550.0, "rated_voltage_v": 37.5},
    {"id": "lab-panel", "name": "Lab panel", "rated_power_w": 300.0, "rated_voltage_v": 35.0},
]


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def paths():
    root = Path(os.getenv("SOLARSENSE_HOME", ".")).resolve()
    return root, root / "var", root / "models"


def load_settings():
    root, state, models = paths()
    state.mkdir(parents=True, exist_ok=True)
    path = state / "credentials.json"
    if not path.exists():
        config = {
            "operator": secrets.token_urlsafe(32),
            "viewer": secrets.token_urlsafe(32),
            "devices": {s["id"]: secrets.token_urlsafe(32) for s in STATIONS},
        }
        # Exclusive creation also protects the first simultaneous startup.
        try:
            with path.open("x") as f:
                json.dump(config, f, indent=2)
            path.chmod(0o600)
        except FileExistsError:
            pass
    credentials = json.loads(path.read_text())
    return {
        "root": root,
        "state": state,
        "models": models,
        "credentials": credentials,
        "database_url": os.getenv("DATABASE_URL", "sqlite:///" + str(state / "solar.db")),
        "public_read": os.getenv("PUBLIC_READ", "0") == "1",
        "origins": os.getenv(
            "ALLOWED_ORIGINS",
            "http://127.0.0.1:8000,http://localhost:8000,http://localhost:8080,http://127.0.0.1:8080",
        ).split(","),
        "notification_url": os.getenv("NOTIFICATION_URL", ""),
        "heartbeat_seconds": float(os.getenv("HEARTBEAT_SECONDS", "10")),
    }
