"""Repair Daytona's false banked-road width pinches without rebuilding its scenery.

The 1994 visible asphalt and coprocessor collision use different triangulations
of twisted quads. The former 30 cm edge filter falsely ended drivable support.
Re-evaluate widths with the reviewed recipe; retain every interior vertex record,
add support at the INSTALLED visible surface, and rebuild only road/blob/boundary.
Never installs. SOURCE and DESTINATION must differ. Mountain is not accepted.
"""
import argparse,collections,hashlib,json,math,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'source/tools/import/core'))
import bsp,bsp_build,build_classic as BC,build_more as BM,build_testtrack as BT,meshgen,sbfw,scene11,trackdeform as TD


def sha(data):return hashlib.sha256(data).hexdigest()


def installed_ground(f):
    by=f.byid();sc=scene11.parse11(by[f.chunks[-1].u32(4)]);tris=[]
    for mid in sc.nodes[0].meshes:
        m=meshgen.parse_mesh(by[mid]);mat=by.get(m['groups'][0][4])
        if mat is None or len(mat.data)!=1848 or struct.unpack_from('<I',mat.data,meshgen.ATEST_CELL)[0] or struct.unpack_from('<I',mat.data,meshgen.ABLEND_CELL)[0]:continue
        p=m['verts']['p'][:,:3].astype(float);ix=m['idx'].astype(np.int64)
        if len(ix)<3:continue
        t=np.stack([p[ix[:-2]],p[ix[1:-1]],p[ix[2:]]],1)
        ok=(ix[:-2]!=ix[1:-1])&(ix[1:-1]!=ix[2:])&(ix[:-2]!=ix[2:])
        n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);ln=np.linalg.norm(n,axis=1)
        ok&=ln>1e-9;ok&=np.abs(n[:,1])>.3*np.maximum(ln,1e-12)
        tris.extend((0,a) for a in t[ok])
    return BC.AttrField(tris)


def source_fields(root,cfg):
    folder=root/'content/classic'/cfg['export']
    BC.HI=str(folder/cfg['visual']);BC.ZS=-1
    visible=BC.visual_ground()
    col=BC.AttrField([(a,t*np.array([1,1,-1])) for a,t in BM.load_obj_tris(folder/cfg['collision']) if not (a>>23)&1])
    return col,visible


def width_profile(td,col,vis,tol,origin,cfg,right_tol=None):
    center,lat,lo,hi=TD.road_frame(td);p=center.copy();p[:,0]-=origin[0];p[:,2]-=origin[1]
    raw=np.array([col.at2(q[0],q[2],q[1])[0] for q in p]);yc=np.convolve(np.r_[raw[-3:],raw,raw[:3]],np.ones(7)/7,'valid')
    BC.EDGE_VISUAL=tol;BC.EDGE_VISUAL_RIGHT=right_tol
    wl,wr=BC.classic_edges(col,p,lat,yc,int(cfg['max_half_width']),vis)
    if cfg.get('max_left') is not None:wl=np.minimum(wl,float(cfg['max_left']))
    if cfg.get('max_right') is not None:wr=np.minimum(wr,float(cfg['max_right']))
    return wl,wr


def repair(source,destination,report_path):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if source==destination:raise ValueError('Use a separate staging destination')
    original_bytes=source.read_bytes()
    cfg=json.loads((Path(__file__).parent/'courses/daytona_1.json').read_text())
    f=sbfw.read_sbf(str(source));by=f.byid();root=f.chunks[-1];rid,bid=root.u32(0xc),root.u32(0x34);td=TD.parse_td(by[rid]);blob=td.blob_id
    if td.n!=1548:raise ValueError('Not the accepted Daytona 1548-slice road')
    before={c.id:(c.kind,c.data,c.fix[:],c.ref[:],c.z) for c in f.chunks}
    center,lat,oldlo,oldhi=TD.road_frame(td)
    xf=json.loads((ROOT/'scratchpad/import/tmp/classic_xform_daytona_1.json').read_text());origin=(xf['ox'],xf['oz'])
    col,vis=source_fields(ROOT,cfg)
    oldwl,oldwr=width_profile(td,col,vis,.3,origin,cfg)
    error=max(float(np.max(np.abs(oldwl+oldlo))),float(np.max(np.abs(oldwr-oldhi))))
    if error>1e-3:raise ValueError('Source geometry no longer reproduces accepted road widths: %g m'%error)
    wl,wr=width_profile(td,col,vis,float(cfg['edge_visual']),origin,cfg,right_tol=cfg.get('edge_visual_right'))
    if np.any(wl<oldwl-1e-6) or np.any(wr<oldwr-1e-6):raise ValueError('Repair must not remove existing supported road')
    off=-np.ceil(wl-1e-6).astype(int);rc=np.ceil(wr-1e-6).astype(int)
    if max(np.max(np.abs(off-np.roll(off,1))),np.max(np.abs(rc-np.roll(rc,1))))>1:raise ValueError('Road edge column jumps exceed engine layout')
    model=TD.td_to_model(td);hf=installed_ground(f)
    common_b14=collections.Counter(bytes(v['b14']) for row in td.verts[1:td.n+1] for v in row[:-1]).most_common(1)[0][0]
    changed_rows=[];new_verts=[];interior_kept=0;edge_updated=0
    for i in range(td.n):
        old=td.verts[i+1];cols=TD.columns(td,i+1);oldmap={c:k for k,c in enumerate(cols)};p=(i-1)%td.n
        c0=min(int(off[i]),int(off[p]));c1=max(int(rc[i]),int(rc[p]));newcols=list(range(c0,c1+1));v=np.zeros(len(newcols),TD.VDT)
        for k,c in enumerate(newcols):
            x=float(np.clip(c,-wl[i],wr[i]));target=center[i]+lat[i]*x
            oldk=oldmap.get(c);same=oldk is not None and np.linalg.norm((old[oldk]['pos']-target)[[0,2]])<5e-5
            if same:
                v[k]=old[oldk]
                if oldlo[i]+.001<x<oldhi[i]-.001:interior_kept+=1
            else:
                # New cells keep the adjacent road's physical surface pair. Heights
                # are sampled from the existing rendered mesh, not extrapolated.
                oldk=max(0,min(len(old)-2,c-cols[0]));v[k]=old[oldk]
                local=target.copy();local[0]-=origin[0];local[2]-=origin[1]
                hcol=col.at2(local[0],local[2],target[1])
                if hcol is None:raise ValueError('No original collision support at new vertex')
                hv=hf.at2(float(target[0]),float(target[2]),float(hcol[0]))
                if hv is None or abs(hv[0]-hcol[0])>.6:raise ValueError('New support does not match installed visible surface')
                target[1]=hv[0];v[k]['pos']=target
                new_verts.append({'slice':i+1,'column':c,'position':[float(q) for q in v[k]['pos']],'visible_y':float(hv[0]),'source_collision_y':float(hcol[0])})
                edge_updated+=oldmap.get(c) is not None
            # Reuse the exact existing edge position for collapsed duplicates.
            # Sampling it again could produce two Y values at the same X/Z and
            # turn a zero-area edge fan into a thin vertical collision triangle.
            if abs(x-oldlo[i])<1e-4:v[k]['pos']=old[0]['pos']
            elif abs(x-oldhi[i])<1e-4:v[k]['pos']=old[-1]['pos']
            if not same:
                new_verts[-1]['sampled_position']=new_verts[-1]['position']
                new_verts[-1]['position']=[float(q) for q in v[k]['pos']]
                new_verts[-1]['retained_existing_edge']=bool(abs(x-oldlo[i])<1e-4 or abs(x-oldhi[i])<1e-4)
            if k<len(v)-1 and bytes(v[k]['b14'])==bytes(4):v[k]['b14']=np.frombuffer(common_b14,np.uint8)
        sl=model['slices'][i+1];sl.update(A=int(rc[i]-off[i]),off=int(off[i]),b6e=int(off[i]-off[p]),b6f=int(off[i]>off[p]),B=len(v),verts=v)
        # Every existing strictly interior record, including column zero, stays exact.
        for oldk,c in enumerate(cols):
            pos=old[oldk]['pos'].astype(float);distance=float((pos-center[i])@lat[i])
            if oldlo[i]+.001<distance<oldhi[i]-.001:
                assert old[oldk].tobytes()==v[newcols.index(c)].tobytes(),(i+1,c)
        assert old[cols.index(0)].tobytes()==v[newcols.index(0)].tobytes()
        if old.tobytes()!=v.tobytes():changed_rows.append(i+1)
    BT.road_width_check(model)
    page_changes=[]
    for index,page in enumerate(model['pages']):
        x0,x1=-page[2]/page[4],(1-page[2])/page[4]
        z0,z1=-page[3]/page[5],(1-page[3])/page[5]
        points=[]
        for i,s in enumerate(model['slices'][1:],1):
            # Include both adjacent batches; all page interpretations used by
            # the loader then cover the boundary row and its next-row vertices.
            uses={model['rec11'][(i-1)//4][10],model['rec11'][i//4][10]}
            if index in uses:points.extend(s['verts']['pos'].tolist())
        if not points:continue
        p=np.array(points);nx0=min(x0,float(p[:,0].min())-2);nx1=max(x1,float(p[:,0].max())+2)
        nz0=min(z0,float(p[:,2].min())-2);nz1=max(z1,float(p[:,2].max())+2)
        if max(abs(nx0-x0),abs(nx1-x1),abs(nz0-z0),abs(nz1-z1))<1e-6:continue
        # Moving a mapping over an authored shadow would change its placement.
        # Daytona's original pages are uniform; verify this rather than assume.
        from PIL import Image
        import io
        for tex in page[:2]:
            raw=f.byid()[tex].data;at=raw.find(b'DDS ')
            if at<0:raise ValueError('Page texture has no DDS header')
            pixels=np.asarray(Image.open(io.BytesIO(raw[at:])).convert('RGBA'))
            if not np.all(pixels==pixels[0,0]):raise ValueError('Cannot resize a non-uniform authored shadow page')
        model['pages'][index]=(page[0],page[1],-nx0/(nx1-nx0),-nz0/(nz1-nz0),1/(nx1-nx0),1/(nz1-nz0))
        page_changes.append({'page':index,'old_bounds':[x0,x1,z0,z1],'new_bounds':[nx0,nx1,nz0,nz1]})
    BT.set_td(f,model)
    newtd=TD.parse_td(f.byid()[rid]);np.testing.assert_array_equal(center,TD.road_frame(newtd)[0])
    surfaces,wall,floor=BM.boundary_surfaces(f)
    rows=[(newtd.verts[i]['pos'].astype(float),int(newtd.off[i]),int(newtd.A[i])) for i in range(1,newtd.n+1)]
    stats=BM.add_walls(f,rows,surfaces,wall,floor,every=1,inset=0.,terrain=True,footprint_boundary=True)
    changed=[c.id for c in f.chunks if (c.kind,c.data,c.fix,c.ref,c.z)!=before[c.id]]
    assert set(changed)=={rid,blob,bid},[hex(x) for x in changed]
    b=bsp.parse_bsp(f.byid()[bid]);data,fix=bsp_build.serialize(*bsp_build.to_tree(b));assert data==f.byid()[bid].data and fix==f.byid()[bid].fix
    destination.parent.mkdir(parents=True,exist_ok=True);payload=sbfw.write_sbf(f,compress=True,layout='auto',level=6);destination.write_bytes(payload)
    reread=sbfw.read_sbf(str(destination)).byid()
    assert all((reread[c].kind,reread[c].data,reread[c].fix,reread[c].ref,reread[c].z)==v for c,v in before.items() if c not in changed)
    assert sha(source.read_bytes())==sha(original_bytes)
    report={'source':str(source),'output':str(destination),'source_sha256':sha(original_bytes),'output_sha256':sha(payload),'source_width_reproduction_max_error_m':error,'recipe_edge_visual_m':cfg['edge_visual'],'recipe_edge_visual_right_m':cfg.get('edge_visual_right'),'uniform_page_bounds_updated':page_changes,'changed_chunk_ids':['%08x'%c for c in changed],'unchanged_chunks':len(before)-len(changed),'interior_vertex_records_unchanged':interior_kept,'reference_line_exact':True,'route_ai_scenery_materials_textures_unchanged':True,'changed_slice_records':len(changed_rows),'extended_left_slices':int(np.sum(wl>oldwl+1e-6)),'extended_right_slices':int(np.sum(wr>oldwr+1e-6)),'max_extension_left_m':float(np.max(wl-oldwl)),'max_extension_right_m':float(np.max(wr-oldwr)),'new_or_moved_edge_vertex_records':len(new_verts),'engine_row_records_max':max(s['A']+1+s['B'] for s in model['slices'][1:]),'engine_row_records_limit':BT.ROAD_ROW_RECORDS,'max_road_quads':max(s['A'] for s in model['slices'][1:]),'stats':stats,'pass':True}
    report_path=Path(report_path);report_path.write_text(json.dumps(report,indent=2)+'\n');report_path.with_name('new-support-vertices.json').write_text(json.dumps(new_verts,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source');ap.add_argument('destination');ap.add_argument('--report',required=True);a=ap.parse_args();repair(a.source,a.destination,a.report)
