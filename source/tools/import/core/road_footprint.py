"""Outer boundary of the union of existing corridor triangles (no road edits).

Road slices may fold back across a tight corner. Their raw left/right lines then
contain internal edges and omit short exposed cross-slice edges. Split the edge
arrangement and keep only pieces separating supported road from the outside.
"""
import collections
import math


def union_boundary(quads, inside, cell_size=8.0, probe=1e-5):
    edges = []; unique = {}
    for source, q in enumerate(quads):
        for tri in ((q[0], q[1], q[2]), (q[0], q[2], q[3])):
            for a, b in zip(tri, tri[1:] + tri[:1]):
                a, b = tuple(a), tuple(b)
                if math.dist(a, b) < 1e-6: continue
                key = tuple(sorted((a, b)))
                if key not in unique:
                    unique[key] = len(edges); edges.append((a, b, source))
    bins = collections.defaultdict(list)
    for i, (a, b, _) in enumerate(edges):
        for x in range(math.floor(min(a[0], b[0])/cell_size), math.floor(max(a[0], b[0])/cell_size)+1):
            for z in range(math.floor(min(a[1], b[1])/cell_size), math.floor(max(a[1], b[1])/cell_size)+1):
                bins[x, z].append(i)
    cuts = [[0.0, 1.0] for _ in edges]; seen = set(); crossings = 0
    cross = lambda a, b: a[0]*b[1]-a[1]*b[0]
    sub = lambda a, b: (a[0]-b[0], a[1]-b[1])
    dot = lambda a, b: a[0]*b[0]+a[1]*b[1]
    for bucket in bins.values():
        for ii, i in enumerate(bucket):
            a, b, _ = edges[i]; r = sub(b, a); rr = dot(r, r)
            for j in bucket[ii+1:]:
                key = (min(i,j), max(i,j))
                if key in seen: continue
                seen.add(key)
                c, d, _ = edges[j]; s = sub(d, c); ss = dot(s, s); ca = sub(c,a)
                den = cross(r,s)
                if abs(den) > 1e-12*math.sqrt(rr*ss):
                    t = cross(ca,s)/den; u = cross(ca,r)/den
                    if -1e-9 <= t <= 1+1e-9 and -1e-9 <= u <= 1+1e-9:
                        cuts[i].append(min(1.,max(0.,t))); cuts[j].append(min(1.,max(0.,u)))
                        crossings += 0 < t < 1 and 0 < u < 1
                elif abs(cross(ca,r)) <= 1e-8*math.sqrt(rr):
                    for p in (c,d):
                        t = dot(sub(p,a),r)/rr
                        if 0 < t < 1: cuts[i].append(t)
                    for p in (a,b):
                        u = dot(sub(p,c),s)/ss
                        if 0 < u < 1: cuts[j].append(u)
    out = []; sources = []; emitted = set(); pieces = 0
    for (a,b,source), ts in zip(edges,cuts):
        r = sub(b,a); ln = math.sqrt(dot(r,r)); nx,nz = -r[1]/ln,r[0]/ln
        ts = sorted(set(ts))
        for t,u in zip(ts,ts[1:]):
            if (u-t)*ln < 1e-6: continue
            pieces += 1
            mid = (a[0]+r[0]*(t+u)/2, a[1]+r[1]*(t+u)/2)
            plus = inside((mid[0]+nx*probe,mid[1]+nz*probe))
            minus = inside((mid[0]-nx*probe,mid[1]-nz*probe))
            if plus == minus: continue
            p = (a[0]+r[0]*t,a[1]+r[1]*t); q = (a[0]+r[0]*u,a[1]+r[1]*u)
            key = tuple(sorted(tuple(round(v,7) for v in pt) for pt in (p,q)))
            if key in emitted: continue
            emitted.add(key)
            sign = 1. if plus else -1.
            n = (nx*sign,nz*sign)
            out.append((p,q,(n[0],n[1],-dot(n,p)))); sources.append(source)
    return out, sources, dict(input_edges=len(edges), split_pieces=pieces, crossings=crossings, boundary_segments=len(out))


def check_height_separation(quads, heights, max_separation=1.0, cell_size=8.0):
    """Reject overpasses: this 2D boundary union cannot merge separate decks.

    Only triangle pairs with a positive plan-overlap area count. Merely touching
    or overlapping bounding boxes are not enough to reject neighbouring bends.
    """
    n=len(quads); bins=collections.defaultdict(list)
    for i,q in enumerate(quads):
        for x in range(math.floor(min(p[0] for p in q)/cell_size),math.floor(max(p[0] for p in q)/cell_size)+1):
            for z in range(math.floor(min(p[1] for p in q)/cell_size),math.floor(max(p[1] for p in q)/cell_size)+1):
                bins[x,z].append(i)
    def overlap(a,b):
        for tr in (a,b):
            area=sum(tr[k][0]*tr[(k+1)%3][1]-tr[(k+1)%3][0]*tr[k][1] for k in range(3))
            if abs(area)<1e-9:return False
            for p,q in zip(tr,tr[1:]+tr[:1]):
                nx,nz=p[1]-q[1],q[0]-p[0];ln=math.hypot(nx,nz)
                if ln<1e-9:continue
                da=[(nx*v[0]+nz*v[1])/ln for v in a];db=[(nx*v[0]+nz*v[1])/ln for v in b]
                if min(max(da),max(db))-max(min(da),min(db))<=1e-6:return False
        return True
    seen=set();checked=0
    for bucket in bins.values():
        for k,i in enumerate(bucket):
            for j in bucket[k+1:]:
                key=(min(i,j),max(i,j))
                if key in seen:continue
                seen.add(key)
                hi=(heights[i]+heights[(i+1)%n])/2;hj=(heights[j]+heights[(j+1)%n])/2
                if abs(hi-hj)<=max_separation:continue
                checked+=1;a=quads[i];b=quads[j]
                if any(overlap(x,y) for x in ((a[0],a[1],a[2]),(a[0],a[2],a[3])) for y in ((b[0],b[1],b[2]),(b[0],b[2],b[3]))):
                    raise ValueError('height-separated road overlap: slices %d/%d differ %.3f m; 2D footprint union is unsafe' % (i,j,abs(hi-hj)))
    return dict(height_separated_pairs_checked=checked, overlapping_decks=0, rejection_threshold_m=max_separation)
