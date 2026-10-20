"""Reviewed surface-only relief corrections, separate from architectural openings.
Diffuse pixels never change. All bounds are approved source-pixel coordinates.
Mortar detection is an approximation confined to reviewed masonry, not geometry truth.
"""
from pathlib import Path
import re
import numpy as np
from PIL import Image, ImageDraw
import cv2
ROOT=Path(__file__).resolve().parents[2]
FAMILY=lambda n:re.sub(r'_c[0-9A-Fa-f]+(?:_t)?(?:_dk)?$','',Path(n).stem)
LIBRARY='tex_s1_x0512_y0640_128x128'
CASTLE='tex_s1_x0960_y0576_64x128'
# Regions reviewed against the HD heads. Trim/openings are further excluded by
# the architecture height field, so stone detail cannot emboss window panes.
REGIONS={
 'tex_s1_x0256_y0448_128x128':[(0,0,512,232),(0,315,512,492)],
 'tex_s1_x0256_y0576_128x128':[(0,75,512,249),(0,272,512,334),(0,346,512,512)],
 'tex_s1_x0640_y0384_128x128':[(0,432,512,512)],
 'tex_s1_x0640_y0704_128x128':[(0,0,512,512)],
 'tex_s1_x0768_y0448_128x128':[(0,0,512,236),(0,316,512,490)],
 'tex_s1_x0896_y0704_128x128':[(0,0,512,512)],
 CASTLE:[(0,0,256,512)],
 'tex_s1_x1984_y0000_64x128':[(0,49,256,320),(0,427,256,512)],
 'tex_s1_x0000_y0768_128x128':[(0,0,384,384)],
 'tex_s1_x0128_y0768_128x64':[(0,0,512,256)],
}

def asphalt_height(size, texture=None):
    # Light, unmarked asphalt between the worn bands. Sample a fixed head once;
    # never read skid-mark/paint brightness from the target diffuse texture.
    ref=ROOT/'content/classic/courses/src/course1_mountain/textures_hd/tex_s1_x0256_y0128_256x256_c07C.png'
    rgb=np.array(Image.open(ref).convert('RGB'),np.float32)/255
    y=rgb@np.array([.2126,.7152,.0722],np.float32)
    crop=y[270:398,45:173]
    grain=cv2.GaussianBlur(crop,(0,0),.65)-cv2.GaussianBlur(crop,(0,0),3.)
    # Mirrored extension joins continuously in both directions; no painted marks.
    tile=np.concatenate([grain,grain[:,::-1]],axis=1)
    tile=np.concatenate([tile,tile[::-1]],axis=0)
    H,W=size
    field=np.tile(tile,(int(np.ceil(H/256)),int(np.ceil(W/256))))[:H,:W]
    h=(.75+field).astype(np.float32)
    fam=FAMILY(texture) if texture else ''
    if fam in ('tex_s1_x1024_y0000_256x256','tex_s1_x1280_y0000_256x256'):
        # Restore the previous paint-edge relief only in visually identified
        # lane-marking regions. A fixed family head keeps tone variants aligned;
        # target skid/stain brightness never contributes to the height field.
        from pom_maps import blur
        paint_ref=ref.parent/(fam+'_c0EE.png')
        paint_rgb=np.array(Image.open(paint_ref).convert('RGB').resize((W,H),Image.Resampling.LANCZOS),np.float32)/255
        paint_y=paint_rgb@np.array([.2126,.7152,.0722],np.float32)
        n=min(H,W)/512
        fine=blur(paint_y,max(.7,n),'wrap')-blur(paint_y,max(1.4,3*n),'wrap')
        previous=.75+np.clip(fine/.1,-1,1)*.035
        # Coordinates reviewed on the native 768-square heads. Include the
        # original bevel's support, then feather into the clean road field.
        boxes=[(15,0,24,768),(744,0,753,768)]
        for x in (258,516):
            for y0,y1 in ((0,1),(51,153),(204,309),(360,459),(510,615),(666,768)):
                boxes.append((x,y0,x+13,y1))
        mask=_mask((H,W),boxes,(768,768)).astype(np.uint8)
        distance=cv2.distanceTransform(1-mask,cv2.DIST_L2,5)
        weight=np.clip((12*W/768-distance)/(4*W/768),0,1)
        h=h*(1-weight)+previous*weight
    return h.astype(np.float32)

def _mask(shape,boxes,reference):
    H,W=shape;rw,rh=reference;im=Image.new('L',(W,H));d=ImageDraw.Draw(im)
    for x,y,X,Y in boxes:d.rectangle((x*W/rw,y*H/rh,X*W/rw,Y*H/rh),fill=255)
    return np.array(im)>0

def _mortar(rgb, mask, fine=False, family=None):
    # Suppress grain first. Retain only elongated/coherent joint candidates.
    y=(rgb[:,:,:3].astype(np.float32)/255)@np.array([.2126,.7152,.0722],np.float32)
    y=cv2.bilateralFilter(y,7,.10,2.5)
    y=cv2.GaussianBlur(y,(0,0),.65 if fine else 1.0)
    size=5 if fine else 9
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(size,size))
    dark=cv2.morphologyEx(y,cv2.MORPH_BLACKHAT,kernel)
    # Pale mortar is common on brick and castle walls, and cannot be read as a
    # raised white stone: use a thin ridge only when it also has low chroma.
    chroma=np.ptp(rgb[:,:,:3].astype(np.float32)/255,axis=2)
    light=cv2.morphologyEx(y,cv2.MORPH_TOPHAT,kernel)*(chroma<.16)
    ridge=np.maximum(dark,light*.8)
    threshold=max(.018,float(np.percentile(ridge[mask],67)))
    binary=((ridge>threshold)&mask).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(binary,8)
    coherent=np.zeros(mask.shape,np.uint8)
    for i in range(1,count):
        x,z,w,h,area=stats[i]
        if area>=8 and max(w,h)>=7:coherent[labels==i]=1
    # Quiet stone faces and narrow recessed seams, never full luminance relief.
    dist=cv2.distanceTransform(1-coherent,cv2.DIST_L2,5)
    # Use coherent interior seeds to partition whole stones. This avoids treating
    # every fracture or speck of pigment inside a stone as another mortar trench.
    seeds=((dist> (1.6 if fine else 2.2))&mask).astype(np.uint8)
    count,seed_labels,stats,_=cv2.connectedComponentsWithStats(seeds,8)
    markers=np.zeros(mask.shape,np.int32);markers[~mask]=1;next_id=2
    for i in range(1,count):
        if stats[i,cv2.CC_STAT_AREA] >= (4 if fine else 10):
            markers[seed_labels==i]=next_id;next_id+=1
    if family==CASTLE:
        # Visually placed stone-interior seeds in the native 256x512 head.
        # Watershed follows the actual mortar around each seed, rather than
        # mistaking mottling within a stone for separate blocks.
        rows=[
        (3,[5,25,46,70,97,120,145,167,190,214,240]),
        (12,[13,39,63,90,117,144,173,200,224,248]),
        (25,[5,25,49,195,215,243]),(37,[13,43,193,215,242]),
        (53,[8,33,53,192,210,243]),(71,[12,36,55,193,219,245]),
        (89,[6,27,48,192,215,244]),(106,[14,38,192,217,245]),
        (119,[5,29,48,198,224,246]),
        (132,[8,35,61,88,114,141,168,193,219,245]),
        (148,[10,32,63,86,115,143,169,195,220,245]),
        (163,[12,38,64,91,118,143,169,194,218,243]),
        (180,[9,35,57,192,218,246]),(198,[13,36,55,193,218,246]),
        (214,[8,28,49,193,217,246]),(231,[12,37,54,194,218,246]),
        (248,[10,34,53,194,218,244]),(265,[12,37,55,192,218,246]),
        (280,[9,34,192,217,242]),
        (293,[12,38,63,88,114,140,167,193,218,245]),
        (310,[7,31,58,85,112,139,167,194,221,246]),
        (327,[14,39,65,89,115,141,167,194,218,246]),
        (343,[9,34,60,82,179,200,225,248]),
        (359,[12,36,61,83,180,201,224,247]),
        (378,[10,35,60,82,180,203,226,248]),
        (394,[12,36,59,81,180,204,227,248]),
        (410,[10,34,59,81,181,203,225,246]),
        (426,[12,37,61,81,181,204,226,247]),
        (443,[11,36,61,83,181,204,226,248]),
        (457,[10,36,61,87,112,140,166,193,218,245]),
        (474,[12,38,64,89,115,143,169,194,220,247]),
        (490,[9,34,60,86,113,140,166,193,218,245]),
        (506,[12,37,63,89,114,141,168,195,220,246])]
        markers[:]=0;markers[~mask]=1;next_id=2
        for y,xs in rows:
            for x in xs:
                yy=min(mask.shape[0]-1,round(y*mask.shape[0]/512));xx=min(mask.shape[1]-1,round(x*mask.shape[1]/256))
                if mask[yy,xx]:markers[yy,xx]=next_id;next_id+=1
    smoothed=cv2.bilateralFilter(rgb[:,:,:3].astype(np.uint8),7,32,3)
    labels=cv2.watershed(smoothed,markers)
    edges=((labels==-1)&mask).astype(np.uint8)
    dist=cv2.distanceTransform(1-edges,cv2.DIST_L2,5)
    joint=np.exp(-(dist/1.1)**2).astype(np.float32)
    return joint*mask

# Large block wall: explicit boundaries, no brightness inference.
WALL_LINES=[
 [(0,46),(67,48),(159,46),(232,47),(333,46),(384,44)],
 [(0,137),(67,137),(106,137),(107,104),(192,103),(230,106),(231,138),(334,138),(384,137)],
 [(0,193),(107,193),(192,192),(271,191),(384,192)],
 [(0,264),(49,264),(145,265),(188,265),(247,264),(361,265),(384,264)],
 [(0,330),(85,332),(187,332),(241,332),(332,332),(384,331)],
 [(10,0),(10,45)],[(102,0),(103,44)],[(274,0),(274,45)],
 [(67,48),(67,137)],[(159,48),(159,102)],[(231,48),(231,136)],[(334,48),(334,137)],
 [(107,138),(107,192)],[(192,105),(192,191)],[(271,140),(271,191)],
 [(49,195),(49,263)],[(145,194),(145,263)],[(193,194),(193,230),(247,230)],[(147,230),(192,230)],[(247,194),(247,264)],[(361,193),(361,265)],
 [(85,267),(85,331)],[(187,266),(187,331)],[(242,267),(242,331)],[(333,266),(333,331)],
 [(54,334),(54,384)],[(148,334),(148,384)],[(274,333),(274,384)]]

def refine(name,rgba,height):
    f=FAMILY(name);h=height.copy();H,W=h.shape
    rgb=np.array(Image.fromarray(rgba).resize((W,H),Image.Resampling.LANCZOS))
    if f in REGIONS:
        ref=(256,512) if f in (CASTLE,'tex_s1_x1984_y0000_64x128') else (384,384) if f=='tex_s1_x0000_y0768_128x128' else (512,256) if f=='tex_s1_x0128_y0768_128x64' else (512,512)
        mask=_mask((H,W),REGIONS[f],ref)&(rgb[:,:,3]>=254)
        if f not in ('tex_s1_x0000_y0768_128x128','tex_s1_x0128_y0768_128x64'):
            plane=.78 if f==CASTLE else .84
            mask &= abs(h-plane)<.008
            # Guard bevels/frames and original opening masks from joint detection.
            mask=cv2.erode(mask.astype(np.uint8),np.ones((3,3),np.uint8))>0
        if f=='tex_s1_x0640_y0704_128x128':
            mask &= ~_mask((H,W),[(195,130,280,265)],(512,512)) # sundial
        if f=='tex_s1_x0256_y0576_128x128':
            mask &= ~_mask((H,W),[(0,275,512,340)],(512,512)) # painted ornaments
        joint=_mortar(rgb,mask,f=='tex_s1_x0768_y0448_128x128',f)
        if f=='tex_s1_x0000_y0768_128x128':
            im=Image.new('L',(W,H));d=ImageDraw.Draw(im)
            for line in WALL_LINES:d.line([(x*W/384,y*H/384) for x,y in line],fill=255,width=max(1,round(W/384)))
            dist=cv2.distanceTransform(1-(np.array(im)>0).astype(np.uint8),cv2.DIST_L2,5)
            joint=np.exp(-(dist/(1.5*W/384))**2)
            h=.84-.20*joint
        elif f=='tex_s1_x0128_y0768_128x64':
            h=.84-.18*joint
        else:h-=joint*.10
    if f==LIBRARY:
        yy,xx=np.indices((H,W));y=yy*512/H;x=xx*512/W
        outline=[(0,320),(511,320),(511,344),(492,348),(476,345),(454,350),(431,349),(406,351),(382,348),(361,351),(338,348),(312,351),(286,348),(262,350),(239,347),(215,350),(191,347),(170,350),(147,344),(128,348),(107,344),(86,350),(65,345),(44,349),(25,344),(0,337)]
        im=Image.new('L',(W,H));ImageDraw.Draw(im).polygon([(a*W/512,b*H/512) for a,b in outline],fill=255);awning=np.array(im)>0
        ramp=.86+.39*np.clip((y-320)/17,0,1)
        h=np.where(awning,ramp,h)
    return h.astype(np.float32)
