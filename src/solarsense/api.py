import asyncio
import contextlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from solarsense import db
from solarsense.config import digest, load_settings
from solarsense.ml import live_forecast, load_release
from solarsense.schemas import Acknowledgement, Batch, Command, Review, Scenario
from solarsense.worker import deliver_notifications, process_one
from solarsense.technicians import deliver_technician_alerts


def create_app(settings=None, start_worker=True):
    settings = settings or load_settings()
    engine = db.connect(settings["database_url"])
    registry = CollectorRegistry()
    accepted = Counter("solar_accepted_total", "Persisted new readings", registry=registry)
    duplicates = Counter("solar_duplicate_total", "Deduplicated readings", registry=registry)
    rejected = Counter("solar_rejected_total", "Rejected HTTP requests", registry=registry)
    processing = Histogram(
        "solar_processing_seconds",
        "Acceptance to committed result",
        registry=registry,
        buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 60),
    )
    viewers = Gauge("solar_viewers", "Active authorized sockets", registry=registry)
    queue = Gauge("solar_pending", "Unprocessed persisted readings", registry=registry)
    notifications_failed = Gauge(
        "solar_notification_failures", "Exhausted notification jobs", registry=registry
    )
    rate = defaultdict(deque)
    state = {
        "bundle": None,
        "model_error": "Model not loaded",
        "last_reload": 0,
        "active_pointer": None,
        "viewers": 0,
    }

    def reload_model():
        pointer = Path(settings["models"]) / "active.json"
        try:
            text = pointer.read_text()
            if state["bundle"] is None or text != state["active_pointer"]:
                bundle = load_release(settings["models"])
                with engine.begin() as conn:
                    if (
                        conn.execute(
                            select(db.releases.c.version).where(db.releases.c.version == bundle["version"])
                        ).first()
                        is None
                    ):
                        manifest = json.loads(
                            (Path(settings["models"]) / bundle["version"] / "manifest.json").read_text()
                        )
                        conn.execute(
                            db.releases.insert().values(
                                version=bundle["version"], manifest=manifest, loaded_at=time.time()
                            )
                        )
                state.update(bundle=bundle, model_error=None, active_pointer=text)
        except (OSError, ValueError, KeyError, SQLAlchemyError) as exc:
            state.update(bundle=None, model_error=type(exc).__name__)
        state["last_reload"] = time.time()

    async def worker_loop():
        while True:
            try:
                if time.time() - state["last_reload"] > 2:
                    await asyncio.to_thread(reload_model)
                if state["bundle"]:
                    for _ in range(20):
                        result = await asyncio.to_thread(process_one, engine, state["bundle"])
                        if result is None:
                            break
                        processing.observe(result["latency_seconds"])
                await asyncio.to_thread(deliver_notifications, engine, settings["notification_url"])
            except SQLAlchemyError:
                logging.getLogger("solarsense").error('{"event":"database_unavailable"}')
            except Exception:
                logging.getLogger("solarsense").exception("Inference worker failed; pending work retained")
                state["model_error"] = "Processing failure; inspect server logs"
            await asyncio.sleep(0.1)

    async def technician_loop():
        while True:
            try:
                await asyncio.to_thread(deliver_technician_alerts, engine)
            except Exception:
                logging.getLogger("solarsense").exception("Technician delivery failed; outbox retained")
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app):
        db.migrate(engine, settings)
        reload_model()
        tasks = (
            [asyncio.create_task(worker_loop()), asyncio.create_task(technician_loop())]
            if start_worker
            else []
        )
        yield
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        engine.dispose()

    app = FastAPI(title="SolarSense", version="1.0.0", lifespan=lifespan)
    app.state.engine, app.state.runtime, app.state.settings = engine, state, settings
    app.state.reload_model = reload_model

    @app.middleware("http")
    async def request_limits(request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > 128_000:
                rejected.inc()
                return JSONResponse({"detail": "Body exceeds 128 KB"}, status_code=413)
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        if len(rate) > 2000:
            for old in list(rate):
                if not rate[old] or rate[old][-1] < now - 60:
                    del rate[old]
        recent = rate[key]
        while recent and recent[0] < now - 60:
            recent.popleft()
        if len(recent) >= 3000:
            rejected.inc()
            return JSONResponse(
                {"detail": "Request rate exceeded"}, status_code=429, headers={"Retry-After": "60"}
            )
        recent.append(now)
        try:
            response = await call_next(request)
        except SQLAlchemyError:
            return JSONResponse(
                {"detail": "Database unavailable; retry with the same reading identities"}, status_code=503
            )
        if response.status_code >= 400:
            rejected.inc()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response

    def identity(token):
        config = settings["credentials"]
        if token and hmac.compare_digest(digest(token), digest(config["operator"])):
            return {"role": "operator", "station_id": None}
        if token and hmac.compare_digest(digest(token), digest(config["viewer"])):
            return {"role": "viewer", "station_id": None}
        if token:
            with engine.connect() as conn:
                station = conn.execute(
                    select(db.credentials.c.station_id).where(db.credentials.c.token_hash == digest(token))
                ).scalar()
            if station:
                return {"role": "device", "station_id": station}
        if not token and settings["public_read"]:
            return {"role": "viewer", "station_id": None}
        raise HTTPException(401, "A valid bearer token is required")

    def auth(authorization: str = Header(default="")):
        if authorization and not authorization.startswith("Bearer "):
            raise HTTPException(401, "Use bearer authentication")
        return identity(authorization.removeprefix("Bearer "))

    def operator(user=Depends(auth)):
        if user["role"] != "operator":
            with engine.begin() as conn:
                conn.execute(
                    db.audit.insert().values(
                        action="operator access", actor=user["role"], allowed=False, at=time.time()
                    )
                )
            raise HTTPException(403, "Operator permission required")
        return user

    def viewer(user=Depends(auth)):
        if user["role"] == "device":
            raise HTTPException(403, "Viewer permission required")
        return user

    def device(user=Depends(auth)):
        if user["role"] != "device":
            raise HTTPException(403, "Scoped device credential required")
        return user

    def station_exists(conn, station_id):
        row = conn.execute(select(db.stations).where(db.stations.c.id == station_id)).first()
        if row is None:
            raise HTTPException(404, "Unknown station")
        return db.row_dict(row)

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.get("/health/ready")
    def ready():
        try:
            with engine.connect() as conn:
                conn.execute(select(db.schema.c.version)).first()
        except SQLAlchemyError:
            return JSONResponse({"status": "unavailable", "reason": "database"}, status_code=503)
        if state["bundle"] is None or state["model_error"]:
            return JSONResponse(
                {"status": "unavailable", "reason": "model", "detail": state["model_error"]}, status_code=503
            )
        return {"status": "ready", "model_version": state["bundle"]["version"]}

    @app.get("/api/v1/me")
    def me(user=Depends(auth)):
        return user

    @app.post("/api/v1/telemetry", status_code=202)
    def ingest(batch: Batch, user=Depends(device)):
        if any(
            r.station_id != user["station_id"] or r.device_id != user["station_id"] for r in batch.readings
        ):
            raise HTTPException(403, "Device credential does not match station")
        count, repeated = 0, 0
        with engine.begin() as conn:
            for reading in batch.readings:
                payload = reading.model_dump(mode="json")
                for optional in ["dc_power_w", "light_lux", "hardware_protocol"]:
                    if payload[optional] is None:
                        payload.pop(optional)
                station = station_exists(conn, reading.station_id)
                if station["config"].get("source_mode", "simulated") != reading.source_kind:
                    raise HTTPException(409, "Reading source does not match the station's selected source")
                match = (
                    (db.telemetry.c.station_id == reading.station_id)
                    & (db.telemetry.c.boot_id == reading.boot_id)
                    & (db.telemetry.c.sequence == reading.sequence)
                )
                now = time.time()
                if engine.dialect.name == "sqlite":
                    from sqlalchemy.dialects.sqlite import insert
                else:
                    from sqlalchemy.dialects.postgresql import insert
                saved = conn.execute(
                    insert(db.telemetry)
                    .values(
                        station_id=reading.station_id,
                        boot_id=reading.boot_id,
                        sequence=reading.sequence,
                        observed_at=payload["observed_at"],
                        received_at=now,
                        payload=payload,
                        processed=False,
                    )
                    .on_conflict_do_nothing(index_elements=["station_id", "boot_id", "sequence"])
                )
                if saved.rowcount == 0:
                    existing = conn.execute(select(db.telemetry.c.payload).where(match)).scalar()
                    if existing != payload:
                        raise HTTPException(409, "An identity was reused with different measurements")
                    repeated += 1
                    continue
                conn.execute(
                    db.stations.update().where(db.stations.c.id == reading.station_id).values(last_seen=now)
                )
                count += 1
        accepted.inc(count)
        duplicates.inc(repeated)
        return {"accepted": count, "duplicates": repeated, "durable": True}

    @app.get("/api/v1/stations")
    def fleet(user=Depends(viewer)):
        with engine.connect() as conn:
            items = []
            for row in conn.execute(select(db.stations).order_by(db.stations.c.id)):
                item = db.row_dict(row)
                item["online"] = bool(
                    item["last_seen"] and time.time() - item["last_seen"] <= settings["heartbeat_seconds"]
                )
                item["age_seconds"] = time.time() - item["last_seen"] if item["last_seen"] else None
                result = conn.execute(
                    select(db.results.c.result).where(db.results.c.telemetry_id == item["latest_id"])
                ).scalar()
                payload = conn.execute(
                    select(db.telemetry.c.payload).where(db.telemetry.c.id == item["latest_id"])
                ).scalar()
                item.update(latest=result, reading=payload)
                if user["role"] != "operator":
                    item.pop("scenario")
                items.append(item)
            cursor = conn.execute(select(func.max(db.results.c.id))).scalar() or 0
        kinds = {item["config"].get("source_mode", "simulated") for item in items}
        return {
            "stations": items,
            "cursor": cursor,
            "source": next(iter(kinds)).upper() if len(kinds) == 1 else "MIXED",
            "server_time": time.time(),
        }

    @app.get("/api/v1/stations/{station_id}/history")
    def history(
        station_id: str,
        after: int = Query(0, ge=0),
        limit: int = Query(180, ge=1, le=500),
        user=Depends(viewer),
    ):
        with engine.connect() as conn:
            station_exists(conn, station_id)
            query = (
                select(db.telemetry, db.results.c.result)
                .outerjoin(db.results, db.telemetry.c.id == db.results.c.telemetry_id)
                .where(db.telemetry.c.station_id == station_id, db.telemetry.c.id > after)
                .order_by(db.telemetry.c.id.desc())
                .limit(limit)
            )
            return {"readings": [db.row_dict(r) for r in reversed(conn.execute(query).all())]}

    @app.get("/api/v1/stations/{station_id}/forecast")
    def forecast(station_id: str, user=Depends(viewer)):
        if state["bundle"] is None:
            raise HTTPException(503, "Model unavailable")
        with engine.connect() as conn:
            station = station_exists(conn, station_id)
            if station["config"].get("source_mode") == "hardware":
                return {
                    "state": "unsupported",
                    "reason": "Original hardware has no AC output series; the synthetic forecast is not applied to it.",
                }
            if not station["last_seen"] or time.time() - station["last_seen"] > settings["heartbeat_seconds"]:
                return {"state": "expired", "reason": "Station heartbeat is stale"}
            rows = (
                conn.execute(
                    select(db.telemetry.c.payload)
                    .where(db.telemetry.c.station_id == station_id)
                    .order_by(db.telemetry.c.observed_at.desc())
                    .limit(500)
                )
                .scalars()
                .all()
            )
        return live_forecast(
            state["bundle"],
            [
                {**r, **{k: v for k, v in station["config"].items() if k.startswith("rated_")}}
                for r in rows
                if r.get("source_kind", "simulated") == "simulated"
            ],
        )

    @app.post("/api/v1/stations/{station_id}/scenario")
    def scenario(station_id: str, payload: Scenario, user=Depends(operator)):
        with engine.begin() as conn:
            station_exists(conn, station_id)
            config = payload.model_dump()
            conn.execute(db.stations.update().where(db.stations.c.id == station_id).values(scenario=config))
            run_id = conn.execute(
                db.runs.insert().values(
                    station_id=station_id, config=config, actor="operator", created_at=time.time()
                )
            ).inserted_primary_key[0]
            conn.execute(
                db.audit.insert().values(
                    action="scenario:" + station_id, actor="operator", allowed=True, at=time.time()
                )
            )
        return {"status": "requested", "run_id": run_id, "config": config}

    @app.post("/api/v1/stations/{station_id}/commands")
    def command(station_id: str, payload: Command, user=Depends(operator)):
        now = time.time()
        with engine.begin() as conn:
            station = station_exists(conn, station_id)
            if station["config"].get("source_mode") == "hardware":
                latest = conn.execute(
                    select(db.telemetry.c.payload).where(db.telemetry.c.id == station["latest_id"])
                ).scalar()
                if os.getenv("ENABLE_PHYSICAL_RELAY", "0") != "1":
                    raise HTTPException(403, "Physical relay control is disabled on this server")
                if not latest or latest.get("hardware_protocol") != "espnow_gateway":
                    raise HTTPException(409, "No gateway relay feedback is available for this station")
            # A newer explicit state supersedes old, unexecuted requests.
            conn.execute(
                db.commands.update()
                .where(
                    db.commands.c.station_id == station_id,
                    db.commands.c.status.in_(["pending", "dispatched"]),
                )
                .values(status="superseded")
            )
            command_id = conn.execute(
                db.commands.insert().values(
                    station_id=station_id,
                    created_at=now,
                    expires_at=now + payload.ttl_seconds,
                    desired=payload.relay_on,
                    status="pending",
                    actor="operator",
                )
            ).inserted_primary_key[0]
            conn.execute(
                db.audit.insert().values(
                    action="command:" + station_id, actor="operator", allowed=True, at=now
                )
            )
        return {"id": command_id, "desired_relay_on": payload.relay_on, "status": "pending"}

    @app.get("/api/v1/device/control")
    def device_control(user=Depends(device)):
        with engine.begin() as conn:
            station = station_exists(conn, user["station_id"])
            conn.execute(
                db.commands.update()
                .where(
                    db.commands.c.station_id == user["station_id"],
                    db.commands.c.status == "pending",
                    db.commands.c.expires_at < time.time(),
                )
                .values(status="expired")
            )
            rows = conn.execute(
                select(db.commands)
                .where(db.commands.c.station_id == user["station_id"], db.commands.c.status == "pending")
                .order_by(db.commands.c.id)
            ).all()
        return {
            "scenario": station["scenario"],
            "commands": [db.row_dict(r) for r in rows],
            "latest_observed": station["latest_observed"],
            "source_mode": station["config"].get("source_mode", "simulated"),
        }

    @app.post("/api/v1/device/commands/{command_id}/ack")
    def ack_command(command_id: int, payload: Acknowledgement, user=Depends(device)):
        with engine.begin() as conn:
            command = db.row_dict(
                conn.execute(
                    select(db.commands).where(
                        db.commands.c.id == command_id, db.commands.c.station_id == user["station_id"]
                    )
                ).first()
            )
            if command is None:
                raise HTTPException(404, "Command not found")
            if command["status"] == "acknowledged" and command["confirmed"] == payload.relay_on:
                return {"status": "acknowledged", "duplicate": True}
            if (
                command["status"] != "pending"
                or command["expires_at"] < time.time()
                or command["desired"] != payload.relay_on
            ):
                raise HTTPException(409, "Command expired, superseded, or state mismatch")
            conn.execute(
                db.commands.update()
                .where(db.commands.c.id == command_id)
                .values(status="acknowledged", confirmed=payload.relay_on, ack_at=time.time())
            )
        return {"status": "acknowledged", "duplicate": False}

    @app.get("/api/v1/commands")
    def command_history(user=Depends(viewer)):
        with engine.connect() as conn:
            return [
                db.row_dict(r)
                for r in conn.execute(select(db.commands).order_by(db.commands.c.id.desc()).limit(100))
            ]

    @app.get("/api/v1/incidents")
    def incident_list(user=Depends(viewer)):
        with engine.connect() as conn:
            return {
                "incidents": [
                    db.row_dict(r)
                    for r in conn.execute(select(db.incidents).order_by(db.incidents.c.id.desc()).limit(100))
                ],
                "events": [
                    db.row_dict(r)
                    for r in conn.execute(
                        select(db.incident_events).order_by(db.incident_events.c.id.desc()).limit(200)
                    )
                ],
                "notifications": [
                    db.row_dict(r)
                    for r in conn.execute(
                        select(db.notifications).order_by(db.notifications.c.id.desc()).limit(100)
                    )
                ],
            }

    @app.post("/api/v1/incidents/{incident_id}/ack")
    def ack_incident(incident_id: int, user=Depends(operator)):
        with engine.begin() as conn:
            row = db.row_dict(
                conn.execute(select(db.incidents).where(db.incidents.c.id == incident_id)).first()
            )
            if row is None:
                raise HTTPException(404, "Incident not found")
            if row["acknowledged_at"] is None:
                conn.execute(
                    db.incidents.update()
                    .where(db.incidents.c.id == incident_id)
                    .values(acknowledged_at=time.time())
                )
                conn.execute(
                    db.incident_events.insert().values(
                        incident_id=incident_id,
                        kind="acknowledged",
                        at=time.time(),
                        details={"actor": "operator"},
                    )
                )
        return {"status": "acknowledged"}

    @app.post("/api/v1/readings/{telemetry_id}/reviews")
    def review(telemetry_id: int, payload: Review, user=Depends(operator)):
        with engine.begin() as conn:
            if (
                conn.execute(select(db.telemetry.c.id).where(db.telemetry.c.id == telemetry_id)).first()
                is None
            ):
                raise HTTPException(404, "Reading not found")
            review_id = conn.execute(
                db.reviews.insert().values(
                    telemetry_id=telemetry_id,
                    label=payload.label,
                    reason=payload.reason,
                    actor="operator",
                    at=time.time(),
                )
            ).inserted_primary_key[0]
        return {"id": review_id, "status": "recorded", "used_for_training": False}

    @app.get("/api/v1/reviews")
    def review_queue(user=Depends(viewer)):
        with engine.connect() as conn:
            recent = [
                db.row_dict(r)
                for r in conn.execute(select(db.results).order_by(db.results.c.id.desc()).limit(500))
            ]
            records = [
                db.row_dict(r)
                for r in conn.execute(select(db.reviews).order_by(db.reviews.c.id.desc()).limit(200))
            ]
        return {
            "queue": [
                r for r in recent if r["result"]["decision_state"] in {"uncertain", "unknown", "data_quality"}
            ][:50],
            "reviews": records,
        }

    @app.get("/api/v1/model")
    def model_info(user=Depends(viewer)):
        if state["bundle"] is None:
            raise HTTPException(503, "Model unavailable")
        version = state["bundle"]["version"]
        report = json.loads((Path(settings["models"]) / version / "evaluation.json").read_text())
        return report

    @app.get("/api/v1/drift")
    def drift(user=Depends(viewer)):
        from solarsense.monitoring import drift_report

        if state["bundle"] is None:
            raise HTTPException(503, "Model unavailable")
        with engine.connect() as conn:
            station_configs = {
                r.id: r.config for r in conn.execute(select(db.stations.c.id, db.stations.c.config))
            }
            recent = (
                conn.execute(select(db.telemetry.c.payload).order_by(db.telemetry.c.id.desc()).limit(500))
                .scalars()
                .all()
            )
        rows = [
            {**r, **{k: v for k, v in station_configs[r["station_id"]].items() if k.startswith("rated_")}}
            for r in recent
        ]
        return drift_report(state["bundle"], rows)

    @app.get("/metrics")
    def metrics(user=Depends(viewer)):
        with engine.connect() as conn:
            queue.set(
                conn.execute(
                    select(func.count()).select_from(db.telemetry).where(db.telemetry.c.processed.is_(False))
                ).scalar()
            )
            notifications_failed.set(
                conn.execute(
                    select(func.count())
                    .select_from(db.notifications)
                    .where(db.notifications.c.status == "failed")
                ).scalar()
            )
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    @app.websocket("/ws")
    async def stream(socket: WebSocket):
        if socket.headers.get("origin") not in settings["origins"] or state["viewers"] >= 20:
            await socket.close(code=1008)
            return
        await socket.accept()
        connected = False
        try:
            hello = await asyncio.wait_for(socket.receive_json(), timeout=5)
            user = identity(str(hello.get("token", "")))
            if user["role"] == "device":
                raise HTTPException(403)
            cursor = max(0, int(hello.get("cursor", 0)))
            connected = True
            state["viewers"] += 1
            viewers.inc()
            await socket.send_json({"type": "connected", "resync": True})
            while True:
                with engine.connect() as conn:
                    latest = conn.execute(select(func.max(db.results.c.id))).scalar() or 0
                await asyncio.wait_for(
                    socket.send_json(
                        {
                            "type": "changed" if latest != cursor else "heartbeat",
                            "cursor": latest,
                            "server_time": time.time(),
                        }
                    ),
                    timeout=2,
                )
                cursor = latest
                # Read a ping or disconnect so closed tabs release their slot.
                try:
                    message = await asyncio.wait_for(socket.receive_text(), timeout=1)
                    if message == "close":
                        break
                except asyncio.TimeoutError:
                    pass
        except (
            WebSocketDisconnect,
            HTTPException,
            ValueError,
            TypeError,
            asyncio.TimeoutError,
            SQLAlchemyError,
        ):
            with contextlib.suppress(RuntimeError):
                await socket.close(code=1008)
        finally:
            if connected:
                state["viewers"] -= 1
                viewers.dec()

    from solarsense.integrations import register_integrations

    register_integrations(app, engine, settings, operator, viewer, station_exists, ingest)

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="dashboard")
    return app
