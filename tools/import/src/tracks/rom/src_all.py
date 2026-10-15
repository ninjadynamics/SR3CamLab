"""SEGA Rally Championship: all four courses -> OBJ + MTL + coloured tiles (same rules as the Mountain work:
classic_export.decode / material, classic_tex page fitting, m2colour). Sky / backdrop objects are exported as a
separate OBJ (<course>_sky.obj) because they are +-100 km polygons.
    python src_all.py [course numbers]     -> ../src/course<N>_<name>/"""
import os, sys, json, numpy as np
from PIL import Image, ImageDraw
import classic_export as ce, classic_tex as ct, m2colour
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..', 'src')
COURSES = {1: dict(name='mountain', hi=(1259, 1318), sky=(1257, 1258), low=(1319, 1378)),
           2: dict(name='desert', hi=(937, 996), sky=(997, 998, 999), low=(1000, 1059)),
           3: dict(name='lakeside', hi=(1379, 1438), sky=(1439, 1440), low=(1441, 1500)),
           4: dict(name='forest', hi=(1135, 1194), sky=(1195, 1196), low=(1197, 1256))}
def write_obj(path, objs, D, mats, tag):
    main, poly, polyf, tex16, tab = D
    base = os.path.splitext(os.path.basename(path))[0]; fo = open(path, 'w')
    fo.write('# SEGA Rally Championship %s. Y up, Z = -gameZ (right-handed)\nmtllib %s.mtl\n' % (tag, base)); nv = nvt = nf = 0; used = {}
    for k in objs:
        fo.write('o obj_%04d\n' % k); vl = []; tl = []; fl = []; cur = None; vmap = {}
        for p in ce.decode(k, tab, poly, polyf, tex16):
            name, info = ce.material(p['hdr']); mats.setdefault(name, info); used[name] = info
            if name != cur: fl.append('usemtl ' + name); cur = name
            Pt = np.array([(x, y, -z) for x, y, z in p['verts']]); idx = []
            tw, th = (info['w'], info['h']) if info else (1, 1)
            for i in range(len(Pt)):
                key = tuple(np.round(Pt[i], 4)); vi = vmap.get(key)
                if vi is None: vi = nv + len(vl) + 1; vmap[key] = vi; vl.append('v %.4f %.4f %.4f' % tuple(Pt[i]))
                u, v = p['uv'][i]
                if info and info['mx']: u = u if int(u // tw) % 2 == 0 else (2 * tw * (int(u // tw) // 2 + 1) - u)
                if info and info['my']: v = v if int(v // th) % 2 == 0 else (2 * th * (int(v // th) // 2 + 1) - v)
                tl.append('vt %.5f %.5f' % (u / tw, 1.0 - v / th)); idx.append((vi, nvt + len(tl)))
            g = np.cross(Pt[1] - Pt[0], Pt[2] - Pt[0]); hn = -np.array([p['normal'][0], p['normal'][1], -p['normal'][2]])
            if np.dot(g, hn) < 0: idx = idx[::-1]
            fl.append('f ' + ' '.join('%d/%d' % t for t in idx)); nf += 1
        fo.write('\n'.join(vl + tl + fl) + '\n'); nv += len(vl); nvt += len(tl)
    fo.close()
    with open(path[:-4] + '.mtl', 'w') as fm:
        for name, info in used.items():
            fm.write('newmtl %s\nKd 0.8 0.8 0.8\n' % name)
            if info:
                fm.write('map_Kd textures/%s.png\n' % name)
                if info['alpha']: fm.write('map_d textures/%s.png\n' % name)
            else:
                pal = m2colour.palette(); cb = int(name[4:], 16); c = pal[cb] / 255.0 if cb < len(pal) else (0.5, 0.5, 0.5)
                fm.seek(fm.tell()); fm.write('Kd %.3f %.3f %.3f\n' % tuple(c))
    return nf, nv, used
# Banner boards that are NOT inside a course's object block (world coordinates, sheet 0 tile x1280 y0 256x32):
# 172 = Mountain (start line + 3 checkpoints, each a front/back pair), 171 = Desert (2 boards). None found for 3 and 4.
PROPS = {1: (172,), 2: (171,)}
def props(n):
    """<course>_props.obj + .mtl + its tiles (added to textures/, nothing else is rewritten)"""
    if n not in PROPS: return None
    C = COURSES[n]; out = os.path.join(ROOT, 'course%d_%s' % (n, C['name'])); os.makedirs(os.path.join(out, 'textures'), exist_ok=True)
    main, poly, polyf, tex16 = ce.load(); D = (main, poly, polyf, tex16, ce.table(main)); mats = {}
    r = write_obj(os.path.join(out, 'src_course%d_props.obj' % n), PROPS[n], D, mats, 'course %d (%s), banner boards outside the course block' % (n, C['name']))
    pg = ct.all_pages(); pages = json.load(open(os.path.join(out, 'pages.json'))) if os.path.exists(os.path.join(out, 'pages.json')) else {}
    auto = {(0, 0): 0x200000, (0, 1): 0x280000}
    for k, o in pages.items(): auto[tuple(int(x) for x in k.split(','))] = o
    for name, m in mats.items():
        if not m: continue
        sh = np.hstack([pg[auto[(m['sheet'], 0)]], pg[auto[(m['sheet'], 1)]]]); t = sh[m['y']:m['y'] + m['h'], m['x']:m['x'] + m['w']]
        ct.to_image(t, m['alpha'], m).save(os.path.join(out, 'textures', name + '.png'))
    print('course %d %s: props %d faces, materials %s' % (n, C['name'], r[0], list(mats)))
    return r
def run(n):
    C = COURSES[n]; out = os.path.join(ROOT, 'course%d_%s' % (n, C['name'])); os.makedirs(os.path.join(out, 'textures'), exist_ok=True); os.makedirs(os.path.join(out, 'sheets'), exist_ok=True)
    main, poly, polyf, tex16 = ce.load(); D = (main, poly, polyf, tex16, ce.table(main)); mats = {}; base = 'src_course%d' % n
    r1 = write_obj(os.path.join(out, base + '_hi.obj'), range(C['hi'][0], C['hi'][1] + 1), D, mats, 'course %d (%s), high detail' % (n, C['name']))
    r2 = write_obj(os.path.join(out, base + '_sky.obj'), C['sky'], D, mats, 'course %d (%s), sky and backdrop objects' % (n, C['name']))
    r3 = write_obj(os.path.join(out, base + '_low.obj'), range(C['low'][0], C['low'][1] + 1), D, mats, 'course %d (%s), low detail' % (n, C['name']))
    json.dump(mats, open(os.path.join(out, 'materials.json'), 'w'), indent=0)
    pg = ct.all_pages(); rects, res = ct.fit_pages(mats, pg)
    for key, sc in res.items(): print('  course %d sheet %d half %d: %d rectangles, best pages %s' % (n, key[0], key[1], len(rects[key]), [('%07x' % o, round(s, 2)) for s, o in sc[:3]]))
    # a sheet is 2048 x 1024 texels = one contiguous 1 MB block of the ROM (two 512 KB halves, x < 1024 first).
    # Sheet 1 = the course's block, taken from the fit of its first half; sheet 0 = the common block at 0x200000.
    base = res[(1, 0)][0][1]; auto = {(1, 0): base, (1, 1): base + 0x80000, (0, 0): 0x200000, (0, 1): 0x280000}
    json.dump({'%d,%d' % k: o for k, o in auto.items()}, open(os.path.join(out, 'pages.json'), 'w'))
    sheets = {s: np.hstack([pg[auto[(s, 0)]], pg[auto[(s, 1)]]]) for s in (0, 1)}
    for s in (0, 1):
        if not any(m and m['sheet'] == s for m in mats.values()): continue
        im = Image.fromarray((sheets[s] * 17).astype(np.uint8)).convert('RGB'); dr = ImageDraw.Draw(im)
        for m in mats.values():
            if m and m['sheet'] == s: dr.rectangle([m['x'], m['y'], m['x'] + m['w'] - 1, m['y'] + m['h'] - 1], outline=(255, 0, 0))
        im.save(os.path.join(out, 'sheets', 'sheet%d_rom%07x_2048x1024_rects.png' % (s, auto[(s, 0)])))
    for fn in os.listdir(os.path.join(out, 'textures')): os.remove(os.path.join(out, 'textures', fn))
    cnt = miss = 0
    for name, m in mats.items():
        if not m: continue
        t = sheets[m['sheet']][m['y']:m['y'] + m['h'], m['x']:m['x'] + m['w']]
        if t.shape != (m['h'], m['w']): miss += 1; continue
        ct.to_image(t, m['alpha'], m).save(os.path.join(out, 'textures', name + '.png')); cnt += 1
    print('course %d %s: hi %d faces, sky %d faces, low %d faces; %d materials, %d tiles written, %d missing' % (n, C['name'], r1[0], r2[0], r3[0], len(mats), cnt, miss))
    print('   sky materials:', {k: (v and (v['cb'], v['luma'])) for k, v in r2[2].items()})
    props(n)                                                          # after the tiles: run() empties textures/ first
if __name__ == '__main__':
    if sys.argv[1:2] == ['props']:
        for n in [int(x) for x in sys.argv[2:]] or [1, 2]: props(n)
    else:
        for n in [int(x) for x in sys.argv[1:]] or [1, 2, 3, 4]: run(n)
