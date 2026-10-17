"""Join patches built one on the other into ONE numbered course patch file, as stages (coursepatch.apply_file applies them in order,
exactly as the separate patches and a board_moves setting were applied).

    python stage_patch.py <out.json> --needs 1,2 --note "..." <stage> [<stage> ...]
        a stage is a course patch file (.json with "format": "sr3lab course patch"), or  boards=<board_moves.json>  (a list of
        [x, y, z, dx, dy, dz] per corner, coursepatch.move_boards)

Made for the owner's "Mountain R4 is accepted, which means v11 is accepted too. Create patch 3 out of it and reapply the chain to
reobtain an identical version of v11" (2026-10-15): patch 3 = the generated patch 3 of 2026-10-12, the tree boards moved in the v11
scene, the v11 scene's patch (scene_diff 4 -> tree_moves 4d)."""
import json, sys, argparse, hashlib, os

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('stages', nargs='+'); ap.add_argument('--needs', default=''); ap.add_argument('--note', default='')
    a = ap.parse_args(); st = []; sha = set(); course = None; srcs = []
    for s in a.stages:
        if s.startswith('boards='):
            B = json.load(open(s[7:])); assert isinstance(B, list) and all(len(r) == 6 for r in B), 'not a board_moves list: ' + s
            st.append({'board_moves': B}); srcs.append('%s (%d corners, sha1 %s)' % (os.path.basename(s[7:]), len(B), hashlib.sha1(open(s[7:], 'rb').read()).hexdigest()[:12])); continue
        J = json.load(open(s)); assert J.get('format') == 'sr3lab course patch', 'not a course patch: ' + s
        assert 'stages' not in J, 'a staged file cannot be a stage: ' + s
        course = course or J.get('course'); w = J.get('base', {}).get('course_export_sha1')
        if w: sha.add(w)
        st.append(J); srcs.append('%s (sha1 %s: %s)' % (os.path.basename(s), hashlib.sha1(open(s, 'rb').read()).hexdigest()[:12], ', '.join('%s %d' % (k, len(J.get(k, []))) for k in ('remove', 'add', 'move', 'bake') if J.get(k))))
    assert len(sha) <= 1, 'the stages were made on different exports of the course: %s' % sorted(sha)
    out = {'format': 'sr3lab course patch', 'version': 3, 'course': course, 'base': {'course_export_sha1': (sorted(sha) or [None])[0], 'needs': [int(x) for x in a.needs.split(',') if x]},
           'made_by': 'stage_patch.py: ' + (a.note or 'patches built one on the other, joined as stages'), 'stages_from': srcs,
           'space': st[0].get('space') if 'space' in st[0] else None, 'stages': st}
    json.dump(out, open(a.out, 'w', newline='\n')); print('%s: %d stages, %.1f MB; %s' % (a.out, len(st), os.path.getsize(a.out) / 1e6, ' | '.join(srcs)))

if __name__ == '__main__': main()
