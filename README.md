# SolarSense

Solar fault monitoring, diagnosis and incident tracking, with an ESP-NOW hardware interface and a reproducible simulation mode.

[![Checks](https://github.com/Szin7/AI-powered-Solar-Fault-detection-system/actions/workflows/ci.yml/badge.svg)](https://github.com/Szin7/AI-powered-Solar-Fault-detection-system/actions/workflows/ci.yml)

A drop in solar output does not always indicate an electrical fault. Shading, dust, changing irradiance, load and faulty sensors can produce similar symptoms. We built SolarSense to bring these measurements together, identify supported fault patterns and keep a record of what happened and how it was handled.

The system follows a reading from acquisition to prediction, incident review and technician notification. The dashboard shows the measurements behind each decision, while the backend continues collecting and processing data independently of the browser. Simulation mode makes the same workflow available without connected panels.

**The published accuracy and forecast results use synthetic data.** Hardware inference uses a separate five-class model and the existing ESP-NOW gateway protocol. Its software equivalence is tested; the synthetic benchmark does not represent field accuracy.

## What the system does

| Area | Implementation |
| --- | --- |
| Monitoring | Three stations with voltage, current, temperature, humidity and light readings; additional irradiance and AC measurements in simulation mode |
| Fault detection | Normal operation, open circuit, short circuit, partial shading and soiling; inverter faults in simulation mode |
| Decision support | Prediction scores, temporal voting, data-quality checks, anomaly scores and TreeSHAP explanations for the simulation model |
| Power analysis | Expected healthy AC output and 15-, 30- and 60-minute forecasts for simulated stations |
| Incident handling | Fault and recovery events, acknowledgement, recommended actions and independent review labels |
| Technician alerts | Per-station SMS or WhatsApp contacts, local previews and a persistent delivery queue |
| Recovery | Duplicate handling, late-reading history, bounded acquisition buffers and recovery of accepted work after a backend restart |

The React dashboard includes circular sensor gauges, expandable charts, station selection, freeze controls and CSV export. Station 1 is East roof, Station 2 is West roof, and Station 3 is Lab panel. Freezing a view or closing the browser does not stop acquisition.

## Run locally

Use **Python 3.12**. The standard demo does not require hardware, a GPU, Docker, Node.js or a paid messaging account. Package installation needs internet access; simulation and inference can then run offline. Weather and live messaging are optional online features.

### WSL on D:

From a WSL terminal with `uv` or Python 3.12 available:

```bash
mkdir -p /mnt/d/Projects
cd /mnt/d/Projects
git clone https://github.com/Szin7/AI-powered-Solar-Fault-detection-system.git SolarSense-Portfolio
cd SolarSense-Portfolio
bash tools/run_wsl.sh
```

The launcher creates the environment, installs dependencies, runs tests, prepares the models and starts the demo. It keeps project state on D: and uses notification preview mode. Startup can take longer on a mounted Windows drive. Errors are saved under `var/launch-*.log`.

### Manual installation

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
python -m solarsense setup
python -m pytest -q
python -m solarsense demo
```

For native Windows PowerShell, create the environment with `py -3.12 -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1`. If activation is blocked, use `.venv\Scripts\python.exe` in place of `python`.

Open **http://localhost:8000**, enter the operator key printed in the terminal and select **Connect**. To display the keys again from an activated environment:

```bash
python -m solarsense credentials
```

The viewer key provides read-only access. Keys are stored locally and excluded from Git. Ctrl+C stops the server and simulator started by `demo`.

The default scenario lasts about eight minutes. After it finishes, the last readings remain visible and eventually become stale. Start/Stop Monitoring controls the browser subscription; it does not start or stop the independent simulator. See the [demo guide](docs/DEMO.md) for longer sessions and replay.

## Try the fault workflow

Select a simulated station and apply a partial-shading or open-circuit preset. The simulator changes the measurements; the model still makes its own prediction. Once the decision stabilizes, inspect the incident, supporting readings and recommended action. Restore normal conditions to observe recovery.

To test notifications, save a contact under **Technician alerts**, enable automatic alerts and select **Include simulated incidents**. In the default preview mode, incident transitions create local message records without contacting anyone. Real SMS or WhatsApp delivery requires explicit provider configuration.

For a compressed day and a forecast demonstration:

```bash
python -m solarsense demo --scenario scenarios/day.yaml
```

This scenario advances event time by five minutes every 0.2 seconds. The default scenario advances two event seconds every two wall-clock seconds and ends before the roughly 15-minute forecast warmup completes. Forecast horizons and incident replay delays refer to event time; heartbeats use wall time.

## System design

Acquisition, inference and display have separate responsibilities. The gateway, serial bridge or simulator submits readings to the API. Validated readings are committed before acknowledgement. A worker processes pending rows, stores predictions and incident transitions, and queues notifications. The browser reads this stored state through the API and WebSocket updates.

We use SQLite for local runs and PostgreSQL in Docker Compose. A reading's station, boot ID and sequence identify retries, so replaying a batch does not create duplicate measurements. Late readings remain available in history without replacing newer live values. The backend runs with one inference worker.

The simulation model compares rules, Random Forest and gradient boosting on whole-session splits. Probability calibration and forecast selection use separate validation data. Three agreeing decisions in the last five readings stabilize the incident state. Missing inputs produce a data-quality result rather than a healthy default.

The [architecture guide](docs/ARCHITECTURE.md) covers contracts, authorization, storage and processing in detail.

## Evaluation

We evaluated the simulation model on **12,096 generated readings across 84 sessions**, with **2,592 readings from 18 held-out sessions** in the test partition. Seed 42 controls generation and splitting. Panel parameters, fault timing, sensor gains, cloud conditions and severity vary between sessions; all partitions still come from the same generator family.

| Measurement | Held-out synthetic result |
| --- | ---: |
| Classifier accuracy | 97.65% |
| Macro F1 | 0.9618 |
| Accepted prediction coverage | 96.95% |
| Accuracy among accepted predictions | 98.77% |
| Healthy expected-power MAE | 6.31 W |

Accuracy and macro F1 above include every classifier prediction before abstention. Coverage measures how often the confidence and support checks accept a known class; accuracy among accepted predictions excludes abstentions.

| Classifier | Validation macro F1 | Test macro F1 |
| --- | ---: | ---: |
| Rules | 0.9294 | 0.8339 |
| Random Forest | 0.9357 | 0.9618 |
| Gradient boosting | 0.9201 | 0.9439 |

We selected Random Forest for serving. Sigmoid calibration increased validation log loss from 0.1107 to 0.4464, so the application retains the uncalibrated forest probabilities. TreeSHAP explains the selected raw class, not the final temporal vote or a physical cause.

The confusion matrix uses actual labels as rows and predicted labels as columns:

| Actual / predicted | Normal | Open circuit | Short circuit | Shading | Soiling | Inverter |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Normal | 1624 | 0 | 0 | 0 | 0 | 0 |
| Open circuit | 0 | 175 | 0 | 0 | 0 | 0 |
| Short circuit | 0 | 0 | 174 | 0 | 0 | 0 |
| Partial shading | 18 | 0 | 0 | 183 | 25 | 0 |
| Soiling | 18 | 0 | 0 | 0 | 169 | 0 |
| Inverter fault | 0 | 0 | 0 | 0 | 0 | 206 |

| Forecast horizon | Forest MAE | Persistence MAE | Selected on validation |
| --- | ---: | ---: | --- |
| 15 minutes | 11.91 W | 13.28 W | Forest |
| 30 minutes | 19.22 W | 24.55 W | Forest |
| 60 minutes | 30.14 W | 43.23 W | Forest |

The incident replay contains 15 fault events, one missed event and three incorrect alert transitions. Median detection delay is 600 event seconds at a five-minute sampling interval. This measures the decision policy on the replay cadence, not API response time.

![Confusion matrix and probability reliability on synthetic test sessions](reports/evaluation.png)

Full results are in [reports/](reports/). The [model card](docs/MODEL_CARD.md) documents features, split sizes, threshold selection, stress cases and limitations.

### Reproduce the results

From an activated environment:

```bash
python -m solarsense setup
python -m solarsense evaluate
python -m pytest -q --junitxml=reports/pytest.xml
```

`setup` generates the default dataset and trains or reuses a checked release. Evaluation writes `reports/metrics.json`, `reports/test_predictions.csv`, `reports/evaluation.png` and `reports/scenarios.json`. Keep the model version and data hash with any reported result.

For a separate experiment, run `python -m solarsense train --trees 80`. Releases are immutable: repeating identical source, data and settings in the same model directory returns an existing-release error. Training does not change the active serving model; [operations](docs/OPERATIONS.md) describes promotion and rollback.

**Local reproduction record:** add the run date, Python version, model version, accuracy, macro F1, confusion matrix and pytest summary after running the commands above. The tables in this README are the recorded reference run.

## Hardware and notifications

The ESP-NOW gateway supplies voltage, current, air temperature, raw light ADC, humidity, thermistor temperature and relay feedback. Hardware mode uses the original six-feature, five-class Random Forest. A 1,000-input comparison with the original model produced identical classes and a maximum probability difference of 2.22 × 10⁻¹⁶.

Hardware mode does not infer missing AC power or irradiance, and does not provide the simulation model's inverter diagnosis, AC forecasts or SHAP explanations. Serial adapters accept Nano JSON and legacy CSV; incomplete sensor sets remain explicitly marked as missing. Physical relay control is disabled by default and requires manual enablement and gateway feedback.

Technician contacts are configured per station. Fault and recovery transitions produce notification jobs; repeated readings of the same incident do not produce a message each time. Preview mode needs no account. Live delivery uses Twilio, with separate states for submission, confirmed delivery, failure and uncertain outcomes.

See [hardware setup](docs/HARDWARE.md) and [technician alerts](docs/TECHNICIAN_ALERTS.md) for configuration and verification steps.

## Development and deployment

The dashboard source is in `frontend/`; its static export is included in `src/solarsense/static/`. To edit and rebuild it, use Node.js 24:

```bash
npm ci --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

The build copies the export into the Python package. Restart the backend and hard-refresh the browser afterward. The operations view is available at `/operations/` and uses the same backend with its own in-memory access key.

To run the Compose deployment with PostgreSQL:

```bash
python deploy/init_compose.py
docker compose up --build
```

Open http://localhost:8080. The [operations guide](docs/OPERATIONS.md) covers access keys, backups, monitoring and model changes.

The regression suite contains **43 tests**. GitHub Actions checks Python linting and tests, frontend type checking and build, dependency and secret scans, and Compose startup with an application-image scan. All four jobs passed in the [recorded verification run](https://github.com/Szin7/AI-powered-Solar-Fault-detection-system/actions/runs/40995107204). See [verification evidence](docs/ACCEPTANCE.md) for the scope of these checks.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/solarsense/` | API, storage, models, simulator, hardware adapters and notification workers |
| `frontend/` | React/Next.js dashboard and export scripts |
| `data/` | Sample schema and synthetic-data notes |
| `scenarios/` | Repeatable fault and network scenarios |
| `notebooks/` | Data and experiment exploration |
| `tests/` | Regression tests, hardware fixtures and browser checks |
| `reports/` | Measured evaluation and verification outputs |
| `deploy/` | Container initialization and monitoring configuration |
| `tools/` | WSL launcher and model-comparison utilities |
| `docs/` | Architecture, model card, setup and operating procedures |

## Limitations and next steps

The main limitation is the gap between generated data and field measurements. Shading and soiling overlap, mild losses can be missed, and unfamiliar conditions can receive confident known labels. An anomaly score or feature explanation does not establish a physical root cause. Independent labelled field sessions are needed before reporting real-world diagnostic accuracy.

The hardware prototype has been tested previously, but the current integration's recorded checks use protocol fixtures and model-equivalence tests. A new physical-device run and live SMS/WhatsApp delivery test remain outstanding. The partial Nano sensor set cannot support the complete hardware model without additional channels.

The system uses one backend process and three configured stations. It has no automatic retraining, per-visitor isolation, retention scheduler or verified 50-device capacity. PostgreSQL startup is covered by Compose CI; PostgreSQL backup restoration, optional monitoring profiles and public hosting need separate validation. Physical switching remains an operator action, and recommended actions are guidance rather than verified repairs.

Our next priorities are collecting labelled field sessions, testing the complete gateway-to-dashboard path on hardware, verifying live technician delivery and measuring performance over longer runs.

## License

SolarSense is released under the [MIT License](LICENSE). Third-party packages and bundled assets retain their own licences; see [components and dependencies](docs/CONTRIBUTIONS.md).
