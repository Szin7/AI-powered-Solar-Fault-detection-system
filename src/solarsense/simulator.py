import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import yaml

from solarsense.config import STATIONS, load_settings
from solarsense.data import reading


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def load_scenario(path):
    scenario = yaml.safe_load(Path(path).read_text())
    required = {
        "schema_version",
        "seed",
        "start",
        "cadence_seconds",
        "event_minutes",
        "steps",
        "buffer_limit",
        "stations",
        "events",
    }
    if not isinstance(scenario, dict) or set(scenario) != required or scenario["schema_version"] != 1:
        raise ValueError("Scenario must use the complete version-one schema")
    if not 0.05 <= scenario["cadence_seconds"] <= 60 or not 1 <= scenario["buffer_limit"] <= 10000:
        raise ValueError("Invalid cadence or buffer bound")
    if not 0 < scenario["event_minutes"] <= 60 or not 1 <= scenario["steps"] <= 100000:
        raise ValueError("Invalid event step or duration")
    if not set(scenario["stations"]).issubset({s["id"] for s in STATIONS}):
        raise ValueError("Unknown station")
    start = datetime.fromisoformat(scenario["start"])
    if start.tzinfo is None:
        raise ValueError("Scenario start needs a UTC offset")
    for event in scenario["events"]:
        if event["station"] not in scenario["stations"] or event["end"] <= event["start"]:
            raise ValueError("Invalid scenario event")
    return scenario


def controls_for(scenario, station_id, step):
    control = {"fault": "normal", "severity": 0.7, "network": "normal", "cloud": 1.0}
    for event in scenario["events"]:
        if event["station"] == station_id and event["start"] <= step < event["end"]:
            control.update({k: v for k, v in event.items() if k in control})
    return control


def next_event_start(start, latest):
    base = datetime.fromisoformat(start)
    previous = datetime.fromisoformat(latest) if latest else None
    if previous and previous >= base:
        # A fresh demo keeps its morning clock but follows stored event history.
        base += timedelta(days=(previous.date() - base.date()).days + 1)
    return base.isoformat()


async def simulate(
    url="http://127.0.0.1:8000", scenario_path="scenarios/interview.yaml", run_dir=None, steps=None
):
    settings = load_settings()
    scenario = load_scenario(scenario_path)
    run_dir = Path(run_dir) if run_dir else settings["state"] / "runs" / uuid.uuid4().hex[:12]
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "spool.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["scenario"] != scenario:
            raise ValueError("Resume uses the original scenario file")
    else:
        state = {
            "run_id": uuid.uuid4().hex[:12],
            "step": 0,
            "scenario": scenario,
            "dropped": 0,
            "devices": {
                s: {"boot": uuid.uuid4().hex, "pending": [], "relay_on": True, "last": None}
                for s in scenario["stations"]
            },
        }
        atomic_json(state_path, state)
    atomic_json(run_dir / "config.json", scenario)
    print(
        f"SIMULATED DATA: {len(state['devices'])} devices, run {state['run_id']}, buffer {scenario['buffer_limit']} per station",
        flush=True,
    )
    retries = {s: {"failures": 0, "next": 0} for s in state["devices"]}
    total_steps = steps if steps is not None else scenario["steps"]
    async with httpx.AsyncClient(base_url=url.rstrip("/"), timeout=3, trust_env=False) as client:
        for step in range(state["step"], total_steps):
            started = time.monotonic()
            for station_id, device in state["devices"].items():
                station = next(s for s in STATIONS if s["id"] == station_id)
                headers = {"Authorization": "Bearer " + settings["credentials"]["devices"][station_id]}
                control = controls_for(scenario, station_id, step)
                try:
                    response = await client.get("/api/v1/device/control", headers=headers)
                    response.raise_for_status()
                    remote = response.json()
                    if remote.get("source_mode") == "hardware":
                        continue
                    if "event_start" not in device and device["last"] is None:
                        device["event_start"] = next_event_start(
                            scenario["start"], remote.get("latest_observed")
                        )
                        atomic_json(state_path, state)
                    if remote["scenario"].get("enabled"):
                        control.update(remote["scenario"])
                    for command in remote["commands"]:
                        if command["expires_at"] <= time.time():
                            continue
                        device["relay_on"] = command["desired"]
                        atomic_json(state_path, state)
                        await client.post(
                            f"/api/v1/device/commands/{command['id']}/ack",
                            json={"relay_on": device["relay_on"]},
                            headers=headers,
                        )
                except httpx.HTTPError:
                    pass
                device.setdefault("event_start", scenario["start"])
                rng = np.random.default_rng(scenario["seed"] + step * 997 + STATIONS.index(station) * 100003)
                row, truth = reading(
                    step,
                    station,
                    rng,
                    control["fault"],
                    control["severity"],
                    datetime.fromisoformat(device["event_start"]),
                    scenario["event_minutes"],
                    control["cloud"],
                )
                if control.get("manual") is not None:
                    row.update(control["manual"])
                    truth = "manual_unlabelled"
                if control["fault"] == "sensor_stuck" and device["last"]:
                    for key in ["voltage_v", "current_a"]:
                        row[key] = device["last"][key]
                if control["fault"] == "missing":
                    row.update(current_a=None, missing_reason="Injected missing current sensor")
                if not device["relay_on"]:
                    row.update(current_a=0.0, ac_power_w=0.0)
                row.update(
                    boot_id=device["boot"], scenario_run_id=state["run_id"], relay_on=device["relay_on"]
                )
                if device["last"] and device["last"]["sequence"] == step:
                    row = dict(device["last"])
                    truth = device.get("last_truth", truth)
                device["last_truth"] = truth
                device["last"] = row
                if not any(
                    p["boot_id"] == row["boot_id"] and p["sequence"] == row["sequence"]
                    for p in device["pending"]
                ):
                    device["pending"].append(row)
                if len(device["pending"]) > scenario["buffer_limit"]:
                    device["pending"].pop(0)
                    state["dropped"] += 1
                with (run_dir / "readings.jsonl").open("a") as f:
                    f.write(json.dumps(row) + "\n")
                with (run_dir / "truth.jsonl").open("a") as f:
                    f.write(
                        json.dumps(
                            {
                                "boot_id": device["boot"],
                                "sequence": step,
                                "station_id": station_id,
                                "observed_at": row["observed_at"],
                                "fault": truth,
                                "severity": control["severity"],
                            }
                        )
                        + "\n"
                    )
                atomic_json(state_path, state)
                retry = retries[station_id]
                if control["network"] == "disconnect" or time.monotonic() < retry["next"]:
                    continue
                if control["network"] == "delay" and len(device["pending"]) < 10:
                    continue
                pending = device["pending"][:50]
                # Delayed batches intentionally arrive out of event-time order.
                batch = list(reversed(pending)) if control["network"] == "delay" else pending
                try:
                    response = await client.post(
                        "/api/v1/telemetry", json={"readings": batch}, headers=headers
                    )
                    response.raise_for_status()
                    if control["network"] == "duplicate":
                        duplicate = await client.post(
                            "/api/v1/telemetry", json={"readings": batch}, headers=headers
                        )
                        duplicate.raise_for_status()
                    del device["pending"][: len(pending)]
                    retry.update(failures=0, next=0)
                except httpx.HTTPError as exc:
                    retry["failures"] += 1
                    retry["next"] = time.monotonic() + min(30, 2 ** min(5, retry["failures"]))
                    print(
                        f"{station_id}: buffered={len(device['pending'])}, retry={type(exc).__name__}",
                        flush=True,
                    )
                atomic_json(state_path, state)
            state["step"] = step + 1
            atomic_json(state_path, state)
            if step % 30 == 0:
                print(
                    f"step={step}, buffered={sum(len(d['pending']) for d in state['devices'].values())}, dropped={state['dropped']}",
                    flush=True,
                )
            await asyncio.sleep(max(0, scenario["cadence_seconds"] - (time.monotonic() - started)))
    print(
        f"Run saved at {run_dir}. Reuse --run-dir to resume; replay readings.jsonl to flush or deduplicate.",
        flush=True,
    )
    return str(run_dir)


def replay(path, url="http://127.0.0.1:8000"):
    settings = load_settings()
    counts = {"accepted": 0, "duplicates": 0}
    pending = {}
    with httpx.Client(base_url=url.rstrip("/"), timeout=10, trust_env=False) as client:

        def send(station, batch):
            headers = {"Authorization": "Bearer " + settings["credentials"]["devices"][station]}
            for attempt in range(6):
                try:
                    response = client.post("/api/v1/telemetry", json={"readings": batch}, headers=headers)
                    if response.status_code not in {429, 503}:
                        response.raise_for_status()
                        for key in counts:
                            counts[key] += response.json()[key]
                        return
                except httpx.TransportError:
                    pass
                time.sleep(min(10, 2**attempt))
            raise RuntimeError("Replay could not reach the API; safely retry the same input file")

        with Path(path).open() as f:
            for line in f:
                row = json.loads(line)
                station = row["station_id"]
                batch = pending.setdefault(station, [])
                batch.append(row)
                if len(batch) == 50:
                    send(station, batch)
                    pending[station] = []
        for station, batch in pending.items():
            if batch:
                send(station, batch)
    print(json.dumps(counts, indent=2))
    return counts
