#!/usr/bin/env bash
set -Eeuo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
case "$repo" in
  /mnt/d/*) ;;
  *) echo 'Run this launcher from the project on D: (/mnt/d/...).'; exit 2 ;;
esac
cd "$repo"
mkdir -p var
log="$repo/var/launch-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$log") 2>&1
stage='initial checks'
trap 'code=$?; printf "\nStopped during: %s (exit %s).\nLog: %s\nSend the final error lines, not your credentials.\n" "$stage" "$code" "$log"; exit "$code"' ERR

if [[ "${1:-}" != '' && "${1:-}" != '--verify-only' ]]; then
  echo 'Usage: bash tools/run_wsl.sh [--verify-only]'
  exit 2
fi
export SOLARSENSE_HOME="$repo"
export UV_LINK_MODE=copy
export UV_CACHE_DIR="$repo/var/uv-cache"
export UV_PYTHON_INSTALL_DIR="$repo/var/uv-python"
export SOLARSENSE_TEST_STARTUP_TIMEOUT="${SOLARSENSE_TEST_STARTUP_TIMEOUT:-120}"
# This launcher is for the hardware-free demonstration, including local alert previews.
export TECHNICIAN_DELIVERY=preview

stage='Python environment'
if command -v uv >/dev/null 2>&1; then
  if [[ ! -x .venv/bin/python ]]; then
    uv venv --python 3.12 .venv
  fi
  .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use a Python 3.12 environment for this project"'
  stage='dependency installation'
  uv pip install --python .venv/bin/python -r requirements.txt
  uv pip install --python .venv/bin/python --no-deps -e .
  uv pip check --python .venv/bin/python
else
  if [[ ! -x .venv/bin/python ]]; then
    python3.12 -m venv .venv
  fi
  .venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Use a Python 3.12 environment for this project"'
  stage='dependency installation'
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python -m pip install --no-deps -e .
  .venv/bin/python -m pip check
fi

stage='automated tests'
.venv/bin/python -m pytest -q
if [[ "${1:-}" != '--verify-only' ]]; then
  stage='local port check'
  .venv/bin/python - <<'PYPORT'
import socket
with socket.socket() as sock:
    try:
        sock.bind(("127.0.0.1", 8000))
    except OSError as exc:
        raise SystemExit("Port 8000 is unavailable. Stop the previous SolarSense server, then rerun the launcher.") from exc
PYPORT
fi
stage='model setup'
.venv/bin/python -m solarsense setup
printf '\nVerification completed. Technician delivery is in preview mode.\n'
if [[ "${1:-}" == '--verify-only' ]]; then
  printf 'Run bash tools/run_wsl.sh to start the demo.\n'
  exit 0
fi
stage='demo startup'
printf 'Open http://localhost:8000 when ready. Press Ctrl+C to stop.\n'
# Keep the printed local access key out of the saved diagnostic log.
.venv/bin/python -m solarsense demo > /dev/tty 2>&1
