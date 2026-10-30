from conftest import auth
from solarsense.simulator import next_event_start


def test_new_demo_clock_follows_previous_session():
    start = "2026-06-01T03:15:00+00:00"
    assert next_event_start(start, None) == start
    assert next_event_start(start, "2026-05-31T04:00:00+00:00") == start
    assert next_event_start(start, "2026-06-01T04:00:00+00:00") == "2026-06-02T03:15:00+00:00"
    assert next_event_start(start, "2027-01-01T23:00:00+00:00") == "2027-01-02T03:15:00+00:00"


def test_manual_controls_require_operator_and_reach_device(client, settings):
    manual = {
        "voltage_v": 34.5,
        "current_a": 6.2,
        "ambient_temp_c": 24,
        "surface_temp_c": 41,
        "humidity_pct": 55,
        "light_adc": 3200,
        "irradiance_wm2": 800,
        "ac_power_w": 200,
    }
    path = "/api/v1/stations/roof-east/scenario"
    assert client.post(path, json={"manual": manual}, headers=auth(settings, "viewer")).status_code == 403
    response = client.post(path, json={"manual": manual}, headers=auth(settings))
    assert response.status_code == 200
    control = client.get("/api/v1/device/control", headers=auth(settings, "device")).json()
    assert control["scenario"]["manual"] == manual
    assert (
        client.post(path, json={"manual": {**manual, "light_adc": 5000}}, headers=auth(settings)).status_code
        == 422
    )
    assert (
        client.post(path, json={"manual": {**manual, "fault": "normal"}}, headers=auth(settings)).status_code
        == 422
    )
    client.post(path, json={"enabled": False}, headers=auth(settings))
    control = client.get("/api/v1/device/control", headers=auth(settings, "device")).json()
    assert not control["scenario"]["enabled"]
    assert control["scenario"]["manual"] is None
