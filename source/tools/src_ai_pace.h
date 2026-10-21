#ifndef SRC_AI_PACE_H
#define SRC_AI_PACE_H
/* SRC opponent pace. Include after srcport.c. The engine correction below is
   complemented by a grounded, forward-only output envelope. Native steering,
   contact losses, lateral/vertical motion and angular velocity are retained.

   Exact Rally.exe 3.8.4.1 roles (not the common car-object vtable):
     controller=[record+300], controller+4=record, controller+10=role.
     role1/vt6ED488: local hardware; role2/vt6ED158: offline AI.
     role3/vt6ED49C: network local hardware; role4/vt6ED49C: local network AI.
     roles5/6: remote/network playback; role7: other playback. Leave untouched.
   Constructors 5E5E30/5E5EB0, setup5CB4C2/5CB518, dispatch5EAE80.

   5EA08F rewrites engine peak from car+8700*(1+car+86FC) every update.
   A fresh CVehicle step45C820 ->44F5F0->44D570->450D80 reads engine+3C;
   44D5C2 also reads gearbox+28. 45C480 caches the resulting native forces.
   Replay(+48!=0) uses45C580, so it must replay those forces without re-scaling.
   Begin/end bracket only the native step, restoring the engine field exactly.
   Do NOT temporarily change gearbox+28: 467DF2 reads it again in the constraint
   solver on cached-force replays, outside the fresh engine calculation.

   Initial fairness settings, requiring drive validation: remove the SRC file's
   2.5x native torque scale and positive catch-up power, retain negative
   AI pacing, then smoothly reduce forward engine power from195 to205km/h.
   This is a power taper, not a hard speed cap: coasting/downhill are still native.
*/
#define SRC_AI_FILE_TORQUE_UNSCALE 0.4f
#define SRC_AI_TAPER_START_KMH 195.0f
#define SRC_AI_TAPER_END_KMH 205.0f

/* One bounded read by the existing recorder each second; no I/O, allocation,
   clock calls or extra hooks in the physics callback. Floats are raw IEEE bits.
   Guards are observable so a rejected live object cannot masquerade as a tune. */
typedef struct {
    u32 role, controller_vt, car_vt, links_valid;
    u32 vehicle_vt, engine_vt, gears_vt, last_reason;
    u32 applied, peak_bits, base_bits, limited_bits;
    u32 factor_bits, kmh_bits, reserved[2];
} SrcAiPaceRow;
typedef struct {
    u32 steps, limited;
    float before_kmh, native_kmh, after_kmh, allowance_mps2;
} SrcAiEnvelopeRow;
struct {
    u32 magic, version, calls, reason[12];
    SrcAiPaceRow row[6];
    SrcAiEnvelopeRow envelope[6];
} src_ai_pace_diagnostics={0x50414953,2,0,{0},{{0}},{{0}}};
/* reason: 0 applied, 1 replay, 2 disabled, 3 race state, 4 vehicle class,
   5 local SRC proof, 6 AI ownership, 7 engine/gears, 8 power range,
   9 velocity range, 10 orientation/reverse, 11 reserved. */
static void src_ai_pace_reason(u32 reason, SrcAiPaceRow *row)
{
    src_ai_pace_diagnostics.reason[reason]++;
    if(row)row->last_reason=reason;
}

typedef struct {
    u8 *engine, *gears;
    u32 engine_peak_bits, gear_factor_bits;
    SrcAiPaceRow *row;
} SrcAiPaceSnapshot;

static u8 *src_ai_pace_car(u8 *rec, u32 local_human)
{
    u8 *controller=RD(rec,0x300,u8*), *car=RD(rec,4,u8*);
    SrcAiPaceRow *row=&src_ai_pace_diagnostics.row[((u32)rec-0x9DBAC8)/0x1F18];
    row->role=controller?RD(controller,0x10,u32):0;
    row->controller_vt=controller?RD(controller,0,u32):0;
    row->car_vt=car?RD(car,0,u32):0;
    row->links_valid=controller && car && row->car_vt==0x6ED0C8 && RD(controller,4,u8*)==rec && RD(car,0x7E4,u8*)==rec;
    if(!controller || !car ||
       RD(controller,4,u8*)!=rec || RD(car,0,u32)!=0x6ED0C8 ||
       RD(car,0x7E4,u8*)!=rec) return 0;
    u32 role=RD(controller,0x10,u32),vt=RD(controller,0,u32);
    if(local_human) {
        if(!((role==1 && vt==0x6ED488)||(role==3 && vt==0x6ED49C)))return 0;
    } else if(!((role==2 && vt==0x6ED158)||(role==4 && vt==0x6ED49C)))return 0;
    return car;
}

static u8 *src_ai_pace_vehicle(u8 *car)
{
    u8 *wrapper=RD(car,0x858,u8*);
    u8 *vehicle=wrapper?RD(wrapper,4,u8*):0;
    u32 record=(u32)RD(car,0x7E4,u8*);
    if(record>=0x9DBAC8 && record<0x9DBAC8+6*0x1F18 && (record-0x9DBAC8)%0x1F18==0)
        src_ai_pace_diagnostics.row[(record-0x9DBAC8)/0x1F18].vehicle_vt=vehicle?RD(vehicle,0,u32):0;
    return vehicle && RD(vehicle,0,u32)==0x678864?vehicle:0;
}

static u32 src_ai_pace_local_src(void)
{
    /* Positive local SRC proof. Do not infer human ownership from record0 or
       the common car vtable, and do not infer SRC from the AI tyre family.
       Sync-RaceFlavor selects SRC race-wide through the car-file path hook at
       5C6144. It does not write record+2E0; that field is NOT a flavor guard.
       The locally controlled human's four Tyre_Road definitions plus active
       SRC candidate mode establish the installed same-race SRC profile. */
    for(u32 r=0;r<6;r++) {
        u8 *rec=(u8*)0x9DBAC8+0x1F18*r;
        u8 *car=src_ai_pace_car(rec,1);
        if(!car)continue;
        u8 *vehicle=src_ai_pace_vehicle(car);
        if(!vehicle || RD(vehicle,0x30,u32)!=4)continue;
        u8 **wheels=RD(vehicle,0x2C,u8**);
        if(!wheels)continue;
        u32 road=0;
        for(u32 i=0;i<4;i++) {
            u8 *wheel=wheels[i],*tyre=wheel?RD(wheel,0x14,u8*):0;
            if(!tyre)break;
            u32 ix=RD(tyre,0x1C,u32);
            if(ix>=g.count || ix>=NCLS || g.cls[ix]==0xFF || !(g.cls[ix]&0x80))break;
            road++;
        }
        if(road==4)return 1;
    }
    return 0;
}

static SrcAiPaceSnapshot src_ai_pace_begin(void *veh,u32 replay)
{
    SrcAiPaceSnapshot s={0,0,0,0,0};
    src_ai_pace_diagnostics.calls++;
    u32 mode=*(u32*)0x728598;
    if(replay){src_ai_pace_reason(1,0);return s;}
    if(g.mode<2){src_ai_pace_reason(2,0);return s;}
    if(!(mode==5 || mode==6 || mode==7) || *(u32*)0x7ECE10!=0x27 || *(u32*)0x9EB390){src_ai_pace_reason(3,0);return s;}
    if(!veh || RD(veh,0,u32)!=0x678864){src_ai_pace_reason(4,0);return s;}
    if(!src_ai_pace_local_src()){src_ai_pace_reason(5,0);return s;}
    u8 *car=0;
    SrcAiPaceRow *row=0;
    for(u32 i=0;i<6;i++) {
        u8 *candidate=src_ai_pace_car((u8*)0x9DBAC8+0x1F18*i,0);
        if(candidate && src_ai_pace_vehicle(candidate)==veh){car=candidate;row=&src_ai_pace_diagnostics.row[i];break;}
    }
    if(!car){src_ai_pace_reason(6,0);return s;}
    u8 *engine=RD(veh,0x10,u8*),*gears=RD(veh,0x18,u8*),*body=RD(veh,8,u8*);
    row->vehicle_vt=RD(veh,0,u32);
    row->engine_vt=engine?RD(engine,0,u32):0;
    row->gears_vt=gears?RD(gears,0,u32):0;
    if(!engine || !gears || !body || RD(engine,0,u32)!=0x6780A4 ||
       RD(engine,0x30,void*)!=veh || RD(gears,0,u32)!=0x677FDC ||
       RD(gears,4,void*)!=veh || RD(gears,8,u32)<2){src_ai_pace_reason(7,row);return s;}
    float peak=RD(engine,0x3C,float),base=RD(car,0x8700,float),factor=RD(gears,0x28,float);
    row->peak_bits=RD(engine,0x3C,u32);row->base_bits=RD(car,0x8700,u32);row->factor_bits=RD(gears,0x28,u32);
    if(!(base>=100 && base<=10000 && peak>=0 && peak<=100000.0f && factor>=0.1f && factor<=10)){src_ai_pace_reason(8,row);return s;}
    const float *v=(const float*)(body+0x170),*forward=(const float*)(body+0x104);
    for(u32 i=0;i<3;i++)if(!(v[i]>=-2000 && v[i]<=2000 && forward[i]>=-1.01f && forward[i]<=1.01f)){src_ai_pace_reason(9,row);return s;}
    float nn=dot3(forward,forward);
    if(!(nn>=0.8f && nn<=1.2f) || dot3(v,forward)<-0.1f){src_ai_pace_reason(10,row);return s;}
    float kmh=fsqrt(v[0]*v[0]+v[2]*v[2])*3.6f;
    float t=clampf((kmh-SRC_AI_TAPER_START_KMH)/(SRC_AI_TAPER_END_KMH-SRC_AI_TAPER_START_KMH),0,1);
    float taper=1-t*t*(3-2*t);
    s.engine=engine;s.gears=gears;s.row=row;
    s.engine_peak_bits=RD(engine,0x3C,u32);s.gear_factor_bits=RD(gears,0x28,u32);
    RD(engine,0x3C,float)=(peak<base?peak:base)*SRC_AI_FILE_TORQUE_UNSCALE*taper;
    row->limited_bits=RD(engine,0x3C,u32);
    union {float f;u32 u;} speed_bits;speed_bits.f=kmh;row->kmh_bits=speed_bits.u;
    row->applied++;src_ai_pace_reason(0,row);
    return s;
}

static void src_ai_pace_end(const SrcAiPaceSnapshot *s)
{
    if(s->engine) {
        u8 *vehicle=RD(s->engine,0x30,u8*),*diff=RD(vehicle,0x24,u8*);
        s->row->reserved[0]=RD(s->engine,0x1C,u32);
        s->row->reserved[1]=diff?RD(diff,8,u32):0;
        RD(s->engine,0x3C,u32)=s->engine_peak_bits;
    }
}

/* The real-race trace 20261021-122852-3f4b46 reached 245.9 km/h with the
   temporary combustion peak already zero. Engine torque alone is therefore
   not a verified bound on AI propulsion. Bound actual longitudinal gain after
   native integration, using its SetVelocity so momentum stays synchronized.

   These conservative knots are below the accepted SRC player's level-road
   launch/acceleration fixture (0-100 ~1.32 s, equilibrium ~204.92 km/h).
   This is opponent balance, not a verbatim port of SRC AI physics. At 200 km/h
   level-road propulsion is zero; existing overspeed settles at <=3 m/s^2.
   Grade acceleration remains available. We never add speed to a slower AI.

   Stateless per-call evaluation is deliberate: native predictions are thrown
   away and collision passes replay the same time. Re-evaluating from each
   pass's actual incoming velocity preserves contact losses without accumulating
   a limiter clock or reusing a stale pre-impact speed. */
static float src_ai_acceleration_allowance(float kmh)
{
    static const float speed[]={0,40,80,100,120,140,160,180,190,195,200};
    static const float accel[]={13,18,15,13,9,7,5.5f,3.2f,2,1,0};
    if(kmh>=200)return -clampf((kmh-200)/3.6f,0,3);
    for(u32 i=1;i<11;i++)if(kmh<speed[i]){
        float t=clampf((kmh-speed[i-1])/(speed[i]-speed[i-1]),0,1);
        return accel[i-1]+t*(accel[i]-accel[i-1]);
    }
    return 0;
}

static void src_ai_pace_govern(void *veh,float dt,const float *before)
{
    u32 mode=*(u32*)0x728598;
    if(g.mode<2 || !(mode==5 || mode==6 || mode==7) ||
       *(u32*)0x7ECE10!=0x27 || *(u32*)0x9EB390 ||
       !veh || RD(veh,0,u32)!=0x678864 || !src_ai_pace_local_src())return;
    u8 *car=0;u32 record=0;
    for(u32 i=0;i<6;i++){
        u8 *candidate=src_ai_pace_car((u8*)0x9DBAC8+0x1F18*i,0);
        if(candidate && src_ai_pace_vehicle(candidate)==veh){car=candidate;record=i;break;}
    }
    if(!car)return;
    u8 *body=RD(veh,8,u8*),*gears=RD(veh,0x18,u8*);
    u8 **wheels=RD(veh,0x2C,u8**);
    if(!body || !gears || RD(gears,0,u32)!=0x677FDC || RD(gears,4,void*)!=veh ||
       RD(gears,8,u32)<2 || !wheels || RD(veh,0x30,u32)!=4)return;
    /* Replays use the native cached substep duration, not their call argument. */
    if(RD(veh,0x48,u32)){
        u32 steps=RD(veh,0x4C,u32);
        if(!steps || steps>128)return;
        dt=RD(veh,0x50,float)*(float)steps;
    }
    float mass=RD(body,8,float);
    if(!(dt>0 && dt<=0.1f && mass>=100 && mass<=10000))return;
    const float *forward=(const float*)(body+0x104),*native=(const float*)(body+0x170);
    for(u32 j=0;j<3;j++)if(!(before[j]>=-2000 && before[j]<=2000 &&
       native[j]>=-2000 && native[j]<=2000 && forward[j]>=-1.01f && forward[j]<=1.01f))return;
    float nn=dot3(forward,forward),flat=fsqrt(forward[0]*forward[0]+forward[2]*forward[2]);
    if(!(nn>=0.8f && nn<=1.2f && flat>=0.5f))return;
    float fx=forward[0]/flat,fz=forward[2]/flat;
    float v0=before[0]*fx+before[2]*fz,v1=native[0]*fx+native[2]*fz;
    if(v0<0 || v1<0)return;
    float nx=0,ny=0,nz=0;u32 contacts=0;
    for(u32 i=0;i<4;i++){
        u8 *a=wheels[i],*su=a?RD(a,0xC,u8*):0;
        if(!su || !RD(su,0x58,u32))continue;
        const float *n=(const float*)(su+0x5C);
        float n2=dot3(n,n);
        if(!(n2>=0.8f && n2<=1.2f && n[1]>=0.5f))return;
        nx+=n[0];ny+=n[1];nz+=n[2];contacts++;
    }
    if(contacts<2)return; /* Airborne/reverse motion stays entirely native. */
    float grade=clampf((nx*fx+nz*fz)/ny,-0.5f,0.5f);
    float allowance=src_ai_acceleration_allowance(v0*3.6f)+9.81f*grade/(1+grade*grade);
    float limit=v0+allowance*dt;
    if(limit<0)limit=0;
    SrcAiEnvelopeRow *r=&src_ai_pace_diagnostics.envelope[record];
    r->steps++;r->before_kmh=v0*3.6f;r->native_kmh=v1*3.6f;
    r->after_kmh=r->native_kmh;r->allowance_mps2=allowance;
    if(v1<=limit)return; /* Never restore speed lost to braking/contact. */
    float excess=v1-limit;
    float result[3]={native[0]-excess*fx,native[1],native[2]-excess*fz};
    SET_VELOCITY(body,result);
    r->limited++;r->after_kmh=(result[0]*fx+result[2]*fz)*3.6f;
}
#endif
