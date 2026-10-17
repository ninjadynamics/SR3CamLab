"""Additive NumPy-free trunk extensions built from the checked fill helpers."""
import collections
import re
import geobuf
import fillboards
import fillbuf
import fillroad
import filltex
from npexact import ddot


def _size(mat):
    m=re.search(r'_(\d+)x(\d+)_',mat)
    return (int(m.group(1)),int(m.group(2))) if m else (64,64)


def _key(p):
    # NumPy round(...,2) scales, rounds to even, then divides. Python's
    # round(x,2) instead rounds decimal digits directly and is not equivalent.
    return tuple(float(round(v*100.))/100. for v in p)


def extend_trunks(faces,tile_alpha,tile_rgb,depth=8.,gap=1.,floor=None,rd=None,max_depth=40.,limit=None,classes=None,labels=None):
    """Return (new_faces, trunk_info, ungrounded_indices), without mutation.

    Tile callbacks supply checked Arr/buffer-protocol images or None. Optional
    road data uses fillroad's Arr contract. With classes, labels maps material
    to its class name; the caller owns label loading. Legacy INFO is untouched.
    """
    if classes and labels is None:raise ValueError('filltrunks: classes require material labels')
    allf=list(faces)+fillroad.road_faces(rd);out=[];seen=set();shortened=0;ends=collections.Counter();ungrounded=[]
    normals=geobuf.prep(faces).nr.view()
    with fillbuf.Index(allf) as ix:
        hanging,tiles=fillboards.hanging_boards(allf,tile_alpha,gap,ix)
        for fi,i,j in hanging:
            mat,sec,P,UV=faces[fi];p=[tuple(map(float,q)) for q in P];uv=[tuple(map(float,q)) for q in UV];tw,th=_size(mat)
            key=tuple(sorted((_key(p[i]),_key(p[j]))))
            if key in seen:continue
            seen.add(key);d=depth;n=normals[3*fi:3*fi+3];mid=[(p[i][a]+p[j][a])/2. for a in range(3)];base=min(p[i][1],p[j][1])
            under=[y for y,k in ix.heights(mid[0],mid[2]) if base-max_depth<y<base];end='air'
            if under:d=base-max(under)+.3;end='ground'
            if floor is not None and base-d<=floor:d=base-floor;end='floor'
            for y0,y1,k,cut in ix.uprights(mid[0],mid[2],.05):
                if k==fi or y1>base-.01:continue
                if k>=len(faces):raise IndexError('filltrunks: upright proxy index outside source faces')
                if abs(ddot(normals[3*k:3*k+3],n))>.999:d=min(d,base-y1-.05);shortened+=1
            if d<.3:continue
            if classes and labels.get(mat) not in classes:ends['not a stem: left alone']+=1;continue
            up=uv[(j+1)%4][1]-uv[j][1];sign=1. if up>0 else -1.
            im=tile_rgb(mat)
            if im is not None and filltex.leaf_row(filltex.image_buffer(im),uv[i][1]+sign*1./th,uv[i][0],uv[j][0]):
                ends['leaves on the lowest edge (a crown, no stem): left alone']+=1;continue
            if limit is not None and (d>limit or end!='ground'):
                ends['no ground within reach: board to be removed']+=1;ungrounded.append(fi);continue
            ends[end]+=1;va=uv[i][1]+sign*1.5/th;vb=uv[i][1]+sign*.5/th;dn=(0.,d,0.)
            out.append((mat,sec,[p[j],p[i],tuple(p[i][a]-dn[a] for a in range(3)),tuple(p[j][a]-dn[a] for a in range(3))],[(uv[j][0],va),(uv[i][0],va),(uv[i][0],vb),(uv[j][0],vb)]))
    return out,dict(added=len(out),shortened=shortened,foot=dict(ends),tiles=tiles),ungrounded
