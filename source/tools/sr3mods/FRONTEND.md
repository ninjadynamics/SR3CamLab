# Frontend expansion: component checkpoint

This is unfinished source work, not an installed feature. The normal game and
accepted Mountain build are unchanged. No game was launched for these checks.

The components cover a 64-record native video-pool relocation, lazy preview
registration and decoder cleanup, a shared installed-track catalog, and a menu
model for Quick Race and Classic game/track navigation. UI identities remain
separate from the game's six native track IDs and slot/directory routing.

Remaining integration includes the in-game renderer, input/state hooks,
selection acknowledgment by the track-routing worker, and real decoder/menu
validation. The original boot video preload is still present. None of these
components is linked into the shipping plugin yet.

Run the component checks from the repository root:

```powershell
python -B source/tools/sr3mods/test_frontend.py --out scratchpad/frontend-tests
```

The suite builds isolated x86 tests with their own import libraries, checks
byte guards and partial-write rollback, exercises video lifetime and menu
navigation, replays the actual executable's pool initialization/allocation/
destruction under emulation, and tests catalog generation. It does not establish
live COM/decoder or visual correctness. The emulator requires the local game
executable; that executable is not included in this source checkpoint.
