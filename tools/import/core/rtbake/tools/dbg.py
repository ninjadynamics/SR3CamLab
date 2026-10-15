"""Crash logger: attaches to Rally.exe as a debugger and writes every access violation (registers,
stack, call chain guesses) to crash.log. Changes nothing in the game; exceptions are passed on."""
import ctypes, ctypes.wintypes as wt, sys, time, os, struct, subprocess
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crash.log')
def log(s):
    line = time.strftime('%H:%M:%S ') + s
    print(line, flush=True); open(LOG, 'a').write(line + '\n')

class EXCEPTION_RECORD64(ctypes.Structure):
    _fields_ = [('ExceptionCode', wt.DWORD), ('ExceptionFlags', wt.DWORD), ('ExceptionRecord', ctypes.c_uint64), ('ExceptionAddress', ctypes.c_uint64),
                ('NumberParameters', wt.DWORD), ('pad', wt.DWORD), ('ExceptionInformation', ctypes.c_uint64 * 15)]
class EXCEPTION_DEBUG_INFO(ctypes.Structure): _fields_ = [('ExceptionRecord', EXCEPTION_RECORD64), ('dwFirstChance', wt.DWORD)]
class DEBUG_EVENT(ctypes.Structure):
    class U(ctypes.Union): _fields_ = [('Exception', EXCEPTION_DEBUG_INFO), ('raw', ctypes.c_byte * 160)]
    _fields_ = [('dwDebugEventCode', wt.DWORD), ('dwProcessId', wt.DWORD), ('dwThreadId', wt.DWORD), ('u', U)]
class FLOATING_SAVE_AREA(ctypes.Structure):
    _fields_ = [('a', wt.DWORD * 7), ('RegisterArea', ctypes.c_byte * 80), ('Cr0NpxState', wt.DWORD)]
class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [('ContextFlags', wt.DWORD), ('Dr', wt.DWORD * 6), ('FloatSave', FLOATING_SAVE_AREA), ('SegGs', wt.DWORD), ('SegFs', wt.DWORD), ('SegEs', wt.DWORD), ('SegDs', wt.DWORD),
                ('Edi', wt.DWORD), ('Esi', wt.DWORD), ('Ebx', wt.DWORD), ('Edx', wt.DWORD), ('Ecx', wt.DWORD), ('Eax', wt.DWORD), ('Ebp', wt.DWORD), ('Eip', wt.DWORD), ('SegCs', wt.DWORD),
                ('EFlags', wt.DWORD), ('Esp', wt.DWORD), ('SegSs', wt.DWORD), ('Ext', ctypes.c_byte * 512)]
k32.OpenThread.restype = wt.HANDLE; k32.OpenProcess.restype = wt.HANDLE

def find_pid():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Rally.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    for l in out.splitlines():
        p = l.split('","')
        if len(p) > 1 and p[0].strip('"').lower() == 'rally.exe': return int(p[1])
def rd(h, a, n):
    b = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    return b.raw[:got.value] if k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(got)) else b''

log('waiting for Rally.exe...')
pid = None
while pid is None: pid = find_pid(); time.sleep(0.5)
delay = float(sys.argv[1]) if len(sys.argv) > 1 else 45
log('Rally.exe pid %d; attaching in %.0f s (after boot)' % (pid, delay)); time.sleep(delay)
if not k32.DebugActiveProcess(pid): log('attach failed, error %d' % ctypes.get_last_error()); sys.exit(1)
k32.DebugSetProcessKillOnExit(False)
hp = k32.OpenProcess(0x0410, False, pid)
log('attached')
ev = DEBUG_EVENT(); nav = 0; seen = {}
dbgout = open(os.path.join(os.path.dirname(LOG), 'gamelog.txt'), 'w', encoding='utf-8')
while True:
    if not k32.WaitForDebugEvent(ctypes.byref(ev), 1000):
        if find_pid() is None: log('process gone'); break
        continue
    status = 0x00010002                                           # DBG_CONTINUE
    code = ev.dwDebugEventCode
    if code == 1:
        r = ev.u.Exception.ExceptionRecord; ec = r.ExceptionCode; first = ev.u.Exception.dwFirstChance
        if ec in (0x80000003, 0x4000001F, 0x80000004, 0x4000001E): status = 0x00010002
        else:
            status = 0x80010001                                   # DBG_EXCEPTION_NOT_HANDLED
            nall = globals().get('nall', 0) + 1; globals()['nall'] = nall
            if nall <= 400: open(LOG + '.all', 'a').write(time.strftime('%H:%M:%S ') + 'exception %08x at %08x %s thread %d' % (ec, r.ExceptionAddress, 'first' if first else 'SECOND', ev.dwThreadId) + chr(10))
            key = (ec, r.ExceptionAddress); seen[key] = seen.get(key, 0) + 1
            if ec == 0xC0000005 or not first or seen[key] <= 2:
                if seen[key] <= 3 or not first:
                    log('EXCEPTION %08x at %08x %s chance, thread %d, info %s' % (ec, r.ExceptionAddress, 'first' if first else 'SECOND', ev.dwThreadId, ' '.join('%x' % r.ExceptionInformation[i] for i in range(min(r.NumberParameters, 4)))))
                    ht = k32.OpenThread(0x1FFFFF, False, ev.dwThreadId); c = WOW64_CONTEXT(); c.ContextFlags = 0x10007
                    if ht and k32.Wow64GetThreadContext(ht, ctypes.byref(c)):
                        log('  eip %08x eax %08x ebx %08x ecx %08x edx %08x esi %08x edi %08x ebp %08x esp %08x' % (c.Eip, c.Eax, c.Ebx, c.Ecx, c.Edx, c.Esi, c.Edi, c.Ebp, c.Esp))
                        log('  code: ' + rd(hp, c.Eip - 16, 48).hex())
                        st = rd(hp, c.Esp, 0x400); words = struct.unpack('<%dI' % (len(st) // 4), st[:len(st) // 4 * 4])
                        log('  stack: ' + ' '.join('%08x' % w for w in words[:48]))
                        log('  return-address candidates: ' + ' '.join('%08x' % w for w in words if 0x401000 <= w < 0x674000)[:900])
                        for nm, v in (('eax', c.Eax), ('ecx', c.Ecx), ('edx', c.Edx), ('esi', c.Esi), ('edi', c.Edi), ('ebx', c.Ebx)):
                            m = rd(hp, v, 32)
                            if m: log('  [%s] %s' % (nm, m.hex()))
                    if ht: k32.CloseHandle(ht)
    elif code == 8:                                               # OutputDebugString
        ptr, uni, ln = struct.unpack_from('<QHH', bytes(ev.u.raw), 0)
        t = rd(hp, ptr, min(ln, 600)); t = t.decode('utf-16le', 'replace') if uni else t.decode('latin1', 'replace')
        t = t.rstrip(chr(0) + chr(13) + chr(10))
        if t: dbgout.write(time.strftime('%H:%M:%S ') + t + chr(10)); dbgout.flush()
    elif code == 5: log('process exited, exit code %08x' % struct.unpack_from('<I', bytes(ev.u.raw), 0)[0]); k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status); break
    elif code in (3, 6):                                          # process / dll load: close the file handle we are given
        h = ctypes.cast(ctypes.byref(ev.u), ctypes.POINTER(wt.HANDLE))[0]
        if h: k32.CloseHandle(h)
    k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
log('done')
