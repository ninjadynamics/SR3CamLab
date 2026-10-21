"""One short-lived PLAY broker: validate relief, start hidden helpers and launch.

No game launch occurs with --check. Content hashes come only from the current
PowerShell preflight; no persistent/mtime cache. Popen waits for launch.exe itself,
not its Rally descendant. Helpers retain their own log handles after this exits.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time

STANDALONE = Path(__file__).resolve().parents[2] / "standalone"
sys.path.insert(0, str(STANDALONE))
from pom_native_config import verify


def local_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Workspace path escapes its root")
    return path


def hidden_options():
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": si}


def run_session(workspace, *, settings=None, run=None, preflight=None, check=False):
    root = Path(workspace).resolve()
    preflight = preflight or {}
    start = time.perf_counter()
    timing = {
        "version": 1,
        "play_started_utc": preflight.get("started_utc"),
        "broker_started_utc": datetime.now(timezone.utc).isoformat(),
        "preflight_ms": preflight.get("elapsed_ms"),
        "preflight_phases_ms": preflight.get("phases_ms", {}),
        "phases_ms": {},
        "game_started": False,
    }
    helpers = []
    run_path = None

    def mark(name):
        timing["phases_ms"][name] = round((time.perf_counter() - start) * 1000, 3)

    try:
        cfg = json.loads(local_path(root, "config/workspace.json").read_text(encoding="utf-8-sig"))
        baseline = json.loads(local_path(root, cfg["baseline"]).read_text(encoding="utf-8-sig"))
        game = local_path(root, cfg["game"])
        yaml = local_path(root, settings or cfg["settings"])
        candidate = local_path(root, cfg["candidate"]) if cfg.get("candidate") else None
        host = local_path(root, "source/tools/handling/candidate_host.py")
        recorder = local_path(root, "source/tools/handling/record_steering.py")
        launcher = local_path(root, "apps/runtime/launch.exe")
        if cfg.get("pom") and baseline.get("pom_native_library_update"):
            verify(root, verified_files=preflight.get("verified_files"))
        mark("relief_verified")
        if check:
            return timing
        if not run:
            raise ValueError("A run directory is required for launch")
        requested_run = local_path(root, run)
        # PLAY creates a unique run directory before any helper is allowed to start.
        if not requested_run.is_dir():
            raise ValueError("Run directory is missing")
        run_path = requested_run
        env = dict(os.environ, SR3LAB_POM="1" if cfg.get("pom") else "0")
        options = dict(cwd=str(root), env=env, stdin=subprocess.DEVNULL, close_fds=True, **hidden_options())
        with ExitStack() as logs:
            if candidate:
                commands = [
                    ("candidate", [cfg["python"], "-B", str(host), "--candidate", str(candidate),
                                   "--game", str(game), "--out", str(run_path / "candidate.csv")]),
                    ("recorder", [cfg["python"], "-B", str(recorder), "--out", str(run_path / "steering.csv"),
                                  "--seconds", "180"]),
                ]
                for name, command in commands:
                    stdout = logs.enter_context((run_path / (name + ".log")).open("wb"))
                    stderr = logs.enter_context((run_path / (name + ".err")).open("wb"))
                    helpers.append(subprocess.Popen(command, stdout=stdout, stderr=stderr, **options))
                    mark(name + "_spawned")
            process = subprocess.Popen([str(launcher), "--settings", str(yaml), "--no-watchdog"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
            mark("launcher_spawned")
            code = process.wait()
            mark("launcher_returned")
            if code:
                raise RuntimeError(f"Game launcher failed ({code})")
            timing["game_started"] = True
        print(f"Ultimate Race Lab launched. SRC helper enabled: {bool(candidate)}. Records: {run_path}")
        return timing
    except BaseException as exc:
        timing["error"] = str(exc)
        # Only processes created by this failed invocation are stopped.
        for process in helpers:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
        raise
    finally:
        mark("broker_finished")
        if run_path is not None:
            target = run_path / "launch-timing.json"
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, target)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--settings", type=Path)
    ap.add_argument("--run", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    # JSON is piped, not interpolated into a shell command. These are freshly
    # measured hashes, not trusted manifest assertions or an on-disk cache.
    preflight = json.load(sys.stdin)
    run_session(args.workspace, settings=args.settings, run=args.run,
                preflight=preflight, check=args.check)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"PLAY startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
