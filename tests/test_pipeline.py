import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from solarsense.config import LABELS, STATIONS
from solarsense.data import generate_dataset, reading
from solarsense.features import FEATURES, forecast_frame, features, quality
from solarsense.ml import load_release, predict, promote, shadow, stabilize
from solarsense.simulator import controls_for, load_scenario


def test_generator_reproducible_and_session_split(tmp_path):
    a, ma = generate_dataset(tmp_path / "a", 24, 60)
    b, mb = generate_dataset(tmp_path / "b", 24, 60)
    pd.testing.assert_frame_equal(a, b)
    assert ma["sha256"] == mb["sha256"]
    assert a.groupby("session").split.nunique().max() == 1
    assert set(a.fault) == set(LABELS)
    assert all(set(part.fault) == set(LABELS) for _, part in a.groupby("split"))


def test_feature_contract_excludes_truth(row):
    row.update(rated_power_w=400, rated_voltage_v=36)
    X = features(pd.DataFrame([row]))
    altered = {**row, "fault": "short_circuit", "scenario_run_id": "different", "station_id": "unseen"}
    pd.testing.assert_frame_equal(X, features(pd.DataFrame([altered])))
    assert list(X) == FEATURES


def test_prediction_label_and_explanation(bundle):
    row, _ = reading(
        4,
        STATIONS[0],
        np.random.default_rng(42),
        "open_circuit",
        start=datetime(2026, 6, 1, 3, 15, tzinfo=timezone.utc),
    )
    result = predict(bundle, {**row, **STATIONS[0]}, ["open_circuit"] * 2)
    assert result["raw_class"] == LABELS[result["raw_index"]]
    assert result["raw_class"] == max(result["probabilities"], key=result["probabilities"].get)
    assert sum(result["probabilities"].values()) == pytest.approx(1)
    assert result["explanation"]
    assert result["raw_class"] in result["explanation_target"]
    assert result == predict(bundle, {**row, **STATIONS[0]}, ["open_circuit"] * 2)


def test_missing_and_invalid_are_not_normal(bundle, row):
    row.update(STATIONS[0])
    row["current_a"] = None
    assert predict(bundle, row)["decision_state"] == "data_quality"
    row["current_a"] = 12
    row["surface_temp_c"] = 200
    assert quality(row) == "invalid"
    assert predict(bundle, row)["raw_class"] is None


def test_night_and_relay_off_suppress_fault_actions(bundle, row):
    row.update(STATIONS[0], irradiance_wm2=0, current_a=0, ac_power_w=0)
    assert predict(bundle, row)["decision_state"] == "inactive"
    row.update(irradiance_wm2=800, relay_on=False)
    result = predict(bundle, row)
    assert result["expected_power_w"] == 0
    assert result["decision_state"] == "inactive"


def test_stabilization_keeps_abstentions_visible():
    assert stabilize([], "short_circuit")[0] == "warming"
    assert stabilize(["short_circuit"] * 2, "short_circuit")[0] == "short_circuit"
    assert stabilize(["normal", "unknown", "uncertain"], "unknown")[0] == "unknown"
    assert stabilize(["normal"] * 4, "data_quality")[0] == "data_quality"


def test_forecast_features_cannot_see_future(model_path):
    df = pd.read_csv(model_path / "data/solar.csv").iloc[:72].copy()
    original = forecast_frame(df)
    changed = df.copy()
    changed.loc[40:, "ac_power_w"] = 9000
    later = forecast_frame(changed)
    from solarsense.features import FORECAST_FEATURES

    pd.testing.assert_frame_equal(original.loc[:39, FORECAST_FEATURES], later.loc[:39, FORECAST_FEATURES])
    assert original.loc[30, "target_60"] == df.loc[42, "ac_power_w"]
    assert original.iloc[-1].target_15 != original.iloc[-1].target_15


def test_integrity_check_and_rollback(model_path, tmp_path):
    import shutil

    shutil.copytree(model_path / "models", tmp_path / "models")
    models = tmp_path / "models"
    pointer = json.loads((models / "active.json").read_text())
    version = pointer["active"]
    (models / "active.json").write_text(json.dumps({"active": version, "previous": version}))
    assert promote(models, None, rollback=True) == version
    assert shadow(models, version, model_path / "data/solar.csv")["passed"]
    artifact = models / version / "model.joblib"
    artifact.write_bytes(artifact.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="integrity"):
        load_release(models)


def test_scenario_file_and_known_event():
    scenario = load_scenario("scenarios/interview.yaml")
    assert controls_for(scenario, "roof-east", 20)["fault"] == "partial_shading"
    assert controls_for(scenario, "roof-east", 80)["fault"] == "normal"


def test_available_and_delivered_power_are_different():
    station = {**STATIONS[0], "load_limit_w": 50}
    row, _ = reading(
        0, station, np.random.default_rng(42), start=datetime(2026, 6, 1, 6, tzinfo=timezone.utc)
    )
    assert row["ac_power_w"] < 55
    assert row["voltage_v"] * row["current_a"] == pytest.approx(50, rel=0.05)


def test_simulator_buffers_disconnects_and_reports_drops(tmp_path, monkeypatch):
    import asyncio
    import httpx
    import yaml
    from solarsense.simulator import simulate

    monkeypatch.setenv("SOLARSENSE_HOME", str(tmp_path))
    scenario = load_scenario("scenarios/interview.yaml")
    scenario.update(
        steps=4,
        cadence_seconds=0.05,
        buffer_limit=2,
        stations=["roof-east"],
        events=[{"station": "roof-east", "start": 0, "end": 4, "network": "disconnect"}],
    )
    path = tmp_path / "offline.yaml"
    path.write_text(yaml.safe_dump(scenario))
    original = httpx.AsyncClient

    def client(*args, **kwargs):
        return original(*args, **kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(503)))

    monkeypatch.setattr(httpx, "AsyncClient", client)
    asyncio.run(simulate(scenario_path=path, run_dir=tmp_path / "run"))
    state = json.loads((tmp_path / "run/spool.json").read_text())
    assert state["dropped"] == 2
    assert len(state["devices"]["roof-east"]["pending"]) == 2
    assert state["step"] == 4
    records = (tmp_path / "run/readings.jsonl").read_text().splitlines()
    assert len(records) == 4
    assert all("fault" not in json.loads(line) for line in records)
    assert len((tmp_path / "run/truth.jsonl").read_text().splitlines()) == 4
