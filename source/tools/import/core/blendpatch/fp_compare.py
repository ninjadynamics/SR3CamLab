"""fp_compare.py <a.json> <b.json> <label a> <label b>: the two fingerprints item by item."""
import sys, json
A = json.load(open(sys.argv[1])); B = json.load(open(sys.argv[2])); la, lb = sys.argv[3], sys.argv[4]; diff = []; n = [0]
def walk(x, y, path):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x: diff.append('%s: only in %s' % (path + '/' + k, lb))
            elif k not in y: diff.append('%s: only in %s' % (path + '/' + k, la))
            else: walk(x[k], y[k], path + '/' + k)
    else:
        n[0] += 1
        if x != y: diff.append('%s: %s | %s' % (path, str(x)[:60], str(y)[:60]))
walk(A, B, '')
print('%s against %s: %d items compared (stored vertex numbers, face tables, texture coordinates, materials, images, vertex groups), %d different' % (la, lb, n[0], len(diff)))
for d in diff[:12]: print('   DIFFERENT', d)
for name, o in A['objects'].items():
    if o.get('type') == 'MESH': print('   %-42s %6d vertices %6d faces ; positions %s ; uv %s' % (name[:42], o['vertices'], o['faces'], o['vertex positions (float32 bytes)'][:12], list(o['uv layers'].values())[0][:12] if o['uv layers'] else '-'))
