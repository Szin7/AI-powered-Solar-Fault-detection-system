import hashlib
import json
import os
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    IsolationForest,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
)

from solarsense.config import FEATURE_VERSION, LABELS, SEED
from solarsense.features import (
    EXPECTED_FEATURES,
    FEATURES,
    FORECAST_FEATURES,
    features,
    forecast_frame,
    quality,
    rule_predict,
)

RESOLUTION = {
    "normal": "No fault action suggested. Keep monitoring.",
    "open_circuit": "In the virtual station, restore the connection and confirm recovery. Physical wiring needs a qualified inspection.",
    "short_circuit": "Inspect the simulated short condition. This demo does not operate physical protection equipment.",
    "partial_shading": "Remove the simulated obstruction, then compare delivered and expected power.",
    "soiling": "Reset the simulated soiling and compare the recovered output. Similar losses can have other causes.",
    "inverter_fault": "Restore the simulated inverter efficiency and compare AC with DC power.",
    "unknown": "Inspect the readings and sensor quality before assigning a fault label.",
    "uncertain": "Collect more readings or record an independent review; the model has abstained.",
    "data_quality": "Check the missing, invalid, or stuck sensor before using its prediction.",
}


def scores(y, pred, probabilities=None, classes=None):
    report = {
        "accuracy": float(accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, labels=LABELS, average="macro", zero_division=0)),
        "confusion_matrix": confusion_matrix(y, pred, labels=LABELS).tolist(),
        "per_class": classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0),
    }
    if probabilities is not None:
        report["log_loss"] = float(log_loss(y, probabilities, labels=classes))
    return report


def stabilize(recent, current):
    votes = (recent + [current])[-5:]
    if current == "data_quality":
        return "data_quality", votes
    eligible = [v for v in votes if v not in {"unknown", "uncertain", "data_quality"}]
    if len(votes) < 3:
        return "warming", votes
    for label in LABELS + ["inactive"]:
        if eligible.count(label) >= 3:
            return label, votes
    return current if current in {"unknown", "uncertain"} else "uncertain", votes


def choose_thresholds(model, X, y):
    probs = model.predict_proba(X)
    indices = probs.argmax(axis=1)
    truth = np.asarray(y)
    thresholds = {}
    for i, label in enumerate(model.classes_):
        threshold = 0.9
        for t in np.arange(0.5, 0.96, 0.05):
            accepted = (indices == i) & (probs[:, i] >= t)
            if accepted.sum() >= 5 and np.mean(truth[accepted] == label) >= 0.95:
                threshold = float(round(t, 2))
                break
        thresholds[str(label)] = threshold
    return thresholds


def decision_labels(bundle, X, probabilities=None):
    probs = bundle["probability_model"].predict_proba(X) if probabilities is None else probabilities
    labels = bundle["probability_model"].classes_[probs.argmax(axis=1)]
    unusual = bundle["anomaly"].score_samples(X) < bundle["anomaly_cutoff"]
    decisions = []
    for i, (label, probability) in enumerate(zip(labels, probs)):
        support = bundle.get("class_support", {}).get(str(label))
        outside = bool(
            support
            and any(
                value < lo or value > hi
                for value, lo, hi in zip(X.iloc[i, :4], support["low"], support["high"])
            )
        )
        if unusual[i] and outside:
            decisions.append("unknown")
        elif probability.max() < bundle["thresholds"][str(label)]:
            decisions.append("unknown" if unusual[i] else "uncertain")
        else:
            decisions.append(str(label))
    return decisions, unusual


def train(data_dir="data/generated", models_dir="models", reports_dir="reports", trees=120, track=False):
    data_dir, models_dir, reports_dir = map(Path, (data_dir, models_dir, reports_dir))
    df = pd.read_csv(data_dir / "solar.csv")
    data_manifest = json.loads((data_dir / "manifest.json").read_text())
    if hashlib.sha256((data_dir / "solar.csv").read_bytes()).hexdigest() != data_manifest["sha256"]:
        raise ValueError("Dataset hash differs from its manifest")
    parts = {split: df[df.split == split] for split in ["train", "calibration", "validation", "test"]}
    for split, part in parts.items():
        if set(part.fault) != set(LABELS):
            raise ValueError(f"{split} must contain all six classes")
    sets = [set(part.session) for part in parts.values()]
    if any(sets[i] & sets[j] for i in range(4) for j in range(i)):
        raise ValueError("Sessions overlap across splits")
    X = {split: features(part) for split, part in parts.items()}
    rf = RandomForestClassifier(
        n_estimators=trees, min_samples_leaf=2, class_weight="balanced", random_state=SEED, n_jobs=1
    )
    rf.fit(X["train"], parts["train"].fault)
    boosting = HistGradientBoostingClassifier(max_iter=80, max_leaf_nodes=15, random_state=SEED)
    boosting.fit(X["train"], parts["train"].fault)
    calibrated = CalibratedClassifierCV(FrozenEstimator(rf), method="sigmoid")
    calibrated.fit(X["calibration"], parts["calibration"].fault)
    raw_validation_loss = log_loss(
        parts["validation"].fault, rf.predict_proba(X["validation"]), labels=rf.classes_
    )
    calibrated_validation_loss = log_loss(
        parts["validation"].fault, calibrated.predict_proba(X["validation"]), labels=calibrated.classes_
    )
    probability_model = calibrated if calibrated_validation_loss < raw_validation_loss else rf
    probability_method = "sigmoid_calibration" if probability_model is calibrated else "raw_forest"
    thresholds = choose_thresholds(probability_model, X["validation"], parts["validation"].fault)
    healthy = parts["train"].fault == "normal"
    anomaly = IsolationForest(n_estimators=80, contamination=0.02, random_state=SEED, n_jobs=1)
    anomaly.fit(X["train"].loc[healthy])
    validation_healthy = parts["validation"].fault == "normal"
    anomaly_cutoff = float(np.quantile(anomaly.score_samples(X["validation"].loc[validation_healthy]), 0.01))
    power = RandomForestRegressor(n_estimators=trees, min_samples_leaf=4, random_state=SEED, n_jobs=1)
    power.fit(parts["train"].loc[healthy, EXPECTED_FEATURES], parts["train"].loc[healthy, "ac_power_w"])
    forecast_data = forecast_frame(df)
    forecasters, forecast_metrics, policies = {}, {}, {}
    for horizon in [15, 30, 60]:
        target = f"target_{horizon}"
        subset = forecast_data.dropna(subset=FORECAST_FEATURES + [target])
        a, v, t = [subset[subset.split == split] for split in ["train", "validation", "test"]]
        reg = RandomForestRegressor(
            n_estimators=60, max_depth=12, min_samples_leaf=5, random_state=SEED, n_jobs=1
        )
        reg.fit(a[FORECAST_FEATURES], a[target])
        val_model = mean_absolute_error(v[target], reg.predict(v[FORECAST_FEATURES]))
        val_persistence = mean_absolute_error(v[target], v.last_power)
        policy = "forest" if val_model < val_persistence else "persistence"
        forecasters[horizon], policies[horizon] = reg, policy
        pred = reg.predict(t[FORECAST_FEATURES])
        metrics = {}
        for regime, mask in {
            "all": np.ones(len(t), dtype=bool),
            "daylight": t.irradiance_wm2 >= 80,
            "low_light": t.irradiance_wm2 < 80,
        }.items():
            if np.sum(mask):
                metrics[regime] = {
                    "samples": int(np.sum(mask)),
                    "forest_mae_w": float(mean_absolute_error(t.loc[mask, target], pred[mask])),
                    "forest_rmse_w": float(np.sqrt(mean_squared_error(t.loc[mask, target], pred[mask]))),
                    "persistence_mae_w": float(
                        mean_absolute_error(t.loc[mask, target], t.loc[mask, "last_power"])
                    ),
                    "persistence_rmse_w": float(
                        np.sqrt(mean_squared_error(t.loc[mask, target], t.loc[mask, "last_power"]))
                    ),
                }
        forecast_metrics[str(horizon)] = {
            "selected_on_validation": policy,
            "validation_forest_mae": float(val_model),
            "validation_persistence_mae": float(val_persistence),
            "test": metrics,
        }
    source_hash = hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))
    ).hexdigest()
    version = hashlib.sha256(f"{data_manifest['sha256']}:{trees}:{source_hash}".encode()).hexdigest()[:12]
    bundle = {
        "version": version,
        "feature_version": FEATURE_VERSION,
        "features": FEATURES,
        "labels": LABELS,
        "classifier": rf,
        "probability_model": probability_model,
        "calibration_candidate": calibrated,
        "probability_method": probability_method,
        "thresholds": thresholds,
        "anomaly": anomaly,
        "anomaly_cutoff": anomaly_cutoff,
        "expected": power,
        "forecasters": forecasters,
        "forecast_policy": policies,
        "reference": X["train"].loc[healthy].to_numpy()[::7].tolist(),
    }
    support = {}
    for label in LABELS:
        values = X["train"].loc[parts["train"].fault == label].iloc[:, :4]
        low, high = values.quantile(0.005).to_numpy(), values.quantile(0.995).to_numpy()
        margin = 0.2 * (high - low) + 0.03
        support[label] = {"low": (low - margin).tolist(), "high": (high + margin).tolist()}
    bundle["class_support"] = support
    y = parts["test"].fault
    probs = probability_model.predict_proba(X["test"])
    pred = probability_model.classes_[probs.argmax(axis=1)]
    decisions, _ = decision_labels(bundle, X["test"], probs)
    accepted = np.array([label in LABELS for label in decisions])
    comparison = {
        name: {split: scores(parts[split].fault, predict(X[split])) for split in ["validation", "test"]}
        for name, predict in {
            "rules": rule_predict,
            "random_forest": rf.predict,
            "boosting": boosting.predict,
        }.items()
    }
    reliability = []
    confidence = probs.max(axis=1)
    for low in np.arange(0, 1, 0.1):
        mask = (confidence >= low) & (confidence < low + 0.100001)
        if mask.any():
            reliability.append(
                {
                    "low": round(float(low), 1),
                    "n": int(mask.sum()),
                    "confidence": float(confidence[mask].mean()),
                    "accuracy": float(np.mean(pred[mask] == y.to_numpy()[mask])),
                }
            )
    rng = np.random.default_rng(SEED)
    session_scores = []
    session_groups = {}
    for session, group in parts["test"].groupby("session"):
        faults = sorted(set(group.fault) - {"normal"})
        session_groups.setdefault(faults[0] if faults else "normal", []).append(session)
    for _ in range(200):
        # Whole-session resampling keeps each fault represented in the interval.
        selected = np.concatenate(
            [rng.choice(group, len(group), replace=True) for group in session_groups.values()]
        )
        indices = np.concatenate([np.flatnonzero(parts["test"].session.to_numpy() == s) for s in selected])
        session_scores.append(
            f1_score(y.iloc[indices], pred[indices], labels=LABELS, average="macro", zero_division=0)
        )
    healthy_test = parts["test"].fault == "normal"
    report = {
        "model_version": version,
        "synthetic": True,
        "seed": SEED,
        "dataset": data_manifest,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "classification": scores(y, pred, probs, probability_model.classes_),
        "baselines": comparison,
        "selection": "Random forest is served for direct TreeSHAP explanations; boosting remains a measured comparison.",
        "macro_f1_session_bootstrap_95": np.quantile(session_scores, [0.025, 0.975]).tolist(),
        "coverage": float(accepted.mean()),
        "calibration": {
            "selected_on_validation": probability_method,
            "raw_validation_log_loss": float(raw_validation_loss),
            "sigmoid_validation_log_loss": float(calibrated_validation_loss),
            "raw_test_log_loss": float(log_loss(y, rf.predict_proba(X["test"]), labels=rf.classes_)),
            "sigmoid_test_log_loss": float(
                log_loss(y, calibrated.predict_proba(X["test"]), labels=calibrated.classes_)
            ),
        },
        "uncalibrated_log_loss": float(log_loss(y, rf.predict_proba(X["test"]), labels=rf.classes_)),
        "accepted_accuracy": float(np.mean(pred[accepted] == y.to_numpy()[accepted]))
        if accepted.any()
        else None,
        "thresholds": thresholds,
        "reliability": reliability,
        "forecast": forecast_metrics,
        "expected_healthy_mae_w": float(
            mean_absolute_error(
                parts["test"].loc[healthy_test, "ac_power_w"],
                power.predict(parts["test"].loc[healthy_test, EXPECTED_FEATURES]),
            )
        ),
        "by_station": {
            str(station): scores(y.loc[mask], pred[mask.to_numpy()])
            for station in parts["test"].station_id.unique()
            for mask in [parts["test"].station_id == station]
        },
    }
    report["promotion_gate"] = {
        "passed": report["classification"]["macro_f1"] >= 0.65 and report["coverage"] >= 0.5,
        "minimum_macro_f1": 0.65,
        "minimum_coverage": 0.5,
    }
    dest = models_dir / version
    if dest.exists():
        raise FileExistsError(
            f"Immutable release already exists: {dest}. Use it or a separate output directory."
        )
    dest.mkdir(parents=True)
    joblib.dump(bundle, dest / "model.joblib", compress=3)
    manifest = {
        "version": version,
        "features": FEATURES,
        "feature_version": FEATURE_VERSION,
        "labels": LABELS,
        "sha256": hashlib.sha256((dest / "model.joblib").read_bytes()).hexdigest(),
        "dataset_sha256": data_manifest["sha256"],
        "source_sha256": source_hash,
        "promotion_gate": report["promotion_gate"],
        "python": platform.python_version(),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (dest / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    pd.DataFrame(
        {
            "session": parts["test"].session,
            "observed_at": parts["test"].observed_at,
            "truth": y,
            "prediction": pred,
            "confidence": confidence,
            "accepted": accepted,
        }
    ).to_csv(reports_dir / "test_predictions.csv", index=False)
    plot_report(report, reports_dir)
    if track:
        import mlflow

        mlflow.set_tracking_uri(
            os.getenv("MLFLOW_TRACKING_URI", "sqlite:///" + str((reports_dir / "mlflow.db").resolve()))
        )
        mlflow.set_experiment("SolarSense")
        with mlflow.start_run(run_name=version):
            mlflow.log_params(
                {
                    "seed": SEED,
                    "trees": trees,
                    "dataset_sha256": data_manifest["sha256"],
                    "source_sha256": source_hash,
                }
            )
            mlflow.log_metrics(
                {
                    "accuracy": report["classification"]["accuracy"],
                    "macro_f1": report["classification"]["macro_f1"],
                    "coverage": report["coverage"],
                }
            )
            mlflow.log_artifacts(str(dest))
    print(
        f"Trained {version}: accuracy={report['classification']['accuracy']:.4f}, macro F1={report['classification']['macro_f1']:.4f}"
    )
    return version, report


def plot_report(report, dest):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    matrix = report["classification"]["confusion_matrix"]
    axes[0].imshow(matrix, cmap="Blues")
    axes[0].set(
        xticks=range(6),
        yticks=range(6),
        xticklabels=LABELS,
        yticklabels=LABELS,
        xlabel="Predicted",
        ylabel="Actual",
        title="Held-out synthetic sessions",
    )
    plt.setp(axes[0].get_xticklabels(), rotation=45, ha="right")
    for i in range(6):
        for j in range(6):
            axes[0].text(j, i, str(matrix[i][j]), ha="center", va="center", color="black")
    bins = report["reliability"]
    axes[1].plot([b["confidence"] for b in bins], [b["accuracy"] for b in bins], "o-")
    axes[1].plot([0, 1], [0, 1], "--", color="gray")
    axes[1].set(
        xlabel="Mean model confidence",
        ylabel="Observed accuracy",
        title="Reliability",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    fig.savefig(Path(dest) / "evaluation.png", dpi=160)
    plt.close(fig)


def load_release(models_dir, version=None):
    models_dir = Path(models_dir)
    if version is None:
        version = json.loads((models_dir / "active.json").read_text())["active"]
    if not version or any(c not in "0123456789abcdef" for c in version) or len(version) != 12:
        raise ValueError("Invalid model version")
    directory = models_dir / version
    manifest = json.loads((directory / "manifest.json").read_text())
    path = directory / "model.joblib"
    if (
        manifest["features"] != FEATURES
        or manifest["feature_version"] != FEATURE_VERSION
        or manifest["labels"] != LABELS
    ):
        raise ValueError("Incompatible feature contract")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Model integrity check failed")
    bundle = joblib.load(path)
    if "probability_model" not in bundle:
        raise ValueError("Artifact predates the validated probability-selection contract")
    if bundle["version"] != version or list(bundle["probability_model"].classes_) != sorted(LABELS):
        raise ValueError("Model label map or version mismatch")
    bundle["explainer"] = shap.TreeExplainer(bundle["classifier"])
    return bundle


def promote(models_dir, version, rollback=False):
    models_dir = Path(models_dir)
    pointer = models_dir / "active.json"
    previous = json.loads(pointer.read_text()) if pointer.exists() else {}
    if rollback:
        version = previous.get("previous")
    bundle = load_release(models_dir, version)
    manifest = json.loads((models_dir / version / "manifest.json").read_text())
    if not manifest["promotion_gate"]["passed"]:
        raise ValueError("Candidate failed the frozen benchmark promotion gate")
    shadow_path = models_dir / version / "shadow.json"
    if not shadow_path.exists() or not json.loads(shadow_path.read_text())["passed"]:
        raise ValueError("Run shadow evaluation before promotion")
    if previous.get("active") == version:
        return bundle["version"]
    temp = models_dir / "active.tmp"
    temp.write_text(json.dumps({"active": version, "previous": previous.get("active")}, indent=2) + "\n")
    temp.replace(pointer)
    return bundle["version"]


def shadow(models_dir, version, data_path):
    candidate = load_release(models_dir, version)
    df = pd.read_csv(data_path)
    df = df[df.split == "validation"]
    a = candidate["probability_model"].predict_proba(features(df))
    b = candidate["probability_model"].predict_proba(features(df))
    result = {
        "passed": bool(np.isfinite(a).all() and np.allclose(a, b, atol=0) and np.allclose(a.sum(axis=1), 1)),
        "rows": len(df),
        "deterministic": bool(np.array_equal(a, b)),
        "candidate": version,
    }
    active_path = Path(models_dir) / "active.json"
    if active_path.exists():
        active = load_release(models_dir)
        pred = active["probability_model"].predict(features(df))
        result["disagreement_with_active"] = float(
            np.mean(candidate["probability_model"].classes_[a.argmax(axis=1)] != pred)
        )
        result["active"] = active["version"]
    (Path(models_dir) / version / "shadow.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def predict(bundle, row, recent=None, explain=True):
    state = quality(row)
    result = {
        "quality_state": state,
        "model_version": bundle["version"],
        "feature_version": FEATURE_VERSION,
        "probability_method": bundle["probability_method"],
        "raw_class": None,
        "raw_index": None,
        "probabilities": {},
        "confidence": None,
        "decision_state": "data_quality",
        "explanation": [],
        "expected_power_w": None,
        "actual_power_w": row.get("ac_power_w"),
        "deficit_ratio": None,
        "anomaly": None,
    }
    if state == "valid":
        X = features(pd.DataFrame([row]))
        probs = bundle["probability_model"].predict_proba(X)[0]
        index = int(probs.argmax())
        label = str(bundle["probability_model"].classes_[index])
        decisions, anomalies = decision_labels(bundle, X, probs.reshape(1, -1))
        unusual = bool(anomalies[0])
        decision = decisions[0]
        if row["irradiance_wm2"] < 80 or not row["relay_on"]:
            decision = "inactive"
        expected = (
            float(bundle["expected"].predict(pd.DataFrame([row])[EXPECTED_FEATURES])[0])
            if row["relay_on"]
            else 0.0
        )
        result.update(
            raw_class=label,
            raw_index=LABELS.index(label),
            confidence=float(probs[index]),
            probabilities={str(c): float(p) for c, p in zip(bundle["probability_model"].classes_, probs)},
            decision_state=decision,
            anomaly=unusual,
            expected_power_w=expected,
            deficit_ratio=max(0.0, 1 - row["ac_power_w"] / expected) if expected >= 10 else None,
        )
        if explain and decision not in {"normal", "inactive"}:
            raw_index = list(bundle["classifier"].classes_).index(label)
            values = bundle["explainer"].shap_values(X, check_additivity=False)[0, :, raw_index]
            top = np.argsort(np.abs(values))[-3:][::-1]
            result["explanation"] = [
                {"feature": FEATURES[i], "value": float(X.iloc[0, i]), "contribution": float(values[i])}
                for i in top
            ]
            result["explanation_target"] = (
                f"Uncalibrated forest probability for {label}; not the stabilized decision"
            )
    stabilized, votes = stabilize(recent or [], result["decision_state"])
    result.update(
        stabilized_class=stabilized,
        stabilization_votes=votes,
        resolution=RESOLUTION.get(stabilized, "Waiting for three agreeing readings in the last five."),
    )
    return result


def live_forecast(bundle, history):
    valid = [r for r in history if quality(r) == "valid"]
    if len(valid) < 4:
        return {"state": "warming", "reason": "Need four distinct five-minute event-time samples"}
    df = pd.DataFrame(valid)
    df["observed_at"] = pd.to_datetime(df.observed_at, utc=True)
    df = df.sort_values("observed_at").set_index("observed_at").resample("5min").last()
    if len(df) < 4 or df.tail(4).ac_power_w.isna().any():
        return {"state": "warming", "reason": "Need four consecutive five-minute bins"}
    df = df.reset_index()
    df["session"] = "live"
    last = forecast_frame(df).iloc[[-1]]
    forecasts = {}
    for horizon in [15, 30, 60]:
        policy = bundle["forecast_policy"][horizon]
        value = (
            float(bundle["forecasters"][horizon].predict(last[FORECAST_FEATURES])[0])
            if policy == "forest"
            else float(last.last_power.iloc[0])
        )
        forecasts[str(horizon)] = {"power_w": max(0, value), "method": policy}
    return {
        "state": "available",
        "origin": max(r["observed_at"] for r in valid),
        "horizons_minutes": forecasts,
    }
