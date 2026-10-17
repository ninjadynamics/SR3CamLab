import sys, numpy as np, pickle
from PIL import Image
R='game/'; A=sys.argv[1]; D=np.load(R+A+'/asbuilt.npz'); P=D['P'].astype(float); U1=D['U1']; LMP=D['LMP']; ONE=D['ONE']; CUT=D['CUT']; G=pickle.load(open(R+'faces.pkl','rb')); rd=G['rd']; ox,oz=float(rd['ox']),float(rd['oz'])
lo=np.array([-309-ox,62,-(174-oz)]); hi=np.array([-297-ox,89.5,-(162-oz)]); c=P.mean(1); m=(c>=lo).all(1)&(c<=hi).all(1)&(P[:,:,1].min(1)<70)&CUT&(LMP>=0)
ctr=np.array([-303-ox,0,-(168-oz)]); pages={}; SUNc=np.array([0.0,0.94,0.34]); print(A,'tower wall triangles with a light map:',int(m.sum()))
for i in np.nonzero(m)[0]:
    n=np.cross(P[i,1]-P[i,0],P[i,2]-P[i,0]); n/=np.linalg.norm(n); out=c[i]-ctr; out[1]=0; pg=int(LMP[i])
    if pg not in pages: pages[pg]=np.asarray(Image.open(R+A+'/tex/%08x.png'%pg).convert('RGB')).astype(float)/255
    im=pages[pg]; H,W=im.shape[:2]; b=np.random.RandomState(1).dirichlet([1,1,1],400); q=b@U1[i]; val=im[np.clip(((1-q[:,1])*H).astype(int),0,H-1),np.clip((q[:,0]*W).astype(int),0,W-1)].mean()
    print('  front normal %s = %-7s ; one-sided %s ; turned to the sun %-5s ; light value %.2f ; page %x uv %s .. %s'%(n.round(1),'OUTSIDE' if n@out>0 else 'inside',bool(ONE[i]),bool(n@SUNc>0.02),val,pg&0xffff,(U1[i].min(0)*np.array([W,H])).round(0),(U1[i].max(0)*np.array([W,H])).round(0)))
