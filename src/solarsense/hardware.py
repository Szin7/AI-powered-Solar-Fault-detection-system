import gzip
import hashlib
import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np

RESOLUTION = {
    "normal": "No fault action suggested. Keep monitoring the physical station.",
    "open_circuit": "Ask a qualified technician to inspect the panel connections and wiring. Confirm recovery from fresh measurements after repair.",
    "short_circuit": "Request a qualified electrical inspection of the suspected short circuit. Do not use this app as a protection device or energize the circuit based on its prediction.",
    "partial_shading": "Inspect the panel for obstruction or uneven illumination. Compare readings after the cause has been checked.",
    "soiling": "Inspect the panel for dirt and other causes of reduced output. Arrange cleaning under the panel maintenance procedure and verify the readings afterward.",
    "inactive": "Light is too low for a useful daytime fault decision. Continue monitoring.",
}

FIELDS = ["voltage_v", "current_a", "ambient_temp_c", "light_adc", "humidity_pct", "surface_temp_c"]
LABELS = {
    "Normal": "normal",
    "Open_Circuit": "open_circuit",
    "Short_Circuit": "short_circuit",
    "Partial_Shading": "partial_shading",
    "Dust_Accumulation": "soiling",
}
BOUNDS = [(-0.5, 25), (-0.01, 2), (-20, 100), (0, 4095), (0, 100), (-20, 150)]


@lru_cache(maxsize=1)
def load_hardware_model():
    path = Path(__file__).parent / "assets/hardware_forest.json.gz"
    blob = path.read_bytes()
    checksum = hashlib.sha256(blob).hexdigest()
    if checksum != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Original hardware model integrity check failed")
    model = json.loads(gzip.decompress(blob))
    model["version"] = "hw-" + checksum[:12]
    return model


def hardware_probabilities(values):
    model = load_hardware_model()
    # sklearn trees compare float32 values after the original StandardScaler.
    X = ((np.asarray(values, dtype=float) - model["mean"]) / model["scale"]).astype(np.float32)
    probabilities = np.zeros(len(model["classes"]))
    for tree in model["trees"]:
        node = 0
        while tree["left"][node] != -1:
            node = (
                tree["left"][node]
                if X[tree["feature"][node]] <= tree["threshold"][node]
                else tree["right"][node]
            )
        probabilities += tree["probabilities"][node]
    return probabilities / len(model["trees"])


def predict_hardware(row, previous):
    model = load_hardware_model()
    result = dict(
        quality_state="valid",
        model_version=model["version"],
        feature_version="original-hardware-six",
        probability_method="original_raw_forest",
        raw_class=None,
        raw_index=None,
        probabilities={},
        confidence=None,
        decision_state="data_quality",
        stabilized_class="data_quality",
        explanation=[],
        expected_power_w=None,
        actual_power_w=row.get("dc_power_w"),
        deficit_ratio=None,
        anomaly=None,
        resolution="Inspect missing or invalid hardware sensor values.",
        source_kind="hardware",
        measurement_basis="DC voltage × current; AC power and irradiance are not estimated from LDR",
        stabilization_votes=[],
    )
    values = [row.get(name) for name in FIELDS]
    if any(value is None for value in values):
        result["quality_state"] = "missing"
        return result
    if any(not np.isfinite(value) or not low <= value <= high for value, (low, high) in zip(values, BOUNDS)):
        result["quality_state"] = "invalid"
        return result
    old = previous[0].get("ema_values", values) if previous else values
    smooth = [round(0.3 * value + 0.7 * prior, 4) for value, prior in zip(values, old)]
    probs = hardware_probabilities(smooth)
    index = int(np.argmax(probs))
    label = LABELS[model["classes"][index]]
    decision = "inactive" if row["light_adc"] < 20 else label
    votes = [r["raw_class"] for r in reversed(previous[:7]) if r.get("raw_class")] + [label]
    counts = Counter(votes)
    stable = previous[0]["stabilized_class"] if previous else "normal"
    if stable not in LABELS.values():
        stable = "normal"
    if len(votes) < 3:
        stable = "warming"
    elif decision == "inactive":
        stable = "inactive"
    elif stable == "normal":
        for candidate, needed in [
            ("short_circuit", 3),
            ("open_circuit", 3),
            ("partial_shading", 5),
            ("soiling", 6),
        ]:
            if counts[candidate] >= needed:
                stable = candidate
                break
    elif counts["normal"] >= 4:
        stable = "normal"
    else:
        for candidate in ["short_circuit", "open_circuit", "partial_shading", "soiling"]:
            if candidate != stable and counts[candidate] >= 6:
                stable = candidate
                break
    result.update(
        raw_class=label,
        raw_index=index,
        confidence=float(probs[index]),
        probabilities={LABELS[name]: float(p) for name, p in zip(model["classes"], probs)},
        decision_state=decision,
        stabilized_class=stable,
        stabilization_votes=votes,
        ema_values=smooth,
        resolution=RESOLUTION.get(stable, "Collecting hardware readings for stabilization."),
    )
    return result


def parse_serial(line, protocol):
    if protocol == "data":
        if not line.startswith("DATA:"):
            return None
        values = [float(v) for v in line[5:].strip().split(",")]
        if not 4 <= len(values) <= 6:
            raise ValueError("DATA requires four to six sensor fields")
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite serial measurement")
        return dict(zip(FIELDS, values))
    value = json.loads(line)
    if not isinstance(value, dict) or not {"v", "i", "t", "l"}.issubset(value):
        return None
    for name in ["v", "i", "t", "l", "light_adc", "humidity", "thermistor_temp"]:
        if value.get(name) is not None:
            value[name] = float(value[name])
            if not math.isfinite(value[name]):
                raise ValueError("Nonfinite serial measurement")
    # The supplied Nano sends a lux-like value, not the ESP32 raw ADC.
    return {
        "voltage_v": value["v"],
        "current_a": value["i"],
        "ambient_temp_c": value["t"],
        "light_lux": value["l"],
        "light_adc": value.get("light_adc"),
        "humidity_pct": value.get("humidity"),
        "surface_temp_c": value.get("thermistor_temp"),
    }
