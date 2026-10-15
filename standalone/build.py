"""Build the x86 runtime from source; SDL is pinned and linked statically.

python build.py [--sdl-source PATH] [--generator "Visual Studio 16 2019"]
Requires CMake, Git (only to fetch SDL), and Visual Studio C++ x86 build tools.
The source cache can be supplied offline. No game files are needed to build.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
SDL_TAG = "release-3.4.16"
SDL_COMMIT = "fa2c02bb6e21974a89ea9824bc53c9932abe5f9c"

def run(*args):
    subprocess.run([str(a) for a in args], check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdl-source", type=Path, default=ROOT / "deps" / "SDL")
    parser.add_argument("--generator")
    args = parser.parse_args()
    source = args.sdl_source.resolve()
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--depth", "1", "--branch", SDL_TAG,
            "https://github.com/libsdl-org/SDL.git", source)
    if not (source / "CMakeLists.txt").is_file():
        raise SystemExit(f"Not an SDL source tree: {source}")
    if not (source / ".git").exists():
        raise SystemExit("Use the pinned SDL Git checkout (it can be copied here offline).")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != SDL_COMMIT:
        raise SystemExit(f"SDL revision mismatch: expected {SDL_COMMIT}, got {revision}")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise SystemExit("SDL source cache has local modifications; use a clean pinned checkout.")
    generator = args.generator
    if not generator:
        vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio/Installer/vswhere.exe"
        if not vswhere.is_file():
            raise SystemExit("Install Visual Studio C++ Build Tools with x86 support, or pass --generator explicitly.")
        installs = json.loads(subprocess.check_output([str(vswhere), "-latest", "-products", "*", "-requires",
                              "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-format", "json"], text=True))
        if not installs:
            raise SystemExit("Visual Studio x86 C++ tools were not found.")
        major = int(installs[0]["installationVersion"].split(".")[0])
        generator = {16: "Visual Studio 16 2019", 17: "Visual Studio 17 2022", 18: "Visual Studio 18 2026"}.get(major)
        if not generator:
            raise SystemExit("Unknown Visual Studio generation; pass --generator.")
    build = ROOT / "build"
    run("cmake", "-S", ROOT, "-B", build, "-G", generator, "-A", "Win32", f"-DSDL_SOURCE={source.as_posix()}")
    run("cmake", "--build", build, "--config", "Release", "--parallel", "1")
    run("ctest", "--test-dir", build, "-C", "Release", "--output-on-failure")
    shutil.copy2(source / "LICENSE.txt", build / "Release" / "SDL-LICENSE.txt")
    print(f"Built {build / 'Release' / 'dinput8.dll'}")

if __name__ == "__main__":
    main()
