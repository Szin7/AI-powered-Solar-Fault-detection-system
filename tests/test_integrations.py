import json
from pathlib import Path

import httpx
import numpy as np
import pytest
from sqlalchemy import select

from conftest import auth
from solarsense import db
from solarsense.hardware import hardware_probabilities, load_hardware_model, parse_serial
from solarsense.technicians import deliver_technician_alerts, enqueue_alert
from solarsense.weather import _cache, weather_snapshot
from solarsense.worker import process_one


def record(sequence=1, voltage=19.2, current=0.2):
    return {
        "senderId": 1,
        "ldrValue": 3500,
        "dhtTemp": 30,
        "humidity": 50,
        "thermistorTemp": 40,
        "voltage": voltage,
        "current": current,
        "relayStatus": False,
        "valid": True,
        "gateway_timestamp_ms": sequence,
    }


def enable_hardware(client, settings, monkeypatch):
    monkeypatch.setenv("SOLARSENSE_GATEWAY_KEY", "integration-test-only")
    response = client.post(
        "/api/v1/stations/roof-east/source", json={"mode": "hardware"}, headers=auth(settings)
    )
    assert response.status_code == 200
    return {"X-Gateway-Key": "integration-test-only"}


def test_original_forest_matches_exported_reference():
    fixtures = json.loads((Path(__file__).parent / "fixtures/hardware_predictions.json").read_text())
    assert len(load_hardware_model()["trees"]) == 100
    for row in fixtures:
        np.testing.assert_allclose(hardware_probabilities(row["values"]), row["probabilities"], atol=1e-12)


def test_gateway_contract_auth_source_dedup_and_inference(client, settings, bundle, monkeypatch):
    headers = enable_hardware(client, settings, monkeypatch)
    assert client.post("/api/gateway-data", json=[record()]).status_code == 401
    assert (
        client.post(
            "/api/v1/stations/roof-east/source", json={"mode": "simulated"}, headers=auth(settings, "viewer")
        ).status_code
        == 403
    )
    for i in range(4):
        payload = record(i, voltage=20 + i * 0.01, current=0.001)
        response = client.post("/api/gateway-data", json=[payload], headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["processed"] == 1
        repeated = client.post("/api/gateway-data", json=[payload], headers=headers)
        assert repeated.json()["duplicates"] == 1
        result = process_one(client.app.state.engine, bundle)["result"]
    assert result["model_version"].startswith("hw-")
    assert result["stabilized_class"] == "open_circuit"
    assert "virtual" not in result["resolution"]
    fleet = client.get("/api/v1/stations", headers=auth(settings)).json()
    station = next(s for s in fleet["stations"] if s["id"] == "roof-east")
    assert station["reading"]["source_kind"] == "hardware"
    assert station["reading"]["ac_power_w"] is None
    assert station["reading"]["irradiance_wm2"] is None
    assert station["reading"]["dc_power_w"] > 0
    assert (
        client.get("/api/v1/stations/roof-east/forecast", headers=auth(settings)).json()["state"]
        == "unsupported"
    )
    assert (
        client.get("/api/v1/device/control", headers=auth(settings, "device")).json()["source_mode"]
        == "hardware"
    )


def test_hardware_relay_requires_enable_and_real_feedback(client, settings, bundle, monkeypatch):
    headers = enable_hardware(client, settings, monkeypatch)
    client.post("/api/gateway-data", json=[record()], headers=headers)
    process_one(client.app.state.engine, bundle)
    path = "/api/v1/stations/roof-east/commands"
    assert client.post(path, json={"relay_on": True}, headers=auth(settings)).status_code == 403
    monkeypatch.setenv("ENABLE_PHYSICAL_RELAY", "1")
    queued = client.post(path, json={"relay_on": True}, headers=auth(settings)).json()
    polled = client.get("/api/get-command/1", headers=headers)
    assert polled.json()["command"] == "ACTIVATE_RELAY"
    assert client.get("/api/get-command/1", headers=headers).json()["command"] == "ACTIVATE_RELAY"
    confirmed = {**record(2), "relayStatus": True}
    client.post("/api/gateway-data", json=[confirmed], headers=headers)
    jobs = client.get("/api/v1/commands", headers=auth(settings)).json()
    assert next(c for c in jobs if c["id"] == queued["id"])["status"] == "acknowledged"
    assert client.get("/api/get-command/1", headers=headers).status_code == 204


def test_invalid_gateway_reading_and_serial_protocols(client, settings, bundle, monkeypatch):
    headers = enable_hardware(client, settings, monkeypatch)
    client.post("/api/gateway-data", json=[{**record(), "valid": False}], headers=headers)
    result = process_one(client.app.state.engine, bundle)["result"]
    assert result["decision_state"] == "data_quality"
    nano = parse_serial('{"v":18,"i":0.2,"t":30,"l":600,"p":3.6,"ts":500}', "nano")
    assert nano["light_adc"] is None and nano["light_lux"] == 600
    assert nano["humidity_pct"] is None
    full = parse_serial("DATA:18,0.2,30,3500,50,40", "data")
    assert full["humidity_pct"] == 50
    assert parse_serial('{"pong":true}', "nano") is None
    with pytest.raises(ValueError):
        parse_serial("DATA:18,no-number,30,3500", "data")


def contact(channel="whatsapp"):
    return {
        "name": "Test technician",
        "phone": "+12025550123",
        "channel": channel,
        "enabled": True,
        "allow_simulated": True,
    }


def event(conn, source="simulated"):
    enqueue_alert(
        conn,
        500,
        {
            "station_id": "roof-east",
            "label": "open_circuit",
            "kind": "fault",
            "source_kind": source,
            "confidence": 0.91,
            "resolution": "Inspect connector with power isolated.",
        },
    )


def test_technician_preview_and_phone_privacy(client, settings, monkeypatch):
    monkeypatch.setenv("TECHNICIAN_DELIVERY", "preview")
    path = "/api/v1/stations/roof-east/technician"
    assert client.post(path, json=contact(), headers=auth(settings, "viewer")).status_code == 403
    assert client.post(path, json={**contact(), "phone": "123"}, headers=auth(settings)).status_code == 422
    assert client.post(path, json=contact(), headers=auth(settings)).status_code == 200
    with client.app.state.engine.begin() as conn:
        event(conn)
    operator_jobs = client.get("/api/v1/technician-alerts", headers=auth(settings)).json()["alerts"]
    viewer_jobs = client.get("/api/v1/technician-alerts", headers=auth(settings, "viewer")).json()["alerts"]
    assert operator_jobs[0]["status"] == "preview"
    assert "SIMULATED DEMO" in operator_jobs[0]["payload"]["message"]
    assert viewer_jobs[0]["payload"]["contact"]["phone"] == "***0123"


def config():
    return {
        "mode": "live",
        "sid": "AC" + "0" * 32,
        "token": "test-only",
        "sms_from": "+12025550124",
        "whatsapp_from": "+12025550124",
        "template": "HX" + "0" * 32,
    }


def prepare_live_job(client, settings, monkeypatch):
    monkeypatch.setenv("TECHNICIAN_DELIVERY", "preview")
    client.post("/api/v1/stations/roof-east/technician", json=contact(), headers=auth(settings))
    monkeypatch.setenv("TECHNICIAN_DELIVERY", "live")
    with client.app.state.engine.begin() as conn:
        event(conn, "hardware")


def test_message_submission_is_not_delivery_and_is_not_repeated(client, settings, monkeypatch):
    prepare_live_job(client, settings, monkeypatch)
    requests = []

    def provider(request):
        requests.append(request.method)
        if request.method == "POST":
            assert b"ContentSid=" in request.content and b"ContentVariables=" in request.content
            return httpx.Response(201, json={"sid": "SM" + "1" * 32, "status": "queued"})
        return httpx.Response(200, json={"status": "delivered"})

    with httpx.Client(transport=httpx.MockTransport(provider)) as session:
        engine = client.app.state.engine
        deliver_technician_alerts(engine, config(), session)
        with engine.begin() as conn:
            job = conn.execute(select(db.technician_deliveries)).first()
            assert job.status == "submitted"
            conn.execute(db.technician_deliveries.update().values(next_attempt=0))
        deliver_technician_alerts(engine, config(), session)
        deliver_technician_alerts(engine, config(), session)
        with engine.connect() as conn:
            assert conn.execute(select(db.technician_deliveries.c.status)).scalar() == "delivered"
    assert requests == ["POST", "GET"]


def test_ambiguous_message_timeout_is_not_automatically_resent(client, settings, monkeypatch):
    prepare_live_job(client, settings, monkeypatch)
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("Provider may have accepted message", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as session:
        deliver_technician_alerts(client.app.state.engine, config(), session)
        deliver_technician_alerts(client.app.state.engine, config(), session)
    with client.app.state.engine.connect() as conn:
        assert conn.execute(select(db.technician_deliveries.c.status)).scalar() == "uncertain"
    assert len(calls) == 1


def test_weather_cache_and_failure_do_not_fabricate_weather():
    _cache.clear()
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"current": {"temperature_2m": 23, "cloud_cover": 70}, "daily": {}})

    with httpx.Client(transport=httpx.MockTransport(provider)) as session:
        assert weather_snapshot(session)["current"]["temperature_2m"] == 23
        assert weather_snapshot(session)["available"]
    assert len(calls) == 1
    for item in _cache.values():
        item["retry_at"] = 0
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as session:
        value = weather_snapshot(session)
        assert value["stale"] and value["current"]["temperature_2m"] == 23
    _cache.clear()


def test_failed_status_poll_does_not_resubmit_message(client, settings, monkeypatch):
    prepare_live_job(client, settings, monkeypatch)
    methods = []

    def provider(request):
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(201, json={"sid": "SM" + "1" * 32})
        raise httpx.ConnectError("Offline during delivery check", request=request)

    engine = client.app.state.engine
    with httpx.Client(transport=httpx.MockTransport(provider)) as session:
        for _ in range(3):
            deliver_technician_alerts(engine, config(), session)
            with engine.begin() as conn:
                conn.execute(db.technician_deliveries.update().values(next_attempt=0))
        with engine.connect() as conn:
            assert conn.execute(select(db.technician_deliveries.c.status)).scalar() == "submitted"
    assert methods == ["POST", "GET", "GET"]


def test_source_switch_keeps_old_pending_readings_out_of_live_view(
    client, settings, row, bundle, monkeypatch
):
    assert (
        client.post(
            "/api/v1/telemetry", json={"readings": [row]}, headers=auth(settings, "device")
        ).status_code
        == 202
    )
    enable_hardware(client, settings, monkeypatch)
    assert process_one(client.app.state.engine, bundle)["result"]["late"]
    fleet = client.get("/api/v1/stations", headers=auth(settings)).json()
    station = next(s for s in fleet["stations"] if s["id"] == "roof-east")
    assert station["reading"] is None


def test_hardware_fault_creates_one_automatic_technician_preview(client, settings, bundle, monkeypatch):
    monkeypatch.setenv("TECHNICIAN_DELIVERY", "preview")
    headers = enable_hardware(client, settings, monkeypatch)
    client.post(
        "/api/v1/stations/roof-east/technician",
        json={**contact(), "allow_simulated": False},
        headers=auth(settings),
    )
    for i in range(6):
        response = client.post(
            "/api/gateway-data", json=[record(i, voltage=20 + i * 0.01, current=0.001)], headers=headers
        )
        assert response.status_code == 200
        process_one(client.app.state.engine, bundle)
    jobs = client.get("/api/v1/technician-alerts", headers=auth(settings)).json()["alerts"]
    assert len(jobs) == 1
    assert jobs[0]["status"] == "preview"
    assert "HARDWARE" in jobs[0]["payload"]["message"]
    assert "open circuit" in jobs[0]["payload"]["message"]


def test_sms_body_and_nonfinite_serial_values():
    from solarsense.technicians import twilio_payload

    payload = twilio_payload({"payload": {"contact": contact("sms"), "message": "Test message"}}, config())
    assert payload == {"To": "+12025550123", "From": "+12025550124", "Body": "Test message"}
    for line, protocol in [
        ("DATA:NaN,0.2,30,3500", "data"),
        ('{"v":18,"i":Infinity,"t":30,"l":400}', "nano"),
    ]:
        with pytest.raises(ValueError):
            parse_serial(line, protocol)
