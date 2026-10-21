from pathlib import Path
import sys,os,math,ast,json
os.environ.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1')
C=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(C),str(C/'rtbake')]
import numpy as np
from canopy_shadow import perforation_mask,project_uv
import build_classic as BC,rays
for f in [C/'build_classic.py',C/'import_classic.py',C/'rtbake/rt_bake_game5.py',C/'rtbake/canopy_shadow.py',C.parent/'stack.py']:
    compile(f.read_text(),str(f),'exec')
grass='tex_s1_x0384_y0768_64x64_c104_t';tree='fixture_tree_t'
BC.LIGHT_K=.01;BC.LIGHT_ENV=(.41,1,(0,2**-.5,-2**-.5));BC.BUMP={};BC.SMOOTH_N={};BC.FLAT_LIT=set();BC.LM_CUTOUTS=set();BC.LM_TERRAIN_CUTOUTS=set();BC.LM_TABLE=None;BC.BAKE_COLLECT=None;BC.BAKE_TABLE=None
pts=[(0.,0.,0.),(0.,0.,2.),(2.,0.,2.),(2.,0.,0.)];uv=[(0.,0.),(0.,1.),(1.,1.),(1.,0.)]
faces=[(grass,'test',pts,uv),(tree,'test',[(x+4,y,z) for x,y,z in pts],uv)]
BC.LM_COLLECT=[];before=BC._faces_to_mesh_numpy(faces,'tile',True)[0];assert BC.LM_COLLECT[0][3].tolist()==[True,True]
BC.LM_TERRAIN_CUTOUTS={grass};BC.LM_COLLECT=[];after=BC._faces_to_mesh_numpy(faces,'tile',True)[0]
assert BC.LM_COLLECT[0][3].tolist()==[False,True]
assert before['p'].tobytes()==after['p'].tobytes() and before['uv0'].tobytes()==after['uv0'].tobytes()
# Exercise the actual closed-shell ray caster, not just the mask histogram.
module=ast.parse((C/'rtbake/rt_bake_game5.py').read_text());ball=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='ball')
ns={'math':math,'nrm':lambda v: math.sqrt(sum(x*x for x in v))};exec(compile(ast.Module(body=[ball],type_ignores=[]),'ball_fixture','exec'),ns)
sun=np.array([0.,2**-.5,-2**-.5]);centre=(0.,4.,0.)
T=np.array(ns['ball'](centre,2.4,2.0));mask=perforation_mask();assert mask==perforation_mask()
opening=sum(mask[2])/len(mask[2]);assert .25<opening<.50,opening
uvs=np.array(project_uv(T,centre,sun)).reshape(-1,3,2)
assert np.allclose(uvs,np.array(project_uv(T+sun*10,centre,sun)).reshape(-1,3,2),rtol=0,atol=1e-12)
grid=np.linspace(-4,4,161);X,Z=np.meshgrid(grid,grid+4);O=np.stack([X.ravel(),np.full(X.size,.02),Z.ravel()],axis=1);D=np.broadcast_to(sun,O.shape)
sc=rays.Scene(T);closed=sc.cast(O,D,30)[0]>=0
sc.masks(np.zeros(len(T),np.int32),uvs,[np.frombuffer(mask[2],dtype=np.uint8).reshape(mask[:2])]);perforated=sc.cast(O,D,30)[0]>=0
assert np.all(~perforated|closed)
gaps=float(np.mean(~perforated[closed]));assert .18<gaps<.55,gaps
# The dapple pattern must contain coherent light patches at usable map scale.
A=perforated.reshape(X.shape);B=closed.reshape(X.shape);interior=(~A)&B
coherent=int(np.sum(interior[:-2,:-2]&interior[2:,:-2]&interior[:-2,2:]&interior[2:,2:]));assert coherent>50,coherent
out={'grass_receives_lightmap':True,'tree_remains_flat_lit':True,'positions_and_uv0_identical':True,'mask_open_fraction':opening,'closed_canopy_rays':int(closed.sum()),'rays_through_canopy':int(np.sum(closed&~perforated)),'through_fraction':gaps,'coherent_10cm_light_patches':coherent,'front_back_openings_aligned':True}
print(json.dumps(out,indent=2));Path(os.environ['TEMP'],'sr3-dappled-tests.json').write_text(json.dumps(out,indent=2))
