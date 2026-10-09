"""Look for the per-course car start positions of SEGA Rally Championship: float triples (x, y, z) in the program ROM /
main data ROM / copro data that lie on the first cells of a course's collision centre line.
    python m2start.py"""
import os, struct
import numpy as np
import i960
from common import *
CL = os.path.join(os.path.dirname(WORK), 'classic', 'obj')

def main():
    roms = {'maincpu': np.fromfile(os.path.join(i960.M2, 'maincpu.bin'), '<f4'), 'main_data': np.fromfile(os.path.join(i960.M2, 'main_data.bin'), '<f4')}
    for c in '1234':
        C = np.loadtxt(os.path.join(CL, 'src_course%s_centreline.csv' % c), delimiter=',', comments='#'); C[:, 2] *= -1          # game axes
        print('course', c, 'cell 0', C[0].round(1).tolist(), 'cell 1', C[1].round(1).tolist(), 'cell 299', C[-1].round(1).tolist())
        for nm, f in roms.items():
            ok = np.isfinite(f) & (np.abs(f) < 2000); hits = []
            for order in ((0, 1, 2), (0, 2, 1)):                                                   # x, y, z or x, z, y
                x = f[:-2]; a = f[1:-1]; b = f[2:]; y, z = (a, b) if order == (0, 1, 2) else (b, a)
                for k in list(range(0, 6)) + list(range(294, 300)):
                    m = ok[:-2] & ok[1:-1] & ok[2:] & (np.abs(x - C[k, 0]) < 9) & (np.abs(z - C[k, 2]) < 9) & (np.abs(y - C[k, 1]) < 3)
                    for o in np.nonzero(m)[0][:6]: hits.append((int(o) * 4, k, order, [round(float(v), 2) for v in f[o:o + 6]]))
            for h in hits[:8]: print('   %-9s offset %06x near cell %3d order %s: %s' % (nm, h[0], h[1], h[2], h[3]))

if __name__ == '__main__':
    main()
