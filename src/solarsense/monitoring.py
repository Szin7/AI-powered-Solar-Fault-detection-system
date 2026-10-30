import numpy as np
import pandas as pd

from solarsense.features import FEATURES, features, quality


def drift_report(bundle, rows):
    valid = [row for row in rows if quality(row) == "valid"]
    report = {
        "samples": len(rows),
        "valid_samples": len(valid),
        "missing_or_invalid_fraction": 1 - len(valid) / len(rows) if rows else None,
        "regimes": {},
        "interpretation": "Distribution changes call for review; they do not measure model accuracy.",
    }
    if not valid:
        return report
    current = features(pd.DataFrame(valid))
    reference = pd.DataFrame(bundle["reference"], columns=FEATURES)
    for name, daylight in [("daylight", True), ("low_light", False)]:
        a = reference[(reference.irradiance >= 0.08) == daylight]
        b = current[(current.irradiance >= 0.08) == daylight]
        if len(a) < 20 or len(b) < 20:
            report["regimes"][name] = {
                "state": "insufficient_samples",
                "reference_n": len(a),
                "current_n": len(b),
            }
            continue
        shifts = {}
        for feature in FEATURES:
            bins = np.unique(np.quantile(a[feature], [0, 0.2, 0.4, 0.6, 0.8, 1]))
            if len(bins) < 3:
                continue
            bins[0], bins[-1] = -np.inf, np.inf
            pa = np.histogram(a[feature], bins)[0] + 0.5
            pb = np.histogram(b[feature], bins)[0] + 0.5
            pa, pb = pa / pa.sum(), pb / pb.sum()
            shifts[feature] = float(np.sum((pb - pa) * np.log(pb / pa)))
        report["regimes"][name] = {
            "state": "review" if any(v > 0.25 for v in shifts.values()) else "within_reference",
            "reference_n": len(a),
            "current_n": len(b),
            "population_stability_index": shifts,
        }
    return report
