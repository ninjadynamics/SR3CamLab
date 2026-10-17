"""Where the 1995 spectators stand against the ground of a collected build, and how many pieces of it are turned over.
    python spec_check.py <faces.pkl of R1> <faces.pkl> [<faces.pkl> ...]      (run from the importer folder)"""
import sys, pickle, os
import numpy as np
sys.path.insert(0, os.getcwd())
import crowd, fill1995 as F, build_classic as BC
def ground(G):
    fl = [fc for fc in G['faces'] + G['sky'] + G['extra'] if fc[1] != 'sea' and not str(fc[0]).split('|')[0].endswith('_t')]; return F.Index(fl), fl
def under(gi, x, y, z):
    hs = [h for h, k in gi.heights(x, z, True) if y - 12.0 <= h <= y + 1.0]; return max(hs) if hs else None      # the highest lying surface not above the feet
G1 = pickle.load(open(sys.argv[1], 'rb')); rd = G1['rd']; spots = crowd.classic_spots('1', np.asarray(rd['V'][:, rd['hw']], float), rd['ox'], rd['oz'], zs=BC.ZS)
gi1, _ = ground(G1); base = [under(gi1, x, y, z) for x, y, z, h in spots]
print('%d spectators ; R1: %d with no ground under them, %d more than 0.5 m above it' % (len(spots), sum(b is None for b in base), sum(b is not None and y - b > 0.5 for (x, y, z, h), b in zip(spots, base))))
for p in sys.argv[2:]:
    G = pickle.load(open(p, 'rb')); gi, fl = ground(G); now = [under(gi, x, y, z) for x, y, z, h in spots]
    drop = np.array([(b - n) if (b is not None and n is not None) else (99.0 if (b is not None and n is None) else 0.0) for b, n in zip(base, now)])
    rise = np.array([(n - b) if (b is not None and n is not None) else 0.0 for b, n in zip(base, now)])
    hang = sum(n is None or y - n > 0.5 for (x, y, z, h), n in zip(spots, now))
    print('%s: hanging more than 0.5 m (or over nothing) %d ; ground under a spectator lower than in R1 by more than 0.10 m: %d, by more than 0.5 m: %d (largest %.2f m) ; higher by more than 0.10 m: %d (largest %.2f m)'
          % (os.path.basename(os.path.dirname(p)), hang, int((drop > 0.10).sum()), int((drop > 0.5).sum()), float(drop.max()), int((rise > 0.10).sum()), float(rise.max())))
    worst = np.argsort(-drop)[:5]; print('   largest drops at', [(round(spots[i][0], 1), round(spots[i][1], 1), round(spots[i][2], 1), round(float(drop[i]), 2)) for i in worst if drop[i] > 0.10])
