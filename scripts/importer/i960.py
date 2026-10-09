"""Minimal Intel i960 (KB core subset) disassembler + interpreter, enough to run table-fill routines of srallyc.
Decoding follows the i960 instruction formats (REG / COBR / CTRL / MEMA / MEMB), cross-checked against MAME's i960 core.
    python i960.py dis <addr hex> [count]"""
import os, sys, struct
M2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tmp', 'm2')
RN = ['pfp', 'sp', 'rip'] + ['r%d' % i for i in range(3, 16)] + ['g%d' % i for i in range(15)] + ['fp']
CTRL = {0x08: 'b', 0x09: 'call', 0x0a: 'ret', 0x0b: 'bal', 0x10: 'bno', 0x11: 'bg', 0x12: 'be', 0x13: 'bge', 0x14: 'bl', 0x15: 'bne', 0x16: 'ble', 0x17: 'bo'}
COBR = {0x30: 'bbc', 0x31: 'cmpobg', 0x32: 'cmpobe', 0x33: 'cmpobge', 0x34: 'cmpobl', 0x35: 'cmpobne', 0x36: 'cmpoble', 0x37: 'bbs',
        0x39: 'cmpibg', 0x3a: 'cmpibe', 0x3b: 'cmpibge', 0x3c: 'cmpibl', 0x3d: 'cmpibne', 0x3e: 'cmpible', 0x38: 'cmpibno', 0x3f: 'cmpibo'}
REG = {(0x58, 0): 'notbit', (0x58, 1): 'and', (0x58, 2): 'andnot', (0x58, 3): 'setbit', (0x58, 4): 'notand', (0x58, 6): 'xor', (0x58, 7): 'or', (0x58, 8): 'nor',
       (0x58, 9): 'xnor', (0x58, 10): 'not', (0x58, 11): 'ornot', (0x58, 12): 'clrbit', (0x58, 13): 'notor', (0x58, 14): 'nand',
       (0x59, 0): 'addo', (0x59, 1): 'addi', (0x59, 2): 'subo', (0x59, 3): 'subi', (0x59, 8): 'shro', (0x59, 10): 'shrdi', (0x59, 11): 'shri', (0x59, 12): 'shlo', (0x59, 13): 'rotate', (0x59, 14): 'shli',
       (0x5a, 0): 'cmpo', (0x5a, 1): 'cmpi', (0x5a, 2): 'concmpo', (0x5a, 3): 'concmpi', (0x5a, 4): 'cmpinco', (0x5a, 5): 'cmpinci', (0x5a, 6): 'cmpdeco', (0x5a, 7): 'cmpdeci', (0x5a, 14): 'chkbit',
       (0x5b, 0): 'addc', (0x5b, 2): 'subc', (0x5c, 12): 'mov', (0x5d, 12): 'movl', (0x5e, 12): 'movt', (0x5f, 12): 'movq',
       (0x64, 0): 'spanbit', (0x64, 1): 'scanbit', (0x65, 0): 'modify', (0x65, 1): 'extract', (0x66, 0): 'calls', (0x66, 13): 'flushreg',
       (0x67, 0): 'emul', (0x67, 1): 'ediv', (0x70, 1): 'mulo', (0x70, 8): 'remo', (0x70, 11): 'divo', (0x74, 1): 'muli', (0x74, 8): 'remi', (0x74, 9): 'modi', (0x74, 11): 'divi'}
FPN = {(0x67, 4): 'cvtir', (0x67, 5): 'cvtilr', (0x67, 6): 'scalerl', (0x67, 7): 'scaler', (0x6c, 0): 'cvtri', (0x6c, 1): 'cvtril', (0x6c, 2): 'cvtzri', (0x6c, 3): 'cvtzril',
       (0x6c, 9): 'movr', (0x6d, 9): 'movrl', (0x6e, 1): 'movre', (0x78, 11): 'divr', (0x78, 12): 'mulr', (0x78, 13): 'subr', (0x78, 15): 'addr',
       (0x79, 11): 'divrl', (0x79, 12): 'mulrl', (0x79, 13): 'subrl', (0x79, 15): 'addrl'}
for _i, _n in enumerate(['atan', 'logep', 'log', 'rem', 'cmpo', 'cmp', None, None, 'sqrt', 'exp', 'logbn', 'round', 'sin', 'cos', 'tan', 'class']):
    if _n: FPN[(0x68, _i)] = _n + 'r'; FPN[(0x69, _i)] = _n + 'rl'
REG.update(FPN); FPNAMES = set(FPN.values())
MEM = {0x80: 'ldob', 0x82: 'stob', 0x84: 'bx', 0x85: 'balx', 0x86: 'callx', 0x88: 'ldos', 0x8a: 'stos', 0x8c: 'lda', 0x90: 'ld', 0x92: 'st', 0x98: 'ldl', 0x9a: 'stl',
       0xa0: 'ldt', 0xa2: 'stt', 0xb0: 'ldq', 0xb2: 'stq', 0xc0: 'ldib', 0xc2: 'stib', 0xc8: 'ldis', 0xca: 'stis'}

def sx(v, bits): return v - (1 << bits) if v & (1 << (bits - 1)) else v

def decode(w, w2, ip):
    """-> dict(kind, name, size, fields...)"""
    op = w >> 24
    if op in CTRL: return dict(kind='ctrl', name=CTRL[op], op=op, size=4, target=(ip + sx(w & 0xfffffc, 24)) & 0xffffffff)
    if 0x20 <= op <= 0x27: return dict(kind='test', name='test', op=op, size=4, dst=(w >> 19) & 31)
    if op in COBR:
        return dict(kind='cobr', name=COBR[op], op=op, size=4, s1=(w >> 19) & 31, lit1=(w >> 13) & 1, s2=(w >> 14) & 31, target=(ip + sx(w & 0x1ffc, 13)) & 0xffffffff)
    if 0x58 <= op <= 0x7f:
        k = (op, (w >> 7) & 15)
        return dict(kind='reg', name=REG.get(k, '?reg_%02x_%x' % k), op=op, f=k[1], size=4, s1=w & 31, m1=(w >> 11) & 1, s2=(w >> 14) & 31, m2=(w >> 12) & 1, dst=(w >> 19) & 31, m3=(w >> 13) & 1)
    if op in MEM:
        d = dict(kind='mem', name=MEM[op], op=op, reg=(w >> 19) & 31, abase=(w >> 14) & 31, size=4)
        if not (w >> 12) & 1: d.update(mode='A', off=w & 0xfff, useb=(w >> 13) & 1)
        else:
            mode = (w >> 10) & 15; d.update(mode=mode, scale=(w >> 7) & 7, index=w & 31)
            if mode in (5, 12, 13, 14, 15): d['disp'] = w2; d['size'] = 8
        return d
    return dict(kind='?', name='?%08x' % w, op=op, size=4)

def fmt(d):
    k = d['kind']
    if k == 'ctrl': return '%s %x' % (d['name'], d['target']) if d['name'] != 'ret' else 'ret'
    if k == 'cobr': return '%s %s, %s, %x' % (d['name'], ('#%d' % d['s1']) if d['lit1'] else RN[d['s1']], RN[d['s2']], d['target'])
    if k == 'reg':
        if d['name'] in FPNAMES:
            def fo(v, m): return ({0: 'fp0', 1: 'fp1', 2: 'fp2', 3: 'fp3', 16: '0.0', 22: '1.0'}.get(v, '?f%d' % v)) if m else RN[v]
            s1 = fo(d['s1'], d['m1']) if d['name'] not in ('cvtir', 'cvtilr') else (('#%d' % d['s1']) if d['m1'] else RN[d['s1']])
            return '%s %s, %s, %s' % (d['name'], s1, fo(d['s2'], d['m2']), fo(d['dst'], d['m3']) if d['m3'] else RN[d['dst']])
        a = ('#%d' % d['s1']) if d['m1'] else RN[d['s1']]; b = ('#%d' % d['s2']) if d['m2'] else RN[d['s2']]
        return '%s %s, %s, %s' % (d['name'], a, b, RN[d['dst']])
    if k == 'mem':
        if d['mode'] == 'A': ea = ('%x(%s)' % (d['off'], RN[d['abase']])) if d['useb'] else '%x' % d['off']
        else:
            m = d['mode']; ea = {4: '(%s)' % RN[d['abase']], 5: 'ip+%x' % d.get('disp', 0), 7: '(%s)[%s*%d]' % (RN[d['abase']], RN[d['index']], 1 << d['scale']),
                                 12: '%x' % d.get('disp', 0), 13: '%x(%s)' % (d.get('disp', 0), RN[d['abase']]), 14: '%x[%s*%d]' % (d.get('disp', 0), RN[d['index']], 1 << d['scale']),
                                 15: '%x(%s)[%s*%d]' % (d.get('disp', 0), RN[d['abase']], RN[d['index']], 1 << d['scale'])}.get(m, '?mode%d' % m)
        return '%s %s, %s' % (d['name'], ea, RN[d['reg']])
    return d['name']

class Mem:
    """program ROM at 0, main data ROM at 0x02000000, sparse RAM elsewhere; write log for the three target areas"""
    def __init__(self):
        self.prog = open(os.path.join(M2, 'maincpu.bin'), 'rb').read(); self.data = open(os.path.join(M2, 'main_data.bin'), 'rb').read()
        self.ram = {}; self.log = {}; self.unk = {}
    def r8(self, a):
        a &= 0xffffffff
        if a in self.ram: return self.ram[a]
        if a < len(self.prog): return self.prog[a]
        if 0x02000000 <= a < 0x02000000 + len(self.data): return self.data[a - 0x02000000]
        self.unk[a & ~0xfff] = self.unk.get(a & ~0xfff, 0) + 1; return 0
    def w8(self, a, v):
        a &= 0xffffffff; self.ram[a] = v & 255
        if 0x01800000 <= a < 0x01820000 or 0x12800000 <= a < 0x12820000: self.log[a] = v & 255
    def r(self, a, n): return sum(self.r8(a + i) << (8 * i) for i in range(n))
    def w(self, a, v, n):
        for i in range(n): self.w8(a + i, v >> (8 * i))

class Cpu:
    def __init__(self, mem):
        self.m = mem; self.r = [0] * 32; self.cc = 0; self.ip = 0; self.frames = []; self.steps = 0; self.halt = None; self.fp = [0.0] * 4
    def ea(self, d, ip):
        R = self.r
        if d['mode'] == 'A': return (d['off'] + (R[d['abase']] if d['useb'] else 0)) & 0xffffffff
        m = d['mode']; x = (R[d['index']] << d['scale'])
        return {4: R[d['abase']], 5: ip + 8 + d.get('disp', 0), 7: R[d['abase']] + x, 12: d.get('disp', 0), 13: d.get('disp', 0) + R[d['abase']],
                14: d.get('disp', 0) + x, 15: d.get('disp', 0) + R[d['abase']] + x}[m] & 0xffffffff
    def cmp(self, a, b): self.cc = 4 if a < b else (2 if a == b else 1)
    def fget(self, v, m, dbl):
        if m:
            if v < 4: return self.fp[v]
            if v == 16: return 0.0
            if v == 22: return 1.0
            raise ValueError('float literal %d' % v)
        R = self.r
        if dbl: return struct.unpack('<d', struct.pack('<II', R[v] & 0xffffffff, R[(v + 1) & 31] & 0xffffffff))[0]
        return struct.unpack('<f', struct.pack('<I', R[v] & 0xffffffff))[0]
    def fput(self, d, v, dbl):
        if d['m3']: self.fp[d['dst'] & 3] = v; return
        R = self.r
        if dbl: R[d['dst']], R[(d['dst'] + 1) & 31] = struct.unpack('<II', struct.pack('<d', v))
        else:
            try: R[d['dst']] = struct.unpack('<I', struct.pack('<f', v))[0]
            except OverflowError: R[d['dst']] = 0x7f800000 if v > 0 else 0xff800000
    def fpu(self, d):
        """i960 KB floating point subset. Returns False if not implemented."""
        import math
        n = d['name']; dbl = n.endswith('rl') and n not in ('cvtril', 'cvtzril'); R = self.r
        if n in ('cvtir', 'cvtilr'):
            if n == 'cvtir': v = d['s1'] if d['m1'] else sx(R[d['s1']] & 0xffffffff, 32)
            else: v = sx((R[d['s1']] & 0xffffffff) | ((R[(d['s1'] + 1) & 31] & 0xffffffff) << 32), 64)
            self.fput(d, float(v), False); return True
        if n in ('cvtri', 'cvtzri', 'cvtril', 'cvtzril'):
            v = self.fget(d['s1'], d['m1'], False); i = int(v) if 'z' in n else int(round(v))
            R[d['dst']] = i & 0xffffffff
            if n.endswith('l'): R[(d['dst'] + 1) & 31] = (i >> 32) & 0xffffffff
            return True
        a = self.fget(d['s1'], d['m1'], dbl)
        if n in ('movr', 'movrl'): self.fput(d, a, dbl); return True
        b = self.fget(d['s2'], d['m2'], dbl); base = n[:-2] if dbl else n[:-1]
        if base in ('cmp', 'cmpo'): self.cc = 4 if a < b else (2 if a == b else (1 if a > b else 0)); return True
        try:
            if base == 'add': v = b + a
            elif base == 'sub': v = b - a
            elif base == 'mul': v = b * a
            elif base == 'div': v = b / a if a else math.copysign(float('inf'), b if b else 1.0)
            elif base == 'sqrt': v = math.sqrt(a)
            elif base == 'exp': v = 2.0 ** a - 1.0
            elif base == 'log': v = b * math.log2(a)
            elif base == 'logep': v = b * math.log2(a + 1.0)
            elif base == 'logbn': v = float(math.floor(math.log2(abs(a))))
            elif base == 'round': v = float(round(a))
            elif base == 'sin': v = math.sin(a)
            elif base == 'cos': v = math.cos(a)
            elif base == 'tan': v = math.tan(a)
            elif base == 'atan': v = math.atan2(b, a)
            elif base == 'scale': v = b * 2.0 ** (d['s1'] if d['m1'] else sx(R[d['s1']] & 0xffffffff, 32))
            else: return False
        except (ValueError, OverflowError): v = float('nan')
        self.fput(d, v, dbl); return True
    def call(self, target, ret):
        self.frames.append(list(self.r[:16])); self.r[2] = ret
        fp = (self.r[1] + 63) & ~63; self.r[0] = self.r[31]; self.r[31] = fp; self.r[1] = fp + 64; self.ip = target
    def step(self):
        m = self.m; ip = self.ip; w = m.r(ip, 4); d = decode(w, m.r(ip + 4, 4), ip); R = self.r; k = d['kind']; nxt = ip + d['size']; self.steps += 1
        S = lambda v: sx(v & 0xffffffff, 32)
        if k == 'ctrl':
            n = d['name']
            if n == 'b': nxt = d['target']
            elif n == 'call': self.call(d['target'], nxt); return
            elif n == 'bal': R[30] = nxt; nxt = d['target']
            elif n == 'ret':
                if not self.frames: self.halt = 'ret from top'; return
                ret_frame = self.frames.pop(); fp = R[0]; R[:16] = ret_frame; R[31] = fp & ~63; nxt = R[2]
            else:
                mask = d['op'] & 7
                if (mask == 0 and self.cc == 0) or (self.cc & mask): nxt = d['target']
        elif k == 'cobr':
            a = d['s1'] if d['lit1'] else R[d['s1']]; b = R[d['s2']]; n = d['name']
            if n in ('bbc', 'bbs'):
                bit = (b >> (a & 31)) & 1
                if (n == 'bbs') == bool(bit): nxt = d['target']
            else:
                if n.startswith('cmpib'): self.cmp(S(a), S(b))
                else: self.cmp(a & 0xffffffff, b & 0xffffffff)
                mask = d['op'] & 7
                if (mask == 0 and self.cc == 0) or (self.cc & mask): nxt = d['target']
        elif k == 'test':
            mask = d['op'] & 7; R[d['dst']] = 1 if ((mask == 0 and self.cc == 0) or (self.cc & mask)) else 0
        elif k == 'reg':
            if d['name'] in FPNAMES:
                if not self.fpu(d): self.halt = 'unimplemented %s at %x' % (d['name'], ip); return
                self.ip = nxt & 0xffffffff; return
            a = d['s1'] if d['m1'] else R[d['s1']]; b = d['s2'] if d['m2'] else R[d['s2']]; n = d['name']; M = 0xffffffff; res = None
            if n == 'mov': res = a
            elif n == 'movl': R[d['dst']] = a if d['m1'] else R[d['s1']]; R[(d['dst'] + 1) & 31] = 0 if d['m1'] else R[(d['s1'] + 1) & 31]
            elif n in ('movt', 'movq'):
                for i in range(3 if n == 'movt' else 4): R[(d['dst'] + i) & 31] = (a if i == 0 else 0) if d['m1'] else R[(d['s1'] + i) & 31]
            elif n in ('addo', 'addi'): res = a + b
            elif n in ('subo', 'subi'): res = b - a
            elif n == 'and': res = a & b
            elif n == 'andnot': res = b & ~a
            elif n == 'notand': res = ~b & a
            elif n == 'or': res = a | b
            elif n == 'xor': res = a ^ b
            elif n == 'nor': res = ~(a | b)
            elif n == 'xnor': res = ~(a ^ b)
            elif n == 'not': res = ~a
            elif n == 'ornot': res = b | ~a
            elif n == 'notor': res = ~b | a
            elif n == 'nand': res = ~(a & b)
            elif n == 'setbit': res = b | (1 << (a & 31))
            elif n == 'clrbit': res = b & ~(1 << (a & 31))
            elif n == 'notbit': res = b ^ (1 << (a & 31))
            elif n == 'shlo': res = (b << a) if a < 32 else 0
            elif n == 'shli': res = b << (a & 31)
            elif n == 'shro': res = ((b & M) >> a) if a < 32 else 0
            elif n in ('shri', 'shrdi'): res = S(b) >> min(a, 31)
            elif n == 'rotate': a &= 31; b &= M; res = (b << a) | (b >> (32 - a)) if a else b
            elif n == 'cmpo': self.cmp(a & M, b & M)
            elif n == 'cmpi': self.cmp(S(a), S(b))
            elif n == 'cmpinco': self.cmp(a & M, b & M); res = b + 1
            elif n == 'cmpinci': self.cmp(S(a), S(b)); res = b + 1
            elif n == 'cmpdeco': self.cmp(a & M, b & M); res = b - 1
            elif n == 'cmpdeci': self.cmp(S(a), S(b)); res = b - 1
            elif n == 'concmpo':
                if not self.cc & 4: self.cc = 2 if (a & M) <= (b & M) else 1
            elif n == 'concmpi':
                if not self.cc & 4: self.cc = 2 if S(a) <= S(b) else 1
            elif n == 'chkbit': self.cc = 2 if (b >> (a & 31)) & 1 else 0
            elif n == 'mulo' or n == 'muli': res = a * b
            elif n == 'divo': res = (b & M) // (a & M) if a & M else 0
            elif n == 'remo': res = (b & M) % (a & M) if a & M else 0
            elif n == 'divi': res = int(S(b) / S(a)) if S(a) else 0
            elif n in ('remi', 'modi'): res = (abs(S(b)) % abs(S(a))) * (1 if S(b) >= 0 else -1) if S(a) else 0
            elif n == 'emul': p = (a & M) * (b & M); R[d['dst']] = p & M; R[(d['dst'] + 1) & 31] = p >> 32
            elif n == 'extract': res = (R[d['dst']] >> (a & 31)) & ((1 << b) - 1) if b < 32 else R[d['dst']] >> (a & 31)
            elif n == 'flushreg': pass
            else: self.halt = 'unimplemented %s at %x' % (n, ip); return
            if res is not None: R[d['dst']] = res & M
        elif k == 'mem':
            n = d['name']; ea = self.ea(d, ip); rg = d['reg']
            if n == 'lda': R[rg] = ea
            elif n == 'ld': R[rg] = m.r(ea, 4)
            elif n == 'ldob': R[rg] = m.r(ea, 1)
            elif n == 'ldos': R[rg] = m.r(ea, 2)
            elif n == 'ldib': R[rg] = sx(m.r(ea, 1), 8) & 0xffffffff
            elif n == 'ldis': R[rg] = sx(m.r(ea, 2), 16) & 0xffffffff
            elif n == 'ldl': R[rg] = m.r(ea, 4); R[(rg + 1) & 31] = m.r(ea + 4, 4)
            elif n == 'ldt' or n == 'ldq':
                for i in range(3 if n == 'ldt' else 4): R[(rg + i) & 31] = m.r(ea + 4 * i, 4)
            elif n == 'st': m.w(ea, R[rg], 4)
            elif n in ('stob', 'stib'): m.w(ea, R[rg], 1)
            elif n in ('stos', 'stis'): m.w(ea, R[rg], 2)
            elif n == 'stl': m.w(ea, R[rg], 4); m.w(ea + 4, R[(rg + 1) & 31], 4)
            elif n == 'stt' or n == 'stq':
                for i in range(3 if n == 'stt' else 4): m.w(ea + 4 * i, R[(rg + i) & 31], 4)
            elif n == 'bx': nxt = ea
            elif n == 'balx': R[rg] = nxt; nxt = ea
            elif n == 'callx': self.call(ea, nxt); return
        else:
            self.halt = 'unknown opcode %08x at %x' % (w, ip); return
        self.ip = nxt & 0xffffffff
    def run(self, entry, sp=0x00580000, maxsteps=5000000, stop_at=()):
        self.ip = entry; self.r[1] = sp; self.r[31] = sp - 64; self.halt = None; self.frames = []
        while self.halt is None and self.steps < maxsteps:
            if self.ip in stop_at: self.halt = 'stop'; break
            self.step()
        return self.halt or 'max steps'

def dis(addr, count=40, mem=None):
    mem = mem or Mem(); out = []
    for _ in range(count):
        w = mem.r(addr, 4); d = decode(w, mem.r(addr + 4, 4), addr); out.append('%06x  %08x  %s' % (addr, w, fmt(d))); addr += d['size']
    return out

if __name__ == '__main__':
    if sys.argv[1] == 'dis': print('\n'.join(dis(int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 40)))
