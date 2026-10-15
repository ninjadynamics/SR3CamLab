"""NumPy-free authored OBJ helpers with explicit paths and coordinate settings."""
import collections
import math
import os
import geobuf


def _read(path,rd,zs,mode,faces=(),log=print):
    if not os.path.exists(path):return []
    V=[];VT=[];out=[];mat=None;sec={'props':'props','fill':'hf','model':'hm'}[mode];centers=None
    with open(path) as src:
        for ln in src:
            if ln.startswith('v '):
                x,y,z=map(float,ln.split()[1:4]);V.append((x+rd['ox'],y,zs*z+rd['oz']))
            elif ln.startswith('vt '):VT.append(tuple(map(float,ln.split()[1:3])))
            elif ln.startswith('o '):sec=ln.split()[1]
            elif ln.startswith('usemtl'):
                mat=ln.split()[1]
                if mode=='model' and mat.startswith('@near:'):
                    x,y,z=map(float,mat[6:].split(','));q=(x+rd['ox'],y,zs*z+rd['oz'])
                    if centers is None:
                        centers=[tuple(sum(float(p[j]) for p in fc[2])/len(fc[2]) for j in range(3)) for fc in faces]
                    def distance(i):
                        if str(faces[i][0]).endswith('_t'):return 1e18
                        d=[centers[i][j]-q[j] for j in range(3)]
                        return (d[0]*d[0]+d[1]*d[1])+d[2]*d[2]
                    mat=faces[min(range(len(faces)),key=distance)][0]
            elif ln.startswith('f '):
                ix=[tuple(int(a)-1 for a in t.split('/')[:2]) for t in ln.split()[1:]]
                P=[V[a] for a,b in ix][::int(zs)];UV=[VT[b] for a,b in ix][::int(zs)]
                if mode=='props':
                    du=float(math.floor(min(u for u,v in UV)));UV=[(u-du,v) for u,v in UV]
                    normal=geobuf.prep([P],col=None).nr.view();shift=[v*.02 for v in normal]
                    P=[tuple(p[j]+shift[j] for j in range(3)) for p in P]
                out.append((mat,sec,P,UV))
    if mode=='props':
        seen=set();keep=[]
        for fc in out:
            key=tuple(sorted(tuple(float(round(v*100.))/100. for v in p) for p in fc[2]))
            if key not in seen:seen.add(key);keep.append(fc)
        return keep
    if mode=='model':log('       hand models: %d faces (%s), tiles %s'%(len(out),os.path.basename(path),sorted({str(fc[0])[-18:] for fc in out})))
    return out


def props(path,rd,zs=-1.):return _read(path,rd,zs,'props')


def handfill(path,rd,zs=-1.):return _read(path,rd,zs,'fill')


def handmodel(path,rd,faces,zs=-1.,log=print):return _read(path,rd,zs,'model',faces,log)


def write_handfill(path,faces,rd,zs,texdir='textures'):
    """Write the original grouped OBJ and MTL byte format; paths are explicit."""
    path=os.fspath(path);by=collections.defaultdict(list)
    for fc in faces:by[fc[1]].append(fc)
    mats=[]
    with open(path,'w',newline='\n') as fo:
        fo.write('# gap fill of the imported course: natural banks where the 1995 data has no polygon (gapfill_gen.py)\n# classic OBJ coordinates; SR3 = (x + ox, y, -z + oz). Read by fill1995.handfill.\n')
        fo.write('mtllib %s\n'%os.path.basename(path).replace('.obj','.mtl'));nv=0
        for sec in sorted(by):
            fo.write('o %s\n'%sec);cur=None
            for mat,_,P,UV in sorted(by[sec],key=lambda f:f[0]):
                if mat!=cur:fo.write('usemtl %s\n'%mat);cur=mat
                if mat not in mats:mats.append(mat)
                P=list(P)[::int(zs)];UV=list(UV)[::int(zs)]
                for (x,y,z),(u,v) in zip(P,UV):fo.write('v %.3f %.3f %.3f\nvt %.4f %.4f\n'%(x-rd['ox'],y,(z-rd['oz'])/zs,u,v))
                fo.write('f '+' '.join('%d/%d'%(nv+k+1,nv+k+1) for k in range(len(P)))+'\n');nv+=len(P)
    with open(path.replace('.obj','.mtl'),'w',newline='\n') as fm:
        for mat in sorted(mats):fm.write('newmtl %s\nKd 0.8 0.8 0.8\nmap_Kd %s/%s.png\n'%(mat,texdir,mat))
