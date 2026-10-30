# Model card

Release: `127932dc8505`. Dataset SHA-256: `2af42e571af9cbe161de13f8f836ee0ef7949df1ae643b5f6d2f630c9544cab6`. Seed: 42. All results are synthetic.

The intended use is a local educational demonstration of monitoring and diagnosis. Unsupported uses include electrical protection, autonomous physical switching, estimating certified panel health, and claiming field fault accuracy.

## Data and splits

The default generator produces 84 sessions of 144 five-minute readings. Each class appears across different panel identities. Fault onset and recovery times vary by session. Panel ratings, load limits, sensor gains, noise, cloud levels and severities vary. The first 42 sessions train the models, 12 calibrate probabilities, 12 select thresholds/policies, and 18 form the fixed test partition. Adjacent readings never cross a split. Test conditions use a wider cloud/severity range. There is no external dataset or hidden physical measurement claim.

The nine classification features are normalized voltage, normalized current, delivered/available power ratio, AC/DC efficiency, irradiance, surface temperature, temperature rise, load ratio and humidity. The metadata/truth exclusions are tested. For expected power, only environmental inputs, rating and load are predictors; simultaneous measured voltage/current are excluded. Forecast features use current/past power, lagged power, rolling past means, current environment, rating, load and time of day. Targets are shifted within a session. A future-value perturbation test proves that forecast features before the perturbation stay unchanged.

## Decisions and experiments

The rule, forest and boosting comparisons are in `reports/metrics.json`. The served forest uses 120 trees, minimum leaf size two, balanced class weights and one CPU thread. A sigmoid calibrator is fitted on its own sessions. It loses to the raw forest on validation log loss, so raw probabilities are served. The unsuccessful calibration result remains in the report. No probability is presented as a proven frequency of real faults.

Validation chooses per-class confidence thresholds from 0.50 through 0.95, requiring at least five accepted examples and 95% validation precision when achievable. A conservative fallback threshold is 0.90. The class-support envelope uses training quantiles with fixed margins. The novelty detector is fitted only on healthy training data, with a healthy validation quantile cutoff. None of these choices uses final-test labels.

Coverage is the fraction of all test samples accepted as one of the six known labels after probability/support abstention. Accuracy among accepted predictions is reported separately; abstentions are not silently counted as successes. Incident replay additionally applies low-light suppression and temporal stabilization. The reliability plot uses the serving probability model. Bootstrap intervals resample complete sessions within their fault group; with only three test sessions per group, they are a weak uncertainty estimate rather than a guarantee.

Expected healthy delivered AC output is learned using healthy training rows, including load limits. Its test MAE is 6.312 W. This is not a calibrated physical performance ratio. Forecast models are evaluated at 15, 30 and 60 minutes against persistence. Serving chooses the validation winner by horizon. Intervals are not claimed. The dataset contains low-light periods, but a whole-night forecast benchmark is not included.

## Recorded limitations

Accuracy is 97.647% and macro F1 is 0.961840 before abstention. Partial shading and soiling are the difficult pair. Their measurements can overlap even in this generator. Strong open/short/inverter patterns are deliberately simpler, so perfect scores on those test classes do not establish field validity.

The separate stress suite includes mild shading, mild soiling, an unfamiliar electrical combination, voltage sensor offset, missing values, implausible temperatures, night, cloud and low load. Its outcome counts are published in `reports/scenarios.json`, including confident misclassification of unfamiliar patterns. Unknown detection is incomplete. The classifier and anomaly detector share the same synthetic family and cannot establish generalization to a real installation.

The incident report uses five-minute event timestamps. Median onset/recovery delay therefore reflects the three-vote policy on that cadence; it must not be quoted as the two-second simulator's detection latency. An incorrect alert transition means a newly stabilized fault differing from the fixture truth. A missed event means its correct label never stabilized during that event. An event can receive a wrong alert and later still be detected correctly.

Feature attribution is computed with TreeSHAP on the uncalibrated forest. It explains the model's association, not causality. Human reviews remain append-only and are not automatically used as labels. Joblib artifacts are trusted local files only; hash checking is corruption detection, not a signature or protection from an attacker who can replace both the artifact and manifest.

## Reproduction

Run `python -m solarsense setup`, then `python -m solarsense evaluate`. `reports/metrics.json`, `test_predictions.csv`, `evaluation.png` and `scenarios.json` are generated outputs. A different experiment uses `train --trees 80`; the immutable directory records source hash, data hash, feature contract, labels, evaluation and model hash. Model version is derived from source, dataset and training settings. Record package and Python versions alongside any rerun; exact byte-level model identity across different platforms is not promised.
