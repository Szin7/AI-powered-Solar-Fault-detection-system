import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time

from solarsense.config import load_settings


def setup(sessions=84, steps=144, trees=120):
    from solarsense import db
    from solarsense.data import generate_dataset
    from solarsense.ml import promote, shadow, train

    settings = load_settings()
    engine = db.connect(settings["database_url"])
    db.migrate(engine, settings)
    engine.dispose()
    active = settings["models"] / "active.json"
    if not active.exists():
        data_dir = settings["root"] / "data" / "generated"
        generate_dataset(data_dir, sessions, steps)
        version, _ = train(data_dir, settings["models"], settings["root"] / "reports", trees)
        shadow(settings["models"], version, data_dir / "solar.csv")
        promote(settings["models"], version)
    print("Setup complete. Run python -m solarsense credentials to see local access keys.")


def demo(port, scenario):
    setup()
    settings = load_settings()
    server = subprocess.Popen([sys.executable, "-m", "solarsense", "serve", "--port", str(port)])
    simulator = None
    try:
        import httpx

        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError("API exited; inspect the error above")
            try:
                if (
                    httpx.get(f"http://127.0.0.1:{port}/health/ready", timeout=1, trust_env=False).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("API did not become ready within 60 seconds")
        simulator = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "solarsense",
                "simulate",
                "--url",
                f"http://127.0.0.1:{port}",
                "--scenario",
                scenario,
            ]
        )
        print(
            f"\nOpen http://127.0.0.1:{port}\nLocal operator key: {settings['credentials']['operator']}\nCtrl+C stops both processes.\n",
            flush=True,
        )
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for process in [simulator, server]:
            if process is not None and process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser(prog="solarsense")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("setup")
    init.add_argument("--sessions", type=int, default=84)
    init.add_argument("--steps", type=int, default=144)
    init.add_argument("--trees", type=int, default=120)
    generate = commands.add_parser("generate")
    generate.add_argument("--sessions", type=int, default=84)
    generate.add_argument("--steps", type=int, default=144)
    generate.add_argument("--output", default="data/generated")
    fit = commands.add_parser("train")
    fit.add_argument("--data", default="data/generated")
    fit.add_argument("--trees", type=int, default=120)
    fit.add_argument("--track", action="store_true")
    sh = commands.add_parser("shadow")
    sh.add_argument("version")
    sh.add_argument("--data", default="data/generated/solar.csv")
    promotion = commands.add_parser("promote")
    promotion.add_argument("version")
    commands.add_parser("rollback")
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    sim = commands.add_parser("simulate")
    sim.add_argument("--url", default="http://127.0.0.1:8000")
    sim.add_argument("--scenario", default="scenarios/interview.yaml")
    sim.add_argument("--run-dir")
    sim.add_argument("--steps", type=int)
    rep = commands.add_parser("replay")
    rep.add_argument("path")
    rep.add_argument("--url", default="http://127.0.0.1:8000")
    live = commands.add_parser("demo")
    live.add_argument("--port", type=int, default=8000)
    live.add_argument("--scenario", default="scenarios/interview.yaml")
    serial = commands.add_parser("serial")
    serial.add_argument("--port", required=True)
    serial.add_argument("--station", choices=["roof-east", "roof-west", "lab-panel"], default="roof-east")
    serial.add_argument("--protocol", choices=["nano-json", "data"], default="nano-json")
    serial.add_argument("--url", default="http://127.0.0.1:8000")
    serial.add_argument("--baud", type=int, default=115200)
    commands.add_parser("credentials")
    commands.add_parser("evaluate")
    benchmark = commands.add_parser("benchmark")
    benchmark.add_argument("--url", default="http://127.0.0.1:8000")
    benchmark.add_argument("--steps", type=int, default=20)
    backup = commands.add_parser("backup")
    backup.add_argument("destination")
    restore = commands.add_parser("restore")
    restore.add_argument("source")
    restore.add_argument("destination")
    args = parser.parse_args()
    settings = load_settings()
    if args.command == "setup":
        setup(args.sessions, args.steps, args.trees)
    elif args.command == "generate":
        from solarsense.data import generate_dataset

        generate_dataset(args.output, args.sessions, args.steps)
    elif args.command == "train":
        from solarsense.ml import train

        train(args.data, settings["models"], settings["root"] / "reports", args.trees, args.track)
    elif args.command == "shadow":
        from solarsense.ml import shadow

        print(json.dumps(shadow(settings["models"], args.version, args.data), indent=2))
    elif args.command in {"promote", "rollback"}:
        from solarsense.ml import promote

        print(promote(settings["models"], getattr(args, "version", None), args.command == "rollback"))
    elif args.command == "serve":
        import uvicorn
        from solarsense.api import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, workers=1)
    elif args.command == "simulate":
        from solarsense.simulator import simulate

        asyncio.run(simulate(args.url, args.scenario, args.run_dir, args.steps))
    elif args.command == "replay":
        from solarsense.simulator import replay

        replay(args.path, args.url)
    elif args.command == "demo":
        demo(args.port, args.scenario)
    elif args.command == "serial":
        from solarsense.serial_bridge import run_serial

        run_serial(args.port, args.station, args.protocol, args.url, args.baud)
    elif args.command == "credentials":
        print(json.dumps(settings["credentials"], indent=2))
    elif args.command == "evaluate":
        from solarsense.evaluation import evaluate

        print(json.dumps(evaluate(settings), indent=2))
    elif args.command == "benchmark":
        from solarsense.evaluation import benchmark

        print(json.dumps(benchmark(settings, args.url, args.steps), indent=2))
    elif args.command == "backup":
        from solarsense.db import backup_snapshot

        print(json.dumps(backup_snapshot(settings, args.destination), indent=2))
    elif args.command == "restore":
        from solarsense.db import restore_snapshot

        print(restore_snapshot(args.source, args.destination))


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    main()
