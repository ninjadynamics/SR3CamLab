"""Rebuild only a track's wall BSP from its unchanged TrackDeform road.

Writes a separate staged SBF; never installs, edits road vertices, or rebakes.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import bsp
import bsp_build
import build_more as BM
import sbfw
import trackdeform as TD


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rebuild(source, destination, *, every=1, inset=0.0):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Use a separate staging destination; installation is a separate step')
    f = sbfw.read_sbf(str(source))
    by = f.byid()
    root = f.chunks[-1]
    bid, rid = root.u32(0x34), root.u32(0x0c)
    if not bid or not rid:
        raise ValueError('Track requires an existing road and boundary')
    original = {c.id: (c.kind, c.data, c.fix[:], c.ref[:], c.z) for c in f.chunks}
    td = TD.parse_td(by[rid])
    rows = [(td.verts[i]['pos'].astype(np.float64), int(td.off[i]), int(td.A[i])) for i in range(1, td.n + 1)]
    surfaces, wall, floor = BM.boundary_surfaces(f)
    stats = BM.add_walls(f, rows, surfaces, wall, floor, every=every, terrain=True, inset=inset, footprint_boundary=True)
    changed = [c.id for c in f.chunks if (c.kind, c.data, c.fix, c.ref, c.z) != original[c.id]]
    if changed != [bid]:
        raise AssertionError('Boundary-only contract failed: %s' % changed)
    # Independent parser + serializer must retain the exact authored BSP.
    new_b = bsp.parse_bsp(f.byid()[bid])
    data, fix = bsp_build.serialize(*bsp_build.to_tree(new_b))
    assert data == f.byid()[bid].data and fix == f.byid()[bid].fix
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = sbfw.write_sbf(f, compress=True, layout='auto', level=6)
    destination.write_bytes(payload)
    reread = sbfw.read_sbf(str(destination))
    after = reread.byid()
    assert set(after) == set(original)
    assert all((after[cid].kind, after[cid].data, after[cid].fix, after[cid].ref, after[cid].z) == value for cid, value in original.items() if cid != bid)
    assert after[bid].data == data
    return dict(source=str(source), output=str(destination), source_sha256=sha(source.read_bytes()), output_sha256=sha(payload),
                changed_chunk_ids=['%08x' % bid], unchanged_chunks=len(original)-1,
                road_chunk='%08x' % rid, road_sha256=sha(original[rid][1]), road_bytes_unchanged=True,
                scenery_materials_textures_lightmaps_unchanged=True, bsp_roundtrip_identical=True, stats=stats)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source'); ap.add_argument('destination')
    ap.add_argument('--every', type=int, default=1); ap.add_argument('--inset', type=float, default=0.0)
    ap.add_argument('--report', required=True)
    a = ap.parse_args()
    report = rebuild(a.source, a.destination, every=a.every, inset=a.inset)
    Path(a.report).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()