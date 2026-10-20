"""Build a self-contained, local WebGL POM family review; never installs game files."""
from pathlib import Path
import sys,json,re,csv,collections,io,base64,hashlib
import numpy as np
from PIL import Image
ROOT=Path(r"F:\Jogos\Ultimate Race Lab")
sys.path[:0]=[str(ROOT/'source/standalone'),str(ROOT/'source/tools/import/core')]
import sbfw,pom_maps as pm,reviewed_relief as reviewed,relief_normalization as rn,surface_relief as sr
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
family=lambda n:re.sub(r'_c[0-9A-Fa-f]+(?:_t)?(?:_dk)?$','',Path(n).stem)
def png_uri(im):
 b=io.BytesIO();im.save(b,format='PNG');return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
def main():
 out=ROOT/'scratchpad/pom-depth-tuner-20261020';out.mkdir(exist_ok=True)
 hd=ROOT/'content/classic/courses/src/course1_mountain/textures_hd'
 track=ROOT/'game/Rally/Main_release/track1/Desert4/desert4_master_gfx_xdata.sbf'
 report=json.loads((ROOT/'work/research/mountain-v19-r4b-20261020/pom-stage-report.json').read_text())
 assert sha(track)==report['staged'][track.name],'Installed build changed; refresh the coverage report'
 by=sbfw.read_sbf(str(track)).byid();labels={x['tile']:x['class'] for x in csv.DictReader((ROOT/'scratchpad/import/retex/tile_labels.csv').open())}
 known={n:v for v in report['textures'].values() for n in v['aliases']}
 old=json.loads((ROOT/'scratchpad/pom-20261019/manifest.json').read_text());maps={x['file']:x for x in old['files']}
 heads={x['id']:x['head'] for x in json.loads((ROOT/'scratchpad/resolution-3x-20261019/facade-plan.json').read_text())}
 for x in old['files']:heads.setdefault(family(x['head']),x['head'])
 families=collections.defaultdict(list)
 for p in sorted(hd.glob('*.png')):families[family(p.name)].append(p)
 pm.PROFILES.update(roof=dict(depth=.003,mode='wrap',micro=.025),grass=dict(depth=.0012,mode='wrap',micro=.025),ivy=dict(depth=.002,mode='wrap',micro=.02),water=dict(depth=.0015,mode='wrap',micro=.015))
 groups={'facade':'Facades','asphalt':'Asphalt','wall':'Walls & stone curbs','rock':'Rock','grass':'Grass','roof':'Roofs','dirt':'Dirt','cobbles':'Ground / cobbles','water':'Water','ivy':'Ivy','fence':'Fences'}
 rows=[]
 for fam,files in families.items():
  head=next((p for p in files if p.name==heads.get(fam)),files[0]);name=head.stem
  cls=labels.get(name,'flat');kind='facade' if cls in pm.FACADES else cls
  if name in known:kind=known[name]['kind']
  if fam==reviewed.CASTLE:kind='facade'
  if name=='tex_sea_blue_64x64_c1DF':kind='water'
  if fam in [reviewed.CURB,'tex_s1_x0128_y0768_128x64'] or kind=='stone_wall':kind='wall'
  im=Image.open(head).convert('RGBA');rgba=np.array(im);H,W=rgba.shape[:2]
  default=1.0 if kind in ['facade','wall','asphalt'] else 4.0
  enabled=False;candidate=False;base=0.0;status='Excluded / no relief map';mode='reflect';note='Excluded from POM. No depth map is invented for this preview.'
  packed=np.zeros((H,W,4),np.uint8);packed[:,:,:3]=(128,128,255);packed[:,:,3]=255
  if reviewed.supported(name):
   h=reviewed.height(name,rgba);base=reviewed.depth(name);mode='wrap' if fam==reviewed.CURB else 'reflect'
   packed=np.dstack([pm.normal(h,base,mode),np.uint8(np.rint(h*255))]);enabled=True;candidate=True
   status='New candidate — not installed';note='Reviewed structure, with transparent edges anchored.' if name in reviewed.CUTOUTS else 'Traced stone faces and recessed joints; paint/grain stays flat. Not installed.'
  elif name in known:
   v=known[name];packed=np.array(Image.open(io.BytesIO(b'DDS '+by[v['normal_id']].data[48:])).convert('RGBA'));base=v['depth_uv'];enabled=True;status='Installed packed relief map';mode=pm.PROFILES.get(v['kind'],{}).get('mode','wrap');note='Decoded from the installed game. Preview lighting is an approximation.'
  elif kind in pm.PROFILES and np.all(rgba[:,:,3]>=254):
   if kind=='facade':h=pm.shape_height(rgba[:,:,:3],kind,name)
   elif head.name in maps:
    h=np.array(Image.open(ROOT/'scratchpad/pom-20261019/height'/head.name),np.float32)/65535
   else:h=pm.shape_height(rgba[:,:,:3],kind,name)
   base=pm.PROFILES[kind]['depth'];mode=pm.PROFILES[kind]['mode'];packed=np.dstack([pm.normal(h,base,mode),np.uint8(np.rint(h*255))]);enabled=True;status='Source-family relief';note='Source-space map. In-game crops/composites can differ; this is a family tuning preview.'
  if kind=='asphalt':note+=' Skid marks and worn bands contribute no independent height. Original lane-paint relief is preserved within reviewed marking regions; clean asphalt grain remains underneath.'
  normalization=None
  if enabled:
   raw_height=packed[:,:,3].astype(np.float32)/255
   # Asphalt has extremely little signal. Recover its unquantized source height
   # rather than expanding the handful of BC3/8-bit levels into visible steps.
   if kind=='asphalt':
    raw_height=pm.shape_height(rgba[:,:,:3],kind,name)
   raw_height=sr.refine(name,rgba,raw_height)
   if fam in sr.REGIONS:note+=' Masonry joints included only in reviewed wall regions; openings and trim protected.'
   if fam==sr.LIBRARY:note+=' Awning has a deeper sloped canopy and projecting scalloped edge.'
   coverage=np.array(im.resize((raw_height.shape[1],raw_height.shape[0]),Image.Resampling.NEAREST))[:,:,3]
   h,normalization=rn.normalize(raw_height,coverage,kind,base)
   normalization['old_height_sha256']=hashlib.sha256(packed.tobytes()).hexdigest()
   base=rn.BASE_DEPTH
   packed=np.dstack([pm.normal(h,base,mode),np.uint8(np.rint(h*255))])
   masters=out/'normalized-height';masters.mkdir(exist_ok=True)
   Image.fromarray(np.uint16(np.rint(h*65535))).save(masters/(fam+'.png'))
   maps_out=out/'normalized-packed';maps_out.mkdir(exist_ok=True)
   Image.fromarray(packed).save(maps_out/(fam+'.png'))
   status='Normalized preview — not installed'
   note+=' Common depth calibration; normals regenerated from the calibrated height. Not installed.'
  rows.append(dict(normalization=normalization,id=fam,name=head.name,kind=kind,group=groups.get(kind,'Excluded / flat surfaces'),members=[p.name for p in files],source_hashes={p.name:sha(p) for p in files},head_sha256=sha(head),width=W,height=H,base_depth=base,default=default,enabled=enabled,candidate=candidate,status=status,note=note,repeat=mode=='wrap',albedo=png_uri(im),packed=png_uri(Image.fromarray(packed)),height_sha256=hashlib.sha256(packed.tobytes()).hexdigest()))
 order=['Facades','Walls & stone curbs','Asphalt','Rock','Grass','Ground / cobbles','Dirt','Roofs','Water','Ivy','Fences','Excluded / flat surfaces']
 rows.sort(key=lambda x:(order.index(x['group']),x['id']))
 manifest=dict(version=2,normalization_version=rn.VERSION,build='mountain-v19-r4b-20261020',main_sha256=sha(track),items=rows)
 template=(Path(__file__).with_name('relief_tuner.html')).read_text(encoding='utf-8')
 (out/'index.html').write_text(template.replace('__INVENTORY__',json.dumps(manifest).replace('</','<\/')),encoding='utf-8')
 compact={**manifest,'items':[{k:v for k,v in x.items() if k not in ['albedo','packed']} for x in rows]}
 (out/'inventory.json').write_text(json.dumps(compact,indent=2))
 print(json.dumps(dict(page=str(out/'index.html'),families=len(rows),enabled=sum(x['enabled'] for x in rows),candidates=sum(x['candidate'] for x in rows),size_MiB=(out/'index.html').stat().st_size/1048576),indent=2))
if __name__=='__main__':main()
