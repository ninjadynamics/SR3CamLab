# Native frontend expansion

The frontend extends SR3's own track-card scene and track selector. It uses the
existing page, card frames, fonts, carousel geometry and transitions. It does
not draw a separate menu or replace the game's renderer. The earlier custom
overlay experiment was rejected and removed.

Quick Race uses the installed-track catalog. Classic opens five source-game
choices, followed by tracks filtered to that game, then native car/transmission
selection. Missing/WIP entries cannot start a race. UI card identities resolve
to the game's six native track IDs and installed slot/directory pairs. The live
track worker acknowledges routing/audio/timing preparation before confirmation.

`config/frontend-tracks.json` enables the native extension. Generate it with
`source/standalone/frontend_catalog.py`; deleting/renaming that generated file
or setting `SR3LAB_FRONTEND=0` leaves the original menu flow in place on the
next launch. The catalog does not duplicate track assets. The 38-card native
scene bank currently holds tracks plus five game cards (33 track records max).
The relocated video pool has 64 records. New preview descriptors register at
scene construction. On entering a custom game or track menu, its decoders are
preloaded incrementally on the rendering thread and retained until the menu
changes; a preview not drawn for 750 ms then releases its graph, texture,
events and COM apartment on that thread. The sweep runs in the runtime's
per-frame callback, which stops when nothing requests it. Previously it
stopped with the menu, so a confirmed race loaded with every preview decoder
of that menu still open. The frontend now keeps requesting the callback after
its menus close until its decoders are released (about one second), for at
most 10 s, and logs each release and anything left open. Only records
registered for frontend cards are evicted. Native videos, including the
loading animation, keep their own lifetime: their widgets can issue playback
controls outside GetFrame. Dedicated game previews use
`URL_GAME_<source game>.wmv` when present; otherwise the catalog falls back to
an available track preview or the stock Classic preview. All five previews
carry their catalog title in white bottom right; the Daytona USA, Daytona USA 2,
Scud Race and SEGA Rally 2 ones are also dimmed 50% with a centred white SOON
(WMV2, `q:v 2`). The clean clips exist only in
`work/video-backups/videos-20261030-132458/`; the source captures are gone.
`classic_MTN.wmv` is 5 s of `work/video-backups/sources-20261030/mountain.mp4`
from 1.6 s with a 25% opaque MOUNTAIN scrolling left, off screen at both ends of
the loop; the same backup holds the earlier Mountain card.

A catalog `title` is the menu's display text. `LABELS` in `frontend_catalog.py`
overrides it by internal source id, so Mountain shows as SEGA Rally Championship -
Mountain while `switch.json`, `classic.json`, installers (which match a track by
title) and the tune lookup keep Mountain R4. The first menu's camera-box popup
reads `switch.json` and still says Classic: Mountain R4.

`sr3mods.log` records each choice: the chosen track with slot, folder and
native ID, its preparation by the track worker, confirmation and menu exits.
The load guard (`load_guard.c`, its own thread, not part of the lockstep live
loop) logs every race load (menus left, race running after N s, or back in the
menus). Quick Race loads have stalled with the loading screen up (2026-10-20,
before this frontend existed, and 2026-10-28), and quitting then left a
windowless process that fullscreen made unreachable. If the loading animation
is still on screen 150 s after the menus close (300 s without that evidence),
or the process is still alive 15 s after its window closed, the guard writes
`game/Rally/sr3lab-load-*.dmp` or `sr3lab-exit-*.dmp`: every thread's stack
and registers, modules, handles and the game's globals (data segments of
Rally.exe and our DLLs only). After a stuck exit it then ends the process.
At most two dumps per session; `SR3LAB_GUARD=0` disables it.
`minidump_threads.py <dump> --exe game/Rally/Rally.exe` lists each thread with
the Rally.exe return addresses on its stack.

The native page transition is asynchronous. Binding waits for the loaded
selector before consuming navigation, and cursor changes notify both the text
selector and 3D carousel. Classic reuses the loaded car page's native text
widgets while showing track cards; its hint is changed to Select Game/Track
and restored for actual car selection. The premature car-select voice callback
is suppressed until the real car page is entered. Leaving a submenu detaches
its selector without restoring hidden card nodes into the outgoing transition.

The native carousel places each card at index*spacing+phase and draws the
selected card last. Its reshuffle-path builder (`61D960`) gives a card a path
on one side of the centre only, so a jump of several cards from rest parks
every card crossing the centre in front of the moving cards, stationary until
its phase crosses zero: SEGA Rally 2 on Right from Scud Race, Daytona USA 2 on
Left from SEGA Rally Championship, and the same in Quick Race. The menus
therefore never ask for more than one card at a time. Wraps rotate the
intrusive card list by one: the covered card at the opposite end moves beside
the selection, and phase, target and selected index shift with the indices, so
no other card moves. The wrap is then the ordinary native one-card reshuffle
with textured videos. A rebuilt view starts at rest with its cursor's card
first and every path, position and foreground flag reset; returning to the
game list is not a jump either. Lists of one or two cards need no rotation.
The template, notifier and carousel-owner addresses are byte-guarded.

Each counted press moves one card immediately, as Quick Race always did; the
native reshuffle builds in-flight paths from the cards' current positions.
Only a wrap can wait: it moves the card at the opposite end of the list, so
it is held until the card in front is two past that card and covers it. That
never happens in lists of nine or more, briefly in five-card lists only while
mashing across the end, and longest (about 0.35 s) in three-card lists. A held
direction repeats (350 ms, then 120 ms) only while the cards are within one
card of the cursor and the next step is not waiting, so releasing coasts at
most about one card. Select behind a waiting step confirms the card it
reaches. A first attempt that paced every press to the animation was rejected
in game as unresponsive. These are offline replay results; acceptance is
Bruno's in-game test.

Short keyboard menu taps are retained for 80 ms in the runtime; this applies
to menu arrows/Start and does not pulse driving controls during a race. Modal
WM_KEYDOWN edges also survive asynchronous native menu polling. A keyboard
press therefore arrives as WM_KEYDOWN and as the polled level, in either order;
the two are paired within 150 ms and counted once. Gamepad presses use the
polled edge.

Native video Open creates a stopped graph. Lazy previews request the native
Run transition before their first frame; merely forcing an unpaused GetFrame
does not start a graph whose native state word already claims it is running.

Windowed live checks verified game-card browsing, titles/statuses, visible
previews, one-press SRC-to-Mountain selection and Back. Full race loading still
requires acceptance; component tests alone do not establish that outcome.
No track geometry, lighting, shader payload,
handling candidate or normal display setting is changed by this extension.

Run the component checks from the repository root:

```powershell
python -B source/tools/sr3mods/test_frontend.py --out scratchpad/frontend-tests
```

The suite builds isolated x86 tests with their own import libraries, checks
byte guards and partial-write rollback, exercises video lifetime, native scene
list reordering/restoration, held-button debounce and navigation, replays the
actual executable's pool initialization/allocation/destruction and native card
constructor/lookup/name builder, replays the actual carousel selection,
reshuffle paths, phase update and painter order for both wraps and paced
taps/holds/reversals, runs the load guard in its own test process (stalled
load, stuck exit, normal quit; dumps parsed back), and tests catalog
generation. The emulators
require the local game executable, which is not included in this source tree.
