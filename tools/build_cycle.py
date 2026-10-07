"""Builds the 'camera cycle + name popup + free-camera controls' block for SEGA Rally 3
(Rally.exe v3.8.4.1).

The block is allocated by patch.ps1 inside the running game (VirtualAllocEx) and is
position-independent: code finds its own base with call/pop. Layout (offsets from base):

  0x000  data (settings, state, strings, per-slot names, colours and camera parameters)
  0x1000 code: DRAW (Present hook) and LOST (device-lost hook)
  0x2000 game cameras (names, list entries, offsets, extras, colours) and the driver-seat
         copy of the cockpit cam's eye

Hooks (5-byte call rel32, written by patch.ps1):
  0x591C4D  mov eax,[0x7ED10C]  (just before EndScene/Present)  -> call DRAW
  0x591B01  call 0x591220       (frees D3D resources before Reset) -> call LOST

Game facts used (found in the disassembly):
  [0x9EB4EC] + 0x18 = camera manager of the local player; [mgr+0] = frame time (float)
  mgr+0x510 chase camera (vtable 0x6EB808), mgr+0x8C4 far chase (vtable 0x6EB8B8)
  mgr+0x190 = the camera in use
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
"""
import json, os
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
         HILITE=0x226C, REOPEN=0x2270, REOPENPATH=0x2274, MODESEL=0x2278)
SLOT_PARAMS = 0x5C          # 11 + 12 dwords copied into the cave
MAX_SLOTS = 21              # the game's list holds 21 pointers
MAX_GAMECAMS = 12
CODE = 0x1000
SIZE = 0x3000
CAVE = 0x673C80

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
c_noreset:
    cvtsi2ss xmm0, dword ptr [ebp + {D['DX']}]
    cvtsi2ss xmm1, dword ptr [ebp + {D['DY']}]
    mulss xmm0, dword ptr [ebp + {D['K_SENS']}]
    mulss xmm1, dword ptr [ebp + {D['K_SENS']}]
    cmp ebx, 1
    jne c_free
    cvtsi2ss xmm1, dword ptr [ebp + {D['DY']}]
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
    movss dword ptr [esi + 0x1b0], xmm0
    push 0x44
    push 0x41
    call keypair
    movss dword ptr [esi + 0x1b4], xmm0
    push 0x20
    push 0x11
    call keypair
    movss dword ptr [esi + 0x1b8], xmm0
    ret
c_off:
    mov dword ptr [ebp + {D['NEEDCENTER']}], 1
    cmp dword ptr [ebp + {D['ACTIVE']}], 0
    je c_ret
    mov dword ptr [ebp + {D['ACTIVE']}], 0
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

ks = Ks(KS_ARCH_X86, KS_MODE_32)
asm = "\n".join(l.split(';')[0].rstrip() for l in asm.splitlines() if l.split(';')[0].strip())
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
           slotParams=SLOT_PARAMS, maxSlots=MAX_SLOTS, maxGameCams=MAX_GAMECAMS)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cycle.json'), 'w'), indent=1)
print('code bytes', len(code), 'lost', hex(lost_off), 'rot', hex(rot_off), 'free', hex(free_off))
