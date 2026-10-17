"""Additive NumPy-free backdrop lids on ordinary float64 face records."""
import collections
import math
import re
import fillbuf
import filltex
import geobuf
from npexact import ddot,pwsum


def _round(v,scale):return float(round(float(v)*scale))/scale


def chains(edges,tol=.05):
    """Join edges in the legacy adjacency/set traversal order."""
    if not math.isfinite(tol) or tol<=0:raise ValueError('fillisland: invalid tolerance')
    def key(p):
        out=[]
        for v in p:
            v=round(float(v)/tol)
            out.append(v if -(1<<31)<=v<(1<<31) else -(1<<31))
        return tuple(out)
    adj=collections.defaultdict(list)
    for a,b in edges:adj[key(a)].append((key(b),b));adj[key(b)].append((key(a),a))
    pos={}
    for a,b in edges:pos[key(a)]=a;pos[key(b)]=b
    left=set(adj);out=[]
    while left:
        ends=[k for k in left if len(adj[k])==1];k=ends[0] if ends else next(iter(left));ch=[k];left.discard(k)
        while True:
            nx=[q for q,_ in adj[ch[-1]] if q in left]
            if not nx:break
            ch.append(nx[0]);left.discard(nx[0])
        closed=len(ch)>2 and any(q==ch[0] for q,_ in adj[ch[-1]])
        out.append(([tuple(map(float,pos[k])) for k in ch],closed))
    return out


def ears(Q):
    """Legacy ear clipping, returning index triples in the original order."""
    idx=list(range(len(Q)));tri=[]
    area=sum(Q[i][0]*Q[(i+1)%len(Q)][1]-Q[(i+1)%len(Q)][0]*Q[i][1] for i in range(len(Q)))
    if area<0:idx.reverse()
    def cr(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    guard=0
    while len(idx)>3 and guard<10000:
        guard+=1;n=len(idx)
        for k in range(n):
            a,b,c=idx[k-1],idx[k],idx[(k+1)%n]
            if cr(Q[a],Q[b],Q[c])<=1e-9:continue
            if any(cr(Q[a],Q[b],Q[p])>0 and cr(Q[b],Q[c],Q[p])>0 and cr(Q[c],Q[a],Q[p])>0 for p in idx if p not in (a,b,c)):continue
            tri.append((a,b,c));idx.pop(k);break
        else:break
    if len(idx)==3:tri.append(tuple(idx))
    return tri


def island_cap(faces,tile_alpha,sink=None,inset=2.,min_length=80.,min_turn=150.):
    """Return (new_faces, cap_info); tiles are explicit checked alpha buffers.

    Legacy fill1995.INFO is not changed. The internally created index is
    closed even when a tile provider raises. Input face storage is unchanged.
    """
    g=geobuf.prep(faces);nr=g.nr.view();edges=[];info={}
    for fi,(mat,sec,P,UV) in enumerate(faces):
        if not mat.endswith('_t') or len(P)!=4:continue
        P=[tuple(map(float,p)) for p in P];height=max(p[1] for p in P)-min(p[1] for p in P)
        if abs(nr[3*fi+1])>.3 or height<4.:continue
        o=sorted(range(4),key=lambda i:P[i][1]);a,b=P[o[2]],P[o[3]]
        if abs(a[1]-b[1])<.5:
            edges.append((a,b));record=(mat,height,float(UV[o[3]][1]),float(UV[o[0]][1]))
            info[tuple(_round(v,10.) for v in a)]=info[tuple(_round(v,10.) for v in b)]=record
    out=[];caps=[]
    with fillbuf.Index(faces) as ix:
        for ch,closed in chains(edges):
            L=0.
            for a,b in zip(ch,ch[1:]):
                v=[b[i]-a[i] for i in range(3)];L+=math.sqrt(ddot(v,v))
            if L<min_length or len(ch)<3:continue
            H=[(p[0],p[2]) for p in ch]
            ang=[math.atan2(b[1]-a[1],b[0]-a[0]) for a,b in zip(H,H[1:])]
            turn=abs(pwsum([(b-a+math.pi)%(2.*math.pi)-math.pi for a,b in zip(ang,ang[1:])])*(180./math.pi))
            if turn<min_turn and not closed:continue
            mat,hgt,vt,vb=info[tuple(_round(v,10.) for v in ch[0])];alpha=tile_alpha(mat)
            m=re.search(r'_(\d+)x(\d+)_',mat);tw,th=map(int,m.groups()) if m else (64,64)
            rows=None
            if alpha is not None:
                alpha=filltex._image(filltex.image_buffer(alpha,True),True)
                if alpha.shape!=(th,tw):raise ValueError('fillisland: tile dimensions differ from material name')
                av=alpha.view();rows=[sum(av[r*tw:(r+1)*tw])/tw for r in range(th)]
            sk=sink
            if sk is None:
                sk=.35
                if rows is not None:
                    for i in range(46):
                        t=.9 if i==45 else i*(.9/45.)
                        if rows[math.floor((1.-(vt+(vb-vt)*t))*th)%th]>=.9:sk=t+.08;break
            y=pwsum([p[1] for p in ch])/len(ch)-sk*hgt
            # mean(axis=0) on the original two-column C-order array is sequential.
            c=[sum(p[a] for p in H)/len(H) for a in range(2)];Q=[]
            for p in H:
                d=[c[a]-p[a] for a in range(2)];ln=max(math.sqrt(d[0]*d[0]+d[1]*d[1]),1e-6)
                Q.append(tuple(p[a]+d[a]/ln*inset for a in range(2)))
            while any(abs(h-y)<.05 for q in Q[::3] for h,k in ix.heights(q[0],q[1])):y-=.1
            r0,r1=.3*th,.6*th
            if rows is not None:
                best=(0,0);s=None
                for r in range(th+1):
                    if r<th and rows[r]>.99:s=r if s is None else s
                    else:
                        if s is not None and r-s>best[1]-best[0]:best=(s,r)
                        s=None
                if best[1]-best[0]>=4:r0,r1=best[0]+1.,best[1]-1.
            lo=[min(q[a] for q in Q) for a in range(2)];ext=[max(max(q[a] for q in Q)-lo[a],1.) for a in range(2)]
            def uvf(q):return (.9*(q[0]-lo[0])/ext[0],1.-(r0+(r1-r0)*(q[1]-lo[1])/ext[1])/th)
            tris=ears(Q)
            for a,b,c_ in tris:
                T=[Q[a],Q[c_],Q[b]];p=[(q[0],y,q[1]) for q in T]
                if geobuf.prep([p],col=None).nr.view()[1]<0:T.reverse();p.reverse()
                out.append((mat,'island_cap',p,[uvf(q) for q in T]))
            caps.append(dict(points=len(ch),closed=closed,length=round(L),turn=round(turn),sink=round(sk,2),y=round(y,2),tile=mat,rows=(round(r0),round(r1)),triangles=len(tris)))
    return out,caps
