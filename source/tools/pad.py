"""Software gamepad for unattended tests: feeds TeknoParrotUi's XInput reader from a script.

    python pad.py hook                      install the hook in the running TeknoParrotUi (in memory only)
    python pad.py set [names...] [gas=0..1] [brake=0..1] [steer=-1..1]     hold this state until the next call
    python pad.py tap <name> [seconds]      press one button briefly (start, coin, view, handbrake, up, down)
    python pad.py state                     print the state last written

How: XInputGetState of every xinput*.dll loaded in TeknoParrotUi is redirected to a stub that copies a 16-byte
XINPUT_STATE from a buffer this script owns (pad 0 only; other pads report "not connected"). The real controller is
ignored until TeknoParrotUi is closed. Nothing is written to disk except the buffer address (pad_state.json).
SR3 profile bindings (UserProfiles/SR3.xml): Coin = Back, Start = Start, wheel = left stick X, gas = right trigger,
brake = left trigger, View Change = A, handbrake = right shoulder, shift up = right stick Y+, shift down = right stick X-.
"""
import ctypes, ctypes.wintypes as wt, json, os, struct, sys, time

K = ctypes.WinDLL('kernel32', use_last_error=True); P = ctypes.WinDLL('psapi', use_last_error=True)
K.OpenProcess.restype = wt.HANDLE; K.VirtualAllocEx.restype = ctypes.c_void_p
K.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
K.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
K.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
K.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, ctypes.POINTER(wt.DWORD)]
P.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
P.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]
K.IsWow64Process.argtypes = [wt.HANDLE, ctypes.POINTER(wt.BOOL)]
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pad_state.json')
BUTTON = dict(start=0x10, coin=0x20, back=0x20, view=0x1000, a=0x1000, handbrake=0x200, rb=0x200)

def pid_of(name):
    import subprocess
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ' + name, '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    for ln in out.splitlines():
        p = ln.split('","')
        if len(p) > 1 and p[0].strip('"').lower() == name.lower(): return int(p[1])
    return None

def rd(h, a, n):
    b = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    if not K.ReadProcessMemory(h, a, b, n, ctypes.byref(got)): raise OSError('read %x: %d' % (a, ctypes.get_last_error()))
    return b.raw

def wr(h, a, data):
    old = wt.DWORD(); K.VirtualProtectEx(h, a, len(data), 0x40, ctypes.byref(old)); got = ctypes.c_size_t()
    ok = K.WriteProcessMemory(h, a, data, len(data), ctypes.byref(got)); K.VirtualProtectEx(h, a, len(data), old.value, ctypes.byref(old))
    if not ok: raise OSError('write %x: %d' % (a, ctypes.get_last_error()))

def modules(h):
    arr = (ctypes.c_void_p * 2048)(); need = wt.DWORD()
    P.EnumProcessModulesEx(h, arr, ctypes.sizeof(arr), ctypes.byref(need), 3)
    out = []
    for m in arr[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
        if not m: continue
        nm = ctypes.create_unicode_buffer(260); P.GetModuleBaseNameW(h, m, nm, 260); out.append((nm.value, m))
    return out

def export(h, base, want):
    """address of an exported function, read from the module's headers in the other process -> (address, is64)"""
    pe = struct.unpack_from('<I', rd(h, base + 0x3c, 4))[0]; magic = struct.unpack_from('<H', rd(h, base + pe + 24, 2))[0]; is64 = magic == 0x20b
    rva, size = struct.unpack_from('<II', rd(h, base + pe + 24 + (112 if is64 else 96), 8))
    if not rva: return None, is64
    ex = rd(h, base + rva, 40); nnames = struct.unpack_from('<I', ex, 24)[0]; afn, anm, aord = struct.unpack_from('<III', ex, 28)
    names = struct.unpack('<%dI' % nnames, rd(h, base + anm, 4 * nnames)); ords = struct.unpack('<%dH' % nnames, rd(h, base + aord, 2 * nnames))
    for i, n in enumerate(names):
        if rd(h, base + n, len(want) + 1) == want.encode() + b'\0':
            return base + struct.unpack_from('<I', rd(h, base + afn + 4 * ords[i], 4))[0], is64
    return None, is64

def hook():
    pid = pid_of('TeknoParrotUi.exe')
    if not pid: sys.exit('TeknoParrotUi.exe is not running')
    h = K.OpenProcess(0x1F0FFF, False, pid)
    if not h: sys.exit('cannot open TeknoParrotUi (%d)' % ctypes.get_last_error())
    mem = K.VirtualAllocEx(h, None, 0x1000, 0x3000, 0x40)
    if not mem: sys.exit('no memory in TeknoParrotUi (%d)' % ctypes.get_last_error())
    buf = mem + 0x800; done = []
    for name, base in modules(h):
        if not name.lower().startswith('xinput'): continue
        fn, is64 = export(h, base, 'XInputGetState')
        if not fn: continue
        cave = mem + 0x40 * len(done)
        if is64:
            stub = b'\x85\xC9\x75\x1B\x48\xB8' + struct.pack('<Q', buf) + b'\x4C\x8B\x00\x4C\x89\x02\x4C\x8B\x40\x08\x4C\x89\x42\x08\x33\xC0\xC3' + b'\xB8\x8F\x04\x00\x00\xC3'
            jump = b'\x48\xB8' + struct.pack('<Q', cave) + b'\xFF\xE0'
        else:
            stub = b'\x8B\x44\x24\x04\x85\xC0\x75\x1B\x8B\x54\x24\x08\x56\x57\xBE' + struct.pack('<I', buf) + b'\x8B\xFA\xB9\x04\x00\x00\x00\xF3\xA5\x5F\x5E\x33\xC0\xC2\x08\x00' + b'\xB8\x8F\x04\x00\x00\xC2\x08\x00'
            jump = b'\xE9' + struct.pack('<i', cave - (fn + 5))
        wr(h, cave, stub); wr(h, fn, jump); done.append((name, hex(fn), 64 if is64 else 32))
    if not done: sys.exit('no xinput module is loaded in TeknoParrotUi yet (start the game first)')
    json.dump(dict(pid=pid, buf=buf, packet=1, buttons=0, lt=0, rt=0, lx=0), open(STATE, 'w'))
    write(dict(pid=pid, buf=buf, packet=1), 0, 0, 0, 0)
    print('hooked', done)

def write(st, buttons, lt, rt, lx, ry=0, rx=0):
    h = K.OpenProcess(0x1F0FFF, False, st['pid'])
    if not h: sys.exit('TeknoParrotUi (pid %d) is gone' % st['pid'])
    st['packet'] = st.get('packet', 0) + 1
    wr(h, st['buf'], struct.pack('<IHBBhhhh', st['packet'], buttons, lt, rt, lx, 0, rx, ry)); K.CloseHandle(h)
    st.update(buttons=buttons, lt=lt, rt=rt, lx=lx); json.dump(st, open(STATE, 'w'))

def parse(args):
    b = 0; gas = brake = steer = 0.0; ry = rx = 0
    for a in args:
        if '=' in a:
            k, v = a.split('='); v = float(v)
            if k == 'gas': gas = v
            elif k == 'brake': brake = v
            elif k == 'steer': steer = v
        elif a == 'up': ry = 32767
        elif a == 'down': rx = -32768
        else: b |= BUTTON[a]
    return b, int(255 * brake), int(255 * gas), int(32767 * max(-1, min(1, steer))), ry, rx

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'state'
    if cmd == 'hook': hook()
    elif cmd == 'state': print(open(STATE).read() if os.path.exists(STATE) else 'not hooked')
    else:
        st = json.load(open(STATE))
        if cmd == 'set': write(st, *parse(sys.argv[2:]))
        elif cmd == 'tap':
            keep = (st.get('buttons', 0), st.get('lt', 0), st.get('rt', 0), st.get('lx', 0)); b, lt, rt, lx, ry, rx = parse(sys.argv[2:3])
            write(st, keep[0] | b, keep[1], keep[2], keep[3], ry, rx); time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 0.15); write(st, *keep)
