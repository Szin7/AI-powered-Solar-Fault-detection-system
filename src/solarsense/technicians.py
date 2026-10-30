import json
import os
import re
import time

import httpx
from sqlalchemy import select

from solarsense import db


def delivery_config():
    return {
        "mode": os.getenv("TECHNICIAN_DELIVERY", "preview"),
        "sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "token": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "sms_from": os.getenv("TWILIO_SMS_FROM", ""),
        "whatsapp_from": os.getenv("TWILIO_WHATSAPP_FROM", ""),
        "template": os.getenv("TWILIO_CONTENT_SID", ""),
    }


def channel_ready(channel, config):
    sender = config[channel + "_from"]
    valid = bool(re.fullmatch(r"AC[0-9a-fA-F]{32}", config["sid"]) and config["token"] and sender)
    if channel == "whatsapp":
        valid = valid and bool(re.fullmatch(r"HX[0-9a-fA-F]{32}", config["template"]))
    return valid


def message_text(details):
    prefix = "SIMULATED DEMO" if details.get("source_kind", "simulated") == "simulated" else "HARDWARE"
    score = details.get("confidence")
    score_text = (
        f"{score * 100:.1f}% model score (uncalibrated)" if score is not None else "no valid model score"
    )
    return (
        f"SolarSense [{prefix}]\nStation: {details['station_id']}\n"
        f"Event: {details['kind']} — {details['label'].replace('_', ' ')}\n{score_text}\n"
        f"Action: {details.get('resolution', 'Inspect the dashboard and verify sensor readings.')}\n"
        f"Event time: {details.get('observed_at', 'unavailable')}"
    )[:1500]


def enqueue_alert(conn, event_id, details):
    if details["kind"] not in {"fault", "recovery"}:
        return
    contact = conn.execute(
        select(db.integration_settings.c.value).where(
            db.integration_settings.c.key == "technician:" + details["station_id"]
        )
    ).scalar()
    if not contact or not contact["enabled"]:
        return
    if details.get("source_kind", "simulated") == "simulated" and not contact["allow_simulated"]:
        return
    now = time.time()
    config = delivery_config()
    payload = {**details, "contact": contact, "message": message_text(details)}
    # The unique event id and incident transitions prevent an alert per sensor row.
    conn.execute(
        db.technician_deliveries.insert().values(
            event_id=event_id,
            station_id=details["station_id"],
            payload=payload,
            status="pending" if config["mode"] == "live" else "preview",
            attempts=0,
            next_attempt=now,
            created_at=now,
            updated_at=now,
        )
    )


def twilio_payload(job, config):
    contact = job["payload"]["contact"]
    if not channel_ready(contact["channel"], config):
        raise ValueError("Messaging credentials or approved WhatsApp template are missing")
    if contact["channel"] == "sms":
        return {"To": contact["phone"], "From": config["sms_from"], "Body": job["payload"]["message"]}
    return {
        "To": "whatsapp:" + contact["phone"],
        "From": "whatsapp:" + config["whatsapp_from"].removeprefix("whatsapp:"),
        "ContentSid": config["template"],
        "ContentVariables": json.dumps(
            {
                "1": job["station_id"],
                "2": job["payload"]["kind"],
                "3": job["payload"]["label"].replace("_", " "),
                "4": ("SIMULATED: " if job["payload"].get("source_kind", "simulated") == "simulated" else "")
                + job["payload"].get("resolution", "Inspect dashboard").replace("\n", " ")[:400],
            }
        ),
    }


def deliver_technician_alerts(engine, config=None, client=None):
    config = config or delivery_config()
    if config["mode"] != "live":
        return 0
    now = time.time()
    with engine.begin() as conn:
        # A crash during POST may have sent the message. Do not blindly repeat it.
        conn.execute(
            db.technician_deliveries.update()
            .where(
                db.technician_deliveries.c.status == "submitting",
                db.technician_deliveries.c.updated_at < now - 60,
            )
            .values(status="uncertain", error="Interrupted submission; check provider before retrying")
        )
        jobs = conn.execute(
            select(db.technician_deliveries)
            .where(
                db.technician_deliveries.c.status.in_(["pending", "submitted"]),
                db.technician_deliveries.c.next_attempt <= now,
            )
            .limit(10)
        ).all()
    owned = client is None
    client = client or httpx.Client(timeout=5, trust_env=False)
    try:
        for raw in jobs:
            job = db.row_dict(raw)
            status, error, sid = job["status"], None, job["provider_sid"]
            submission_started = False
            current_contact = None
            with engine.connect() as conn:
                current_contact = conn.execute(
                    select(db.integration_settings.c.value).where(
                        db.integration_settings.c.key == "technician:" + job["station_id"]
                    )
                ).scalar()
            if status == "pending" and (
                not current_contact
                or not current_contact["enabled"]
                or current_contact["phone"] != job["payload"]["contact"]["phone"]
                or current_contact["channel"] != job["payload"]["contact"]["channel"]
                or (
                    job["payload"].get("source_kind", "simulated") == "simulated"
                    and not current_contact["allow_simulated"]
                )
            ):
                status, error = "cancelled", "Contact disabled or reassigned before submission"
            else:
                try:
                    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", config["sid"]):
                        raise ValueError("Messaging account not configured")
                    base = "https://api.twilio.com/2010-04-01/Accounts/" + config["sid"] + "/Messages"
                    auth = (config["sid"], config["token"])
                    if status == "pending":
                        data = twilio_payload(job, config)
                        with engine.begin() as conn:
                            claimed = conn.execute(
                                db.technician_deliveries.update()
                                .where(
                                    db.technician_deliveries.c.id == job["id"],
                                    db.technician_deliveries.c.status == "pending",
                                )
                                .values(status="submitting", updated_at=now)
                            )
                            if claimed.rowcount != 1:
                                continue
                        submission_started = True
                        response = client.post(base + ".json", data=data, auth=auth)
                        response.raise_for_status()
                        sid = response.json()["sid"]
                        if not re.fullmatch(r"[SM][M][0-9a-fA-F]{32}", sid):
                            raise KeyError("Invalid message id")
                        status = "submitted"
                    else:
                        response = client.get(base + "/" + sid + ".json", auth=auth)
                        response.raise_for_status()
                        provider_status = response.json()["status"]
                        status = (
                            "delivered"
                            if provider_status in {"delivered", "read"}
                            else (
                                "failed"
                                if provider_status in {"failed", "undelivered", "canceled"}
                                else "submitted"
                            )
                        )
                        if status == "submitted" and now - job["created_at"] > 86400:
                            status, error = "uncertain", "No delivery confirmation within 24 hours"
                except httpx.ConnectError:
                    status, error = (
                        (
                            "submitted"
                            if job["status"] == "submitted"
                            else "pending"
                            if job["attempts"] < 4
                            else "failed"
                        ),
                        "Could not connect to provider",
                    )
                except httpx.HTTPStatusError as exc:
                    if job["status"] == "submitted":
                        status = "submitted"
                    else:
                        status = (
                            "pending" if exc.response.status_code == 429 and job["attempts"] < 4 else "failed"
                        )
                    error = "Provider HTTP " + str(exc.response.status_code)
                except ValueError:
                    status = (
                        "submitted"
                        if job["status"] == "submitted"
                        else "uncertain"
                        if submission_started
                        else "failed"
                    )
                    error = "Provider configuration or response is invalid"
                except (httpx.HTTPError, KeyError):
                    status = "submitted" if job["status"] == "submitted" else "uncertain"
                    error = "Delivery outcome unknown; inspect provider before repeating"
            if status == "submitted" and now - job["created_at"] > 86400:
                status, error = "uncertain", "No delivery confirmation within 24 hours"
            with engine.begin() as conn:
                conn.execute(
                    db.technician_deliveries.update()
                    .where(db.technician_deliveries.c.id == job["id"])
                    .values(
                        status=status,
                        error=error,
                        provider_sid=sid,
                        attempts=job["attempts"] + 1,
                        next_attempt=now + min(300, 30 * (job["attempts"] + 1)),
                        updated_at=now,
                    )
                )
    finally:
        if owned:
            client.close()
    return len(jobs)
