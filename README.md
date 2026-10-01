# SR3CamLab

**A chase camera that swings into the slide for SEGA Rally 3 (arcade, via TeknoParrot), the
game's hidden debug cameras, and a little app to tune it all.**

*by Ninja Dynamics*

![CamLab](res/camlab.png)

SEGA Rally 3's chase camera sits locked behind the bumper like a GoPro on a stick. This mod
gives it a camera that swings out when you slide, so in a drift you see the car sideways,
and more:

- **Your own chase cameras.** Camera profiles with travel follow, spring, angle limit and
  framing (distance, height, field of view), switchable in the race with View Change.
- **The cameras SEGA hid.** Cockpit (plus a driver's-seat version), wheel, far chase, an
  orbiting car rotate cam and two free-flying cams, steered with mouse and keyboard.
- **Fixes.** Scenery no longer pops in and out for high or roaming cameras, your camera
  stays picked between stages, and the game no longer runs out of memory on modern
  many-core CPUs ("Out of memory for VB" / white-screen freeze, a bug in the original game).
- **Nothing on disk changes.** The patch works on the running game's memory only. Close the
  game and everything is stock again.
- **CamLab** (`camlab.exe`): a driving playground with the same camera model, to tune
  profiles with sliders and launch the game with them. See [CAMLAB.md](CAMLAB.md).

## Requirements

- Windows 10 or 11 (uses the built-in Windows PowerShell 5.1).
- **SEGA Rally 3 (arcade), `Rally.exe` v3.8.4.1, set up in TeknoParrot** with the game
  profile `SR3.xml`. The game is not included. The patch checks every byte it touches and
  refuses any other version.

## Install

Download the latest zip from [Releases](https://github.com/ninjadynamics/SR3CamLab/releases)
(it includes `camlab.exe`) and unzip the `SR3CamLab` folder **inside your TeknoParrot
folder**, next to `TeknoParrotUi.exe`:

```
TeknoParrot\
├── TeknoParrotUi.exe
├── UserProfiles\SR3.xml
└── SR3CamLab\
    ├── PLAY.bat          start the game with the mod
    ├── patch.ps1         the live patcher
    ├── profiles.yaml     your camera profiles (the game and CamLab share them)
    ├── defaults.yaml     factory profiles (don't edit)
    └── camlab.exe        the tuning app (from the release, or build it: see CAMLAB.md)
```

## Play

Double-click **`PLAY.bat`**. It starts the game through TeknoParrot, waits for it to boot and
then patches it (about 20 s). Keep its window open; it says **ACTIVE** when done.

```
PLAY.bat                    the default profile
PLAY.bat Drone              a profile by name
PLAY.bat "SR3 Chase"        SEGA Rally 3's own chase camera ("SR3 Chase Far": its far one)
PLAY.bat Drone -Overlay 64  bigger camera names (0 = none)
PLAY.bat -Cores 0           don't limit the game's CPU threads (see below)
```

**In a race, View Change cycles through every camera.** Its name shows for 2 seconds:

| Group | Cameras | Name |
|---|---|---|
| Game | Chase, Bumper, Bonnet | white, "Game: Chase cam" |
| CamLab | each of your profiles | lime, "CamLab: Daytona" |
| Debug | Chase cam far, Cockpit cam, Cockpit cam (patched) = driver's seat, Wheel cam, Car rotate cam, Free cam, Car free cam | orange, "Debug: Free cam" |

**Steering the debug cameras** (while one is on screen):

- **Car rotate cam:** mouse left/right orbits the car, forward/back tilts, W/S zoom.
- **Free cam, Car free cam:** mouse looks around, WASD moves, Space/Ctrl up and down.
- **`~`** (the key below Esc) resets them.

**Turning it off:** start the game normally from TeknoParrot.

**Switching live** while the game runs (from the `SR3CamLab` folder):

```
powershell -ExecutionPolicy Bypass -File patch.ps1 Daytona -NoLaunch -DelaySeconds 0
powershell -ExecutionPolicy Bypass -File patch.ps1 -List
powershell -ExecutionPolicy Bypass -File patch.ps1 -Off -NoLaunch
```

**About `-Cores`:** the game keeps every video it plays loaded, and Windows' video decoder
starts one thread per CPU core for each. On a 32-thread CPU that fills the 32-bit game's 4 GB
and it crashes. `PLAY.bat` lets the game use 4 CPU threads, which halves the cost (the game
itself only needs one).

## Profiles

`profiles.yaml` is plain YAML; CamLab edits it for you. Settings at the top:

```yaml
default: Daytona     # the profile PLAY.bat starts on
overlay: 48          # camera name size in px at 1080p (0 = off)
hiddenCameras: true  # include the debug cameras in View Change
speedUnits: km/h     # CamLab's speedometer
```

Each profile sets `strength`, `fadeInStartKmh`, `fadeInFullKmh`, `stiffnessMin`,
`stiffnessMax`, `damping`, `maxAngle`, `capStiffness` and, optionally, `distance`, `height`,
`fov`. [CAMLAB.md](CAMLAB.md) explains each one.

## More

- [CAMLAB.md](CAMLAB.md): CamLab, the profile format, the camera model, building from source.
- [FINDINGS.md](FINDINGS.md): everything learned about `Rally.exe` along the way (addresses,
  structures, hidden cameras, the memory bug), for modders.
- [tools/](tools/README.md): the patch's assembly sources, its tests, and the scripts used to
  investigate the game.

## Disclaimer

Above all, this is a personal project: I love SEGA Rally 3, but I always hated its camera.
So I fixed it, and it grew from there.

It's a fan project, not affiliated with or endorsed by SEGA or TeknoParrot, and you need your
own copy of the game. The patch only changes the running game's memory, and only after
checking that it's the exact version it was made for. Beyond that, no promises: it works on
my machine™.

## License

[MIT](LICENSE) © Ninja Dynamics
