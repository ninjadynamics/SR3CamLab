"""Rebake Hornet PNG overrides without changing model, UVs or handling.
Stages files only. Refuses unless ROM-rendered SD atlases exactly match the installed
texture payloads, so differing livery/light/layout cannot silently corrupt a car.
Set DAYTONA_SCRATCH to the owned Daytona region images directory.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image
import daytona_car as D
import sbfw, texdxt


def atlases(hd=None, scale=1, light=174.0):
    faces=D.day_faces(1460)+D.day_faces(1462)
    layers=D.overlay_layers(faces); tiles=D.Tiles(light,hd)
    for f in faces: f['sel']=not f['mat']['translucent']
    body,buv,density=D.bake(faces,layers,tiles,1024,0,render_scale=scale)
    for f in faces: f['sel']=bool(f['mat']['translucent'])
    glass,guv,_=D.bake(faces,layers,tiles,512,density,alpha_target=True,render_scale=scale)
    wheels={side:tuple(D.day_faces(row) for row in rows) for side,rows in D.WHEEL_ROWS.items()}
    allw=[f for side in ('l','r') for part in wheels[side] for f in part]
    for f in allw: f['sel']=True
    wheel,wuv,_=D.bake(allw,np.zeros(len(allw),int),tiles,512,0,render_scale=scale)
    body=np.clip(body*255,0,255); body[...,3]=255
    glass=np.clip(glass*255,0,255)
    wheel=np.clip(wheel*255,0,255); wheel[...,3]=255
    blur=D.radial_blur_atlas(wheel,allw,wuv,wheels)
    return dict(body=body,glass=glass,wheels=wheel,blur=blur),dict(body=buv,glass=guv,wheels=wuv),tiles.used_hd


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game',type=Path,required=True);ap.add_argument('--hd',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--scale',type=int,choices=(2,4),default=2)
    ap.add_argument('--light',type=float,default=174.0)
    a=ap.parse_args()
    if (a.out/'manifest.json').exists(): raise ValueError('Use a fresh output directory')
    print('Reconstructing SD atlases for exact source validation',flush=True)
    sd,suv,_=atlases(light=a.light)
    names=['hornetchassismodel_data.sbf','hornetgravelmodel_data.sbf','hornetmudmodel_data.sbf',
           'hornetsnowmodel_data.sbf','bonnets/hornet_data.sbf']
    matches={};originals={};encoded={}
    for name in names:
        rel=Path('Main_release/cars')/name;path=a.game/rel;f=sbfw.read_sbf(str(path))
        hit={}
        for i,c in enumerate(f.chunks):
            if c.kind!=4: continue
            w,h,fc=texdxt.texture_info(c.data)
            for kind,img in sd.items():
                if img.shape[:2]!=(h,w):continue
                key=(kind,fc)
                if key not in encoded: encoded[key]=texdxt.texture_data(c.data,img)[172:]
                if c.data[172:]==encoded[key]:hit[i]=kind
        expected={'body','glass'} if name.startswith('hornetchassis') else {'wheels','blur'} if name.startswith('hornetgravelmodel') else {'body'}
        if set(hit.values())!=expected:raise ValueError(f'{name}: SD atlas mismatch: found {hit}, expected {expected}')
        matches[str(rel)]=hit;originals[str(rel)]=f
        print(name,hit,flush=True)
    print('Baking HD atlases',flush=True)
    hd,huv,used=atlases(str(a.hd),a.scale,a.light)
    for part in suv:
        assert suv[part].keys()==huv[part].keys()
        assert all(np.array_equal(suv[part][i],huv[part][i]) for i in suv[part]),'UV layout changed'
    found={p.name for p in a.hd.glob('*.png')}
    if not found or found-set(used):raise ValueError('Unused HD PNGs: '+str(sorted(found-set(used))))
    a.out.mkdir(parents=True,exist_ok=True)
    manifest=dict(game=str(a.game.resolve()),hd=str(a.hd.resolve()),used=used,scale=a.scale,runtime_max_texture=2048,files=[])
    cache={}
    for rel,f in originals.items():
        before=[(c.kind,c.id,c.data,c.fix,c.ref,c.z) for c in f.chunks]
        edits=[]
        for i,kind in matches[rel].items():
            c=f.chunks[i];key=(kind,c.data[:172])
            if key not in cache:cache[key]=texdxt.texture_data(c.data,hd[kind])
            data=texdxt.fit_texture_mips(cache[key],2048)
            f.chunks[i]=sbfw.Ch(c.kind,c.id,data,c.fix,c.ref,c.z,c.gap)
            edits.append(dict(chunk_id=f'{c.id:08x}',atlas=kind,dimensions=texdxt.texture_info(data)[:2]))
        target=a.out/rel;target.parent.mkdir(parents=True,exist_ok=True)
        D.write_realigned(f,str(target));back=sbfw.read_sbf(str(target))
        assert len(back.chunks)==len(before)
        for i,c in enumerate(back.chunks):
            b=before[i]
            assert (c.kind,c.id,c.fix,c.ref,c.z)==(b[0],b[1],b[3],b[4],b[5])
            if i not in matches[rel]: assert c.data==b[2],'Nontexture data changed'
            else:
                assert c.data==f.chunks[i].data
                decoded=texdxt.decode_texture(c.data)
                assert max(decoded.shape[:2])<=2048
                assert decoded.shape[2]==4
        manifest['files'].append(dict(path=rel,source_sha256=hashlib.sha256((a.game/rel).read_bytes()).hexdigest(),
                                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),textures=edits))
        print('Validated',rel,flush=True)
    for kind,img in hd.items():Image.fromarray(img.astype(np.uint8),'RGBA').save(a.out/('atlas_'+kind+'.png'))
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Staged',len(manifest['files']),'files;',len(used),'PNG overrides; all UVs/nontexture chunks unchanged')

if __name__=='__main__':main()
