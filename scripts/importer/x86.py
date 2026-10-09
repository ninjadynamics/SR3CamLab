"""Rally.exe static-analysis helpers (read-only). Usage:
  python x86.py dis <addr> [len]         disassemble
  python x86.py fn <addr> [maxlen]       disassemble the function containing addr
  python x86.py str <regex>              find strings + code xrefs
  python x86.py xref <addr>              find code/data references to an address (imm32 / disp32 / call / jmp)
  python x86.py find <hexbytes>
"""
import sys, os, struct, re, pefile, capstone, bisect
EXE = r"F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally\Rally.exe"
pe = pefile.PE(EXE, fast_load=True); base = pe.OPTIONAL_HEADER.ImageBase
img = bytes(pe.get_memory_mapped_image())
TEXT = (0x401000, 0x401000 + 0x272c80)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
def rd(a, n): return img[a - base:a - base + n]
def u32(a): return struct.unpack_from('<I', img, a - base)[0]
def f32(a): return struct.unpack_from('<f', img, a - base)[0]
def cstr(a, mn=3):
    o = a - base
    if 0 < o < len(img):
        s = img[o:o + 96].split(b'\0')[0]
        if len(s) >= mn and all(32 <= c < 127 for c in s): return s.decode()
def note_for(i):
    note = ''
    for tok in re.findall(r'0x[0-9a-f]+', i.op_str):
        v = int(tok, 16)
        if 0x674000 <= v < 0xb4d000:
            s = cstr(v)
            if s: note += '   ; "%s"' % s
            elif 0x674000 <= v < 0x707000 and 'dword ptr' in i.op_str and ('fld' in i.mnemonic or 'fmul' in i.mnemonic or 'fadd' in i.mnemonic or 'fsub' in i.mnemonic or 'fdiv' in i.mnemonic or 'fcom' in i.mnemonic or 'ss' in i.mnemonic):
                note += '   ; %g' % f32(v)
    return note
def dis(a, n, stop_ret=False):
    out = []
    for i in md.disasm(rd(a, n), a):
        out.append('%08x  %-8s %s%s' % (i.address, i.mnemonic, i.op_str, note_for(i)))
        if stop_ret and i.mnemonic in ('ret', 'retn') : break
    return out
def fstart(a):
    o = a - base
    while True:
        if img[o - 1] in (0xcc, 0xc3, 0x90) or img[o - 3] == 0xc2:
            if img[o] in (0x55, 0x53, 0x56, 0x57, 0x83, 0x81, 0x8b, 0x6a, 0x51, 0x64, 0xa1, 0xd9, 0xf3, 0x0f, 0x8a, 0x80, 0x33, 0xb8, 0xe9, 0x68, 0x52, 0x50, 0xc7, 0xff): return o + base
        o -= 1
def fn(a, maxlen=0x600):
    s = fstart(a); out = []; end = s; far = s
    for i in md.disasm(rd(s, maxlen), s):
        out.append('%08x  %-8s %s%s' % (i.address, i.mnemonic, i.op_str, note_for(i)))
        if i.mnemonic.startswith('j') and i.op_str.startswith('0x'):
            t = int(i.op_str, 16)
            if s <= t < s + maxlen: far = max(far, t)
        if i.mnemonic in ('ret', 'retn') and i.address >= far: break
        if i.mnemonic == 'jmp' and i.address >= far and not i.op_str.startswith('0x'): break
    return out
def xref(target):
    """imm32/disp32 occurrences of target in .text, and rel32 call/jmp"""
    res = []
    k = struct.pack('<I', target); t0 = TEXT[0] - base; t1 = TEXT[1] - base
    for m in re.finditer(re.escape(k), img[t0:t1]): res.append(('abs', m.start() + t0 + base))
    if TEXT[0] <= target < TEXT[1]:
        for m in re.finditer(rb'[\xe8\xe9]', img[t0:t1]):
            o = m.start() + t0
            rel = struct.unpack_from('<i', img, o + 1)[0]
            if o + 5 + rel + base == target: res.append(('call' if img[o] == 0xe8 else 'jmp', o + base))
    # data refs
    for m in re.finditer(re.escape(k), img[t1:]): res.append(('data', m.start() + t1 + base))
    return res
def strings(rx):
    r = re.compile(rb'[\x20-\x7e]*' + rx.encode() + rb'[\x20-\x7e]*', re.I)
    for m in r.finditer(img):
        a = m.start() + base
        yield a, m.group().decode()
if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dis': print('\n'.join(dis(int(sys.argv[2], 16), int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x100)))
    elif cmd == 'fn': print('\n'.join(fn(int(sys.argv[2], 16), int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x600)))
    elif cmd == 'str':
        for a, s in strings(sys.argv[2]):
            xs = [x for x in xref(a)] if len(sys.argv) > 3 else []
            print('%08x "%s" %s' % (a, s, ' '.join('%s:%08x' % x for x in xs)))
    elif cmd == 'xref':
        for k, a in xref(int(sys.argv[2], 16)): print(k, '%08x' % a, 'in fn %08x' % fstart(a) if TEXT[0] <= a < TEXT[1] else '')
    elif cmd == 'find':
        k = bytes.fromhex(sys.argv[2])
        for m in re.finditer(re.escape(k), img): print('%08x' % (m.start() + base))
