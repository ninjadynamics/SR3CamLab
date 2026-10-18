# Daytona extraction: Model 2 or PS3

Run from the Ultimate Race Lab root, using the project's Python environment
(numpy, Pillow and matplotlib are needed for the existing full asset exporter).

```powershell
python source/tools/import/daytona/tracks/rom/daytona_build.py --source model2 --input "path/to/daytona.zip" --export all
python source/tools/import/daytona/tracks/rom/daytona_build.py --source ps3 --input "path/to/Daytona.pkg" --export all
```

Both commands produce the same cars, course meshes, PNG textures, driving lines
and collision meshes through the shared Model 2 decoders. `--export cars` or
`--export tracks` limits the export; omit `--export` to prepare ROM regions only.
Nothing is installed into the running game.

PS3 inputs accepted:

- The verified NPUB30493 retail PSN `.pkg` (Windows; native system AES, no extra package dependency).
- Its extracted `USRDIR/ps3/rom.psarc` (all platforms).
- An extracted game directory containing that path, or a `daytona_rom` directory.

Raw `.iso` images are not supported. The owner's verified copy is a PSN package,
not a disc image. Other PS3 revisions fail with an explicit message before any
region outputs are written; support requires verifying their assets and layout.
No Model 2 ROMs are required for the PS3 path.

Defaults come from local `config/import.json`:

```json
{
  "daytona_source": "ps3",
  "daytona_ps3": "D:/path/to/Daytona.pkg"
}
```

`daytona_source` defaults to `model2`. The Model 2 path accepts a ZIP or unpacked
ROM chips, retaining the original no-argument workflow and configured ROM folder.
Command-line options override configuration. `--scratch` changes the region
workspace (`out/` beneath it); `--courses` changes the asset export destination.
Use these for comparisons without replacing your authored assets:

```powershell
python source/tools/import/daytona/tracks/rom/daytona_build.py --source ps3 --input "path/to/Daytona.pkg" --scratch scratchpad/daytona-test --courses scratchpad/daytona-test/assets --export all
```

`out/source.json` records provenance and region SHA-256 hashes. All extracted
SEGA data stays local, in content or scratchpad; it must never be committed.
Race Settings' extraction UI is still a separate TODO; this source option is
implemented in the importer CLI/configuration now.

## Validation

On 2026-10-18 both sources exported 2,475 files. 2,471 matched byte-for-byte:
135 OBJ, 2,174 PNG, 66 MTL, 27 CSV, and 69 JSON. The remaining four files record
source-dependent addresses (three placement reports) or output paths (cars.json).
Placement semantics and car metadata match after those fields are normalized.
All 63 exported car entries and all three courses were included.

Synthetic archive and AES tests (no SEGA data needed):

```powershell
python source/tools/import/daytona/tracks/rom/test_daytona_ps3.py
```

The PS3 program differs from the original program. Its placement data tables
move by 0x11DC; handler addresses are mapped individually. The geometry object
table, palette, luma and lighting tables used by the importer remain identical
at the original offsets. The PS3 texture ROM omits unused banks and its
coprocessor data omits the mirrored second half; the reader restores that
address layout for the existing decoders. Assets are hash-checked before use.
