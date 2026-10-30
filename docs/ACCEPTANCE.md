# Verification and test coverage

We check SolarSense at three levels: automated regression tests, recorded application runs and deployment checks. This document separates those results from work that still requires physical devices or external services.

## Current baseline

The regression suite contains 43 tests. The latest local run completed in 18.90 seconds, recorded in [continuation-pytest.xml](../reports/continuation-pytest.xml). Runtime varies by machine and filesystem; process startup can be considerably slower on a WSL-mounted Windows drive.

All four jobs passed in [GitHub Actions run 40995107204](https://github.com/Szin7/AI-powered-Solar-Fault-detection-system/actions/runs/40995107204), for commit `12584dd26f60bc84fa1a22fd8239b711a15f7b0e`:

| Job | Checks |
| --- | --- |
| Python | Lint and format checks, regression tests, setup and evaluation |
| Frontend | Clean dependency installation, TypeScript checking and static build |
| Security | Python dependency audit and repository secret scan |
| Containers | Compose configuration and build, API readiness, station endpoint and application-image vulnerability scan |

The image scan checks high and critical vulnerabilities with available fixes. A passing scan reflects the database and dependencies used in that run, not a continuing security guarantee. The upstream Starlette/httpx deprecation warning is non-fatal.

## Behaviour covered

| Area | Evidence |
| --- | --- |
| Installation and setup | Clean-environment installation, compatible dependencies, generated data, trained model and evaluation |
| Authorization | Anonymous and viewer writes rejected; scoped device tokens cannot impersonate another station |
| Duplicate readings | Concurrent retries create one record; conflicting values under the same identity return 409 |
| Sensor quality | Invalid contracts rejected; missing, implausible and stuck measurements produce explicit quality states |
| Viewer independence | Multiple WebSocket clients do not create telemetry or trigger inference |
| Connectivity | Heartbeat transitions, retained history, bounded offline spool and dropped-reading counts |
| Late arrivals | Older event timestamps remain historical and cannot replace newer live state |
| Process recovery | Backend killed after accepting a 30-reading batch; all 30 results present after restart |
| Database failure | Injected failure returns 503 instead of acknowledging unsaved data |
| Model availability | Readiness fails when a compatible, intact artifact is unavailable |
| Prediction consistency | Class index, probability argmax, explanation target, votes and model version checked |
| Reproducibility | Seeded generation hashes, repeated inference and shadow probabilities agree |
| Forecast leakage | Changing future power leaves earlier features unchanged; targets stay within sessions |
| Model lifecycle | Promotion, rollback, integrity rejection and deterministic replay checks |
| SQLite restoration | Restored identities, result counts and model pointer match the snapshot |
| Hardware protocol | Gateway authorization, replay handling, source separation and command feedback |
| Technician alerts | Preview creation, masking, deduplication, message formats, status polling and ambiguous-timeout handling |

## Application and browser checks

[baseline.json](../reports/baseline.json) records a three-station run at a two-second cadence. Two viewers were connected for 27 seconds during the 40-second run. All 60 readings were processed, with approximately 0.15-second p95 acceptance-to-result latency. Two relay commands were acknowledged and an incident was recorded.

A separate 60-reading burst is recorded in [system.json](../reports/system.json). Its p95 latency is higher and can exceed one second. These measurements do not establish 50-device capacity, ten-viewer performance or browser paint latency.

The browser checks cover desktop 1440 × 1000 and mobile 390 × 844 layouts, WebSocket updates, station switching, freeze, expandable charts, manual sensor input, relay feedback, CSV export, missing-current display and viewer restrictions. The recorded run found no JavaScript errors or horizontal overflow. See [integrations-browser.json](../reports/integrations-browser.json).

[continuation-live-check.json](../reports/continuation-live-check.json) records API readiness, three online stations, the served dashboard and an incident-triggered technician preview. No external message was sent.

## Model evidence

The simulation benchmark, session splits, confusion matrix, accepted-prediction coverage and stress outcomes are recorded in [metrics.json](../reports/metrics.json) and [scenarios.json](../reports/scenarios.json). The [model card](MODEL_CARD.md) explains their scope. Unknown-pattern recognition remains incomplete, and synthetic accuracy is not field accuracy.

The hardware model comparison uses 1,000 seed-42 input vectors. It produced identical classes and a maximum probability difference of 2.22 × 10⁻¹⁶ against the original model. This verifies the exported model's computation, not its diagnostic accuracy. Twenty-five reference vectors also form part of the regression fixtures.

## Remaining validation

The hardware prototype was tested previously. The current gateway and serial integration still needs a complete physical-device run, including relay feedback with the actual wiring. Live SMS and WhatsApp delivery require a configured account, an approved destination and, for WhatsApp, an approved template.

Compose CI covers startup with PostgreSQL and the application readiness path. It does not cover PostgreSQL network-outage recovery or backup restoration. The optional monitoring and tracking profiles, manual image-release workflow and public hosting also need their own execution checks.

Long-duration storage growth, automatic retention, full-night forecasting, a 50-device load test and resource measurements on the intended deployment machine remain outside the recorded evidence.
