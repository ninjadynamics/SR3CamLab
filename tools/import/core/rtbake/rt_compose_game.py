"""From the raw game bake to the light-map pages and table the importer reads (course setting lm_table=<out>).   python rt_compose_game.py <path> <out> <AMB> [BOUNCE]
    light = (1 - AMB) x sun seen x facing + AMB x (0.35 + 0.65 x sky seen) + BOUNCE x colour coming back         (open flat ground = 1)
The game multiplies its own brightness rule by the map, so a texel holds light / rule (never above 1). The road (lying polygons within 9 m of the
centre line) takes the light without its colour. AMB is the shade level: 0.34 = the look of RT2 ; higher = softer.
No numpy (2026-10-15): the files are read and written by npyio.py / scenefile.py, the arithmetic is rtcompose.c's (its comments quote the
numpy lines it replaced, which it matches to the bit: the pages file is byte for byte numpy's)."""
import os as _os_, sys as _sys_; _sys_.path.insert(0, _os_.path.normpath(_os_.path.join(_os_.path.dirname(_os_.path.abspath(__file__)), '..')))      # tools/import/core
import sys, ctypes
import npyio, scenefile, cbuild
PATH, OUT, AMB = sys.argv[1], sys.argv[2], float(sys.argv[3]); BOUNCE = float(sys.argv[4]) if len(sys.argv) > 4 else 0.55
RAW = npyio.load(PATH + '.raw.npy', mmap=True); npg, side = RAW.shape[0], RAW.shape[1]      # (pages, 2048, 2048, 7) bytes: the bake's light per texel
K = npyio.loadz(PATH + '.pack.npz'); D = npyio.loadz(PATH + '.lm.npz'); S = scenefile.load(PATH + '.scene')
P, N, cen = D['P'], D['N'], S['centre']; n, k = P.shape[0], P.shape[1]
for a, want in ((RAW, '|u1'), (P, '<f8'), (N, '<f8'), (cen, '<f8'), (K['page'], '<i4'), (K['x0'], '<i4'), (K['y0'], '<i4'), (K['nu'], '<i4'), (K['nv'], '<i4')):
    if a.dtype != want: raise SystemExit('%s: an array of %s where %s was expected' % (PATH, a.dtype, want))
if min(K['x0'].view()) < 0 or min(K['y0'].view()) < 0: raise SystemExit('%s: a rectangle outside its page' % PATH)
cbuild.runtime(); L = ctypes.CDLL(cbuild.dll('rtcompose')); Pv, LL, Dd, Ii = ctypes.c_void_p, ctypes.c_longlong, ctypes.c_double, ctypes.c_int
L.rtc_road.restype = LL; L.rtc_road.argtypes = [Pv, LL, Ii, Pv, Pv, LL, Pv]
L.rtc_pages.argtypes = [Pv, Ii, Ii] + [Pv] * 6 + [LL, Dd, Dd, Pv, Pv, Pv]; L.rtc_key.argtypes = [Pv, LL, Pv]
road = npyio.Arr('|b1', (n,)); nroad = L.rtc_road(P.ptr(), n, k, N.ptr(), cen.ptr(), cen.shape[0], road.ptr())
pages = npyio.Arr('|u1', (npg, side, side, 3)); over = LL(0); lsum = Dd(0)
L.rtc_pages(RAW.ptr(), npg, side, *(K[f].ptr() for f in ('page', 'x0', 'y0', 'nu', 'nv')), road.ptr(), n, AMB, BOUNCE, pages.ptr(), ctypes.byref(over), ctypes.byref(lsum))
key = npyio.Arr('|V48', (n,)); L.rtc_key(P.ptr(), n, key.ptr())
npyio.save(OUT + '.lm.pages.npy', pages)
npyio.savez(OUT + '.lm.table.npz', K=key, **{f: K[f] for f in ('page', 'x0', 'y0', 'nu', 'nv')}, **({'ab': K['ab']} if 'ab' in K else {}))      # (ab: where a polygon's corners are in its rectangle - the pieces of a rounded polygon share one)
print('RTCG amb %.3f bounce %.2f ; road polygons %d of %d ; mean light over the pages %.2f ; texels that wanted more than the rule allows (clipped at 1): %.2f%% -> %s' % (AMB, BOUNCE, nroad, n, lsum.value / npg, 100.0 * over.value / (npg * side * side), OUT))
