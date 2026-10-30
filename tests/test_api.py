import json
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from conftest import auth
from solarsense import db
from solarsense.api import create_app
from solarsense.config import STATIONS
from solarsense.data import reading
from solarsense.worker import deliver_notifications, process_one


def ingest(client, settings, row):
    return client.post("/api/v1/telemetry", json={"readings": [row]}, headers=auth(settings, "device"))


def test_permissions_and_station_scope(client, settings, row):
    path = "/api/v1/stations/roof-east/scenario"
    assert client.post(path, json={}).status_code == 401
    assert client.post(path, json={}, headers=auth(settings, "viewer")).status_code == 403
    assert client.post(path, json={}, headers=auth(settings)).status_code == 200
    row["station_id"] = "roof-west"
    assert ingest(client, settings, row).status_code == 403
    assert client.get("/api/v1/stations", headers=auth(settings, "device")).status_code == 403


def test_duplicate_is_idempotent_and_collision_rejected(client, settings, row, bundle):
    assert ingest(client, settings, row).json()["accepted"] == 1
    assert ingest(client, settings, row).json()["duplicates"] == 1
    row["voltage_v"] += 1
    assert ingest(client, settings, row).status_code == 409
    assert process_one(client.app.state.engine, bundle) is not None
    assert process_one(client.app.state.engine, bundle) is None


def test_invalid_and_truth_payload_rejected(client, settings, row):
    row["fault"] = "normal"
    assert ingest(client, settings, row).status_code == 422
    del row["fault"]
    row["observed_at"] = "2026-01-01T12:00:00"
    assert ingest(client, settings, row).status_code == 422
    row["observed_at"] = "2026-01-01T12:00:00Z"
    row["current_a"] = None
    assert ingest(client, settings, row).status_code == 422
    row["missing_reason"] = "Sensor unavailable"
    assert ingest(client, settings, row).status_code == 202


def test_late_readings_do_not_replace_live_state(client, settings, row, bundle):
    newer = dict(row, sequence=2, observed_at="2026-06-01T04:00:00Z")
    assert ingest(client, settings, newer).status_code == 202
    process_one(client.app.state.engine, bundle)
    assert ingest(client, settings, row).status_code == 202
    result = process_one(client.app.state.engine, bundle)
    assert result["result"]["late"]
    data = client.get("/api/v1/stations", headers=auth(settings)).json()
    station = next(s for s in data["stations"] if s["id"] == "roof-east")
    assert station["reading"]["sequence"] == 2
    assert (
        len(client.get("/api/v1/stations/roof-east/history", headers=auth(settings)).json()["readings"]) == 2
    )


def test_outage_and_recovery_preserve_history(client, settings, row):
    ingest(client, settings, row)
    engine = client.app.state.engine
    with engine.begin() as conn:
        conn.execute(
            db.stations.update().where(db.stations.c.id == "roof-east").values(last_seen=time.time() - 11)
        )
    fleet = client.get("/api/v1/stations", headers=auth(settings)).json()["stations"]
    assert not next(s for s in fleet if s["id"] == "roof-east")["online"]
    row.update(sequence=1, observed_at="2026-06-01T04:00:00Z")
    ingest(client, settings, row)
    fleet = client.get("/api/v1/stations", headers=auth(settings)).json()["stations"]
    assert next(s for s in fleet if s["id"] == "roof-east")["online"]


def test_pending_work_survives_new_engine(client, settings, row, bundle):
    ingest(client, settings, row)
    engine = db.connect(settings["database_url"])
    assert process_one(engine, bundle) is not None
    assert process_one(engine, bundle) is None
    engine.dispose()


def test_database_failure_does_not_acknowledge(client, settings, row, monkeypatch):
    def fail():
        raise OperationalError("connection unavailable", {}, Exception())

    monkeypatch.setattr(client.app.state.engine, "begin", fail)
    response = ingest(client, settings, row)
    assert response.status_code == 503
    assert "durable" not in response.json()


def test_model_missing_reports_unready(settings):
    from fastapi.testclient import TestClient

    settings["models"] = settings["state"] / "missing-models"
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503


def test_two_viewers_do_not_generate_telemetry(client, settings, row, bundle):
    ingest(client, settings, row)
    process_one(client.app.state.engine, bundle)
    hello = {"token": settings["credentials"]["viewer"], "cursor": 0}
    headers = {"Origin": "http://127.0.0.1:8000"}
    with (
        client.websocket_connect("/ws", headers=headers) as first,
        client.websocket_connect("/ws", headers=headers) as second,
    ):
        for socket in [first, second]:
            socket.send_json(hello)
            assert socket.receive_json()["type"] == "connected"
            assert socket.receive_json()["cursor"] == 1
        with client.app.state.engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(db.telemetry)).scalar() == 1
            assert conn.execute(select(func.count()).select_from(db.results)).scalar() == 1
    assert process_one(client.app.state.engine, bundle) is None


def test_websocket_requires_origin_and_viewer(client, settings):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"Origin": "https://untrusted.invalid"}):
            pass
    with client.websocket_connect("/ws", headers={"Origin": "http://127.0.0.1:8000"}) as socket:
        socket.send_json({"token": settings["credentials"]["devices"]["roof-east"]})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_commands_scoped_idempotent_and_expiring(client, settings):
    command = client.post(
        "/api/v1/stations/roof-east/commands", json={"relay_on": False}, headers=auth(settings)
    ).json()
    path = f"/api/v1/device/commands/{command['id']}/ack"
    assert (
        client.post(path, json={"relay_on": False}, headers=auth(settings, "device", "roof-west")).status_code
        == 404
    )
    assert client.post(path, json={"relay_on": True}, headers=auth(settings, "device")).status_code == 409
    assert (
        client.post(path, json={"relay_on": False}, headers=auth(settings, "device")).json()["duplicate"]
        is False
    )
    assert (
        client.post(path, json={"relay_on": False}, headers=auth(settings, "device")).json()["duplicate"]
        is True
    )
    command = client.post(
        "/api/v1/stations/roof-east/commands", json={"relay_on": True}, headers=auth(settings)
    ).json()
    with client.app.state.engine.begin() as conn:
        conn.execute(
            db.commands.update().where(db.commands.c.id == command["id"]).values(expires_at=time.time() - 1)
        )
    assert client.get("/api/v1/device/control", headers=auth(settings, "device")).json()["commands"] == []


def test_fault_incident_recovery_outbox_and_reviews(client, settings, bundle):
    start = datetime(2026, 6, 1, 3, 15, tzinfo=timezone.utc)
    engine = client.app.state.engine
    for i in range(10):
        row, _ = reading(
            i,
            STATIONS[0],
            np.random.default_rng(i + 42),
            "open_circuit" if i < 5 else "normal",
            start=start,
            minutes=0.1,
        )
        assert ingest(client, settings, row).status_code == 202
        process_one(engine, bundle)
    with engine.connect() as conn:
        incidents = conn.execute(select(db.incidents)).all()
        assert len(incidents) == 1
        assert incidents[0]._mapping["status"] == "closed"
    attempts = []

    def flaky(job):
        attempts.append(job["id"])
        raise RuntimeError("Local sink unavailable")

    deliver_notifications(engine, sender=flaky)
    with engine.begin() as conn:
        conn.execute(db.notifications.update().values(next_attempt=0))
    deliver_notifications(engine)
    deliver_notifications(engine)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(db.inbox)).scalar() == 2
        assert all(r[0] == "delivered" for r in conn.execute(select(db.notifications.c.status)))
    for label in ["unknown", "open_circuit"]:
        assert (
            client.post(
                "/api/v1/readings/1/reviews",
                json={"label": label, "reason": "Independent fixture inspection"},
                headers=auth(settings),
            ).status_code
            == 200
        )
    assert len(client.get("/api/v1/reviews", headers=auth(settings)).json()["reviews"]) == 2


def test_stuck_sensor_creates_quality_incident(client, settings, row, bundle):
    for i in range(8):
        row.update(
            sequence=i,
            observed_at=(
                datetime(2026, 6, 1, 3, 15, tzinfo=timezone.utc) + timedelta(seconds=i * 2)
            ).isoformat(),
        )
        ingest(client, settings, row)
        result = process_one(client.app.state.engine, bundle)
    assert result["result"]["quality_state"] == "stuck"
    assert result["result"]["stabilized_class"] == "data_quality"


def test_backup_and_restore_exact_records(client, settings, row, bundle, tmp_path):
    ingest(client, settings, row)
    process_one(client.app.state.engine, bundle)
    backup = tmp_path / "snapshot"
    db.backup_snapshot(settings, backup)
    dest = tmp_path / "restored"
    db.restore_snapshot(backup, dest)
    engine = db.connect("sqlite:///" + str(dest / "var/solar.db"))
    with engine.connect() as conn:
        restored = conn.execute(select(db.telemetry.c.payload)).scalar()
        assert restored["boot_id"] == row["boot_id"]
        assert conn.execute(select(func.count()).select_from(db.results)).scalar() == 1
    assert json.loads((dest / "models/active.json").read_text()) == json.loads(
        (settings["models"] / "active.json").read_text()
    )
    engine.dispose()


def test_concurrent_duplicate_requests(client, settings, row):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: ingest(client, settings, row), range(4)))
    assert all(r.status_code == 202 for r in responses)
    assert sum(r.json()["accepted"] for r in responses) == 1
    assert sum(r.json()["duplicates"] for r in responses) == 3


def test_normal_cloud_and_low_load_do_not_open_critical_incidents(client, settings, bundle):
    engine = client.app.state.engine
    for i in range(15):
        station = dict(STATIONS[0])
        if i >= 10:
            station["load_limit_w"] = 60
        row, _ = reading(
            i,
            station,
            np.random.default_rng(42 + i),
            start=datetime(2026, 6, 1, 3, 15, tzinfo=timezone.utc),
            minutes=0.1,
            cloud=0.3 if 5 <= i < 10 else 1,
        )
        ingest(client, settings, row)
        process_one(engine, bundle)
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(db.incidents)
                .where(db.incidents.c.label.in_(["open_circuit", "short_circuit", "inverter_fault"]))
            ).scalar()
            == 0
        )


def test_drift_reports_need_comparable_regimes(client, settings, row, bundle):
    ingest(client, settings, row)
    result = client.get("/api/v1/drift", headers=auth(settings)).json()
    assert result["samples"] == 1
    assert result["regimes"]["daylight"]["state"] == "insufficient_samples"
