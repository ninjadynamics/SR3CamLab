"""Stage Mountain-wide material relief without touching albedo, geometry or lightmaps.
Compose scalar heights through the SAME facade/overlay UV recipes as the albedo;
recompute normals afterwards so mirrored/cropped facades have correct directions.
Existing approved rock DDS is reused byte-for-byte for its simple tile family.
"""
from pathlib import Path
import os
os.environ['SR3_FASTGEO']='0'
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import argparse,collections,csv,hashlib,io,json,re,struct,sys
import numpy as np
from PIL import Image,ImageDraw
import pom_maps as pm
import pom_dds as codec
from stage_pom import add_dependency_before_users
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/import/core'))
import sbfw,facadebake,overlay_bake
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
family=lambda n:re.sub(r'_c[0-9A-Fa-f]+(?:_t)?(?:_dk)?$','',n)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--workspace',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--base-main',type=Path);ap.add_argument('--track-dir',type=Path,help='Verified staged track folder, including its texmap.json; defaults to installed track');ap.add_argument('--fresh-facades',action='store_true');ap.add_argument('--tuning',type=Path);a=ap.parse_args()
 r=a.workspace.resolve();out=a.out.resolve();track=a.track_dir.resolve() if a.track_dir else r/'game/Rally/Main_release/track1/Desert4'
 assert (track/'texmap.json').is_file() and track.is_dir(),'Track metadata required'
 assert r in out.parents and 'scratchpad' in out.parts and not out.exists(),'New scratchpad stage required'
 out.mkdir(parents=True);(out/'maps').mkdir();(out/'review').mkdir()
 hd=r/'content/classic/courses/src/course1_mountain/textures_hd';sd=hd.with_name('textures')
 tune={};gains={};height_dir=None;excluded_variants=set()
 if a.tuning:
  from pom_native_config import load as load_tuning
  config=load_tuning(a.tuning);gains=config['families']
  excluded_variants=set(config['excluded_variants'])
  export=json.loads((r/config['review_export']).read_text());height_dir=r/config['height_directory']
  assert sha(track/'desert4_master_gfx_xdata.sbf')==export['main_sha256']
  for row in export['families']:
   for name,h in row['source_hashes'].items():assert sha(hd/name)==h,('Changed source',name)
   if row['eligible']:tune[row['id']]=row
  assert set(gains)==set(tune)

 research=r/'scratchpad/pom-20261019';manifest=json.loads((research/'manifest.json').read_text())
 mr={Path(x['file']).stem:x for x in manifest['files']}
 assert all(sha(x['source'])==x['source_sha256'] for x in manifest['files']),'HD changed since map review'
 m=json.loads((track/'texmap.json').read_text());aliases=m['engine_compaction']['aliases'];fac={e['name']:e for e in m['facade_recipes']}
 labels={e['tile']:e['class'] for e in csv.DictReader((r/'scratchpad/import/retex/tile_labels.csv').open())}
 # These derived ROM palette variants lack CSV rows but have known material use.
 labels.update(tex_s1_x0000_y0000_256x256_c0DA='rock',tex_s1_x0256_y0000_256x128_c0C2_t='tree',tex_sea_blue_64x64_c1DF='water')
 pm.PROFILES.update(roof=dict(depth=.003,mode='wrap',micro=.025),grass=dict(depth=.0012,mode='wrap',micro=.025),ivy=dict(depth=.002,mode='wrap',micro=.02),water=dict(depth=.0015,mode='wrap',micro=.015))
 def classify(n):
  if n in fac:return 'facade'
  if n in m['recipes']:return classify(m['recipes'][n][0])
  if n in m['derived_recipes']:return 'grass'
  k=labels.get(n,labels.get(n.removesuffix('_dk'),'flat'))
  return 'facade' if k in pm.FACADES else k
 def canonical(i):
  seen=set()
  while str(i) in aliases:
   assert i not in seen;seen.add(i);i=int(aliases[str(i)])
  return i
 recs=collections.defaultdict(list)
 for k,v in m['scenery'].items():recs[canonical(int(k))].append(v)
 original_hash={p.name:sha(p) for p in track.glob('*.sbf')};ids=set();total_raw=0
 for fn in original_hash:
  f=sbfw.read_sbf(str(a.base_main if a.base_main and fn=='desert4_master_gfx_xdata.sbf' else track/fn));ids.update(c.id for c in f.chunks);total_raw+=len(f.raw)
 filename='desert4_master_gfx_xdata.sbf';f=sbfw.read_sbf(str(a.base_main or track/filename));oldraw=len(f.raw);original={c.id:(c.kind,c.data,c.fix[:],c.ref[:],c.z) for c in f.chunks};by=f.byid();root=f.chunks[-1].id
 template=next(c for c in f.kinds(4) if c.data[128:132]==b'DXT5')
 memo={};baseheights={};source_hash={};heads={}
 for p in sorted(hd.glob('*.png')):heads.setdefault((family(p.stem),classify(p.stem)),p.stem)
 for x in manifest['files']:heads[(family(Path(x['file']).stem),x['kind'])]=Path(x['head']).stem
 def dependencies(n):
  if n in fac:return set().union(*(dependencies(x['tile']) for x in fac[n]['sources']))
  if n in m['recipes']:return dependencies(m['recipes'][n][0])|dependencies(m['recipes'][n][1])
  if n in m['derived_recipes']:return dependencies(m['derived_recipes'][n]['background'])
  return {family(n)}
 def variant_leaves(n):
  if n in fac:return set().union(*(variant_leaves(x['tile']) for x in fac[n]['sources']))
  if n in m['recipes']:return variant_leaves(m['recipes'][n][0])|variant_leaves(m['recipes'][n][1])
  if n in m['derived_recipes']:return variant_leaves(m['derived_recipes'][n]['background'])
  return {n.removesuffix('_dk')}
 target_depth=.018
 def source(n):
  path=hd/(n+'.png')
  if not path.exists():path=sd/(n+'.png')
  assert path.exists(),n
  source_hash[str(path)]=sha(path)
  return np.array(Image.open(path).convert('RGBA'))
 def pixels(n):
  if n in memo:return memo[n]
  if n in fac:
   e=fac[n];w,h=e['size'];scale=max(1,512/max(w,h));size=(max(8,round(w*scale)),max(8,round(h*scale)))
   value=facadebake.compose(size,e['sources'],pixels),None
  elif n in m['recipes']:
   lo,up,t,rect=m['recipes'][n];value=overlay_bake._recipe(lo,up,np.array(t).reshape(3,2),pixels,rect)
  elif n in m['derived_recipes']:
   e=m['derived_recipes'][n];value=pixels(e['background'])
  else:
   rgba=source(n);kind=classify(n);head=heads.get((family(n),kind),n)
   if a.tuning:
    row=tune.get(family(n))
    if row:
     h=np.array(Image.open(height_dir/(family(n)+'.png')),np.float32)/65535
     h=1-(1-h)*(row['base_depth']*gains[family(n)])/target_depth
    else:h=np.ones(rgba.shape[:2],np.float32)
    v=np.array(Image.fromarray(h).resize((rgba.shape[1],rgba.shape[0]),Image.Resampling.BILINEAR))
    gray=np.uint8(np.rint(np.clip(v,0,1)*255));hole=rgba[:,:,3]<128
    value=np.repeat(gray[:,:,None],3,axis=2),hole if hole.any() else None
    memo[n]=value;return value

   key=(head,kind)
   if key not in baseheights:
    if n in mr and not (a.fresh_facades and kind=='facade'):
     # Original height before BC3, shared across approved palette variants.
     h=np.array(Image.open(research/'height'/mr[n]['file']),np.float32)/65535
    elif kind in pm.PROFILES:h=pm.shape_height(source(head)[:,:,:3],kind,head)
    else:h=np.full(rgba.shape[:2],.80,np.float32) # a flat overlay never gains invented relief
    baseheights[key]=h
   h=baseheights[key]
   # Preserve source UV/alpha footprint; height is linear, never tone/gain adjusted.
   size=(rgba.shape[1],rgba.shape[0]);v=np.array(Image.fromarray(h).resize(size,Image.Resampling.BILINEAR));gray=np.uint8(np.rint(v*255))
   hole=rgba[:,:,3]<128;value=(np.repeat(gray[:,:,None],3,axis=2),hole if hole.any() else None)
  memo[n]=value;return value
 selected=[];excluded=[];textures={};unique={};next_id=0xc1b00000;review=[]
 mats=list(f.kinds(2))
 for c in mats:
  if len(c.data)!=1848:continue
  tid=c.u32(0x1bc);rs=recs.get(tid,[])
  if not rs:continue
  kinds={classify(v['tile']) for v in rs};kind=next(iter(kinds)) if len(kinds)==1 else None
  reason=None
  if any(v.get('cut') for v in rs) or c.u32(0x4d4) or c.u32(0x4e4):reason='flat alpha-cutout geometry'
  elif kind not in pm.PROFILES:reason='flat scenery/sign or mixed incompatible alias classes'
  if a.tuning and rs and all(dependencies(v['tile'])<=set(tune) for v in rs) and not c.u32(0x4e4):
   reason=None
   if kind not in pm.PROFILES:kind=tune[sorted(dependencies(rs[0]['tile']))[0]]['kind']
  if a.tuning and rs and not any(dependencies(v['tile'])&set(tune) for v in rs):reason='No approved relief family'
  if excluded_variants and any(variant_leaves(v['tile'])&excluded_variants for v in rs):
   assert all(variant_leaves(v['tile'])&excluded_variants for v in rs),'Mixed excluded/nonexcluded aliases need separate materials'
   reason='Explicit variant exclusion'
  if reason:excluded.append(dict(material=c.id,tile=rs[0]['tile'],classes=sorted(kinds),reason=reason));continue
  expected={0x4d4:0,0x4e4:0,0x51c:0,0x52c:1,0x540:1,0x594:1,0x5b4:1,0x620:1}
  if a.tuning:expected[0x4d4]=c.u32(0x4d4)
  assert all(c.u32(o)==v for o,v in expected.items()),('Unexpected shader switches',hex(c.id))
  assert 0x1dc in c.ref
  if tid not in textures:
   n=rs[0]['tile'];profile=pm.PROFILES.get(kind,dict(depth=.018,mode='wrap' if kind=='wall' else 'reflect'));depth=profile['depth'];mode=profile['mode'];approved=not a.tuning and n in mr and kind=='rock' and mr[n]['head']=='tex_s1_x0000_y0000_256x256_c0AE.png'
   if a.tuning:
    deps=dependencies(n)&set(tune);depth=max((tune[k]['base_depth']*gains[k] for k in deps),default=.018);depth=max(depth,.000001);target_depth=depth;memo.clear()
   if approved:
    dds=(research/'dds'/Path(mr[n]['head']).with_suffix('.dds')).read_bytes()
   else:
    hp,hole=pixels(n);assert a.tuning or hole is None or not hole.any(),('Opaque material got holes',n)
    # Match target aspect and normalized UVs; lower-frequency relief needs <=512, albedo stays untouched.
    w,h=struct.unpack_from('<II',by[tid].data,8);factor=min(1,512/max(w,h));ww=max(4,int(w*factor));hh=max(4,int(h*factor));ww=1<<(ww-1).bit_length();hh=1<<(hh-1).bit_length()
    height=np.array(Image.fromarray(hp[:,:,0]).resize((ww,hh),Image.Resampling.BILINEAR),np.float32)/255
    if not a.tuning and (mode!='wrap' or n in fac or (n in m['recipes'] and m['recipes'][n][3] is not None)):
     # Reference-height rim means exactly zero displacement at nonrepeating edges.
     yy,xx=np.indices(height.shape);edge=np.minimum.reduce([xx,yy,ww-1-xx,hh-1-yy]);fade=np.clip(edge/max(3,min(ww,hh)*.025),0,1);height=1+(height-1)*fade;mode='reflect'
    normal=pm.normal(height,depth,mode);rgba=np.dstack([normal,np.uint8(np.rint(height*255))]);dds,_=codec.dds(rgba)
   decoded=Image.open(io.BytesIO(dds)).convert('RGBA');w,h=decoded.size;mips=struct.unpack_from('<I',dds,28)[0]
   assert w&(w-1)==0 and h&(h-1)==0 and mips==max(w,h).bit_length() and dds[84:88]==b'DXT5'
   key=hashlib.sha256(dds).hexdigest()
   if key not in unique:
    while next_id in ids:next_id+=1
    normalid=next_id;ids.add(normalid);next_id+=1;descriptor=bytearray(template.data[:48]);struct.pack_into('<II',descriptor,8,w,h)
    chunk=sbfw.Ch(4,normalid,bytes(descriptor)+dds[4:],[],[],template.z);unique[key]=dict(chunk=chunk,dds=dds)
    (out/'maps'/f'{normalid:08x}.dds').write_bytes(dds)
   normalid=unique[key]['chunk'].id
   textures[tid]=dict(tile=n,aliases=sorted({x['tile'] for x in rs}),kind=kind,depth_uv=depth,normal_id=normalid,size=[w,h],sha256=key,approved_rock_unchanged=approved)
   albedo=Image.open(io.BytesIO(b'DDS '+by[tid].data[48:])).convert('RGB');review.append((n,kind,albedo,decoded.getchannel('A').convert('RGB'),decoded.convert('RGB')))
  row=textures[tid];data=bytearray(c.data);struct.pack_into('<I',data,0x1dc,row['normal_id']);struct.pack_into('<I',data,0x5b4,0);struct.pack_into('<3f',data,0x644,row['depth_uv'],row['depth_uv'],1/1024);c.data=bytes(data)
  selected.append(dict(material=c.id,diffuse=tid,kind=kind,normal=row['normal_id'],depth=row['depth_uv']))
  if len(selected)%50==0:print('Prepared',len(selected),'materials;',len(textures),'texture mappings',flush=True)
 for v in unique.values():add_dependency_before_users(f,v['chunk'])
 assert f.chunks[-1].id==root
 for c in f.chunks:
  if c.id not in original:continue
  kind,data,fix,ref,z=original[c.id];assert (c.kind,c.fix,c.ref,c.z)==(kind,fix,ref,z)
  row=next((x for x in selected if x['material']==c.id),None)
  if row:
   expected_data=bytearray(data);struct.pack_into('<I',expected_data,0x1dc,row['normal']);struct.pack_into('<I',expected_data,0x5b4,0);struct.pack_into('<3f',expected_data,0x644,row['depth'],row['depth'],1/1024);assert c.data==expected_data
  else:assert c.data==data
 # Reject memory growth before producing any candidate install file.
 estimated=total_raw+sum(len(v['chunk'].data)+128 for v in unique.values());assert estimated<384*2**20,estimated/2**20
 path=out/filename;path.write_bytes(sbfw.write_sbf(f,compress=True,layout='auto',level=1));check=sbfw.read_sbf(str(path));newby=check.byid()
 assert [(c.id,c.kind,c.data,c.fix,c.ref,c.z) for c in check.chunks]==[(c.id,c.kind,c.data,c.fix,c.ref,c.z) for c in f.chunks]
 positions={c.id:i for i,c in enumerate(check.chunks)};assert check.chunks[-1].id==root
 assert all(positions[v]<i for i,c in enumerate(check.chunks) for v in c.refs() if v in positions)
 extern={v for c in check.chunks for v in c.refs()}-set(newby);assert not sbfw.validate(check,extern_ids=extern,quiet=True)
 raw_after=total_raw-oldraw+len(check.raw);assert raw_after<384*2**20
 assert all(sha(track/n)==h for n,h in original_hash.items());assert all(sha(p)==h for p,h in source_hash.items())
 # Every eligible material must be marked, all excluded material payloads unchanged.
 covered={x['material'] for x in selected};assert all(c.u32(0x1dc)==textures[c.u32(0x1bc)]['normal_id'] for c in check.kinds(2) if c.id in covered)
 for page in range(0,len(review),8):
  sheet=Image.new('RGB',(1200,8*180),(32,32,32));d=ImageDraw.Draw(sheet)
  for j,(name,kind,*images) in enumerate(review[page:page+8]):
   y=j*180;d.text((5,y+4),f'{page+j+1:03} {name} | {kind} | installed albedo / height / normal',fill='white')
   for k,im in enumerate(images):
    im=im.copy();im.thumbnail((390,148));x=k*400;sheet.paste(im,(x+(390-im.width)//2,y+24+(148-im.height)//2));d.rectangle((x,y+23,x+394,y+174),outline='#00ffff',width=1)
  sheet.save(out/'review'/f'{page//8+1:02}.jpg',quality=92)
 report=dict(installed=False,materials=len(selected),texture_mappings=len(textures),unique_maps=len(unique),classes=dict(collections.Counter(x['kind'] for x in selected)),excluded=excluded,selected=selected,textures=textures,unpacked_MiB_before=total_raw/2**20,unpacked_MiB_after=raw_after/2**20,normal_payload_MiB=sum(len(v['dds']) for v in unique.values())/2**20,before=original_hash,staged={filename:sha(path)},root_id=root,forward_references=0,geometry_unchanged=True,albedo_unchanged=True,lightmaps_unchanged=True,source_hashes=source_hash,live_validation='user accepted original rock family; extended coverage pending gameplay')
 if a.tuning:
  report['tuning_yaml']=str(a.tuning);report['family_gains']=gains;report['covered_families']=sorted(set().union(*(dependencies(x['tile'])&set(tune) for x in textures.values())))
  explicitly_excluded=set().union(*(dependencies(x['tile'])&set(tune) for x in excluded if x['reason']=='Explicit variant exclusion'))
  report['explicitly_excluded_families']=sorted(explicitly_excluded)
  assert set(report['covered_families'])|explicitly_excluded==set(tune),set(tune)-set(report['covered_families'])-explicitly_excluded
 (out/'stage-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['materials','texture_mappings','unique_maps','classes','unpacked_MiB_before','unpacked_MiB_after','normal_payload_MiB']},indent=2))
if __name__=='__main__':main()
