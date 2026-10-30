# Solar data

We use a deterministic synthetic dataset to develop and compare the simulation models. All included sample data and the published simulation benchmark come from this generator, not from a labelled field collection. Hardware readings use a separate model and are not part of this benchmark.

From the repository root:

```bash
python -m solarsense generate
```

With the default `SOLARSENSE_HOME`, this writes `data/generated/solar.csv` and its SHA-256 manifest. The dataset contains 84 sessions of 144 five-minute measurements each: 12,096 rows in total. Seed 42 controls generation, and the manifest records the session split. Generated files are ignored by Git; [sample.csv](sample.csv) provides a small schema example.

## Generation

The generator uses pvlib's PVWatts DC calculation for available power and caps delivered power by load. Sessions vary panel ratings, sensor gains, cloud trajectories, noise, fault timing and severity. The six labels are normal, open circuit, short circuit, partial shading, soiling and inverter fault.

Irradiance is a simulated measurement. The separate `light_adc` channel approximates brightness and is not a classification feature. The AC channel makes inverter losses observable in simulation. Voltage/current relationships and fault multipliers are simplified, so shading and soiling can overlap and unfamiliar conditions may receive confident known labels.

## Splits and leakage checks

Whole sessions remain within one partition: 42 for training, 12 for calibration, 12 for validation and 18 for testing. This keeps adjacent readings from appearing in both training and test data. All partitions still share the same generator family.

Model features exclude truth labels, session and station identity, split labels, scenario IDs, severity controls and future observations. Forecast targets are shifted within sessions. Tests check feature exclusions and confirm that changing future power does not alter earlier forecast features.

Live simulation saves truth separately in `var/runs/.../truth.jsonl`; it is never included in an ingestion payload. Runtime logs and physical telemetry remain local. See the [model card](../docs/MODEL_CARD.md) for evaluation details and limitations.
