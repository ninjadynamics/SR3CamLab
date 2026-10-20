"""NumPy-free texture lookup with explicit stores and lazy ROM access."""
import json
import math
import os
from PIL import Image
from npyio import Arr

def _pixels(im,cut=True):
    w,h=im.size;raw=im.tobytes();rgb=bytearray(w*h*3)
    for k in range(3):rgb[k::3]=raw[k::4]
    hole=bytearray(a<128 for a in raw[3::4]) if cut else None
    return Arr('|u1',(h,w,3),rgb),Arr('|b1',(h,w),hole) if hole is not None and any(hole) else None

def _rgba(path):
    with Image.open(path) as im:return im.convert('RGBA')

class Tiles:
    """Composed -> changed HD -> ROM -> PNG lookup, with explicit cache state.

    baked maps names to RGB/hole Arr pairs; its values are returned unchanged.
    hd_used is the mutable positive/negative HD cache, cleared by the caller.
    rom is an optional callable(name)->pair/None; RomTiles provides real ROMs.
    PNG fallback is read fresh on every call, exactly like build_classic.
    """
    def __init__(self,extra_tex=None,baked=None,hd_used=None,rom=None):
        self.extra_tex=os.fspath(extra_tex) if extra_tex else None
        self.baked={} if baked is None else baked
        self.hd_used={} if hd_used is None else hd_used
        self.rom=rom

    def hd_tile(self,name):
        if not self.extra_tex:return None
        if name in self.hd_used:return self.hd_used[name]
        p=os.path.join(self.extra_tex+'_hd',name+'.png');o=os.path.join(self.extra_tex,name+'.png');out=None
        if os.path.exists(p):
            with _rgba(p) as im:
                same=False
                if os.path.exists(o):
                    with _rgba(o) as original:same=original.size==im.size and original.tobytes()==im.tobytes()
                if not same:
                    w,h=im.size;size=tuple(max(4,min(2048,1 << (v-1).bit_length())) for v in (w,h))
                    if im.size==size:out=_pixels(im)
                    else:
                        with im.resize(size,Image.Resampling.LANCZOS) as resized:out=_pixels(resized)
        self.hd_used[name]=out
        return out

    def tile_pixels(self,name):
        name=str(name).split('|')[0]
        if name in self.baked:return self.baked[name]
        out=self.hd_tile(name)
        if out is not None:return out
        if self.rom is not None:
            out=self.rom(name)
            if out is not None:return out
        if self.extra_tex:
            path=os.path.join(self.extra_tex,name+'.png')
            if os.path.exists(path):
                with _rgba(path) as im:return _pixels(im,name.endswith('_t'))
        return None

class RomTiles:
    """Lazy classic_tex ROM tiles as Arrs; optional explicit byte-page fixtures.

    pages maps (sheet,half) to 1024x1024 texel bytes. Defaults use classic_tex's
    configured page/material files and m2colour's existing byte APIs.
    """
    def __init__(self,pages=None,materials=None,palette=None,luma=None):
        self.pages=pages;self.materials=materials;self.palette=palette;self.luma=luma
        self._ready=False

    def _tile(self,m):
        import classic_tex as CT
        half=m['x']//1024;p=self.pages.get((m['sheet'],half))
        if p is None:return None
        right=self.pages.get((m['sheet'],half+1));width=1024
        if right is not None and m['x']%1024+m['w']>1024:p=CT.sheet_bytes(p,right);width=2048
        return CT.tile_bytes(p,width,dict(m,x=m['x']%1024))

    def __call__(self,name):
        import classic_tex as CT
        import m2colour as MC
        if not self._ready:
            if self.pages is None:
                pages=CT.page_bytes()
                with open(CT.PAGEFILE) as f:choice=json.load(f)
                self.pages={tuple(int(v) for v in k.split(',')):pages[o] for k,o in choice.items()}
            source=CT.materials() if self.materials is None else self.materials
            self.materials={k:(m if m and self._tile(m) is not None else None) for k,m in source.items()}
            self._ready=True
        m=self.materials.get(name)
        if not m:return None
        b,w,h=self._tile(m)
        if self.palette is None:self.palette=MC.palette_bytes()
        if self.luma is None:self.luma=MC.lumaram_bytes()
        lb=m.get('luma',0)
        if not any(self.luma[lb<<7:(lb<<7)+128]):lb=0
        tabs=MC.colour_tables(m['cb'],lb,self.palette,self.luma,False)
        rgb=bytearray(w*h*3)
        for k in range(3):rgb[k::3]=b.translate(tabs[k])
        hole=Arr('|b1',(h,w),bytearray(v==15 for v in b)) if m['alpha'] else None
        return Arr('|u1',(h,w,3),rgb),hole
