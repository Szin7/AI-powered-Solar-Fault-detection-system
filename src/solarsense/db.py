import hashlib
import json
import sqlite3
import time
from pathlib import Path

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    select,
)

from solarsense.config import STATIONS, digest

metadata = MetaData()
schema = Table("schema_version", metadata, Column("version", Integer, primary_key=True))
stations = Table(
    "stations",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("name", String(80)),
    Column("config", JSON),
    Column("scenario", JSON),
    Column("last_seen", Float),
    Column("latest_observed", String(40)),
    Column("latest_id", Integer),
)
credentials = Table(
    "device_credentials",
    metadata,
    Column("station_id", String(40), primary_key=True),
    Column("token_hash", String(64), unique=True),
)
telemetry = Table(
    "telemetry",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("station_id", String(40), nullable=False),
    Column("boot_id", String(64), nullable=False),
    Column("sequence", BigInteger, nullable=False),
    Column("observed_at", String(40), nullable=False),
    Column("received_at", Float, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("processed", Boolean, nullable=False, default=False),
    UniqueConstraint("station_id", "boot_id", "sequence", name="reading_identity"),
)
Index("station_event_time", telemetry.c.station_id, telemetry.c.observed_at)
Index("pending_telemetry", telemetry.c.processed, telemetry.c.id)
results = Table(
    "inference_results",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("telemetry_id", Integer, nullable=False),
    Column("station_id", String(40), nullable=False),
    Column("model_version", String(20), nullable=False),
    Column("processed_at", Float),
    Column("late", Boolean),
    Column("result", JSON),
    UniqueConstraint("telemetry_id", "model_version", name="result_identity"),
)
incidents = Table(
    "incidents",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("station_id", String(40)),
    Column("label", String(40)),
    Column("opened_at", Float),
    Column("observed_at", String(40)),
    Column("closed_at", Float),
    Column("acknowledged_at", Float),
    Column("status", String(20)),
)
incident_events = Table(
    "incident_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("incident_id", Integer),
    Column("kind", String(20)),
    Column("at", Float),
    Column("details", JSON),
)
commands = Table(
    "commands",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("station_id", String(40)),
    Column("created_at", Float),
    Column("expires_at", Float),
    Column("desired", Boolean),
    Column("confirmed", Boolean),
    Column("status", String(20)),
    Column("actor", String(30)),
    Column("ack_at", Float),
)
notifications = Table(
    "notification_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("event_id", Integer, unique=True),
    Column("payload", JSON),
    Column("attempts", Integer, default=0),
    Column("next_attempt", Float),
    Column("status", String(20)),
    Column("history", JSON),
)
inbox = Table(
    "notification_inbox",
    metadata,
    Column("event_id", Integer, primary_key=True),
    Column("payload", JSON),
    Column("delivered_at", Float),
)
reviews = Table(
    "label_reviews",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("telemetry_id", Integer),
    Column("label", String(40)),
    Column("reason", String(500)),
    Column("actor", String(30)),
    Column("at", Float),
)
releases = Table(
    "model_releases",
    metadata,
    Column("version", String(20), primary_key=True),
    Column("manifest", JSON),
    Column("loaded_at", Float),
)
runs = Table(
    "scenario_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("station_id", String(40)),
    Column("config", JSON),
    Column("actor", String(30)),
    Column("created_at", Float),
)
audit = Table(
    "audit_log",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("action", String(100)),
    Column("actor", String(40)),
    Column("allowed", Boolean),
    Column("at", Float),
)


integration_settings = Table(
    "integration_settings",
    metadata,
    Column("key", String(80), primary_key=True),
    Column("value", JSON),
)
technician_deliveries = Table(
    "technician_deliveries",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("event_id", Integer, unique=True),
    Column("station_id", String(40)),
    Column("payload", JSON),
    Column("status", String(30)),
    Column("provider_sid", String(50)),
    Column("attempts", Integer, default=0),
    Column("next_attempt", Float),
    Column("created_at", Float),
    Column("updated_at", Float),
    Column("error", String(200)),
)


def connect(url):
    kwargs = {"connect_args": {"check_same_thread": False, "timeout": 10}} if url.startswith("sqlite") else {}
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_settings(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def migrate(engine, config):
    # Version one is additive. Later versions must supply an explicit migration.
    metadata.create_all(engine)
    with engine.begin() as conn:
        versions = conn.execute(select(schema.c.version)).scalars().all()
        if versions and versions != [1]:
            raise RuntimeError("Unsupported database schema; restore a compatible application")
        if not versions:
            conn.execute(schema.insert().values(version=1))
        for station in STATIONS:
            if conn.execute(select(stations.c.id).where(stations.c.id == station["id"])).first() is None:
                conn.execute(
                    stations.insert().values(
                        id=station["id"],
                        name=station["name"],
                        config=station,
                        scenario={
                            "fault": "normal",
                            "severity": 0.7,
                            "network": "normal",
                            "cloud": 1,
                            "enabled": False,
                        },
                    )
                )
            token_hash = digest(config["credentials"]["devices"][station["id"]])
            existing = conn.execute(
                select(credentials.c.station_id).where(credentials.c.station_id == station["id"])
            ).first()
            if existing:
                conn.execute(
                    credentials.update()
                    .where(credentials.c.station_id == station["id"])
                    .values(token_hash=token_hash)
                )
            else:
                conn.execute(credentials.insert().values(station_id=station["id"], token_hash=token_hash))


def row_dict(row):
    return dict(row._mapping) if row is not None else None


def add_event(conn, incident_id, kind, station_id, label, context=None):
    now = time.time()
    details = {"station_id": station_id, "label": label, "kind": kind, **(context or {})}
    event_id = conn.execute(
        incident_events.insert().values(incident_id=incident_id, kind=kind, at=now, details=details)
    ).inserted_primary_key[0]
    conn.execute(
        notifications.insert().values(
            event_id=event_id, payload=details, attempts=0, next_attempt=now, status="pending", history=[]
        )
    )
    from solarsense.technicians import enqueue_alert

    enqueue_alert(conn, event_id, details)


def backup_sqlite(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.exists() or destination.exists():
        raise ValueError("Source must exist and backup destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def backup_snapshot(config, destination):
    import shutil

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    if not config["database_url"].startswith("sqlite:///"):
        raise ValueError("Use pg_dump for PostgreSQL; see docs/OPERATIONS.md")
    checksum = backup_sqlite(config["database_url"].removeprefix("sqlite:///"), destination / "solar.db")
    shutil.copytree(config["models"], destination / "models")
    manifest = {
        "database_sha256": checksum,
        "schema": 1,
        "model_files": {
            str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((destination / "models").rglob("*"))
            if p.is_file()
        },
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def restore_snapshot(source, destination):
    import shutil

    source, destination = Path(source), Path(destination)
    manifest = json.loads((source / "manifest.json").read_text())
    if destination.exists():
        raise ValueError("Restore requires a new, empty destination")
    expected = {"solar.db": manifest["database_sha256"], **manifest["model_files"]}
    for name, checksum in expected.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Backup integrity failed: {name}")
    destination.mkdir(parents=True)
    (destination / "var").mkdir()
    backup_sqlite(source / "solar.db", destination / "var" / "solar.db")
    shutil.copytree(source / "models", destination / "models")
    # Device credentials are intentionally regenerated on first startup.
    return str(destination)
