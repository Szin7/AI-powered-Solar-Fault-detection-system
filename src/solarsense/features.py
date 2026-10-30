import numpy as np
import pandas as pd

FEATURES = [
    "voltage_ratio",
    "current_ratio",
    "power_ratio",
    "ac_efficiency",
    "irradiance",
    "surface_temp",
    "temp_rise",
    "load_ratio",
    "humidity",
]
EXPECTED_FEATURES = ["irradiance_wm2", "ambient_temp_c", "surface_temp_c", "rated_power_w", "load_limit_w"]
FORECAST_FEATURES = [
    "last_power",
    "lag_1",
    "lag_3",
    "mean_3",
    "irradiance_wm2",
    "ambient_temp_c",
    "rated_power_w",
    "load_limit_w",
    "hour_sin",
    "hour_cos",
]


def features(df):
    df = pd.DataFrame(df).copy()
    available = (df.rated_power_w * df.irradiance_wm2 / 1000 * (1 - 0.004 * (df.surface_temp_c - 25))).clip(
        lower=1
    )
    expected = np.minimum(available, df.load_limit_w.clip(lower=1))
    voltage = df.rated_voltage_v * (1 - 0.003 * (df.surface_temp_c - 25))
    dc = df.voltage_v * df.current_a
    values = {
        "voltage_ratio": df.voltage_v / voltage.clip(lower=1),
        "current_ratio": df.current_a / (expected / voltage.clip(lower=1)).clip(lower=0.1),
        "power_ratio": dc / expected,
        "ac_efficiency": df.ac_power_w / dc.clip(lower=1),
        "irradiance": df.irradiance_wm2 / 1000,
        "surface_temp": df.surface_temp_c / 100,
        "temp_rise": (df.surface_temp_c - df.ambient_temp_c) / 40,
        "load_ratio": df.load_limit_w / df.rated_power_w,
        "humidity": df.humidity_pct / 100,
    }
    return pd.DataFrame(values, index=df.index)[FEATURES].clip(-5, 5)


def quality(row):
    required = [
        "voltage_v",
        "current_a",
        "ac_power_w",
        "irradiance_wm2",
        "ambient_temp_c",
        "surface_temp_c",
        "humidity_pct",
    ]
    if any(row.get(k) is None for k in required):
        return "missing"
    bounds = {
        "voltage_v": (0, 100),
        "current_a": (0, 60),
        "ac_power_w": (0, 4000),
        "irradiance_wm2": (0, 1500),
        "ambient_temp_c": (-30, 65),
        "surface_temp_c": (-30, 100),
        "humidity_pct": (0, 100),
    }
    if any(not np.isfinite(row[k]) or not lo <= row[k] <= hi for k, (lo, hi) in bounds.items()):
        return "invalid"
    return "valid"


def forecast_frame(df):
    df = df.sort_values(["session", "observed_at"]).copy()
    group = df.groupby("session", sort=False)
    df["last_power"] = df.ac_power_w
    df["lag_1"] = group.ac_power_w.shift(1)
    df["lag_3"] = group.ac_power_w.shift(3)
    df["mean_3"] = group.ac_power_w.transform(lambda s: s.rolling(3).mean())
    times = pd.to_datetime(df.observed_at, utc=True)
    hour = times.dt.hour + times.dt.minute / 60
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    for horizon in [15, 30, 60]:
        df[f"target_{horizon}"] = group.ac_power_w.shift(-horizon // 5)
    return df


def rule_predict(X):
    labels = np.full(len(X), "normal", dtype=object)
    daylight = X.irradiance.to_numpy() >= 0.08
    labels[daylight & (X.power_ratio.to_numpy() < 0.82)] = "soiling"
    labels[daylight & (X.voltage_ratio.to_numpy() < 0.88) & (X.power_ratio.to_numpy() < 0.8)] = (
        "partial_shading"
    )
    labels[daylight & (X.ac_efficiency.to_numpy() < 0.6)] = "inverter_fault"
    labels[daylight & (X.current_ratio.to_numpy() < 0.04)] = "open_circuit"
    labels[daylight & (X.voltage_ratio.to_numpy() < 0.12)] = "short_circuit"
    return labels
