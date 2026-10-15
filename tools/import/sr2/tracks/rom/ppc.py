"""Compact PowerPC 603e disassembler + constant tracker (lis/addi|ori pairs, SDA-relative) for SEGA Rally 2.
dis(word, pc) -> (mnemonic, operand string, info dict).  info keys: rd (written GPR), kind, ra, imm, target ...
"""
import struct

def sx(v, b):
    return v - (1 << b) if v & (1 << (b - 1)) else v

X31 = {  # xo: (name, form)
    0: ('cmpw', 'cmp'), 32: ('cmplw', 'cmp'), 4: ('tw', 'tab'),
    8: ('subfc', 'dab'), 10: ('addc', 'dab'), 11: ('mulhwu', 'dab'), 75: ('mulhw', 'dab'), 40: ('subf', 'dab'),
    104: ('neg', 'da'), 136: ('subfe', 'dab'), 138: ('adde', 'dab'), 200: ('subfze', 'da'), 202: ('addze', 'da'),
    232: ('subfme', 'da'), 234: ('addme', 'da'), 235: ('mullw', 'dab'), 266: ('add', 'dab'), 459: ('divwu', 'dab'), 491: ('divw', 'dab'),
    28: ('and', 'asb'), 60: ('andc', 'asb'), 124: ('nor', 'asb'), 284: ('eqv', 'asb'), 316: ('xor', 'asb'), 412: ('orc', 'asb'),
    444: ('or', 'asb'), 476: ('nand', 'asb'), 24: ('slw', 'asb'), 536: ('srw', 'asb'), 792: ('sraw', 'asb'), 824: ('srawi', 'assh'),
    26: ('cntlzw', 'as'), 922: ('extsh', 'as'), 954: ('extsb', 'as'),
    23: ('lwzx', 'ldx'), 55: ('lwzux', 'ldx'), 87: ('lbzx', 'ldx'), 119: ('lbzux', 'ldx'), 279: ('lhzx', 'ldx'), 311: ('lhzux', 'ldx'),
    343: ('lhax', 'ldx'), 375: ('lhaux', 'ldx'), 151: ('stwx', 'stx'), 183: ('stwux', 'stx'), 215: ('stbx', 'stx'), 247: ('stbux', 'stx'),
    407: ('sthx', 'stx'), 439: ('sthux', 'stx'), 534: ('lwbrx', 'ldx'), 662: ('stwbrx', 'stx'), 790: ('lhbrx', 'ldx'), 918: ('sthbrx', 'stx'),
    535: ('lfsx', 'fldx'), 567: ('lfsux', 'fldx'), 599: ('lfdx', 'fldx'), 631: ('lfdux', 'fldx'),
    663: ('stfsx', 'fstx'), 695: ('stfsux', 'fstx'), 727: ('stfdx', 'fstx'), 759: ('stfdux', 'fstx'), 983: ('stfiwx', 'fstx'),
    19: ('mfcr', 'd'), 83: ('mfmsr', 'd'), 146: ('mtmsr', 'd'), 144: ('mtcrf', 'mtcrf'), 339: ('mfspr', 'spr'), 467: ('mtspr', 'spr'),
    371: ('mftb', 'spr'), 54: ('dcbst', 'ab'), 86: ('dcbf', 'ab'), 246: ('dcbtst', 'ab'), 278: ('dcbt', 'ab'), 470: ('dcbi', 'ab'),
    1014: ('dcbz', 'ab'), 982: ('icbi', 'ab'), 598: ('sync', ''), 854: ('eieio', ''), 306: ('tlbie', 'b'), 370: ('tlbia', ''),
    20: ('lwarx', 'ldx'), 150: ('stwcx.', 'stx'), 210: ('mtsr', 'd'), 595: ('mfsr', 'd'), 512: ('mcrxr', ''), 597: ('lswi', 'dab'), 725: ('stswi', 'dab'),
}
X63 = {0: 'fcmpu', 32: 'fcmpo', 12: 'frsp', 14: 'fctiw', 15: 'fctiwz', 40: 'fneg', 72: 'fmr', 136: 'fnabs', 264: 'fabs',
       583: 'mffs', 711: 'mtfsf', 70: 'mtfsb0', 38: 'mtfsb1', 134: 'mtfsfi', 64: 'mcrfs'}
A63 = {18: ('fdiv', 'dab'), 20: ('fsub', 'dab'), 21: ('fadd', 'dab'), 22: ('fsqrt', 'db'), 23: ('fsel', 'dacb'), 24: ('fres', 'db'), 25: ('fmul', 'dac'),
       26: ('frsqrte', 'db'), 28: ('fmsub', 'dacb'), 29: ('fmadd', 'dacb'), 30: ('fnmsub', 'dacb'), 31: ('fnmadd', 'dacb')}
LOADS = {32: 'lwz', 33: 'lwzu', 34: 'lbz', 35: 'lbzu', 40: 'lhz', 41: 'lhzu', 42: 'lha', 43: 'lhau', 46: 'lmw', 48: 'lfs', 49: 'lfsu', 50: 'lfd', 51: 'lfdu'}
STORES = {36: 'stw', 37: 'stwu', 38: 'stb', 39: 'stbu', 44: 'sth', 45: 'sthu', 47: 'stmw', 52: 'stfs', 53: 'stfsu', 54: 'stfd', 55: 'stfdu'}
SPR = {1: 'xer', 8: 'lr', 9: 'ctr', 18: 'dsisr', 19: 'dar', 22: 'dec', 25: 'sdr1', 26: 'srr0', 27: 'srr1', 272: 'sprg0', 273: 'sprg1', 274: 'sprg2',
       275: 'sprg3', 287: 'pvr', 1008: 'hid0', 1009: 'hid1'}
CND = ['lt', 'gt', 'eq', 'so']
NCND = ['ge', 'le', 'ne', 'ns']

def bcname(bo, bi, suffix):
    c = bi & 3; cr = bi >> 2; crs = ('cr%d' % cr) if cr else ''
    if bo & 0x14 == 0x14: return 'b' + suffix, ''
    if bo & 0x10 == 0:
        if bo & 4:
            return 'b' + (CND[c] if bo & 8 else NCND[c]) + suffix, crs
        return ('bdnz' if not bo & 2 else 'bdz') + ('t' if bo & 8 else 'f') + suffix, '%d' % bi
    return ('bdnz' if not bo & 2 else 'bdz') + suffix, ''

def dis(w, pc=0):
    op = w >> 26; d = (w >> 21) & 31; a = (w >> 16) & 31; b = (w >> 11) & 31; c = (w >> 6) & 31
    simm = sx(w & 0xFFFF, 16); uimm = w & 0xFFFF; rc = '.' if w & 1 else ''
    I = {}
    if op == 14:
        I = dict(kind='addi', rd=d, ra=a, imm=simm)
        if a == 0: return 'li', 'r%d,%d' % (d, simm), I
        return 'addi', 'r%d,r%d,%d' % (d, a, simm), I
    if op == 15:
        I = dict(kind='addis', rd=d, ra=a, imm=simm)
        if a == 0: return 'lis', 'r%d,0x%04X' % (d, uimm), I
        return 'addis', 'r%d,r%d,0x%04X' % (d, a, uimm), I
    if op in (12, 13, 7, 8):
        n = {12: 'addic', 13: 'addic.', 7: 'mulli', 8: 'subfic'}[op]
        return n, 'r%d,r%d,%d' % (d, a, simm), dict(kind='arith', rd=d, ra=a, imm=simm)
    if op in (10, 11):
        n = 'cmplwi' if op == 10 else 'cmpwi'; cr = d >> 2
        return n, ('cr%d,' % cr if cr else '') + 'r%d,%d' % (a, uimm if op == 10 else simm), dict(kind='cmpi', ra=a, imm=uimm if op == 10 else simm)
    if op in (24, 25, 26, 27, 28, 29):
        n = {24: 'ori', 25: 'oris', 26: 'xori', 27: 'xoris', 28: 'andi.', 29: 'andis.'}[op]
        if w == 0x60000000: return 'nop', '', {}
        return n, 'r%d,r%d,0x%04X' % (a, d, uimm), dict(kind=n, rd=a, ra=d, imm=uimm)
    if op == 18:
        li = sx(w & 0x03FFFFFC, 26); t = (li if w & 2 else pc + li) & 0xFFFFFFFF
        return 'b' + ('l' if w & 1 else '') + ('a' if w & 2 else ''), '0x%06X' % t, dict(kind='bl' if w & 1 else 'b', target=t)
    if op == 16:
        bd = sx(w & 0xFFFC, 16); t = (bd if w & 2 else pc + bd) & 0xFFFFFFFF
        n, crs = bcname(d, a, ('l' if w & 1 else '') + ('a' if w & 2 else ''))
        return n, (crs + ',' if crs else '') + '0x%06X' % t, dict(kind='bc', target=t)
    if op == 17: return 'sc', '', {}
    if op == 3: return 'twi', '%d,r%d,%d' % (d, a, simm), {}
    if op == 19:
        xo = (w >> 1) & 0x3FF
        if xo == 16:
            n, crs = bcname(d, a, 'lr' + ('l' if w & 1 else '')); return n, crs, dict(kind='blr' if n == 'blr' else 'bclr')
        if xo == 528:
            n, crs = bcname(d, a, 'ctr' + ('l' if w & 1 else '')); return n, crs, dict(kind='bctrl' if w & 1 else 'bctr')
        if xo == 50: return 'rfi', '', dict(kind='blr')
        if xo == 0: return 'mcrf', 'cr%d,cr%d' % (d >> 2, a >> 2), {}
        if xo == 150: return 'isync', '', {}
        crn = {257: 'crand', 129: 'crandc', 289: 'creqv', 225: 'crnand', 33: 'crnor', 449: 'cror', 417: 'crorc', 193: 'crxor'}.get(xo)
        if crn: return crn, '%d,%d,%d' % (d, a, b), {}
        return '.long', '0x%08X' % w, dict(bad=1)
    if op in (20, 21, 23):
        mb = c; me = (w >> 1) & 31
        if op == 21:
            I = dict(kind='rlwinm', rd=a, ra=d, sh=b, mb=mb, me=me)
            if mb == 0 and me == 31 - b: return 'slwi' + rc, 'r%d,r%d,%d' % (a, d, b), I
            if me == 31 and b == 32 - mb: return 'srwi' + rc, 'r%d,r%d,%d' % (a, d, mb), I
            if b == 0 and me == 31: return 'clrlwi' + rc, 'r%d,r%d,%d' % (a, d, mb), I
            return 'rlwinm' + rc, 'r%d,r%d,%d,%d,%d' % (a, d, b, mb, me), I
        n = 'rlwimi' if op == 20 else 'rlwnm'
        return n + rc, ('r%d,r%d,%d,%d,%d' if op == 20 else 'r%d,r%d,r%d,%d,%d') % (a, d, b, mb, me), dict(kind='other', rd=a)
    if op in LOADS:
        fp = op >= 48
        return LOADS[op], '%s%d,%d(r%d)' % ('f' if fp else 'r', d, simm, a), dict(kind='load', rd=None if fp else d, ra=a, imm=simm, upd=op & 1, fp=fp, rt=d)
    if op in STORES:
        fp = op >= 52
        return STORES[op], '%s%d,%d(r%d)' % ('f' if fp else 'r', d, simm, a), dict(kind='store', ra=a, imm=simm, upd=op & 1 and op != 47, fp=fp, rt=d)
    if op == 31:
        xo = (w >> 1) & 0x3FF
        e = X31.get(xo) or X31.get(xo & 0x1FF if (xo & 0x1FF) in (8, 10, 40, 104, 136, 138, 200, 202, 232, 234, 235, 266, 459, 491) else -1)
        if not e: return '.long', '0x%08X' % w, dict(bad=1)
        n, f = e
        if f == 'cmp': cr = d >> 2; return n, ('cr%d,' % cr if cr else '') + 'r%d,r%d' % (a, b), {}
        if f == 'dab': return n + rc, 'r%d,r%d,r%d' % (d, a, b), dict(kind='rrr', rd=d, ra=a, rb=b, op=n)
        if f == 'da': return n + rc, 'r%d,r%d' % (d, a), dict(kind='other', rd=d)
        if f == 'asb':
            if n == 'or' and d == b: return 'mr' + rc, 'r%d,r%d' % (a, d), dict(kind='mr', rd=a, ra=d)
            return n + rc, 'r%d,r%d,r%d' % (a, d, b), dict(kind='other', rd=a)
        if f == 'assh': return n + rc, 'r%d,r%d,%d' % (a, d, b), dict(kind='other', rd=a)
        if f == 'as': return n + rc, 'r%d,r%d' % (a, d), dict(kind='other', rd=a)
        if f == 'ldx': return n, 'r%d,r%d,r%d' % (d, a, b), dict(kind='loadx', rd=d, ra=a, rb=b, upd=n.endswith('ux'))
        if f == 'stx': return n, 'r%d,r%d,r%d' % (d, a, b), dict(kind='storex', ra=a, rb=b, rt=d, upd=n.endswith('ux'))
        if f == 'fldx': return n, 'f%d,r%d,r%d' % (d, a, b), dict(kind='loadx', rd=None, ra=a, rb=b, fp=True, upd=n.endswith('ux'))
        if f == 'fstx': return n, 'f%d,r%d,r%d' % (d, a, b), dict(kind='storex', ra=a, rb=b, fp=True, upd=n.endswith('ux'))
        if f == 'd': return n, 'r%d' % d, dict(kind='other', rd=d if n.startswith('mf') else None)
        if f == 'spr':
            s = ((w >> 16) & 31) | (((w >> 11) & 31) << 5); sn = SPR.get(s, 'spr%d' % s)
            if n == 'mfspr': return 'mf' + sn if s in (1, 8, 9) else 'mfspr', ('r%d' % d) if s in (1, 8, 9) else 'r%d,%s' % (d, sn), dict(kind='other', rd=d)
            return 'mt' + sn if s in (1, 8, 9) else 'mtspr', ('r%d' % d) if s in (1, 8, 9) else '%s,r%d' % (sn, d), dict(kind='mtspr', spr=s, rs=d)
        if f == 'mtcrf': return n, '0x%02X,r%d' % ((w >> 12) & 0xFF, d), {}
        if f == 'ab': return n, 'r%d,r%d' % (a, b), {}
        if f == 'tab': return n, '%d,r%d,r%d' % (d, a, b), {}
        if f == 'b': return n, 'r%d' % b, {}
        return n, '', {}
    if op in (59, 63):
        xo5 = (w >> 1) & 31; s = 's' if op == 59 else ''
        if xo5 in A63 and (op == 59 or xo5 >= 18):
            n, f = A63[xo5]
            ops = {'dab': (d, a, b), 'db': (d, b), 'dac': (d, a, c), 'dacb': (d, a, c, b)}[f]
            return n + s + rc, ','.join('f%d' % x for x in ops), dict(kind='fp')
        if op == 63:
            xo = (w >> 1) & 0x3FF
            n = X63.get(xo)
            if n in ('fcmpu', 'fcmpo'): return n, 'cr%d,f%d,f%d' % (d >> 2, a, b), dict(kind='fp')
            if n in ('frsp', 'fctiw', 'fctiwz', 'fneg', 'fmr', 'fnabs', 'fabs'): return n + rc, 'f%d,f%d' % (d, b), dict(kind='fp')
            if n: return n + rc, '0x%X' % (w & 0x3FFFFFF), dict(kind='fp')
    return '.long', '0x%08X' % w, dict(bad=1)

VOL = [0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

class Tracker:
    """Linear constant propagation. reg[i] = known constant or None. Yields per-instruction resolved info."""
    def __init__(self, sda=None):
        self.sda = dict(sda or {}); self.reset()
    def reset(self):
        self.reg = [None] * 32
        for r, v in self.sda.items(): self.reg[r] = v
    def step(self, pc, w):
        m, o, I = dis(w, pc); k = I.get('kind'); R = self.reg; res = {}
        if k == 'addis':
            R[I['rd']] = ((I['imm'] << 16) & 0xFFFFFFFF) if I['ra'] == 0 else (None if R[I['ra']] is None else (R[I['ra']] + (I['imm'] << 16)) & 0xFFFFFFFF)
            if I['ra'] and R[I['rd']] is not None: res['const'] = R[I['rd']]
        elif k == 'addi':
            if I['ra'] == 0: R[I['rd']] = I['imm'] & 0xFFFFFFFF
            else:
                v = R[I['ra']]; R[I['rd']] = None if v is None else (v + I['imm']) & 0xFFFFFFFF
                if v is not None: res['const'] = R[I['rd']]
        elif k == 'ori':
            v = R[I['ra']]; R[I['rd']] = None if v is None else v | I['imm']
            if v is not None and v >= 0x10000: res['const'] = R[I['rd']]
        elif k == 'mr':
            R[I['rd']] = R[I['ra']]
        elif k in ('load', 'store'):
            v = R[I['ra']] if I['ra'] else None
            if v is not None:
                res['mem'] = (v + I['imm']) & 0xFFFFFFFF; res['rw'] = 'r' if k == 'load' else 'w'
            if I.get('upd'): R[I['ra']] = None if v is None else res['mem']
            if k == 'load' and I.get('rd') is not None:
                if m == 'lmw':
                    for r in range(I['rd'], 32): R[r] = None
                else: R[I['rd']] = None
        elif k in ('loadx', 'storex'):
            va = R[I['ra']] if I['ra'] else None; vb = R[I['rb']]
            if va is not None and vb is None: res['tbl'] = va; res['rw'] = 'r' if k == 'loadx' else 'w'
            elif vb is not None and va is None and I['ra']: res['tbl'] = vb; res['rw'] = 'r' if k == 'loadx' else 'w'
            elif va is not None and vb is not None: res['mem'] = (va + vb) & 0xFFFFFFFF; res['rw'] = 'r' if k == 'loadx' else 'w'
            if I.get('upd'): R[I['ra']] = None
            if k == 'loadx' and I.get('rd') is not None: R[I['rd']] = None
        elif k == 'rrr':
            va = R[I['ra']]; vb = R[I['rb']]
            if I['op'] == 'add':
                if va is not None and vb is not None: R[I['rd']] = (va + vb) & 0xFFFFFFFF
                else:
                    t = va if va is not None else vb
                    if t is not None and t >= 0x1000: res['tbl'] = t; res['rw'] = 'a'
                    R[I['rd']] = None
            else: R[I['rd']] = None
        elif k in ('bl', 'bctrl'):
            for r in VOL: R[r] = None
        elif k == 'blr':
            pass
        elif I.get('rd') is not None:
            R[I['rd']] = None
        for r, v in self.sda.items(): R[r] = v
        return m, o, I, res
