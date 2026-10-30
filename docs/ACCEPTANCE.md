# Acceptance evidence

This is a completed local implementation of the core hardware-free system, with measured evidence below. It is not a claim that every proposed deployment or performance target has been verified. The source is complete; optional infrastructure still requires its own runtime check.

| Plan check | Evidence / outcome |
| --- | --- |
| A01 fresh clone and offline fixtures | Clean-venv installation, setup, evaluation and pytest; no network calls are made by the default simulator or model pipeline after installation. |
| A02 operator authorization | Anonymous and viewer writes denied in API regression tests; real browser viewer controls disabled. |
| A03 station scope | Device impersonation and cross-station command acknowledgement denied. |
| A04 duplicates | Concurrent duplicate requests create one row; conflicting values return 409. Live replay of 60 existing readings creates zero new rows. |
| A05 invalid/missing sensors | Validation rejects malformed contracts; explicit missing/invalid/stuck states are tested and never fabricated as normal. |
| A06 viewer independence | Two WebSocket clients do not create readings or results; the independent simulator was also run with two browser viewers. |
| A07 outage/recovery | Heartbeat boundary and recovery tested; history retained; bounded offline spool and dropped counts tested. |
| A08 delayed messages | Historical late readings cannot replace newer live state. |
| A09 crash recovery | A backend subprocess is killed after durable acceptance of a 30-row batch; all 30 results are present after restart. |
| A10 database failure | Injected database failure returns 503, not durable acknowledgement. Full PostgreSQL network outage remains a Docker integration check. |
| A11 unavailable model | Readiness fails without a compatible artifact; no invented diagnosis. |
| A12 label consistency | Raw index, probability argmax, explanation target, votes and version are checked. |
| A13 reproducibility | Same seeded generator output has the same hash; repeated inference and shadow probabilities agree. |
| A14 difficult scenarios | Per-class, abstention, session-bootstrap and stress outcomes are recorded, including failures. Unknown recognition is incomplete. |
| A15 benign regimes | Normal/cloud/low-load fixture produces no critical circuit/inverter incident; night and relay-off suppression tested. |
| A16 forecast leakage | Changing future power leaves all earlier forecast features unchanged; targets stay within sessions. |
| A17 notifications | Persistent fault/recovery jobs retry a failed sink, then deliver once to the local inbox. |
| A18 promotion/rollback | Compatible candidate promotion and rollback to a distinct prior release executed; integrity failure and shadow checks tested. |
| A19 restore | SQLite snapshot restored to a new directory; identity and result counts match, model pointer preserved. PostgreSQL restore not executed here. |
| A20 browser/mobile | Chromium desktop 1440×1000 and mobile 390×844: restored original gauges and charts, live socket, station switching, manual readings, relay confirmation, CSV export, missing-current handling, viewer restrictions and freeze; no JavaScript errors or horizontal overflow. |

The original automated suite had 29 tests. The dashboard restoration adds manual-control authorization/validation and repeated-session clock checks, for 31 tests. `reports/dashboard-pytest.xml` records the updated run; the older `reports/pytest.xml` remains historical. Runtime depends on the machine: the user's mounted D: drive took 84 seconds for the process recovery test alone, so there is no universal under-one-minute suite claim. An upstream Starlette/httpx deprecation warning is retained; it is not a test failure. `reports/dependency-audit.json` records the base dependency audit with no known vulnerabilities at the time it was run. That is a dated scan result, not a continuing security guarantee.

The live baseline uses three stations at a two-second cadence, with two connected browser viewers for 27 seconds during a 40-second simulator run. Its 60 readings were processed with about 0.15-second p95 acceptance-to-result latency, below the proposed one-second target. Two relay commands were acknowledged and an incident was recorded. Exact values and model version are in `reports/baseline.json`.

The separate 60-reading burst completed without data loss. Its p95 latency is higher than the baseline and can exceed one second; inspect `reports/system.json`. This is not evidence for 50 devices or ten simultaneous viewers. Browser change events and reconnect were exercised, but no dedicated end-to-end paint latency distribution or full 16-GB-laptop memory benchmark was measured.

## Implementation decisions relative to the plan

The original Next.js dashboard has been restored. It is exported at build time and served by FastAPI locally and by Nginx in Compose. The Python demo needs no Node server. SQLite is the verified default; PostgreSQL is supplied in Compose. The same authentication, independent acquisition, history, incident, explanation and control boundaries remain.

Model tracking works locally through optional MLflow dependencies. Monitoring and MLflow Compose profiles, container image scans, PostgreSQL runtime/restore and the manual image-release workflow are supplied but unexecuted because Docker and a connected GitHub deployment target were unavailable. GitHub Actions includes a container integration job to perform those checks after push. No public hosted service, cloud resources or GitHub repository was created.

The core captures simulator configuration, event truth, data hashes, model manifests, label-review history and notification attempt history. The hardware update adds the original ESP-NOW gateway and serial adapters. It does not implement public per-visitor sessions, MQTT, predictive remaining life, automatic retraining or a retention scheduler. These were deferred extensions or require evidence absent from this release. A general scenario registry for arbitrary fleets and a 50-device load campaign are not claimed.

The SQLite migration is versioned and rejects unknown versions; there is only one schema version in this initial release. A genuine future upgrade must add an explicit migration and test data restoration. Tests of mocked database failure do not substitute for a complete infrastructure outage experiment.

## Hardware and technician update

`reports/integrations-pytest.xml` records 43 passing tests, including gateway authentication, replay deduplication, source separation, original-model regression, physical-command gating and feedback, automatic technician previews, SMS/WhatsApp formatting and provider retry semantics. Model parity covers 1,000 seed-42 vectors with identical classes, documented separately from the synthetic accuracy benchmark. Weather success/cache/failure paths use mocked HTTP responses. New settings and delivery tables are created additively without altering existing telemetry; old databases are opened by the browser regression.

Physical hardware was tested by the owner in the original project. This update's physical-device run and live paid messaging remain unverified here. The serial Nano path exposes missing channels instead of inventing the six-feature input. See HARDWARE.md and TECHNICIAN_ALERTS.md for exact boundaries.
