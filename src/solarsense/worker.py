import json
import logging
import time

import httpx
from sqlalchemy import select

from solarsense import db
from solarsense.ml import predict
from solarsense.hardware import predict_hardware

logger = logging.getLogger("solarsense")


def process_one(engine, bundle):
    with engine.begin() as conn:
        row = conn.execute(
            select(db.telemetry)
            .where(db.telemetry.c.processed.is_(False))
            .order_by(db.telemetry.c.id)
            .limit(1)
        ).first()
        if row is None:
            return None
        item = db.row_dict(row)
        station = db.row_dict(
            conn.execute(select(db.stations).where(db.stations.c.id == item["station_id"])).first()
        )
        row_data = {
            **item["payload"],
            **{k: v for k, v in station["config"].items() if k.startswith("rated_")},
        }
        late = bool(station["latest_observed"] and item["observed_at"] <= station["latest_observed"])
        source = row_data.get("source_kind", "simulated")
        late = (
            late
            or source != station["config"].get("source_mode", "simulated")
            or item["received_at"] < station["config"].get("source_changed_at", 0)
        )
        previous = (
            conn.execute(
                select(db.results.c.result)
                .where(db.results.c.station_id == item["station_id"], db.results.c.late.is_(False))
                .order_by(db.results.c.id.desc())
                .limit(7)
            )
            .scalars()
            .all()
        )
        source = row_data.get("source_kind", "simulated")
        previous = [
            r
            for r in previous
            if r.get("source_kind", "simulated") == source
            and r.get("received_at", 0) >= station["config"].get("source_changed_at", 0)
        ]
        recent = [r["decision_state"] for r in reversed(previous[:4])]
        result = (
            predict_hardware(row_data, previous)
            if source == "hardware"
            else predict(bundle, row_data, recent, explain=not late)
        )
        result["source_kind"] = source
        if len(previous) >= 7 and (
            (row_data.get("irradiance_wm2") or 0) > 80
            or (source == "hardware" and (row_data.get("light_adc") or 0) > 20)
        ):
            sensor_pair = [row_data["voltage_v"], row_data["current_a"]]
            if all(r.get("sensor_pair") == sensor_pair for r in previous):
                result.update(
                    quality_state="stuck",
                    decision_state="data_quality",
                    stabilized_class="data_quality",
                    resolution="Inspect the repeated sensor pair; eight identical readings were received.",
                )
        deficits = [r.get("deficit_ratio") for r in previous[:2]] + [result.get("deficit_ratio")]
        result["sustained_deficit"] = bool(
            len(deficits) == 3
            and all(d is not None and d > 0.25 for d in deficits)
            and result["decision_state"] != "inactive"
        )
        result["sensor_pair"] = [row_data["voltage_v"], row_data["current_a"]]
        result["observed_at"] = item["observed_at"]
        result["received_at"] = item["received_at"]
        result["late"] = late
        event_context = {
            "source_kind": source,
            "confidence": result.get("confidence"),
            "resolution": result["resolution"],
            "observed_at": item["observed_at"],
            "model_version": result["model_version"],
        }
        if not late:
            active = conn.execute(
                select(db.incidents).where(
                    db.incidents.c.station_id == item["station_id"], db.incidents.c.status == "open"
                )
            ).first()
            active = db.row_dict(active)
            label = result["stabilized_class"]
            fault = label not in {"normal", "inactive", "warming", "uncertain", "unknown"}
            resolved = label in {"normal", "inactive"}
            # Abstention never silently closes an existing incident.
            if active and (resolved or (fault and active["label"] != label)):
                conn.execute(
                    db.incidents.update()
                    .where(db.incidents.c.id == active["id"])
                    .values(status="closed", closed_at=time.time())
                )
                db.add_event(
                    conn,
                    active["id"],
                    "recovery" if resolved else "superseded",
                    item["station_id"],
                    active["label"],
                    event_context,
                )
                active = None
            if fault and active is None:
                incident_id = conn.execute(
                    db.incidents.insert().values(
                        station_id=item["station_id"],
                        label=label,
                        opened_at=time.time(),
                        observed_at=item["observed_at"],
                        status="open",
                    )
                ).inserted_primary_key[0]
                db.add_event(conn, incident_id, "fault", item["station_id"], label, event_context)
            conn.execute(
                db.stations.update()
                .where(db.stations.c.id == item["station_id"])
                .values(latest_observed=item["observed_at"], latest_id=item["id"])
            )
        result_id = conn.execute(
            db.results.insert().values(
                telemetry_id=item["id"],
                station_id=item["station_id"],
                model_version=result["model_version"],
                processed_at=time.time(),
                late=late,
                result=result,
            )
        ).inserted_primary_key[0]
        conn.execute(db.telemetry.update().where(db.telemetry.c.id == item["id"]).values(processed=True))
    logger.info(
        json.dumps(
            {
                "event": "processed",
                "telemetry_id": item["id"],
                "station_id": item["station_id"],
                "model_version": result["model_version"],
                "late": late,
            }
        )
    )
    return {"id": result_id, "latency_seconds": time.time() - item["received_at"], "result": result}


def deliver_notifications(engine, url="", sender=None):
    with engine.connect() as conn:
        jobs = conn.execute(
            select(db.notifications)
            .where(db.notifications.c.status == "pending", db.notifications.c.next_attempt <= time.time())
            .order_by(db.notifications.c.id)
            .limit(10)
        ).all()
    for row in jobs:
        job = db.row_dict(row)
        error = None
        try:
            if sender:
                sender(job)
            elif url:
                with httpx.Client(timeout=3, trust_env=False) as client:
                    response = client.post(
                        url,
                        json={"event_id": job["event_id"], **job["payload"]},
                        headers={"Idempotency-Key": str(job["event_id"])},
                    )
                    response.raise_for_status()
            else:
                with engine.begin() as conn:
                    if (
                        conn.execute(
                            select(db.inbox.c.event_id).where(db.inbox.c.event_id == job["event_id"])
                        ).first()
                        is None
                    ):
                        conn.execute(
                            db.inbox.insert().values(
                                event_id=job["event_id"], payload=job["payload"], delivered_at=time.time()
                            )
                        )
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            error = type(exc).__name__
        attempts = job["attempts"] + 1
        history = job["history"] + [{"at": time.time(), "attempt": attempts, "error": error}]
        with engine.begin() as conn:
            conn.execute(
                db.notifications.update()
                .where(db.notifications.c.id == job["id"])
                .values(
                    attempts=attempts,
                    history=history,
                    status="delivered" if error is None else ("failed" if attempts >= 6 else "pending"),
                    next_attempt=time.time() + min(60, 2**attempts),
                )
            )
    return len(jobs)
