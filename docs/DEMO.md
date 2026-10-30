# Demo and replay guide

The demo runs three simulated stations through the same storage, inference and incident workflow used by the application. No hardware or messaging account is required. Keep technician delivery in preview mode when demonstrating alerts.

## Start a session

After installation and setup, run:

```bash
python -m solarsense demo
```

Open http://localhost:8000 and connect with the operator key printed in the terminal. A second browser window can use the viewer key. `python -m solarsense credentials` prints both local keys again from an activated environment.

The default scenario lasts about eight minutes. Its event clock advances two seconds every two wall-clock seconds. Ctrl+C stops the server and simulator. The dashboard's monitoring button changes only that browser's subscription.

## Walk through the system

1. **Inspect a station.** Select East roof. Compare voltage, current, temperatures, irradiance, load and AC output. Check the source label and distinguish event time from receive time. Freeze one browser while leaving another connected; acquisition continues.
2. **Introduce a fault.** Apply partial shading at severity 0.7. The preset changes measurements, not the predicted label. Inspect the raw class, score, temporal votes and feature contributions. The model can disagree with the injected condition.
3. **Review the incident.** Acknowledge an incident once it opens. Restore normal conditions and wait for a confirmed recovery. The fault and recovery remain in history.
4. **Preview an alert.** Save a technician contact with automatic alerts and **Include simulated incidents** enabled. A new incident transition produces a preview record. **Preview message** renders the latest message immediately without sending it.
5. **Interrupt telemetry.** Disconnect the simulated link. After the heartbeat interval of ten wall-clock seconds, readings become stale/offline. Restore the link and observe buffered delivery and recovery.
6. **Check a command.** Request virtual relay OFF, then ON. Compare requested, acknowledged and measured states. These simulated commands do not reach physical devices.

The management poll remains reachable during the simulated telemetry-link fault so that the operator can restore it. An actual API outage also interrupts management polling. The simulator holds pending readings in a bounded local spool and reports dropped counts when applicable.

The benchmark panel reports synthetic results. Shading and soiling overlap, calibration did not improve validation log loss, and unfamiliar patterns are not reliably recognized. The stress report includes these failure cases.

## Accelerated forecast run

```bash
python -m solarsense demo --scenario scenarios/day.yaml
```

The compressed day advances event time by five minutes every 0.2 seconds, making forecast history available quickly. Forecast horizons follow reading timestamps rather than browser wall time. The scenario includes faults, delayed batches, a disconnected link and cloud variation.

The default eight-minute scenario ends before the roughly 15-minute forecast warmup completes. Use the compressed day or a longer session to exercise forecasting.

## Longer sessions and replay

Run the backend in one activated terminal:

```bash
python -m solarsense serve
```

Start the simulator in another:

```bash
python -m solarsense simulate --scenario scenarios/interview.yaml --steps 10000 --run-dir var/my-session
```

Repeating the same command resumes the saved step and pending spool. A new run directory creates a new boot/run identity. Changing scenario settings during a resume is rejected. Ground truth is stored in `var/my-session/truth.jsonl`, separately from the inference inputs in `readings.jsonl`.

With the backend still running:

```bash
python -m solarsense replay var/my-session/readings.jsonl
```

Replaying the same readings again should report duplicates instead of new accepted rows. Identities are preserved. Use a fresh `SOLARSENSE_HOME` when replaying an earlier day as current data; older timestamps deliberately cannot replace newer live state.

A fresh online simulator can move its start to a later simulated day to avoid overlapping stored history. That start is recorded in the run directory. Resumed runs retain their original timeline.

## Browser verification

With the API and simulator running, use a third activated terminal:

```bash
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python tests/browser_check.py
```

The check covers desktop and mobile layout, WebSocket updates, viewer restrictions, freeze, expanded charts, manual inputs, relay acknowledgement, missing-current rendering and CSV export. It runs with the normal content security policy, temporarily changes Station 1 conditions and restores the scheduled scenario afterward.
