"""Builds the SRC turning port (srcport.c) into a blob for sr3mods.ps1, and its surface table.

    python build_srcport.py [--game <Rally folder>] [--embed]   writes srcport.json next to this file; --embed also
                                                                 writes the blob into ..\sr3mods.ps1 ($SrcPortCode ...)

1. clang (i686, freestanding, SSE2 + x87 for sin / cos / atan / pow) compiles srcport.c to a COFF object.
2. The object's .text, .rdata, .data and .bss are laid out one after the other (16-byte aligned) from offset 0; every
   IMAGE_REL_I386_DIR32 site gets its target's offset, and its place is listed in "relocs": the launcher writes the
   blob at the address it allocated, then adds that address to the dword at each listed offset. No other relocation
   type is accepted (calls into Rally.exe are absolute addresses in registers, not relocations). The blob ends where
   .bss starts (the log); the launcher allocates ALLOC bytes, zero-filled, so .bss needs no bytes in sr3mods.ps1.
3. The surface table: the grip file's surface-pair records in file order (the index a tyre keeps at + 0x1C, the same
   order in every grip file the flavor builder writes), each classed for SRC's four records by its name and, for the
   rest, by its Tyre_Rally grip against Tyre_Rally_Tarmac's. Bit 7 marks the Tyre_Road records (the SRC files' tyres),
   which is how the port knows a car is on the SRC handling.
Needs clang on the PATH (C:\\mingw64\\bin) and the game's SurfacePairEffects\\surfacepairdata_xdata.sbf (SEGA's own)."""
import os, sys, re, json, struct, subprocess, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts', 'importer'))
SRC = os.path.join(HERE, 'srcport.c')
FLAGS = ['-target', 'i686-pc-windows-gnu', '-O2', '-c', '-ffreestanding', '-fno-math-errno', '-msse2', '-mfpmath=sse',
         '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-Wall', '-Wno-unused-function']
OFF_COUNT, OFF_CLS, NCLS, OFF_LOG, ALLOC = 0x48, 0x50, 128, 0x1E0, 0x10000

def compile_obj(out):
    subprocess.run(['clang'] + FLAGS + [SRC, '-o', out], check=True)
    return open(out, 'rb').read()

def link(obj):
    """COFF i386 object -> (blob, symbols {name: offset}, relocs [offsets])"""
    mach, nsec, _, psym, nsym, optsz, _ = struct.unpack_from('<HHIIIHH', obj, 0)
    if mach != 0x14C: raise SystemExit('not an i386 object')
    secs = []
    for i in range(nsec):
        o = 20 + optsz + 40 * i
        name = obj[o:o + 8].rstrip(b'\0').decode()
        vsz, va, rsz, praw, prel, pln, nrel, nln, ch = struct.unpack_from('<IIIIIIHHI', obj, o + 8)
        secs.append(dict(name=name, size=rsz, raw=praw, prel=prel, nrel=nrel, bss=bool(ch & 0x80)))
    blob = bytearray(); base = {}; bss_at = None
    for want in ('.text', '.rdata', '.data', '.bss'):
        for i, s in enumerate(secs):
            if s['name'] != want: continue
            blob += b'\0' * (-len(blob) % 16); base[i] = len(blob)
            if want == '.bss' and bss_at is None: bss_at = len(blob)
            blob += b'\0' * s['size'] if s['bss'] or not s['raw'] else obj[s['raw']:s['raw'] + s['size']]
    strtab = psym + 18 * nsym
    syms = []; names = {}
    i = 0
    while i < nsym:
        o = psym + 18 * i
        if obj[o:o + 4] == b'\0\0\0\0': nm = obj[strtab + struct.unpack_from('<I', obj, o + 4)[0]:].split(b'\0')[0].decode()
        else: nm = obj[o:o + 8].rstrip(b'\0').decode()
        val, sec, typ, scl, naux = struct.unpack_from('<IhHBB', obj, o + 8)
        syms.append((nm, val, sec)); syms += [None] * naux
        if sec > 0 and (sec - 1) in base: names[nm] = base[sec - 1] + val
        i += 1 + naux
    relocs = []
    for i, s in enumerate(secs):
        if i not in base: continue
        for r in range(s['nrel']):
            va, si, typ = struct.unpack_from('<IIH', obj, s['prel'] + 10 * r)
            if typ != 6: raise SystemExit('relocation type %d in %s: only DIR32 is handled' % (typ, s['name']))
            nm, val, sec = syms[si]
            if sec <= 0 or (sec - 1) not in base: raise SystemExit('relocation to an outside symbol %s' % nm)
            site = base[i] + va
            struct.pack_into('<I', blob, site, struct.unpack_from('<I', blob, site)[0] + base[sec - 1] + val)
            relocs.append(site)
    if any(r >= (bss_at or len(blob)) for r in relocs): raise SystemExit('a relocation inside .bss')
    return bytes(blob), names, sorted(relocs), bss_at or len(blob)

def surface_classes(game):
    from sbfw import read_sbf
    f = read_sbf(os.path.join(game, 'SurfacePairEffects', 'surfacepairdata_xdata.sbf'))
    c = [x for x in f.chunks if x.id == 0x6172a752][0]; d = bytes(c.data)
    recs = []; o = 8
    while True:
        nxt = struct.unpack_from('<I', d, o)[0]; end = nxt if o in c.fix else len(d)
        runs = list(re.finditer(rb'[A-Za-z_][ -~]{3,}', d[o + 4:end]))
        recs.append((runs[-1].group().decode() if runs else '?', struct.unpack_from('<f', d, o + 4)[0]))
        if o not in c.fix: break
        o = nxt
    mu = {n: m for n, m in recs}
    tarmac = mu.get('Tyre_Rally_Tarmac_Top', 2.25)
    out = []
    for n, m in recs:
        mt = re.match(r'(Tyre_Rally|Tyre_Road|Tyre_AllTerrain)_(.+?)(_Top|_Base)?$', n)
        if not mt: out.append((n, 0xFF, '')); continue
        surf = mt.group(2); layer = mt.group(3) or ''
        ref = mu.get('Tyre_Rally_%s%s' % (surf, layer), mu.get('Tyre_Rally_' + surf, m))
        r = ref / tarmac
        if re.search('Grass|Swamp|Verge', surf): k, why = 3, 'name'
        elif re.search('Water|River|Puddle', surf): k, why = 2, 'name'
        elif re.search('Tarmac|Cobbles|Bridge|Concrete', surf) and not re.search('Snow|Ice', surf): k, why = 0, 'name'
        elif r >= 0.92: k, why = 0, 'grip %.2f' % r
        elif r >= 0.5: k, why = 1, 'grip %.2f' % r
        else: k, why = 2, 'grip %.2f' % r
        out.append((n, k | (0x80 if mt.group(1) == 'Tyre_Road' else 0), why))
    return out

def build(game):
    obj = compile_obj(os.path.join(HERE, 'srcport.o'))
    blob, names, relocs, image = link(obj)
    if len(blob) > ALLOC: raise SystemExit('%d bytes: more than the %d the launcher allocates' % (len(blob), ALLOC))
    os.remove(os.path.join(HERE, 'srcport.o'))
    entry, data = names['_srcport_step'], names['_g']
    blob = bytearray(blob)
    if struct.unpack_from('<I', blob, data)[0] != 0x50435253: raise SystemExit('data block not found')
    cls = surface_classes(game)
    if len(cls) > NCLS: raise SystemExit('%d surface records, the table holds %d' % (len(cls), NCLS))
    struct.pack_into('<I', blob, data + OFF_COUNT, len(cls))
    for i, (n, k, why) in enumerate(cls): blob[data + OFF_CLS + i] = k
    return bytes(blob[:image]), entry, data, relocs, cls

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=r'F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally')
    ap.add_argument('--embed', action='store_true')
    a = ap.parse_args()
    blob, entry, data, relocs, cls = build(a.game)
    names = 'ABCD'
    json.dump(dict(code=blob.hex(), entry=entry, data=data, relocs=relocs, size=len(blob), alloc=ALLOC,
                   surfaces=['%d %s %s%s (%s)' % (i, n, names[k & 3] if k != 0xFF else '-', ' road' if k != 0xFF and k & 0x80 else '', why) for i, (n, k, why) in enumerate(cls)]),
              open(os.path.join(HERE, 'srcport.json'), 'w', newline='\n'), indent=0)
    print('SRCPORT %d bytes, entry +0x%X, data +0x%X, %d relocations, %d surface records (%d Tyre_Road)' % (
        len(blob), entry, data, len(relocs), len(cls), sum(1 for _, k, _ in cls if k != 0xFF and k & 0x80)))
    for i, (n, k, why) in enumerate(cls):
        if k != 0xFF and k & 0x80: print('  %3d %-34s %s  (%s)' % (i, n, names[k & 3], why))
    if a.embed:
        ps = os.path.join(HERE, '..', 'sr3mods.ps1'); t = open(ps, encoding='utf-8-sig').read()
        if any(r > 0xFFFF for r in relocs): raise SystemExit('a relocation beyond 0xFFFF')
        lines = {'$SrcPortCode = ': "$SrcPortCode = '%s'" % blob.hex(),
                 '$SrcPortEntry = ': '$SrcPortEntry = 0x%X; $SrcPortData = 0x%X; $SrcPortAlloc = 0x%X; $SrcPortVersion = %d' % (entry, data, ALLOC, struct.unpack_from('<I', blob, data + 4)[0]),
                 '$SrcPortRelocs = ': "$SrcPortRelocs = '%s'" % ''.join('%04x' % r for r in relocs)}
        out = []
        for ln in t.split('\n'):
            for k, v in lines.items():
                if ln.startswith(k): ln = v + ('\r' if ln.endswith('\r') else ''); break
            out.append(ln)
        n = sum(1 for ln in out for k in lines if ln.startswith(k))
        if n != 3: raise SystemExit('sr3mods.ps1: %d of the 3 lines found; nothing written' % n)
        bom = open(ps, 'rb').read(3) == b'\xef\xbb\xbf'
        open(ps, 'w', encoding='utf-8-sig' if bom else 'utf-8', newline='').write('\n'.join(out))
        print('sr3mods.ps1: $SrcPortCode (%d bytes), entry, data, %d relocations written' % (len(blob), len(relocs)))
