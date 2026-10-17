"""Additive NumPy-free fastside orientation, preserving face and UV records.

orient(faces, log=print, scores=None) -> (faces, info, float32 Arr scores).
Optional scores are expanded per-input-face records, useful for replaying the
decision phase independently. Legacy fastside/lightside APIs remain unchanged.
Finite xyz polygons with at least three corners and rounded coordinates below
2**20 are supported. Unsupported inputs raise ValueError before native reads.
"""
import ctypes
import math
from array import array

from npyio import Arr
from fastround import _buffer
import geobuf
import sidebuf

NONE, KEEP, TURN, BOTH, ENC = range(5)


def _scene(faces, X, off, cut, active):
    """First four corners, opaque blockers and the same floor as fastside."""
    vb=bytearray(); fi=array('q'); ab=bytearray(); keep=[]; low=float('inf')
    xv=X.view(); raw=memoryview(X.buf)
    for i,fc in enumerate(faces):
        start=off[i]; count=min(off[i+1]-start,4); v0=len(vb)//24
        vb.extend(raw[24*start:24*(start+count)])
        for j in range(start,start+count): low=min(low,xv[3*j+1])
        if not cut[i]:
            fi.extend((v0,v0+1,v0+2,v0+3 if count==4 else v0+2))
            ab.append(active[i]);keep.append(i)
    k=len(vb)//24; low-=5.0
    floor=array('d',(-5000.,low,-5000.,5000.,low,-5000.,5000.,low,5000.,-5000.,low,5000.))
    vb.extend(floor.tobytes());fi.extend((k,k+1,k+2,k+3));ab.append(0)
    r=sidebuf.scores(Arr('<f8',(k+4,3),vb),Arr('<i8',(len(ab),4),fi.tobytes()),Arr('|b1',(len(ab),),ab))
    sc=Arr('<f4',(len(faces),4));src=memoryview(r.buf)
    for j,i in enumerate(keep): sc.buf[16*i:16*i+16]=src[16*j:16*j+16]
    return sc


def orient(faces, log=print, *, scores=None, open_share=3/32., free_min=1., free_ratio=2.5, sure_ratio=4.):
    """Orient without changing inputs; returned scores always own their storage."""
    n=len(faces)
    if not n: raise ValueError('sideorient: at least one polygon required')
    X,O,lens=geobuf.pack(faces);off=O.view();lv=lens.view()
    if min(lv)<3: raise ValueError('sideorient: polygons need at least three corners')
    L=geobuf._native();P=ctypes.c_void_p;I=ctypes.c_longlong
    L.fg_side_geometry.argtypes=[P,P,I,P,P,P];L.fg_side_geometry.restype=ctypes.c_int
    geom=Arr('<f8',(n,8));keys=Arr('<i8',X.shape);ties=Arr('|u1',X.shape)
    if L.fg_side_geometry(X.ptr(),O.ptr(),n,geom.ptr(),keys.ptr(),ties.ptr()):
        raise ValueError('sideorient: nonfinite or out-of-range coordinates')
    kv=keys.view();tv=ties.view();gv=geom.view()
    # At half-centimetre ties, round the ORIGINAL scalar: NumPy and Python
    # float objects intentionally have different decimal-rounding semantics.
    for i,fc in enumerate(faces):
        for j,p in enumerate(fc[2]):
            base=3*(off[i]+j)
            for a in range(3):
                if tv[base+a]: kv[base+a]=round(float(round(p[a],2))*100.)
    vertex={};vid=[];bias=1<<20
    for j in range(X.shape[0]):
        a,b,c=kv[3*j:3*j+3]
        if max(abs(a),abs(b),abs(c))>=bias: raise ValueError('sideorient: rounded coordinates out of range')
        key=((a+bias)<<42)|((b+bias)<<21)|(c+bias)
        vid.append(vertex.setdefault(key,len(vertex)))
    nv=len(vertex);del vertex,keys,ties
    cut=[str(fc[0]).split('|')[0].endswith('_t') for fc in faces]
    active=[not cut[i] and fc[1]!='sea' and not str(fc[1]).startswith('gate_') for i,fc in enumerate(faces)]
    if scores is None: sc=_scene(faces,X,off,cut,active)
    else:
        src=_buffer(scores,'<f4',(4,),'scores')
        if src.shape!=(n,4): raise ValueError('sideorient: score count differs from faces')
        if not all(math.isfinite(v) for v in src.view()): raise ValueError('sideorient: scores must be finite')
        sc=Arr('<f4',src.shape,bytearray(src.buf))
    sv=sc.view();st=bytearray(n);sure=bytearray(n)
    how=dict.fromkeys(('sky','lying, looks up','few rays','free path'),0)
    for i in range(n):
        if not active[i]: continue
        ea,eb,fa,fb=sv[4*i:4*i+4];a=ea>=open_share;b=eb>=open_share
        if a and b: st[i]=BOTH;how['sky']+=1
        elif a or b:
            st[i]=KEEP if a else TURN;how['sky']+=1
            sure[i]=max(ea,eb)>=2*open_share and max(ea,eb)>=sure_ratio*min(ea,eb)
        elif abs(gv[8*i])>.5*gv[8*i+1]:
            st[i]=KEEP if gv[8*i]>0 else TURN;sure[i]=1;how['lying, looks up']+=1
        elif ea!=eb: st[i]=KEEP if ea>eb else TURN;how['few rays']+=1
        elif max(fa,fb)>=free_min and max(fa,fb)>=free_ratio*min(fa,fb):
            st[i]=KEEP if fa>fb else TURN;how['free path']+=1
        else: st[i]=ENC
    fwd=[];bwd=[]
    for i in range(n):
        p=vid[off[i]:off[i+1]];q=p[1:]+p[:1]
        fwd.append(tuple(a*nv+b for a,b in zip(p,q)));bwd.append(tuple(b*nv+a for a,b in zip(p,q)))
    nfol=0
    for rnd in range(6):
        enclosed=[i for i,s in enumerate(st) if s==ENC]
        if not enclosed: break
        edges=set()
        for i,s in enumerate(st):
            if s==KEEP: edges.update(fwd[i])
            elif s==TURN: edges.update(bwd[i])
        changed=0
        for i in enclosed:
            same=sum(e in edges for e in fwd[i]);opp=sum(e in edges for e in bwd[i])
            if same or opp: st[i]=TURN if same>opp else KEEP;changed+=1
        nfol+=changed
        if not changed: break
    del fwd,bwd
    ii=[i for i,s in enumerate(st) if s and gv[8*i+1]>=1e-9];nagree=0
    if ii:
        nodes={};items=array('q');ns=array('q');planes={}
        for pos,i in enumerate(ii):
            a,b,c,d=gv[8*i+2:8*i+6];pk=(round(a,1),round(b,1),round(c,1),round(d))
            plane=planes.setdefault(pk,len(planes))
            for v in vid[off[i]:off[i+1]]:
                node=nodes.setdefault(plane*nv+v,len(nodes));items.append(pos);ns.append(node)
        label=Arr('<i8',(len(ii),));L.fg_components.argtypes=[I,P,P,I,I,P];L.fg_components.restype=ctypes.c_int
        if L.fg_components(len(ii),items.buffer_info()[0],ns.buffer_info()[0],len(items),len(nodes),label.ptr()):
            raise MemoryError('sideorient: wall components allocation failed')
        lab=label.view();size=[0]*len(ii);vote=[0.]*len(ii)
        for pos,i in enumerate(ii):
            k=lab[pos];size[k]+=1
            if sure[i] and st[i] in (KEEP,TURN): vote[k]+=(gv[8*i+6]*(1. if st[i]==KEEP else -1.))*gv[8*i+7]
        for pos,i in enumerate(ii):
            k=lab[pos]
            if size[k]>=2 and vote[k]!=0.:
                want=KEEP if (gv[8*i+6]>0)==(vote[k]>0) else TURN
                nagree+=st[i]!=want or not sure[i];st[i]=want;sure[i]=1
    out=[];counts=[0]*5
    for i,fc in enumerate(faces):
        s=st[i];counts[s]+=1
        if s==NONE: out.append(fc);continue
        mat,sec,p,uv=fc;k4=str(mat).split('|')[0]+'|4'
        m=mat if sure[i] and s in (KEEP,TURN) else k4
        reverse=s==TURN or (s==ENC and gv[8*i]<0)
        out.append((m,sec,list(p)[::-1],list(uv)[::-1]) if reverse else (m,sec,p,uv))
    nact=sum(active);nsure=sum(sure)
    info=dict(tested=nact,seen_from_winding_side=counts[KEEP],turned_round=counts[TURN],seen_from_both_sides=counts[BOTH],enclosed_left=counts[ENC],enclosed_set_by_their_neighbours=nfol,decided_by=how,set_by_the_wall_they_belong_to=nagree,sure=nsure,not_sure_lit_as_their_brighter_side=nact-nsure)
    log('       which side is seen (ray casting, 32 rays a side): %s'%info)
    return out,info,sc
