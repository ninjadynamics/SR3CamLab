"""Deterministic, conservative height/normal candidates from approved HD albedo.
No installed pixels are changed. These are hypotheses, not recovered geometry.
Use --overrides JSON to supply authored height PNGs for ambiguous facades.
"""
from pathlib import Path
import argparse,base64,csv,hashlib,json,os,re,sys
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scratchpad/atlas-recovery/deps'))
import cv2
cv2.setNumThreads(1)
PROFILES={
 'rock':dict(depth=.008,mode='wrap',micro=.12),
 'stone_wall':dict(depth=.006,mode='wrap',micro=.07),
 'asphalt':dict(depth=.0007,mode='wrap',micro=.015),
 'cobbles':dict(depth=.004,mode='wrap',micro=.045),
 'dirt':dict(depth=.0015,mode='wrap',micro=.025),
 'facade':dict(depth=.012,mode='reflect',micro=.018)}
FACADES={'house_brick','house_plaster','house_stone','church','arcade'}

def blur(a,s,mode):
 r=max(1,int(np.ceil(s*3)));p=np.pad(a,((r,r),(r,r)),mode=mode)
 return cv2.GaussianBlur(p,(0,0),s)[r:-r,r:-r]
from facade_semantics import facade_height

def shape_height(rgb,kind,texture=None):
 p=PROFILES[kind];mode=p['mode'];n=min(rgb.shape[:2])/512
 if kind=='asphalt':
  from surface_relief import asphalt_height
  return asphalt_height(rgb.shape[:2], texture)
 if kind=='facade' and texture:
  authored=facade_height(rgb,texture)
  if authored is not None:return authored
 # Suppress colour and high-frequency sparkle before interpreting luminance.
 y=(rgb[...,:3].astype(np.float32)/255)@np.array([.2126,.7152,.0722],np.float32)
 low=blur(y,max(.9,2*n),mode);broad=blur(low,max(5,32*n),mode)
 band=np.clip((low-broad)/.25,-1,1)
 if kind=='facade':
  # Only coherent dark components; tiny letters/paint/grain must not become holes.
  mask=((low<.32)&(low<broad-.08)).astype(np.uint8)
  k=max(3,int(3*n)|1);mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((k,k),np.uint8))
  count,lab,stats,_=cv2.connectedComponentsWithStats(mask,8)
  coherent=np.zeros(y.shape,np.float32)
  for i in range(1,count):
   x,z,w,h,area=stats[i]
   if area>=y.size*.0008 and area<=y.size*.10 and w/h>.30 and w/h<3 and area/(w*h)>.70: coherent[lab==i]=1
  recess=blur(coherent,max(1,2*n),mode)
  h=.78-.40*recess+p['micro']*band
 elif kind=='asphalt':
  # Paint, skid marks and broad patches are NOT potholes: no broad luminance height.
  fine=blur(y,max(.7,n),mode)-blur(y,max(1.4,3*n),mode)
  h=.75+np.clip(fine/.1,-1,1)*.035
 else:
  # Broad illumination removed; smooth joint-scale structure dominates micrograin.
  mid=blur(y,max(1,5*n),mode)-broad
  h=.65+np.clip(mid/.30,-1,1)*.23+band*p['micro']
 # Height relief must remain inside a non-tileable image, preventing frame pull-in.
 if mode!='wrap':
  yy,xx=np.indices(h.shape);dist=np.minimum.reduce([xx,yy,h.shape[1]-1-xx,h.shape[0]-1-yy]);f=np.clip(dist/max(4,12*n),0,1)
  h=.78+(h-.78)*f
 return np.clip(h,.05,.95).astype(np.float32)

def normal(h,depth,mode):
 if mode=='wrap': dx=(np.roll(h,-1,1)-np.roll(h,1,1))*.5*h.shape[1];dy=(np.roll(h,-1,0)-np.roll(h,1,0))*.5*h.shape[0]
 else:dy,dx=np.gradient(h);dx*=h.shape[1];dy*=h.shape[0]
 v=np.stack([-dx*depth,-dy*depth,np.ones_like(h)],-1);v/=np.linalg.norm(v,axis=2,keepdims=True)
 return np.uint8(np.clip(np.rint(v*127.5+127.5),0,255))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,default=ROOT/'content/classic/courses/src/course1_mountain/textures_hd');ap.add_argument('--labels',type=Path,default=ROOT/'scratchpad/import/retex/tile_labels.csv');ap.add_argument('--output',type=Path,default=ROOT/'scratchpad/pom-20261019');ap.add_argument('--overrides',type=Path);args=ap.parse_args()
 out=args.output;out.mkdir(parents=True,exist_ok=True)
 for sub in ['height','normal','packed','review']: (out/sub).mkdir(exist_ok=True)
 overrides=json.loads(args.overrides.read_text()) if args.overrides else {}
 labels={r['tile']:r['class'] for r in csv.DictReader(args.labels.open())};groups={};skipped=[]
 for f in sorted(args.input.glob('*.png')):
  cls=labels.get(f.stem,'unlabelled');kind='facade' if cls in FACADES else cls
  if kind not in PROFILES:skipped.append(dict(file=f.name,reason='not requested/eligible class: '+cls));continue
  a=np.array(Image.open(f).convert('RGBA'))
  if np.any(a[:,:,3]<254):skipped.append(dict(file=f.name,reason='cutout alpha: no silhouette/depth-pass support in first opaque POM pass'));continue
  family=re.sub(r'_c[0-9A-Fa-f]+(?:_t)?$','',f.stem)
  groups.setdefault((family,kind),[]).append(f)
 # Reuse approved geometry heads across tone-only siblings, never infer relief per paint colour.
 heads={v['id']:v['head'] for v in json.loads((ROOT/'scratchpad/resolution-3x-20261019/facade-plan.json').read_text())}
 rows=[]
 for (family,kind),files in groups.items():
  f=next((x for x in files if x.name==heads.get(family)),files[0]);rgb=np.array(Image.open(f).convert('RGB'))
  h=shape_height(rgb,kind,f.name)
  if f.stem in overrides:
   h=np.array(Image.open(overrides[f.stem]).convert('I'),np.float32);h/=65535 if h.max()>255 else 255
   assert h.shape==rgb.shape[:2],(f,h.shape,rgb.shape)
  p=PROFILES[kind];n=normal(h,p['depth'],p['mode']);packed=np.dstack([n,np.uint8(np.rint(h*255))])
  for file in files:
   dims=Image.open(file).size;assert dims==(rgb.shape[1],rgb.shape[0]),(family,dims,rgb.shape)
   Image.fromarray(np.uint16(np.rint(h*65535))).save(out/'height'/file.name)
   Image.fromarray(n).save(out/'normal'/file.name)
   Image.fromarray(packed,'RGBA').save(out/'packed'/file.name)
   row=dict(file=file.name,source=str(file),source_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),kind=kind,head=f.name,size=list(dims),height_range=[float(h.min()),float(h.max())],depth_uv=p['depth'],edge_fade_uv=.025 if kind=='facade' else 0,source_tone_shared=len(files),needs_semantic_review=kind=='facade',normal_max_degrees=float(np.degrees(np.arccos(np.clip((n[:,:,2].astype(float)-127.5)/127.5,-1,1))).max()),packed_sha256=hashlib.sha256((out/'packed'/file.name).read_bytes()).hexdigest())
   rows.append(row)
 # Samples are representative, not claims of all maps being visually approved.
 selected=[]
 for kind in PROFILES:
  candidates=[r for r in rows if r['kind']==kind]
  if candidates:selected.extend(candidates[:2] if kind in ['rock','facade'] else candidates[:1])
 for i,r in enumerate(selected):
  ims=[Image.open(r['source']).convert('RGB'),Image.open(out/'height'/r['file']).point(lambda x:x/257).convert('RGB'),Image.open(out/'normal'/r['file']).convert('RGB')]
  sheet=Image.new('RGB',(1000,370),(35,35,35));d=ImageDraw.Draw(sheet)
  for j,(im,label) in enumerate(zip(ims,['Approved HD albedo','Candidate height (not geometry truth)','Tangent normal'])):
   im.thumbnail((320,320));x=j*333;sheet.paste(im,(x+(320-im.width)//2,32+(320-im.height)//2));d.rectangle((x,31,x+321,353),outline=(0,235,255),width=2);d.text((x+4,8),label,fill='white')
  sheet.save(out/'review'/('%02d_%s.png'%(i,r['kind'])))
 manifest=dict(eligible=len(rows),families=len(groups),skipped=skipped,files=rows,samples=selected,installed=False)
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(json.dumps(dict(eligible=len(rows),families=len(groups),skipped=len(skipped),classes={k:sum(r['kind']==k for r in rows) for k in PROFILES},output=str(out))))
if __name__=='__main__':main()

