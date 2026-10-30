# Repository workflow

## Clone on D:

```bash
mkdir -p /mnt/d/Projects
cd /mnt/d/Projects
git clone https://github.com/Szin7/AI-powered-Solar-Fault-detection-system.git SolarSense-Portfolio
cd SolarSense-Portfolio
bash tools/run_wsl.sh
```

The WSL launcher installs dependencies, runs the regression suite, prepares models and starts the demo. Use `bash tools/run_wsl.sh --verify-only` to stop after setup and verification.

## Work on a change

Start from a clean working tree. If `git status --short` shows local work, commit it or deliberately set it aside before updating.

```bash
git status --short
git pull --ff-only
git switch -c docs/clarify-setup
```

Choose a branch name that describes the change. Review the diff, stage the intended files and commit with a message that explains the result:

```bash
git diff --check
git diff
git add README.md docs
git diff --cached --stat
git commit -m "clarify setup and operating procedures"
git push -u origin HEAD
```

Use a pull request to review changes before merging into `main`. Configure `user.name` and `user.email` locally if Git has no author identity. Keep existing history intact when updating a clone.

## Verify a clean checkout

Use Python 3.12 and run from the repository root:

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

Open http://localhost:8000 and connect with the newly generated operator key. Use `.venv/bin/python -m solarsense credentials` from the repository root if the shell is not activated. Native Windows uses `.venv\Scripts\python.exe` instead.

Frontend changes also require Node.js 24:

```bash
npm ci --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
```

Commit the dashboard source and its rebuilt export in `src/solarsense/static/` together. Run the browser check in [DEMO.md](DEMO.md) for changes to dashboard behaviour.

## Files to keep local

`.gitignore` excludes credentials, generated datasets, trained runtime models, local databases, notification contacts and dependency directories. Inspect staged files before committing, especially after adding configuration or reports. Include only measurements that belong to the recorded model version and dataset hash.

Secrets already exposed outside the project need rotation at the relevant service; removing a file from the latest commit does not revoke its contents. Do not commit `.env`, `var/credentials.json`, provider tokens or real technician contact exports.
