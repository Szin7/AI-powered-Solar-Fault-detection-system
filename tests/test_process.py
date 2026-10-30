import json
import os
import shutil
import socket
import subprocess
import sys
import time

import httpx
from sqlalchemy import func, select

from solarsense import db


def test_killed_backend_recovers_durable_batch(tmp_path, model_path, row):
    shutil.copytree(model_path / "models", tmp_path / "models")
    env = {**os.environ, "SOLARSENSE_HOME": str(tmp_path)}
    env.pop("DATABASE_URL", None)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = None
    engine = None
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=2)
    startup_timeout = float(os.environ.get("SOLARSENSE_TEST_STARTUP_TIMEOUT", "45"))
    assert 0 < startup_timeout <= 120, "Startup timeout must be between 0 and 120 seconds"
    starts = 0

    def stop(child):
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)

    def start():
        nonlocal starts
        starts += 1
        log_path = tmp_path / f"backend-start-{starts}.log"
        with log_path.open("wb") as log:
            child = subprocess.Popen(
                [sys.executable, "-m", "solarsense", "serve", "--port", str(port)],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + startup_timeout
        last_status = "No readiness response received"
        while time.monotonic() < deadline:
            if child.poll() is not None:
                last_status = f"Backend exited with code {child.returncode}; {last_status}"
                break
            try:
                remaining = deadline - time.monotonic()
                response = client.get("/health/ready", timeout=max(0.01, min(1.0, remaining)))
                last_status = f"HTTP {response.status_code}: {response.text[:1000]}"
                if response.status_code == 200:
                    return child
            except httpx.HTTPError as exc:
                last_status = f"{type(exc).__name__}: {exc}"
            time.sleep(0.1)
        stop(child)
        log_tail = log_path.read_text(errors="replace")[-6000:]
        raise AssertionError(
            f"Backend failed to become ready within {startup_timeout:g} seconds.\n"
            f"Last readiness check: {last_status}\n"
            f"Backend log: {log_path}\n{log_tail or '(no backend output)'}"
        )

    try:
        process = start()
        config = json.loads((tmp_path / "var/credentials.json").read_text())
        rows = [dict(row, sequence=i, boot_id="crash-test") for i in range(30)]
        response = client.post(
            "/api/v1/telemetry",
            json={"readings": rows},
            headers={"Authorization": "Bearer " + config["devices"]["roof-east"]},
        )
        assert response.status_code == 202
        assert response.json()["accepted"] == 30
        process.kill()
        process.wait(timeout=5)
        process = start()
        engine = db.connect("sqlite:///" + str(tmp_path / "var/solar.db"))
        for _ in range(100):
            with engine.connect() as conn:
                done = conn.execute(select(func.count()).select_from(db.results)).scalar()
            if done == 30:
                break
            time.sleep(0.1)
        assert done == 30
        with engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(db.telemetry)).scalar() == 30
    finally:
        client.close()
        if engine is not None:
            engine.dispose()
        if process is not None:
            stop(process)
