# Use the original hardware

This update connects the current backend to the original ESP-NOW gateway contract. The original hardware was tested by the project owner. This integration was checked here with protocol fixtures and the supplied trained model, without physical devices.

## Supported paths

| Original device path | Connection in this version | Measurements and limits |
| --- | --- | --- |
| ESP32 ESP-NOW sender → gateway | Existing POST `/api/gateway-data` and GET `/api/get-command/{senderId}` | Voltage, current, air temperature, raw LDR ADC, humidity, thermistor temperature and reported relay state. Original five-class model. |
| Arduino Nano serial JSON | `serial --protocol nano-json` sends `READ` | Reads `v`, `i`, `t`, `l`; the original Nano does not supply humidity, thermistor temperature or raw ADC. Those stay missing, so six-feature diagnosis returns data quality until the channels are supplied. |
| Legacy serial CSV | `serial --protocol data` sends `GET_DATA` | Parses `DATA:voltage,current,temperature,light_adc,humidity,thermistor_temp`. Four-field messages are accepted with missing channels explicitly recorded. |
| Standalone ESP32 web-server sketches | Not connected by this adapter | Their `/api/data` pull interface differs from the tested gateway. Use the gateway path or implement a separate collector before claiming compatibility. |

The original gateway payload and command strings are unchanged. Already flashed sender nodes do not need rewriting. The gateway's configured backend address must still reach this computer; if the address changed, update `flaskServerUrl` in the original gateway sketch and reflash that gateway. Wi-Fi credentials and MAC addresses belong to the hardware setup and are not copied into this repository.

Station mapping is sender 1 → `roof-east` (Station 1), sender 2 → `roof-west` (Station 2), sender 3 → `lab-panel` (Station 3). Each dashboard station has a Simulator / ESP32-Serial source choice. The simulator skips hardware stations. Switching sources clears the current display and cancels pending commands while retaining historical rows. New readings must match the selected source.

## Run on D: with the existing gateway

From WSL:

```bash
cd /mnt/d/Projects/SolarSense
source .venv/bin/activate
python -m solarsense setup
python -m solarsense credentials
read -r -p 'Gateway LAN IP: ' LEGACY_GATEWAY_IPS
export LEGACY_GATEWAY_IPS
python -m solarsense serve --host 0.0.0.0 --port 8000
```

Use the operator key at http://localhost:8000, select the matching station, then **ESP32 / Serial**. The gateway should POST its array to `http://COMPUTER_LAN_IP:8000/api/gateway-data`. A 200 response contains `processed`, `duplicates` and `durable`. A 401 means the actual peer IP is not allowed; 409 means the station is still in simulator mode. Configure each sender station represented in the gateway's batch.

The unchanged gateway has no authentication header, so the command above explicitly allows its private LAN IP. This is intended for the local project network. A gateway that supports headers can instead send `X-Gateway-Key` on both POST and command polling, with the same value in the server's `SOLARSENSE_GATEWAY_KEY` environment variable. Do not put keys into source control.

WSL may not be reachable from another LAN device just because localhost works in Windows. Verify Windows/WSL networking and the firewall for TCP 8000 using your existing hardware-tested arrangement. The backend must see an allowed private peer address. If Windows forwards all clients through one address, an IP allowlist identifies that forwarder, not an individual gateway; use the header-key option to distinguish devices. This update cannot configure your laptop's LAN remotely.

## Relay commands

Hardware mode uses the original meaning: `relayStatus=true` means **relay activated**, not a universal claim that the panel is supplying power. Wiring determines the electrical effect. Physical commands are disabled by default. To use the existing manual relay controls, restart the server with:

```bash
export ENABLE_PHYSICAL_RELAY=1
python -m solarsense serve --host 0.0.0.0 --port 8000
```

The gateway polls the original command endpoint and receives `ACTIVATE_RELAY` or `DEACTIVATE_RELAY`. An accepted API request is not a physical confirmation. The command becomes acknowledged only after it was polled and a newly accepted gateway sample reports the requested state before expiry. Commands expire after 30 seconds by default. Serial adapters do not claim relay feedback. No model prediction automatically switches a physical relay.

## Serial devices

Keep the server running and select hardware source for the station. In a second activated terminal:

```bash
cd /mnt/d/Projects/SolarSense
source .venv/bin/activate
python -m solarsense serial --port /dev/ttyUSB0 --station roof-east --protocol nano-json
```

Replace the port with the actual device, for example `/dev/ttyACM0` or Windows `COM3` when running native Python. WSL needs the USB device exposed to Linux first. Baud rate defaults to 115200; `--baud` changes it. Use `--protocol data` for the legacy CSV protocol. The bridge persists up to 500 pending readings in `var/serial-STATION.json`, retries backend failures and stops acquiring when that queue is full. It never fabricates replacement values. Stop the bridge with Ctrl+C before switching that station back to simulation.

## Model and measurement provenance

Hardware inference uses the original 100-tree Random Forest, scaler and class order, exported to `src/solarsense/assets/hardware_forest.json.gz`. The asset records hashes of the original files. JSON tree traversal removes runtime dependence on loading an old sklearn pickle. It preserves the raw model's probabilities; smoothing and incident handling are explicit in `hardware.py` and `worker.py`.

The supported hardware classes are normal, open circuit, short circuit, partial shading and dust accumulation (displayed as soiling). The hardware path does not claim inverter diagnosis, synthetic-model SHAP explanations or AC forecasts. Voltage × current is displayed as DC power. LDR ADC is not converted to invented irradiance. Original sensor bounds are retained; measurements outside them produce data quality rather than silently being clipped into a diagnosis.

`reports/hardware-model-parity.json` records 1,000 seed-42 input comparisons: identical predicted classes and maximum probability difference 2.22e-16. This checks software equivalence, not accuracy on real faults. `tests/fixtures/hardware_predictions.json` stores 25 reference vectors for regression testing. Recheck with the trusted original archive using:

```bash
python tools/check_original_model.py --original ../OriginalSolarSense/backend
```

Adjust that path to the original backend directory containing the four `solar_fault_*.joblib` files. The original hardware's field accuracy has not been measured again in this environment.

## Weather

The dashboard requests current weather from Open-Meteo and caches successful responses for ten minutes. Failed requests retain a visibly stale cached response, or show unavailable. Weather does not replace measured model inputs. Defaults are Kathmandu; change `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_LOCATION` before starting the server for another location. Internet access is needed only for weather and live messaging, not the simulator. A cloudy-weather advisory does not prove that clouds caused a detected electrical fault.
