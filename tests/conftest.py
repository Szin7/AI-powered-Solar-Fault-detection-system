import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from solarsense.api import create_app
from solarsense.config import STATIONS, load_settings
from solarsense.data import generate_dataset, reading
from solarsense.ml import load_release, promote, shadow, train


@pytest.fixture(scope="session")
def model_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("ml")
    generate_dataset(root / "data", sessions=24, steps=72)
    version, _ = train(root / "data", root / "models", root / "reports", trees=16)
    shadow(root / "models", version, root / "data/solar.csv")
    promote(root / "models", version)
    return root


@pytest.fixture(scope="session")
def bundle(model_path):
    return load_release(model_path / "models")


@pytest.fixture
def settings(tmp_path, model_path, monkeypatch):
    monkeypatch.setenv("SOLARSENSE_HOME", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PUBLIC_READ", raising=False)
    config = load_settings()
    config["models"] = model_path / "models"
    return config


@pytest.fixture
def client(settings):
    app = create_app(settings, start_worker=False)
    with TestClient(app) as session:
        yield session


@pytest.fixture
def row():
    item, _ = reading(
        0, STATIONS[0], np.random.default_rng(42), start=datetime(2026, 6, 1, 3, 15, tzinfo=timezone.utc)
    )
    return item


def auth(settings, role="operator", station="roof-east"):
    token = settings["credentials"]["devices"][station] if role == "device" else settings["credentials"][role]
    return {"Authorization": "Bearer " + token}
