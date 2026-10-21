"""YAML source-of-truth and installed native POM receipt validation (no game)."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import struct
import sys

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(path):
    config = {}
    gains = {}
    families = False
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line == "families:":
            assert not families, "Duplicate families"
            families = True
            continue
        if families:
            match = re.fullmatch(r"  ([A-Za-z0-9_]+): ([0-9.]+)", line)
            assert match, f"Invalid family setting: {line}"
            key, value = match.groups()
            assert key not in gains, f"Duplicate family {key}"
            value = float(value)
            assert math.isfinite(value) and 0 <= value <= 12
            gains[key] = value
        else:
            key, sep, value = line.partition(":")
            assert sep, f"Invalid setting: {line}"
            value = value.strip()
            assert key not in config, f"Duplicate {key}"
            config[key] = value
    assert config["version"] == "1" and gains
    depth = float(config["global_depth_initial"])
    assert math.isfinite(depth) and 0 <= depth <= 1
    assert abs(depth * 10 - round(depth * 10)) < 1e-6, "Global depth must use 0.1 steps"
    assert float(config["global_depth_min"]) == 0 and float(config["global_depth_max"]) == 1
    assert config["live_tuner"] in ("true", "false")
    assert config["fps_overlay"] == config["fps_measurement"] == "false"
    assert config["zero_depth"] == "native_shader_bypass"
    config["families"] = gains
    config["excluded_variants"] = sorted(set(v.strip() for v in config.get("excluded_variants", "").split(",") if v.strip()))
    return config

def material_settings(config):
    return {k: config[k] for k in ("normalization", "families", "excluded_variants", "height_directory", "review_export")}

def audit_materials(workspace, track_path, config, report_path, texmap_path):
    """Verify staged values against the YAML-built material report and recipe leaves."""
    sys.path.insert(0, str(Path(workspace) / "source/tools/import/core"))
    import sbfw
    report = json.loads(Path(report_path).read_text())
    assert report["family_gains"] == config["families"], "Family gains changed: restage with stage_pom_wide --tuning"
    metadata = json.loads(Path(texmap_path).read_text())
    aliases = metadata["engine_compaction"]["aliases"]
    facades = {x["name"]: x for x in metadata["facade_recipes"]}
    def leaves(name):
        if name in facades:
            return set().union(*(leaves(x["tile"]) for x in facades[name]["sources"]))
        if name in metadata["recipes"]:
            return leaves(metadata["recipes"][name][0]) | leaves(metadata["recipes"][name][1])
        if name in metadata["derived_recipes"]:
            return leaves(metadata["derived_recipes"][name]["background"])
        return {name.removesuffix("_dk")}
    records = {}
    for key, value in metadata["scenery"].items():
        seen = set()
        while key in aliases:
            assert key not in seen
            seen.add(key)
            key = str(aliases[key])
        records.setdefault(int(key), []).append(value)
    f = sbfw.read_sbf(str(track_path))
    by = f.byid()
    selected = {x["material"]: x for x in report["selected"]}
    excluded = set(config["excluded_variants"])
    active, disabled = [], []
    for c in f.kinds(2):
        if len(c.data) != 1848:
            continue
        rs = records.get(c.u32(0x1bc), [])
        skips = [bool(leaves(x["tile"]) & excluded) for x in rs]
        marked = c.f32(0x64c) == 1 / 1024 and c.f32(0x644) + c.f32(0x648) > 0
        if any(skips):
            assert all(skips), "Excluded variant shares a material with a non-excluded variant"
            assert not marked, f"Excluded material still has POM: {c.id}"
            disabled.append(c.id)
        elif c.id in selected:
            row = selected[c.id]
            assert marked and c.u32(0x1dc) == row["normal"], f"Missing/changed POM material {c.id}"
            expected = struct.pack("<ff", row["depth"], row["depth"])
            assert c.data[0x644:0x64c] == expected, f"Changed depth {c.id}"
            active.append(c.id)
        else:
            assert not marked, f"Unexpected POM material {c.id}"
    # No active material from the staging report may disappear silently.
    assert set(selected) <= set(active) | set(disabled)
    for tex in report["textures"].values():
        normal = by[tex["normal_id"]]
        assert hashlib.sha256(b"DDS " + normal.data[48:]).hexdigest() == tex["sha256"], "Height/normal payload changed"
    return {"active_materials": len(active), "excluded_materials": len(disabled),
            "excluded_material_ids": disabled, "families": len(config["families"])}

def verify(workspace, verified_files=None):
    """Check YAML/receipt; reuse only hashes computed by this same launch.

    The optional map is internal launcher input, never a disk/mtime cache.
    Standalone callers still hash every receipt file, and missing map entries
    fall back to a full content hash. Every digest is compared to the receipt.
    """
    r = Path(workspace)
    config = load(r / "config/mountain-pom-depth.yaml")
    receipt = json.loads((r / "config/pom-native-install.json").read_text())
    assert receipt["material_settings"] == material_settings(config), (
        "POM family values/exceptions changed. Restage maps with stage_pom_wide --tuning, "
        "then integrate_pom_library; installed maps must match YAML.")
    for name, value in receipt["files"].items():
        actual = (verified_files or {}).get(name)
        if actual is None:
            actual = sha(r / "game/Rally" / name)
        assert isinstance(actual, str) and re.fullmatch(r"[0-9a-fA-F]{64}", actual), "Invalid launch digest"
        assert actual.lower() == value.lower(), f"Native POM file changed: {name}"
    print(f"PASS native POM YAML: {len(config['families'])} families, exclusions match; "
          f"startup {config['global_depth_initial']}x, live tuner {config['live_tuner']}. No game launched.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True)
    a = ap.parse_args()
    verify(a.workspace)
