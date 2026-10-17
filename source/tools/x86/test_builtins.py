"""Tests tools/x86/builtins.c and implib.py the way they are used: a 32-bit program built with our 64-bit gcc
(-m32 -nostdlib), builtins.o and an import library implib.py made from the program's own references.

    python tools\\x86\\test_builtins.py [--keep DIR]

- Arithmetic: exact answers from Python's integers for every boundary pair (0, 1, 2^31, 2^32, 2^63, 2^64-1, the powers
  of two and their neighbours, against each other), random pairs of every bit length, high-bit divisors (>= 2^63) and
  33-bit divisors; signed ones with INT64_MIN, -1 and both signs. Through the C operators (gcc's own calls) and the
  helpers called directly. Bit counts on the same values.
- Stack probe: frames of 4095 B to 3 MB and a 4 MB nest, touched at their lowest byte first, in a thread whose 8 MB stack
  is only reserved; and every register (EAX included) and the stack pointer unchanged across ___chkstk_ms.
- Negative control: the same stack test built with probes switched off must crash; it shows the test can see a probe
  that is missing or wrong.
- implib.py run twice into different folders gives the same files."""
import os, random, shutil, subprocess, sys, tempfile, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'import', 'core')); sys.path.insert(0, HERE)
import cbuild, implib
GCC = cbuild.GCC; M = 1 << 64

def s64(v): v &= M - 1; return v - M if v >> 63 else v
def cdiv(a, b):                                  # C: truncate toward zero, remainder has the dividend's sign, wraps
    q = abs(a) // abs(b); q = -q if (a < 0) != (b < 0) else q
    return s64(q), s64(a - q * b)
def char(v): v &= 255; return v - 256 if v > 127 else v
def frame(n, k):                                 # what test_builtins32.c's FRAME(n)(k) returns
    a = {0: char(k)}
    for j in range(0, n, 4096): a[j] = char(j + k)
    a[n - 1] = 1
    return sum(a[j] for j in range(0, n, 4096)) + a[n - 1]
def nest(d): return nest(d - 1) + d + 2 if d else d

def vectors(path):
    rnd = random.Random(1995)
    edge = sorted({0, 1, 2, 3, 5, 7, 10, 255, 256, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe, 0xffffffff, 0x100000000,
                   0x100000001, 0x1ffffffff, 0xffffffff00000000, 0xffffffff00000001, (1 << 63) - 1, 1 << 63, (1 << 63) + 1, M - 2, M - 1}
                  | {1 << k for k in range(0, 64, 3)} | {(1 << k) - 1 for k in range(2, 65, 5)} | {(1 << k) + 1 for k in range(1, 64, 7)})
    def rbits(): n = rnd.randint(1, 64); return rnd.getrandbits(n) | (1 << (n - 1))
    up = [(a, b) for a in edge for b in edge if b]
    up += [(rbits(), rbits()) for _ in range(20000)]
    up += [(rnd.getrandbits(64), (1 << 63) | rnd.getrandbits(63)) for _ in range(4000)]      # high-bit divisors
    up += [(rnd.getrandbits(64), (1 << 32) | rnd.getrandbits(32)) for _ in range(4000)]      # just over 32 bits
    up += [(rnd.getrandbits(64), rnd.getrandbits(32) | 1) for _ in range(4000)]              # 32-bit divisors
    sedge = sorted({s64(v) for v in edge} | {-v for v in (1, 2, 3, 7, 0x7fffffff, 0x80000000, 0xffffffff, 1 << 32, (1 << 63) - 1)} | {-(1 << 63)})
    sp = [(a, b) for a in sedge for b in sedge if b]
    sp += [(s64(rbits()) * rnd.choice((1, -1)), s64(rbits()) * rnd.choice((1, -1)) or 1) for _ in range(20000)]
    sp = [(s64(a), s64(b)) for a, b in sp if s64(b)]
    bits = sorted(set(edge) | {rnd.getrandbits(64) for _ in range(3000)})
    L = ['/* written by test_builtins.py */', 'struct UV { unsigned long long a, b, q, r; };', 'static const struct UV UVEC[] = {']
    L += ['{%#xULL,%#xULL,%#xULL,%#xULL},' % (a, b, a // b, a % b) for a, b in up]
    L += ['};', '#define NU %d' % len(up), 'struct SV { long long a, b, q, r; };', 'static const struct SV SVEC[] = {']
    L += ['{(long long)%#xULL,(long long)%#xULL,(long long)%#xULL,(long long)%#xULL},' % tuple(v % M for v in (a, b) + cdiv(a, b)) for a, b in sp]
    L += ['};', '#define NS %d' % len(sp), 'struct BV { unsigned long long x; int ctz, clz, pop, ffs, par; };', 'static const struct BV BVEC[] = {']
    for x in bits:
        ctz = (x & -x).bit_length() - 1 if x else 64; pop = bin(x).count('1')
        L.append('{%#xULL,%d,%d,%d,%d,%d},' % (x, ctz, 64 - x.bit_length(), pop, ctz + 1 if x else 0, pop & 1))
    stack = frame(4095, 1) + frame(4096, 2) + frame(4097, 3) + frame(8191, 4) + frame(8192, 5) + frame(8193, 6) + frame(65553, 7) \
        + frame(1048576, 8) + frame(3145728, 9) + nest(5)
    L += ['};', '#define NB %d' % len(bits), '#define EXPECT_STACK %du' % (stack & 0xffffffff)]
    open(path, 'w', newline='\n').write('\n'.join(L) + '\n')
    return len(up), len(sp), len(bits)

def run(cmd, **k):
    r = subprocess.run(cmd, capture_output=True, text=True, **k)
    if r.returncode: raise SystemExit('failed: %s\n%s' % (' '.join(cmd), r.stdout + r.stderr))
    return r

def build(b, name, defines=()):
    o = os.path.join(b, name + '.o'); imp = os.path.join(b, name + '_imp'); exe = os.path.join(b, name + '.exe')
    run([GCC, '-m32', '-O2', '-Wall', '-I', b] + list(defines) + ['-c', 'test_builtins32.c', '-o', o], cwd=HERE)
    if implib.main(['--out', imp, '--dll', 'kernel32', o, os.path.join(b, 'builtins.o')]): raise SystemExit('implib failed')
    run([GCC, '-m32', '-nostdlib', '-nostartfiles', '-Wl,-e,_start@0', o, os.path.join(b, 'builtins.o'), '-L', imp, '-lkernel32', '-o', exe])
    return exe, imp

def tree_hashes(d): return {f: hashlib.sha256(open(os.path.join(d, f), 'rb').read()).hexdigest() for f in sorted(os.listdir(d))}

def main(argv):
    keep = argv[argv.index('--keep') + 1] if '--keep' in argv else None
    b = keep or tempfile.mkdtemp(prefix='x86test_'); os.makedirs(b, exist_ok=True)
    nu, ns, nb = vectors(os.path.join(b, 'vectors.h'))
    run([GCC, '-m32', '-O2', '-Wall', '-Wextra', '-c', 'builtins.c', '-o', os.path.join(b, 'builtins.o')], cwd=HERE)
    exe, imp = build(b, 'test')
    r = subprocess.run([exe], capture_output=True, text=True)
    print(r.stdout.strip()[-2000:])
    print('arithmetic: %d unsigned pairs, %d signed pairs, %d bit-count values; stack frames and registers: exit code %d'
          % (nu, ns, nb, r.returncode))
    ok = r.returncode == 0 and r.stdout.strip().endswith('PASS')
    neg, _ = build(b, 'noprobe', ['-DSTACK_ONLY', '-mno-stack-arg-probe'])
    n = subprocess.run([neg], capture_output=True, text=True)
    crashed = (n.returncode & 0xffffffff) >= 0xc0000000
    print('negative control (no probes): exit code %#x, %s' % (n.returncode & 0xffffffff, 'crashed as it must' if crashed else 'DID NOT CRASH: the stack test proves nothing'))
    other = os.path.join(b, 'again', 'elsewhere'); os.makedirs(other, exist_ok=True)
    implib.main(['--out', other, '--dll', 'kernel32', os.path.join(b, 'test.o'), os.path.join(b, 'builtins.o')])
    same = tree_hashes(imp) == tree_hashes(other)
    print('implib.py in another folder: %s' % ('the same files' if same else 'DIFFERENT FILES'))
    if not keep: shutil.rmtree(b, ignore_errors=True)
    print('RESULT: %s' % ('PASS' if ok and crashed and same else 'FAIL'))
    return 0 if ok and crashed and same else 1

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
