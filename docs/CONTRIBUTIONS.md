# Components and dependencies

SolarSense combines a FastAPI backend, a React/Next.js dashboard, solar-data simulation and fault detection. The dashboard is exported as static files and served by the backend. A separate acquisition process feeds validated readings into the database and inference worker.

PV calculations use pvlib. Model training, calibration, anomaly scoring and evaluation use scikit-learn. Feature explanations use SHAP. FastAPI and Pydantic handle the API and input validation; SQLAlchemy provides database access. Third-party packages retain their respective licences.

Hardware inference uses the original six-feature Random Forest, scaler and class order, stored as a checksum-verified JSON tree export. Source hashes and a 1,000-input comparison report document model equivalence. These checks do not establish accuracy on independent field data.

The ESP-NOW gateway endpoints and relay commands follow the original device protocol. Wi-Fi credentials and local runtime files are excluded from the repository. Technician notifications use the Twilio HTTP API, with local previews and mock-provider tests. Live message delivery requires a configured account and a separate acceptance test.
