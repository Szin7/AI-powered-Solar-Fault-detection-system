# Operations

Run commands from the repository root. `SOLARSENSE_HOME` can point to another local state directory. The default is the current directory; runtime files live in `var/`, models in `models/`, and generated data in `data/generated/`. Use one backend worker. The supported demo requires no external notification recipient, cloud credential or weather endpoint.

| Setting | Default / meaning |
| --- | --- |
| DATABASE_URL | Local SQLite file; PostgreSQL accepts a `postgresql+psycopg://` URL |
| PUBLIC_READ | 0 locally; 1 in Compose grants anonymous viewer access only |
| ALLOWED_ORIGINS | Exact local browser origins; set the hosted origin before any remote deployment |
| HEARTBEAT_SECONDS | 10 wall-clock seconds |
| NOTIFICATION_URL | Empty: local inbox; optional explicitly configured HTTP sink |
| MLFLOW_TRACKING_URI | Optional experiment tracking endpoint; defaults to a local SQLite tracking DB when `--track` is used |

The first setup creates random keys in ignored `var/credentials.json`. Device tokens are stored hashed in the database. Operators/viewers use distinct local bearer keys. To rotate a local deployment, stop both processes, archive/delete that credentials file, and rerun setup; existing data remains, and device hashes are replaced. Restart every process so it reads the new keys. Do not publish the previous prototype's credential history. This new repository does not contain that history or the old firmware.

## Model promotion and rollback

Training never silently changes active inference. After a new experiment, the following commands select the candidate from its generated report without a manual version substitution:

```bash
python -m solarsense train --trees 80
python -c "import json; from solarsense.ml import shadow; v=json.load(open('reports/metrics.json'))['model_version']; print(shadow('models',v,'data/generated/solar.csv'))"
python -c "import json; from solarsense.ml import promote; v=json.load(open('reports/metrics.json'))['model_version']; print(promote('models',v))"
python -m solarsense rollback
```

The API reloads the active pointer within two seconds. Check `/health/ready` and the result's model version. Promotion requires compatible features/labels, a matching artifact hash, the recorded minimum synthetic benchmark gates, and a successful deterministic validation replay. Shadow output also records disagreement with the active model. This is a simple replay check, not a full live canary service. Rollback needs a previously promoted compatible release. To return to a different compatible version, `python -m solarsense promote VERSION` accepts the actual 12-character version printed by training.

Keep candidate evaluation reports with their immutable model directory. Only locally trained/trusted joblib files may be loaded. The public API has no artifact upload path. The minimum promotion thresholds are deliberately modest educational checks, documented in the manifest; passing them is not permission for physical control.

For optional MLflow tracking:

```bash
python -m pip install -r requirements-mlflow.txt -c requirements.txt
python -m solarsense train --trees 64 --track
```

The default stores tracking metadata in `reports/mlflow.db`, with artifacts in the local MLflow artifact directory. For the optional Compose tracking service, set `MLFLOW_TRACKING_URI=http://127.0.0.1:5000` in the shell before running the same command. The full container profile remains an unexecuted deployment check in this release.

## Back up and restore SQLite

Stop the simulator first, then the API for a coordinated database/model snapshot. The database backup API itself is safe against concurrent SQLite writes; stopping also ensures the model pointer cannot change halfway through the snapshot.

```bash
python -m solarsense backup backups/interview-snapshot
python -m solarsense restore backups/interview-snapshot restored-demo
```

The destination must be new. The backup contains a consistent database copy, models and SHA-256 manifest. Restore verifies hashes and SQLite integrity, and creates `restored-demo/var/solar.db` and its model directory. Credentials are intentionally regenerated on first setup; they are not carried in the backup. The database's old device hashes are replaced by migration initialization. Set `SOLARSENSE_HOME` to the absolute path of `restored-demo`, run setup and serve. Restore does not overwrite the source or an existing target. The test compares persisted identities and result counts in the restored database.

For PostgreSQL, stop the simulator/API, keep PostgreSQL running, and use:

```bash
mkdir -p backups
docker compose exec -T postgres pg_dump -U solar -d solar -Fc > backups/solar.dump
```

Copy the corresponding model volume separately using `docker compose cp api:/app/models backups/models` before removing containers. For a fresh Compose deployment with its database initialized but app stopped:

```bash
docker compose exec -T postgres pg_restore -U solar -d solar --clean --if-exists < backups/solar.dump
```

Restore the compatible model directory and verify station/result counts and readiness before starting the simulator. This PostgreSQL procedure is provided for the unverified container route; only SQLite backup/restore was executed here. Never apply an unknown schema version to existing data. Future migrations require a versioned migration function and a tested rollback/restore procedure.

## Docker and monitoring

```bash
python deploy/init_compose.py
docker compose up --build
```

The setup job trains once into persistent volumes. App and simulator containers run as a non-root user. The frontend uses unprivileged Nginx. Only loopback ports are published. `docker compose exec api python -m solarsense credentials` prints local access keys. Public reads are enabled for this loopback Docker demo, while all operator writes remain authenticated.

```bash
docker compose --profile monitoring up -d
docker compose --profile tracking up -d
```

Prometheus is at http://127.0.0.1:9090, Grafana at http://127.0.0.1:3000, and optional MLflow at http://127.0.0.1:5000. Grafana uses user `admin` and the generated `GRAFANA_PASSWORD` in `.env`. No default shared password is committed. Metrics use fixed names without device/run labels: accepted/duplicate/rejected counters, processing latency, pending work, connected viewers and failed notifications. The drift API compares daylight and low-light regimes separately; a PSI above 0.25 is a review cue, not an accuracy measurement.

`docker compose down` stops services and retains volumes. `docker compose down -v` permanently removes demo database/models and should only be used after an intentional backup. Image tags are fixed, but tag contents can still be updated by publishers; pin verified digests before a hosted release.

No hosted deployment has been provisioned. Before one is published, complete the container CI job, use TLS, restrict origins, leave public access read-only, protect/rotate local keys, measure memory/latency on the intended host, and document its actual bill and shutdown procedure. This avoids inventing a hosting claim or cost estimate.

## Troubleshooting and checks

A model error makes readiness fail; telemetry can still be durably accepted and queued. A database error returns 503 rather than pretending a reading was saved. Inspect server logs and `var/` disk space. Notification jobs retry with bounded exponential backoff and preserve attempt history; after six failures they remain failed for inspection. The default local inbox deduplicates event IDs. An external sink must honour the `Idempotency-Key` header to avoid duplicate delivery after an acknowledgement loss.

Local API clients bypass environment proxy settings. That keeps loopback traffic local; use a reachable direct URL for the supported simulator path. Change `demo --port 8001` if port 8000 is occupied and add the matching origin to `ALLOWED_ORIGINS` before connecting a browser. Do not run a second API worker against the same state. Ensure the filesystem is writable and allow package downloads during first installation.
