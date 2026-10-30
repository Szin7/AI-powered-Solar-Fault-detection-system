import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from solarsense.hardware import BOUNDS, hardware_probabilities, load_hardware_model


def main():
    parser = argparse.ArgumentParser(
        description="Compare the included export with trusted original model files"
    )
    parser.add_argument("--original", type=Path, required=True)
    args = parser.parse_args()
    forest = joblib.load(args.original / "solar_fault_rf_model.joblib")
    scaler = joblib.load(args.original / "solar_fault_scaler.joblib")
    encoder = joblib.load(args.original / "solar_fault_label_encoder.joblib")
    features = joblib.load(args.original / "solar_fault_feature_names.joblib")
    assert list(encoder.classes_) == load_hardware_model()["classes"]
    assert list(features) == load_hardware_model()["features"]
    rng = np.random.default_rng(42)
    low, high = np.asarray(BOUNDS).T
    values = rng.uniform(low, high, size=(1000, 6))
    X = pd.DataFrame(values, columns=features)
    expected = forest.predict_proba(scaler.transform(X))
    actual = np.asarray([hardware_probabilities(row) for row in values])
    np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)
    report = {
        "reference": "Original user-provided RF/scaler/encoder",
        "rows": len(values),
        "seed": 42,
        "max_probability_error": float(np.max(np.abs(actual - expected))),
        "identical_predicted_classes": bool(np.all(actual.argmax(axis=1) == expected.argmax(axis=1))),
        "physical_hardware_tested_here": False,
    }
    path = Path("reports/hardware-model-parity.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
