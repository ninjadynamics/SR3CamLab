"""SEGA Rally Championship (Model 2A) lap recorder: reads the running emulator's memory (read-only) at ~60 Hz into a CSV.

    python src_recorder.py [--process EMULATOR.EXE] [--out laps.csv] [--hz 60] [--seconds 0 (=until Ctrl+C)]

Works with ElSemi's Model 2 emulator (EMULATOR.EXE / emulator_multicpu.exe) and with MAME (mame.exe); it only READS the
process (OpenProcess with PROCESS_VM_READ | PROCESS_QUERY_INFORMATION), never writes.

How it finds the emulated RAM: the game's two RAM areas are separate buffers in the emulator, located by signatures
(found with MAME runs of srallyc, 2026-10-14):
  * work RAM 0x200000: the list of car display slots at 0x213980 = {0x213B40, 0x213B98, ...} (8 entries in a
    Championship, 2 in Practice); a hit is accepted when the player's slot record holds the car object's position.
    Validated against MAME (2026-10-14): positions exact, accelerator 100 %, wheel within one frame, 60 Hz.
  * RAM 0x500000: the player car object = {4, <code ptr>, <prev>, 0x00500100 (next object), ...}; the scan keys on the
    "next" pointer at +0x0C and checks that +0x8C points to 0x213B40 (its display slot).
Player car object fields (Model 2 addresses; floats; speed unit = metres per frame, 1 m/frame = 216 km/h on the speedo):
  0x500014/18/1C position x, y (up), z     0x50002C/30/34 velocity x, y, z (world)     0x500038/3C/40 pitch, yaw, roll (rad;
  heading psi = -yaw, atan2(dx, dz) convention)    0x500078 gear (u32)    0x50007C engine rpm    0x500080 wheel spin rate
Inputs (bytes the game copies from the ADC each frame): 0x202050 steering (0x80 = centre, raw), 0x202051 accelerator,
0x202052 brake.  0x20B0B0 = remaining time (frames) (18_src_1995_rom_data.md).
The CSV columns match analyse.py (t, r, acc, steer, brk, gear, x, y, z, vx, vy, vz, w38, w3c, w40, rpm, wspd, psi)."""
import ctypes, ctypes.wintypes as W, struct, sys, time, argparse, os

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400
MEM_COMMIT, PAGE_NOACCESS, PAGE_GUARD = 0x1000, 0x01, 0x100
class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p), ('AllocationProtect', W.DWORD),
                ('PartitionId', W.WORD), ('RegionSize', ctypes.c_size_t), ('State', W.DWORD), ('Protect', W.DWORD), ('Type', W.DWORD)]
k32.OpenProcess.restype = W.HANDLE
k32.VirtualQueryEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

def find_pid(names):
    import subprocess
    out = subprocess.run(['tasklist', '/fo', 'csv', '/nh'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower() in names: return int(parts[1]), parts[0]
    return None, None

class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h: raise OSError('OpenProcess failed (%d)' % ctypes.get_last_error())
    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n: return None
        return buf.raw
    def regions(self):
        a, mbi = 0, MBI()
        while k32.VirtualQueryEx(self.h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            if mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) and size >= 0x10000:
                yield base, size
            a = base + size
            if a >= 1 << 47: break

SLOTS = b''.join(struct.pack('<I', 0x213B40 + 0x58 * i) for i in range(8))     # at Model 2 address 0x213980
NEXT = struct.pack('<I', 0x00500100)

SLOT_ADDRS = set(0x213B40 + 0x58 * i for i in range(8))

def chunks(p):
    for base, size in p.regions():
        for off in range(0, size, 1 << 24):
            d = p.read(base + off, min(1 << 24, size - off))
            if d is not None: yield base + off, d

def scan(p, verbose=False):
    """returns (host address of Model 2 0x200000, host address of Model 2 0x500000) or None.
    0x500000: the player car object {4, code ptr, prev, next = 0x500100, ...} whose +0x8C points at one of the 8 display
    slots. 0x200000: the slot list at 0x213980 if present; otherwise found from the slot record, which holds the same
    position (x, y, z) as the object (+0x14)."""
    b2 = b5 = None; slot = None; pos = None
    for host, d in chunks(p):
        if b5 is None:
            i = d.find(NEXT)
            while i >= 0:
                o = i - 0x0C
                if o >= 0 and o + 0x90 <= len(d):
                    w = struct.unpack_from('<I', d, o)[0]; s = struct.unpack_from('<I', d, o + 0x8C)[0]
                    if w == 4 and s in SLOT_ADDRS: b5 = host + o; slot = s; pos = d[o + 0x14:o + 0x20]; break
                i = d.find(NEXT, i + 1)
        if b2 is None:
            i = d.find(SLOTS)
            if i >= 0: b2 = host + i - 0x13980
    if b5 is not None and b2 is None:
        # Practice mode has only 2 slots in the list at 0x213980: {0x213B40, 0x213B98, 0, ...}. Each hit is checked by
        # comparing the player's display slot (which holds the car position) with the car object's position.
        key = SLOTS[:8]
        for host, d in chunks(p):
            i = d.find(key)
            while i >= 0:
                cand = host + i - 0x13980
                a, b = p.read(cand + (slot - 0x200000), 12), p.read(b5 + 0x14, 12)
                if a and b:
                    pa, pb = struct.unpack('<3f', a), struct.unpack('<3f', b)
                    if all(abs(x - y) < 3.0 for x, y in zip(pa, pb)) and any(abs(x) > 1e-3 for x in pb): b2 = cand; break
                i = d.find(key, i + 1)
            if b2 is not None: break
    if verbose: print('  scan: car object %s, work RAM %s' % (hex(b5) if b5 else 'not found', hex(b2) if b2 else 'not found'))
    if b2 is not None and b5 is not None: return b2, b5
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--process', default='')
    ap.add_argument('--out', default='src_lap_%s.csv' % time.strftime('%Y%m%d_%H%M%S'))
    ap.add_argument('--hz', type=float, default=60.0)
    ap.add_argument('--seconds', type=float, default=0.0)
    a = ap.parse_args()
    names = [a.process.lower()] if a.process else ['emulator.exe', 'emulator_multicpu.exe', 'mame.exe']
    pid, name = find_pid(names)
    if not pid: sys.exit('no emulator process found (%s)' % ', '.join(names))
    p = Proc(pid)
    print('reading %s (pid %d), read-only' % (name, pid))
    try: ctypes.WinDLL('winmm').timeBeginPeriod(1)
    except OSError: pass
    def alive():
        return find_pid([name.lower()])[0] == pid
    found = None; tries = 0
    while not found:
        found = scan(p, verbose=(tries % 5 == 0))
        if not found:
            if not alive(): sys.exit('the emulator has ended')
            tries += 1; print('  game RAM not found yet (start a race); trying again in 2 s'); time.sleep(2)
    b2, b5 = found
    print('  RAM 0x200000 at host %#x, RAM 0x500000 at host %#x; writing %s (Ctrl+C to stop)' % (b2, b5, a.out))
    f = open(a.out, 'w', newline='')
    f.write('t,r,acc,steer,brk,gear,x,y,z,vx,vy,vz,w38,w3c,w40,rpm,wspd,psi,time_left,host_t\n')
    t0 = time.perf_counter(); period = 1.0 / a.hz; nxt = t0; last = None; n = 0; lost = 0
    try:
        while True:
            now = time.perf_counter()
            if now < nxt: time.sleep(max(0, nxt - now - 0.0015)); continue
            nxt += period
            if nxt < now - 0.5: nxt = now + period
            car = p.read(b5, 0x90); inp = p.read(b2 + 0x2050, 4); tl = p.read(b2 + 0xB0B0, 4)
            if car is None or inp is None:
                lost += 1
                if lost > 120: print('  emulator gone'); break
                continue
            lost = 0
            if struct.unpack_from('<I', car, 0x0C)[0] != 0x00500100:            # object moved / race over: find it again
                print('  car object lost; rescanning'); found = None
                while not found:
                    found = scan(p)
                    if not found:
                        if not alive(): break
                        time.sleep(1)
                if not found: print('  the emulator has ended'); break
                b2, b5 = found; continue
            fl = lambda o: struct.unpack_from('<f', car, o)[0]
            vals = (fl(0x14), fl(0x18), fl(0x1C), fl(0x2C), fl(0x30), fl(0x34), fl(0x38), fl(0x3C), fl(0x40))
            if vals == last: continue                                            # emulator paused or slower than the sampler
            last = vals; n += 1
            ht = now - t0
            f.write('%.4f,%.4f,%d,%d,%d,%d,%s,%.6g,%.6g,%.6g,%d,%.4f\n' % (ht, ht, inp[1], inp[0], inp[2], struct.unpack_from('<I', car, 0x78)[0],
                    ','.join('%.6g' % v for v in vals), fl(0x7C), fl(0x80), -fl(0x3C), struct.unpack_from('<i', tl, 0)[0] if tl else 0, ht))
            if n % 600 == 0:
                f.flush(); v = (vals[3] ** 2 + vals[5] ** 2) ** 0.5 * 216
                print('  %6.0f s  %5.0f km/h  gear %d' % (ht, v, struct.unpack_from('<I', car, 0x78)[0]))
            if a.seconds and ht > a.seconds: break
    except KeyboardInterrupt: pass
    f.close(); print('%d samples written to %s' % (n, a.out))

if __name__ == '__main__': main()

