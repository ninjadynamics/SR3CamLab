"""Manually traced HD architecture masks; coordinates are source pixels.
The 21 heads were inspected at their native 512px height. Palette children share
these shapes. Recesses are semantic, not inferred from dark paint or stone grain.
Heights describe plausible relief, not metrically recovered building geometry.
"""
from pathlib import Path
import re, json, hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def family(name): return re.sub(r'_c[0-9A-Fa-f]+(?:_t)?(?:_dk)?$','',Path(name).stem)

def shapes(index):
 s=[]
 def rect(b,h):s.append(('rect',list(b),h))
 def poly(p,h):s.append(('poly',p,h))
 def ellipse(b,h):s.append(('ellipse',list(b),h))
 def arch(b,h,r=None):s.append(('arch',list(b)+[r if r is not None else (b[2]-b[0])/2],h))
 def line(p,h=.9,w=2):s.append(('line',p,h,w))
 def window(b,gridx=(),gridy=(),archtop=False,depth=.28,frame=4):
  x,y,X,Y=b
  if archtop:
   arch((x-frame,y-frame,X+frame,Y+frame),.93)
   arch(b,depth)
  else:
   rect((x-frame,y-frame,X+frame,Y+frame),.93);rect(b,depth)
  for a in gridx:line([(a,y+1),(a,Y-1)],.67,2)
  for a in gridy:line([(x+1,a),(X-1,a)],.67,2)
 def door(b):window(b,depth=.61,frame=4)
 def sill(b):rect(b,.98)
 def rail(b,posts):
  x,y,X,Y=b;line([(x,y),(X,y)],.98,2);line([(x,Y),(X,Y)],.98,2)
  for a in posts:line([(a,y),(a,Y)],.98,2)
  s.append(('rail',list(b),.96)) # dark iron pixels ONLY inside a reviewed railing region
 if index==0:
  window((27,101,79,149),depth=.64,frame=3)
  window((383,53,416,94),[395,407],[70,82],frame=3)
  for b in [(27,211,80,297),(196,211,248,298),(366,212,422,281)]:
   x,y,X,Y=b;window(b,[x+16,x+32],[y+18,y+36,y+55],frame=4)
  window((305,231,323,277),[315],[248],True,frame=3)
  for b in [(28,335,79,445),(196,335,248,445),(366,335,423,445)]:door(b)
  for b in [(42,473,69,512),(166,473,264,512),(376,473,405,512)]:door(b)
  for x,X in [(24,84),(192,253),(362,429)]:sill((x,298 if x<300 else 284,X,305 if x<300 else 291))
  rail((0,408,511,449),list(range(4,512,13)));sill((0,450,511,459));sill((0,155,511,165))
 elif index==1:
  for row,(y,Y) in enumerate([(31,84),(147,218),(299,372),(441,511)]):
   for x,X in [(55,118),(228,294),(403,466)]:
    window((x,y,X,Y),[x+22,x+43],[(y+Y)//2],frame=5)
    poly([(x-10,y-6),((x+X)//2,y-21),(X+10,y-6)],.94)
   sill((0,min(Y+7,511),511,min(Y+12,511)))
 elif index==2:
  for x,X in [(24,80),(166,220),(286,342),(408,465)]:window((x,29,X,54),[x+14,x+29,x+43],[42],frame=3)
  for y,Y,top in [(120,202,89),(270,348,239),(420,481,390)]:
   for col,(x,X) in enumerate([(24,80),(166,220),(286,342),(408,465)]):
    arch((x-8,top,X+8,Y+5),.91,r=29)
    arch((x-3,top+6,X+3,Y),.78,r=25)
    if y==420 and col==2:door((282,y,344,512))
    else:window((x,y,X,Y),[x+14,x+29,x+43] if y!=420 else [x+27],[y+36] if y!=420 else [450],frame=3)
  for y in [61,211,356,488]:sill((0,y,511,y+5))
 elif index==3:
  ellipse((201,63,331,204),.94);ellipse((219,83,312,181),.27)
  # Actual carved tracery pixels inside the reviewed rose-glass ellipse.
  s.append(('tracery',[219,83,312,181],.72))
  for b in [(25,410,53,484),(88,410,117,484),(409,409,439,485),(472,410,503,485)]:window(b,depth=.36,frame=3)
  for x,X in [(17,61),(79,126),(399,448),(462,511)]:arch((x,381,X,408),.92,r=22)
  for pad,h in [(0,.95),(8,.87),(16,.79),(24,.71),(32,.63)]:arch((189+pad,325+pad,333-pad,487),h,r=max(3,72-pad))
  arch((241,390,280,484),.53,r=19)
  for x in range(2,512,19):arch((x,252,x+14,291),.67,r=7)
  for y in [232,241,298,308,492,503]:sill((0,y,511,y+3))
 elif index==4:
  for group in [(49,193),(320,464)]:
   x,X=group;arch((x-16,98,X+16,241),.93,r=(X-x+32)/2)
   for a,b in [(x+16,x+59),(x+87,x+128)]:window((a,147,b,225),[a+21],[173,200],True,frame=5)
  for b in [(96,378,144,451),(364,378,412,451)]:window(b,[b[0]+24],[405,430],True,frame=5)
  for x in range(-29,512,64):arch((x,43,x+54,71),.68,r=27)
  for y in [14,26,251,266,337]:sill((0,y,511,y+4))
 elif index==5:
  for y,Y in [(26,86),(151,207),(272,332)]:
   for x,X in [(11,80),(212,283),(409,482)]:
    window((x,y,X,Y),depth=.65,frame=4);line([((x+X)//2,y),((x+X)//2,Y)],.75,3)
  # Open shutters are on the wall; only the actual gap is a deep opening.
  rect((9,149,40,204),.92);rect((46,149,83,202),.24);rect((88,149,115,204),.92)
  window((212,151,283,201),[247],[],depth=.3,frame=3)
  arch((27,384,153,512),.34,r=26);line([(91,411),(91,512)],.65,3)
  door((367,405,485,512))
  for y in [110,239,355]:sill((0,y,511,y+3))
 elif index==6:
  for y,Y in [(114,166),(265,338)]:
   for x in [34,139,240,343,447]:window((x,y,x+31,Y),frame=5)
  for y,Y in [(168,215),(342,384)]:
   for x in [36,141,449] if y==342 else [36,141,449]:rect((x,y,x+26,Y),.97)
  for b in [(35,401,65,512),(139,401,170,460),(230,403,282,512),(344,401,375,459),(448,400,479,512)]:door(b)
  for y in [45,56,72,187,342]:sill((0,y,511,y+3))
 elif index==7:
  for b in [(23,96,72,184),(433,96,482,184),(24,271,66,357)]:window(b,[(b[0]+b[2])//2],[(b[1]+b[3])//2],frame=4)
  window((121,82,242,187),depth=.42,frame=5);window((256,82,384,187),depth=.42,frame=5)
  window((120,251,311,364),depth=.42,frame=5);window((325,251,384,364),depth=.42,frame=5)
  for b in [(188,108,233,186),(312,101,367,187),(333,264,365,363),(151,270,179,363)]:window(b,depth=.24,frame=3)
  rect((228,160,301,191),.96);rect((206,320,260,351),.61)
  window((433,276,479,355),depth=.66,frame=5)
  for b in [(107,447,151,512),(359,449,395,512),(192,437,313,512)]:door(b)
  for y in [192,228,367,401]:sill((0,y,511,y+4))
 elif index==8:
  for x,X in [(23,96),(146,221),(272,347),(399,474)]:
   window((x,23,X,94),[(x+X)//2],[56],frame=5)
   window((x,176,X,190),frame=3);window((x,201,X,291),[(x+X)//2],[],frame=3)
  rail((3,245,507,299),list(range(7,508,26)));sill((0,300,511,310))
  for b in [(22,355,99,458),(148,357,249,506),(267,357,350,507),(370,408,475,508)]:door(b)
  poly([(0,320),(511,320),(511,345),(0,342)],.96)
 elif index==9:
  for y,Y in [(50,87),(178,216),(305,344)]:
   for x in [55,179,308,431]:
    window((x,y,x+29,Y),[x+14],frame=3)
    rect((x-23,y-4,x-10,Y),.91);rect((x+34,y-4,x+49,Y),.91)
    rect((x+2,Y+5,x+28,Y+40),.97)
  for b in [(167,425,219,512),(297,425,350,512)]:window(b,frame=4)
  for y in [95,224,353]:sill((0,y,511,y+4))
 elif index==10:
  for x,X in [(68,117),(232,281),(396,445)]:window((x,105,X,203),[(x+X)//2],[151],frame=5)
  for x,X in [(54,130),(216,295),(381,458)]:
   window((x,277,X,397),[],[],True,frame=6)
   line([(x,320),(X,320)],.66,3);line([((x+X)//2,320),((x+X)//2,397)],.66,3)
  for x in [174,338]:arch((x-16,129,x+16,203),.65,r=16)
  for x in [174,338]:rect((x-9,328,x+9,373),.77)
  window((235,445,282,512),frame=4)
  rail((13,402,499,426),list(range(23,500,15)))
  for y in [70,210,234,246,429]:sill((0,y,511,y+4))
 elif index==11:
  for b in [(34,58,93,151),(372,52,431,145),(36,247,100,354),(374,242,442,348)]:
   x,y,X,Y=b;window(b,[x+20,x+40],[y+25,y+50,y+75],frame=5)
  window((87,494,123,512),frame=4);rect((204,138,269,231),.95)
 elif index==12:
  for b in [(40,82,85,162),(224,86,270,166),(413,91,458,171)]:
   x,y,X,Y=b;window(b,[x+14,x+29],list(range(y+15,Y,15)),frame=4)
  for y,Y in [(218,332),(366,456)]:
   for x,X in [(44,84),(165,204),(296,335),(419,459)]:window((x,y,X,Y),[(x+X)//2],list(range(y+15,Y,16)),frame=4)
  for x,X in [(25,98),(147,221),(276,349),(399,475)]:rail((x,305,X,343),[x+5,x+18,x+35,x+51,x+67])
  for y in [181,191,351,474]:sill((0,y,511,y+4))
 elif index==13:
  for x,X in [(41,65),(107,131),(226,251),(292,317),(398,423),(466,491)]:
   arch((x-9,383,X+9,486),.93,r=21);window((x,415,X,483),[],[449],frame=3)
  for x in range(6,512,20):rect((x,257,x+9,289),.70)
  for y in [239,250,302,313,490]:sill((0,y,511,y+4))
 elif index==14:
  for x in [38,278]:
   window((x,36,x+65,103),depth=.64,frame=4)
   window((x+2,60,x+62,102),[x+33],[82],frame=2)
  # Blind panels are shallow, not deep glass holes.
  for b in [(155,38,223,103),(396,38,464,103),(39,216,105,277),(156,216,223,277),(279,216,345,277),(399,216,465,277)]:window(b,depth=.78,frame=5)
  for x in [41,162,282,402]:
   window((x,356,x+65,371),frame=3);window((x,382,x+66,442),[x+31],frame=3);rect((x,450,x+66,489),.67)
  rail((97,109,251,160),list(range(100,252,17)));rail((337,109,486,160),list(range(340,486,17)))
  for b in [(94,161,251,170),(333,161,487,170),(0,316,511,324)]:sill(b)
 elif index==15:
  window((111,158,147,215),[129],[172],frame=3)
  for b in [(317,120,356,183),(437,121,477,184),(309,247,354,321),(432,247,476,321),(309,385,354,480),(432,386,476,479),(44,294,104,381),(158,294,217,379)]:
   x,y,X,Y=b;window(b,[(x+X)//2],[(y+Y)//2],frame=4)
  for b in [(42,431,104,512),(153,431,215,512)]:door(b)
  sill((0,222,269,232));sill((269,72,511,82))
 elif index==16:
  for b in [(45,176,84,275),(227,176,276,304),(422,177,462,275),(45,350,83,453),(228,350,278,498),(422,350,461,454)]:
   x,y,X,Y=b;window(b,[(x+X)//2],[y+37,y+65],depth=.42,frame=4)
  rail((143,269,357,308),list(range(147,358,19)));rail((144,460,358,499),list(range(148,358,19)))
  for b in [(138,311,361,321),(140,500,362,511),(29,279,100,289),(410,279,476,289),(29,459,100,469),(410,459,476,469)]:sill(b)
  sill((0,100,511,109));sill((0,118,511,125))
 elif index==17:
  for y,Y in [(24,101),(170,249)]:
   for x,X in [(165,207),(235,276),(305,346)]:window((x,y,X,Y),[],[y+36],True,frame=5)
  for b in [(40,385,150,460),(369,385,472,460)]:window(b,depth=.34,frame=5)
  arch((201,350,303,512),.59,r=51);line([(252,378),(252,512)],.73,3)
  for p in [[(29,337),(153,337),(151,371),(18,371)],[(353,338),(473,338),(468,371),(341,371)]]:poly(p,.97)
  for b in [(135,107,371,115),(137,255,370,264),(22,466,160,473),(360,467,483,475)]:sill(b)
 elif index==18:
  for x,X in [(65,123),(233,290),(399,456)]:window((x,126,X,211),[(x+X)//2],[174,185],True,frame=5)
  for x,X in [(11,159),(187,327),(356,501)]:arch((x,323,X,512),.32,r=(X-x)/2)
  for y in [72,216,226,294,304]:sill((0,y,511,y+4))
 elif index==19:
  for x in [39,225,409]:
   window((x,150,x+64,184),frame=4)
   window((x,191,x+64,274),depth=.66,frame=4)
   window((x,376,x+64,503),depth=.66,frame=4)
   line([(x+32,191),(x+32,274)],.76,3);line([(x+32,376),(x+32,503)],.76,3)
  for x,X in [(1,24),(51,88),(116,151),(178,211),(238,274),(303,335),(366,399),(426,458),(489,511)]:rect((x,44,X,85),.65)
  rail((206,281,304,332),list(range(211,305,17)))
  for y in [20,91,100,279,340]:sill((0,y,511,y+4))
 elif index==20:
  # 256x512 source: paired Gothic apertures, the center columns remain proud.
  for x in [64,89,145,172]:
   poly([(x,112),(x+3,103),(x+7,98),(x+12,105),(x+15,115),(x+15,178),(x,178)],.26)
   arch((x+1,135,x+14,179),.23,r=6)
  for x in [82,165]:rect((x,120,x+7,180),.94)
  for x in range(10,238,30):arch((x,13,x+19,40),.65,r=9)
  ellipse((86,230,177,286),.96);ellipse((94,237,171,279),.78)
  for x in range(9,238,28):arch((x,333,x+18,347),.66,r=9)
  for x in range(-8,255,41):arch((x,365,x+27,400),.57,r=13)
  for y in [46,319,351,409,424]:sill((0,y,255,y+3))
 return s

def render(rgb,index):
 H,W=rgb.shape[:2]; assert H==512 and W==(256 if index==20 else 512),(index,W,H)
 # 2x rasterization for subpixel edge coverage, then native-resolution output.
 scale=2; im=Image.new('F',(W*scale,H*scale),.84);draw=ImageDraw.Draw(im)
 for shape in shapes(index):
  typ,b,h,*args=shape
  if typ in ('rail','tracery'):
   # Preserve the gaps in intricate ironwork. No brightness-to-depth outside this region.
   x,y,X,Y=map(int,b);a=rgb[y:Y+1,x:X+1,:3].astype(float).mean(2)
   if typ=='rail':
    # Fine dark ironwork, not a solid dark door behind it.
    broad=np.array(Image.fromarray(np.uint8(a)).filter(ImageFilter.GaussianBlur(3)),float)
    alpha=np.clip((broad-a-3)/18,0,1)*np.clip((120-a)/35,0,1)
   else:
    alpha=np.clip((a-100)/35,0,1)
    yy,xx=np.indices(a.shape);alpha*=((xx-(X-x)/2)/((X-x)/2))**2+((yy-(Y-y)/2)/((Y-y)/2))**2<=1
   mask=Image.fromarray(np.uint8(alpha*255)).resize(((X-x+1)*scale,(Y-y+1)*scale),Image.Resampling.BILINEAR)
   im.paste(float(h),(x*scale,y*scale),mask);draw=ImageDraw.Draw(im);continue
  if typ in ('poly','line'):
   pts=[(int(round(x*scale)),int(round(y*scale))) for x,y in b]
   if typ=='poly':draw.polygon(pts,fill=h)
   else:draw.line(pts,fill=h,width=max(1,round(args[0]*scale)))
  elif typ=='arch':
   x,y,X,Y,r=b;r=min(r,(Y-y)/2)
   draw.ellipse(tuple(round(v*scale) for v in (x,y,X,y+2*r)),fill=h)
   draw.rectangle(tuple(round(v*scale) for v in (x,y+r,X,Y)),fill=h)
  else:getattr(draw,'rectangle' if typ=='rect' else 'ellipse')(tuple(round(v*scale) for v in b),fill=h)
 # A subpixel bevel only; do not soften/shift the architectural mask.
 a=np.array(im.resize((W,H),Image.Resampling.BOX),np.float32)
 return np.clip(a,.05,.98)

def facade_height(rgb,texture):
 spec=json.loads((Path(__file__).with_name('facade_relief.json')).read_text())
 keys=sorted(spec);key=family(texture)
 if key not in spec:raise ValueError('Unreviewed facade family: '+key)
 return render(rgb,keys.index(key))

def review(root,out):
 root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True)
 spec=json.loads(Path(__file__).with_name('facade_relief.json').read_text());rows=[]
 for i,(key,entry) in enumerate(sorted(spec.items())):
  p=root/'content/classic/courses/src/course1_mountain/textures_hd'/entry['reference'];rgb=np.array(Image.open(p).convert('RGB'));h=render(rgb,i)
  Image.fromarray(np.uint16(np.rint(h*65535))).save(out/(key+'.height.png'))
  # Cyan outlines show transitions in the actual depth field over source pixels.
  edge=np.maximum(np.abs(np.diff(h,axis=0,prepend=h[:1])),np.abs(np.diff(h,axis=1,prepend=h[:,:1])))>.08
  overlay=rgb.copy();overlay[edge]=(0,255,255)
  w=rgb.shape[1];canvas=Image.new('RGB',(w*3+16,544),(30,30,30));d=ImageDraw.Draw(canvas)
  for j,(a,label) in enumerate([(rgb,'HD source'),(overlay,'Authored depth boundaries'),(np.uint8(h*255),'Height: light = raised')]):
   canvas.paste(Image.fromarray(a).convert('RGB'),(j*(w+8),28));d.text((j*(w+8)+4,8),label,fill='white')
  canvas.save(out/f'{i:02d}.png')
  rows.append(dict(index=i,family=key,reference=p.name,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),shape_count=len(shapes(i)),size=[w,512]))
 (out/'manifest.json').write_text(json.dumps(rows,indent=2))
 return rows
