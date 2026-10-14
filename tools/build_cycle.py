"""Builds the 'camera cycle + name popup + free-camera controls' block for SEGA Rally 3
(Rally.exe v3.8.4.1).

The block is allocated by patch.ps1 inside the running game (VirtualAllocEx) and is
position-independent: code finds its own base with call/pop. Layout (offsets from base):

  0x000  data (settings, state, strings, per-slot names, colours and camera parameters)
  0x1000 code: DRAW (Present hook) and LOST (device-lost hook)
  0x2000 game cameras (names, list entries, offsets, extras, colours) and the driver-seat
         copy of the cockpit cam's eye
  0x2280 smoothing and blend: settings, then their state (zero in a new block, never copied from an older one)
  0x2400 scratch strings of the track switcher (patch.ps1)
  0x2800 second code area: constants (0x70 bytes), then the smoothing of the steerable cameras' mouse and keys
         and the blend between cameras (BLEND, the third hook)

Hooks (5-byte call rel32, written by patch.ps1):
  0x591C4D  mov eax,[0x7ED10C]  (just before EndScene/Present)  -> call DRAW
  0x591B01  call 0x591220       (frees D3D resources before Reset) -> call LOST
  0x5C948C  call 0x5F1690       (the cameras' state of this drawn frame) -> call BLEND, which calls it first

Game facts used (found in the disassembly):
  [0x9EB4EC] + 0x18 = camera manager of the local player; [mgr+0] = frame time (float)
  mgr+0x510 chase camera (vtable 0x6EB808), mgr+0x8C4 far chase (vtable 0x6EB8B8)
  mgr+0x190 = the camera in use (more exactly the camera asked for: see "How a camera reaches the screen")
  race camera list: count mgr+0x22C, index mgr+0x230, camera pointers from mgr+0x234 (max 21)
    View Change does index = (index + 1) % count; a pointer equal to the current camera keeps it
  developer camera inputs, never written by the arcade game: floats mgr+0x1A8..0x1C4
    Car rotate cam (mgr+0xEEC): 1A8 orbit (x dt x pi/2), 1AC tilt, 1B8 / 1BC (x dt x 10)
    Free cams (mgr+0xC78, mgr+0x1D68): 1A8 yaw, 1AC pitch, 1C4 roll (x cam+0x230),
                                        1B0 / 1B4 move, 1B8 up/down
  [0x7ED10C] IDirect3DDevice9*, [0x7EDB74] present parameters (back buffer width, height),
  [0xA339A4] the game window
  Car rotate cam: the game adds the inputs to distance (+0x20) and height (+0x48) offsets with
  no limit, on top of the base distance / height at [[mgr+0x50C]] / [[mgr+0x50C]+4]; held
  W/S or mouse would drive the camera through the car or out of the stage. The block clamps
  base + offset to K_RDMIN..K_RDMAX and K_RHMIN..K_RHMAX before the game applies them.
  Menu videos (stage and car cards): table of 18 x (name, file, per-language flag, handle) at
             0x728630; 0x621600 loads every entry whose handle is -1 (except LOADING_TEXTURE),
             0x61C2C0 looks a video up by name and returns the table's handle. The track switcher
             in patch.ps1 points an entry at another file, sets its handle to -1 and LOADVIDEOS
             to 1; the block then calls 0x621600 on the game's own thread, once.
             The game has 20 video objects (0x16C bytes each at 0xAD2F90) and uses 18, and never
             frees one. REOPEN = handle + 1 has the block close that object's video (stop the
             graph [+0x120] IMediaControl, release [+0x11C..0x12C] and the texture [+0x144]) and
             open the file at REOPENPATH in its place (0x4DDC80: ecx = path, edi = object), then
             start it the way the loader does. That is how a stage card shows another track.
  HILITE:    the track id the stage selector is on, -1 when there is none: what the game itself
             asks when a stage is confirmed (0x6669C0): 0x606490 with edi = the hash (0x5470D0)
             of "ID_SELECTOR_TRACKSELECT" (0x6E53FC), guarded by [0x9C0F48].
  MODESEL:   the same question for "ID_SELECTOR_MODESELECT" (0x6E5E14): what the first menu
             (Championship / Quick Race / Classic) is on, -1 when there is none.
  CARSEL:    the same for the car select "ID_SELECTOR_CARSELECT" (lookup2 hash 0x6EACE04A, given as is): the highlighted
             car's id (its library id: the highlighted entry's data, 0x606510 as the confirm does; 0x606490 gives its place), -1 when there is none (patch.ps1, the handling keys).
  PHINT: when not 0, the text of the popup's second line (instead of the built-in hint).
  [0xA65794] PVS off: the scene manager's visibility refresh (0x500EA0) marks every node
             visible instead of using the camera's BSP leaf. The PVS is built for eyes near
             the road, so higher or roaming cameras lose scenery to it. Set for CamLab
             profiles and the debug cameras, cleared for the game's own.
  IAT: GetModuleHandleA [0x6741F4], GetProcAddress [0x674204]
  cave (existing patch) tunables: cave+0x08..0x34 (11 dwords) and cave+0x50..0x80 (12 dwords)

Driver-seat cockpit: an extra entry offset | 0x80000000 adds the cockpit cam a second time;
while that entry is selected the cockpit cam's eye/look points ([cam+0x194], car space,
x = sideways) point to a copy with x mirrored.

Keeping the camera: View Change only ever moves the index one step forward. Any other jump
(the game resetting its camera for a new stage or a continue) is undone, and when the game
rebuilds its list the camera in use before is selected again.

List layout written by the block: [chase] + the game's other cameras + [chase] x one per
CamLab profile + the hidden ones (debug cameras). Slot 0 = SR3's stock chase settings (also used for the
far chase cam), slots 1.. = the profiles.

How a camera reaches the screen (read in the disassembly on 2026-10-14, NOT yet seen in the running game; the
smoothing and the blend below rest on it):
  The game updates its cameras in steps of its own (0x5F17A0, and the same code inline at 0x5CAE45) and draws
  frames in between, so every camera keeps a "state" object that is interpolated for each drawn frame:
    state = camera vtable slot 23 (+0x5C), a one-line "lea eax,[ecx+N]": +0x54 chase / far chase, +0x64 car
    rotate, +8 every other class looked at (bumper, bonnet, cockpit, wheel, free, car free)
    six records of 0x3C bytes from state+0: eye, look-at point, eye and look-at of the look-behind view, up,
    one more; each = five vec3: value before the update, value after it, the two the drawn frame lies
    between, the interpolated one (+0x30). Field of view (radians) the same way at +0x168 .. +0x178.
    0x413CA0 shifts "after" to "before" (first thing in an update), 0x413850 latches both for drawing (slot 2),
    0x413990 interpolates (slot 4, alpha in xmm0).
  mgr+0x190 = the camera asked for, mgr+0x18C = the one being updated, mgr+0x188 / mgr+0x184 = the one the
  frame is drawn from. View Change (0x5EE250, with mgr+0x1A0 set) steps the list of group [mgr+0x198] (0x5C
  bytes per group from mgr+0x1D0; the race list at mgr+0x22C is group 1) and stores the entry at +0x190; an
  entry that is another object is then updated twice alongside the old camera before +0x18C moves to it.
  0x5F1690 (esi = mgr, one float = alpha, ret 4) is called for every player once per drawn frame from
  0x5C948C: [mgr+0x184] = [mgr+0x188], then slot 4 of the cameras. It does nothing unless the game is in
  state 0x27 / 0x1C ([0x7ECE10] = [0x7ECE14]) or [0x9DB800] is set. Its only other caller, 0x5FEA43, sits in
  the replay page's routine 0x5FE810 ("ID_BUTTON_REPLAY_PLAYPAUSE") and is left alone.
  The view is built from the interpolated state of [mgr+0x184] only (0x5A1A70: D3DXMatrixLookAtLH of eye
  state+0x30, look-at +0x6C, up +0x120, and the field of view +0x178; with mgr+0x1A4, look-behind, eye +0xA8 and
  look-at +0xE4). Nothing was found that reads the interpolated values back into an update.
  Free cams (update 0x5F3FE0): angle += [cam+0x230] x input and position += speed x input PER UPDATE, with no
  frame time in it; the car rotate cam's handler 0x5EED30 multiplies its inputs by [mgr] (frame time).
  car + 0x135C: the car's matrix, rows right / up / forward / position (the cameras' updates read it there).

Smoothing of the steerable cameras (K_LOOKTAU, K_MOVETAU; 0 = raw, as before): the update wrappers hand the
camera only a share of the mouse movement that is outstanding, 1 - e^(-dt / tau) of it per update (dt = [mgr]),
and keep the rest for the next updates: the camera turns towards where the raw mouse would have put it, at a
rate that does not depend on the frame rate, and ends exactly there. The keys' -1 / 0 / +1 go the same share
of the way to their value per update, so a movement starts and stops softly.

Blend between cameras (K_BLEND seconds; 0 = cut, as before): BLEND runs after the game has interpolated its
cameras for the frame and keeps the view of every frame in the car's frame (eye, direction, look distance, up,
field of view). After a View Change it rewrites the interpolated eye / look-at / up / field of view of the camera
the frame is drawn from: the view the change left from, carried along by the car's heading and place as the game draws
the car (the drawn position car + 0xAC, which moves as the cameras do; not its pitch and roll, which the cameras' springs
smooth: carried by those it shook, carried by the stepped matrix it jumped at speed), towards the camera's own,
by t x t x (3 - 2t) of the way, t = real time since the start / K_BLEND (QueryPerformanceCounter). At t = 1 it
stops writing, so the camera's own values are shown untouched. Only a View Change this block accepted starts
one; a camera change of the game's own (intro, time over, replay) stays a cut and ends a running blend.
Assumed, not measured: the rows of the car's matrix are unit length (checked when a blend starts: no blend
otherwise), and nothing but the view reads the interpolated state in a way that minds the blend.
Known and left: directions are mixed in a straight line and made unit length again, so between views that look
nearly opposite ways most of the turn happens in the middle of the blend; the look-behind records are not
blended; the PVS switch above follows the new camera at once, not the travelling view.
tools/cycle_real.py runs BLEND and the update wrappers against the game's own routines named here.
"""
import json, os, struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

D = dict(MAGIC=0x00, FONT=0x08, FONTH=0x0C, FRAMES=0x10, SHOWFRAMES=0x14, SIZE=0x18, LASTIDX=0x1C,
         NSLOTS=0x20, START=0x24, EXTCOUNT=0x28, NORIG=0x2C, CURNAME=0x50, PCREATE=0x54,
         MGR=0x58, ORIGFULL=0x5C, S_DLL=0x60, S_FN=0x70, S_FACE=0x80, RECT=0xA0, QUIET=0xB0, TOP=0xB4,
         DIAG=0xB8, NORIGTRUE=0xBC, S_CAMERA=0xE0, NAMES=0x100,
         PARAMS=0x500, SLOTCOLOR=0xE00, CURCOLOR=0xE60, ACTIVE=0xE64,
         NEEDCENTER=0xE68, PT=0xE70, PGETCUR=0xE80, PSETCUR=0xE84, PKEY=0xE88, PFORE=0xE8C,
         S_USER32=0xEA0, S_GETCUR=0xEB0, S_SETCUR=0xEC0, S_KEY=0xED0, S_FORE=0xEF0,
         K_SENS=0xF10, K_ORBIT=0xF14, K_TILT=0xF18, K_FREE=0xF1C, DX=0xF20, DY=0xF24, CX=0xF28, CY=0xF2C,
         CTRLSTATE=0xF30, KEYDBG=0xF34, PIDTMP=0xF38, PWTPID=0xE90, PCURPID=0xE94,
         S_WTPID=0xF40, S_K32=0xF60, S_CURPID=0xF70, K_PITCH=0xF90, K_PITCHN=0xF94, FONT2=0xF98,
         HINT=0xFA0, TEXT=0xFA4, KEEP=0xFA8, S_HINT=0xFB0, K_TILTS=0xFD0, RESETPREV=0xFD8, K_RDMIN=0xFE0, K_RDMAX=0xFE4, K_RHMIN=0xFE8, K_RHMAX=0xFEC,
         GAMENAMES=0x2000, ORIG=0x2180, CAMOFF=0x21B0, EXTRA=0x21E0, CAMCOLOR=0x2210,
         MIRROR=0x2240, SAVEDPTR=0x2258, PATCHIDX=0x225C, NGAME=0x2260, LOADVIDEOS=0x2264, PHINT=0x2268,
         HILITE=0x226C, REOPEN=0x2270, REOPENPATH=0x2274, MODESEL=0x2278, CARSEL=0x227C,
         # settings (seconds, written by patch.ps1): mouse and key smoothing of the steerable cameras, blend time
         K_LOOKTAU=0x2280, K_MOVETAU=0x2284, K_BLEND=0x2288,
         # smoothing: mouse movement not handed out yet (x, y pixels), smoothed keys (free cams forward, sideways,
         # up; car rotate zoom), this update's mouse part (x, y), the keys' share of this update, x87 scratch
         MREM=0x2290, KAX=0x2298, SMXY=0x22A8, SHARE_K=0x22B0, FTMP=0x22B4,
         # blend: QueryPerformanceCounter and its readings, seconds since the last frame / into the blend, running,
         # start with the next frame, start when the view moves to this camera (for so many frames), the camera
         # the last frame was drawn from, BLAST holds a view
         PQPC=0x22B8, QFREQ=0x22C0, QNOW=0x22C8, QPREV=0x22D0, BDT=0x22D8, BT=0x22DC, BACTIVE=0x22E0, BGO=0x22E4,
         BWAIT=0x22E8, BWAITN=0x22EC, BLASTCAM=0x22F0, BHAVE=0x22F4,
         # views (0x40 each: eye, direction, up as 4 floats, then look distance and field of view): the last
         # frame's and the one the blend left from, both in the car's frame; this frame's in the world; then the
         # look-at point written back and a scratch vector. Ends at 0x23E0, below the switcher's strings (0x2400)
         BLAST=0x2300, BFROM=0x2340, BNOW=0x2380, BAT=0x23C0, BTMP=0x23D0,
         # the car's frame the blend carries views in: heading and place only, no pitch or roll (4 rows of 4 floats:
         # right, up, forward, position), between the switcher's strings (up to 0x27C0) and the second code area
         BYAW=0x27C0,
         # the car as the game draws it: the matrix's axes with the drawn position (car + 0xAC)
         INTM=0x3F80)
SLOT_PARAMS = 0x5C          # 11 + 12 dwords copied into the cave
MAX_SLOTS = 21              # the game's list holds 21 pointers
MAX_GAMECAMS = 12
CODE = 0x1000
SIZE = 0x4000              # 0x3000 until 2026-10-14 (the blend's heading-only frame did not fit the second code area)
CAVE = 0x673C80
ks = Ks(KS_ARCH_X86, KS_MODE_32)
strip = lambda a: "\n".join(l.split(';')[0].rstrip() for l in a.splitlines() if l.split(';')[0].strip())

# ---- the second code area (the first one, below, is nearly full): constants, then code. Everything here is reached
# with ebp = the block's base; the first area calls these routines by their offsets, so they are assembled first.
CODE2 = 0x2800              # after the track switcher's strings (0x2400 .. 0x27C0)
CODE2_END = 0x3F00         # (0x3F00 .. 0x4000: the car's states, see CURM)
C2 = dict(ONE=CODE2, THREE=CODE2 + 4, DTBIG=CODE2 + 8, DTMAX=CODE2 + 0xC, TINY2=CODE2 + 0x10, UNIT2=CODE2 + 0x14, MASK=CODE2 + 0x20,
          S_QPC=CODE2 + 0x30, S_QPF=CODE2 + 0x48, XZ=CODE2 + 0x70, UPY=CODE2 + 0x80, RSIGN=CODE2 + 0x90)
consts2 = (struct.pack('<6f', 1.0, 3.0,
                       0.25,        # DTBIG: a frame time over this (or not above 0) is not smoothed over: raw
                       0.1,         # DTMAX: the most real time one frame may add to a blend (a hitch does not eat it)
                       1e-6,        # TINY2: (0.001)^2: pixels, key travel and metres under 0.001 count as nothing
                       0.0625       # UNIT2: (0.25)^2: a car axis with a length squared within 1 +- 0.25 passes for unit length
                       ).ljust(0x20, b'\0') + struct.pack('<4I', 0xffffffff, 0xffffffff, 0xffffffff, 0)   # MASK: x, y, z of 4 floats
           + b'QueryPerformanceCounter'.ljust(0x18, b'\0') + b'QueryPerformanceFrequency'.ljust(0x28, b'\0')
           + struct.pack('<12f', 1, 0, 1, 0,   0, 1, 0, 0,   1, 0, -1, 0))     # XZ: drops y; UPY: straight up; RSIGN: (z, -x) of a heading
assert len(consts2) == 0xA0
BWAIT_FRAMES = 120          # the game moves to another camera object 2 updates after View Change; 2 s is ample

asm2 = f"""
; eax = address of a time constant (seconds), esi = camera manager: xmm2 = the share of what is outstanding that
; goes out in this update, 1 - e^(-dt / tau), dt = the game's frame time [mgr]. 1 = everything now = no smoothing:
; tau 0 (or less, or no number), or a dt that is no usable time (not above 0, over DTBIG). Keeps xmm0, xmm1.
; e^x on the x87: 2^(x log2 e), whole part by fscale, the rest (-0.5 .. 0.5) by f2xm1; two stack slots, like the
; fpatan of the chase camera's cave
share:
    movss xmm2, dword ptr [ebp + {C2['ONE']}]
    xorps xmm3, xmm3
    comiss xmm3, dword ptr [eax]
    jae sh_ret
    jp sh_ret
    movss xmm4, dword ptr [esi]
    comiss xmm4, xmm3
    jbe sh_ret
    comiss xmm4, dword ptr [ebp + {C2['DTBIG']}]
    ja sh_ret
    fld dword ptr [esi]
    fdiv dword ptr [eax]
    fchs
    fldl2e
    fmulp st(1), st(0)
    fld st(0)
    frndint
    fsub st(1), st(0)
    fxch st(1)
    f2xm1
    fld1
    faddp st(1), st(0)
    fscale
    fstp st(1)
    fld1
    fsubrp st(1), st(0)
    fstp dword ptr [ebp + {D['FTMP']}]
    movss xmm2, dword ptr [ebp + {D['FTMP']}]
sh_ret:
    ret

; xmm0 = movement that came in, [eax] = what was left over, xmm2 = the share: xmm0 = the part for this update, the
; rest stays at [eax]. A rest under 0.001 goes out with it, so the total handed out is exactly the total that
; came in (and with share 1: xmm0 unchanged, to the bit). Keeps xmm1.
sm_axis:
    addss xmm0, dword ptr [eax]
    movaps xmm3, xmm0
    mulss xmm0, xmm2
    subss xmm3, xmm0
    movaps xmm4, xmm3
    mulss xmm4, xmm4
    comiss xmm4, dword ptr [ebp + {C2['TINY2']}]
    jae sa_keep
    addss xmm0, xmm3
    xorps xmm3, xmm3
sa_keep:
    movss dword ptr [eax], xmm3
    ret

; xmm0 / xmm1 = the mouse movement read in this update (pixels), esi = camera manager: returns the part of it
; the camera gets now (also left at SMXY), and sets SHARE_K, the keys' share of this update
smooth_mouse:
    lea eax, [ebp + {D['K_MOVETAU']}]
    call share
    movss dword ptr [ebp + {D['SHARE_K']}], xmm2
    lea eax, [ebp + {D['K_LOOKTAU']}]
    call share
    lea eax, [ebp + {D['MREM']}]
    call sm_axis
    movss dword ptr [ebp + {D['SMXY']}], xmm0
    movaps xmm0, xmm1
    lea eax, [ebp + {D['MREM'] + 4}]
    call sm_axis
    movss dword ptr [ebp + {D['SMXY'] + 4}], xmm0
    movaps xmm1, xmm0
    movss xmm0, dword ptr [ebp + {D['SMXY']}]
    ret

; xmm0 = a key pair now (-1 / 0 / +1), eax = address of its smoothed value: xmm0 = the smoothed value, which goes
; SHARE_K of the way to the keys' in every update and lands on it once within 0.001 (a released key ends on
; exactly 0; with share 1 the value is the keys', to the bit)
smooth_key:
    movss xmm2, dword ptr [ebp + {D['SHARE_K']}]
    movaps xmm5, xmm0
    subss xmm0, dword ptr [eax]
    mulss xmm0, xmm2
    addss xmm0, dword ptr [eax]
    movaps xmm3, xmm5
    subss xmm3, xmm0
    mulss xmm3, xmm3
    comiss xmm3, dword ptr [ebp + {C2['TINY2']}]
    jae sk_keep
    movaps xmm0, xmm5
sk_keep:
    movss dword ptr [eax], xmm0
    ret

; nothing outstanding: no mouse movement left over, keys at rest (when no steerable camera is on, the game is
; not in front, or the reset key was pressed). No xmm registers: the draw hook comes through here too
smooth_reset:
    push eax
    xor eax, eax
    mov dword ptr [ebp + {D['MREM']}], eax
    mov dword ptr [ebp + {D['MREM'] + 4}], eax
    mov dword ptr [ebp + {D['KAX']}], eax
    mov dword ptr [ebp + {D['KAX'] + 4}], eax
    mov dword ptr [ebp + {D['KAX'] + 8}], eax
    mov dword ptr [ebp + {D['KAX'] + 12}], eax
    pop eax
    ret

; a View Change was accepted (esi = camera manager, from the draw hook: no xmm registers). The same camera object
; with other settings (a CamLab profile, the cockpit's other seat) moves at its next update: the blend starts with
; the next frame. Another object takes over only after the game has updated it twice: the blend starts on the
; frame the view is first drawn from it, and is forgotten if that has not happened after BWAIT_FRAMES frames
blend_arm:
    push eax
    mov eax, dword ptr [esi + 0x230]
    mov eax, dword ptr [esi + eax*4 + 0x234]
    cmp eax, dword ptr [ebp + {D['BLASTCAM']}]
    je ba_go
    mov dword ptr [ebp + {D['BWAIT']}], eax
    mov dword ptr [ebp + {D['BWAITN']}], {BWAIT_FRAMES}
    pop eax
    ret
ba_go:
    mov dword ptr [ebp + {D['BGO']}], 1
    mov dword ptr [ebp + {D['BWAIT']}], 0
    pop eax
    ret

; xmm2 = x + y + z of xmm2 (uses xmm3)
hsum:
    movaps xmm3, xmm2
    shufps xmm3, xmm3, 0x55
    addss xmm3, xmm2
    movhlps xmm2, xmm2
    addss xmm2, xmm3
    ret

; xmm0 = xmm0 + (xmm1 - xmm0) x xmm6: from xmm0 to xmm1, xmm6 of the way (exactly xmm0 at 0)
lerp:
    subps xmm1, xmm0
    mulps xmm1, xmm6
    addps xmm0, xmm1
    ret

; [ecx] = the direction [eax] of the world (3 floats) seen in the car's frame: its parts along the car's right,
; up and forward axes, the rows of the car's matrix at edx (uses xmm0, xmm1; eax and ecx must differ)
w2c:
    push ebx
    xor ebx, ebx
w2c_l:
    movss xmm0, dword ptr [eax]
    mulss xmm0, dword ptr [edx + ebx*4]
    movss xmm1, dword ptr [eax + 4]
    mulss xmm1, dword ptr [edx + ebx*4 + 4]
    addss xmm0, xmm1
    movss xmm1, dword ptr [eax + 8]
    mulss xmm1, dword ptr [edx + ebx*4 + 8]
    addss xmm0, xmm1
    movss dword ptr [ecx + ebx], xmm0
    add ebx, 4
    cmp ebx, 12
    jb w2c_l
    pop ebx
    ret

; [ecx] = the car-frame direction [eax] back in the world: that much of the car's right, up and forward axes
c2w:
    push ebx
    xor ebx, ebx
c2w_l:
    movss xmm0, dword ptr [eax]
    mulss xmm0, dword ptr [edx + ebx]
    movss xmm1, dword ptr [eax + 4]
    mulss xmm1, dword ptr [edx + ebx + 0x10]
    addss xmm0, xmm1
    movss xmm1, dword ptr [eax + 8]
    mulss xmm1, dword ptr [edx + ebx + 0x20]
    addss xmm0, xmm1
    movss dword ptr [ecx + ebx], xmm0
    add ebx, 4
    cmp ebx, 12
    jb c2w_l
    pop ebx
    ret

; BDT = seconds since the previous frame by QueryPerformanceCounter, at most DTMAX; 0 on the first frame. The blend
; runs on real time: it is stepped once per drawn frame, whatever the game's update rate. PQPC stays 0 (no
; blend) when kernel32 does not give the two functions. Uses eax, ebx, ecx, edx, edi, xmm0
frame_dt:
    mov dword ptr [ebp + {D['BDT']}], 0
    cmp dword ptr [ebp + {D['PQPC']}], 0
    jne fd_have
    lea eax, [ebp + {D['S_K32']}]
    push eax
    call dword ptr [0x6741f4]
    test eax, eax
    jz fd_ret
    mov edi, eax
    lea ecx, [ebp + {C2['S_QPF']}]
    push ecx
    push edi
    call dword ptr [0x674204]
    test eax, eax
    jz fd_ret
    lea ecx, [ebp + {D['QFREQ']}]
    push ecx
    call eax
    lea ecx, [ebp + {C2['S_QPC']}]
    push ecx
    push edi
    call dword ptr [0x674204]
    test eax, eax
    jz fd_ret
    mov dword ptr [ebp + {D['PQPC']}], eax
fd_have:
    lea eax, [ebp + {D['QNOW']}]
    push eax
    call dword ptr [ebp + {D['PQPC']}]
    mov eax, dword ptr [ebp + {D['QNOW']}]
    mov edx, dword ptr [ebp + {D['QNOW'] + 4}]
    mov ecx, dword ptr [ebp + {D['QPREV']}]
    mov ebx, dword ptr [ebp + {D['QPREV'] + 4}]
    mov dword ptr [ebp + {D['QPREV']}], eax
    mov dword ptr [ebp + {D['QPREV'] + 4}], edx
    mov edi, ecx
    or edi, ebx
    jz fd_ret
    sub eax, ecx
    sbb edx, ebx
    jnz fd_long
    test eax, eax
    js fd_long
    mov dword ptr [ebp + {D['QNOW']}], eax
    fild dword ptr [ebp + {D['QNOW']}]
    fild qword ptr [ebp + {D['QFREQ']}]
    fdivp st(1), st(0)
    fstp dword ptr [ebp + {D['BDT']}]
    movss xmm0, dword ptr [ebp + {D['BDT']}]
    minss xmm0, dword ptr [ebp + {C2['DTMAX']}]
    movss dword ptr [ebp + {D['BDT']}], xmm0
    ret
fd_long:
    mov eax, dword ptr [ebp + {C2['DTMAX']}]
    mov dword ptr [ebp + {D['BDT']}], eax
fd_ret:
    ret

; esi = a camera manager whose cameras the game has just interpolated for the frame to draw (or not: see below)
blend_step:
    mov eax, dword ptr [0x9eb4ec]
    test eax, eax
    jz bs_ret
    add eax, 0x18
    cmp eax, esi
    jne bs_ret
    ; 0x5F1690's own test: outside the states 0x27 / 0x1C it interpolated nothing, unless [0x9DB800] is set, and
    ; the state would still hold what was written into it for the frame before
    mov eax, dword ptr [0x7ece10]
    cmp eax, dword ptr [0x7ece14]
    jne bs_forced
    cmp eax, 0x27
    je bs_on
    cmp eax, 0x1c
    je bs_on
bs_forced:
    cmp dword ptr [0x9db800], 0
    je bs_ret
bs_on:
    xorps xmm1, xmm1
    comiss xmm1, dword ptr [ebp + {D['K_BLEND']}]
    jae bs_none
    jp bs_none
    call frame_dt
    cmp dword ptr [ebp + {D['PQPC']}], 0
    je bs_none
    mov edi, dword ptr [esi + 0x184]
    test edi, edi
    jz bs_none
    mov ecx, edi
    mov eax, dword ptr [edi]
    call dword ptr [eax + 0x5c]
    mov ebx, eax
    mov edx, dword ptr [esi + 0x1c8]
    test edx, edx
    jz bs_none
    add edx, 0x135c
    movups xmm7, xmmword ptr [ebp + {C2['MASK']}]
    ; -- does a blend start, go on, or end with a cut?
    cmp edi, dword ptr [ebp + {D['BLASTCAM']}]
    je bs_same
    mov dword ptr [ebp + {D['BLASTCAM']}], edi
    cmp edi, dword ptr [ebp + {D['BWAIT']}]
    je bs_start
    mov dword ptr [ebp + {D['BACTIVE']}], 0
    jmp bs_live
bs_same:
    cmp dword ptr [ebp + {D['BGO']}], 0
    jne bs_start
    cmp dword ptr [ebp + {D['BWAIT']}], 0
    je bs_run
    dec dword ptr [ebp + {D['BWAITN']}]
    jg bs_run
    mov dword ptr [ebp + {D['BWAIT']}], 0
bs_run:
    cmp dword ptr [ebp + {D['BACTIVE']}], 0
    je bs_live
    movss xmm0, dword ptr [ebp + {D['BT']}]
    addss xmm0, dword ptr [ebp + {D['BDT']}]
    movss dword ptr [ebp + {D['BT']}], xmm0
    jmp bs_live
bs_start:
    mov dword ptr [ebp + {D['BGO']}], 0
    mov dword ptr [ebp + {D['BWAIT']}], 0
    cmp dword ptr [ebp + {D['BHAVE']}], 0
    je bs_live
    ; the car's axes must be unit length for a view to keep its place in the car's frame: each row's
    ; length squared within 0.75 .. 1.25, or the change stays a cut
    xor ecx, ecx
bs_unit:
    movups xmm2, xmmword ptr [edx + ecx]
    andps xmm2, xmm7
    mulps xmm2, xmm2
    call hsum
    subss xmm2, dword ptr [ebp + {C2['ONE']}]
    mulss xmm2, xmm2
    comiss xmm2, dword ptr [ebp + {C2['UNIT2']}]
    ja bs_live
    jp bs_live
    add ecx, 0x10
    cmp ecx, 0x30
    jb bs_unit
    push esi
    push edi
    lea esi, [ebp + {D['BLAST']}]
    lea edi, [ebp + {D['BFROM']}]
    mov ecx, 16
    rep movsd dword ptr es:[edi], dword ptr [esi]
    pop edi
    pop esi
    mov dword ptr [ebp + {D['BT']}], 0
    mov dword ptr [ebp + {D['BACTIVE']}], 1
bs_live:
    ; -- the car as the game draws this frame. Its matrix moves in physics steps (about 63 a second, measured) and the
    ; game draws between steps (0x5BA410 has every object interpolate by the frame's fraction). The drawn position is
    ; car + 0xAC (the fifth of five position records: before and after the step, the two the frame lies between, the
    ; drawn one; car = the matrix - 0x135C): measured in game, it moves frame by frame exactly as the camera does, while
    ; the matrix holds one step in some frames and two in others. Carried by the matrix, the old view jumped by a step,
    ; the more the faster the car (owner, 2026-10-14). The heading stays the matrix's.
    movups xmm0, xmmword ptr [edx]
    movups xmmword ptr [ebp + {D['INTM']}], xmm0
    movups xmm0, xmmword ptr [edx + 0x10]
    movups xmmword ptr [ebp + {D['INTM'] + 0x10}], xmm0
    movups xmm0, xmmword ptr [edx + 0x20]
    movups xmmword ptr [ebp + {D['INTM'] + 0x20}], xmm0
    movups xmm0, xmmword ptr [edx - 0x135c + 0xac]
    andps xmm0, xmm7
    movups xmmword ptr [ebp + {D['INTM'] + 0x30}], xmm0
    lea edx, [ebp + {D['INTM']}]
    ; -- the car's frame the views are carried in: its heading and its place, without pitch and roll. Carried by the
    ; whole body matrix, the view a blend leaves from shook with every bump and lean of the car, which the cameras'
    ; own springs smooth away: the first part of each blend was jerky (owner, 2026-10-14). Made here, after the start
    ; checks, which look at the car's own matrix
    ; (the car's whole matrix must be numbers: 0 x every part is 0, or no number)
    movups xmm0, xmmword ptr [edx]
    andps xmm0, xmm7
    movups xmm1, xmmword ptr [edx + 0x10]
    andps xmm1, xmm7
    addps xmm0, xmm1
    movups xmm1, xmmword ptr [edx + 0x20]
    andps xmm1, xmm7
    addps xmm0, xmm1
    movups xmm1, xmmword ptr [edx + 0x30]
    andps xmm1, xmm7
    addps xmm0, xmm1
    xorps xmm1, xmm1
    mulps xmm0, xmm1
    movaps xmm2, xmm0
    call hsum
    ucomiss xmm2, xmm1
    jp bs_none
    movups xmm0, xmmword ptr [edx + 0x20]
    andps xmm0, xmm7
    mulps xmm0, xmmword ptr [ebp + {C2['XZ']}]
    movaps xmm2, xmm0
    mulps xmm2, xmm2
    call hsum
    comiss xmm2, dword ptr [ebp + {C2['TINY2']}]
    jbe bs_none
    sqrtss xmm2, xmm2
    shufps xmm2, xmm2, 0
    divps xmm0, xmm2
    movups xmmword ptr [ebp + {D['BYAW'] + 0x20}], xmm0
    movups xmm1, xmmword ptr [ebp + {C2['UPY']}]
    movups xmmword ptr [ebp + {D['BYAW'] + 0x10}], xmm1
    movaps xmm1, xmm0
    shufps xmm1, xmm1, 0xC6
    mulps xmm1, xmmword ptr [ebp + {C2['RSIGN']}]
    movups xmm2, xmmword ptr [edx]
    andps xmm2, xmm7
    mulps xmm2, xmm1
    call hsum
    xorps xmm3, xmm3
    comiss xmm2, xmm3
    jae bs_right
    subps xmm3, xmm1
    movaps xmm1, xmm3
bs_right:
    movups xmmword ptr [ebp + {D['BYAW']}], xmm1
    movups xmm0, xmmword ptr [edx + 0x30]
    movups xmmword ptr [ebp + {D['BYAW'] + 0x30}], xmm0
    lea edx, [ebp + {D['BYAW']}]
    ; -- the camera's own view of this frame, in the world: eye, unit direction, look distance, up, field of view
    movups xmm0, xmmword ptr [ebx + 0x30]
    andps xmm0, xmm7
    movups xmmword ptr [ebp + {D['BNOW']}], xmm0
    movups xmm1, xmmword ptr [ebx + 0x6c]
    andps xmm1, xmm7
    subps xmm1, xmm0
    movaps xmm2, xmm1
    mulps xmm2, xmm2
    call hsum
    comiss xmm2, dword ptr [ebp + {C2['TINY2']}]
    jbe bs_none
    sqrtss xmm2, xmm2
    movss dword ptr [ebp + {D['BNOW'] + 0x30}], xmm2
    shufps xmm2, xmm2, 0
    divps xmm1, xmm2
    movups xmmword ptr [ebp + {D['BNOW'] + 0x10}], xmm1
    movups xmm0, xmmword ptr [ebx + 0x120]
    andps xmm0, xmm7
    movups xmmword ptr [ebp + {D['BNOW'] + 0x20}], xmm0
    mov eax, dword ptr [ebx + 0x178]
    mov dword ptr [ebp + {D['BNOW'] + 0x34}], eax
    cmp dword ptr [ebp + {D['BACTIVE']}], 0
    je bs_keep
    ; -- how far along: t = time / duration, eased in and out: s = t x t x (3 - 2t), in all four of xmm6
    movss xmm6, dword ptr [ebp + {D['BT']}]
    divss xmm6, dword ptr [ebp + {D['K_BLEND']}]
    comiss xmm6, dword ptr [ebp + {C2['ONE']}]
    jae bs_end
    movaps xmm0, xmm6
    addss xmm0, xmm0
    movss xmm1, dword ptr [ebp + {C2['THREE']}]
    subss xmm1, xmm0
    mulss xmm1, xmm6
    mulss xmm6, xmm1
    shufps xmm6, xmm6, 0
    ; -- the view the blend left from sits in the car's frame: where is it in the world now, and s of the way on
    lea eax, [ebp + {D['BFROM']}]
    lea ecx, [ebp + {D['BTMP']}]
    call c2w
    movups xmm0, xmmword ptr [ebp + {D['BTMP']}]
    andps xmm0, xmm7
    movups xmm1, xmmword ptr [edx + 0x30]
    andps xmm1, xmm7
    addps xmm0, xmm1
    movups xmm1, xmmword ptr [ebp + {D['BNOW']}]
    call lerp
    movups xmmword ptr [ebp + {D['BNOW']}], xmm0
    lea eax, [ebp + {D['BFROM'] + 0x10}]
    call c2w
    movups xmm0, xmmword ptr [ebp + {D['BTMP']}]
    andps xmm0, xmm7
    movups xmm1, xmmword ptr [ebp + {D['BNOW'] + 0x10}]
    call lerp
    movaps xmm2, xmm0
    mulps xmm2, xmm2
    call hsum
    comiss xmm2, dword ptr [ebp + {C2['TINY2']}]
    jbe bs_dir
    sqrtss xmm2, xmm2
    shufps xmm2, xmm2, 0
    divps xmm0, xmm2
    movups xmmword ptr [ebp + {D['BNOW'] + 0x10}], xmm0
bs_dir:
    lea eax, [ebp + {D['BFROM'] + 0x20}]
    call c2w
    movups xmm0, xmmword ptr [ebp + {D['BTMP']}]
    andps xmm0, xmm7
    movups xmm1, xmmword ptr [ebp + {D['BNOW'] + 0x20}]
    call lerp
    movups xmmword ptr [ebp + {D['BNOW'] + 0x20}], xmm0
    movups xmm0, xmmword ptr [ebp + {D['BFROM'] + 0x30}]
    movups xmm1, xmmword ptr [ebp + {D['BNOW'] + 0x30}]
    call lerp
    movlps qword ptr [ebp + {D['BNOW'] + 0x30}], xmm0
    ; -- look-at = eye + direction x look distance; all of it numbers?
    movss xmm0, dword ptr [ebp + {D['BNOW'] + 0x30}]
    shufps xmm0, xmm0, 0
    movups xmm1, xmmword ptr [ebp + {D['BNOW'] + 0x10}]
    mulps xmm1, xmm0
    movups xmm0, xmmword ptr [ebp + {D['BNOW']}]
    addps xmm1, xmm0
    movups xmmword ptr [ebp + {D['BAT']}], xmm1
    movups xmm2, xmmword ptr [ebp + {D['BNOW'] + 0x20}]
    addps xmm2, xmm1
    addps xmm2, xmm0
    call hsum
    addss xmm2, dword ptr [ebp + {D['BNOW'] + 0x34}]
    xorps xmm3, xmm3
    mulss xmm2, xmm3
    ucomiss xmm2, xmm3
    jp bs_none
    ; -- into the camera's interpolated state, which is what the view is built from (3 floats each, no more)
    movlps qword ptr [ebx + 0x30], xmm0
    movhlps xmm0, xmm0
    movss dword ptr [ebx + 0x38], xmm0
    movlps qword ptr [ebx + 0x6c], xmm1
    movhlps xmm1, xmm1
    movss dword ptr [ebx + 0x74], xmm1
    movups xmm0, xmmword ptr [ebp + {D['BNOW'] + 0x20}]
    movlps qword ptr [ebx + 0x120], xmm0
    movhlps xmm0, xmm0
    movss dword ptr [ebx + 0x128], xmm0
    mov eax, dword ptr [ebp + {D['BNOW'] + 0x34}]
    mov dword ptr [ebx + 0x178], eax
    jmp bs_keep
bs_end:
    mov dword ptr [ebp + {D['BACTIVE']}], 0
bs_keep:
    ; -- this frame's view (the camera's own, or the blended one) in the car's frame: where the next blend leaves from
    movups xmm0, xmmword ptr [ebp + {D['BNOW']}]
    movups xmm1, xmmword ptr [edx + 0x30]
    andps xmm1, xmm7
    subps xmm0, xmm1
    movups xmmword ptr [ebp + {D['BTMP']}], xmm0
    lea eax, [ebp + {D['BTMP']}]
    lea ecx, [ebp + {D['BLAST']}]
    call w2c
    lea eax, [ebp + {D['BNOW'] + 0x10}]
    lea ecx, [ebp + {D['BLAST'] + 0x10}]
    call w2c
    lea eax, [ebp + {D['BNOW'] + 0x20}]
    lea ecx, [ebp + {D['BLAST'] + 0x20}]
    call w2c
    mov eax, dword ptr [ebp + {D['BNOW'] + 0x30}]
    mov dword ptr [ebp + {D['BLAST'] + 0x30}], eax
    mov eax, dword ptr [ebp + {D['BNOW'] + 0x34}]
    mov dword ptr [ebp + {D['BLAST'] + 0x34}], eax
    mov dword ptr [ebp + {D['BHAVE']}], 1
    ret
bs_none:
    ; no blend (off, no clock, no camera, no car, a view that is no view): nothing kept, nothing pending
    xor eax, eax
    mov dword ptr [ebp + {D['BHAVE']}], eax
    mov dword ptr [ebp + {D['BACTIVE']}], eax
    mov dword ptr [ebp + {D['BGO']}], eax
    mov dword ptr [ebp + {D['BWAIT']}], eax
bs_ret:
    ret

; replaces "call 0x5F1690" at 0x5C948C (esi = camera manager, one float on the stack, the callee removes it):
; the game's routine first, untouched, then the blend on what it left
blend_wrap:
    push dword ptr [esp + 4]
    mov eax, 0x5f1690
    call eax
    pushfd
    pushad
    call bw_base
bw_base:
    pop ebp
    sub ebp, BWBASE
    call blend_step
    popad
    popfd
    ret 4
"""
asm2 = strip(asm2)
CODE2_CODE = CODE2 + len(consts2)
def entry2(label): return CODE2_CODE + len(bytes(ks.asm(asm2.split(label + ':')[0], addr=CODE2_CODE)[0]))
SM_MOUSE, SM_KEY, SM_RESET, B_ARM, blend_off = (entry2(l) for l in ('smooth_mouse', 'smooth_key', 'smooth_reset', 'blend_arm', 'blend_wrap'))
code2 = consts2 + bytes(ks.asm(asm2.replace('BWBASE', str(blend_off + 18)), addr=CODE2_CODE)[0])   # 18 = up to and with "call bw_base"
assert code2[blend_off - CODE2:blend_off - CODE2 + 19] == bytes.fromhex('ff742404' 'b890165f00' 'ffd0' '9c60' 'e800000000' '5d'), code2[blend_off - CODE2:blend_off - CODE2 + 19].hex()
assert CODE2 + len(code2) <= CODE2_END <= SIZE
assert max(D[k] for k in ('BTMP',)) + 0x10 <= 0x2400     # the switcher's strings start there

asm = f"""
draw_hook:
    pushfd
    pushad
    call d_base
d_base:
    pop ebp
    sub ebp, {CODE + 7}

    cmp dword ptr [ebp + {D['LOADVIDEOS']}], 0
    je no_videos
    mov dword ptr [ebp + {D['LOADVIDEOS']}], 0
    mov eax, 0x621600
    call eax
no_videos:

    or eax, -1
    cmp dword ptr [0x9c0f48], 0
    je hilite_store
    push 23
    mov ecx, 0x6e53fc
    mov eax, 0x5470d0
    call eax
    add esp, 4
    mov edi, eax
    mov eax, 0x606490
    call eax
hilite_store:
    mov dword ptr [ebp + {D['HILITE']}], eax

    or eax, -1
    cmp dword ptr [0x9c0f48], 0
    je modesel_store
    push 22
    mov ecx, 0x6e5e14
    mov eax, 0x5470d0
    call eax
    add esp, 4
    mov edi, eax
    mov eax, 0x606490
    call eax
modesel_store:
    mov dword ptr [ebp + {D['MODESEL']}], eax

    or eax, -1
    cmp dword ptr [0x9c0f48], 0
    je carsel_store
    mov edi, 0x6eace04a
    mov eax, 0x606510
    call eax
carsel_store:
    mov dword ptr [ebp + {D['CARSEL']}], eax

    mov eax, dword ptr [ebp + {D['REOPEN']}]
    test eax, eax
    je no_reopen
    dec eax
    cmp eax, 20
    jae reopen_done
    push eax
    imul edi, eax, 0x16c
    add edi, 0xad2f90
    cmp dword ptr [edi + 4], 0
    je reopen_open
    mov eax, dword ptr [edi + 0x120]
    test eax, eax
    je reopen_release
    mov ecx, dword ptr [eax]
    push eax
    call dword ptr [ecx + 0x24]
reopen_release:
    mov ebx, 0x12c
reopen_loop:
    mov eax, dword ptr [edi + ebx]
    test eax, eax
    je reopen_next
    mov dword ptr [edi + ebx], 0
    mov ecx, dword ptr [eax]
    push eax
    call dword ptr [ecx + 8]
reopen_next:
    sub ebx, 4
    cmp ebx, 0x11c
    jae reopen_loop
    mov eax, dword ptr [edi + 0x144]
    test eax, eax
    je reopen_closed
    mov dword ptr [edi + 0x144], 0
    mov ecx, dword ptr [eax]
    push eax
    call dword ptr [ecx + 8]
reopen_closed:
    mov dword ptr [edi + 0x130], 0
    mov dword ptr [edi], 0
    mov dword ptr [edi + 4], 0
    mov dword ptr [edi + 8], 0
reopen_open:
    mov ecx, dword ptr [ebp + {D['REOPENPATH']}]
    push ebp
    mov eax, 0x4ddc80
    call eax
    pop ebp
    test eax, eax
    je reopen_failed
    mov eax, dword ptr [edi + 0x120]
    mov ecx, dword ptr [eax]
    push eax
    call dword ptr [ecx + 0x1c]
    test eax, eax
    jl reopen_play
    mov dword ptr [edi], 0
reopen_play:
    mov eax, dword ptr [esp]
    push 1
    push 0
    push eax
    mov eax, 0x4de370
    call eax
    add esp, 12
reopen_failed:
    add esp, 4
reopen_done:
    mov dword ptr [ebp + {D['REOPEN']}], 0
no_reopen:

    mov esi, dword ptr [0x9eb4ec]
    test esi, esi
    jz nocam
    add esi, 0x18
    cmp dword ptr [esi + 0x510], 0x6eb808
    jne nocam
    lea edi, [esi + 0x510]
    cmp dword ptr [esi + 0x234], edi
    jne nocam
    mov eax, dword ptr [esi + 0x22c]
    cmp eax, dword ptr [ebp + {D['EXTCOUNT']}]
    jne doext
    cmp dword ptr [ebp + {D['MGR']}], esi
    je extok

doext:
    cmp eax, 1
    jb nocam
    mov dword ptr [ebp + {D['PATCHIDX']}], 0
    cmp eax, {MAX_SLOTS}
    ja nocam
    xor ecx, ecx
    xor edx, edx
collect:
    cmp ecx, eax
    jae collected
    mov ebx, dword ptr [esi + ecx*4 + 0x234]
    cmp ebx, edi
    je collect_next
    cmp edx, {MAX_GAMECAMS}
    jae collect_next
    cmp dword ptr [ebp + {D['MGR']}], esi
    jne collect_take
    cmp edx, dword ptr [ebp + {D['NORIGTRUE']}]
    jae collect_next
collect_take:
    mov dword ptr [ebp + edx*4 + {D['ORIG']}], ebx
    inc edx
collect_next:
    inc ecx
    jmp collect
collected:
    cmp dword ptr [ebp + {D['MGR']}], esi
    je keeptrue
    mov dword ptr [ebp + {D['NORIGTRUE']}], edx
    mov dword ptr [ebp + {D['ORIGFULL']}], eax
keeptrue:
    mov dword ptr [ebp + {D['NGAME']}], edx
    xor ecx, ecx
extra_loop:
    cmp ecx, {MAX_GAMECAMS}
    jae extras_done
    mov ebx, dword ptr [ebp + ecx*4 + {D['EXTRA']}]
    cmp ebx, -1
    je extras_done
    test ebx, ebx
    js extra_patched
    add ebx, esi
    cmp dword ptr [ebx], 0
    je extra_next
    push ecx
    xor ecx, ecx
dd_loop:
    cmp ecx, edx
    jae dd_new
    cmp dword ptr [ebp + ecx*4 + {D['ORIG']}], ebx
    je dd_done
    inc ecx
    jmp dd_loop
dd_new:
    cmp edx, {MAX_GAMECAMS}
    jae dd_done
    mov dword ptr [ebp + edx*4 + {D['ORIG']}], ebx
    inc edx
dd_done:
    pop ecx
extra_next:
    inc ecx
    jmp extra_loop
extra_patched:
    and ebx, 0x7fffffff
    add ebx, esi
    cmp dword ptr [ebx], 0
    je extra_next
    cmp edx, {MAX_GAMECAMS}
    jae extra_next
    mov dword ptr [ebp + edx*4 + {D['ORIG']}], ebx
    inc edx
    mov dword ptr [ebp + {D['PATCHIDX']}], edx
    jmp extra_next
extras_done:
    mov ecx, dword ptr [ebp + {D['NSLOTS']}]
    lea ebx, [ecx + edx]
    cmp ebx, {MAX_SLOTS}
    ja nocam
    cmp dword ptr [ebp + {D['PATCHIDX']}], 0
    je no_patchidx
    dec ecx
    add dword ptr [ebp + {D['PATCHIDX']}], ecx
no_patchidx:
    mov dword ptr [ebp + {D['NORIG']}], edx
    mov dword ptr [ebp + {D['MGR']}], esi
    mov dword ptr [esi + 0x234], edi
    mov ebx, 1
    xor ecx, ecx
worig:
    cmp ecx, dword ptr [ebp + {D['NGAME']}]
    jae worigd
    mov eax, dword ptr [ebp + ecx*4 + {D['ORIG']}]
    mov dword ptr [esi + ebx*4 + 0x234], eax
    inc ebx
    inc ecx
    jmp worig
worigd:
    mov ecx, 1
wprof:
    cmp ecx, dword ptr [ebp + {D['NSLOTS']}]
    jae wprofd0
    mov dword ptr [esi + ebx*4 + 0x234], edi
    inc ebx
    inc ecx
    jmp wprof
wprofd0:
    mov ecx, dword ptr [ebp + {D['NGAME']}]
wdebug:
    cmp ecx, edx
    jae wprofd
    mov eax, dword ptr [ebp + ecx*4 + {D['ORIG']}]
    mov dword ptr [esi + ebx*4 + 0x234], eax
    inc ebx
    inc ecx
    jmp wdebug
wprofd:
    mov dword ptr [esi + 0x22c], ebx
    mov dword ptr [ebp + {D['EXTCOUNT']}], ebx
    mov eax, dword ptr [ebp + {D['KEEP']}]
    test eax, eax
    jz use_start
    dec eax
    cmp eax, ebx
    jb start_set
use_start:
    mov eax, dword ptr [ebp + {D['START']}]
    cmp eax, -2
    jne start_slot
    lea ecx, [esi + 0x8c4]
    xor eax, eax
find_far:
    cmp eax, ebx
    jae start_zero
    cmp dword ptr [esi + eax*4 + 0x234], ecx
    je start_set
    inc eax
    jmp find_far
start_zero:
    xor eax, eax
    jmp start_set
start_slot:
    test eax, eax
    jz start_set
    add eax, dword ptr [ebp + {D['NGAME']}]
start_set:
    mov dword ptr [esi + 0x230], eax
    mov dword ptr [ebp + {D['LASTIDX']}], -1
    mov dword ptr [ebp + {D['QUIET']}], 1

extok:
    mov eax, dword ptr [esi + 0x230]
    cmp eax, dword ptr [ebp + {D['LASTIDX']}]
    je nocam
    mov ecx, dword ptr [ebp + {D['LASTIDX']}]
    cmp ecx, -1
    je idx_ok
    lea edx, [ecx + 1]
    cmp edx, dword ptr [ebp + {D['EXTCOUNT']}]
    jb no_wrap
    xor edx, edx
no_wrap:
    cmp eax, edx
    je idx_ok
    mov edx, dword ptr [esi + eax*4 + 0x234]
    cmp dword ptr [esi + 0x190], edx
    jne keep_idx
    mov edx, dword ptr [esi + ecx*4 + 0x234]
    mov dword ptr [esi + 0x190], edx
keep_idx:
    mov dword ptr [esi + 0x230], ecx
    jmp nocam
idx_ok:
    cmp eax, dword ptr [esi + 0x22c]
    jae nocam
    mov dword ptr [ebp + {D['LASTIDX']}], eax
    lea ecx, [eax + 1]
    mov dword ptr [ebp + {D['KEEP']}], ecx
    mov ecx, dword ptr [esi + eax*4 + 0x234]
    sub ecx, esi
    xor edx, edx
    cmp ecx, 0xeec
    je hint_yes
    cmp ecx, 0xc78
    je hint_yes
    cmp ecx, 0x1d68
    jne hint_set
hint_yes:
    inc edx
hint_set:
    mov dword ptr [ebp + {D['HINT']}], edx
    call cockpit_seat
    xor ecx, ecx
    test eax, eax
    jz pvs_set
    cmp eax, dword ptr [ebp + {D['NGAME']}]
    jbe pvs_set
    inc ecx
pvs_set:
    mov dword ptr [0xa65794], ecx
    test eax, eax
    jz chase_slot
    cmp eax, dword ptr [ebp + {D['NGAME']}]
    jbe gamecam
    mov ecx, eax
    sub ecx, dword ptr [ebp + {D['NGAME']}]
    cmp ecx, dword ptr [ebp + {D['NSLOTS']}]
    jae gamecam
    mov eax, ecx
chase_slot:
    call apply_slot
    mov ecx, dword ptr [ebp + eax*4 + {D['SLOTCOLOR']}]
    mov dword ptr [ebp + {D['CURCOLOR']}], ecx
    shl eax, 5
    lea eax, [ebp + eax + {D['NAMES']}]
    jmp setname
gamecam:
    mov ebx, dword ptr [esi + eax*4 + 0x234]
    cmp dword ptr [ebx], 0x6eb8b8
    jne not_far
    push eax
    xor eax, eax
    call apply_slot
    pop eax
not_far:
    sub ebx, esi
    cmp eax, dword ptr [ebp + {D['PATCHIDX']}]
    jne not_patched
    or ebx, 0x80000000
not_patched:
    lea eax, [ebp + {D['S_CAMERA']}]
    mov dword ptr [ebp + {D['CURCOLOR']}], 0xffffffff
    xor ecx, ecx
camlookup:
    cmp ecx, {MAX_GAMECAMS}
    jae setname
    cmp dword ptr [ebp + ecx*4 + {D['CAMOFF']}], ebx
    jne camnext
    mov eax, dword ptr [ebp + ecx*4 + {D['CAMCOLOR']}]
    mov dword ptr [ebp + {D['CURCOLOR']}], eax
    mov eax, ecx
    shl eax, 5
    lea eax, [ebp + eax + {D['GAMENAMES']}]
    jmp setname
camnext:
    inc ecx
    jmp camlookup
setname:
    mov dword ptr [ebp + {D['CURNAME']}], eax
    mov ecx, dword ptr [ebp + {D['QUIET']}]
    mov dword ptr [ebp + {D['QUIET']}], 0
    test ecx, ecx
    jnz nocam
    mov eax, dword ptr [ebp + {D['SHOWFRAMES']}]
    mov dword ptr [ebp + {D['FRAMES']}], eax
    call {B_ARM}
nocam:
    call controls_idle

    cmp dword ptr [ebp + {D['FRAMES']}], 0
    jle done
    dec dword ptr [ebp + {D['FRAMES']}]
    mov eax, dword ptr [ebp + {D['SIZE']}]
    test eax, eax
    jle done
    mul dword ptr [0x7edb78]
    mov ecx, 1080
    div ecx
    cmp eax, 8
    jge h_ok
    mov eax, 8
h_ok:
    push eax
    lea ebx, [ebp + {D['FONT']}]
    call ensure_font
    pop ecx
    test eax, eax
    jz fontfail
    mov ebx, eax
    push ecx
    mov eax, dword ptr [0x7edb78]
    mov ecx, 14
    mul ecx
    mov ecx, 100
    div ecx
    mov dword ptr [ebp + {D['TOP']}], eax
    mov eax, dword ptr [ebp + {D['CURNAME']}]
    mov dword ptr [ebp + {D['TEXT']}], eax
    mov eax, dword ptr [esp]
    mov ecx, dword ptr [ebp + {D['CURCOLOR']}]
    call draw_outlined
    pop eax
    cmp dword ptr [ebp + {D['HINT']}], 0
    je done
    push eax
    imul eax, eax, 11
    xor edx, edx
    mov ecx, 10
    div ecx
    add dword ptr [ebp + {D['TOP']}], eax
    pop eax
    shr eax, 1
    cmp eax, 8
    jge h2_ok
    mov eax, 8
h2_ok:
    push eax
    lea ebx, [ebp + {D['FONT2']}]
    call ensure_font
    pop ecx
    test eax, eax
    jz done
    mov ebx, eax
    mov edx, dword ptr [ebp + {D['PHINT']}]
    test edx, edx
    jnz hint_text
    lea edx, [ebp + {D['S_HINT']}]
hint_text:
    mov dword ptr [ebp + {D['TEXT']}], edx
    mov eax, ecx
    mov ecx, 0xffe0e0e0
    call draw_outlined
    jmp done
fontfail:
    mov dword ptr [ebp + {D['FRAMES']}], 0
done:
    popad
    popfd
    mov eax, dword ptr [0x7ed10c]
    ret

; eax = slot: copy its settings into the cave (keeps eax)
; eax = list index now selected, esi = camera manager: the cockpit cam looks from the
; driver's seat on the patched entry, from its own data otherwise
cockpit_seat:
    pushad
    lea edi, [esi + 0x1a38]
    cmp dword ptr [edi], 0x6ebdf0
    jne cs_done
    lea edx, [ebp + {D['MIRROR']}]
    mov ebx, dword ptr [ebp + {D['PATCHIDX']}]
    test ebx, ebx
    jz cs_off
    cmp eax, ebx
    jne cs_off
    mov ecx, dword ptr [edi + 0x194]
    cmp ecx, edx
    je cs_done
    test ecx, ecx
    jz cs_done
    mov dword ptr [ebp + {D['SAVEDPTR']}], ecx
    mov eax, dword ptr [ecx]
    xor eax, 0x80000000
    mov dword ptr [edx], eax
    mov eax, dword ptr [ecx + 4]
    mov dword ptr [edx + 4], eax
    mov eax, dword ptr [ecx + 8]
    mov dword ptr [edx + 8], eax
    mov eax, dword ptr [ecx + 0xc]
    xor eax, 0x80000000
    mov dword ptr [edx + 0xc], eax
    mov eax, dword ptr [ecx + 0x10]
    mov dword ptr [edx + 0x10], eax
    mov eax, dword ptr [ecx + 0x14]
    mov dword ptr [edx + 0x14], eax
    mov dword ptr [edi + 0x194], edx
    jmp cs_done
cs_off:
    cmp dword ptr [edi + 0x194], edx
    jne cs_done
    mov ecx, dword ptr [ebp + {D['SAVEDPTR']}]
    mov dword ptr [edi + 0x194], ecx
cs_done:
    popad
    ret

apply_slot:
    push esi
    push edi
    push ecx
    push edx
    imul edx, eax, {SLOT_PARAMS}
    lea esi, [ebp + edx + {D['PARAMS']}]
    mov edi, {CAVE + 0x08}
    mov ecx, 11
    rep movsd dword ptr es:[edi], dword ptr [esi]
    mov edi, {CAVE + 0x50}
    mov ecx, 12
    rep movsd dword ptr es:[edi], dword ptr [esi]
    cmp dword ptr [{CAVE + 0x68}], 0
    jne fov_kept
    mov edx, dword ptr [ebp + {D['MGR']}]
    test edx, edx
    jz fov_kept
    mov dword ptr [edx + 0x510 + 0x3b0], 0x42700000
fov_kept:
    pop edx
    pop ecx
    pop edi
    pop esi
    ret

; eax = wanted height, ebx = address of a (font, height) pair: (re)creates the font when the
; height changed; returns eax = the font or 0
ensure_font:
    cmp eax, dword ptr [ebx + 4]
    jne ef_new
    mov eax, dword ptr [ebx]
    ret
ef_new:
    push eax
    mov ecx, dword ptr [ebx]
    test ecx, ecx
    jz ef_noold
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
    mov dword ptr [ebx], 0
ef_noold:
    pop eax
    mov dword ptr [ebx + 4], eax
    mov edx, dword ptr [ebp + {D['PCREATE']}]
    test edx, edx
    jnz ef_have
    lea ecx, [ebp + {D['S_DLL']}]
    push ecx
    call dword ptr [0x6741f4]
    test eax, eax
    jz ef_fail
    lea ecx, [ebp + {D['S_FN']}]
    push ecx
    push eax
    call dword ptr [0x674204]
    test eax, eax
    jz ef_fail
    mov dword ptr [ebp + {D['PCREATE']}], eax
    mov edx, eax
ef_have:
    push ebx
    lea ecx, [ebp + {D['S_FACE']}]
    push ecx
    push 0
    push 4
    push 0
    push 1
    push 0
    push 1
    push 700
    push 0
    push dword ptr [ebx + 4]
    push dword ptr [0x7ed10c]
    call edx
    test eax, eax
    jl ef_fail
    mov eax, dword ptr [ebx]
    ret
ef_fail:
    mov dword ptr [ebx], 0
    mov dword ptr [ebx + 4], 0
    xor eax, eax
    ret

; [TEXT] at [TOP], centred: a dark outline, then the text; eax = font height, ecx = colour, ebx = font
draw_outlined:
    push ecx
    xor edx, edx
    mov ecx, 22
    div ecx
    test eax, eax
    jnz t_ok
    inc eax
t_ok:
    mov edi, eax
    imul eax, eax, 7
    xor edx, edx
    mov ecx, 10
    div ecx
    test eax, eax
    jnz d_ok
    inc eax
d_ok:
    mov dword ptr [ebp + {D['DIAG']}], eax
    mov ecx, edi
    neg ecx
    xor edx, edx
    call outline_at
    mov ecx, edi
    xor edx, edx
    call outline_at
    xor ecx, ecx
    mov edx, edi
    neg edx
    call outline_at
    xor ecx, ecx
    mov edx, edi
    call outline_at
    mov ecx, dword ptr [ebp + {D['DIAG']}]
    mov edx, ecx
    call outline_at
    mov ecx, dword ptr [ebp + {D['DIAG']}]
    mov edx, ecx
    neg edx
    call outline_at
    mov ecx, dword ptr [ebp + {D['DIAG']}]
    mov edx, ecx
    neg ecx
    call outline_at
    mov ecx, dword ptr [ebp + {D['DIAG']}]
    neg ecx
    mov edx, ecx
    call outline_at
    xor ecx, ecx
    xor edx, edx
    pop eax
    call draw_at
    ret

outline_at:
    mov eax, 0xd0000000
; ecx = dx, edx = dy, eax = colour, ebx = font, ebp = base; text top at [TOP] + dy
draw_at:
    push esi
    mov dword ptr [ebp + {D['RECT']}], ecx
    mov esi, dword ptr [ebp + {D['TOP']}]
    add esi, edx
    mov dword ptr [ebp + {D['RECT'] + 4}], esi
    mov esi, dword ptr [0x7edb74]
    add esi, ecx
    mov dword ptr [ebp + {D['RECT'] + 8}], esi
    mov esi, dword ptr [0x7edb78]
    add esi, edx
    mov dword ptr [ebp + {D['RECT'] + 12}], esi
    push eax
    push 0x21
    lea esi, [ebp + {D['RECT']}]
    push esi
    push -1
    push dword ptr [ebp + {D['TEXT']}]
    push 0
    push ebx
    mov esi, dword ptr [ebx]
    call dword ptr [esi + 0x38]
    pop esi
    ret

; per frame: when no controllable camera is on, reset the controls (the cameras read the mouse
; themselves, in their update wrappers below)
controls_idle:
    mov esi, dword ptr [0x9eb4ec]
    test esi, esi
    jz controls
    add esi, 0x18
    mov edi, dword ptr [esi + 0x190]
    lea eax, [esi + 0xeec]
    cmp edi, eax
    je ci_ret
    lea eax, [esi + 0xc78]
    cmp edi, eax
    je ci_ret
    lea eax, [esi + 0x1d68]
    cmp edi, eax
    je ci_ret
    jmp controls
ci_ret:
    ret

; ---- mouse / keyboard for the car rotate and free cams (only with the game in front) ----
controls:
    mov esi, dword ptr [0x9eb4ec]
    test esi, esi
    jz c_off
    add esi, 0x18
    cmp dword ptr [esi + 0x510], 0x6eb808
    jne c_off
    mov edi, dword ptr [esi + 0x190]
    lea eax, [esi + 0xeec]
    mov ebx, 1
    cmp edi, eax
    je c_mode
    lea eax, [esi + 0xc78]
    mov ebx, 2
    cmp edi, eax
    je c_mode
    lea eax, [esi + 0x1d68]
    cmp edi, eax
    je c_mode
    mov dword ptr [ebp + {D['CTRLSTATE']}], 1
    jmp c_off
c_mode:
    cmp dword ptr [ebp + {D['PFORE']}], 0
    jne c_have
    lea ecx, [ebp + {D['S_USER32']}]
    push ecx
    call dword ptr [0x6741f4]
    test eax, eax
    jz c_off
    mov edx, eax
    push edx
    lea ecx, [ebp + {D['S_GETCUR']}]
    push ecx
    push edx
    call dword ptr [0x674204]
    pop edx
    mov dword ptr [ebp + {D['PGETCUR']}], eax
    push edx
    lea ecx, [ebp + {D['S_SETCUR']}]
    push ecx
    push edx
    call dword ptr [0x674204]
    pop edx
    mov dword ptr [ebp + {D['PSETCUR']}], eax
    push edx
    lea ecx, [ebp + {D['S_KEY']}]
    push ecx
    push edx
    call dword ptr [0x674204]
    pop edx
    mov dword ptr [ebp + {D['PKEY']}], eax
    push edx
    lea ecx, [ebp + {D['S_WTPID']}]
    push ecx
    push edx
    call dword ptr [0x674204]
    pop edx
    mov dword ptr [ebp + {D['PWTPID']}], eax
    lea ecx, [ebp + {D['S_K32']}]
    push edx
    push ecx
    call dword ptr [0x6741f4]
    pop edx
    test eax, eax
    jz c_fail
    lea ecx, [ebp + {D['S_CURPID']}]
    push edx
    push ecx
    push eax
    call dword ptr [0x674204]
    pop edx
    mov dword ptr [ebp + {D['PCURPID']}], eax
    lea ecx, [ebp + {D['S_FORE']}]
    push ecx
    push edx
    call dword ptr [0x674204]
    mov dword ptr [ebp + {D['PFORE']}], eax
    cmp dword ptr [ebp + {D['PGETCUR']}], 0
    je c_fail
    cmp dword ptr [ebp + {D['PSETCUR']}], 0
    je c_fail
    cmp dword ptr [ebp + {D['PKEY']}], 0
    je c_fail
    cmp dword ptr [ebp + {D['PWTPID']}], 0
    je c_fail
    cmp dword ptr [ebp + {D['PCURPID']}], 0
    je c_fail
    test eax, eax
    jnz c_have
c_fail:
    mov dword ptr [ebp + {D['PFORE']}], 0
    mov dword ptr [ebp + {D['CTRLSTATE']}], 2
    jmp c_off
c_have:
    call dword ptr [ebp + {D['PFORE']}]
    lea ecx, [ebp + {D['PIDTMP']}]
    mov dword ptr [ecx], 0
    push ecx
    push eax
    call dword ptr [ebp + {D['PWTPID']}]
    call dword ptr [ebp + {D['PCURPID']}]
    cmp eax, dword ptr [ebp + {D['PIDTMP']}]
    je c_front
    mov dword ptr [ebp + {D['CTRLSTATE']}], 3
    jmp c_off
c_front:
    mov dword ptr [ebp + {D['CTRLSTATE']}], 4
    mov dword ptr [ebp + {D['KEYDBG']}], 0
    mov eax, dword ptr [0x7edb74]
    shr eax, 1
    mov dword ptr [ebp + {D['CX']}], eax
    mov eax, dword ptr [0x7edb78]
    shr eax, 1
    mov dword ptr [ebp + {D['CY']}], eax
    lea ecx, [ebp + {D['PT']}]
    push ecx
    call dword ptr [ebp + {D['PGETCUR']}]
    xor eax, eax
    mov dword ptr [ebp + {D['DX']}], eax
    mov dword ptr [ebp + {D['DY']}], eax
    cmp dword ptr [ebp + {D['NEEDCENTER']}], 0
    jne c_center
    mov eax, dword ptr [ebp + {D['PT']}]
    sub eax, dword ptr [ebp + {D['CX']}]
    mov dword ptr [ebp + {D['DX']}], eax
    mov eax, dword ptr [ebp + {D['PT'] + 4}]
    sub eax, dword ptr [ebp + {D['CY']}]
    mov dword ptr [ebp + {D['DY']}], eax
c_center:
    mov dword ptr [ebp + {D['NEEDCENTER']}], 0
    push dword ptr [ebp + {D['CY']}]
    push dword ptr [ebp + {D['CX']}]
    call dword ptr [ebp + {D['PSETCUR']}]
    mov dword ptr [ebp + {D['ACTIVE']}], 1
    push 0xc0
    call dword ptr [ebp + {D['PKEY']}]
    push eax
    push 0xdc
    call dword ptr [ebp + {D['PKEY']}]
    pop ecx
    or eax, ecx
    and eax, 0x8000
    mov ecx, dword ptr [ebp + {D['RESETPREV']}]
    mov dword ptr [ebp + {D['RESETPREV']}], eax
    test eax, eax
    jz c_noreset
    test ecx, ecx
    jnz c_noreset
    mov ecx, edi
    mov eax, dword ptr [edi]
    call dword ptr [eax + 4]
    call {SM_RESET}
c_noreset:
    cvtsi2ss xmm0, dword ptr [ebp + {D['DX']}]
    cvtsi2ss xmm1, dword ptr [ebp + {D['DY']}]
    call {SM_MOUSE}
    mulss xmm0, dword ptr [ebp + {D['K_SENS']}]
    mulss xmm1, dword ptr [ebp + {D['K_SENS']}]
    cmp ebx, 1
    jne c_free
    movss xmm1, dword ptr [ebp + {D['SMXY'] + 4}]
    mulss xmm1, dword ptr [ebp + {D['K_TILTS']}]
    movss xmm2, dword ptr [esi]
    xorps xmm3, xmm3
    comiss xmm2, xmm3
    jbe c_zero_rot
    movss xmm3, xmm2
    mulss xmm3, dword ptr [ebp + {D['K_ORBIT']}]
    divss xmm0, xmm3
    mulss xmm2, dword ptr [ebp + {D['K_TILT']}]
    divss xmm1, xmm2
    jmp c_rot_ok
c_zero_rot:
    xorps xmm0, xmm0
    xorps xmm1, xmm1
c_rot_ok:
    movss dword ptr [esi + 0x1a8], xmm0
    movss dword ptr [esi + 0x1b8], xmm1
    push 0x53
    push 0x57
    call keypair
    lea eax, [ebp + {D['KAX'] + 12}]
    call {SM_KEY}
    movss dword ptr [esi + 0x1ac], xmm0
    xorps xmm0, xmm0
    movss dword ptr [esi + 0x1bc], xmm0
    movss xmm2, dword ptr [esi]
    xorps xmm3, xmm3
    comiss xmm2, xmm3
    jbe c_rot_done
    mulss xmm2, dword ptr [ebp + {D['K_TILT']}]
    mov eax, dword ptr [esi + 0x50c]
    test eax, eax
    jz c_rot_done
    movss xmm0, dword ptr [esi + 0x1ac]
    mulss xmm0, xmm2
    addss xmm0, dword ptr [edi + 0x20]
    addss xmm0, dword ptr [eax]
    maxss xmm0, dword ptr [ebp + {D['K_RDMIN']}]
    minss xmm0, dword ptr [ebp + {D['K_RDMAX']}]
    subss xmm0, dword ptr [eax]
    subss xmm0, dword ptr [edi + 0x20]
    divss xmm0, xmm2
    movss dword ptr [esi + 0x1ac], xmm0
    movss xmm0, dword ptr [esi + 0x1b8]
    mulss xmm0, xmm2
    addss xmm0, dword ptr [edi + 0x48]
    addss xmm0, dword ptr [eax + 4]
    maxss xmm0, dword ptr [ebp + {D['K_RHMIN']}]
    minss xmm0, dword ptr [ebp + {D['K_RHMAX']}]
    subss xmm0, dword ptr [eax + 4]
    subss xmm0, dword ptr [edi + 0x48]
    divss xmm0, xmm2
    movss dword ptr [esi + 0x1b8], xmm0
c_rot_done:
    ret
c_free:
    movss xmm2, dword ptr [edi + 0x230]
    xorps xmm3, xmm3
    comiss xmm2, xmm3
    jbe c_free_r1
    divss xmm0, xmm2
    divss xmm1, xmm2
    jmp c_free_r
c_free_r1:
    mulss xmm0, dword ptr [ebp + {D['K_FREE']}]
    mulss xmm1, dword ptr [ebp + {D['K_FREE']}]
    jmp c_pitch_ok
c_free_r:
    movss xmm3, xmm1
    mulss xmm3, xmm2
    addss xmm3, dword ptr [edi + 0x268]
    minss xmm3, dword ptr [ebp + {D['K_PITCH']}]
    maxss xmm3, dword ptr [ebp + {D['K_PITCHN']}]
    subss xmm3, dword ptr [edi + 0x268]
    divss xmm3, xmm2
    movss xmm1, xmm3
c_pitch_ok:
    movss dword ptr [esi + 0x1a8], xmm0
    movss dword ptr [esi + 0x1ac], xmm1
    xorps xmm0, xmm0
    movss dword ptr [esi + 0x1c4], xmm0
    push 0x57
    push 0x53
    call keypair
    lea eax, [ebp + {D['KAX']}]
    call {SM_KEY}
    movss dword ptr [esi + 0x1b0], xmm0
    push 0x44
    push 0x41
    call keypair
    lea eax, [ebp + {D['KAX'] + 4}]
    call {SM_KEY}
    movss dword ptr [esi + 0x1b4], xmm0
    push 0x20
    push 0x11
    call keypair
    lea eax, [ebp + {D['KAX'] + 8}]
    call {SM_KEY}
    movss dword ptr [esi + 0x1b8], xmm0
    ret
c_off:
    mov dword ptr [ebp + {D['NEEDCENTER']}], 1
    cmp dword ptr [ebp + {D['ACTIVE']}], 0
    je c_ret
    mov dword ptr [ebp + {D['ACTIVE']}], 0
    call {SM_RESET}
    mov esi, dword ptr [ebp + {D['MGR']}]
    test esi, esi
    jz c_ret
    xor eax, eax
    mov dword ptr [esi + 0x1a8], eax
    mov dword ptr [esi + 0x1ac], eax
    mov dword ptr [esi + 0x1b0], eax
    mov dword ptr [esi + 0x1b4], eax
    mov dword ptr [esi + 0x1b8], eax
    mov dword ptr [esi + 0x1bc], eax
    mov dword ptr [esi + 0x1c0], eax
    mov dword ptr [esi + 0x1c4], eax
c_ret:
    ret

; stdcall keypair(posKey pushed first, negKey pushed second): xmm0 = (pos down) - (neg down)
keypair:
    push ebx
    xor ebx, ebx
    push dword ptr [esp + 12]
    call dword ptr [ebp + {D['PKEY']}]
    or word ptr [ebp + {D['KEYDBG']}], ax
    test ax, 0x8000
    jz kp_neg
    inc ebx
kp_neg:
    push dword ptr [esp + 8]
    call dword ptr [ebp + {D['PKEY']}]
    test ax, 0x8000
    jz kp_done
    dec ebx
kp_done:
    cvtsi2ss xmm0, ebx
    pop ebx
    ret 8

rot_wrap:
    pushfd
    pushad
    call r_base
r_base:
    pop ebp
    sub ebp, ROTBASE
    call controls
    popad
    popfd
    push 0x5f1e00
    ret

free_wrap:
    pushfd
    pushad
    call f_base
f_base:
    pop ebp
    sub ebp, FREEBASE
    call controls
    popad
    popfd
    push 0x5f3fe0
    ret

lost_hook:
    pushfd
    pushad
    call l_base
l_base:
    pop ebp
    sub ebp, LOSTBASE
    mov ecx, dword ptr [ebp + {D['FONT']}]
    test ecx, ecx
    jz l_none
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
    mov dword ptr [ebp + {D['FONT']}], 0
    mov dword ptr [ebp + {D['FONTH']}], 0
l_none:
    mov ecx, dword ptr [ebp + {D['FONT2']}]
    test ecx, ecx
    jz l_none2
    push ecx
    mov edx, dword ptr [ecx]
    call dword ptr [edx + 8]
    mov dword ptr [ebp + {D['FONT2']}], 0
    mov dword ptr [ebp + {D['FONT2']} + 4], 0
l_none2:
    popad
    popfd
    push 0x591220
    ret
"""

asm = strip(asm)
def entry(label):
    t = asm.split(label + ':')[0]
    for k in ('ROTBASE', 'FREEBASE', 'LOSTBASE'): t = t.replace(k, '65536')
    return CODE + len(bytes(ks.asm(t, addr=CODE)[0]))
rot_off, free_off, lost_off = entry('rot_wrap'), entry('free_wrap'), entry('lost_hook')
enc, _ = ks.asm(asm.replace('ROTBASE', str(rot_off + 7)).replace('FREEBASE', str(free_off + 7)).replace('LOSTBASE', str(lost_off + 7)), addr=CODE)
code = bytes(enc)
for o in (rot_off, free_off): assert code[o - CODE:o - CODE + 2] == bytes([0x9c, 0x60])
assert code[:2] == b'\x9c\x60', code[:4].hex()
assert code[lost_off - CODE:lost_off - CODE + 2] == b'\x9c\x60'
assert len(code) <= 0x1000
out = dict(code=code.hex(), codeOff=CODE, drawOff=CODE, lostOff=lost_off, rotOff=rot_off, freeOff=free_off, size=SIZE, data=D,
           slotParams=SLOT_PARAMS, maxSlots=MAX_SLOTS, maxGameCams=MAX_GAMECAMS,
           code2=code2.hex(), code2Off=CODE2, blendOff=blend_off, consts2=C2)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cycle.json'), 'w'), indent=1)
print('code bytes', len(code), 'lost', hex(lost_off), 'rot', hex(rot_off), 'free', hex(free_off),
      ' second area: bytes', len(code2), 'of', CODE2_END - CODE2, 'blend', hex(blend_off))
