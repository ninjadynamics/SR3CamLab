"""NumPy-free UV subdivision, retaining fastbuild's face and edge order."""
import math


def _flipped(uv):return [(float(u),1.-float(v)) for u,v in uv]


def _span(uv):return [max(u[d] for u in uv)-min(u[d] for u in uv) for d in range(2)]


def _fits(uv,maxspan):
    u=_flipped(uv);lo=[min(v[d] for v in u) for d in range(2)];sp=_span(u)
    return max((lo[d]-math.floor(lo[d]+1e-6))+sp[d] for d in range(2))<=maxspan


def uv_split(faces,maxspan=1.999):
    """Return (faces, number of initially oversized faces), ordinary floats.

    Fitting faces retain their original position/UV objects. Subdivision uses
    bilinear grids, followed by ordered triangle bisection for at most twelve
    rounds. Numeric/layout validation and allocation bounds fail explicitly;
    legacy build_classic/fastbuild entry points remain unchanged.
    """
    maxspan=float(maxspan)
    if not math.isfinite(maxspan) or maxspan<=0:raise ValueError('builduv: finite positive maxspan required')
    out=[];known=[];count=0;limit=2000000
    for mat,sec,P,UV in faces:
        if len(P)<3 or len(UV)!=len(P) or any(len(p)!=3 for p in P) or any(len(u)!=2 for u in UV):
            raise ValueError('builduv: matching xyz and UV polygons required')
        if any(not math.isfinite(float(x)) or abs(float(x))>1e12 for A in (P,UV) for row in A for x in row):
            raise ValueError('builduv: invalid coordinate')
        if _fits(UV,maxspan):out.append((mat,sec,P,UV));known.append(True);continue
        sp=_span(_flipped(UV));k=math.ceil(max(sp)/.999);count+=1
        if k*k+len(out)>limit:raise ValueError('builduv: excessive subdivision')
        if len(P)==3:P=list(P)+[P[2]];UV=list(UV)+[UV[2]]
        Pa=[tuple(map(float,p)) for p in P[:4]];Ua=[tuple(map(float,u)) for u in UV[:4]]
        def pt(A,a,b):return tuple((A[0][d]*(1-a)+A[1][d]*a)*(1-b)+(A[3][d]*(1-a)+A[2][d]*a)*b for d in range(len(A[0])))
        for i in range(k):
            for j in range(k):
                corners=((i/k,j/k),((i+1)/k,j/k),((i+1)/k,(j+1)/k),(i/k,(j+1)/k))
                out.append((mat,sec,[pt(Pa,a,b) for a,b in corners],[pt(Ua,a,b) for a,b in corners]));known.append(False)
    done=[];todo=[]
    for fc,ok in zip(out,known):
        if ok or _fits(fc[3],maxspan):done.append(fc)
        else:
            mat,sec,P,UV=fc
            for ix in (((0,1,2),(0,2,3)) if len(P)>=4 else ((0,1,2),)):
                todo.append((mat,sec,[P[i] for i in ix],[UV[i] for i in ix]))
    for depth in range(12):
        nxt=[]
        for mat,sec,P,UV in todo:
            if _fits(UV,maxspan):done.append((mat,sec,P,UV));continue
            lengths=[max(abs(float(UV[(i+1)%3][d])-float(UV[i][d])) for d in range(2)) for i in range(3)]
            a=max(range(3),key=lengths.__getitem__);b=(a+1)%3;c=(a+2)%3
            pm=tuple((float(P[a][d])+float(P[b][d]))/2 for d in range(3));um=tuple((float(UV[a][d])+float(UV[b][d]))/2 for d in range(2))
            nxt.extend(((mat,sec,[P[a],pm,P[c]],[UV[a],um,UV[c]]),(mat,sec,[pm,P[b],P[c]],[um,UV[b],UV[c]])))
            if len(done)+len(nxt)>limit:raise ValueError('builduv: excessive bisection')
        todo=nxt
        if not todo:break
    return done+todo,count
