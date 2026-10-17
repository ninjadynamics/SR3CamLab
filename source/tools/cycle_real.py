"""Runs the block's blend hook and its smoothing (cycle.json) against SEGA Rally 3's OWN code instead of
cycle_emu.py's fake game: Rally.exe is loaded into the emulated CPU (read only; set SR3_EXE as for
build_patch.py). The hook is called the way 0x5C948C calls 0x5F1690; the game's routine, its cameras' vtables,
their interpolation (0x413990) and the accessors the view is built through (0x5EE1E0 eye, 0x5EE030 look-at,
0x5EE000 up, 0x5EDFD0 field of view) are the real ones. The update wrappers of the free cam and the car rotate
cam run into the game's own updates (0x5F3FE0 up to its first D3DX call, 0x5F1E00 up to the return of its input
handler 0x5EED30). The camera manager, the cameras' data, the car, the mouse and the clock are made up here.
It checks what cycle_emu.py has to take on trust: the hooked call's convention, where the game's interpolation
leaves its results, that the accessors hand out exactly the fields the blend writes, and what the game's updates
do with the inputs the wrappers write. It is still not the running game: when and how often the game makes
these calls is read from the disassembly only."""
import json, struct, math, os, sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *

exe = os.environ.get('SR3_EXE', '')
if not os.path.isfile(exe): sys.exit('Set SR3_EXE to the full path of Rally.exe (v3.8.4.1); the file is only read.')
image = open(exe, 'rb').read()
j = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cycle.json'))); D = j['data']
BASE = 0x20000000; OWNER = 0x30000000; MGR = OWNER + 0x18; STUB = 0x40000000; STACK = 0x50000000; DONE = 0x60000000
u = Uc(UC_ARCH_X86, UC_MODE_32)
for a, n in ((0x400000, 0x800000), (BASE, json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cycle.json")))["size"]), (OWNER, 0x10000), (STUB, 0x1000), (STACK - 0x10000, 0x20000), (DONE, 0x1000)): u.mem_map(a, n)
u.mem_write(0x400000, image[:0x32B000])                                 # headers, .text, .rdata, the initialised part of .data (file offset = RVA)
u.mem_write(BASE + j['codeOff'], bytes.fromhex(j['code'])); u.mem_write(BASE + j['code2Off'], bytes.fromhex(j['code2']))
u.mem_write(BASE, b'SR3V'); u.mem_write(BASE + D['S_K32'], b'kernel32.dll\0')
w32 = lambda a, v: u.mem_write(a, struct.pack('<I', v & 0xffffffff)); r32 = lambda a: struct.unpack('<I', u.mem_read(a, 4))[0]
wf = lambda a, *v: u.mem_write(a, struct.pack('<%df' % len(v), *v)); rf = lambda a, n=1: struct.unpack('<%df' % n, u.mem_read(a, 4 * n))
f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
res = [0, 0]
def check(what, ok, detail=''):
    res[0 if ok else 1] += 1; print('  %s %s%s' % ('ok    ' if ok else 'FAILED', what, '   [%s]' % detail if detail else ''))

# the game's bytes the hook and its reading of the game rest on
print('== Rally.exe:', len(image), 'bytes')
check('0x5C948C is "call 0x5F1690" (e8ff810200), the bytes sr3mods.ps1 expects', image[0x1C948C:0x1C9491].hex() == 'e8ff810200', image[0x1C948C:0x1C9491].hex())
check('0x5F1690 ends in "ret 4" (c20400) at 0x5F178E and starts with the state test "mov eax,[0x7ECE10]"', image[0x1F178E:0x1F1791].hex() == 'c20400' and image[0x1F1690:0x1F1695].hex() == 'a110ce7e00')
slot23 = {0x6EB808: 0x54, 0x6EB8B8: 0x54, 0x6EBD00: 8, 0x6EBD78: 8, 0x6EBDF0: 8, 0x6EBC88: 8, 0x6EBB30: 0x64, 0x6ECB98: 8, 0x6ECC88: 8}
ok = True
for vt, n in slot23.items():
    fn = r32(vt + 0x5C); ok &= bytes(u.mem_read(fn, 4)) == bytes([0x8D, 0x41, n, 0xC3]); slot4 = r32(vt + 0x10)
    ok &= bytes(u.mem_read(slot4, 10)) == bytes.fromhex('f30f10442408' '8d41') + bytes([n, 0xE8]) and (r32(slot4 + 10) + slot4 + 14) & 0xffffffff == 0x413990   # movss xmm0,[esp+8] ; lea eax,[ecx+n] ; call 0x413990
check('the 9 camera classes (chase, far chase, bumper, bonnet, cockpit, wheel, car rotate, free, car free): slot 23 is "lea eax,[ecx+N]; ret" with N = 0x54 / 0x64 / 8, and slot 4 interpolates that same object with 0x413990', ok)

# a made-up camera manager with the real vtables
w32(0x9EB4EC, OWNER); CHASE, BUMPER = MGR + 0x510, MGR + 0x1700; w32(CHASE, 0x6EB808); w32(BUMPER, 0x6EBD00)
sobj = lambda cam: cam + slot23[r32(cam)]
CAR = OWNER + 0xA000; w32(MGR + 0x1C8, CAR); yaw = 0.4; R, U, F, P = (math.cos(yaw), 0, -math.sin(yaw)), (0, 1, 0), (math.sin(yaw), 0, math.cos(yaw)), (250.0, 12.0, -80.0)
wf(CAR + 0x135C, *R, 0, *U, 0, *F, 0, *P, 1)
w32(0x9EB81C, OWNER + 0xC000); w32(OWNER + 0xC000 + 0x64, OWNER + 0xD000)       # 0x5F1690's tail reads three floats from [[0x9EB81C]+0x64]+0xB0
w32(0x7ECE10, 0x27); w32(0x7ECE14, 0x27)
world = lambda p, point=True: tuple(p[0] * R[i] + p[1] * U[i] + p[2] * F[i] + (P[i] if point else 0) for i in range(3))
def latch(cam, before, after, fovs):                                             # the two updates the drawn frame lies between: eye, look-at, up (car frame), field of view
    s = sobj(cam)
    for rec, point in ((0, True), (1, True), (4, False)):
        wf(s + 0x3C * rec + 0x18, *world(before[min(rec, 2)], point)); wf(s + 0x3C * rec + 0x24, *world(after[min(rec, 2)], point))
    wf(s + 0x170, *fovs)
stubs = {}; clock = [5000000000, 0]
def stub(addr, nargs, fn): stubs[addr] = (nargs, fn); u.mem_write(addr, b'\xc3')
cstr = lambda a: bytes(u.mem_read(a, 64)).split(b'\0')[0].decode()
stub(STUB, 1, lambda a: 0x77000000); stub(STUB + 8, 2, lambda a: {'QueryPerformanceFrequency': STUB + 0x10, 'QueryPerformanceCounter': STUB + 0x18}.get(cstr(a[1]), 0))
stub(STUB + 0x10, 1, lambda a: u.mem_write(a[0], struct.pack('<q', 10000000)) or 1); stub(STUB + 0x18, 1, lambda a: u.mem_write(a[0], struct.pack('<q', clock[0])) or 1)
w32(0x6741F4, STUB); w32(0x674204, STUB + 8)                                     # the import table's GetModuleHandleA / GetProcAddress
ran = []
def on_code(uc, addr, size, _):
    if addr in stubs:
        n, fn = stubs[addr]; esp = uc.reg_read(UC_X86_REG_ESP); ret = fn([r32(esp + 4 + 4 * i) for i in range(n)])
        uc.reg_write(UC_X86_REG_EAX, ret & 0xffffffff); uc.reg_write(UC_X86_REG_EIP, r32(esp)); uc.reg_write(UC_X86_REG_ESP, esp + 4 + 4 * n)
    elif addr in (0x5F1690, 0x413990): ran.append(addr)
u.hook_add(UC_HOOK_CODE, on_code)
ALPHA = 0.25
def run(entry, **regs):
    esp = STACK - 4; w32(esp, DONE); u.reg_write(UC_X86_REG_ESP, esp)
    for k, v in regs.items(): u.reg_write(getattr(sys.modules[__name__], 'UC_X86_REG_' + k.upper()), v)
    u.emu_start(entry, DONE, count=100000); return u.reg_read(UC_X86_REG_EAX)
def render(dt=1 / 60):                                                           # the hooked call, as at 0x5C9481: fld alpha ; push ecx ; lea esi,[owner+0x18] ; fstp [esp] ; call
    clock[0] += round(dt * 10000000); ran.clear(); esp = STACK - 4; wf(esp, ALPHA); esp -= 4; w32(esp, DONE)
    u.reg_write(UC_X86_REG_ESP, esp); u.reg_write(UC_X86_REG_ESI, MGR); u.reg_write(UC_X86_REG_EDI, 0x9DBAC8); u.reg_write(UC_X86_REG_EBP, 1)
    u.emu_start(BASE + j['blendOff'], DONE, count=200000)
    return u.reg_read(UC_X86_REG_ESP) == STACK and u.reg_read(UC_X86_REG_ESI) == MGR and u.reg_read(UC_X86_REG_EDI) == 0x9DBAC8 and u.reg_read(UC_X86_REG_EBP) == 1 and (u.reg_read(UC_X86_REG_FPSW) >> 11) & 7 == 0
def seen():                                                                      # what the view is built from, through the game's own accessors
    eye = run(0x5EE1E0, esi=MGR); at = run(0x5EE030, esi=MGR); up = run(0x5EE000, eax=MGR); run(0x5EDFD0, eax=MGR)
    return (eye, at, up), (rf(eye, 3), rf(at, 3), rf(up, 3), struct.unpack('<f', struct.pack('<I', u.reg_read(UC_X86_REG_XMM0) & 0xffffffff))[0])
mix = lambda a, b, s: tuple(x + (y - x) * s for x, y in zip(a, b)); dist = lambda a, b: max(abs(x - y) for x, y in zip(a, b))
def drawn(before, after, fovs):                                                  # the game's interpolation of a camera's two updates, in the world, with its
    g = lambda p, c: f32(f32(p) + f32(f32(f32(c) - f32(p)) * f32(ALPHA)))        # single-precision steps (0x413990: cur - prev, x alpha, + prev): the same bits
    v = lambda p, c: tuple(g(x, y) for x, y in zip(p, c))
    return v(world(before[0]), world(after[0])), v(world(before[1]), world(after[1])), v(world(before[2], False), world(after[2], False)), g(*fovs)
def off(v, w): return max(dist(v[0], w[0]), dist(v[1], w[1]), dist(v[2], w[2]), abs(v[3] - w[3]))
ease = lambda t: t * t * (3 - 2 * t)
def blend(frm, to, s):                                                           # the blend's arithmetic on two drawn views
    d0 = tuple(x - y for x, y in zip(frm[1], frm[0])); d1 = tuple(x - y for x, y in zip(to[1], to[0])); n0 = math.sqrt(sum(x * x for x in d0)); n1 = math.sqrt(sum(x * x for x in d1))
    e = mix(frm[0], to[0], s); d = mix(tuple(x / n0 for x in d0), tuple(x / n1 for x in d1), s); n = math.sqrt(sum(x * x for x in d)); ln = n0 + (n1 - n0) * s
    return e, tuple(e[i] + d[i] / n * ln for i in range(3)), mix(frm[2], to[2], s), frm[3] + (to[3] - frm[3]) * s

A = (((0.3, 1.9, -4.7), (0, 1.0, -0.87), (0, 1, 0)), ((0.32, 1.92, -4.6), (0.01, 1.0, -0.85), (0, 1, 0)), (1.25, 1.26))      # a chase view: before / after the last update
B = (((-0.2, 4.6, -6.9), (0, 1.0, -0.87), (0, 1, 0)), ((-0.2, 4.62, -6.8), (0, 1.01, -0.86), (0.02, 1, 0)), (1.5, 1.52))    # another framing of the same camera
C = (((0, 0.75, 1.45), (0, 0, 20), (0, 1, 0)), ((0, 0.76, 1.45), (0, 0.1, 20), (0, 1, 0)), (1.047, 1.047))                  # the bumper camera
for cam in (0x188, 0x18C, 0x190): w32(MGR + cam, CHASE)
wf(BASE + D['K_BLEND'], 0.5); latch(CHASE, *A)
print('== the hook around the real 0x5F1690, blend on, no View Change')
clean = render(); ptr, v = seen(); s = sobj(CHASE)
check('the game\'s routine ran once, its interpolation (0x413990) once; stack, esi / edi / ebp and x87 as the caller left them', ran == [0x5F1690, 0x413990] and clean, str([hex(x) for x in ran]))
check('it set the camera to draw from ([mgr+0x184] = [mgr+0x188]) and left the interpolated state where the blend reads it: eye state+0x30, look-at +0x6C, up +0x120, field of view +0x178 (off by %.2g)' % off(v, drawn(*A)),
      r32(MGR + 0x184) == CHASE and ptr == (s + 0x30, s + 0x6C, s + 0x120) and off(v, drawn(*A)) < 1e-4)
render(); render(); keep = seen()[1]
check('with no View Change the hook changes nothing of it (3 frames)', off(keep, drawn(*A)) < 1e-4 and r32(BASE + D['BACTIVE']) == 0 and r32(BASE + D['BHAVE']) == 1)
print('== View Change on the same camera object (set as the block\'s draw hook sets it), the camera then holds another view')
w32(BASE + D['BGO'], 1); latch(CHASE, *B); own = drawn(*B); path = []
for k in range(34):
    clean &= render(); t = k * (round(1e7 / 60) / 1e7) / 0.5; v = seen()[1]; path.append((t, off(v, blend(keep, own, ease(t))) if t < 1 else None, off(v, own)))
done = [k for k, x in enumerate(path) if x[2] == 0]
check('first frame = the old view (off by %.2g); every frame on the eased path as the renderer\'s accessors see it (worst %.2g); half way at t = %.3f' % (path[0][1], max(x[1] for x in path if x[1] is not None), path[15][0]),
      path[0][1] < 1e-4 and max(x[1] for x in path if x[1] is not None) < 3e-4 and path[0][2] > 1)
check('from frame %d on (%.3f s) the accessors give exactly the game\'s own interpolation of the new view; stack and registers right in all %d frames' % (done[0], done[0] / 60, len(path)), done == list(range(done[0], 34)) and done[0] in (30, 31) and clean)
print('== View Change to another object: the game moves [mgr+0x188] to the bumper camera a few frames later')
w32(BASE + D['BWAIT'], BUMPER); w32(BASE + D['BWAITN'], 120); latch(BUMPER, *C); w32(MGR + 0x190, BUMPER)
wait = [render() and off(seen()[1], own) == 0 for k in range(3)]; ran3 = list(ran)
check('while it still draws from the chase camera: untouched (3 frames); the game interpolates both cameras in those frames (0x413990 ran %d times a frame)' % ran3.count(0x413990), all(wait) and ran3.count(0x413990) == 2)
for cam in (0x18C, 0x188): w32(MGR + cam, BUMPER)
keep = own; own = drawn(*C); path = []
for k in range(34):
    clean &= render(); t = k * (round(1e7 / 60) / 1e7) / 0.5; ptr, v = seen(); path.append((t, off(v, blend(keep, own, ease(t))) if t < 1 else None, off(v, own)))
done = [k for k, x in enumerate(path) if x[2] == 0]; s = sobj(BUMPER)
check('the accessors now point into the bumper camera\'s state (+8): eye +0x30, look-at +0x6C, up +0x120', ptr == (s + 0x30, s + 0x6C, s + 0x120))
check('first frame from it = the chase view (off by %.2g), eased path to the bumper view (worst %.2g), the game\'s own values from frame %d on' % (path[0][1], max(x[1] for x in path if x[1] is not None), done[0]),
      path[0][1] < 1e-4 and max(x[1] for x in path if x[1] is not None) < 5e-4 and done == list(range(done[0], 34)) and done[0] in (30, 31) and clean)
print('== the game outside its running states')
w32(BASE + D['BGO'], 1); w32(0x7ECE10, 0x30); before = bytes(u.mem_read(s, 0x17C)); render()
check('state 0x30: the real routine returns at once (no interpolation: 0x413990 ran %d times) and the hook leaves the state and its own flags alone' % ran.count(0x413990), ran == [0x5F1690] and bytes(u.mem_read(s, 0x17C)) == before and r32(BASE + D['BGO']) == 1)

# ---- the smoothing in front of the game's own updates of the steerable cameras
print('== free cam: the wrapper, then the game\'s update 0x5F3FE0 (to its first D3DX call)')
blk = {0xEA0: b'user32.dll', 0xEB0: b'GetCursorPos', 0xEC0: b'SetCursorPos', 0xED0: b'GetAsyncKeyState', 0xEF0: b'GetForegroundWindow', 0xF40: b'GetWindowThreadProcessId', 0xF70: b'GetCurrentProcessId'}
for o, t in blk.items(): u.mem_write(BASE + o, t + b'\0')                         # the block's data, as sr3mods.ps1 writes it
wf(BASE + 0xF10, 0.0025, math.pi / 2, 10.0, 1.0); wf(BASE + 0xF90, 1.5706, -1.5706); wf(BASE + 0xFE0, 3.0, 30.0, 0.5, 20.0); wf(BASE + 0xFD0, -0.01)
w32(0x7EDB74, 1920); w32(0x7EDB78, 1080); mouse = dict(pos=(960, 540), keys=set())
api = {'GetCursorPos': (1, lambda a: u.mem_write(a[0], struct.pack('<ii', *mouse['pos'])) or 1), 'SetCursorPos': (2, lambda a: mouse.update(pos=(a[0], a[1])) or 1),
       'GetAsyncKeyState': (1, lambda a: 0x8000 if a[0] in mouse['keys'] else 0), 'GetForegroundWindow': (0, lambda a: 0x5555),
       'GetWindowThreadProcessId': (2, lambda a: w32(a[1], 4242) or 1), 'GetCurrentProcessId': (0, lambda a: 4242)}
addr = {}
for k, (name, (n, fn)) in enumerate(api.items()): addr[name] = STUB + 0x40 + 8 * k; stub(addr[name], n, fn)
stub(STUB + 8, 2, lambda a: {'QueryPerformanceFrequency': STUB + 0x10, 'QueryPerformanceCounter': STUB + 0x18, **addr}.get(cstr(a[1]), 0))
FREE, ROT = MGR + 0xC78, MGR + 0xEEC; w32(FREE, 0x6ECB98); w32(ROT, 0x6EBB30); wf(FREE + 0x230, 0.02); wf(OWNER + 0x9000, 7.0, 2.3); w32(MGR + 0x50C, OWNER + 0x9000); w32(0x7ECE10, 0x27)
stops = {0x5F41E7: 'free', 0x5F1E62: 'rot'}; reached = []
def on_stop(uc, a, size, _):
    if a in stops: reached.append(a); uc.emu_stop()
u.hook_add(UC_HOOK_CODE, on_stop)
def update(cam, entry, dx=0, dy=0, keys=()):                                     # the game calls a camera's update: ecx = camera, the manager on the stack
    mouse['pos'] = (960 + dx, 540 + dy); mouse['keys'] = set(keys); reached.clear()
    esp = STACK - 4; w32(esp, MGR); esp -= 4; w32(esp, DONE); u.reg_write(UC_X86_REG_ESP, esp); u.reg_write(UC_X86_REG_ECX, cam); u.reg_write(UC_X86_REG_ESI, 0x1234)
    u.emu_start(BASE + entry, DONE, count=200000)
    return reached == [a for a, n in stops.items() if n == ('rot' if cam == ROT else 'free')] and (u.reg_read(UC_X86_REG_FPSW) >> 11) & 7 == 0
def select(cam, tau, dt):                                                        # this camera freshly selected: the controls as the block leaves them while none is on
    wf(BASE + D['K_LOOKTAU'], tau); wf(BASE + D['K_MOVETAU'], 2 * tau); wf(MGR, dt); w32(MGR + 0x190, cam)
    u.mem_write(BASE + D['MREM'], bytes(8)); u.mem_write(BASE + D['KAX'], bytes(16)); w32(BASE + D['NEEDCENTER'], 1)
    for o in (0x268, 0x26C, 0x270, 0x22C): wf(FREE + o, 0.0)
    for o in (0x0C, 0x20, 0x34, 0x48): wf(ROT + o, 0.0)
    return update(cam, j['rotOff'] if cam == ROT else j['freeOff'])
ok = select(FREE, 0.0, 1 / 60); ok &= update(FREE, j['freeOff'], 120, -60)
check('smoothing 0: the game\'s update is reached with the wrapper\'s inputs and adds the whole movement at once: yaw %.6f (raw 0.3), pitch %.6f (raw -0.15)' % (rf(FREE + 0x26C)[0], rf(FREE + 0x268)[0]),
      ok and abs(rf(FREE + 0x26C)[0] - 0.3) < 1e-6 and abs(rf(FREE + 0x268)[0] + 0.15) < 1e-6)
got = {}
for fps in (30, 60, 120):
    ok = select(FREE, 0.08, 1 / fps)
    for k in range(round(0.2 * fps)): ok &= update(FREE, j['freeOff'], 120 if k == 0 else 0, -60 if k == 0 else 0)
    got[fps] = rf(FREE + 0x26C)[0] / 0.3
    for k in range(round(1.5 * fps)): ok &= update(FREE, j['freeOff'])
    got[fps] = (got[fps], rf(FREE + 0x26C)[0], rf(FREE + 0x268)[0], ok)
want = 1 - math.exp(-0.2 / 0.08)
check('smoothing 0.08 s at 30 / 60 / 120 updates a second: the game\'s own yaw is %s of the way after 0.2 s (want %.4f) and ends on %s (raw 0.3), pitch on %s (raw -0.15)'
      % (' / '.join('%.4f' % got[k][0] for k in sorted(got)), want, ' / '.join('%.6f' % got[k][1] for k in sorted(got)), ' / '.join('%.6f' % got[k][2] for k in sorted(got))),
      all(g[3] and abs(g[0] - want) < 1e-4 and abs(g[1] - 0.3) < 2e-6 and abs(g[2] + 0.15) < 2e-6 for g in got.values()))
print('== car rotate cam: the wrapper, then the game\'s update 0x5F1E00 (to the return of its input handler 0x5EED30)')
ok = select(ROT, 0.08, 1 / 60)
for k in range(150): ok &= update(ROT, j['rotOff'], 90 if k == 0 else 0, 40 if k == 0 else 0)
check('a 90 / 40 pixel flick, smoothed: the game\'s handler ends the orbit angle on %.6f rad (raw 0.225) and the height offset on %.6f m (raw -0.4)' % (rf(ROT + 0x0C)[0], rf(ROT + 0x48)[0]),
      ok and abs(rf(ROT + 0x0C)[0] - 0.225) < 3e-6 and abs(rf(ROT + 0x48)[0] + 0.4) < 3e-6)
print('REAL-CODE CHECKS: %d passed, %d failed' % tuple(res))
