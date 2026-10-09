import sys, os, struct, pefile, capstone
from sbf3 import ARC
pe = pefile.PE(os.path.join(ARC,'Rally.exe'), fast_load=True); base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
def cstr(a):
    o = a - base
    if 0 < o < len(img):
        s = img[o:o+48].split(b'\0')[0]
        if len(s) >= 4 and all(32 <= c < 127 for c in s): return s.decode()
def dis(a, n):
    for i in md.disasm(img[a-base:a-base+n], a):
        note = ''
        for tok in i.op_str.replace('[',' ').replace(']',' ').split():
            if tok.startswith('0x'):
                try:
                    s = cstr(int(tok.rstrip(','),16))
                    if s: note = '   ; "%s"' % s
                except ValueError: pass
        print('%08x  %-8s %s%s' % (i.address, i.mnemonic, i.op_str, note))
def fstart(a):
    o = a - base
    while not (img[o-1] in (0xcc, 0xc3, 0x90) or img[o-3] == 0xc2) or img[o] not in (0x55, 0x53, 0x56, 0x57, 0x83, 0x81, 0x8b, 0x6a, 0x51, 0x64, 0xa1): o -= 1
    return o + base
if __name__ == '__main__':
    a = int(sys.argv[1], 16); n = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x100
    if len(sys.argv) > 3: a = fstart(a)
    dis(a, n)
