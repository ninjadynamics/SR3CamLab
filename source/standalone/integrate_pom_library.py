"""Stage native POM records, leaving every existing shader record intact."""
from pathlib import Path
import sys, struct, json, hashlib, math, argparse
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'source/tools/import/core'),str(ROOT/'source/standalone')]
import sbfw, compile_pom, shaderdis
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--source-library',type=Path,required=True,help='Original pre-native shader library')
ap.add_argument('--source-track',type=Path,required=True,help='YAML-staged POM track, before native metadata')
ap.add_argument('--out',type=Path,required=True)
ap.add_argument('--tuning',type=Path,default=ROOT/'config/mountain-pom-depth.yaml')
ap.add_argument('--material-report',type=Path,required=True,help='stage_pom_wide report for these maps')
ap.add_argument('--texmap',type=Path,default=ROOT/'game/Rally/Main_release/track1/Desert4/texmap.json')
args=ap.parse_args()
from pom_native_config import load, material_settings, audit_materials
tuning=load(args.tuning)
material_audit=audit_materials(ROOT,args.source_track,tuning,args.material_report,args.texmap)
OUT=args.out.resolve()
assert ROOT in OUT.parents and 'scratchpad' in OUT.parts and not OUT.exists(), 'Use a new workspace scratchpad folder'
OUT.mkdir(parents=True)
U32=lambda d,o:struct.unpack_from('<I',d,o)[0]
def string(d,o):return d[o:d.index(b'\0',o)].decode()
def digest(b):return hashlib.sha256(b).hexdigest()
libpath=args.source_library
trackpath=args.source_track
lib=sbfw.read_sbf(str(libpath));effect=lib.kinds(3)[0];old=effect.copy();d=old.data
nt,nr=struct.unpack_from('<HH',d);params=[string(d,U32(d,U32(d,12)+4*i)) for i in range(U32(d,4))]
techs={string(d,U32(d,U32(d,8)+24*i)):U32(d,8)+24*i for i in range(nt)}
target=techs['T_Lpse_Tdnl_Sds']
vrec,prec=U32(d,target+4),U32(d,target+8)
def record_blob(rec):
 off=U32(d,rec)
 return next(b for _,b in shaderdis.blobs(d[off:]) )
original_vs=record_blob(vrec);original_ps=record_blob(prec)
for k,b in [('vs',original_vs),('ps',original_ps)]:
 assert digest(b)==compile_pom.ORIGINAL[k]['sha256']
vs=compile_pom.compile_shader((ROOT/'source/standalone/shaders/pom_vs.hlsl').read_text(),'vs_3_0')
ps_source=(ROOT/'source/standalone/shaders/pom.hlsl').read_text()
# An otherwise unused specular sampler carries four endpoint bits. This avoids
# per-draw GetTexture/GetLevelDesc calls and preserves original c10 material data.
ps_source=ps_source.replace('float4 Controls : register(c30); // depth multiplier, enabled, reserved',
'''sampler2D MapMetadata : register(s2);
float4 NativeControls() {
 float4 bits=step(0.5,tex2Dlod(MapMetadata,float4(0.5,0.5,0,0)));
 return float4(POM_GAIN,1,exp2(7+bits.r+2*bits.g),exp2(7+bits.b+2*bits.a));
}
#define Controls NativeControls()''')
ps=[original_ps]+[compile_pom.compile_shader('#define POM_GAIN %.1f\n'%(i/10)+ps_source,'ps_3_0') for i in range(1,11)]
(OUT/'pom_native.hlsl').write_text(ps_source)
for i,b in enumerate(ps):(OUT/f'ps-{i}.bin').write_bytes(b)
(OUT/'vs.bin').write_bytes(vs)

class Builder:
 def __init__(self,data=b'',fix=()):self.data=bytearray(data);self.fix=list(fix)
 def add(self,b):
  self.data+=bytes(-len(self.data)%4);o=len(self.data);self.data+=b;return o
 def ptr(self,o,v):struct.pack_into('<I',self.data,o,v);self.fix.append(o)
 def rec(self,code,source,extra=False):
  r=self.add(bytes(20));b=self.add(code);entry=self.add(b'main\0')
  n=U32(d,source+8);mapping=bytearray(d[U32(d,source+12):U32(d,source+12)+8*n])
  if extra:mapping+=struct.pack('<HHI',2,1,params.index('TexSpecular'));n+=1
  m=self.add(mapping);self.ptr(r,b);self.ptr(r+4,entry);struct.pack_into('<I',self.data,r+8,n);self.ptr(r+12,m);return r

# Auxiliary effect is instantiated by the native kind-3 loader with the library.
# Each gain has a technique, so the engine creates and owns every shader.
a=Builder(bytes(28));at=a.add(bytes(24*11));pn=a.add(bytes(4*len(params)))
for i,name in enumerate(params):a.ptr(pn+4*i,a.add(name.encode()+b'\0'))
an=a.add(b'url_pom_controls_v1.fx\0')
av0=a.rec(original_vs,vrec);av=a.rec(vs,vrec)
ap=[a.rec(b,prec,i!=0) for i,b in enumerate(ps)]
for i in range(11):
 t=at+24*i;a.ptr(t,a.add(('depth_%02d'%i).encode()+b'\0'));a.ptr(t+4,av0 if i==0 else av);a.ptr(t+8,ap[i])
 struct.pack_into('<I',a.data,t+12,U32(d,target+12))
# Record array is canonical and contiguous; move all record pointers to it.
def canonical_records(b,records,tech_offsets):
 arr=b.add(b''.join(bytes(b.data[r:r+20]) for r in records))
 remap={r:arr+20*i for i,r in enumerate(records)}
 for i,r in enumerate(records):
  for k in [0,4,12]:b.fix.append(arr+20*i+k)
 for t in tech_offsets:
  for k in [4,8]:struct.pack_into('<I',b.data,t+k,remap[U32(b.data,t+k)])
 b.ptr(16,arr);return remap
canonical_records(a,[av0,av]+ap,[at+24*i for i in range(11)])
struct.pack_into('<HHI',a.data,0,11,13,len(params));a.ptr(8,at);a.ptr(12,pn);a.ptr(24,an)
aux_id=0xc1b0f001
assert aux_id not in lib.byid()
aux=sbfw.Ch(3,aux_id,a.data,sorted(set(a.fix)),[],old.z)

# Append own records, relocating the canonical record array, but do not modify
# bytecode/maps of any original shader. Only one unused-by-vanilla technique changes.
b=Builder(d,old.fix);bv=b.rec(vs,vrec);initial=round(float(tuning['global_depth_initial'])*10);bp=b.rec(ps[initial],prec,initial!=0)
b.ptr(target+4,bv if initial else vrec);b.ptr(target+8,bp)
original_records=[U32(d,16)+20*i for i in range(nr)]
remap=canonical_records(b,original_records+[bv,bp],[U32(d,8)+24*i for i in range(nt)])
struct.pack_into('<H',b.data,2,nr+2)
effect.data=bytes(b.data);effect.fix=sorted(set(b.fix))
lib.chunks.insert(lib.chunks.index(effect),aux)
# The library root continues to reference its native uber effect. Both effects
# have already gone through kind-3 construction before that root is processed.
staged_lib=OUT/libpath.name;staged_lib.write_bytes(sbfw.write_sbf(lib,level=6))
check=sbfw.read_sbf(str(staged_lib));assert not sbfw.validate(check,quiet=True)
for i,r in enumerate(original_records):
 q=remap[r]
 assert b.data[q:q+20]==d[r:r+20]
for name,t in techs.items():
 if t==target:continue
 assert b.data[t:t+4]==d[t:t+4] and b.data[t+12:t+24]==d[t+12:t+24]
 for k in [4,8]:assert U32(b.data,t+k)==remap[U32(d,t+k)]

track=sbfw.read_sbf(str(trackpath));by=track.byid();before={c.id:c.copy() for c in track.chunks}
marked=[c for c in track.kinds(2) if len(c.data)==1848 and c.f32(0x64c)==1/1024 and c.f32(0x644)+c.f32(0x648)>0]
assert len(marked)==material_audit['active_materials']
dimensions={};templates={}
for c in marked:
 normal=by[c.u32(0x1dc)];wh=(normal.u32(8),normal.u32(12));templates[wh]=normal
def metadata(wh,template,cid):
 x,y=[int(math.log2(v))-7 for v in wh];assert all(0<=v<=3 for v in [x,y])
 assert wh==(2**(x+7),2**(y+7))
 r,g,bb,alpha=x&1,(x>>1)&1,y&1,(y>>1)&1
 c565=(31*r<<11)|(63*g<<5)|(31*bb)
 block=bytes([255*alpha,0])+bytes(6)+struct.pack('<HHI',c565,c565,0)
 header=bytearray(template.data[48:172])
 struct.pack_into('<II',header,8,64,64);struct.pack_into('<I',header,16,4096);struct.pack_into('<I',header,24,7)
 descriptor=bytearray(template.data[:48]);struct.pack_into('<II',descriptor,8,64,64)
 payload=b''.join(block*max(1,((64>>i)+3)//4)**2 for i in range(7))
 return sbfw.Ch(4,cid,descriptor+header+payload,[],[],template.z)
for i,wh in enumerate(sorted(templates)):
 cid=0xc1b0f100+i;assert cid not in by;dimensions[wh]=cid
 meta=metadata(wh,templates[wh],cid);first=min(track.chunks.index(c) for c in marked if (by[c.u32(0x1dc)].u32(8),by[c.u32(0x1dc)].u32(12))==wh)
 track.chunks.insert(first,meta)
for c in marked:
 n=by[c.u32(0x1dc)];wh=(n.u32(8),n.u32(12));data=bytearray(c.data)
 assert 0x21c in c.ref
 struct.pack_into('<I',data,0x21c,dimensions[wh]);c.data=bytes(data)
staged_track=OUT/trackpath.name;staged_track.write_bytes(sbfw.write_sbf(track,level=6))
ct=sbfw.read_sbf(str(staged_track));pos={c.id:i for i,c in enumerate(ct.chunks)}
assert all(pos[v]<i for i,c in enumerate(ct.chunks) for v in c.refs() if v in pos)
for c in ct.chunks:
 if c.id not in before:continue
 oldc=before[c.id];expected=bytearray(oldc.data)
 if c.id in {m.id for m in marked}:expected[0x21c:0x220]=c.data[0x21c:0x220]
 assert c.data==expected and c.fix==oldc.fix and c.ref==oldc.ref
assert ct.chunks[-1].id==track.chunks[-1].id
manifest={'version':1,'technique':'T_Lpse_Tdnl_Sds','target_offset':target,'uber_name_offset':U32(d,24),'aux_name_offset':an,'aux_techniques_offset':at,'aux_id':aux_id,'marked_materials':len(marked),'metadata_dimensions':{str(k):v for k,v in dimensions.items()},'library_before':digest(libpath.read_bytes()),'track_before':digest(trackpath.read_bytes()),'library_after':digest(staged_lib.read_bytes()),'track_after':digest(staged_track.read_bytes()),'native_engine_owns_shaders':True,'unrelated_shader_records_preserved':True,'live_validation':'pending'}
manifest['material_settings']=material_settings(tuning)
manifest['material_audit']=material_audit
manifest['yaml_sha256']=digest(args.tuning.read_bytes())
manifest['initial_depth']=float(tuning['global_depth_initial'])
(OUT/'pom-native-install.json').write_text(json.dumps({
 'version':1,'material_settings':material_settings(tuning),'material_audit':material_audit,
 'files':{'system/shaderlib3_uber_data.sbf':manifest['library_after'],
 'Main_release/track1/Desert4/desert4_master_gfx_xdata.sbf':manifest['track_after']}
},indent=2)+'\n')
(OUT/'stage-report.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'pom_native_layout.h').write_text(f'''/* Generated by integrate_pom_library.py. */
#define POM_NATIVE_UBER_NAME_OFFSET {U32(d,24)}u
#define POM_NATIVE_AUX_NAME_OFFSET {an}u
#define POM_NATIVE_TARGET_OFFSET {target}u
#define POM_NATIVE_AUX_TECH_OFFSET {at}u
#define POM_NATIVE_RECORD_COUNT {nr+2}u
''')
print(json.dumps(manifest,indent=2))
