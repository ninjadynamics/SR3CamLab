"""Reviewed Mountain relief: castle cutouts, fence, and stone curb.
Geometry masks are shared across palette siblings. Diffuse artwork is untouched.
Source coordinates: curb 384x768; castle 256x512; fence 1024x512.
"""
import re
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import cv2

CASTLE='tex_s1_x0960_y0576_64x128'
CURB='tex_s1_x1536_y0000_128x256'
FENCE='tex_s1_x1792_y0256_256x128'
CUTOUTS={CASTLE+'_c10D_t',CASTLE+'_c10F_t',FENCE+'_c058_t'}
def family(name):return re.sub(r'_c[0-9A-Fa-f]+(?:_t)?$', '',Path(name).stem)
def supported(name):return Path(name).stem in CUTOUTS or family(name)==CURB

def depth(name):
 return {CASTLE:.012,FENCE:.010,CURB:.018}[family(name)]

# Reviewed stone boundaries. Interior speckling is pigment/roughness, not cavities.
CURB_STONES=[
[(12,10),(91,8),(93,46),(83,80),(31,78),(8,51)],
[(106,0),(153,0),(158,64),(125,68),(97,56)],
[(161,0),(214,0),(214,50),(198,67),(175,54)],
[(222,0),(287,0),(315,34),(307,73),(251,83),(220,59)],
[(337,15),(370,20),(376,48),(356,83),(335,81),(325,52)],
[(106,76),(141,77),(151,109),(119,118),(101,101)],
[(174,74),(203,69),(218,91),(214,134),(185,149),(156,141),(148,116)],
[(3,98),(40,94),(69,110),(88,141),(75,167),(45,182),(14,171),(1,150)],
[(106,146),(137,139),(159,167),(153,185),(121,201),(98,188),(90,167)],
[(178,162),(199,151),(219,177),(238,207),(226,225),(188,225),(169,205),(161,183)],
[(244,103),(301,89),(319,108),(325,159),(310,184),(263,177),(233,151),(228,125)],
[(342,118),(370,105),(384,137),(378,169),(349,189),(327,172),(327,145)],
[(247,181),(309,189),(317,212),(282,219),(241,204)],
[(34,196),(73,189),(94,205),(94,263),(75,294),(32,290),(8,268),(15,226)],
[(116,202),(149,198),(163,214),(162,275),(146,288),(109,278),(94,252),(99,222)],
[(178,231),(216,232),(223,262),(206,290),(177,286),(162,274)],
[(246,223),(283,224),(291,257),(283,299),(248,308),(222,285),(224,256)],
[(314,223),(348,216),(383,223),(380,276),(370,298),(328,306),(295,292),(293,254)],
[(87,299),(109,291),(133,303),(127,342),(116,361),(93,350),(77,329)],
[(152,296),(188,290),(218,314),(220,353),(208,377),(165,385),(131,367),(131,334)],
[(242,312),(271,315),(280,344),(273,383),(237,383),(219,366),(222,337)],
[(296,312),(347,309),(379,328),(373,374),(353,391),(291,386),(278,360)],
[(1,339),(38,330),(65,352),(77,388),(68,422),(23,431),(0,416)],
[(81,351),(100,360),(110,399),(108,430),(87,438),(73,418)],
[(145,390),(191,384),(206,404),(203,462),(189,508),(164,521),(132,502),(108,463),(112,424)],
[(226,392),(262,391),(275,412),(271,460),(261,503),(248,518),(219,513),(202,486),(205,440)],
[(287,389),(309,394),(312,417),(299,437),(277,425),(277,407)],
[(308,448),(340,422),(371,427),(381,460),(361,487),(330,500),(304,486),(284,471)],
[(34,441),(62,435),(84,453),(98,483),(92,515),(65,534),(34,528),(17,506),(21,471)],
[(111,515),(131,506),(162,531),(162,558),(144,580),(113,574),(101,551)],
[(0,535),(26,538),(38,559),(31,606),(16,634),(0,625)],
[(70,583),(111,579),(158,595),(173,631),(159,674),(141,693),(111,680),(86,670),(64,645),(58,613)],
[(176,561),(198,554),(216,576),(219,612),(207,628),(181,626),(167,610),(163,580)],
[(232,527),(254,520),(275,541),(276,589),(260,621),(237,626),(217,601),(217,557)],
[(293,522),(343,517),(382,521),(382,578),(368,598),(333,607),(292,596),(278,566)],
[(31,660),(62,652),(86,680),(87,711),(70,725),(32,719),(11,706),(14,676)],
[(183,640),(215,635),(249,644),(256,681),(245,729),(228,763),(188,758),(173,732),(166,687)],
[(279,626),(304,612),(337,620),(363,646),(375,685),(372,716),(340,724),(300,735),(271,717),(263,683)],
[(109,714),(140,704),(151,729),(145,756),(123,768),(103,755)],
[(28,735),(65,728),(81,743),(78,768),(24,768),(8,758)],
[(288,745),(324,737),(357,741),(384,768),(285,768)]
]

def raster_poly(size,points):
 im=Image.new('L',size);ImageDraw.Draw(im).polygon(points,fill=255);return np.array(im)>0

def height(name,rgba):
 f=family(name);H,W=rgba.shape[:2]
 if f==CURB:
  h=np.full((768,384),.27,np.float32)
  for points in CURB_STONES:
   mask=raster_poly((384,768),points).astype(np.uint8)
   dist=cv2.distanceTransform(mask,cv2.DIST_L2,5)
   # Narrow bevel and quiet, slightly rounded faces; no albedo grain in height.
   stone=.27+.48*np.clip(dist/3,0,1)+.10*np.clip(dist/19,0,1)
   h=np.maximum(h,stone)
 elif f==CASTLE:
  im=Image.new('F',(256,512),.78);d=ImageDraw.Draw(im)
  def arch(box,value):
   x,y,X,Y=box;r=(X-x)/2
   d.ellipse((x,y,X,y+2*r),fill=value);d.rectangle((x,y+r,X,Y),fill=value)
  for box in [(77,31,112,121),(126,30,166,122),(74,184,110,279),(133,184,172,280),(98,342,152,441)]:
   x,y,X,Y=box;arch((x-5,y-6,X+5,Y+3),.94);arch(box,.30)
  for box in [(56,122,195,128),(58,280,192,288),(73,442,177,450)]:d.rectangle(box,fill=.98)
  # Actual narrow central columns remain raised between the openings.
  for box in [(115,46,123,119),(114,205,130,277)]:d.rectangle(box,fill=.96)
  h=np.array(im,np.float32)
 elif f==FENCE:
  y,x=np.indices((512,1024));h=np.full((512,1024),.62,np.float32)
  # Rail: convex cylinder; upright posts: raised faces with lower bevels.
  # Do not fade the cutout rim UP to height 1: that makes posts hollow.
  # Weathering stays paint; transparent neighbours are extended by calibration.
  for a,b in [(82,153),(239,306),(405,468),(574,643),(731,802),(913,993)]:
   t=np.clip(np.minimum(x-a,b-x)/9,0,1);h=np.where((x>=a)&(x<=b),.62+.14*t,h)
  rail=np.sqrt(np.clip(1-((y-155)/33)**2,0,1));h=np.where((y>=122)&(y<=188),.77+.20*rail,h)
 else:raise ValueError(name)
 h=np.array(Image.fromarray(h).resize((W,H),Image.Resampling.BILINEAR),np.float32)
 if Path(name).stem in CUTOUTS and f!=FENCE:
  # Anchor transparent pixels and a narrow opaque rim at zero displacement.
  # Cutout coverage remains in diffuse alpha; packed height alpha is unrelated.
  mask=(rgba[:,:,3]>=128).astype(np.uint8)
  dist=cv2.distanceTransform(np.pad(mask,1),cv2.DIST_L2,5)[1:-1,1:-1]
  weight=np.clip((dist-2)/max(4,min(H,W)*.018),0,1)
  h=1+(h-1)*weight
 return np.clip(h,0,1)
