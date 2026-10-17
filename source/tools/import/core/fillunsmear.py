"""NumPy-free correction of stretched ground textures, using shared LAPACK."""
import math
import re
import nplapack
import overlay_bake as OB


def _mm(A,B):
    return [[0.+(a[0]*B[0][j]+a[1]*B[1][j]) for j in range(2)] for a in A]


def _mean(A):
    out=[0.,0.]
    for a in A:
        for j in range(2):out[j]+=a[j]
    return [v/len(A) for v in out]


def unsmear(faces,labels,origin=None,skip=(),ratio=10.,min_area=10.,classes=('rock','grass','dirt','sand','gravel')):
    """Return (faces,count) with explicit label/origin maps, no global INFO.

    Eligible polygons need 3..8 corners, the committed solver's exact domain.
    Skipped/unmodified records and modified position objects retain identity.
    Shared overlay plane helpers and nplapack stay untouched.
    """
    origin={} if origin is None else origin;out=[];count=0
    for fc in faces:
        mat,sec,P,UV=fc;m0=str(mat).split('|')[0]
        if id(fc) in skip or m0.endswith('_t') or len(P)<3 or labels.get(origin.get(m0,m0)) not in classes:
            out.append(fc);continue
        if len(P)!=len(UV) or any(len(p)!=3 for p in P) or any(len(u)!=2 for u in UV):raise ValueError('fillunsmear: invalid polygon layout')
        Pn=[tuple(map(float,p)) for p in P];U=[tuple(map(float,u)) for u in UV]
        if any(not math.isfinite(x) for A in (Pn,U) for p in A for x in p):raise ValueError('fillunsmear: finite coordinates required')
        nrm,ar=OB._newell_f(Pn)
        if ar<min_area:out.append(fc);continue
        if not nplapack.fits(len(P),3,2):raise ValueError('fillunsmear: eligible polygon exceeds exact solver domain')
        Q=OB._to2_f(Pn,OB._basis_f(Pn));X,_=nplapack.lstsq([(q[0],q[1],1.) for q in Q],U)
        M=[[X[j][i] for j in range(2)] for i in range(2)]
        match=re.search(r'_(\d+)x(\d+)_',m0);size=[int(match.group(1)),int(match.group(2))] if match else [64,64]
        if min(size)<=0:raise ValueError('fillunsmear: positive texture dimensions required')
        a,sv,bt=nplapack.svd([[v*size[i] for v in row] for i,row in enumerate(M)])
        if sv[1]>1e-9 and sv[0]/sv[1]<=ratio:out.append(fc);continue
        M2=_mm(_mm(a,[[sv[0],0.],[0.,sv[0]]]),bt);M2=[[v/size[i] for v in row] for i,row in enumerate(M2)]
        um=_mean(U);qm=_mean(Q);T=[[M2[j][i] for j in range(2)] for i in range(2)]
        delta=_mm([[q[i]-qm[i] for i in range(2)] for q in Q],T)
        out.append((mat,sec,P,[tuple(um[i]+d[i] for i in range(2)) for d in delta]));count+=1
    return out,count
