All included solar data is synthetic. I do not have a physical panel or a labelled field dataset.

`python -m solarsense generate` writes `generated/solar.csv` and its SHA-256 manifest. The CSV contains 84 separate sessions with 144 five-minute measurements each. The six labels are normal, open circuit, short circuit, partial shading, soiling and inverter fault. The manifest records the complete session split. Generated files are ignored by Git; the small `sample.csv` is included for inspecting the schema.

The generator uses pvlib's PVWatts DC calculation for available DC power. Delivered power is capped by load. It adds temperature variation, a smooth cloud trajectory, measurement noise and persistent session-level sensor gains. The reported irradiance is a simulated irradiance measurement, not an LDR conversion or live weather feed. `light_adc` is a separate approximate brightness channel and is not a model feature.

Voltage/current relationships and fault multipliers are simplified. The AC channel makes simulated inverter faults observable. The model cannot establish real fault causes from this synthetic training distribution. Shading and soiling can overlap, mild losses can be missed, and unseen conditions can receive confident known labels.

Features exclude truth labels, session IDs, split labels, device identity, scenario IDs, severity controls and future observations. The simulator saves truth in a separate `truth.jsonl`, never in an ingestion payload. Live simulator logs are under ignored `var/runs/`.
