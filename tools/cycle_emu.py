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
for a, n in ((0x400000, 0x800000), (BASE, 0x3000), (MGR_OWNER, 0x10000), (STUB, 0x1000), (FONT, 0x2000),
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
