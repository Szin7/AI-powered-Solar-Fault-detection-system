import hashlib
import hmac
import ipaddress
import json
import os
import time
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from solarsense import db
from solarsense.config import STATIONS
from solarsense.schemas import Batch, Reading
from solarsense.technicians import channel_ready, delivery_config, message_text
from solarsense.weather import weather_snapshot


class GatewayRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    senderId: int = Field(ge=1, le=3)
    ldrValue: int = Field(ge=0, le=4095)
    dhtTemp: float
    humidity: float
    thermistorTemp: float
    voltage: float
    current: float
    relayStatus: bool = False
    valid: bool
    gateway_timestamp_ms: int = Field(ge=0)


class Technician(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    channel: str = Field(pattern=r"^(whatsapp|sms)$")
    enabled: bool = False
    allow_simulated: bool = False


class SourceMode(BaseModel):
    mode: str = Field(pattern=r"^(simulated|hardware)$")


def register_integrations(app, engine, settings, operator, viewer, station_exists, ingest):
    def gateway(request: Request, x_gateway_key: str = Header(default="")):
        secret = os.getenv("SOLARSENSE_GATEWAY_KEY", "")
        if secret and hmac.compare_digest(x_gateway_key, secret):
            return
        allowed = {v.strip() for v in os.getenv("LEGACY_GATEWAY_IPS", "").split(",") if v.strip()}
        host = request.client.host if request.client else ""
        # Legacy firmware has no auth header: an explicit private-LAN allowlist is opt-in.
        try:
            private = ipaddress.ip_address(host).is_private
        except ValueError:
            private = False
        if host in allowed and private:
            return
        raise HTTPException(401, "Configure a gateway key or explicitly allow the legacy gateway LAN IP")

    @app.get("/api/v1/integrations")
    def integrations(user=Depends(viewer)):
        config = delivery_config()
        with engine.connect() as conn:
            modes = {
                r.id: r.config.get("source_mode", "simulated") for r in conn.execute(select(db.stations))
            }
        return {
            "source_modes": modes,
            "notification_mode": config["mode"],
            "channels_ready": {c: channel_ready(c, config) for c in ["whatsapp", "sms"]},
            "physical_relays_enabled": os.getenv("ENABLE_PHYSICAL_RELAY", "0") == "1",
            "gateway_configured": bool(
                os.getenv("SOLARSENSE_GATEWAY_KEY") or os.getenv("LEGACY_GATEWAY_IPS")
            ),
        }

    @app.post("/api/v1/stations/{station_id}/source")
    def set_source(station_id: str, body: SourceMode, user=Depends(operator)):
        with engine.begin() as conn:
            station = station_exists(conn, station_id)
            if station["config"].get("source_mode", "simulated") == body.mode:
                return {"mode": body.mode}
            config = {**station["config"], "source_mode": body.mode, "source_changed_at": time.time()}
            conn.execute(
                db.stations.update()
                .where(db.stations.c.id == station_id)
                .values(config=config, latest_observed=None, latest_id=None, last_seen=None)
            )
            conn.execute(
                db.commands.update()
                .where(
                    db.commands.c.station_id == station_id,
                    db.commands.c.status.in_(["pending", "dispatched"]),
                )
                .values(status="superseded")
            )
            conn.execute(
                db.incidents.update()
                .where(db.incidents.c.station_id == station_id, db.incidents.c.status == "open")
                .values(status="closed", closed_at=time.time())
            )
            conn.execute(
                db.audit.insert().values(
                    action="source:" + station_id + ":" + body.mode,
                    actor="operator",
                    allowed=True,
                    at=time.time(),
                )
            )
        return {"mode": body.mode, "history_retained": True}

    @app.get("/api/v1/weather")
    def weather(user=Depends(viewer)):
        return weather_snapshot()

    @app.get("/api/v1/stations/{station_id}/technician")
    def contact(station_id: str, user=Depends(operator)):
        with engine.connect() as conn:
            station_exists(conn, station_id)
            value = conn.execute(
                select(db.integration_settings.c.value).where(
                    db.integration_settings.c.key == "technician:" + station_id
                )
            ).scalar()
        return {"contact": value, "delivery_mode": delivery_config()["mode"]}

    @app.post("/api/v1/stations/{station_id}/technician")
    def save_contact(station_id: str, body: Technician, user=Depends(operator)):
        config = delivery_config()
        if body.enabled and config["mode"] == "live" and not channel_ready(body.channel, config):
            raise HTTPException(
                422, "Configure messaging credentials and the WhatsApp template before enabling live alerts"
            )
        with engine.begin() as conn:
            station_exists(conn, station_id)
            key = "technician:" + station_id
            if conn.execute(
                select(db.integration_settings.c.key).where(db.integration_settings.c.key == key)
            ).first():
                conn.execute(
                    db.integration_settings.update()
                    .where(db.integration_settings.c.key == key)
                    .values(value=body.model_dump())
                )
            else:
                conn.execute(db.integration_settings.insert().values(key=key, value=body.model_dump()))
        return {
            "saved": True,
            "delivery_mode": config["mode"],
            "note": "Only future incident transitions create alerts.",
        }

    @app.get("/api/v1/technician-alerts")
    def technician_alerts(user=Depends(viewer)):
        with engine.connect() as conn:
            jobs = [
                db.row_dict(r)
                for r in conn.execute(
                    select(db.technician_deliveries).order_by(db.technician_deliveries.c.id.desc()).limit(50)
                )
            ]
        for job in jobs:
            if user["role"] != "operator":
                contact = job["payload"]["contact"]
                job["payload"] = {
                    **job["payload"],
                    "contact": {
                        "name": "Assigned technician",
                        "phone": "***" + contact["phone"][-4:],
                        "channel": contact["channel"],
                    },
                }
        return {"alerts": jobs, "mode": delivery_config()["mode"]}

    @app.get("/api/v1/stations/{station_id}/alert-preview")
    def preview(station_id: str, user=Depends(operator)):
        with engine.connect() as conn:
            station = station_exists(conn, station_id)
            result = conn.execute(
                select(db.results.c.result).where(db.results.c.telemetry_id == station["latest_id"])
            ).scalar()
        if not result:
            raise HTTPException(409, "No processed reading available for this station")
        return {
            "sent": False,
            "message": message_text(
                {**result, "station_id": station_id, "label": result["stabilized_class"], "kind": "preview"}
            ),
        }

    @app.post("/api/gateway-data")
    def gateway_data(records: list[GatewayRecord], allowed=Depends(gateway)):
        if not 1 <= len(records) <= 50:
            raise HTTPException(422, "Send one to fifty gateway records")
        count, repeated = 0, 0
        for record in records:
            station_id = STATIONS[record.senderId - 1]["id"]
            fingerprint = hashlib.sha256(
                json.dumps(record.model_dump(), sort_keys=True).encode()
            ).hexdigest()[:32]
            boot = "gateway-" + fingerprint
            with engine.connect() as conn:
                station = station_exists(conn, station_id)
                if station["config"].get("source_mode") != "hardware":
                    raise HTTPException(409, "Select hardware source for " + station_id)
                existing = conn.execute(
                    select(db.telemetry.c.payload).where(
                        db.telemetry.c.station_id == station_id,
                        db.telemetry.c.boot_id == boot,
                        db.telemetry.c.sequence == record.gateway_timestamp_ms,
                    )
                ).scalar()
            payload = existing or {
                "schema_version": 1,
                "device_id": station_id,
                "station_id": station_id,
                "boot_id": boot,
                "sequence": record.gateway_timestamp_ms,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "source_kind": "hardware",
                "clock_kind": "gateway_receive",
                "hardware_protocol": "espnow_gateway",
                "simulator_version": "1.0.0",
                "scenario_run_id": "hardware-gateway",
                "voltage_v": record.voltage if record.valid else None,
                "current_a": record.current if record.valid else None,
                "ambient_temp_c": record.dhtTemp,
                "surface_temp_c": record.thermistorTemp,
                "humidity_pct": record.humidity,
                "light_adc": record.ldrValue,
                "ac_power_w": None,
                "irradiance_wm2": None,
                "load_limit_w": None,
                "dc_power_w": record.voltage * record.current if record.valid else None,
                "relay_on": record.relayStatus,
                "missing_reason": "Gateway has no AC meter or calibrated irradiance sensor"
                if record.valid
                else "Device marked sample invalid",
            }
            saved = ingest(Batch(readings=[Reading(**payload)]), {"role": "device", "station_id": station_id})
            count += saved["accepted"]
            repeated += saved["duplicates"]
            if saved["accepted"]:
                with engine.begin() as conn:
                    # Confirm only a command that this gateway actually polled.
                    pending = conn.execute(
                        select(db.commands).where(
                            db.commands.c.station_id == station_id,
                            db.commands.c.status == "dispatched",
                            db.commands.c.desired == record.relayStatus,
                            db.commands.c.expires_at > time.time(),
                        )
                    ).first()
                    if pending:
                        conn.execute(
                            db.commands.update()
                            .where(db.commands.c.id == pending.id)
                            .values(status="acknowledged", confirmed=record.relayStatus, ack_at=time.time())
                        )
        return {"status": "success", "processed": count, "duplicates": repeated, "durable": True}

    @app.get("/api/get-command/{sender_id}")
    def get_command(sender_id: int, allowed=Depends(gateway)):
        if sender_id not in {1, 2, 3}:
            raise HTTPException(404, "Unknown sender")
        if os.getenv("ENABLE_PHYSICAL_RELAY", "0") != "1":
            return Response(status_code=204)
        station_id = STATIONS[sender_id - 1]["id"]
        now = time.time()
        with engine.begin() as conn:
            station = station_exists(conn, station_id)
            if station["config"].get("source_mode") != "hardware":
                return Response(status_code=204)
            conn.execute(
                db.commands.update()
                .where(
                    db.commands.c.station_id == station_id,
                    db.commands.c.status.in_(["pending", "dispatched"]),
                    db.commands.c.expires_at <= now,
                )
                .values(status="expired")
            )
            command = conn.execute(
                select(db.commands)
                .where(
                    db.commands.c.station_id == station_id,
                    db.commands.c.status.in_(["pending", "dispatched"]),
                    db.commands.c.expires_at > now,
                )
                .order_by(db.commands.c.id.desc())
            ).first()
            if not command:
                return Response(status_code=204)
            conn.execute(
                db.commands.update().where(db.commands.c.id == command.id).values(status="dispatched")
            )
            return {
                "station_id": sender_id,
                "command": "ACTIVATE_RELAY" if command.desired else "DEACTIVATE_RELAY",
            }
