"""Build the Daytona USA (original Model 2, MAME set `daytona`) region images from the unpacked ROM chips.
Layout taken from MAME model2.cpp ROM_START( daytona ): every pair is ROM_LOAD32_WORD (two 16-bit chips make
one little-endian 32-bit word; the first chip is the low half).

    python daytona_build.py --source model2 --input daytona.zip --export all
    python daytona_build.py --source ps3 --input Daytona.pkg --export all

The no-argument command uses config/import.json (Model 2 by default). See README.md.

Regions written to <scratch>/daytona/out/ :
    maincpu.bin    0x040000  i960 program            (mapped at 0x00000000; second half also at 0x00220000)
    main_data.bin  0x900000  main data ROM           (mapped at 0x02000000)
    copro_data.bin 0x400000  coprocessor data ROM
    polygons.bin   0x1000000 polygon ROM             (geometry engine address 0x800000 | word index)
    textures.bin   0x1000000 "texture" ROM           (texture coordinate lists and texture headers, 16-bit words)
"""
import os
import numpy as np
from daytona_paths import ROMS, OUT

SETS = {
    "maincpu":    (0x040000,  [(0x000000, "epr-16722a.12", "epr-16723a.13")]),
    "main_data":  (0x900000,  [(0x000000, "mpr-16528.10", "mpr-16529.11"),
                               (0x400000, "mpr-16808.8", "mpr-16809.9"),
                               (0x800000, "epr-16724a.6", "epr-16725a.7")]),
    "copro_data": (0x400000,  [(0x000000, "mpr-16537.28", "mpr-16536.29")]),
    "polygons":   (0x1000000, [(0x000000, "mpr-16523.16", "mpr-16518.20"),
                               (0x400000, "mpr-16524.17", "mpr-16519.21"),
                               (0x800000, "mpr-16525.18", "mpr-16520.22"),
                               (0xC00000, "mpr-16772.19", "mpr-16771.23")]),
    "textures":   (0x1000000, [(0x000000, "mpr-16522.25", "mpr-16521.24"),
                               (0x800000, "mpr-16770.27", "mpr-16769.26")]),
}


def load32(pairs, size):
    buf = np.zeros(size // 2, dtype="<u2")
    for off, lo, hi in pairs:
        a = np.fromfile(os.path.join(ROMS, lo), dtype="<u2")
        b = np.fromfile(os.path.join(ROMS, hi), dtype="<u2")
        buf[off // 2: off // 2 + 2 * len(a): 2] = a
        buf[off // 2 + 1: off // 2 + 1 + 2 * len(b): 2] = b
    return buf


def main():
    import argparse, hashlib, json, subprocess, sys, zipfile
    from pathlib import Path
    from daytona_paths import ZIP, SCRATCH, COURSES
    from common import SETTINGS
    ap = argparse.ArgumentParser(description="Extract Daytona USA from Model 2 ROMs or the verified PS3 PSN package.")
    ap.add_argument('--source', choices=('model2', 'ps3'), default=SETTINGS.get('daytona_source', 'model2'))
    ap.add_argument('--input', help='Model 2 ZIP/chip directory, or PS3 PKG/rom.psarc/extracted directory')
    ap.add_argument('--scratch', default=SCRATCH, help='Disposable extraction workspace (regions go in out/)')
    ap.add_argument('--courses', default=COURSES, help='Destination for exported cars and courses')
    ap.add_argument('--export', choices=('all', 'cars', 'tracks'), help='Also export OBJ/PNG assets using the existing decoders')
    args = ap.parse_args()
    if args.source not in ('model2', 'ps3'): ap.error('Invalid daytona_source in config/import.json')
    source = args.input or (SETTINGS.get('daytona_ps3') if args.source == 'ps3' else (ROMS if os.path.isdir(ROMS) else ZIP))
    if not source: ap.error('PS3 source missing: pass --input or set daytona_ps3 in config/import.json')
    try:
        if args.source == 'ps3':
            from daytona_ps3 import build_regions
            regions = build_regions(source)
        else:
            source = Path(source)
            archive = zipfile.ZipFile(source) if source.is_file() else None
            try:
                def chip(name): return archive.read(name) if archive else (source/name).read_bytes()
                regions = {}
                for name, (size, pairs) in SETS.items():
                    buf = bytearray(size)
                    for off, lo, hi in pairs:
                        a, b = chip(lo), chip(hi)
                        if len(a) != len(b) or len(a) % 2 or off + 2*len(a) > size:
                            raise ValueError('Invalid ROM chip size: ' + lo)
                        buf[off:off+len(a)*2:4] = a[::2]; buf[off+1:off+len(a)*2:4] = a[1::2]
                        buf[off+2:off+len(b)*2:4] = b[::2]; buf[off+3:off+len(b)*2:4] = b[1::2]
                    regions[name] = bytes(buf)
            finally:
                if archive: archive.close()
        # Validate the whole source before changing any generated region files.
        out = Path(args.scratch).resolve()/'out'; out.mkdir(parents=True, exist_ok=True)
        for name, data in regions.items():
            target = out/(name+'.bin'); tmp = out/(name+'.bin.tmp')
            tmp.write_bytes(data); os.replace(tmp, target)
            print('%s: %d bytes' % (target.name, len(data)), flush=True)
        manifest = dict(source=args.source, input=str(Path(source).resolve()),
                        regions={n: dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest()) for n,b in regions.items()})
        (out/'source.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        if args.export:
            env = dict(os.environ, DAYTONA_SCRATCH=str(Path(args.scratch).resolve()), DAYTONA_COURSES=str(Path(args.courses).resolve()), PYTHONDONTWRITEBYTECODE='1')
            here = Path(__file__).parent
            jobs = []
            if args.export in ('all', 'cars'): jobs.append(('daytona_cars.py',))
            if args.export in ('all', 'tracks'):
                jobs.append(('daytona_export.py', 'all'))
                for course in ('beginner', 'advanced', 'expert'):
                    jobs.extend([('daytona_course.py', course), ('daytona_collision.py', course)])
            for script, *params in jobs:
                subprocess.run([sys.executable, '-B', str(here/script), *params], env=env, check=True)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        ap.exit(1, 'Daytona extraction failed: %s\n' % exc)


if __name__ == "__main__":
    main()
