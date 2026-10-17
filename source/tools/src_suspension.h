/* SRC spring/damper and sprung-body state for the test adapter.
   Ground planes come from SR3; this state does not move SR3's collision body.
   Original: 0x37200, 0x35E2C..36350, 0x36760..36A5C. */
typedef struct { float y, vy, pitch, roll, wp, wr, c[4]; } SrcSuspension;

static void src_wheel_point(int i,float pitch,float roll,float *v)
{
    float x=(i&1?1.0f:-1.0f)*(i<2?0.635f:0.66f),y=-0.4f,z=i<2?1.25f:-1.25f;
    float cr=fcos(roll),sr=fsin(roll),cp=fcos(pitch),sp=fsin(pitch);
    v[0]=x*cr+y*sr;
    float yr=-x*sr+y*cr;
    v[1]=yr*cp+z*sp;v[2]=-yr*sp+z*cp;
}

static float src_spring(float depth,float previous,float damper)
{
    if(depth<=0)return 0;
    float c=clampf(depth,0,0.2f);
    /* Spring * depth * 100 * G; bump stop uses the mass; damping is
       (new compression - old compression) * damper * G * 3600. */
    float force=30.0f*depth*100.0f*G_SRC;
    if(depth>0.2f)force+=(depth-0.2f)*1000.0f*G_SRC;
    force+=(c-previous)*damper*G_SRC*3600.0f;
    return force>0?force:0;
}

/* planes[i] = normal in the current flat yaw frame, and ground height at
   the predicted centre. Return world-horizontal (yaw-local) normal forces,
   body torques, and predicted wheel displacements for original slip. */
static void src_suspension_forces(SrcSuspension *s,const int *on,
    const float planes[4][4],float vx,float vz,float yaw,float damper,
    float c[4],float forces[3],float torque[3],float wheel_delta[4][3])
{
    float bf[4][3];float cp=fcos(s->pitch),sp=fsin(s->pitch),cr=fcos(s->roll),sr=fsin(s->roll);
    float cw=fcos(yaw),sw=fsin(yaw);
    for(int k=0;k<3;k++)forces[k]=torque[k]=0;
    for(int i=0;i<4;i++){
        float a[3],b[3];src_wheel_point(i,s->pitch,s->roll,a);
        src_wheel_point(i,s->pitch+s->wp,s->roll+s->wr,b);
        float bx=b[0]*cw-b[2]*sw,bz=b[0]*sw+b[2]*cw;
        wheel_delta[i][0]=vx+bx-a[0];wheel_delta[i][1]=s->vy+b[1]-a[1];wheel_delta[i][2]=vz+bz-a[2];
        float depth=on[i]?planes[i][3]-(planes[i][0]*bx+planes[i][2]*bz)/planes[i][1]-(s->y+s->vy+b[1]):0;
        c[i]=clampf(depth,0,0.2f);
        float f=on[i]?src_spring(depth,s->c[i],damper):0;
        s->c[i]=c[i];
        float fx=f*planes[i][0],fy=f*planes[i][1],fz=f*planes[i][2];
        forces[0]+=fx;forces[1]+=fy;forces[2]+=fz;
        /* Inverse pitch then inverse roll, matching inverse TGP body rotation. */
        float yp=fy*cp-fz*sp,zp=fy*sp+fz*cp;
        bf[i][0]=fx*cr-yp*sr;bf[i][1]=fx*sr+yp*cr;bf[i][2]=zp;
    }
    torque[0]=1.35f*(bf[0][1]+bf[1][1]-bf[2][1]-bf[3][1]);
    torque[1]=1.35f*(bf[2][0]+bf[3][0]-bf[0][0]-bf[1][0])
             +0.635f*(bf[1][2]-bf[0][2])+0.66f*(bf[3][2]-bf[2][2]);
    torque[2]=0.635f*(bf[0][1]-bf[1][1])+0.66f*(bf[2][1]-bf[3][1]);
    for(int i=0;i<4;i++){torque[0]+=0.2f*bf[i][2];torque[2]-=0.2f*bf[i][0];}
}

static void src_suspension_advance(SrcSuspension *s,const float *forces,const float *torque,
    float tyre_x,float tyre_z,unsigned mask)
{
    s->wp=clampf(s->wp+(torque[0]+0.2f*tyre_z)/1146.0f,-0.1f,0.1f);
    s->wr=clampf(s->wr+(torque[2]-0.2f*tyre_x)/300.0f,-0.1f,0.1f);
    /* Original attitude levelling only when fewer than all four wheels touch. */
    if(mask!=15){
        if(s->roll*s->wr>=0)s->roll-=copysignf_(0.3f*s->roll*s->roll,s->roll);
        s->pitch-=copysignf_(0.42f*s->pitch*s->pitch,s->pitch);
    }
    s->vy+=forces[1]/1000.0f-G_SRC;s->y+=s->vy;
    s->pitch+=s->wp;s->roll+=s->wr;
}
