"""NumPy-free hanging-board detection, with explicit tile and index inputs."""
import collections
import math
import geobuf
import fillbuf
import filltex


def hanging_boards(faces,tile_alpha,gap=1.,ix=None,sunk=1.5):
    """Return ([(face,i,j), ...], tile_counts), without modifying faces.

    tile_alpha(mat) supplies an alpha Arr (or buffer-protocol bool image), or
    None when missing. An optional index supplies heights/uprights. An index
    created here is always closed, including when a tile callback fails.
    """
    own=not ix
    if own:ix=fillbuf.Index(faces)
    try:
        ids=[i for i,fc in enumerate(faces) if fc[0].endswith('_t') and len(fc[2])==4]
        geo=geobuf.prep([faces[i] for i in ids]);nr=geo.nr.view();xyz=geo.X.view()
        out=[];tiles=collections.Counter()
        for pos,fi in enumerate(ids):
            if abs(nr[3*pos+1])>.3:continue
            mat,sec,P,UV=faces[fi];al=tile_alpha(mat)
            if al is None:continue
            al=filltex._image(filltex.image_buffer(al,True),True);th,tw=al.shape
            p=[tuple(xyz[12*pos+3*j:12*pos+3*j+3]) for j in range(4)]
            i=min(range(4),key=lambda k:p[k][1]+p[(k+1)%4][1]);j=(i+1)%4
            d=[p[i][a]-p[j][a] for a in range(3)]
            length=math.sqrt((d[0]*d[0]+d[2]*d[2])+d[1]*d[1])
            if abs(d[1])>.5*length+.05:continue
            if len(UV)!=4 or any(len(q)!=2 for q in UV):raise ValueError('fillboards: expected four UV pairs')
            uv=[tuple(map(float,q)) for q in UV]
            up=uv[(j+1)%4][1]-uv[j][1]
            if abs(up)<1e-6:continue
            v=uv[i][1]+(1. if up>0 else -1.)*1./th
            row=math.floor((1.-v)*th)%th
            frac,runs=filltex.stem_runs(al,row,uv[i][0],uv[j][0])
            if frac==0 or frac>.5 or runs>2:continue
            base=min(p[i][1],p[j][1]);held=False
            for t in (.25,.5,.75):
                q=[p[i][a]+(p[j][a]-p[i][a])*t for a in range(3)]
                if any(base-gap<=y<=q[1]+sunk for y,k in ix.heights(q[0],q[2]) if k!=fi):held=True;break
                if any(y0<base-.05 and y1>base-gap for y0,y1,k,cut in ix.uprights(q[0],q[2]) if k!=fi):held=True;break
            if not held:out.append((fi,i,j));tiles[mat]+=1
        return out,dict(tiles)
    finally:
        if own:ix.close()
