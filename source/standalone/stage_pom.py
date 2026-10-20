"""Stage one reviewed rock family for opt-in POM, never install or launch.
The supplied manifest/maps are local research assets, not distributed game data.
"""
from pathlib import Path
import argparse, hashlib, json, struct, sys, os
os.environ['SR3_FASTGEO']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/import/core'))
import sbfw
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def add_dependency_before_users(f, chunk):
 """Preserve the engine's last-chunk root and resolve local refs in load order."""
 root=f.chunks[-1]
 if chunk.id in f.byid():raise ValueError('Duplicate POM texture id')
 users=[i for i,c in enumerate(f.chunks) if chunk.id in c.refs()]
 if not users:raise ValueError('POM texture has no users')
 f.chunks.insert(min(users),chunk)
 positions={c.id:i for i,c in enumerate(f.chunks)}
 bad=[(c.id,v) for i,c in enumerate(f.chunks) for v in c.refs() if v in positions and positions[v]>=i]
 if bad:raise ValueError('Invalid local dependency order: '+str(bad[:4]))
 if f.chunks[-1] is not root:raise ValueError('Track root changed')
 return root.id

def main():
 a=argparse.ArgumentParser();a.add_argument('--track',type=Path,required=True);a.add_argument('--manifest',type=Path,required=True);a.add_argument('--maps',type=Path,required=True);a.add_argument('--head',required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args()
 track=args.track.resolve();out=args.out.resolve()
 if out==track or track in out.parents or out in track.parents:raise ValueError('Stage outside the input track directory')
 if out.exists():raise ValueError('Choose a new output directory; existing stage is preserved')
 manifest=json.loads(args.manifest.read_text());family=[x for x in manifest['files'] if x['head']==args.head]
 assert family and all(x['kind']=='rock' and not x['needs_semantic_review'] and x['edge_fade_uv']==0 for x in family)
 assert all(sha(x['source'])==x['source_sha256'] for x in family),'HD source changed; regenerate and review its maps first'
 depths={x['depth_uv'] for x in family};assert len(depths)==1;depth=depths.pop();assert 0<depth<=.05
 names={Path(x['file']).stem for x in family}
 texmap=json.loads((track/'texmap.json').read_text());records=texmap['scenery'];aliases=texmap.get('engine_compaction',{}).get('aliases',{})
 def canonical(i):
  seen=set()
  while str(i) in aliases:
   assert i not in seen;seen.add(i);i=aliases[str(i)]
  return i
 ids={canonical(int(k)) for k,v in records.items() if v['tile'] in names and not v.get('cut')}
 assert ids
 # Do not accidentally activate a different material aliased to the selected texture.
 assert all(v['tile'] in names and not v.get('cut') for k,v in records.items() if canonical(int(k)) in ids)
 before={x.name:sha(x) for x in track.glob('*.sbf')};all_ids=set();total_raw=0
 for name in before:
  f=sbfw.read_sbf(str(track/name));all_ids.update(c.id for c in f.chunks);total_raw+=len(f.raw)
 del f
 new_id=0xc1b00000
 while new_id in all_ids:new_id+=1
 name='desert4_master_gfx_xdata.sbf';f=sbfw.read_sbf(str(track/name));original={c.id:(c.kind,c.data,c.fix[:],c.ref[:],c.z) for c in f.chunks}
 dds=(args.maps/(Path(args.head).stem+'.dds')).read_bytes();assert dds[:4]==b'DDS ' and dds[84:88]==b'DXT5'
 h,w=struct.unpack_from('<II',dds,12);mips=struct.unpack_from('<I',dds,28)[0]
 assert w>0 and h>0 and w<=2048 and h<=2048 and not(w&(w-1)) and not(h&(h-1)) and mips==max(w,h).bit_length()
 expected=0;ww,hh=w,h
 for i in range(mips):expected+=max(1,ww//4)*max(1,hh//4)*16;ww=max(1,ww//2);hh=max(1,hh//2)
 assert len(dds)==128+expected
 template=next(c for c in f.chunks if c.kind==4 and c.data[128:132]==b'DXT5')
 descriptor=bytearray(template.data[:48]);struct.pack_into('<II',descriptor,8,w,h)
 normal=sbfw.Ch(4,new_id,bytes(descriptor)+dds[4:],[],[],template.z)
 selected=[]
 for c in f.kinds(2):
  if len(c.data)!=1848 or c.u32(0x1bc) not in ids:continue
  # Existing opaque, normal+lightmap, static+dynamic shadows and reflection switches.
  expected_switches={0x4d4:0,0x4e4:0,0x51c:0,0x52c:1,0x540:1,0x594:1,0x5b4:1,0x620:1}
  assert all(c.u32(o)==v for o,v in expected_switches.items()),('Unexpected material variant',hex(c.id))
  assert 0x1dc in c.ref
  data=bytearray(c.data);struct.pack_into('<I',data,0x1dc,new_id);struct.pack_into('<I',data,0x5b4,0);struct.pack_into('<3f',data,0x644,depth,depth,1/1024)
  c.data=bytes(data);selected.append(c.id)
 assert selected
 root_id=add_dependency_before_users(f,normal)
 out.mkdir(parents=True);path=out/name;path.write_bytes(sbfw.write_sbf(f,compress=True,layout='auto',level=6))
 check=sbfw.read_sbf(str(path));newby=check.byid()
 assert check.chunks[-1].id==root_id
 positions={c.id:i for i,c in enumerate(check.chunks)}
 assert all(positions[v]<i for i,c in enumerate(check.chunks) for v in c.refs() if v in positions)
 assert [(c.id,c.kind,c.data,c.fix,c.ref,c.z) for c in check.chunks]==[(c.id,c.kind,c.data,c.fix,c.ref,c.z) for c in f.chunks]
 for cid,(kind,data,fix,ref,z) in original.items():
  c=newby[cid];assert (c.kind,c.fix,c.ref,c.z)==(kind,fix,ref,z)
  if cid in selected:
   expected_data=bytearray(data);struct.pack_into('<I',expected_data,0x1dc,new_id);struct.pack_into('<I',expected_data,0x5b4,0);struct.pack_into('<3f',expected_data,0x644,depth,depth,1/1024)
   assert c.data==expected_data
  else:assert c.data==data,('Unrelated chunk changed',hex(cid))
 extern={v for c in f.chunks for v in c.refs()}-set(newby)
 assert not sbfw.validate(check,extern_ids=extern,quiet=True)
 new_total=total_raw-len(f.raw)+len(check.raw);assert new_total<384*1024*1024
 assert all(sha(track/n)==h for n,h in before.items()),'Input changed during staging'
 report={'installed':False,'root_id':root_id,'forward_references':0,'head':args.head,'material_ids':selected,'materials':len(selected),'normal_texture_id':new_id,'normal_size':[w,h],'normal_mips':mips,'normal_dds_sha256':hashlib.sha256(dds).hexdigest(),'depth_uv':depth,'before':before,'staged':{name:sha(path)},'unpacked_MiB_before':total_raw/2**20,'unpacked_MiB_after':new_total/2**20,'geometry_unchanged':True,'lightmaps_unchanged':True,'shadow_switches_unchanged':True,'live_validation':'pending'}
 (out/'stage-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['before','material_ids']},indent=2))
if __name__=='__main__':main()
