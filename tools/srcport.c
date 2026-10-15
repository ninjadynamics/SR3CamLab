/* srcport.c - SEGA Rally Championship (1995) turning inside SEGA Rally 3 (Rally.exe 3.8.4.1), "option B".

   After every SR3 vehicle physics step, a car on the SRC handling gets its yaw rate and its sideways velocity from
   SRC's own equations (docs\kb\29_src_steering_code.md, read from the Model 2 program), fed with SR3's own speed,
   surface and suspension state. SR3 keeps the speed along the car (engine, brakes, the SRC files' torque and gears),
   the vertical motion, pitch and roll, walls and the air.

   Built by tools\build_srcport.py (clang, i686, freestanding) into a blob that sr3mods.ps1 puts in memory; the hook is
   CVehicle's vtable 0x678864 slot 5 (entry 0x678878 = 0x45C820, the vehicle step, thiscall, one float: dt in s).

   SR3 objects (static reading of Rally.exe, 2026-10-15; docs\kb\28_handling_flavors.md):
     vehicle (CVehicle): +0x08 body, +0x28 controls (+8 steering value, the fraction of the lock), +0x2C wheel list,
                         +0x30 wheel count (4: front left, front right, rear left, rear right; x < 0 = left)
     wheel list[i]:      +0x0C suspension (+0x58 in contact, +0x8C compression), +0x10 wheel (+0x184 lock, rad),
                         +0x14 tyre (+0x1C index of its surface-pair record in the grip file)
     body (CRigidBody3D): +0x170 velocity (m/s, world), +0x17C angular velocity (rad/s, world), +0xEC / +0xF8 / +0x104
                         the body's up / x (right) / z (forward) axes in the world; 0x45A120 SetVelocity(&v),
                         0x45A1A0 SetAngularVelocity(&w) (thiscall, set the momenta too)
     gravity:            [0x78340C] vec3 (the force sum adds mass x this)
     the vehicle step 0x45C820 restores the body's position and orientation at its end: the pose is moved later, by
     the collision code, from the velocities this routine leaves.
   The player: car records 0x9DBAC8 + 0x1F18 x i, record + 4 = driver; the human driver has vtable 0x6ED0C8, driver +
   0x7E4 = its record, [[driver + 0x858] + 4] = its CVehicle, pad steering bytes driver + 0x1C84 (left) / + 0x1C85
   (right), 0..255 each.

   SRC (kb 29) works per frame in metres, frames and radians with the car's mass 1000 and yaw inertia 1146; the
   cabinet runs 57.5 frames a second. One SR3 step of dt seconds is k = dt x FPS SRC frames; the per-frame rules are
   applied for k frames (lags and damping as powers of k, forces x k).  Directions: SRC's body x = SR3's x (right),
   SRC's z = SR3's z (forward); SRC's yaw rate is positive to the left: w_src = -(omega . up) / FPS. */

typedef unsigned int u32;
typedef unsigned char u8;

#define NSLOT 8
#define NLOG 256
#define NCLS 128

typedef struct { float t[40]; } LogRec;

typedef struct {
    void *veh;
    float y, beta, lt;
    u32 last, valid;
    float px, pz;                    /* where the car was at its last step: a jump of more than 20 m (a new race, the car
                                        put back on the road) starts SRC's state afresh */
} Slot;

typedef struct {
    u32 magic, version;              /* +0x00 'SRCP', 1 */
    u32 mode;                        /* +0x08 0 off, 1 observe (compute and log, change nothing), 2 on */
    u32 ai;                          /* +0x0C 0 the player's car only, 1 every car on the SRC files */
    float fps;                       /* +0x10 SRC frames per second (57.5, the cabinet) */
    float counts;                    /* +0x14 SRC steering counts at full stick (95: the pad's range in SRC) */
    float half_track_f, half_track_r;/* +0x18 / +0x1C SRC wheel offsets 0.635 / 0.66 (0 = the axle centres) */
    float axle;                      /* +0x20 1.25 */
    u32 off_contact;                 /* +0x24 suspension + 0x58 */
    u32 off_comp;                    /* +0x28 suspension + 0x8C */
    float comp_scale, comp_add;      /* +0x2C / +0x30 compression = scale x field + add */
    u32 need_road_tyre;              /* +0x34 1: only a car whose tyres stand on Tyre_Road records (the SRC files) */
    u32 scrub;                       /* +0x38 1: the front tyres' side force slows the car (SRC's Fy_f sin d) */
    float x_sign;                    /* +0x3C +1: the body's x axis (+0xF8) is the car's right */
    float yaw_sign;                  /* +0x40 +1: a positive yaw rate (omega . up) turns the nose toward +x */
    float use_gravity;               /* +0x44 1: SR3's gravity [0x78340C] along the car's x pushes it sideways, and
                                        is taken out of SR3's change of speed when that becomes SRC's drive force */
    u32 count;                       /* +0x48 the number of entries in cls */
    float ai_gain;                   /* +0x4C a computer car's steering value (controls + 8, a fraction of SR3's lock) is
                                        taken as SRC's stick x this: 1.8 gives SRC's small-stick yaw gain per value
                                        about what SR3's own turning gives per value (3.7 rad/s at 120-150 km/h,
                                        kb 28), so the AI's own steering controller sees a familiar car */
    u8 cls[NCLS];                    /* +0x50 per surface-pair record: bit 7 a Tyre_Road record, bits 0-1 SRC's record
                                        (0 A tarmac, 1 B gravel / dirt, 2 C water, 3 D verge), 0xFF unknown */
    u32 steps, player_steps, log_pos;/* +0xD0 counters; log_pos = the next record written (modulo NLOG) */
    u32 last_err;                    /* +0xDC why the last player step was skipped (0 = run, 1 not on the SRC files,
                                        2 no wheel on the ground, 3 SR3's hit recovery) */
    Slot slot[NSLOT];                /* +0xE0 */
    LogRec *log;                     /* +0x1E0 the player's steps, NLOG records of 40 floats (in the zero-filled area
                                        after the blob: the launcher allocates 0x10000 bytes, the blob is smaller) */
} Data;

_Static_assert(__builtin_offsetof(Data, cls) == 0x50, "layout");
_Static_assert(__builtin_offsetof(Data, steps) == 0xD0, "layout");
_Static_assert(__builtin_offsetof(Data, slot) == 0xE0, "layout");
_Static_assert(__builtin_offsetof(Data, log) == 0x1E0, "layout");
_Static_assert(sizeof(Slot) == 32, "layout");


static LogRec glog[NLOG];
Data g = {
    0x50435253, 1, 2, 0, 57.5f, 95.0f, 0.635f, 0.66f, 1.25f, 0x58, 0x8C, 1.0f, 0.0f, 1, 1, 1.0f, 1.0f, 1.0f, 0, 1.8f,
    .log = glog,
};

/* SRC's four surface records (kb 29 section 5): grip front, grip rear, front drive share, yaw damping on d(beta), on
   the yaw rate, load-transfer lag rising, falling */
typedef struct { float grip_f, grip_r, share, kb, kw, lag_up, lag_dn; } Rec;
static const Rec REC[4] = {
    {1.3f, 1.3f, 0.25f, 0.07f, 0.07f, 0.10f, 0.4f},   /* A tarmac (codes 0, 1, 8, 9) */
    {1.1f, 1.1f, 0.25f, 0.07f, 0.07f, 0.05f, 0.4f},   /* B gravel, dirt (2, 3, 10-15) */
    {0.5f, 0.5f, 0.25f, 0.07f, 0.07f, 0.10f, 0.4f},   /* C water (4, 5) */
    {1.2f, 1.2f, 0.23f, 0.07f, 0.07f, 0.10f, 0.4f},   /* D verge (6, 7) */
};
static const u8 PRIO[4] = {0, 1, 2, 3};               /* SRC: the highest code under any wheel wins: D > C > B > A */

#define PI 3.14159265358979f
#define G_SRC (9.81f / 3500.0f)

static float fsqrt(float x) { return x > 0.0f ? __builtin_sqrtf(x) : 0.0f; }
static float fabsf_(float x) { return x < 0.0f ? -x : x; }
static float clampf(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }
static float copysignf_(float m, float s) { m = fabsf_(m); return s < 0.0f ? -m : m; }
static float fsin(float x) { float r; __asm__("fsin" : "=t"(r) : "0"(x)); return r; }
static float fcos(float x) { float r; __asm__("fcos" : "=t"(r) : "0"(x)); return r; }
static float fatan2(float y, float x) { float r; __asm__("fpatan" : "=t"(r) : "0"(x), "u"(y) : "st(1)"); return r; }
static float fasin(float x) { x = clampf(x, -1.0f, 1.0f); return fatan2(x, fsqrt(1.0f - x * x)); }
/* b^k for b > 0: 2^(k log2 b) with the x87's fyl2x / f2xm1 / fscale */
static float fpow(float b, float k)
{
    float r;
    if (b <= 0.0f) return 0.0f;
    __asm__("fyl2x\n\t"                 /* st0 = k log2 b */
            "fld %%st(0)\n\t"
            "frndint\n\t"               /* st0 = n, st1 = x */
            "fsubr %%st(0), %%st(1)\n\t"/* st1 = x - n */
            "fxch\n\t"
            "f2xm1\n\t"
            "fld1\n\t"
            "faddp\n\t"                 /* st0 = 2^(x - n), st1 = n */
            "fscale\n\t"
            "fstp %%st(1)"
            : "=t"(r) : "0"(b), "u"(k) : "st(1)");
    return r;
}

#define RD(p, o, T) (*(T *)((u8 *)(p) + (o)))
typedef void (__attribute__((thiscall)) *StepFn)(void *veh, float dt);
typedef void (__attribute__((thiscall)) *SetVecFn)(void *body, const float *v);
#define VEHICLE_STEP ((StepFn)0x45C820)
#define SET_VELOCITY ((SetVecFn)0x45A120)
#define SET_ANGULAR ((SetVecFn)0x45A1A0)

static float dot3(const float *a, const float *b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

/* the human driver whose vehicle this is, or 0 */
static u8 *player_driver(void *veh)
{
    for (u32 i = 0; i < 6; i++) {
        u8 *rec = (u8 *)0x9DBAC8 + 0x1F18 * i;
        u8 *drv = RD(rec, 4, u8 *);
        if (!drv || RD(drv, 0, u32) != 0x6ED0C8 || RD(drv, 0x7E4, u8 *) != rec) continue;
        u8 *wrap = RD(drv, 0x858, u8 *);
        if (wrap && RD(wrap, 4, void *) == veh) return drv;
    }
    return 0;
}

static Slot *slot_of(void *veh)
{
    Slot *free_ = 0, *oldest = &g.slot[0];
    for (u32 i = 0; i < NSLOT; i++) {
        Slot *s = &g.slot[i];
        if (s->veh == veh) {
            if (g.steps - s->last > 400) s->valid = 0;    /* not stepped for a while (all cars count): a new race */
            return s;
        }
        if (!s->veh && !free_) free_ = s;
        if (s->last < oldest->last) oldest = s;
    }
    Slot *s = free_ ? free_ : oldest;
    s->veh = veh; s->valid = 0;
    return s;
}

/* signed sine of the slip angle of displacement (dx, dz) against heading (hx, hz) (kb 29 section 4) */
static float slip(float dx, float dz, float hx, float hz, float *len)
{
    float l = fsqrt(dx * dx + dz * dz);
    *len = l;
    if (l < 1e-10f) return 0.0f;
    dx /= l; dz /= l;
    float c = fabsf_(dx * hx + dz * hz); if (c > 1.0f) c = 1.0f;
    float cr = dx * hz - dz * hx;
    return copysignf_(fsqrt(1.0f - c * c), cr != 0.0f ? cr : 1.0f);
}

/* SRC's tyre force for one axle (kb 29 section 7); returns the side force, fx in / out */
static float tyre(float sig, float axle_speed, float fmax, float k, float *fx, float c)
{
    float a = fabsf_(sig) * k; if (a > PI / 2) a = PI / 2;
    float fy = fmax * fsin(a);
    float tot = fsqrt(fy * fy + *fx * *fx);                 /* (1 + w) with w = 0: SR3 does the wheelspin */
    if (tot > fmax) {
        float q = fmax / tot, f = c * fsqrt(q) + (1.0f - c) * q * q;
        fy = fy * f * 1.1f; *fx = *fx * f;
    }
    if (sig >= 0.0f) fy = -fy;
    float ls = fabsf_(sig) * axle_speed;
    if (ls < 0.02f) fy *= ls / 0.02f;
    return fy;
}

static void port(void *veh, float dt, const float *v0, const float *w0)
{
    u8 *body = RD(veh, 8, u8 *);
    u8 *drv = player_driver(veh);
    if (!drv && !g.ai) return;
    u8 **list = RD(veh, 0x2C, u8 **);
    if (!body || !list || RD(veh, 0x30, u32) != 4 || !(dt > 0.0f) || dt > 0.1f) return;

    const float *up = (const float *)(body + 0xEC), *ax = (const float *)(body + 0xF8), *az = (const float *)(body + 0x104);
    float *v1 = (float *)(body + 0x170), *w1v = (float *)(body + 0x17C);
    const float F = g.fps, k = dt * F;

    /* wheels: contact, compression, surface */
    int contact[4], n_on = 0, road = 0, cls = -1;
    float comp[4], lock = 0.0f;
    for (int i = 0; i < 4; i++) {
        u8 *a = list[i]; if (!a) return;
        u8 *susp = RD(a, 0xC, u8 *), *wh = RD(a, 0x10, u8 *), *ty = RD(a, 0x14, u8 *);
        contact[i] = susp && RD(susp, g.off_contact, u32) != 0;
        comp[i] = contact[i] ? clampf(g.comp_scale * RD(susp, g.off_comp, float) + g.comp_add, 0.0f, 1.0f) : 0.0f;
        if (i == 0 && wh) lock = RD(wh, 0x184, float);
        u32 idx = ty ? RD(ty, 0x1C, u32) : 0xFFFFFFFF;
        u8 c = idx < g.count && idx < NCLS ? g.cls[idx] : 0xFF;
        if (c != 0xFF) {
            if (c & 0x80) road = 1;
            if (contact[i] && (cls < 0 || PRIO[c & 3] > PRIO[cls])) cls = c & 3;
        }
        n_on += contact[i];
    }
    if (g.need_road_tyre && !road) { if (drv) g.last_err = 1; return; }      /* not a car on the SRC files */
    Slot *st = slot_of(veh);
    {
        float px = RD(body, 0x88, float), pz = RD(body, 0x90, float);
        if (st->valid && (px - st->px) * (px - st->px) + (pz - st->pz) * (pz - st->pz) > 400.0f) st->valid = 0;
        st->px = px; st->pz = pz;
    }
    if (cls < 0) cls = 0;
    const Rec *R = &REC[cls];

    /* SRC's state in its units: m / frame, rad / frame; SRC x = SR3 x (right), z forward, yaw + = left */
    const float xs = g.x_sign, ys = g.x_sign * g.yaw_sign;
    float vx = xs * dot3(v0, ax) / F, vz = dot3(v0, az) / F, vy = dot3(v0, up) / F;
    float w = -ys * dot3(w0, up) / F;
    float sp3 = fsqrt(vx * vx + vy * vy + vz * vz), sp2 = fsqrt(vx * vx + vz * vz);

    /* steering: SRC 0x395D8 / 0x39A90 */
    float s;
    if (drv) {
        float u = ((float)RD(drv, 0x1C85, u8) - (float)RD(drv, 0x1C84, u8)) / 255.0f;
        s = 0.84f * clampf(g.counts * u, -80.0f, 80.0f) / 80.0f;
    } else {
        u8 *ctl = RD(veh, 0x28, u8 *);
        float u = (ctl ? RD(ctl, 8, float) : 0.0f) * g.ai_gain;
        s = 0.84f * clampf(g.counts * u, -80.0f, 80.0f) / 80.0f;
    }
    if (!st->valid) { st->y = s; st->lt = 0.0f; }
    st->y += (1.0f - fpow(0.1f, k)) * (s - st->y);
    float d = -st->y;

    /* body slip angle and its change (0x3580C) */
    float beta = sp2 > 0.01f ? fasin(vx / sp2) : 0.0f;
    float dbeta = (sp2 > 0.01f && st->valid) ? beta - st->beta : 0.0f;
    st->beta = beta;
    /* SR3's own in the air, and while SR3's hit recovery runs: the force model (vehicle + 0x38) + 0x24 is set by a hard
       contact (above 40 mph and 40 degrees, 0x44F910 from the contact handler 0x5B2F00) for up to 1 s, during which
       SR3 straightens the wheels, cuts the tyre load term and halves the throttle; PowerslideSteer's update clears it.
       The steering filter and the body slip keep running, as SRC's do every frame. */
    u8 *fmodel = RD(veh, 0x38, u8 *);
    u32 hit = fmodel && RD(fmodel, 0x24, u32) != 0;
    if (!n_on || hit) { st->valid = 1; st->last = g.steps; if (drv) g.last_err = hit ? 3 : 2; return; }

    /* each wheel's displacement over one frame, its slip (0x37200); the axle values (0x35D00) */
    float sl[2] = {0, 0}, spd[2] = {0, 0}; int nax[2] = {0, 0};
    float sd = fsin(d), cd = fcos(d), sw = fsin(w), cw = fcos(w);
    for (int i = 0; i < 4; i++) {
        if (!contact[i]) continue;
        int fr = i < 2;
        float ox = xs * (i & 1 ? 1.0f : -1.0f) * (fr ? g.half_track_f : g.half_track_r), oz = fr ? g.axle : -g.axle;
        float dx = vx + (ox * cw - oz * sw) - ox, dz = vz + (ox * sw + oz * cw) - oz, len;
        float sg = fr ? slip(dx, dz, -sd, cd, &len) : slip(dx, dz, 0.0f, 1.0f, &len);
        sl[1 - fr] += sg; spd[1 - fr] += len; nax[1 - fr]++;
    }
    for (int a = 0; a < 2; a++) if (nax[a]) { sl[a] /= nax[a]; spd[a] /= nax[a]; }

    /* load transfer (0x37900, 0x38A18) from SR3's suspension */
    float Cf = comp[0] + comp[1], Cr = comp[2] + comp[3];
    float raw = Cf + Cr > 1e-6f ? (Cf - Cr) / (Cf + Cr) : st->lt;
    float K = raw > st->lt ? R->lag_up : R->lag_dn;
    float lt = raw - fpow(K, k) * (raw - st->lt);
    if (lt > 0.0f) lt += 0.08f * fsin(PI * lt);
    st->lt = lt;

    /* drive / brake force: what SR3 did along the car this step, without gravity (SRC's D, mass-1000 units) */
    const float *gv = (const float *)0x78340C;
    float D = 1000.0f * (dot3(v1, az) - dot3(v0, az) - g.use_gravity * dot3(gv, az) * dt) / (F * k);
    if (!nax[0] || !nax[1]) D = 0.0f;                     /* an axle in the air: no drive force (SRC) */

    /* tyre forces (0x37870) */
    float fm = G_SRC * 1000.0f * (1.0f + 0.3f * sp3);
    float fmf = fm * R->grip_f * (1.0f + lt), fmr = fm * R->grip_r * (1.0f - lt);
    float sf = sl[0];
    sf = fabsf_(sf) < 0.01f ? 0.0f : sf - copysignf_(0.01f, sf);
    float fxf = R->share * D, fxr = D - fxf;
    float fyf = nax[0] ? tyre(sf, spd[0], fmf, 2.0f * PI / 3.0f, &fxf, 1.2f) : (fxf = 0.0f, 0.0f);
    float fyr = nax[1] ? tyre(sl[1], spd[1], fmr, PI, &fxr, 0.4f) : (fxr = 0.0f, 0.0f);
    if (fxf < 0.0f) { fxr += fxf; fxf = 0.0f; }

    /* yaw torque and the yaw rate (0x36760, 0x36A5C) */
    float xf = fyf * cd - fxf * sd, zf_side = fyf * sd;
    float r14 = fxf > 0.0f && Cf > 1e-6f ? xs * 1.1f * (comp[1] - comp[0]) / Cf : 0.0f;   /* SRC: (right - left) */
    float r13 = fxr > 0.0f && Cr > 1e-6f ? xs * 1.1f * (comp[3] - comp[2]) / Cr : 0.0f;
    float T = g.axle * (fyr - xf) + 0.66f * r13 * fxr - 0.635f * r14 * fxf;
    float wn = clampf(w + k * T / 1146.0f, -0.1f, 0.1f);
    wn = wn - R->kb * dbeta - (1.0f - fpow(1.0f - R->kw, k)) * wn;

    /* the new side velocity (SRC's side force, gravity along the car's x) and forward velocity (SR3's) */
    float vxn = vx + k * (fyr + xf) / 1000.0f + g.use_gravity * xs * dot3(gv, ax) * dt / F;
    float vzn = dot3(v1, az) / F + (g.scrub ? k * zf_side / 1000.0f : 0.0f);
    float vu = dot3(v1, up), wu = dot3(w1v, up);
    float V[3], W[3];
    for (int j = 0; j < 3; j++) {
        V[j] = (xs * vxn * ax[j] + vzn * az[j]) * F + vu * up[j];
        W[j] = w1v[j] - wu * up[j] - ys * wn * F * up[j];
    }
    st->valid = 1; st->last = g.steps;

    if (drv) {
        LogRec *L = &g.log[g.log_pos % NLOG];
        float *t = L->t;
        t[0] = (float)g.player_steps; t[1] = dt; t[2] = s; t[3] = d; t[4] = vx; t[5] = vz; t[6] = w; t[7] = beta;
        t[8] = dbeta; t[9] = sl[0]; t[10] = sl[1]; t[11] = spd[0]; t[12] = spd[1]; t[13] = fyf; t[14] = fyr;
        t[15] = fxf; t[16] = fxr; t[17] = T; t[18] = lt; t[19] = raw; t[20] = (float)cls;
        t[21] = (float)(contact[0] | contact[1] << 1 | contact[2] << 2 | contact[3] << 3);
        t[22] = comp[0]; t[23] = comp[1]; t[24] = comp[2]; t[25] = comp[3]; t[26] = D; t[27] = wn; t[28] = vxn;
        t[29] = vzn; t[30] = -ys * wu / F;               /* SR3's own yaw rate after its step, SRC units */
        t[31] = xs * dot3(v1, ax) / F;                   /* SR3's own side velocity after its step */
        t[32] = sp3; t[33] = (float)g.mode; t[34] = vy; t[35] = lock;
        t[36] = (drv ? ((float)RD(drv, 0x1C85, u8) - (float)RD(drv, 0x1C84, u8)) / 255.0f : 0.0f);   /* the stick */
        u8 *wh0 = RD(list[0], 0x10, u8 *);
        t[37] = wh0 ? RD(wh0, 0x190, float) : 0.0f;      /* SR3's own wheel angle, front left */
        t[38] = k; t[39] = fmodel ? RD(fmodel, 0x28, float) : -1.0f;   /* the hit timer (0 when no hit) */
        g.log_pos++; g.player_steps++; g.last_err = 0;
    }
    if (g.mode >= 2) { SET_VELOCITY(body, V); SET_ANGULAR(body, W); }
}

/* CVehicle vtable slot 5 */
__attribute__((thiscall)) void srcport_step(void *veh, float dt)
{
    float v0[3] = {0, 0, 0}, w0[3] = {0, 0, 0};
    u8 *body = RD(veh, 8, u8 *);
    int go = g.mode != 0 && body;
    if (go) for (int j = 0; j < 3; j++) { v0[j] = RD(body, 0x170 + 4 * j, float); w0[j] = RD(body, 0x17C + 4 * j, float); }
    VEHICLE_STEP(veh, dt);
    g.steps++;
    if (go) port(veh, dt, v0, w0);
}
