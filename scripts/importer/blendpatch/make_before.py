"""The 'before' faces of the patch, in the stored numbers of the base file, face for face and corner for corner with the 'as edited' object of patch.blend."""
import pickle, numpy as np
def load(p):
    D = pickle.load(open(p, 'rb'))
    for d in D['objects']:
        for k, v in list(d.items()):
            if isinstance(v, tuple) and len(v) == 4 and v[0] == 'nd': d[k] = np.frombuffer(v[3], v[1]).reshape(v[2])
    return D
A = load('blenddiff/x_mountain.pkl')['objects'][0]; U = load('blenddiff/x_mountain_patched.pkl')['objects'][0]; PB = load('blenddiff/x_patch.pkl')['objects']; K = pickle.load(open('blenddiff/final.pkl', 'rb'))
aft = next(o for o in PB if '(as edited)' in o['name'])
def poly(o, k): s, n = int(o['loop_start'][k]), int(o['loop_total'][k]); return o['co_local'][o['loop_vert'][s:s + n]]
b = lambda p: np.ascontiguousarray(p, np.float32).tobytes()
byk = {}
for k in K['moved']: byk.setdefault(frozenset(b(p) for p in poly(U, k)), []).append(k)
before = []
for j in range(len(aft['loop_total'])):
    Q = poly(aft, j); ks = byk[frozenset(b(p) for p in Q)]; assert len(ks) == 1; k = ks[0]; Pu = poly(U, k); Pa = poly(A, k); idx = [next(i for i in range(len(Pu)) if b(Pu[i]) == b(c)) for c in Q]
    before.append([tuple(float(x) for x in Pa[i]) for i in idx])
pickle.dump(dict(before=before, matrix=[list(map(float, r)) for r in A['matrix']]), open('blenddiff/before.pkl', 'wb')); print('before faces', len(before))
