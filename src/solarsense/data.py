import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pvlib.pvsystem import pvwatts_dc

from solarsense.config import LABELS, SEED, STATIONS


def reading(step, station, rng, fault="normal", severity=0.6, start=None, minutes=5, cloud=1.0):
    start = start or datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc)
    observed = start + timedelta(minutes=minutes * step)
    local = observed.astimezone(ZoneInfo("Asia/Kathmandu"))
    local_hour = local.hour + local.minute / 60 + local.second / 3600
    sun = max(0, np.sin(np.pi * (local_hour - 6) / 12))
    cloud_shape = 0.88 + 0.10 * np.sin(step / 11) + 0.02 * np.sin(step / 3)
    irradiance = max(0, 1000 * sun * cloud_shape * cloud + rng.normal(0, 6) * (sun > 0))
    ambient = 21 + 8 * sun + rng.normal(0, 0.3)
    surface = ambient + 0.027 * irradiance
    available = max(0, float(pvwatts_dc(irradiance, surface, station["rated_power_w"], -0.004)))
    load = station.get("load_limit_w", station["rated_power_w"] * 0.92)
    delivered = min(available, load)
    voltage = station["rated_voltage_v"] * (0.9 + 0.1 * sun) * (1 - 0.003 * (surface - 25))
    voltage = max(0, voltage + rng.normal(0, 0.13)) if irradiance > 5 else 0.0
    current = delivered / max(voltage, 1) * (1 + rng.normal(0, 0.018))
    active = fault if irradiance >= 80 else "normal"
    if active == "open_circuit":
        voltage *= 1.12
        current *= 0.008
    elif active == "short_circuit":
        voltage *= 0.025
        current *= 1.08
    elif active == "partial_shading":
        voltage *= 1 - severity * (0.3 + 0.08 * np.sin(step / 2))
        current *= 1 - severity * (0.65 + 0.15 * np.sin(step / 3))
    elif active == "soiling":
        voltage *= 1 - 0.025 * severity
        current *= 1 - 0.6 * severity
    elif active == "sensor_offset":
        voltage *= 1.65
    elif active == "unknown":
        voltage *= 0.45
        current *= 1.65
    ac = voltage * current * 0.95 * (1 + rng.normal(0, 0.006))
    if active == "inverter_fault":
        ac *= 1 - 0.96 * severity
    row = {
        "schema_version": 1,
        "device_id": station["id"],
        "station_id": station["id"],
        "boot_id": "fixture",
        "sequence": step,
        "observed_at": observed.isoformat(),
        "voltage_v": round(voltage * station.get("voltage_gain", 1.0), 4),
        "current_a": round(current * station.get("current_gain", 1.0), 4),
        "ac_power_w": round(max(0, ac), 4),
        "irradiance_wm2": round(irradiance * station.get("irradiance_gain", 1.0), 4),
        "ambient_temp_c": round(ambient, 4),
        "surface_temp_c": round(surface, 4),
        "humidity_pct": round(float(np.clip(65 - 20 * sun + rng.normal(0, 1), 0, 100)), 3),
        "light_adc": int(np.clip(irradiance / 1000 * 3500, 0, 4095)),
        "load_limit_w": float(load),
        "relay_on": True,
        "source_kind": "simulated",
        "simulator_version": "1.0.0",
        "scenario_run_id": "fixture",
        "clock_kind": "event",
        "missing_reason": None,
    }
    return row, active


def generate_dataset(output="data/generated", sessions=84, steps=144, seed=SEED):
    if sessions < 24 or steps < 60:
        raise ValueError("Use at least 24 sessions and 60 steps for separate splits and all labels")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    # Entire sessions are held out. Test conditions are fixed before training.
    split_cycle = ["train"] * 7 + ["calibration"] * 2 + ["validation"] * 2 + ["test"] * 3
    for session in range(sessions):
        rng = np.random.default_rng(seed + session * 997)
        split = split_cycle[(session // 6) % len(split_cycle)]
        station = dict(STATIONS[(session + session // 6) % 3])
        station["rated_power_w"] *= rng.uniform(0.8, 1.2)
        station["rated_voltage_v"] *= rng.uniform(0.96, 1.04)
        station["load_limit_w"] = station["rated_power_w"] * rng.uniform(0.55, 1.0)
        station["voltage_gain"] = rng.uniform(0.96, 1.04)
        station["current_gain"] = rng.uniform(0.94, 1.06)
        station["irradiance_gain"] = rng.uniform(0.88, 1.12)
        severity = rng.uniform(0.3, 0.88) if split != "test" else rng.uniform(0.2, 0.95)
        cloud = rng.uniform(0.65, 1.0) if split != "test" else rng.uniform(0.45, 0.95)
        fault = LABELS[session % len(LABELS)]
        fault_start = int(steps * rng.uniform(0.2, 0.35))
        fault_end = int(steps * rng.uniform(0.6, 0.85))
        start = datetime(2026, 1, 1, 0, 15, tzinfo=timezone.utc) + timedelta(days=session)
        for step in range(steps):
            applied = fault if fault_start <= step < fault_end else "normal"
            row, truth = reading(step, station, rng, applied, severity, start, cloud=cloud)
            row.update(
                session=f"session-{session:03}",
                split=split,
                fault=truth,
                rated_power_w=station["rated_power_w"],
                rated_voltage_v=station["rated_voltage_v"],
            )
            rows.append(row)
    df = pd.DataFrame(rows)
    required = {"train", "calibration", "validation", "test"}
    if set(df.split) != required:
        # Small smoke datasets use complete, balanced groups of six sessions.
        groups = sorted(df.session.unique())
        mapping = {
            s: ["train", "calibration", "validation", "test"][min(3, i * 4 // len(groups))]
            for i, s in enumerate(groups)
        }
        df["split"] = df.session.map(mapping)
    path = output / "solar.csv"
    df.to_csv(path, index=False, float_format="%.7f")
    manifest = {
        "seed": seed,
        "sessions": sessions,
        "steps": steps,
        "rows": len(df),
        "generator": "1.0.0",
        "synthetic": True,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "split_sessions": {k: sorted(v.session.unique().tolist()) for k, v in df.groupby("split")},
        "test_shift": "held-out sessions; cloud 0.45-0.95; severity 0.20-0.95",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Generated {len(df)} synthetic rows in {path}")
    return df, manifest
