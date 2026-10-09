"""patch.blend -> the patch file that ships with the mod (a few kB of JSON: our own faces and positions, no SEGA picture, no .blend).
    blender -b <patch.blend> --python bl_dump.py -- <patch.pkl>          (first: the content of patch.blend as plain arrays)
    python patch_to_json.py <patch.pkl> <texmap.json of the build the base scene was decoded from> <out.json> [<base scene dump .pkl>]
    <out.json> = work/courses/<game>.<course name>.patch.<number>.json  (src.mountain.patch.1.json, then .2, ...: the importer applies them in that order)

    add    faces to add, in the order and corner order of patch.blend: 1995 tile name, corners, texture coordinates
    move   original faces some corners of which move: the corners as they are in the base ('before') and as edited ('after')
    base   fingerprints of what the patch was made on; a tool that applies it refuses anything else
Coordinates are the base scene's own (the build decoded back by preview_obj.py: x, y up, z = -gameZ of the 1995 course, metres), written with
the shortest decimals that give the stored 32-bit numbers back exactly."""
import sys, json, pickle, hashlib, os
import numpy as np

EXPORT = 'F:/Jogos/SEGA Rally 3/SR3 track format/work/classic_tex/course1/src_course1_hi.obj'

def load(p):
    D = pickle.load(open(p, 'rb'))
    for d in D['objects']:
        for k, v in list(d.items()):
            if isinstance(v, tuple) and len(v) == 4 and v[0] == 'nd': d[k] = np.frombuffer(v[3], v[1]).reshape(v[2])
    return D
def export_sha1(path=EXPORT):
    """the 1995 course export without its comment lines (an older exporter worded the first line differently)"""
    return hashlib.sha1(b'\n'.join(l for l in open(path, 'rb').read().split(b'\n') if not l.startswith(b'#'))).hexdigest()
f32 = lambda x: float(str(np.float32(x)))                            # shortest decimal that reads back as the same float32
def pts(a): return [[f32(x) for x in p] for p in a]
def loops(d, k): s, n = int(d['loop_start'][k]), int(d['loop_total'][k]); return d['loop_vert'][s:s + n], s

def main(pkl, texmap, out, base=None):
    D = load(pkl); PT = next(o for o in D['objects'] if o['name'] == 'patch'); BEF = next(o for o in D['objects'] if '(before)' in o['name']); AFT = next(o for o in D['objects'] if '(as edited)' in o['name'])
    M = json.load(open(texmap)); tile = lambda m: M['scenery'][str(int(m[4:], 16))]['tile']
    add = []
    for k in range(len(PT['loop_total'])):
        vi, s = loops(PT, k); name = PT['mats'][int(PT['mat_index'][k])]; t = tile(name); assert t not in M['recipes'], 'a patch face uses a composed tile: ' + t
        uv = np.asarray(PT['uv'][s:s + len(vi)], np.float32); add.append(dict(tile=t, p=pts(PT['co_local'][vi]), uv=[[f32(x) for x in q] for q in uv]))
    move = []
    for j in range(len(BEF['loop_total'])):
        vb, _ = loops(BEF, j); va, _ = loops(AFT, j); move.append(dict(before=pts(BEF['co_local'][vb]), after=pts(AFT['co_local'][va])))
    b = dict(course_export_sha1=export_sha1())
    if base:
        A = load(base)['objects'][0]; b.update(scene_vertices=int(len(A['co_local'])), scene_faces=int(len(A['loop_total'])), scene_vertices_sha1=hashlib.sha1(np.ascontiguousarray(A['co_local'], np.float32).tobytes()).hexdigest())
    head = dict(format='sr3lab course patch', version=1, course=dict(game='src', course='1', name='mountain'), base=b,
                space='the build decoded back (preview_obj.py): x, y up, z = -gameZ of the 1995 course, metres; uv as Blender has them (v up)')
    with open(out, 'w', newline='\n') as fo:                              # one face a line: a change shows as changed lines
        fo.write('{\n'); fo.write(''.join(' %s: %s,\n' % (json.dumps(k), json.dumps(v)) for k, v in head.items()))
        fo.write(' "add": [\n' + ',\n'.join('  ' + json.dumps(a) for a in add) + '\n ],\n'); fo.write(' "move": [\n' + ',\n'.join('  ' + json.dumps(m) for m in move) + '\n ]\n}\n')
    print('patch file: %d faces to add (%s), %d faces with moved corners ; %d bytes -> %s' % (len(add), dict(__import__('collections').Counter(a['tile'][-22:] for a in add)), len(move), os.path.getsize(out), out))

if __name__ == '__main__': main(*sys.argv[1:5])
