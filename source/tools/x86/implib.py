"""Import libraries for 32-bit code built with gcc -m32 -nostdlib: made from what the objects actually call.

    python tools\\x86\\implib.py --out DIR [--dll NAME ...] [--system DIR] [--dlltool PATH] [--ignore SYMBOL ...] INPUT...

INPUT: the 32-bit COFF objects (.o / .obj) and static libraries (.a) of one link. Every external symbol they use but
none of them defines is an import. Its name gives the function and, for stdcall, its argument bytes (_Name@N): the
compiler wrote those, so nothing has to be guessed. Each is looked up, by name only, in the export tables of Windows'
own 32-bit DLLs (--system, default %SystemRoot%\\SysWOW64; nothing is copied from them), in the --dll order given
(default below); the first DLL that exports it gets it. Ordinals and addresses are never used.
Out: DIR\\<dll>.def (sorted), DIR\\lib<dll>.a (binutils dlltool: -m i386 --as-flags=--32 -k, deterministic),
DIR\\imports.json (each DLL's symbols, the .def's and library's SHA-256, the order and the inputs). A symbol no DLL
exports stops the run (exit 2) with the list. The same inputs give the same files in any folder.
Link with: gcc -m32 -nostdlib -nostartfiles ... -LDIR -lkernel32 -l... (and tools\\x86\\builtins.o for gcc's helpers)."""
import argparse, hashlib, json, os, shutil, struct, subprocess, sys, tempfile

DEFAULT_DLLS = ['kernel32', 'user32', 'gdi32', 'winmm', 'ole32', 'oleaut32', 'setupapi', 'shell32', 'advapi32', 'imm32',
                'version', 'cfgmgr32', 'hid', 'ucrtbase']
LINKER_SYMBOLS = {'___ImageBase', '__image_base__', '___RUNTIME_PSEUDO_RELOC_LIST__', '___RUNTIME_PSEUDO_RELOC_LIST_END__',
                  '__data_start__', '__data_end__', '__bss_start__', '__bss_end__', '__end__', '__tls_used', '___tls_start__',
                  '___tls_end__', '___CTOR_LIST__', '___DTOR_LIST__'}       # ld defines these itself

def coff_symbols(b, where):
    """(defined, undefined) external symbol names of one i386 COFF object"""
    if len(b) < 20: return set(), set()
    machine, nsec, _, symptr, nsym, optsz, _ = struct.unpack_from('<HHIIIHH', b, 0)
    if machine == 0 and nsec == 0xffff: return short_import(b, where)
    if machine != 0x14c: raise SystemExit('%s: not a 32-bit x86 COFF object (machine %#x)' % (where, machine))
    strtab = symptr + nsym * 18; defined, undefined = set(), set(); i = 0
    while i < nsym:
        o = symptr + i * 18; raw = b[o:o + 8]
        name = (b[strtab + struct.unpack_from('<I', raw, 4)[0]:].split(b'\0', 1)[0] if raw[:4] == b'\0\0\0\0'
                else raw.rstrip(b'\0')).decode('latin-1')
        value, sec, _, cls, aux = struct.unpack_from('<IhHBB', b, o + 8)
        if cls == 2:                                                       # IMAGE_SYM_CLASS_EXTERNAL
            (undefined if sec == 0 and value == 0 else defined).add(name)
        elif cls == 105: defined.add(name)                                 # a weak external carries its own default
        i += 1 + aux
    return defined, undefined

def short_import(b, where):
    """an import library's short import member (Microsoft format) defines __imp_Name and Name"""
    size = struct.unpack_from('<I', b, 12)[0]; name = b[20:20 + size].split(b'\0', 1)[0].decode('latin-1')
    return {name, '__imp_' + name}, set()

def inputs(path):
    """yield (where, object bytes) for an object or every member of an ar archive"""
    b = open(path, 'rb').read()
    if not b.startswith(b'!<arch>\n'): yield path, b; return
    o = 8; longnames = b''
    while o + 60 <= len(b):
        h = b[o:o + 60]; name = h[:16].decode('latin-1').rstrip(); size = int(h[48:58].decode('latin-1').strip()); data = b[o + 60:o + 60 + size]
        if name == '//': longnames = data
        elif name not in ('/', '/SYM64/', '__.SYMDEF'):
            if name.startswith('/') and name[1:].isdigit(): name = longnames[int(name[1:]):].split(b'/\n', 1)[0].split(b'\n', 1)[0].decode('latin-1')
            yield '%s(%s)' % (path, name.rstrip('/')), data
        o += 60 + size + (size & 1)

def pe_exports(path):
    """the export names of a PE file (32- or 64-bit), forwarded ones included"""
    b = open(path, 'rb').read(); pe = struct.unpack_from('<I', b, 0x3c)[0]
    if b[pe:pe + 4] != b'PE\0\0': raise SystemExit('%s: not a PE file' % path)
    nsec, optsz = struct.unpack_from('<H', b, pe + 6)[0], struct.unpack_from('<H', b, pe + 20)[0]; opt = pe + 24
    magic = struct.unpack_from('<H', b, opt)[0]; dd = opt + (96 if magic == 0x10b else 112)
    rva, size = struct.unpack_from('<II', b, dd)
    if not rva: return set()
    secs = [struct.unpack_from('<IIII', b, opt + optsz + k * 40 + 8) for k in range(nsec)]   # vsize, va, rawsize, rawptr
    def off(r):
        for vs, va, rs, rp in secs:
            if va <= r < va + max(vs, rs): return r - va + rp
        raise SystemExit('%s: export table outside every section' % path)
    e = off(rva); nnames, names = struct.unpack_from('<I', b, e + 24)[0], off(struct.unpack_from('<I', b, e + 32)[0])
    return {b[off(struct.unpack_from('<I', b, names + 4 * k)[0]):].split(b'\0', 1)[0].decode('latin-1') for k in range(nnames)}

def def_entry(sym):
    """the C symbol of an import -> (its .def line, the name the DLL exports); None when it isn't a C symbol"""
    if sym.startswith('__imp_'): sym = sym[6:]
    if sym.startswith('@'): return None                                    # fastcall: no Windows API uses it
    if not sym.startswith('_'): return None
    body = sym[1:]; at = body.rfind('@')
    if at > 0 and body[at + 1:].isdigit(): return body, body[:at]          # stdcall: Name@N; -k imports "Name"
    return body, body                                                      # cdecl

def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True); ap.add_argument('--dll', action='append')
    ap.add_argument('--system', default=os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'SysWOW64'))
    ap.add_argument('--dlltool'); ap.add_argument('--ignore', action='append', default=[]); ap.add_argument('inputs', nargs='+')
    a = ap.parse_args(argv)
    dlls = [d.lower().removesuffix('.dll') for d in (a.dll or DEFAULT_DLLS)]
    gcc = find_gcc(); dlltool = a.dlltool or os.environ.get('SR3_DLLTOOL') or os.path.join(os.path.dirname(gcc), 'dlltool.exe')
    # dlltool starts the assembler by the name "as" (PATH); the toolchain zip has it only where gcc keeps its programs
    asm = subprocess.run([gcc, '-print-prog-name=as'], capture_output=True, text=True).stdout.strip() or 'as'
    defined, undefined = set(), set()
    for p in a.inputs:
        for where, b in inputs(p):
            d, u = coff_symbols(b, where); defined |= d; undefined |= u
    need = sorted(undefined - defined - LINKER_SYMBOLS - set(a.ignore))
    exports = {d: pe_exports(os.path.join(a.system, d + '.dll')) for d in dlls}
    per, unresolved, seen = {d: set() for d in dlls}, [], set()
    for s in need:
        e = def_entry(s)
        if not e: unresolved.append(s); continue
        line, name = e
        for d in dlls:
            if name in exports[d]: per[d].add(line); seen.add(s); break
        else: unresolved.append(s)
    if unresolved: print('not exported by any of %s:\n  %s' % (', '.join(dlls), '\n  '.join(unresolved))); return 2
    os.makedirs(a.out, exist_ok=True); manifest = {'system': a.system, 'order': dlls, 'inputs': sorted(os.path.basename(p) for p in a.inputs), 'dlls': []}
    for d in dlls:
        if not per[d]: continue
        dp, lp = os.path.join(a.out, d + '.def'), os.path.join(a.out, 'lib%s.a' % d)
        open(dp, 'w', newline='\n').write('LIBRARY %s.dll\nEXPORTS\n%s\n' % (d, '\n'.join(sorted(per[d]))))
        # dlltool names the library's own symbols after the paths it is given, so it gets bare file names in a scratch
        # folder (its temporary files go there too) and the library is moved out afterwards: the same bytes in any folder
        with tempfile.TemporaryDirectory() as td:
            shutil.copyfile(dp, os.path.join(td, d + '.def'))
            r = subprocess.run([dlltool, '-m', 'i386', '--as', asm, '--as-flags=--32', '-k', '--deterministic-libraries', '-t', d,
                                '-d', d + '.def', '-l', 'lib%s.a' % d], cwd=td, capture_output=True, text=True)
            if r.returncode: raise SystemExit('dlltool failed for %s:\n%s' % (d, r.stdout + r.stderr))
            shutil.move(os.path.join(td, 'lib%s.a' % d), lp)
        manifest['dlls'].append({'dll': d + '.dll', 'symbols': sorted(per[d]), 'def': os.path.basename(dp), 'lib': os.path.basename(lp),
                                 'def_sha256': sha(dp), 'lib_sha256': sha(lp)})
    open(os.path.join(a.out, 'imports.json'), 'w', newline='\n').write(json.dumps(manifest, indent=1, sort_keys=True) + '\n')
    print('implib: %d imports from %s -> %s' % (len(seen), ', '.join('%s %d' % (x['dll'], len(x['symbols'])) for x in manifest['dlls']), a.out))
    return 0

def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def find_gcc():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'import', 'core'))
    import cbuild
    return cbuild.GCC

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
