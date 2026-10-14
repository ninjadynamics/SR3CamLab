"""Runs the camera-cycle block (cycle.json) on an emulated x86 against a fake SEGA Rally 3:
camera manager, cave, globals, and stubbed Win32 / D3DX calls."""
import json, struct, math, os
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

j = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cycle.json')))
D = j['data']; CODE = bytes.fromhex(j['code'])
BASE = 0x20000000; MGR_OWNER = 0x30000000; MGR = MGR_OWNER + 0x18; CAVE = 0x673C80
STUB = 0x40000000; FONT = 0x41000000; FONTVT = 0x41001000; STACK = 0x50000000; DONE = 0x60000000
u = Uc(UC_ARCH_X86, UC_MODE_32)
for a, n in ((0x400000, 0x800000), (BASE, json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cycle.json")))["size"]), (MGR_OWNER, 0x10000), (STUB, 0x1000), (FONT, 0x2000),
             (STACK - 0x10000, 0x20000), (DONE, 0x1000)):
    u.mem_map(a, n)
w32 = lambda a, v: u.mem_write(a, struct.pack('<I', v & 0xffffffff))
r32 = lambda a: struct.unpack('<I', u.mem_read(a, 4))[0]
rf = lambda a: struct.unpack('<f', u.mem_read(a, 4))[0]
wf = lambda a, v: u.mem_write(a, struct.pack('<f', v))
cstr = lambda a: bytes(u.mem_read(a, 64)).split(b'\0')[0].decode()

# ---- the block, as patch.ps1 writes it
blk = bytearray(0x2264)
def put(o, b): blk[o:o + len(b)] = b
def s32(o, v): put(o, struct.pack('<i', v))
def name(o, t, n=32): put(o, t.encode().ljust(n, b'\0'))
put(0, b'SR3V'); s32(0x14, 120); s32(0x18, 48); s32(0x1C, -1)
slots = [('Game: Chase cam', 0xFFFFFFFF, 15, 90), ('CamLab: Daytona', 0xFF9CFF3A, 65, 92), ('CamLab: Chase', 0xFF9CFF3A, 30, 50),
         ('CamLab: Chase Far', 0xFF9CFF3A, 30, 50), ('CamLab: Drone', 0xFF9CFF3A, 30, 50)]
s32(0x20, len(slots)); s32(0x24, 1); s32(0x28, 0); s32(0xB0, 1)
name(0x60, 'd3dx9_41.dll', 16); name(0x70, 'D3DXCreateFontA', 16); name(0x80, 'Arial'); name(0xE0, 'Camera', 16)
cams = [(0x1700, 'Game: Bumper cam', 0xFFFFFFFF), (0x189C, 'Game: Bonnet cam', 0xFFFFFFFF), (0x8C4, 'Debug: Chase cam far', 0xFFFF9A2E),
        (0x1A38, 'Debug: Cockpit cam', 0xFFFF9A2E), (0x80001A38, 'Debug: Cockpit cam (patched)', 0xFFFF9A2E), (0x1BD0, 'Debug: Wheel cam', 0xFFFF9A2E), (0xEEC, 'Debug: Car rotate cam', 0xFFFF9A2E),
        (0xC78, 'Debug: Free cam', 0xFFFF9A2E), (0x1D68, 'Debug: Car free cam', 0xFFFF9A2E)]
for i in range(12): s32(0x21B0 + 4 * i, -1); s32(0x21E0 + 4 * i, -1)
for i, (o, t, c) in enumerate(cams):
    put(0x21B0 + 4 * i, struct.pack('<I', o)); name(0x2000 + 32 * i, t); put(0x2210 + 4 * i, struct.pack('<I', c))
for i, h in enumerate([0x8C4, 0x1A38, 0x80001A38, 0x1BD0, 0xEEC, 0xC78, 0x1D68]): put(0x21E0 + 4 * i, struct.pack('<I', h & 0xffffffff))
for i, (t, c, kmin, kmax) in enumerate(slots):
    name(0x100 + 32 * i, t); put(0xE00 + 4 * i, struct.pack('<I', c))
    p = 0x500 + 0x5C * i
    put(p + 0x10, struct.pack('<ff', kmin, kmax))                # cave+0x18/0x1C = kmin/kmax
    put(p + 0x2C, struct.pack('<f', 7.5 if i == 0 else 1.0))     # cave+0x50 = multiplier
name(0xEA0, 'user32.dll', 16); name(0xEB0, 'GetCursorPos', 16); name(0xEC0, 'SetCursorPos', 16)
name(0xED0, 'GetAsyncKeyState'); name(0xEF0, 'GetForegroundWindow')
put(0xF10, struct.pack('<ffff', 0.0025, math.pi / 2, 10.0, 1.0))
name(0xF40, 'GetWindowThreadProcessId'); name(0xF60, 'kernel32.dll', 16); name(0xF70, 'GetCurrentProcessId')
for i in range(1, 5): put(0x500 + 0x5C * i + 0x44, struct.pack('<i', 1))
name(0xFB0, 'Use mouse/WASD to navigate'); put(0xF90, struct.pack('<ff', 1.5706, -1.5706)); put(0xFE0, struct.pack('<4f', 3.0, 30.0, 0.5, 20.0)); put(0xFD0, struct.pack('<f', -0.01))   # profiles: own framing on (cave+0x68)
u.mem_write(BASE, bytes(blk)); u.mem_write(BASE + 0x1000, CODE)
assert len(CODE) <= 0x1000
# the second code area. The smoothing and the blend stay off (their settings 0, as in a block that never had them)
# for every check up to "NEW CHECKS" below: those are the checks of the block as it was, and must not change
u.mem_write(BASE + j['code2Off'], bytes.fromhex(j['code2']))

# ---- the fake game
w32(0x9EB4EC, MGR_OWNER); wf(MGR, 1 / 60)
vt = {0x510: 0x6EB808, 0x8C4: 0x6EB8B8, 0x1700: 0x6EBD00, 0x189C: 0x6EBD78, 0x1A38: 0x6EBDF0, 0x1BD0: 0x6EBC88,
      0xEEC: 0x6EBB30, 0xC78: 0x6ECB98, 0x1D68: 0x6ECC88}
for o, v in vt.items(): w32(MGR + o, v)
CFG = MGR_OWNER + 0x9000; u.mem_write(CFG, struct.pack('<2f', 7.0, 2.3)); w32(MGR + 0x50C, CFG)   # base distance / height
EYE = MGR_OWNER + 0x8000; u.mem_write(EYE, struct.pack('<6f', 0.35, 0.95, -0.1, 0.35, 0.95, 0.9)); w32(MGR + 0x1A38 + 0x194, EYE)
wf(MGR + 0xC78 + 0x230, 0.02); wf(MGR + 0x1D68 + 0x230, 0.02)            # free cams' rotation speed
w32(MGR + 0x22C, 3); w32(MGR + 0x230, 0)
for i, o in enumerate((0x510, 0x1700, 0x189C)): w32(MGR + 0x234 + 4 * i, MGR + o)
w32(MGR + 0x190, MGR + 0x510)
w32(0x7ED10C, 0xD3D00000); w32(0x7EDB74, 3840); w32(0x7EDB78, 2160); w32(0xA339A4, 0x1234)   # TeknoParrot's window differs

# ---- stubs (stdcall: pop the return address and the arguments)
stubs = {}; log = []; state = dict(cursor=(1920, 1080), keys=set(), fore=0x5555)
def stub(addr, nargs, fn):
    stubs[addr] = (nargs, fn); u.mem_write(addr, b'\xc3')
def args(n): esp = u.reg_read(UC_X86_REG_ESP); return [r32(esp + 4 + 4 * i) for i in range(n)]
names = {'GetCursorPos': STUB + 0x10, 'SetCursorPos': STUB + 0x20, 'GetAsyncKeyState': STUB + 0x30,
         'GetForegroundWindow': STUB + 0x40, 'D3DXCreateFontA': STUB + 0x50,
         'GetWindowThreadProcessId': STUB + 0x80, 'GetCurrentProcessId': STUB + 0x90,
         'SetWindowLongW': STUB + 0xA0, 'CallWindowProcW': STUB + 0xB0}
def setwl(a): log.append(('SetWindowLongW', hex(a[0]), a[1], 'proc at block+%#x' % (a[2] - BASE))); state['wndproc'] = a[2]; return 0x45000000
def callwp(a): log.append(('CallWindowProcW', hex(a[0]), hex(a[1]), hex(a[2]), hex(a[3]), hex(a[4]))); return 77
stub(STUB + 0xA0, 3, setwl); stub(STUB + 0xB0, 5, callwp)
def wtpid(a):
    if a[1]: w32(a[1], 4242 if a[0] == 0x5555 else 7)
    return 1
stub(STUB + 0x80, 2, wtpid); stub(STUB + 0x90, 0, lambda a: 4242)
stub(STUB + 0x00, 1, lambda a: 0x77000000)                                # GetModuleHandleA
stub(STUB + 0x08, 2, lambda a: names.get(cstr(a[1]), 0))                  # GetProcAddress
def getcur(a): u.mem_write(a[0], struct.pack('<ii', *state['cursor'])); return 1
stub(STUB + 0x10, 1, getcur)
def setcur(a): log.append(('SetCursorPos', a[0], a[1])); state['cursor'] = (a[0], a[1]); return 1
stub(STUB + 0x20, 2, setcur)
stub(STUB + 0x30, 1, lambda a: 0x8000 if a[0] in state['keys'] else 0)
stub(STUB + 0x40, 0, lambda a: state['fore'])
def create(a): log.append(('D3DXCreateFontA', 'height', a[1], 'weight', a[3], 'face', cstr(a[10]))); w32(a[11], FONT); return 0
stub(STUB + 0x50, 12, create)
def release(a): log.append(('Release',)); return 0
def drawtext(a):
    rect = struct.unpack('<iiii', u.mem_read(a[4], 16))
    log.append(('DrawTextA', cstr(a[2]), 'rect', rect, 'fmt', hex(a[5]), 'colour', hex(a[6]))); return 1
stub(STUB + 0x60, 1, release); stub(STUB + 0x70, 7, drawtext)
w32(FONT, FONTVT); w32(FONTVT + 8, STUB + 0x60); w32(FONTVT + 0x38, STUB + 0x70)
w32(0x6741F4, STUB + 0x00); w32(0x674204, STUB + 0x08)

def on_code(uc, addr, size, _):
    if addr in stubs:
        n, fn = stubs[addr]
        ret = fn(args(n)); esp = uc.reg_read(UC_X86_REG_ESP)
        uc.reg_write(UC_X86_REG_EAX, ret & 0xffffffff)
        uc.reg_write(UC_X86_REG_EIP, r32(esp)); uc.reg_write(UC_X86_REG_ESP, esp + 4 + 4 * n)
    elif addr in (0x591220, 0x5F1E00, 0x5F3FE0):
        log.append(('jumped to %#x' % addr,)); uc.emu_stop()
u.hook_add(UC_HOOK_CODE, on_code)

def call(entry):
    esp = STACK; esp -= 4; w32(esp, DONE)
    u.reg_write(UC_X86_REG_ESP, esp); u.reg_write(UC_X86_REG_EBP, 0x11111111)
    u.emu_start(entry, DONE, count=200000)
    assert u.reg_read(UC_X86_REG_ESP) in (STACK, STACK - 4), hex(u.reg_read(UC_X86_REG_ESP))
def wrap(entry, title):
    log.clear(); call(BASE + entry)
    print(f'== {title}:', [l for l in log if l[0] != 'DrawTextA'])
def frame(title):
    log.clear(); call(BASE + j['drawOff'])
    eax = u.reg_read(UC_X86_REG_EAX)
    lst = [r32(MGR + 0x234 + 4 * i) - MGR for i in range(r32(MGR + 0x22C))]
    print(f'== {title}: eax={eax:#x} (device) list[{len(lst)}] idx={r32(MGR + 0x230)}  cave kmin/kmax={rf(CAVE + 0x18):g}/{rf(CAVE + 0x1C):g} mult={rf(CAVE + 0x50):g}  popup frames={r32(BASE + 0x10)}')
    for l in log: print('   ', l)
    return lst

def go(n):                                  # a View Change press: the block saw the index just before
    w32(BASE + 0x1C, (n - 1) % r32(MGR + 0x22C)); w32(MGR + 0x230, n)
def seat(title):
    frame(title); p = r32(MGR + 0x1A38 + 0x194)
    print('    name', repr(cstr(r32(BASE + 0x50))), 'colour', hex(r32(BASE + 0xE60)), 'PVS off', r32(0xA65794), ' cockpit eye', 'COPY' if p == BASE + 0x2240 else 'game' if p == EYE else hex(p),
          ['%g' % v for v in struct.unpack('<6f', u.mem_read(p, 24))])
lst = frame('race start (extension)')
print('    list offsets:', ' '.join(f'{o:X}' for o in lst))
frame('next frame (no change)')
go(4); seat('View Change -> idx 4 (CamLab: Chase)')
go(0); seat('idx 0 (Game: Chase cam): PVS on')
go(2); seat('idx 2 (Game: Bonnet cam): PVS on')
go(7); seat('idx 7 (far chase): stock settings 15/90 x7.5')
go(8); seat('idx 8 (cockpit)')
go(9); seat('idx 9 (cockpit, driver seat): eye x must be -0.35')
go(10); seat('idx 10 (wheel): eye back to the game data')
go(9); seat('idx 9 again')
go(8); seat('idx 8: back to the game data')
go(9); frame('idx 9'); w32(BASE + 0x28, 0)
lst = frame('live update: re-extend an extended list (must stay 14, cockpit twice)')
print('    list offsets:', ' '.join(f'{o:X}' for o in lst), ' patched idx', r32(BASE + 0x225C), ' eye', 'COPY' if r32(MGR + 0x1A38 + 0x194) == BASE + 0x2240 else 'game')
go(11); w32(MGR + 0x190, MGR + 0xEEC); state['cursor'] = (1950, 1100); frame('car rotate, first frame (centre)')
log.clear(); call(BASE + j['drawOff']); print('== car rotate popup, next frame: text drawn', sorted({(l[1], l[3][1]) for l in log if l[0] == 'DrawTextA'}), [l for l in log if l[0] == 'D3DXCreateFontA'])
wrap(j['rotOff'], 'car rotate update (centre)')
state['cursor'] = (1950, 1100); state['keys'] = {0x57}; frame('car rotate, mouse +30/+20, W held (frame)')
print('    axes after the frame only (must stay 0):', rf(MGR + 0x1A8))
wrap(j['rotOff'], 'car rotate update')
print('    axes orbit/zoom/tilt (W held):', rf(MGR + 0x1A8), rf(MGR + 0x1AC), rf(MGR + 0x1B8), ' expected', 30 * 0.0025 / (1 / 60 * math.pi / 2), -1.0, 20 * -0.01 / (1 / 60 * 10))
state['cursor'] = (1920, 1100); state['keys'] = {0x53}; wrap(j['rotOff'], 'car rotate update, mouse back 20 px, S held')
print('    axes orbit/zoom/tilt:', rf(MGR + 0x1A8), rf(MGR + 0x1AC), rf(MGR + 0x1B8), ' expected', 0, 1.0, 20 * -0.01 / (1 / 60 * 10))
ROT = MGR + 0xEEC
wf(ROT + 0x20, -3.9); wf(ROT + 0x48, 0.0); state['cursor'] = (1920, 1080); state['keys'] = {0x57}; wrap(j['rotOff'], 'car rotate: distance 3.1 m, W held (zoom in)')
d = 7.0 + -3.9 + rf(MGR + 0x1AC) * (1 / 60) * 10; print('    distance next frame %.3f (want 3.0, the limit; unclamped %.3f)' % (d, 7.0 - 3.9 - 10 / 60))
wf(ROT + 0x20, 0.0); wf(ROT + 0x48, -1.3); state['keys'] = set(); state['cursor'] = (1920, 1080 + 600); wrap(j['rotOff'], 'car rotate: height 1.0, mouse 600 px back')
h = 2.3 - 1.3 + rf(MGR + 0x1B8) * (1 / 60) * 10; print('    height next frame %.3f (want 0.5, the limit; unclamped %.3f)' % (h, 1.0 - 6))
wf(ROT + 0x48, 17.5); state['cursor'] = (1920, 1080 - 600); wrap(j['rotOff'], 'car rotate: height 19.8, mouse 600 px forward')
h = 2.3 + 17.5 + rf(MGR + 0x1B8) * (1 / 60) * 10; print('    height next frame %.3f (want 20, the limit; unclamped %.3f)' % (h, 19.8 + 6))
wf(ROT + 0x20, 0.0); wf(ROT + 0x48, 0.0); state['cursor'] = (1920, 1080)
RESETFN = STUB + 0xC0; RVT = 0x42000000; u.mem_map(RVT, 0x1000)
def camreset(a): log.append(('camera reset, this=%#x' % u.reg_read(UC_X86_REG_ECX),)); return 0
stubs[RESETFN] = (0, camreset); u.mem_write(RESETFN, bytes([0xC3]))
saved = r32(MGR + 0xEEC); w32(RVT + 4, RESETFN); w32(MGR + 0xEEC, RVT)
state['keys'] = {0xDC}; wrap(j['rotOff'], 'reset key pressed')
wrap(j['rotOff'], 'reset key still held (must not reset again)')
state['keys'] = set(); wrap(j['rotOff'], 'released'); state['keys'] = {0xC0}; wrap(j['rotOff'], '~ pressed again')
w32(MGR + 0xEEC, saved)
wf(MGR + 0xC78 + 0x268, 1.5); state['cursor'] = (1920, 1080 + 400)
w32(MGR + 0x190, MGR + 0xC78); frame('free cam: pitch 1.5 rad, mouse 400 px down'); wrap(j['freeOff'], 'free cam update')
print('    pitch would become', 1.5 + 0.02 * rf(MGR + 0x1AC), ' (stopper: want 1.5706, unclamped would be', 1.5 + 400 * 0.0025, ')')
wf(MGR + 0xC78 + 0x268, -1.5); state['cursor'] = (1920, 1080 - 400); wrap(j['freeOff'], 'free cam update, pitch -1.5, mouse 400 px up')
print('    pitch would become', -1.5 + 0.02 * rf(MGR + 0x1AC), ' (want -1.5706)')
wf(MGR + 0xC78 + 0x268, 0.0)
w32(MGR + 0x190, MGR + 0xC78); state['cursor'] = (1900, 1070); state['keys'] = {0x57, 0x41, 0x20}; frame('free cam (frame)'); wrap(j['freeOff'], 'free cam update, mouse -20/-10, W + A + Space')
print('    axes 1A8/1AC/1B0/1B4/1B8:', rf(MGR + 0x1A8), rf(MGR + 0x1AC), rf(MGR + 0x1B0), rf(MGR + 0x1B4), rf(MGR + 0x1B8), ' expected 1B0 +1 (W), 1B4 -1 (A), 1B8 +1')
print('    control state:', r32(BASE + 0xF30), 'keys seen', hex(r32(BASE + 0xF34)))
state['fore'] = 0x9999; state['cursor'] = (100, 100); wrap(j['freeOff'], 'free cam update, game not in front')
print('    control state:', r32(BASE + 0xF30))
print('    axes zeroed:', [rf(MGR + 0x1A8 + 4 * i) for i in range(8)], 'cursor untouched:', state['cursor'])
w32(MGR + 0x190, MGR + 0x510); state['fore'] = 0x5555; frame('back to chase')
print('    control state:', r32(BASE + 0xF30))
go(4); frame('CamLab: Chase again'); wf(MGR + 0x510 + 0x3B0, 72.0)
go(0); frame('back to Chase cam after a 72 deg profile')
print('    chase fov now', rf(MGR + 0x510 + 0x3B0), '(want 60)')
go(3); w32(MGR + 0x190, MGR + 0x510); frame('CamLab: Daytona selected')
w32(MGR + 0x230, 0); frame('the game resets its camera to index 0 (new stage / continue)')
print('    index now', r32(MGR + 0x230), '(want 3: the reset is undone)  camera in use +%X' % (r32(MGR + 0x190) - MGR))
go(4); frame('View Change still steps forward'); print('    index', r32(MGR + 0x230), '(want 4)')
w32(MGR + 0x230, 13); frame('View Change from 13 wraps'); w32(BASE + 0x1C, 13); w32(MGR + 0x230, 0); frame('13 -> 0 is a View Change')
print('    index', r32(MGR + 0x230), '(want 0)')
go(3); frame('back on Daytona')
log.clear(); call(BASE + j['lostOff']); print('== device lost hook:', log, ' font now', hex(r32(BASE + 8)))
w32(MGR + 0x22C, 3); w32(MGR + 0x230, 0)
for i, o in enumerate((0x510, 0x1700, 0x189C)): w32(MGR + 0x234 + 4 * i, MGR + o)
lst = frame('next race (game rebuilt its list)')
print('    list offsets:', ' '.join(f'{o:X}' for o in lst))
print('    index after the rebuild', r32(MGR + 0x230), '(want 3: Daytona kept, not the launch slot)')

# ---- track switcher support: the video-load request and the hint text override
loads = []
stub(0x621600, 0, lambda a: loads.append(1) or 0)
w32(BASE + D['LOADVIDEOS'], 1)
u.mem_write(BASE + 0x2400, b'Press VIEW CHANGE to select alternative tracks\0')
w32(BASE + D['PHINT'], BASE + 0x2400); w32(BASE + D['HINT'], 1); w32(BASE + D['FRAMES'], 5)
frame('video-load request + own hint text')
frame('next frame')
print('    video loader called', len(loads), 'time(s) (want 1), request now', r32(BASE + D['LOADVIDEOS']), '(want 0)')
print('    hint drawn:', sorted(set(l[1] for l in log if l[0] == 'DrawTextA' and 'VIEW' in l[1])))

# ---- track switcher support: the highlighted stage and a card video opened in its own object
seen = []
stub(0x5470d0, 0, lambda a: seen.append(('hash', cstr(u.reg_read(UC_X86_REG_ECX)), args(1)[0])) or 0x1234)
stub(0x606490, 0, lambda a: seen.append(('selector', hex(u.reg_read(UC_X86_REG_EDI)))) or 0x55AA)
frame('no menu system: no selector asked')
print('    highlighted', hex(r32(BASE + D['HILITE'])), '(want 0xffffffff), calls', seen)
w32(0x9C0F48, 1)
frame('stage selector asked')
print('    highlighted', hex(r32(BASE + D['HILITE'])), '(want 0x55aa), calls', seen)
VOBJ = 0xAD2F90 + 5 * 0x16C; COM = RVT + 0x400
def com(a, name): seen.append((name, hex(a[0]))); return 0
stub(STUB + 0xD0, 1, lambda a: com(a, 'Release')); stub(STUB + 0xD4, 1, lambda a: com(a, 'Run')); stub(STUB + 0xD8, 1, lambda a: com(a, 'Stop'))
w32(COM + 8, STUB + 0xD0); w32(COM + 0x1C, STUB + 0xD4); w32(COM + 0x24, STUB + 0xD8)
for k, o in enumerate((0x11C, 0x120, 0x124, 0x128, 0x12C, 0x144)): w32(COM + 0x100 + 4 * k, COM); w32(VOBJ + o, COM + 0x100 + 4 * k)
w32(VOBJ, 1); w32(VOBJ + 4, 1); w32(VOBJ + 8, 1); w32(VOBJ + 0x130, 0x777)
def vopen(a):
    seen.append(('open', cstr(u.reg_read(UC_X86_REG_ECX)), hex(u.reg_read(UC_X86_REG_EDI) - 0xAD2F90), 'object closed' if r32(VOBJ + 4) == 0 and r32(VOBJ + 0x144) == 0 and r32(VOBJ + 0x120) == 0 else 'OBJECT NOT CLOSED'))
    w32(VOBJ + 0x120, COM + 0x104); w32(VOBJ + 4, 1); return 1
stub(0x4ddc80, 0, vopen); stub(0x4de370, 0, lambda a: seen.append(('play',) + tuple(args(3))) or 0)
u.mem_write(BASE + 0x2500, b'.\frontend\PC\Videos\LANG_ENGLISH_CA1.wmv\0')
w32(BASE + D['REOPENPATH'], BASE + 0x2500); w32(BASE + D['REOPEN'], 6); seen.clear()
frame('card video reopened in object 5')
for x in seen: print('    ', x)
print('    request now', r32(BASE + D['REOPEN']), '(want 0)')
seen.clear(); frame('next frame'); print('    calls', [x[0] for x in seen], '(want hash, selector only)')

# ==== NEW CHECKS: the smoothing of the steerable cameras' mouse and keys, and the blend between cameras ====
# Each one prints its verdict; the count is on the last line. The fake game below does what the disassembly says the
# real one does (build_cycle.py, "How a camera reaches the screen"); none of it has been seen in the running game.
print('\n==== NEW CHECKS (smoothing, blend) ====')
res = [0, 0]
def check(what, ok, detail=''):
    res[0 if ok else 1] += 1; print('  %s %s%s' % ('ok    ' if ok else 'FAILED', what, '   [%s]' % detail if detail else ''))
f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
raw = lambda a, n=1: bytes(u.mem_read(a, 4 * n))
x87_empty = lambda: (u.reg_read(UC_X86_REG_FPSW) >> 11) & 7 == 0          # as many pops as pushes
def quiet_frame(): log.clear(); call(BASE + j['drawOff'])
def upd(entry=0):                            # one update of the camera asked for: its wrapper, up to the jump into the game's own update
    log.clear(); call(BASE + (entry or j['freeOff'])); assert log[-1][0].startswith('jumped to'), log
CX, CY, SENS, RATE, FREE, ROT = 1920, 1080, 0.0025, 0.02, MGR + 0xC78, MGR + 0xEEC
def steer(cam, tau, tauk, dt):               # a steerable camera freshly selected: nothing outstanding, cursor centred
    wf(BASE + D['K_LOOKTAU'], tau); wf(BASE + D['K_MOVETAU'], tauk); wf(MGR, dt); state.update(cursor=(CX, CY), keys=set(), fore=0x5555)
    w32(MGR + 0x190, MGR + 0x510); quiet_frame()
    w32(MGR + 0x190, cam); wf(FREE + 0x268, 0.0); wf(ROT + 0x20, 0.0); wf(ROT + 0x48, 0.0); upd(j['rotOff'] if cam == ROT else 0)
def look(dx, dy, keys=()):                   # one free cam update with this mouse movement: the angles the game adds (yaw, pitch), its move inputs
    state['cursor'] = (CX + dx, CY + dy); state['keys'] = set(keys); upd()
    return rf(MGR + 0x1A8) * RATE, rf(MGR + 0x1AC) * RATE, rf(MGR + 0x1B0), rf(MGR + 0x1B4), rf(MGR + 0x1B8)

print('-- smoothing off (0): the camera gets the raw mouse and keys, as before')
steer(FREE, 0.0, 0.0, 1 / 60); same = True; yawok = True
for dx, dy, keys in ((40, -24, {0x57}), (-3, 1, {0x57, 0x44}), (0, 0, {0x53, 0x11}), (500, 300, ()), (-1, -1, {0x41, 0x20})):
    y, p, f, s, v = look(dx, dy, keys)
    same &= raw(BASE + D['SMXY'], 2) == struct.pack('<2f', dx, dy) and raw(BASE + D['MREM'], 2) == bytes(8)
    same &= (f, s, v) == ((0x57 in keys) - (0x53 in keys), (0x44 in keys) - (0x41 in keys), (0x20 in keys) - (0x11 in keys))
    yawok &= raw(MGR + 0x1A8) == struct.pack('<f', f32(f32(dx * f32(SENS)) / f32(RATE)))
check('smoothing 0: mouse part = the movement read, to the bit; nothing left over; keys -1 / 0 / +1 exactly (5 updates)', same)
check('smoothing 0: yaw input = pixels x 0.0025 / camera rate in single precision, to the bit (the old arithmetic)', yawok)
for bad in (0.0, -0.01, 0.3, float('nan')):
    steer(FREE, 0.08, 0.16, bad); y, p, f, s, v = look(80, 0, {0x57})
    check('smoothing on but frame time %g is no usable time: raw (yaw %.4f want 0.2, forward %g want 1)' % (bad, y, f), abs(y - 0.2) < 1e-6 and f == 1.0)

print('-- smoothed look: a share of what is outstanding per update, 1 - e^(-dt / tau)')
TAU = 0.08; steer(FREE, TAU, 0.0, 1 / 60); tot = [0.0, 0.0]; parts = []
while len(parts) < 240 and not (parts and raw(BASE + D['MREM'], 2) == bytes(8)):
    y, p, *_ = look(0 if parts else 120, 0 if parts else -60); parts.append((y, -p)); tot[0] += y; tot[1] += p
n = len(parts)
def shrinking(v):                            # ever smaller, never backwards; an axis' last part takes the rest with it once that is under 0.001 pixel
    v = [x for x in v if x != 0]; return all(b <= a for a, b in zip(v, v[1:-1])) and all(x > 0 for x in v) and v[-1] <= 0.0013 * SENS
check('a 120 / -60 pixel flick is handed out in ever smaller parts, never backwards (first %.4f rad of 0.3, then %.4f, %.4f ... the last, with the crumb, %.2g)' % (parts[0][0], parts[1][0], parts[2][0], parts[-1][0]),
      shrinking([p[0] for p in parts]) and shrinking([p[1] for p in parts]) and 0 < parts[0][0] < 0.1)
check('...and ends exactly on the raw target: yaw %.7f (raw 0.3), pitch %.7f (raw -0.15), nothing left after %d updates (%.2f s)' % (tot[0], tot[1], n, n / 60),
      abs(tot[0] - 0.3) < 2e-6 and abs(tot[1] + 0.15) < 2e-6 and n < 240)
T = 0.2; want = 1 - math.exp(-T / TAU); got = {}
for fps in (30, 60, 120, 240):
    steer(FREE, TAU, 0.0, 1 / fps); got[fps] = sum(look(120 if k == 0 else 0, 0)[0] for k in range(round(T * fps))) / 0.3
check('time constant %g s at 30 / 60 / 120 / 240 updates a second: after %g s %s of the flick is out (want %.5f = 1 - e^(-%g/%g))' % (TAU, T, ' / '.join('%.5f' % got[k] for k in sorted(got)), want, T, TAU),
      all(abs(v - want) < 2e-5 for v in got.values()))
steer(FREE, TAU, 0.0, 1 / 60); a1 = look(100, 0)[0] / 0.25
check('one update of 1/60 s hands out %.5f of what is outstanding (want %.5f)' % (a1, 1 - math.exp(-1 / 60 / TAU)), abs(a1 - (1 - math.exp(-1 / 60 / TAU))) < 1e-6)
steer(FREE, TAU, 0.0, 1 / 60); ys = [look(10, 0)[0] for k in range(180)]
check('a steady 10 pixels per update comes through at the full rate: %.6f rad per update after 3 s (raw 0.025), %.2f pixels behind (want %.2f)' % (ys[-1], rf(BASE + D['MREM']), 10 * math.exp(-1 / 60 / TAU) / (1 - math.exp(-1 / 60 / TAU))),
      abs(ys[-1] - 0.025) < 1e-6 and all(b >= a - 1e-9 for a, b in zip(ys, ys[1:])))
steer(FREE, TAU, 0.0, 1 / 60); wf(FREE + 0x268, 1.5); worst = -9
for k in range(120):
    y, p, *_ = look(0, 400 if k == 0 else 0); wf(FREE + 0x268, rf(FREE + 0x268) + p); worst = max(worst, rf(FREE + 0x268))
check('pitch stopper with smoothing: 400 pixels down from 1.5 rad never passes 1.5706 (highest %.5f, ends %.5f)' % (worst, rf(FREE + 0x268)), worst <= 1.5706 + 1e-6 and worst > 1.57)
steer(FREE, TAU, 0.0, 1 / 60); look(200, 100); left = rf(BASE + D['MREM']); state['keys'] = {0xDC}; state['cursor'] = (CX, CY)
saved = r32(FREE); w32(RVT + 4, RESETFN); w32(FREE, RVT); upd(); w32(FREE, saved)
check('reset key: the camera is reset and what was outstanding (%.1f pixels) is dropped: inputs %g / %g, left over %s' % (left, rf(MGR + 0x1A8), rf(MGR + 0x1AC), raw(BASE + D['MREM'], 2).hex()),
      any('camera reset' in l[0] for l in log) and left > 100 and rf(MGR + 0x1A8) == 0 and rf(MGR + 0x1AC) == 0 and raw(BASE + D['MREM'], 2) == bytes(8))
steer(FREE, TAU, 0.16, 1 / 60); look(200, 100, {0x57}); state['fore'] = 0x9999; upd()
check('game not in front: nothing stays outstanding (mouse %s, keys %s), inputs zeroed' % (raw(BASE + D['MREM'], 2).hex(), raw(BASE + D['KAX'], 4).hex()),
      raw(BASE + D['MREM'], 2) == bytes(8) and raw(BASE + D['KAX'], 4) == bytes(16) and all(rf(MGR + 0x1A8 + 4 * i) == 0 for i in range(8)))

print('-- smoothed keys: the same share of the way to -1 / 0 / +1 per update')
TK = 0.16; curve = {}
for fps in (30, 60, 120):
    steer(FREE, 0.0, TK, 1 / fps); curve[fps] = [look(0, 0, {0x57, 0x41, 0x20})[2:] for k in range(round(0.3 * fps))][-1]
want = 1 - math.exp(-0.3 / TK)
check('W + A + Space held 0.3 s at 30 / 60 / 120 updates a second: forward %s (want %.5f), sideways and up the same size' % (' / '.join('%.5f' % curve[k][0] for k in sorted(curve)), want),
      all(abs(c[0] - want) < 2e-5 and abs(c[1] + want) < 2e-5 and abs(c[2] - want) < 2e-5 for c in curve.values()))
steer(FREE, 0.0, TK, 1 / 60); up = [look(0, 0, {0x57})[2] for k in range(200)]; n1 = up.index(1.0) if 1.0 in up else -1
down = [look(0, 0)[2] for k in range(200)]; n0 = down.index(0.0) if 0.0 in down else -1
check('W held: rises without a step back and lands on exactly 1 (after %d updates); released: falls and lands on exactly 0 (after %d, want about %d)' % (n1 + 1, n0 + 1, round(TK * math.log(1000) * 60)),
      n1 > 30 and n0 > 30 and all(b >= a for a, b in zip(up, up[1:])) and all(b <= a for a, b in zip(down, down[1:])) and abs(n0 + 1 - TK * math.log(1000) * 60) < 3)
check('x87 stack as it was after all these updates (the share is worked out on it)', x87_empty())

print('-- car rotate cam: the same smoothing in front of its own scaling and limits')
steer(ROT, TAU, TK, 1 / 60); orbit = tilt = 0.0; zoom = []
for k in range(200):
    state['cursor'] = (CX + (90 if k == 0 else 0), CY + (40 if k == 0 else 0)); state['keys'] = {0x57} if k < 100 else set(); upd(j['rotOff'])
    orbit += rf(MGR + 0x1A8) * (1 / 60) * math.pi / 2; tilt += rf(MGR + 0x1B8) * (1 / 60) * 10; zoom.append(rf(MGR + 0x1AC))
check('90 / 40 pixel flick: orbit ends on %.6f rad (raw 0.225), height on %.6f m (raw -0.4)' % (orbit, tilt), abs(orbit - 0.225) < 2e-6 and abs(tilt + 0.4) < 2e-6)
check('W (zoom in) eases to -1 and back to 0: %.4f after 19 updates (want %.4f), %.6f while held, %g at the end' % (zoom[18], -(1 - math.exp(-19 / 60 / TK)), zoom[99], zoom[-1]),
      abs(zoom[18] + 1 - math.exp(-19 / 60 / TK)) < 2e-5 and abs(zoom[99] + 1.0) < 1e-5 and zoom[-1] == 0.0)
steer(ROT, TAU, TK, 1 / 60); wf(ROT + 0x20, -3.9); low = 99
for k in range(120):
    state['keys'] = {0x57}; upd(j['rotOff']); wf(ROT + 0x20, rf(ROT + 0x20) + rf(MGR + 0x1AC) * (1 / 60) * 10); low = min(low, 7.0 + rf(ROT + 0x20))
check('zoom limit with smoothing: W held from 3.1 m stops at %.4f m (want 3, the limit)' % low, abs(low - 3.0) < 1e-4)
wf(ROT + 0x20, 0.0); wf(BASE + D['K_LOOKTAU'], 0.0); wf(BASE + D['K_MOVETAU'], 0.0); w32(MGR + 0x190, MGR + 0x510); state['keys'] = set(); quiet_frame()

# ---- the fake game's side of a drawn frame: camera state objects, the car, 0x5F1690, the clock
print('-- blend between cameras')
SOFF = {0x510: 0x54, 0x8C4: 0x54, 0xEEC: 0x64}                           # camera -> its state object (vtable slot 23); +8 for the other classes
for o, v in vt.items():
    n = SOFF.get(o, 8); fn = {0x54: 0x412710, 0x64: 0x4126C0, 8: 0x413790}[n]
    u.mem_write(fn, bytes([0x8D, 0x41, n, 0xC3])); w32(v + 0x5C, fn)     # lea eax,[ecx+n] ; ret, as in the game
CAR = MGR_OWNER + 0xA000; MAT = CAR + 0x135C; car = {}
def set_car(pos, yaw, scale=1.0):
    c, s = math.cos(yaw), math.sin(yaw); car.update(R=(c, 0, -s), U=(0, 1, 0), F=(s, 0, c), P=pos)
    u.mem_write(MAT, struct.pack('<16f', *(x * scale for x in car['R']), 0, *(x * scale for x in car['U']), 0, *(x * scale for x in car['F']), 0, *pos, 1))
def world(p, point=True): return tuple(p[0] * car['R'][i] + p[1] * car['U'][i] + p[2] * car['F'][i] + (car['P'][i] if point else 0) for i in range(3))
deg = math.pi / 180
VIEWS = dict(daytona=((0.3, 1.9, -4.7), (0, 1.0, -0.87), (0, 1, 0), 72 * deg), drone=((-0.2, 4.6, -6.9), (0, 1.0, -0.87), (0, 1, 0), 87 * deg),
             bonnet=((0, 1.19, 0.94), (0, 0, 20), (0, 1, 0), 60 * deg), bumper=((0, 0.75, 1.45), (0, 0, 20), (0.05, 1, 0), 60 * deg),
             wheel=((-1.3, 0.3, 2.1), (-1.2, 0, 1.2), (0, 1, 0), 60 * deg))        # eye, look-at, up in the car's frame, field of view
shown = {}                                                               # camera offset -> the view its state holds in this frame
def pose(view):                                                          # that view in the world: eye, look-at, up, field of view
    e, a, up, fov = VIEWS[view]; return world(e), world(a), world(up, False), fov
def sobj(cam): return cam + SOFF.get(cam - MGR, 8)
game = dict(calls=[], running=True, garbage=None)
def interpolate(a):                                                      # 0x5F1690: esi = manager, one float; the camera the frame is drawn from gets its state
    esi = u.reg_read(UC_X86_REG_ESI); game['calls'].append((esi, a[0]))
    if esi != MGR or not (r32(0x9DB800) or (r32(0x7ECE10) == r32(0x7ECE14) and r32(0x7ECE10) in (0x27, 0x1C))): return 0x5F1690
    w32(MGR + 0x184, r32(MGR + 0x188)); cam = r32(MGR + 0x184)
    if cam:
        e, at, up, fov = game['garbage'] or pose(shown[cam - MGR]); s = sobj(cam)
        u.mem_write(s + 0x30, struct.pack('<4f', *e, 777.0)); u.mem_write(s + 0x6C, struct.pack('<4f', *at, 777.0))      # 777: the float after each vec3,
        u.mem_write(s + 0x120, struct.pack('<4f', *up, 777.0)); u.mem_write(s + 0x178, struct.pack('<2f', fov, 777.0))    # which is not the blend's to write
    return 0x5F1690
stub(0x5F1690, 1, interpolate)
QF = 10000000; state['qpc'] = 123456789012; state['qpcalls'] = 0
names['QueryPerformanceFrequency'] = STUB + 0xE0; names['QueryPerformanceCounter'] = STUB + 0xE8
stub(STUB + 0xE0, 1, lambda a: u.mem_write(a[0], struct.pack('<q', QF)) or 1)
def qpc(a): state['qpcalls'] += 1; u.mem_write(a[0], struct.pack('<q', state['qpc'])); return 1
stub(STUB + 0xE8, 1, qpc)
ALPHA = struct.unpack('<I', struct.pack('<f', 0.375))[0]
def render(dt=1 / 60, mgr=MGR):              # one drawn frame: the hooked call at 0x5C948C. Returns what the view is then built from
    state['qpc'] += round(dt * QF); game['calls'].clear(); game['dt'] = round(dt * QF) / QF
    esp = STACK - 4; w32(esp, ALPHA); esp -= 4; w32(esp, DONE); regs = (UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EDI, UC_X86_REG_EBP)
    u.reg_write(UC_X86_REG_ESP, esp); u.reg_write(UC_X86_REG_ESI, mgr)
    for k, r in enumerate(regs): u.reg_write(r, 0x51510000 + k)
    u.emu_start(BASE + j['blendOff'], DONE, count=200000)
    game['clean'] = game.get('clean', True) and u.reg_read(UC_X86_REG_ESP) == STACK and u.reg_read(UC_X86_REG_ESI) == mgr and all(u.reg_read(r) == 0x51510000 + k for k, r in enumerate(regs)) and x87_empty()   # since setup()
    return view()
def view():                                  # eye, look-at, up, field of view in the state of the camera the frame is drawn from
    s = sobj(r32(MGR + 0x184)); return struct.unpack('<3f', raw(s + 0x30, 3)), struct.unpack('<3f', raw(s + 0x6C, 3)), struct.unpack('<3f', raw(s + 0x120, 3)), rf(s + 0x178)
def own(): cam = r32(MGR + 0x184); e, a, up, fov = pose(shown[cam - MGR]); return tuple(f32(x) for x in e), tuple(f32(x) for x in a), tuple(f32(x) for x in up), f32(fov)
def untouched():                             # the state is exactly what the game wrote, the floats after the vectors included
    s = sobj(r32(MGR + 0x184)); return view() == own() and all(rf(s + o) == 777.0 for o in (0x3C, 0x78, 0x12C, 0x17C))
sub = lambda a, b: tuple(x - y for x, y in zip(a, b)); mix = lambda a, b, s: tuple(x + (y - x) * s for x, y in zip(a, b)); norm = lambda a: math.sqrt(sum(x * x for x in a))
def carframe(v):                             # a drawn view as the block keeps it: eye, unit direction, up in the car's frame, look distance, field of view
    e, at, up, fov = v; d = sub(at, e); n = norm(d); tc = lambda p: tuple(sum(p[i] * car[ax][i] for i in range(3)) for ax in 'RUF')
    return tc(sub(e, car['P'])), tc(tuple(x / n for x in d)), tc(up), n, fov
def blended(frm, s):                         # the model: from a kept view (car frame), carried by the car as it is now, s of the way to the camera's own
    e1, a1, u1, f1 = pose(shown[r32(MGR + 0x184) - MGR]); d1 = sub(a1, e1); n1 = norm(d1)
    e = mix(world(frm[0]), e1, s); d = mix(world(frm[1], False), tuple(x / n1 for x in d1), s); n = norm(d); dist = frm[3] + (n1 - frm[3]) * s
    return e, tuple(e[i] + d[i] / n * dist for i in range(3)), mix(world(frm[2], False), u1, s), frm[4] + (f1 - frm[4]) * s
def err(v, w): return max(max(abs(x - y) for x, y in zip(v[i], w[i])) for i in range(3)), abs(v[3] - w[3])
ease = lambda t: t * t * (3 - 2 * t)
def setup(dur, cam, view_, idx):             # a race under way on this camera, a few frames drawn: the block has seen the view
    wf(BASE + D['K_BLEND'], dur); w32(0x7ECE10, 0x27); w32(0x7ECE14, 0x27); w32(0x9DB800, 0); w32(MGR + 0x1C8, CAR); set_car((100.0, 5.0, -40.0), 0.3); game.update(garbage=None, clean=True)
    for o in vt: shown[o] = 'bonnet'
    shown[cam] = view_; w32(MGR + 0x190, MGR + cam); w32(MGR + 0x18C, MGR + cam); w32(MGR + 0x188, MGR + cam)
    w32(MGR + 0x230, idx); w32(BASE + 0x1C, idx)
    for k in range(3): render()
def press(idx): go(idx); quiet_frame()       # View Change: the game stepped its index, the block's draw hook sees it at the end of the frame
def travel(dur, dt, frames, frm, drive=None):                            # draw frames of a running blend; the worst distance from the model, per frame
    out = []; t = 0.0
    for k in range(frames):
        if drive: drive(k)
        v = render(dt); t = k * game['dt'] / dur
        out.append((t, v, None if t >= 1 else err(v, blended(frm, ease(t))), untouched()))
    return out

# 1. the same camera object with other settings: CamLab Daytona -> CamLab Chase (both the chase camera)
setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); before = view()
check('before any View Change the hook leaves the state as the game wrote it; the game\'s routine ran once per frame with the caller\'s esi and float; registers, stack and x87 as before',
      untouched() and game['clean'] and game['calls'] == [(MGR, ALPHA)])
press(4); shown[0x510] = 'drone'
check('View Change to a slot of the same object: the blend is armed for the next frame (go %d, waiting for %#x)' % (r32(BASE + D['BGO']), r32(BASE + D['BWAIT'])), r32(BASE + D['BGO']) == 1 and r32(BASE + D['BWAIT']) == 0)
tr = travel(0.5, 1 / 60, 40, frm); e0 = err(tr[0][1], before)
check('first frame of the blend = the old view (off by %.2g m, %.2g rad of field of view) although the camera already holds the new one' % e0, max(e0) < 1e-4 and not tr[0][3])
mid = tr[15]; em = err(mid[1], blended(frm, 0.5)); way = lambda k: (tr[k][1][0][1] - before[0][1]) / (own()[0][1] - before[0][1])     # by the eye's height
check('ease in / ease out: at t = %.3f the view is half way (off by %.2g m); at t = %.3f it is %.1f%% of the way (want %.1f%%), at t = %.3f %.1f%% (want %.1f%%)'
      % (mid[0], em[0], tr[6][0], 100 * way(6), 100 * ease(tr[6][0]), tr[24][0], 100 * way(24), 100 * ease(tr[24][0])),
      abs(mid[0] - 0.5) < 1e-3 and max(em) < 2e-4 and abs(way(6) - ease(tr[6][0])) < 1e-3 and abs(way(24) - ease(tr[24][0])) < 1e-3 and way(6) < 0.2 * 0.6 and way(24) > 1 - 0.2 * 0.6)
worst = max(max(x[2]) for x in tr if x[2]); done = [k for k, x in enumerate(tr) if x[3]]
check('every frame on the eased straight path from the old view to the new (eye, look-at, up, field of view): worst %.2g m' % worst, worst < 3e-4)
check('ends exactly on the new camera: from frame %d (%.3f s) on the state is the game\'s own, to the bit, and stays so (%d frames checked); the frame before was %.2g m short' % (done[0], done[0] * game['dt'], len(done), err(tr[done[0] - 1][1], own())[0]),
      done == list(range(done[0], 40)) and done[0] in (30, 31) and err(tr[done[0] - 1][1], own())[0] < 0.05 and r32(BASE + D['BACTIVE']) == 0)
check('...and only 3 floats of each vector and the field of view were ever written; registers, stack and x87 as before in every frame', all(rf(sobj(MGR + 0x510) + o) == 777.0 for o in (0x3C, 0x78, 0x12C, 0x17C)) and game['clean'])

# 2. frame rate: the same blend drawn at other rates
at = {}
for fps in (30, 60, 144):
    setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); press(4); shown[0x510] = 'drone'; tr = travel(0.5, 1 / fps, round(0.7 * fps), frm)
    k = round(0.25 * fps); at[fps] = (tr[k][0], tr[k][1][0][1], [i for i, x in enumerate(tr) if x[3]][0] / fps, max(max(x[2]) for x in tr if x[2]))
yref = lambda t: before[0][1] + (own()[0][1] - before[0][1]) * ease(t)
check('duration is real time, whatever the frame rate: at 30 / 60 / 144 frames a second the eye height %s m at t = %s (want %s), the blend over after %s s (want 0.5)'
      % (' / '.join('%.4f' % at[k][1] for k in sorted(at)), ' / '.join('%.3f' % at[k][0] for k in sorted(at)), ' / '.join('%.4f' % yref(at[k][0]) for k in sorted(at)), ' / '.join('%.3f' % at[k][2] for k in sorted(at))),
      all(abs(v[1] - yref(v[0])) < 3e-4 and abs(v[2] - 0.5) <= 1 / k + 1e-6 and v[3] < 3e-4 for k, v in at.items()))
setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); press(4); shown[0x510] = 'drone'; render(1 / 60); v = render(2.0); t = 0.1 / 0.5
check('a 2 s hitch does not eat the blend: one frame adds at most 0.1 s (view %.2g m from the model at t = 0.2)' % err(v, blended(frm, ease(t)))[0], max(err(v, blended(frm, ease(t)))) < 3e-4)

# 3. duration 0: a cut, as before
setup(0.0, 0x510, 'daytona', 3); n0 = state['qpcalls']; press(4); shown[0x510] = 'drone'; cut = [render() and untouched() for k in range(5)]
w32(MGR + 0x188, MGR + 0x1700); shown[0x1700] = 'bumper'; press(5); cut += [render() and untouched() for k in range(5)]
check('duration 0 = cut: the state is never written, same object or another (10 frames), nothing armed, the clock not even read',
      all(cut) and state['qpcalls'] == n0 and raw(BASE + D['BACTIVE'], 3) == bytes(12) and r32(BASE + D['BHAVE']) == 0)

# 4. another camera object: Game: Bonnet cam -> CamLab: Daytona. The game draws from the old one for a few frames more
setup(0.4, 0x189C, 'bonnet', 2); press(3); shown[0x510] = 'daytona'; w32(MGR + 0x190, MGR + 0x510)
check('View Change to another object: the blend waits for the view to move to it (go %d, waiting for the chase camera: %s)' % (r32(BASE + D['BGO']), r32(BASE + D['BWAIT']) == MGR + 0x510), r32(BASE + D['BGO']) == 0 and r32(BASE + D['BWAIT']) == MGR + 0x510)
wait = [render() and untouched() for k in range(3)]; frm = carframe(view()); before = view()
check('while the game still draws from the old camera (3 frames) nothing is written', all(wait) and r32(BASE + D['BACTIVE']) == 0)
w32(MGR + 0x18C, MGR + 0x510); w32(MGR + 0x188, MGR + 0x510); tr = travel(0.4, 1 / 60, 30, frm); e0 = err(tr[0][1], before); done = [k for k, x in enumerate(tr) if x[3]]
check('the frame the view moves to the new camera shows the old view (off by %.2g m), then travels (worst %.2g m off the path) and ends on the new camera, to the bit, at frame %d (%.3f s)' % (e0[0], max(max(x[2]) for x in tr if x[2]), done[0], done[0] * game['dt']),
      max(e0) < 1e-4 and max(max(x[2]) for x in tr if x[2]) < 5e-4 and done == list(range(done[0], 30)) and done[0] in (24, 25) and r32(BASE + D['BWAIT']) == 0)

# 5. the old view rides with the car: the car drives and turns during the blend
setup(0.5, 0x189C, 'bonnet', 2); press(3); shown[0x510] = 'daytona'; render(); frm = carframe(view()); w32(MGR + 0x188, MGR + 0x510)
tr = travel(0.5, 1 / 60, 34, frm, lambda k: set_car((100.0 + 0.9 * k, 5.0 + 0.02 * k, -40.0 + 0.3 * k), 0.3 + 0.02 * k)); done = [k for k, x in enumerate(tr) if x[3]]
check('car at 200 km/h turning 69 deg/s through the blend: every frame is the kept view carried by the car, eased towards the camera (worst %.2g m off), ends to the bit at frame %d' % (max(max(x[2]) for x in tr if x[2]), done[0]),
      max(max(x[2]) for x in tr if x[2]) < 1e-3 and done == list(range(done[0], 34)))

# 5b. the car bounces (pitch, roll, heave) during the blend: the old view rides with its heading and place only, so the
# body's movements do not shake it (owner, 2026-10-14: "janky in the first 1/3 second of the transition")
def set_car_pr(pos, yaw, pitch, roll):
    c, s = math.cos(yaw), math.sin(yaw); R0, U0, F0 = (c, 0, -s), (0, 1, 0), (s, 0, c)
    F1 = tuple(F0[i] * math.cos(pitch) + U0[i] * math.sin(pitch) for i in range(3)); U1 = tuple(U0[i] * math.cos(pitch) - F0[i] * math.sin(pitch) for i in range(3))
    R2 = tuple(R0[i] * math.cos(roll) + U1[i] * math.sin(roll) for i in range(3)); U2 = tuple(U1[i] * math.cos(roll) - R0[i] * math.sin(roll) for i in range(3))
    car.update(R=R2, U=U2, F=F1, P=pos); u.mem_write(MAT, struct.pack('<16f', *R2, 0, *U2, 0, *F1, 0, *pos, 1))
def yawframe():                              # the car's heading and place, as the block makes them
    f = (car['F'][0], 0.0, car['F'][2]); n = norm(f); f = tuple(x / n for x in f); r = (f[2], 0.0, -f[0])
    if sum(r[i] * car['R'][i] for i in range(3)) < 0: r = tuple(-x for x in r)
    return dict(R=r, U=(0.0, 1.0, 0.0), F=f, P=car['P'])
def carframe_y(v):
    y = yawframe(); e, at, up, fov = v; d = sub(at, e); n = norm(d); tc = lambda p: tuple(sum(p[i] * y[ax][i] for i in range(3)) for ax in 'RUF')
    return tc(sub(e, y['P'])), tc(tuple(x / n for x in d)), tc(up), n, fov
def blended_y(frm, s):
    y = yawframe(); wy = lambda p, pt=True: tuple(p[0] * y['R'][i] + p[1] * y['U'][i] + p[2] * y['F'][i] + (y['P'][i] if pt else 0) for i in range(3))
    e1, a1, u1, f1 = pose(shown[r32(MGR + 0x184) - MGR]); d1 = sub(a1, e1); n1 = norm(d1)
    e = mix(wy(frm[0]), e1, s); d = mix(wy(frm[1], False), tuple(x / n1 for x in d1), s); n = norm(d); dist = frm[3] + (n1 - frm[3]) * s
    return e, tuple(e[i] + d[i] / n * dist for i in range(3)), mix(wy(frm[2], False), u1, s), frm[4] + (f1 - frm[4]) * s
bounce = lambda k: set_car_pr((100.0 + 0.9 * k, 5.0 + 0.05 * math.sin(k * 0.6), -40.0 + 0.3 * k), 0.3 + 0.01 * k, 6 * deg * math.sin(k * 0.6), 4 * deg * math.sin(k * 0.45 + 1))
# Since the second fix the old view rides with the NEW camera: on the blend's first frame the kept view (carried by the
# car's heading and place) becomes an offset from the new camera's eye in that camera's level heading frame, and each
# frame it is that camera's eye + the offset turned with it. The model of that:
def headframe(e1, d1):
    f = (d1[0], 0.0, d1[2]); n = norm(f); y = yawframe()
    if n < 1e-3: return dict(R=y['R'], U=y['U'], F=y['F'], P=e1)
    f = tuple(x / n for x in f); r = (f[2], 0.0, -f[0])
    if sum(r[i] * y['R'][i] for i in range(3)) < 0: r = tuple(-x for x in r)
    return dict(R=r, U=(0.0, 1.0, 0.0), F=f, P=e1)
def ownview():
    e1, a1, u1, f1 = pose(shown[r32(MGR + 0x184) - MGR]); d1 = sub(a1, e1); n1 = norm(d1); return e1, tuple(x / n1 for x in d1), u1, n1, f1
def offset_from(frm):                                    # the first frame: the kept view, carried by the car, as an offset in the new camera's frame
    e, a, up, fov = blended_y(frm, 0.0); d = sub(a, e); n = norm(d); e1, d1, u1, n1, f1 = ownview(); H = headframe(e1, d1)
    th = lambda p: tuple(sum(p[i] * H[ax][i] for i in range(3)) for ax in 'RUF')
    return th(sub(e, e1)), th(tuple(x / n for x in d)), th(up), n, fov
def blended_h(off, s):
    e1, d1, u1, n1, f1 = ownview(); H = headframe(e1, d1); hw = lambda p: tuple(p[0] * H['R'][i] + p[1] * H['U'][i] + p[2] * H['F'][i] for i in range(3))
    e = mix(tuple(e1[i] + hw(off[0])[i] for i in range(3)), e1, s); d = mix(hw(off[1]), d1, s); n = norm(d); dist = off[3] + (n1 - off[3]) * s
    return e, tuple(e[i] + d[i] / n * dist for i in range(3)), mix(hw(off[2]), u1, s), off[4] + (f1 - off[4]) * s
setup(0.5, 0x510, 'daytona', 3); bounce(0); render(); frm = carframe_y(view()); press(4); shown[0x510] = 'drone'
worst, rigid = 0.0, 0.0; t = 0.0; off = None
for k in range(34):
    bounce(k + 1)
    if off is None: off = offset_from(frm)
    v = render(1 / 60); t = k * game['dt'] / 0.5
    if t < 1:
        worst = max(worst, max(err(v, blended_h(off, ease(t))))); rigid = max(rigid, err(v, blended(frm, ease(t)))[0] if t < 0.4 else 0)
check('car bouncing through the blend (pitch 6 deg, roll 4 deg, 5 cm, at 6 Hz): the old view rides with the new camera, its eye and level heading (worst %.2g m off that path); carried by the whole body it would have been up to %.2f m off in the first 0.2 s' % (worst, rigid),
      worst < 1e-3 and rigid > 0.05)

# 5c. the game moves the car's matrix in physics steps and interpolates the cameras for each drawn frame: here the
# matrix moves every second frame (30 Hz) at 200 km/h while the camera moves every frame. The blended eye must move as
# evenly as the camera's (carried by the stepped matrix it jumped 1.85 m every second frame: the owner's "janky when the
# car is moving, the faster the worse")
def drive_stepped(k):
    yaw = 0.3 + 0.004 * k; pos = (100.0 + 0.926 * math.sin(yaw) * k, 5.0, -40.0 + 0.926 * math.cos(yaw) * k)
    c, s_ = math.cos(yaw), math.sin(yaw); car.update(R=(c, 0, -s_), U=(0, 1, 0), F=(s_, 0, c), P=pos)
    if k % 2 == 0: u.mem_write(MAT, struct.pack('<16f', c, 0, -s_, 0, 0, 1, 0, 0, s_, 0, c, 0, *pos, 1))
setup(0.5, 0x510, 'daytona', 3); drive_stepped(0); render(); press(4); shown[0x510] = 'drone'
eyes = []
for k in range(1, 31):
    drive_stepped(k); v = render(1 / 60); eyes.append(v[0])
acc = max(norm(tuple(eyes[k + 1][i] - 2 * eyes[k][i] + eyes[k - 1][i] for i in range(3))) for k in range(1, len(eyes) - 1))
check('car at 200 km/h whose matrix moves in 30 Hz steps while the camera moves every frame: the blended eye moves evenly (largest change of its step from one frame to the next %.3f m; the matrix itself jumps 1.85 m every second frame)' % acc, acc < 0.05)

# 6. View Change again while a blend runs: on from where the view is, no jump
setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); press(4); shown[0x510] = 'drone'; tr = travel(0.5, 1 / 60, 12, frm); midv = tr[-1][1]; frm2 = carframe(midv)
press(5); shown[0x510] = 'daytona'; tr2 = travel(0.5, 1 / 60, 40, frm2); done = [k for k, x in enumerate(tr2) if x[3]]
check('a second View Change 0.2 s into a blend starts from the view as it is (first frame off by %.2g m), no jump, and ends on its camera to the bit at frame %d' % (err(tr2[0][1], midv)[0], done[0]),
      max(err(tr2[0][1], midv)) < 2e-4 and max(max(x[2]) for x in tr2 if x[2]) < 5e-4 and done[0] in (30, 31))

# 7. a camera change of the game's own stays a cut, and ends a running blend
setup(0.5, 0x510, 'daytona', 3); w32(MGR + 0x188, MGR + 0x1700); shown[0x1700] = 'bumper'; cut = [render() and untouched() for k in range(4)]
check('the game changes camera by itself (no View Change): a cut, nothing written (4 frames)', all(cut) and r32(BASE + D['BACTIVE']) == 0)
setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); press(4); shown[0x510] = 'drone'; tr = travel(0.5, 1 / 60, 8, frm)
w32(MGR + 0x188, MGR + 0x189C); cut = [render() and untouched() for k in range(4)]
check('...also in the middle of a blend (it was %.0f%% along): the cut is shown at once' % (100 * ease(tr[-1][0])), not tr[-1][3] and all(cut) and r32(BASE + D['BACTIVE']) == 0)
setup(0.5, 0x189C, 'bonnet', 2); press(3); shown[0x510] = 'daytona'; idle = [render() and untouched() for k in range(125)]; w32(MGR + 0x188, MGR + 0x510); late = [render() and untouched() for k in range(4)]
check('a View Change the game never follows is forgotten after 120 frames: a move to that camera later is a cut (waiting for %#x)' % r32(BASE + D['BWAIT']), all(idle) and all(late) and r32(BASE + D['BWAIT']) == 0)

# 8. things the blend must not trip over
setup(0.5, 0x510, 'daytona', 3); press(4); shown[0x510] = 'drone'; w32(0x7ECE10, 0x30); s = sobj(MGR + 0x510); keep = raw(s, 0x60); r = [render() for k in range(3)]
check('game not in a running state: its routine interpolates nothing and the hook writes nothing (state bytes unchanged, blend not started: go still %d)' % r32(BASE + D['BGO']), raw(s, 0x60) == keep and r32(BASE + D['BGO']) == 1 and r32(BASE + D['BACTIVE']) == 0)
setup(0.5, 0x510, 'daytona', 3); press(4); shown[0x510] = 'drone'; other = MGR_OWNER + 0x4000; keep = raw(BASE + D['BDT'], 10); n0 = state['qpcalls']; render(mgr=other)
check('another player\'s manager: the game\'s routine is called with it, the block does nothing else', game['calls'] == [(other, ALPHA)] and raw(BASE + D['BDT'], 10) == keep and state['qpcalls'] == n0 and game['clean'])
setup(0.5, 0x510, 'daytona', 3); press(4); shown[0x510] = 'drone'; w32(MGR + 0x1C8, 0); r = [render() and untouched() for k in range(3)]
check('no car: nothing written, nothing kept', all(r) and r32(BASE + D['BHAVE']) == 0 and r32(BASE + D['BACTIVE']) == 0)
setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); press(4); shown[0x510] = 'drone'; tr = travel(0.5, 1 / 60, 5, frm)
u.mem_write(MAT + 0x10, struct.pack('<f', float('nan'))); v = render(); bad = any(x != x for part in v[:3] for x in part)
check('car matrix turns into no-numbers in the middle of a blend: nothing but the game\'s values in the state, blend dropped', not bad and r32(BASE + D['BACTIVE']) == 0 and r32(BASE + D['BHAVE']) == 0)
setup(0.5, 0x510, 'daytona', 3); set_car((100.0, 5.0, -40.0), 0.3, 2.0); render(); press(4); shown[0x510] = 'drone'; r = [render() for k in range(3)]
check('car axes of length 2 (not the rigid matrix the blend assumes): the change stays a cut', r32(BASE + D['BACTIVE']) == 0 and r32(BASE + D['BGO']) == 0)
setup(0.5, 0x510, 'daytona', 3); frm = carframe(view()); press(4); shown[0x510] = 'drone'; tr = travel(0.5, 1 / 60, 5, frm)
e, a, up, fov = pose('drone'); game['garbage'] = (e, e, up, fov); v = render(); s = sobj(MGR + 0x510)
check('a camera whose look-at point is its eye (no direction): its state is left alone, blend dropped', raw(s + 0x30, 3) == raw(s + 0x6C, 3) and r32(BASE + D['BACTIVE']) == 0)
game['garbage'] = None
VIEWS['back'] = ((-1.3, 0.3, 2.1), (-1.3, 0.3, -3.0), (0, 1, 0), 60 * deg); VIEWS['fwd'] = ((-1.3, 0.3, 2.1), (-1.3, 0.3, 7.0), (0, 1, 0), 60 * deg)
setup(0.5, 0x1A38, 'fwd', 8); press(9); shown[0x1A38] = 'back'; r = [render() for k in range(33)]; finite = all(x == x and abs(x) < 1e6 for v in r for part in v[:3] for x in part)
check('old and new view looking in exactly opposite directions: every frame still a view of numbers with a direction (shortest eye-to-look-at %.3f m), ends on the camera' % min(norm(sub(v[1], v[0])) for v in r),
      finite and min(norm(sub(v[1], v[0])) for v in r) > 1.0 and untouched())
setup(0.5, 0x510, 'daytona', 3); names.pop('QueryPerformanceCounter'); w32(BASE + D['PQPC'], 0); press(4); shown[0x510] = 'drone'; r = [render() and untouched() for k in range(3)]; names['QueryPerformanceCounter'] = STUB + 0xE8
check('no QueryPerformanceCounter to be had: no blend, nothing written', all(r) and r32(BASE + D['BACTIVE']) == 0)

# back to how the old checks left things: smoothing and blend off, the chase camera
wf(BASE + D['K_BLEND'], 0.0); w32(MGR + 0x190, MGR + 0x510)
print('NEW CHECKS: %d passed, %d failed' % tuple(res))
