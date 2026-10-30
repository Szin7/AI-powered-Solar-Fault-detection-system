# Components and dependencies

SolarSense brings together sensor acquisition, model inference, incident handling and a browser dashboard. We keep the acquisition process independent of the interface so that monitoring continues when a browser disconnects. The backend stores readings, predictions and incident history; the dashboard presents that state and exposes authorized controls.

## Main components

| Component | Role |
| --- | --- |
| FastAPI and Pydantic | HTTP/WebSocket interfaces, authentication boundaries and payload validation |
| SQLAlchemy | Persistent telemetry, commands, reviews and notification records |
| React and Next.js | Dashboard components and static frontend export |
| Recharts and Framer Motion | Sensor charts and interface transitions |
| pvlib | PVWatts DC calculation used by the synthetic-data generator |
| scikit-learn | Classifier comparison, calibration, novelty detection and power models |
| SHAP | Feature contributions for the simulation classifier |
| pyserial | Acquisition from supported serial devices |
| Twilio HTTP API | Optional SMS and WhatsApp delivery |

Python versions are pinned in `requirements.txt`; frontend dependencies are recorded in `frontend/package-lock.json`. Optional browser testing and experiment tracking have separate requirement files.

## Hardware model and protocol

The hardware path retains the original six-feature Random Forest, scaler and class order. A JSON tree export provides inference without loading the older pickle files. Source hashes and a 1,000-input comparison record the export's equivalence to the original model. That comparison is separate from diagnostic accuracy on field data.

The ESP-NOW gateway endpoints and relay command strings follow the existing device protocol. Network credentials, device-specific configuration and local runtime files stay outside the repository. The [hardware guide](HARDWARE.md) describes compatibility and missing-channel behaviour.

## Licensing

Repository code is provided under the [MIT License](../LICENSE). Third-party packages and bundled assets retain their own licences, including the bundled font licence. Dependency use and model provenance do not change those terms.
