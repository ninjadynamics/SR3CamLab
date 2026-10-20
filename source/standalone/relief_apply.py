"""Transactional Mountain relief Apply backend. Never launches the game."""
from pathlib import Path
import contextlib
import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from pom_native_config import load, material_settings, sha

ROOT = Path(__file__).resolve().parents[2]
MAIN = "desert4_master_gfx_xdata.sbf"
TRACK = "Main_release/track1/Desert4/" + MAIN
LIBRARY = "system/shaderlib3_uber_data.sbf"
YAML = "config/mountain-pom-depth.yaml"
RECEIPT = "config/pom-native-install.json"
BASELINE = "config/accepted-baseline.json"
JOURNAL = "config/pom-apply-pending.json"
INPUTS = "work/pom-native-inputs"

def atomic(path, data):
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists(): temp.unlink()

def dump(value):
    return (json.dumps(value, indent=2) + "\n").encode()

def revision(root=ROOT):
    return hashlib.sha256(b"".join((root / x).read_bytes() for x in (YAML, RECEIPT, BASELINE))).hexdigest()

def closed():
    result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Rally.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, check=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return '"rally.exe"' not in result.stdout.lower()

def allowed_variants(root=ROOT):
    inventory = json.loads((root / "scratchpad/pom-depth-tuner-20261020/inventory.json").read_text())
    current = load(root / YAML)
    return sorted({Path(n).stem.removesuffix("_dk") for x in inventory["items"]
                   if x["id"] in current["families"] for n in x["members"]})

def request_settings(payload, root=ROOT):
    """Only accept explicit settings, not client-provided paths or commands."""
    expected = {"revision", "families", "excluded_variants", "global_depth_initial", "live_tuner"}
    if set(payload) != expected: raise ValueError("Unexpected or missing Apply fields")
    if payload["revision"] != revision(root): raise ValueError("Settings changed elsewhere. Reload installed settings first.")
    config = load(root / YAML)
    gains = payload["families"]
    if not isinstance(gains, dict) or gains.keys() != config["families"].keys():
        raise ValueError("Texture families do not match this installed build")
    def number(n, high):
        return type(n) in (int, float) and math.isfinite(n) and 0 <= n <= high
    if not all(number(v, 12) for v in gains.values()):
        raise ValueError("Family depth must be between 0 and 12")
    g = payload["global_depth_initial"]
    if not number(g, 1) or abs(g * 10 - round(g * 10)) > 1e-6:
        raise ValueError("Global depth must be 0.0–1.0 in 0.1 steps")
    if type(payload["live_tuner"]) is not bool: raise ValueError("Invalid live tuning setting")
    variants = payload["excluded_variants"]
    if not isinstance(variants, list) or any(not isinstance(x, str) for x in variants):
        raise ValueError("Invalid exclusions")
    if not set(variants) <= set(allowed_variants(root)): raise ValueError("Unknown excluded variant")
    config.update(families=gains, excluded_variants=sorted(set(variants)),
                  global_depth_initial=f"{g:.1f}", live_tuner=str(payload["live_tuner"]).lower())
    return config

def yaml_text(config, root=ROOT):
    # Preserve comments and stable source paths; rewrite just editable fields.
    text = (root / YAML).read_text()
    lines = text.splitlines()
    result = []; in_families = False
    for line in lines:
        if line == "families:":
            in_families = True
            result.append(line)
            result.extend(f"  {k}: {v:g}" for k, v in config["families"].items())
        elif not in_families:
            key = line.split(":", 1)[0]
            if key == "excluded_variants": line = key + ": " + ",".join(config[key])
            elif key in ("global_depth_initial", "live_tuner"): line = key + ": " + config[key]
            result.append(line)
    return "\n".join(result) + "\n"

def checked_install(root, files, backup, is_closed=closed, replace=atomic):
    """Back up all members before mutation. Roll back on any copy/hash failure."""
    if not is_closed(): raise RuntimeError("Close the game before applying relief settings")
    backup.mkdir(parents=True, exist_ok=False)
    for rel in files:
        old = root / rel
        target = backup / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, target)
        assert sha(old) == sha(target)
    atomic(root / JOURNAL, dump({"backup": str(backup), "files": list(files)}))
    try:
        if not is_closed(): raise RuntimeError("Game started during preparation; nothing installed")
        for rel, source in files.items():
            if not is_closed(): raise RuntimeError("Game started during install; restoring previous files")
            replace(root / rel, Path(source).read_bytes())
            if sha(root / rel) != sha(source): raise RuntimeError("Installed file verification failed: " + rel)
    except BaseException:
        # Keep the journal if rollback itself fails: PLAY refuses a mixed install.
        for rel in files: atomic(root / rel, (backup / rel).read_bytes())
        (root / JOURNAL).unlink()
        raise
    (root / JOURNAL).unlink()

def apply(payload, progress=lambda message: None, root=ROOT, stage_only=False):
    cfg = request_settings(payload, root)
    if (root / JOURNAL).exists(): raise RuntimeError("An interrupted install needs recovery before Apply")
    if not closed(): raise RuntimeError("Close the game before applying relief settings")
    initial_revision = revision(root)
    baseline = json.loads((root / BASELINE).read_text())
    receipt = json.loads((root / RECEIPT).read_text())
    for name, value in baseline["files"].items():
        if sha(root / "game/Rally" / name) != value: raise RuntimeError("Installed file changed: " + name)
    inputs = root / INPUTS
    pins = json.loads((inputs / "pins.json").read_text())
    for name, value in pins.items():
        if sha(inputs / name) != value: raise RuntimeError("Rebuild source changed: " + name)
    run = root / "scratchpad/pom-apply" / (datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True)
    staged_yaml = run / "mountain-pom-depth.yaml"
    staged_yaml.write_text(yaml_text(cfg, root), encoding="utf-8")
    load(staged_yaml)
    changed = material_settings(cfg) != receipt["material_settings"]
    files = {YAML: staged_yaml}
    report = {}
    if changed:
        env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
        def run_command(args, label):
            progress(label)
            with (run / (label.split(":")[0].replace(" ", "-") + ".log")).open("w") as log:
                result = subprocess.run([sys.executable, *map(str, args)], cwd=root, env=env,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
            if result.returncode: raise RuntimeError(f"{label} failed. Logs: {run}")
        run_command([root / "source/standalone/stage_pom_wide.py", "--workspace", root,
            "--out", run / "maps", "--track-dir", inputs / "review-track",
            "--base-main", inputs / "clean-rt.sbf", "--tuning", staged_yaml],
            "Rebuilding maps: applying family depths and exclusions")
        run_command([root / "source/standalone/integrate_pom_library.py",
            "--source-library", inputs / "shaderlib3_uber_data.sbf",
            "--source-track", run / "maps" / MAIN, "--material-report", run / "maps/stage-report.json",
            "--texmap", inputs / "review-track/texmap.json", "--tuning", staged_yaml, "--out", run / "native"],
            "Preparing shaders: checking the rebuilt materials")
        if (run / "native/pom_native_layout.h").read_bytes() != (root / "source/standalone/pom_native_layout.h").read_bytes():
            raise RuntimeError("Native shader layout changed; runtime rebuild required before installation")
        files.update({"game/Rally/" + TRACK: run / "native" / MAIN,
                      "game/Rally/" + LIBRARY: run / "native/shaderlib3_uber_data.sbf",
                      RECEIPT: run / "native/pom-native-install.json"})
        report = json.loads((run / "native/stage-report.json").read_text())
        baseline["files"][TRACK] = sha(files["game/Rally/" + TRACK])
        baseline["files"][LIBRARY] = sha(files["game/Rally/" + LIBRARY])
    else:
        progress("Saving controls: material maps already match")
    if revision(root) != initial_revision: raise RuntimeError("Settings changed while rebuilding. No files installed.")
    if not closed(): raise RuntimeError("Game is running. Rebuild saved; close the game and Apply again.")
    backup = root / "work/pom-backups" / ("page-apply-" + run.name)
    baseline.setdefault("pom_native_library_update", {}).update(
        yaml_sha256=sha(staged_yaml), initial_depth=float(cfg["global_depth_initial"]),
        live_tuner=cfg["live_tuner"] == "true", last_page_apply=str(run), last_page_backup=str(backup),
        status="installed from Mountain relief page; gameplay check pending")
    staged_baseline = run / "accepted-baseline.json"; staged_baseline.write_bytes(dump(baseline))
    files[BASELINE] = staged_baseline
    if stage_only:
        return {"staged": True, "run": str(run), "material_rebuild": changed, "audit": report.get("material_audit")}
    progress("Installing: backing up and verifying the finished files")
    checked_install(root, files, backup)
    result = {"installed": True, "run": str(run), "backup": str(backup), "material_rebuild": changed,
              "revision": revision(root), "audit": report.get("material_audit"),
              "game_launched": False}
    (run / "install-report.json").write_bytes(dump(result))
    progress("Applied to game. Ready for your next launch.")
    return result
