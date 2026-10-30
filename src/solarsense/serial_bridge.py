import json
import time
import uuid
from datetime import datetime, timezone

import httpx

from solarsense.config import load_settings
from solarsense.hardware import parse_serial
from solarsense.schemas import Reading
from solarsense.simulator import atomic_json


def run_serial(port, station_id, protocol, url, baud=115200):
    import serial

    settings = load_settings()
    token = settings["credentials"]["devices"][station_id]
    path = settings["state"] / ("serial-" + station_id + ".json")
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {"boot": uuid.uuid4().hex, "sequence": 0, "pending": []}
    )
    headers = {"Authorization": "Bearer " + token}
    with serial.Serial(port, baud, timeout=1) as device, httpx.Client(timeout=3, trust_env=False) as client:
        time.sleep(2)
        while True:
            if len(state["pending"]) < 500:
                device.write(b"READ\n" if protocol == "nano-json" else b"GET_DATA\n")
                line = device.readline().decode("utf-8", errors="replace").strip()
                try:
                    values = (
                        parse_serial(line, "nano" if protocol == "nano-json" else "data") if line else None
                    )
                except (ValueError, TypeError):
                    print("Malformed serial sample ignored; no synthetic fallback.", flush=True)
                    values = None
                if values:
                    record = {
                        name: None
                        for name in [
                            "voltage_v",
                            "current_a",
                            "ambient_temp_c",
                            "surface_temp_c",
                            "humidity_pct",
                            "light_adc",
                            "ac_power_w",
                            "irradiance_wm2",
                            "load_limit_w",
                        ]
                    }
                    record.update(values)
                    if values.get("light_adc") is not None:
                        record["light_adc"] = int(values["light_adc"])
                    record.update(
                        schema_version=1,
                        station_id=station_id,
                        device_id=station_id,
                        boot_id=state["boot"],
                        sequence=state["sequence"],
                        observed_at=datetime.now(timezone.utc).isoformat(),
                        source_kind="hardware",
                        clock_kind="gateway_receive",
                        simulator_version="1.0.0",
                        scenario_run_id="serial",
                        hardware_protocol="nano_json" if protocol == "nano-json" else "serial_data",
                        relay_on=False,
                        missing_reason="Serial device does not supply every channel; no values are fabricated",
                        dc_power_w=values["voltage_v"] * values["current_a"],
                    )
                    try:
                        Reading(**record)
                    except ValueError:
                        print(
                            "Serial sample outside telemetry contract; discarded without replacement.",
                            flush=True,
                        )
                        continue
                    state["pending"].append(record)
                    state["sequence"] += 1
                    atomic_json(path, state)
            if state["pending"]:
                batch = state["pending"][:50]
                try:
                    response = client.post(
                        url.rstrip("/") + "/api/v1/telemetry", json={"readings": batch}, headers=headers
                    )
                    response.raise_for_status()
                    del state["pending"][: len(batch)]
                    atomic_json(path, state)
                except httpx.HTTPError:
                    print(
                        "Hardware samples buffered; check server, station source and credentials.", flush=True
                    )
            time.sleep(1)
