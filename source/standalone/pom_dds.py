"""Continuous-alpha BC3/DXT5 research encoder and normal-aware mip chain.
Existing importer's DXT5 path is binary cutout alpha and must NOT encode height.
Pure offline codec: reads staged maps, writes unique head DDS files only.
"""
from pathlib import Path
import io,json,struct,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source/tools/import/core'))
from build_classic import _dxt1_rgb_np

def encode_level(rgba):
 h,w=rgba.shape[:2];p=np.pad(rgba,((0,(-h)%4),(0,(-w)%4),(0,0)),mode='edge');hh,ww=p.shape[:2]
 col=np.frombuffer(_dxt1_rgb_np(p[:,:,:3]),np.uint8).reshape(-1,8)
 a=p[:,:,3].reshape(hh//4,4,ww//4,4).transpose(0,2,1,3).reshape(-1,16).astype(np.int32)
 a0=a.max(1);a1=a.min(1);same=a0==a1;a0=np.where(same & (a0<255),a0+1,a0);a1=np.where(a0==a1,a1-1,a1)
 pal=np.stack([a0,a1]+[((7-i)*a0+i*a1)//7 for i in range(1,7)],1)
 ix=np.abs(a[:,:,None]-pal[:,None,:]).argmin(2)
 bits=(ix.astype(np.uint64)<<(3*np.arange(16,dtype=np.uint64))).sum(1)
 b=np.zeros((len(col),16),np.uint8);b[:,0]=a0;b[:,1]=a1
 for i in range(6):b[:,i+2]=(bits>>(8*i))&255
 b[:,8:]=col;return b.tobytes()

def normalized_rgb(rgb):
 n=rgb.astype(np.float32)/127.5-1;n/=np.maximum(np.linalg.norm(n,axis=2,keepdims=True),1e-8)
 return np.uint8(np.clip(np.rint(n*127.5+127.5),0,255))

def dds(rgba):
 h,w=rgba.shape[:2]
 assert w&(w-1)==0 and h&(h-1)==0,'SR3 floor-block loader requires power-of-two full mip dimensions'
 assert max(w,h)<=2048
 levels=[];shape=[];a=rgba
 while True:
  shape.append([a.shape[1],a.shape[0]]);levels.append(encode_level(a))
  if a.shape[0]==a.shape[1]==1:break
  size=(max(1,a.shape[1]//2),max(1,a.shape[0]//2))
  small=np.dstack([np.array(Image.fromarray(a[:,:,:3]).resize(size,Image.Resampling.BOX)),np.array(Image.fromarray(a[:,:,3]).resize(size,Image.Resampling.BOX))]);small[:,:,:3]=normalized_rgb(small[:,:,:3]);a=small
 flags=0x1|0x2|0x4|0x1000|0x20000|0x80000;caps=0x1000|0x8|0x400000
 hdr=struct.pack('<7I11I8I5I',124,flags,h,w,len(levels[0]),0,len(levels),*([0]*11),32,4,struct.unpack('<I',b'DXT5')[0],0,0,0,0,0,caps,0,0,0,0)
 for (ww,hh),lev in zip(shape,levels):assert len(lev)==max(1,ww//4)*max(1,hh//4)*16
 return b'DDS '+hdr+b''.join(levels),shape

def run():
 stage=ROOT/'scratchpad/pom-20261019';out=stage/'dds';out.mkdir(exist_ok=True);m=json.loads((stage/'manifest.json').read_text());done={};logical={}
 for r in m['files']:
  key=r['head'];logical[r['file']]=key.replace('.png','.dds')
  if key in done:continue
  rgba=np.array(Image.open(stage/'packed'/key).convert('RGBA'));h,w=rgba.shape[:2];size=(1<<(w-1).bit_length(),1<<(h-1).bit_length())
  if size!=(w,h):
   rgba=np.dstack([np.array(Image.fromarray(rgba[:,:,:3]).resize(size,Image.Resampling.BILINEAR)),np.array(Image.fromarray(rgba[:,:,3]).resize(size,Image.Resampling.BILINEAR))]);rgba[:,:,:3]=normalized_rgb(rgba[:,:,:3])
  data,levels=dds(rgba);decoded=np.array(Image.open(io.BytesIO(data)).convert('RGBA'));assert decoded.shape==rgba.shape
  ae=decoded[:,:,3].astype(float)-rgba[:,:,3];normalA=rgba[:,:,:3].astype(float)/127.5-1;normalB=decoded[:,:,:3].astype(float)/127.5-1
  normalA/=np.linalg.norm(normalA,axis=2,keepdims=True);normalB/=np.linalg.norm(normalB,axis=2,keepdims=True)
  deg=np.degrees(np.arccos(np.clip((normalA*normalB).sum(2),-1,1)))
  (out/key.replace('.png','.dds')).write_bytes(data)
  row=dict(bytes=len(data),size=list(size),mips=len(levels),height_rmse=float(np.sqrt((ae*ae).mean())),height_max_abs=float(np.abs(ae).max()),normal_mean_degrees=float(deg.mean()),normal_p99_degrees=float(np.percentile(deg,99)),height_unique=len(np.unique(decoded[:,:,3])))
  assert row['height_rmse']<3,(key,row)
  done[key]=row
 # Synthetic independent roundtrip: full smooth alpha ramp is not collapsed to cutout.
 a=np.zeros((16,256,4),np.uint8);a[:,:,:3]=(128,128,255);a[:,:,3]=np.arange(256)
 data,_=dds(a);dec=np.array(Image.open(io.BytesIO(data)).convert('RGBA'));assert len(np.unique(dec[:,:,3]))>128;assert np.max(abs(dec[:,:,3].astype(int)-a[:,:,3]))<=1
 for size in [1,2,4,8]:
  a=np.zeros((size,size,4),np.uint8);a[:]=(128,128,255,173);data,_=dds(a);dec=np.array(Image.open(io.BytesIO(data)).convert('RGBA'));assert (dec[:,:,3]==173).all()
 report=dict(unique_heads=len(done),logical_maps=len(logical),dds_payload_MiB=sum(x['bytes'] for x in done.values())/1048576,logical_to_dds=logical,files=done,tests=['full 256-level alpha ramp survives','constant alpha exact at 1/2/4/8 sizes','all mip sizes match standard and SR3 floor-block formulas','normal vectors renormalized per mip','every output decoded using independent Pillow DDS reader'],installed=False)
 (stage/'dds-audit.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['files','logical_to_dds']},indent=2))
if __name__=='__main__':run()

