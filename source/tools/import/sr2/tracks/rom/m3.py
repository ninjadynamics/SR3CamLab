"""Fixed-CROM course tables (road blocks, scenery blocks, debug course line)."""
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr2common import *
SCENERY_DESC = 0xCF180; ROAD_DESC = 0xDE1F8; LINE_TAB = 0xE2C0C

def desc(base, k): return u32(base + 12 * k), u32(base + 12 * k + 4), u32(base + 12 * k + 8)
def blocks(base, k):
    n, kind, p = desc(base, k); out = []
    for i in range(n):
        a = p + 48 * i
        out.append((f32(a), f32(a + 4), f32(a + 8), u32(a + 12), [(u32(a + 16 + 8 * j), u32(a + 20 + 8 * j)) for j in range(4)]))
    return out
def road_blocks(k): return np.array([b[:3] for b in blocks(ROAD_DESC, k)])
def course_line(k):
    n = u32(LINE_TAB + 8 * k) + 1; p = u32(LINE_TAB + 8 * k + 4)
    return np.frombuffer(C, dtype='>f4', count=3 * n, offset=p).reshape(n, 3).astype(float)
