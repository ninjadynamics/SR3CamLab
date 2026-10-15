"""Create a separate SR3 game folder. The source folder is never modified.

python overlay.py SOURCE DESTINATION [--mode copy|hardlink|junction]
SOURCE is Rally.exe or the folder containing it. DESTINATION must not exist.
Copy is fully independent. Link modes share only asset directories; materialize
them with --materialize DESTINATION before using tools that edit game assets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent
EXE_SHA256 = "8eb7bdf01b8dc30ba40a43ac3d4065b9035cc59d58dd01b3c03113a1403171b5"
MARKER = "sr3lab-overlay.json"

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def inside(path, parent):
    return path == parent or parent in path.parents

def junction(path, target):
    # Literal PowerShell parameters, no interpolated shell commands.
    script = "New-Item -ItemType Junction -Path $env:SR3_LINK_PATH -Target $env:SR3_LINK_TARGET -ErrorAction Stop | Out-Null"
    env = dict(os.environ, SR3_LINK_PATH=str(path), SR3_LINK_TARGET=str(target))
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, check=True)

def create(source, destination, mode="copy", dll=None):
    source = source.resolve()
    if source.is_file():
        source = source.parent
    destination = destination.absolute()
    resolved = destination.resolve()
    dll = (dll or ROOT / "build/native/dinput8.dll").resolve()
    exe = source / "Rally.exe"
    if not exe.is_file() or digest(exe) != EXE_SHA256:
        raise ValueError("Requires Rally.exe 3.8.4.1 with the supported SHA-256; no executable was changed.")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination must not exist. Existing folders are never overwritten.")
    if inside(resolved, source) or inside(source, resolved):
        raise ValueError("Source and destination must be separate, non-nested folders.")
    if (source / "dinput8.dll").exists():
        raise ValueError("Source already has a dinput8.dll. Use an unmodified source folder; proxy chaining is not implicit.")
    if not dll.is_file():
        raise ValueError("Build dinput8.dll first with build.py.")
    sdl_license = dll.parent / "SDL-LICENSE.txt"
    if not sdl_license.is_file():
        raise ValueError("SDL-LICENSE.txt missing beside DLL. Run build.py to complete the build.")
    companions = ['launch.exe', 'settings.exe', 'raylib-LICENSE.txt']
    for name in companions:
        if not (dll.parent / name).is_file():
            raise ValueError(f'{name} is missing. Run build.py and build_companion.py first.')
    if mode not in {"copy", "hardlink", "junction"}:
        raise ValueError("Unknown overlay mode.")
    # Reparse points could refer outside the selected source or form loops.
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            p = Path(directory) / name
            if p.is_symlink() or getattr(p.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Source contains a reparse point: {p}. Supply a concrete game folder.")
    destination.mkdir(parents=True)
    manifest = {"format": 1, "source": str(source), "mode": mode,
                "exe_sha256": EXE_SHA256, "assets": [], "complete": False}
    marker = destination / MARKER
    marker.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            manifest["assets"].append(entry.name)
            if mode == "junction":
                junction(target, entry)
            else:
                shutil.copytree(entry, target, copy_function=os.link if mode == "hardlink" else shutil.copy2)
        elif entry.name.lower() not in {"teknoparrot.ini", "inpout32.dll", "inpout32_d.dll"}:
            # Root files, including the executable, configs and DLLs, are always private copies.
            shutil.copy2(entry, target)
    save = destination / "SR3LabSave"
    save.mkdir(exist_ok=True)
    for name in ("HighScoreData.txt", "HighScoreCounter.txt"):
        candidates = [source / "ShellData" / name, source.parent / "ShellData" / name, source / name]
        existing = next((p for p in candidates if p.is_file()), None)
        if existing:
            shutil.copy2(existing, save / name)
    shutil.copy2(dll, destination / "dinput8.dll")
    shutil.copy2(ROOT / "sr3lab.ini", destination / "sr3lab.ini")
    shutil.copy2(ROOT / "settings.yaml", destination / "settings.yaml")
    for name in companions:
        shutil.copy2(dll.parent / name, destination / name)
    shutil.copy2(ROOT.parent / "LICENSE", destination / "SR3Lab-LICENSE.txt")
    shutil.copy2(sdl_license, destination / "SDL-LICENSE.txt")
    (destination / "PLAY-STANDALONE.bat").write_text(
        '@echo off\ncd /d "%~dp0"\nstart "" "%~dp0launch.exe"\n', encoding="ascii")
    manifest["complete"] = True
    manifest["runtime_sha256"] = digest(destination / "dinput8.dll")
    marker.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

def materialize(destination):
    """Replace linked asset directories with private copies before editing them."""
    destination = destination.resolve()
    marker = destination / MARKER
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("format") != 1 or not data.get("complete"):
        raise ValueError("Not a complete SR3Lab overlay.")
    if data["mode"] == "copy":
        return
    # Verify the entire path set before any mutation; only direct child asset directories are accepted.
    for name in data["assets"]:
        if Path(name).name != name or name in ("", ".", "..") or "/" in name or "\\" in name:
            raise ValueError("Invalid asset directory in overlay manifest.")
    for name in data["assets"]:
        target = destination / name
        temporary = destination / (".sr3lab-copy-" + uuid.uuid4().hex)
        shutil.copytree(target, temporary)
        if data["mode"] == "junction":
            # os.rmdir removes the junction itself, never its target.
            if not getattr(target.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Expected junction: {target}")
            os.rmdir(target)
        else:
            # Resolved path is constrained to the verified overlay before recursive deletion.
            if target.is_symlink() or target.resolve().parent != destination:
                raise ValueError("Asset path escaped overlay.")
            shutil.rmtree(target)
        temporary.rename(target)
    data["mode"] = "copy"
    marker.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("destination", type=Path, nargs="?")
    parser.add_argument("--mode", choices=["copy", "hardlink", "junction"], default="copy")
    parser.add_argument("--dll", type=Path)
    parser.add_argument("--materialize", type=Path)
    args = parser.parse_args()
    try:
        if args.materialize:
            materialize(args.materialize)
            print("Assets are now private copies.")
        elif args.source and args.destination:
            create(args.source, args.destination, args.mode, args.dll)
            print(f"Ready: {args.destination / 'PLAY-STANDALONE.bat'}")
        else:
            parser.error("Supply SOURCE and DESTINATION, or --materialize DESTINATION.")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error

if __name__ == "__main__":
    main()
