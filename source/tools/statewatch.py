"""Logs which bytes of a small Rally.exe memory range change over time (to find game-state flags).
    python statewatch.py <hex start> <length> <seconds> [interval]"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, time
K = ctypes.WinDLL('kernel32', use_last_error=True); K.OpenProcess.restype = wt.HANDLE
K.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Rally.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
pid = int(out.split('","')[1]); h = K.OpenProcess(0x0410, False, pid)
start, n, secs = int(sys.argv[1], 16), int(sys.argv[2]), float(sys.argv[3]); dt = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
def rd():
    b = ctypes.create_string_buffer(n); got = ctypes.c_size_t(); K.ReadProcessMemory(h, start, b, n, ctypes.byref(got)); return b.raw
prev = rd(); t0 = time.time(); print('%6.1f start %s' % (0, prev.hex()), flush=True)
while time.time() - t0 < secs:
    time.sleep(dt); cur = rd()
    if cur != prev:
        ch = ['%x:%02x>%02x' % (start + i, prev[i], cur[i]) for i in range(n) if prev[i] != cur[i]]
        if len(ch) <= 12: print('%6.1f %s' % (time.time() - t0, ' '.join(ch)), flush=True)
        prev = cur
