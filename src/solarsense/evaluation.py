import json
import platform
import time
import uuid
from datetime import datetime, timezone

import httpx
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from solarsense.config import LABELS, STATIONS
from solarsense.data import reading
from solarsense.features import features
from solarsense.ml import decision_labels, load_release, predict, stabilize


def evaluate(settings):
    bundle = load_release(settings["models"])
    df = pd.read_csv(settings["root"] / "data/generated/solar.csv")
    test = df[df.split == "test"].copy()
    X = features(test)
    probs = bundle["probability_model"].predict_proba(X)
    pred = bundle["probability_model"].classes_[probs.argmax(axis=1)]
    decisions, _ = decision_labels(bundle, X, probs)
    test["decision"] = [
        "inactive" if irr < 80 else decision for irr, decision in zip(test.irradiance_wm2, decisions)
    ]
    delays, recoveries, missed, false_alerts, total_events = [], [], 0, 0, 0
    per_session = []
    for session, group in test.groupby("session"):
        recent, stable, active = [], [], "normal"
        false = 0
        for row in group.itertuples():
            current, votes = stabilize(recent, row.decision)
            recent = votes
            stable.append(current)
            if current not in {"normal", "inactive", "uncertain", "unknown", "warming"} and current != active:
                if current != row.fault:
                    false += 1
                active = current
            elif current in {"normal", "inactive"}:
                active = "normal"
        truth = group.fault.to_numpy()
        for start in range(len(group)):
            if truth[start] == "normal" or (start > 0 and truth[start] == truth[start - 1]):
                continue
            total_events += 1
            end = start + 1
            while end < len(group) and truth[end] == truth[start]:
                end += 1
            hits = [i for i in range(start, end) if stable[i] == truth[start]]
            if hits:
                delays.append((hits[0] - start) * 5 * 60)
                recovered = [i for i in range(end, len(group)) if stable[i] in {"normal", "inactive"}]
                if recovered:
                    recoveries.append((recovered[0] - end) * 5 * 60)
            else:
                missed += 1
        false_alerts += false
        per_session.append({"session": session, "false_alerts": false, "rows": len(group)})
    station_days = len(test) * 5 / (24 * 60)
    stress = {}
    for condition in [
        "normal",
        "partial_shading",
        "soiling",
        "inverter_fault",
        "unknown",
        "sensor_offset",
        "missing",
        "invalid",
        "night",
        "cloud",
        "low_load",
    ]:
        counts = {}
        for i in range(20):
            station = dict(STATIONS[0])
            if condition == "low_load":
                station["load_limit_w"] = 60
            row, _ = reading(
                i,
                station,
                np.random.default_rng(9000 + i),
                condition,
                severity=0.2,
                start=datetime(2026, 6, 1, 3, 15, tzinfo=timezone.utc),
                minutes=0.1,
                cloud=0.2 if condition == "cloud" else 1,
            )
            if condition == "night":
                row.update(irradiance_wm2=0, voltage_v=0, current_a=0, ac_power_w=0)
            if condition == "missing":
                row.update(current_a=None, missing_reason="stress fixture")
            if condition == "invalid":
                row["surface_temp_c"] = 160
            result = predict(
                bundle, {**row, **{k: v for k, v in station.items() if k.startswith("rated_")}}, explain=False
            )
            key = result["decision_state"]
            counts[key] = counts.get(key, 0) + 1
        stress[condition] = counts
    report = {
        "model_version": bundle["version"],
        "synthetic": True,
        "test_macro_f1": float(f1_score(test.fault, pred, labels=LABELS, average="macro", zero_division=0)),
        "incidents": {
            "fault_events": total_events,
            "missed_events": missed,
            "false_alerts": false_alerts,
            "observed_station_days": station_days,
            "false_alerts_per_station_day": false_alerts / station_days,
            "median_detection_delay_event_seconds": float(np.median(delays)) if delays else None,
            "median_recovery_delay_event_seconds": float(np.median(recoveries)) if recoveries else None,
            "sampling_seconds": 300,
            "per_session": per_session,
        },
        "stress_decisions": stress,
        "warning": "Stress outcomes are counts, not a claim of unknown-fault accuracy. Event-clock delays differ from live wall-clock latency.",
    }
    (settings["root"] / "reports/scenarios.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def benchmark(settings, url, steps=20):
    if not 3 <= steps <= 200:
        raise ValueError("Use 3 to 200 steps")
    headers = {"Authorization": "Bearer " + settings["credentials"]["operator"]}
    boot = "benchmark-" + uuid.uuid4().hex[:12]
    timings, accepted = [], 0
    start = time.monotonic()
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
        for step in range(steps):
            for station in STATIONS:
                row, _ = reading(
                    step,
                    station,
                    np.random.default_rng(step + 42),
                    start=datetime(2027, 1, 1, 3, 15, tzinfo=timezone.utc),
                    minutes=0.1,
                )
                row.update(boot_id=boot, scenario_run_id=boot)
                t = time.monotonic()
                response = client.post(
                    "/api/v1/telemetry",
                    json={"readings": [row]},
                    headers={"Authorization": "Bearer " + settings["credentials"]["devices"][station["id"]]},
                )
                response.raise_for_status()
                accepted += response.json()["accepted"]
                timings.append(time.monotonic() - t)
        deadline = time.monotonic() + 60
        processed, latencies = 0, []
        while time.monotonic() < deadline:
            rows = []
            for station in STATIONS:
                response = client.get(f"/api/v1/stations/{station['id']}/history?limit=500", headers=headers)
                response.raise_for_status()
                rows.extend(r for r in response.json()["readings"] if r["boot_id"] == boot)
            processed = sum(r["processed"] for r in rows)
            if processed == accepted:
                break
            time.sleep(0.25)
    elapsed = time.monotonic() - start
    # Persisted timestamps provide latency separately from HTTP acknowledgement time.
    from solarsense import db
    from sqlalchemy import select

    engine = db.connect(settings["database_url"])
    with engine.connect() as conn:
        pairs = conn.execute(
            select(db.results.c.processed_at, db.telemetry.c.received_at)
            .join(db.telemetry, db.results.c.telemetry_id == db.telemetry.c.id)
            .where(db.telemetry.c.boot_id == boot)
        ).all()
        latencies = [a - b for a, b in pairs]
    engine.dispose()
    report = {
        "workload": "three stations, burst ingestion, no browser viewers",
        "steps_per_station": steps,
        "accepted": accepted,
        "processed": processed,
        "elapsed_wall_seconds": elapsed,
        "completed_readings_per_second": processed / elapsed,
        "http_ack_p95_seconds": float(np.quantile(timings, 0.95)),
        "accept_to_result_p95_seconds": float(np.quantile(latencies, 0.95)) if latencies else None,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "passed": processed == accepted,
        "note": "This is a small burst benchmark, not the proposed 50-device capacity claim.",
    }
    (settings["root"] / "reports/system.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
