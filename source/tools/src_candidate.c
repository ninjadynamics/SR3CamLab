/* Experimental SRC planar drivetrain/tyres inside SR3. Offline-reviewed core;
   native suspension/contact/collision are an explicit adapter boundary.
   Loaded by the normal PLAY helper only for the selected SRC handling mode. */
#include "srcport.c"
#include "src_suspension.h"
#include "src_ai_pace.h"

float candidate_engine_curve[104]; /* filled by builder from owner's SRC ROM */
typedef struct { float rpm, feedback, spin, pending; unsigned int gear, age; SrcSuspension suspension; } EngineState;
static EngineState engine_state[NSLOT];
/* SR3 first predicts a whole step with vehicle+0x48=0, saves its forces,
   then restores the body (0x44A7F0). Collision integration repeats the step
   with +0x48=1, replaying those forces. These calls are NOT additional time.
   Re-evaluate from the same SRC state on a replay; commit time only once. */
typedef struct {
    Slot slot; EngineState engine; u32 armed; float dt;
    float v[3], w[3];
    u32 rebase_beta, input_rebase;
} Prediction;
static Prediction prediction[NSLOT];

static void candidate_port(void *veh, float dt, const float *v0, const float *w0, u32 *rebase_beta)
{
    u8 *body=RD(veh,8,u8*), *drv=player_driver(veh);
    if (!drv || !body || dt<=0.0f || dt>0.1f || candidate_engine_curve[0]<=0.0f) return;
    u8 **list=RD(veh,0x2C,u8**);
    if (!list || RD(veh,0x30,u32)!=4) return;
    int on[4],n=0,road=0,cls=-1;float c[4],plane_world[4][4];
    for(int i=0;i<4;i++) {
        u8 *a=list[i]; if(!a)return;
        u8 *su=RD(a,0xC,u8*),*ty=RD(a,0x14,u8*);
        on[i]=su && RD(su,0x58,u32)!=0; n+=on[i];
        for(int j=0;j<4;j++)plane_world[i][j]=su?RD(su,0x5C+4*j,float):0;
        /* CVehicleSuspension +5C is the contact plane: n dot p + d = 0.
           Reject walls/invalid planes; never substitute native tyre support. */
        float nn=dot3(plane_world[i],plane_world[i]);
        if(on[i] && (!(nn>0.5f && nn<1.5f) || !(plane_world[i][1]>0.1f))){slot_of(veh)->valid=0;g.last_err=5;return;}
        u32 idx=ty?RD(ty,0x1C,u32):0xFFFFFFFF;
        u8 sc=idx<g.count && idx<NCLS?g.cls[idx]:0xFF;
        if(sc!=0xFF) {
            if(sc&0x80)road=1;
            if(on[i] && (cls<0 || PRIO[sc&3]>PRIO[cls]))cls=sc&3;
        }
    }
    if(!road){g.last_err=1;return;}
    Slot *st=slot_of(veh);EngineState *es=&engine_state[st-g.slot];
    u8 *fm=RD(veh,0x38,u8*),*gears=RD(veh,0x18,u8*);
    /* Native impact recovery and reverse remain native. No timer writes. */
    if((fm && RD(fm,0x24,u32)) || (gears && RD(gears,8,u32)==0)) {
        st->valid=0;st->last=g.steps;g.last_err=3;return;
    }
    if(!n){st->valid=0;st->last=g.steps;g.last_err=2;return;}
    float px=RD(body,0x88,float),pz=RD(body,0x90,float);
    if(st->valid && (px-st->px)*(px-st->px)+(pz-st->pz)*(pz-st->pz)>400.0f)st->valid=0;
    st->px=px;st->pz=pz;
    const float *native_forward=(float*)(body+0x104);
    float flat=fsqrt(native_forward[0]*native_forward[0]+native_forward[2]*native_forward[2]);
    if(flat<0.1f){slot_of(veh)->valid=0;g.last_err=5;return;}
    float az[3]={native_forward[0]/flat,0,native_forward[2]/flat};
    float ax[3]={az[2],0,-az[0]};
    const float *v1=(float*)(body+0x170),*w1=(float*)(body+0x17C);
    float vx=dot3(v0,ax)/g.fps,vz=dot3(v0,az)/g.fps,vy=v0[1]/g.fps;
    float w=-w0[1]/g.fps;
    /* A selected forward gear does not imply forward travel: a car can roll
       backwards downhill. The forward-only SRC tyre/engine branch must yield
       to native reverse motion in that case as well. */
    if(vz*g.fps < -0.1f){st->valid=0;st->last=g.steps;g.last_err=7;return;}
    float planes[4][4],ground=0,nx=0,nz=0,ny=0;
    for(int i=0;i<4;i++){
        planes[i][0]=dot3(plane_world[i],ax);planes[i][1]=plane_world[i][1];
        planes[i][2]=dot3(plane_world[i],az);
        planes[i][3]=on[i]?-(plane_world[i][0]*(px+v0[0]/g.fps)+plane_world[i][2]*(pz+v0[2]/g.fps)+plane_world[i][3])/plane_world[i][1]:0;
        if(on[i]){ground+=planes[i][3];nx+=planes[i][0];nz+=planes[i][2];ny+=planes[i][1];}
    }
    float counts=g.counts*((float)RD(drv,0x1C85,u8)-(float)RD(drv,0x1C84,u8))/255.0f;
    float throttle=(float)RD(drv,0x1C86,u8)/255.0f;
    int brake_byte=48+(int)(207.0f*(float)RD(drv,0x1C87,u8)/255.0f+0.5f);
    if(!st->valid) {
        *rebase_beta=0; /* initialization already seeds current slip */
        st->y=0.84f*clampf(counts,-80.0f,80.0f)/80.0f;st->lt=0.0f;
        st->beta=fsqrt(vx*vx+vz*vz)>0.01f?fasin(vx/fsqrt(vx*vx+vz*vz)):0.0f;
        es->gear=1;es->age=31;es->spin=0;es->feedback=0;es->pending=0;
        /* Rejoin after an impact/landing without a false first-gear launch. */
        static const float ratios[5]={0,10.5f,6.0f,4.95f,4.2f};
        float speed=fsqrt(vx*vx+vy*vy+vz*vz);
        while(es->gear<4 && speed*3600.0f/1.8849556f*ratios[es->gear]>7920.0f)es->gear++;
        es->rpm=clampf(speed*3600.0f/1.8849556f*ratios[es->gear],0,8800);
        SrcSuspension *ss=&es->suspension;
        ss->pitch=fatan2(-nz,ny);ss->roll=fatan2(nx,ny);
        ss->y=ground/n+0.4f-1.0f/12.0f;ss->vy=ss->wp=ss->wr=0;
        for(int i=0;i<4;i++)ss->c[i]=on[i]?1.0f/12.0f:0;

    }
    st->valid=1;st->last=g.steps;if(cls<0)cls=0;
    const Rec *R=&REC[cls];
    for(int i=0;i<4;i++)c[i]=es->suspension.c[i];
    es->pending+=dt*g.fps;
    float D=0,fyf=0,fyr=0,fxf=0,fxr=0,T=0,susp_yaw=0;
    int ticks=0,contact_repairs=0,slip_rebases=0;
    while(es->pending>=1.0f && ticks<6) {
        es->pending-=1.0f;ticks++;
        st->y=src_steering(counts,st->y,1.0f);float d=-st->y,sd=fsin(d),cd=fcos(d);
        float speed=fsqrt(vx*vx+vy*vy+vz*vz),sp2=fsqrt(vx*vx+vz*vz);
        float beta=sp2>0.01f?fasin(vx/sp2):0.0f;
        /* A native contact impulse changes slip instantaneously. It is already
           present in v0/w0, so SRC must not add a second yaw impulse from its
           previous slip history. Consume only on a real SRC tick. */
        float dbeta=*rebase_beta?0.0f:beta-st->beta;
        if(*rebase_beta){slip_rebases++;*rebase_beta=0;}
        st->beta=beta;
        es->gear=src_auto_gear(es->gear,&es->age,es->rpm,es->spin,throttle);
        static const float ratios[5]={0,10.5f,6.0f,4.95f,4.2f};float ratio=ratios[es->gear];
        float forward=-vx*sd+vz*cd;
        es->rpm=src_engine_rpm(es->rpm,speed,ratio,forward,es->feedback);
        es->spin=src_wheelspin(speed,es->rpm,ratio,forward);
        D=src_drive_force(speed,es->rpm,ratio,throttle,brake_byte,forward,G_SRC,candidate_engine_curve);
        float normal_force[3],normal_torque[3],wheel_delta[4][3];
        contact_repairs+=src_reconcile_grounded(&es->suspension,on,planes,w,vy);
        src_suspension_forces(&es->suspension,on,planes,vx,vz,w,cls==0?8.0f:3.0f,c,normal_force,normal_torque,wheel_delta);
        float Cf=c[0]+c[1],Cr=c[2]+c[3];
        float drive=(Cf*Cr>0.0f)?D:0.0f;
        st->lt=src_load_transfer(Cf,Cr,st->lt,R->lag_up,R->lag_dn,1.0f);
        float sl[2]={0,0},speedax[2]={0,0};int count[2]={0,0};
        for(int i=0;i<4;i++)if(on[i] && c[i]>0) {
            int a=i/2;float len,dx=wheel_delta[i][0],dy=wheel_delta[i][1],dz=wheel_delta[i][2];
            sl[a]+=slip(dx,dz,a?0.0f:-sd,a?1.0f:cd,&len);
            speedax[a]+=fsqrt(dx*dx+dy*dy+dz*dz);count[a]++;
        }
        for(int a=0;a<2;a++)if(count[a]){sl[a]/=count[a];speedax[a]/=count[a];}
        sl[0]=fabsf_(sl[0])<0.01f?0.0f:sl[0]-copysignf_(0.01f,sl[0]);
        float fm=G_SRC*1000.0f*(1.0f+0.3f*speed);
        if(Cf+Cr==0.0f)fm=0;
        fxf=R->share*drive;fxr=drive-fxf;
        fyf=count[0]?src_tyre(sl[0],speedax[0],fm*R->grip_f*(1+st->lt),2*PI/3,&fxf,1.2f,es->spin):(fxf=0,0);
        fyr=count[1]?src_tyre(sl[1],speedax[1],fm*R->grip_r*(1-st->lt),PI,&fxr,0.4f,es->spin):(fxr=0,0);
        if(fxf<0){fxr+=fxf;fxf=0;}
        es->feedback=src_engine_feedback(es->rpm,ratio,throttle,D,fxf+fxr);
        float xf=fyf*cd-fxf*sd,zf=fyf*sd+fxf*cd;
        float r14=fxf>0 && Cf>0?1.1f*(c[1]-c[0])/Cf:0;
        float r13=fxr>0 && Cr>0?1.1f*(c[3]-c[2])/Cr:0;
        T=1.25f*(fyr-xf)+0.66f*r13*fxr-0.635f*r14*fxf;
        susp_yaw=normal_torque[1];
        w=src_yaw(w,T+susp_yaw,dbeta,R->kb,R->kw,1.0f);
        src_suspension_advance(&es->suspension,normal_force,normal_torque,fyr+xf,fxr+zf,
            (c[0]>0)|(c[1]>0)<<1|(c[2]>0)<<2|(c[3]>0)<<3);
        vx+=(fyr+xf+normal_force[0])/1000.0f;vz+=(fxr+zf+normal_force[2])/1000.0f;
        vx*=0.997f;vz*=0.997f;
        float sp=fsqrt(vx*vx+vz*vz);if(sp>1.157f){vx*=1.157f/sp;vz*=1.157f/sp;}
    }
    float V[3]={ (vx*ax[0]+vz*az[0])*g.fps,v1[1],(vx*ax[2]+vz*az[2])*g.fps };
    float W[3]={w1[0],-w*g.fps,w1[2]};
    /* Fail closed to native motion if any adapter input produced a nonfinite result. */
    for(int j=0;j<3;j++)if(!(V[j]>=-1000 && V[j]<=1000 && W[j]>=-100 && W[j]<=100)){st->valid=0;g.last_err=4;return;}
    float *t=g.log[g.log_pos%NLOG].t;
    for(int i=0;i<40;i++)t[i]=0;
    t[0]=(float)g.player_steps;t[1]=dt;t[2]=counts;t[3]=st->y;t[4]=vx;t[5]=vz;t[6]=w;t[7]=st->beta;
    t[8]=es->suspension.pitch;t[9]=es->suspension.roll;t[10]=es->suspension.y;t[11]=es->suspension.vy;t[12]=susp_yaw;
    t[13]=fyf;t[14]=fyr;t[15]=fxf;t[16]=fxr;t[17]=T;t[18]=st->lt;t[20]=(float)cls;
    t[21]=(float)(on[0]|on[1]<<1|on[2]<<2|on[3]<<3);
    for(int i=0;i<4;i++)t[22+i]=c[i];
    t[32]=(float)RD(veh,0x48,u32);t[33]=px;t[34]=pz;t[35]=es->pending;t[36]=(float)contact_repairs;t[37]=(float)slip_rebases;
    t[26]=D;t[27]=es->rpm;t[28]=(float)es->gear;t[29]=es->spin;t[30]=(float)ticks;t[31]=es->feedback;
    g.log_pos++;g.player_steps++;g.last_err=0;
    if(!(es->suspension.pitch>=-1.6f && es->suspension.pitch<=1.6f && es->suspension.roll>=-1.6f && es->suspension.roll<=1.6f && es->suspension.y-ground/n>-3 && es->suspension.y-ground/n<3)){
        st->valid=0;g.last_err=6;return;
    }
    if(g.mode>=2){SET_VELOCITY(body,V);SET_ANGULAR(body,W);}
}

__attribute__((thiscall)) void candidate_step(void *veh,float dt)
{
    u8 *body=RD(veh,8,u8*);float v[3]={0,0,0},w[3]={0,0,0};
    u32 replay=RD(veh,0x48,u32);
    if(body)for(int j=0;j<3;j++){v[j]=RD(body,0x170+j*4,float);w[j]=RD(body,0x17C+j*4,float);}
    SrcAiPaceSnapshot ai_pace=src_ai_pace_begin(veh,replay);
    VEHICLE_STEP(veh,dt);
    src_ai_pace_end(&ai_pace);
    src_ai_pace_govern(veh,dt,v);
    g.steps++;
    u32 mode=*(u32*)0x728598;
    if(!g.mode || !body || !(mode==5 || mode==6 || mode==7) || *(u32*)0x7ECE10!=0x27 || *(u32*)0x9EB390 || !player_driver(veh)) {
        for(u32 j=0;j<NSLOT;j++)if(prediction[j].slot.veh==veh){
            prediction[j].armed=prediction[j].rebase_beta=prediction[j].input_rebase=0;
        }
        return;
    }
    Slot *st=slot_of(veh);u32 ix=st-g.slot;
    EngineState *es=&engine_state[ix];Prediction *pr=&prediction[ix];
    if(!replay) {
        if(!st->valid || pr->slot.veh!=veh)pr->rebase_beta=0;
        pr->slot=*st;pr->engine=*es;pr->armed=1;pr->dt=dt;
        pr->input_rebase=pr->rebase_beta;
        for(int j=0;j<3;j++){pr->v[j]=v[j];pr->w[j]=w[j];}
        candidate_port(veh,dt,v,w,&pr->rebase_beta);
        if(!st->valid || g.last_err)pr->rebase_beta=0;
    } else if(pr->armed && pr->slot.veh==veh) {
        /* Native wall/contact resolution can alter a retry's planar input.
           Ignore vertical suspension, pitch and roll: those remain native and
           are not evidence that planar slip was changed by a collision. */
        u32 changed=fabsf_(v[0]-pr->v[0])>0.00001f ||
                    fabsf_(v[2]-pr->v[2])>0.00001f ||
                    fabsf_(w[1]-pr->w[1])>0.00001f;
        u32 rebase=pr->input_rebase || changed;
        Slot committed=*st;EngineState committed_engine=*es;
        *st=pr->slot;*es=pr->engine;
        candidate_port(veh,pr->dt,v,w,&rebase);
        if(!st->valid || g.last_err){
            pr->rebase_beta=0;
            /* A collision retry can hand off to native reverse/impact motion.
               Do not restore stale slip when SRC resumes on a later step. */
            if(changed)committed.valid=0;
        } else if(changed)pr->rebase_beta=1;
        *st=committed;*es=committed_engine;
    }
}
