# Clone, commit and push

Clone the project into D: from WSL:

```bash
cd /mnt/d/Projects
git clone https://github.com/Szin7/AI-powered-Solar-Fault-detection-system.git SolarSense-Portfolio
cd SolarSense-Portfolio
bash tools/run_wsl.sh
```

The launcher installs dependencies, runs checks and starts the local demo. To update an existing clone, commit your local changes first, then run `git pull --ff-only`.

For an independent repository, extract the source ZIP and create a new history. The following seven commits cover every tracked deliverable in dependency order. Use them only in the source folder without the supplied Git history.

```bash
git init -b main
git add .gitignore .dockerignore LICENSE pyproject.toml requirements.txt requirements-mlflow.txt src/solarsense/__init__.py src/solarsense/__main__.py src/solarsense/config.py src/solarsense/data.py src/solarsense/features.py scenarios data
git commit -m "add reproducible solar data generator"
git add src/solarsense/ml.py src/solarsense/monitoring.py src/solarsense/evaluation.py
git commit -m "train and compare solar fault models"
git add src/solarsense/db.py src/solarsense/schemas.py src/solarsense/worker.py src/solarsense/api.py src/solarsense/hardware.py src/solarsense/assets src/solarsense/integrations.py src/solarsense/technicians.py src/solarsense/weather.py src/solarsense/serial_bridge.py
git commit -m "persist telemetry and add fault resolution rules"
git add src/solarsense/cli.py src/solarsense/simulator.py src/solarsense/static frontend tools
git commit -m "add independent simulator and live dashboard"
git add tests requirements-browser.txt
git commit -m "test auth recovery replay and model integrity"
git add Dockerfile compose.yaml deploy .github
git commit -m "add container deployment and continuous integration"
git add README.md docs notebooks reports
git add -A
git commit -m "document measured results and interview demo"
```

These commits describe the final delivered snapshot in seven stages; they do not imply seven independently deployable historical releases. If your repository already contains earlier work, use one update commit instead:

```bash
git status --short
git add -A
git diff --cached --stat
git commit -m "connect original hardware and technician alerts"
git status --short
```

The final status should show no forgotten source files. Runtime credentials, models, local data and dependencies are excluded by `.gitignore`.

Git needs your own author name and email configured before those commits. For new commits, set your usual Git identity locally with `git config user.name` and `git config user.email` using your own values.

With GitHub CLI installed, these commands create a new public repository under your authenticated account and push the existing branch. Use `--private` instead of `--public` if that is your preference. The name must be unused in that account.

```bash
gh auth login
gh repo create SolarSense --public --source=. --remote=origin
git push -u origin main
```

For an existing empty GitHub repository, use this Bash sequence, pasting its actual clone URL when prompted:

```bash
read -r -p "GitHub repository clone URL: " solar_repo_url
git remote add origin "$solar_repo_url"
git push -u origin main
```

Never force-push over an existing project without reviewing its history. This new repository intentionally excludes the old archive's credentials. If those credentials were ever published, removing them from this new tree does not revoke them; rotate them in the original service before using that old configuration again.

## Verify from a clean clone

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
python -m pip check
ruff check src tests deploy/init_compose.py
ruff format --check src tests deploy/init_compose.py
python -m pytest -q
python -m solarsense setup
python -m solarsense evaluate
python -m solarsense demo
```

Expect the app at http://127.0.0.1:8000 and a newly generated local operator key. Training metrics are written to `reports/metrics.json`; never paste values from a different experiment without its manifest. Initial installation requires network access and writable disk space. Adjust only the Python launcher/activation command for your OS, an occupied port/origin, and your own GitHub identity/destination. No source-code edit is required for the standard local demo.
