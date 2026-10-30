import os
import threading
import time

import httpx

_cache = {}
_lock = threading.Lock()


def weather_snapshot(client=None):
    try:
        lat = float(os.getenv("WEATHER_LAT", "27.7172"))
        lon = float(os.getenv("WEATHER_LON", "85.3240"))
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Invalid weather coordinates")
    except ValueError:
        return {
            "available": False,
            "stale": True,
            "error": "Set valid WEATHER_LAT and WEATHER_LON coordinates",
        }
    key = (lat, lon)
    with _lock:
        now = time.time()
        cached = _cache.get(key)
        if cached and now < cached["retry_at"]:
            return cached["value"]
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "timezone": "Asia/Kathmandu",
                "current": "temperature_2m,relative_humidity_2m,weather_code,cloud_cover,precipitation,is_day",
                "daily": "sunrise,sunset",
                "forecast_days": 1,
            }
            if client is None:
                with httpx.Client(timeout=5, trust_env=False) as session:
                    response = session.get("https://api.open-meteo.com/v1/forecast", params=params)
            else:
                response = client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            raw = response.json()
            value = {
                "available": True,
                "stale": False,
                "source": "Open-Meteo",
                "location": os.getenv("WEATHER_LOCATION", "Kathmandu"),
                "current": raw["current"],
                "daily": raw.get("daily", {}),
                "fetched_at": now,
                "note": "Local weather context, not a panel sensor measurement or proof of a fault.",
            }
            _cache[key] = {"value": value, "retry_at": now + 600}
        except (httpx.HTTPError, ValueError, KeyError):
            value = (
                {**cached["value"], "stale": True}
                if cached
                else {"available": False, "stale": True, "source": "Open-Meteo"}
            )
            value["error"] = "Weather unavailable; sensor processing continues."
            _cache[key] = {"value": value, "retry_at": now + 60}
        return value
