# Five-minute interview demo

Start `python -m solarsense demo`. Connect as operator in one window and viewer in another. Explain the persistent SIMULATED DATA badge before quoting any measurements.

During the first minute, select Station 1 (East roof). Identify the distinction between DC sensors, AC output, expected healthy output and load. Show event time versus receive time, the selected model version, and warming or normal state. Freeze one browser and show that the other continues updating.

Set partial shading to severity 0.7 and apply it. Wait for the measurements to change. The model may disagree with an injected condition; the controls never directly set its prediction. Explain raw prediction, confidence method, the last-five votes, and the SHAP inputs. Acknowledge the incident if one opens. Restore normal operation and show the recovery event and local notification delivery attempts.

Disconnect the telemetry link. In ten wall-clock seconds the station should show stale/offline while retaining its last readings. Restore the link and observe recovery. This fault disconnects telemetry delivery; the separate simulator management poll remains reachable so an operator can restore it. A real API outage also interrupts that management poll. Pending readings are held in the bounded local spool; dropped counts are printed explicitly.

Request virtual relay OFF, then ON. Show the difference between requested, acknowledged and measured state. These are idempotent state requests, not toggles, and never reach electrical hardware.

Finish with the benchmark panel. Explain why the data is synthetic, why shading and soiling overlap, and why calibration was rejected on validation evidence. Show a failed stress case rather than claiming unknown detection is solved.

## Forecast and replay demo

Use `python -m solarsense demo --scenario scenarios/day.yaml` for a separate accelerated run. Fifteen event minutes arrive in under a second, allowing the forecast history to warm quickly. Its timestamps, not browser wall time, determine the prediction horizon. The run includes faults, delayed batches, a disconnected link and cloud cover. The event schedule is in the YAML file.

For longer sessions, run two terminals:

```bash
python -m solarsense serve
```

```bash
python -m solarsense simulate --scenario scenarios/interview.yaml --steps 10000 --run-dir var/my-session
```

Restarting that exact command resumes its saved step and spool. A new directory creates a new boot/run identity. Switching YAML settings while resuming is rejected. Ground truth is in `var/my-session/truth.jsonl`; the inference input is the separate `readings.jsonl`.

```bash
python -m solarsense replay var/my-session/readings.jsonl
```

Replay twice: the second response should report duplicates, not new accepted readings. Existing identities are preserved. To demonstrate clean event-time history for an earlier recorded day, use a fresh `SOLARSENSE_HOME`; older readings intentionally cannot overwrite a newer live timestamp.

## Browser verification

With a running API and simulator, in a third terminal:

```bash
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python tests/browser_check.py
```

Run the browser check while the server and simulator are running. It checks the restored dashboard on desktop and mobile, live WebSocket connection, viewer restrictions, freeze, expanded charts, manual sensor input, relay acknowledgement, missing-current rendering and CSV export. CSP is not bypassed. The check temporarily changes Station 1 conditions, then restores the scheduled scenario.
