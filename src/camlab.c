/*
    CamLab - a tiny chase camera playground for SR3CamLab.

    A low-poly hatchback races an endless, procedurally generated rally stage
    (turns, hills, jump crests), driven by steering behaviours (path following,
    racing line, corner-speed planning, drift flicks). The chase camera is the
    same model as the SEGA Rally 3 camera mod: it bends towards the direction of
    travel, rides on a damped spring, and has a soft angle limit.

    Single source file, raylib 5.5, static build (see Makefile / build.bat):
        gcc camlab.c -o camlab.exe -O2 -std=c99 -s -static -mwindows -lraylib -lopengl32 -lgdi32 -lwinmm

    Keys:  Tab panel   M autopilot/manual   R respawn   P pause   F12 screenshot
           Manual: arrows / WASD drive, Space handbrake (drift)
    Profiles live in profiles.yaml (shared with the game's patch.ps1); defaults.yaml holds
    the factory values that Reset returns to.
*/
#include "raylib.h"
#include "rlgl.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// ============================================================== math helpers
static float Clampf(float v, float a, float b) { return v < a ? a : (v > b ? b : v); }
static float Lerpf(float a, float b, float t) { return a + (b - a)*t; }
static float WrapAngle(float a) { a = fmodf(a + PI, 2*PI); if (a < 0) a += 2*PI; return a - PI; }
static Vector3 V3(float x, float y, float z) { return (Vector3){ x, y, z }; }
static Vector3 Add(Vector3 a, Vector3 b) { return V3(a.x + b.x, a.y + b.y, a.z + b.z); }
static Vector3 Scl(Vector3 a, float s) { return V3(a.x*s, a.y*s, a.z*s); }
static float Dot(Vector3 a, Vector3 b) { return a.x*b.x + a.y*b.y + a.z*b.z; }
// yaw 0 looks down +Z; increasing yaw turns left (as seen from the chase camera)
static Vector3 Fwd(float yaw) { return V3(sinf(yaw), 0, cosf(yaw)); }
static Vector3 Right(float yaw) { return V3(-cosf(yaw), 0, sinf(yaw)); }

// ============================================================== track
#define TRK_N   8192
#define SEG     2.0f            // metres between centreline samples
#define ROAD_HW 6.0f            // road half width
#define CURB_W  0.9f

// Road surfaces. Grip scales cornering and the slide; SR3 mixes them within a stage
// (Canyon: gravel and tarmac, Tropical: mud, Alpine: snow and a tarmac village).
enum { SURF_TARMAC, SURF_GRAVEL, SURF_MUD, SURF_SNOW, SURF_COUNT };
static const float SURF_GRIP[SURF_COUNT] = { 1.00f, 0.86f, 0.76f, 0.70f };

typedef struct { Vector3 p; float yaw, k; int surf; } TrackPt;     // k = signed curvature (1/m)
static TrackPt trk[TRK_N];
static long trkHead = -1;

static unsigned rngS = 12345u;
static float Frand(void) { rngS ^= rngS << 13; rngS ^= rngS >> 17; rngS ^= rngS << 5; return (rngS >> 8)*(1.0f/16777216.0f); }
static float Frange(float a, float b) { return a + (b - a)*Frand(); }

typedef struct { int len, pos; float kPeak; } YawSeg;              // turn: curvature follows a sine window
typedef struct { int len, pos; float h0, dy; int ease; } HSeg;     // height: eased hill or linear ramp
static struct { Vector3 p; float yaw, baseYaw; YawSeg ys; HSeg hs, hNext; int hasNext, surf, surfLeft; } G;

static TrackPt *TP(long i)
{
    long lo = trkHead - TRK_N + 1;
    if (lo < 0) lo = 0;
    if (i < lo) i = lo;
    if (i > trkHead) i = trkHead;
    return &trk[i % TRK_N];
}

// The generator is calibrated against the route splines of the real SR3 stages (Tropical,
// Canyon, Alpine, Lakeside): ~45% straight, ~9 corners per km that are mostly kinks and
// 20-40 degree bends with the odd hairpin, grades around 10-13%, ~1 launch crest per km.
static void NextYawSeg(void)
{
    G.baseYaw += Frange(-0.35f, 0.35f);                 // the stage wanders, but never loops back
    if (Frand() < 0.30f) { G.ys.len = (int)Frange(10, 45); G.ys.kPeak = 0; }
    else {
        float r = Frand(), radius =                      // radius mix of the real stages
            r < 0.10f ? Frange(20, 30) : r < 0.50f ? Frange(30, 60) : r < 0.85f ? Frange(60, 120) : Frange(120, 250);
        float a = Frand(), angle =                       // mostly kinks and medium bends
            (a < 0.55f ? Frange(8, 35) : a < 0.88f ? Frange(35, 80) : Frange(80, 150))*DEG2RAD;
        float dev = WrapAngle(G.yaw - G.baseYaw);
        float side = dev > 1.0f ? -1.0f : dev < -1.0f ? 1.0f : (Frand() < 0.5f ? -1.0f : 1.0f);
        float k = 1.0f/radius;
        G.ys.len = (int)(angle*PI/(2*k)/SEG) + 2;       // sine window: total turn = k*L*2/pi
        G.ys.kPeak = side*k;
    }
    G.ys.pos = 0;
}

static void NextHSeg(void)
{
    float h = G.p.y, r = Frand();
    if (G.hasNext) { G.hs = G.hNext; G.hasNext = 0; }
    else if (h > 5.0f && r < 0.12f) {                   // jump: short kicker, then a long landing slope
        float up = Frange(2.0f, 3.0f);
        G.hs = (HSeg){ 7, 0, h, up, 0 };
        float down = up + fminf(h - 0.6f, Frange(5, 9));
        G.hNext = (HSeg){ (int)Frange(34, 46), 0, 0, -down, 0 };
        G.hasNext = 1;
    } else if (r < 0.70f) {                             // hill
        float dy = Frange(3, 12)*(Frand() < 0.5f ? -1.0f : 1.0f);
        if (h + dy < 0.6f) dy = fabsf(dy);
        if (h + dy > 60.0f) dy = -fabsf(dy);
        G.hs = (HSeg){ (int)Frange(50, 140), 0, h, dy, 1 };
    } else G.hs = (HSeg){ (int)Frange(15, 50), 0, h, 0, 1 };
    G.hs.h0 = h; G.hs.pos = 0;
}

static void NextSurface(void)
{
    static const float weight[SURF_COUNT] = { 0.30f, 0.35f, 0.20f, 0.15f };
    int s;
    do {
        float r = Frand(), acc = 0;
        for (s = 0; s < SURF_COUNT - 1; s++) { acc += weight[s]; if (r < acc) break; }
    } while (s == G.surf);
    G.surf = s;
    G.surfLeft = (int)Frange(90, 320);                  // 180-640 m sections
}

static void GenOne(void)
{
    if (G.ys.pos >= G.ys.len) NextYawSeg();
    if (G.hs.pos >= G.hs.len) NextHSeg();
    if (--G.surfLeft <= 0) NextSurface();
    float k = G.ys.kPeak != 0 ? G.ys.kPeak*sinf(PI*(G.ys.pos + 0.5f)/G.ys.len) : 0;
    G.ys.pos++;
    G.yaw = WrapAngle(G.yaw + k*SEG);
    float t = (G.hs.pos + 1)/(float)G.hs.len;
    float e = G.hs.ease ? 0.5f - 0.5f*cosf(PI*t) : t;
    G.hs.pos++;
    Vector3 f = Fwd(G.yaw);
    G.p = V3(G.p.x + f.x*SEG, G.hs.h0 + G.hs.dy*e, G.p.z + f.z*SEG);
    trkHead++;
    trk[trkHead % TRK_N] = (TrackPt){ G.p, G.yaw, k, G.surf };
}

static void TrackInit(unsigned seed)
{
    rngS = seed ? seed : 1u;
    memset(&G, 0, sizeof G);
    G.p = V3(0, 1, 0);
    G.ys = (YawSeg){ 40, 0, 0 };
    G.hs = (HSeg){ 30, 0, 1, 0, 1 };
    G.surf = SURF_GRAVEL; G.surfLeft = 200;
    trkHead = -1;
    for (int i = 0; i < 1200; i++) GenOne();
}

// ============================================================== car
#define GRAV    22.0f
#define ENGINE  17.0f
#define BRAKE   24.0f
#define DRIFT_GRIP 1.6f         // how hard a slide bites (sideways speed shed per second, per unit of surface grip)
#define VMAX    63.0f            // ~225 km/h: SR3's arcade pace (the Championship record averages ~180 km/h)

typedef struct {
    Vector3 pos;                    // pos.y = height of the contact point
    Vector2 v;                      // planar velocity (x, z)
    float vy, yaw, yawRate, pitch, roll;
    float steer, throttle;
    int ground, drift, handbrake;
    float driftT, airT, stuckT;
    long idx; float lat, surfY, slope, trackYaw; int surf;
} Car;

static float CarSpeed(const Car *c) { return sqrtf(c->v.x*c->v.x + c->v.y*c->v.y); }
static float CarTravel(const Car *c) { return CarSpeed(c) > 0.5f ? atan2f(c->v.x, c->v.y) : c->yaw; }
// full-lock yaw rate: falls with speed, capped by the surface's lateral grip unless sliding
static float CarMaxYawRate(const Car *c)
{
    float speed = CarSpeed(c), rate = 2.3f/(1.0f + speed*0.028f);
    if (!c->drift && speed > 1) rate = fminf(rate, 24.0f*SURF_GRIP[c->surf]/speed);   // ~2.4 g on tarmac, arcade style
    return c->drift ? rate*1.25f : rate;
}

static void CarLocate(Car *c)
{
    long best = c->idx; float bd = 1e30f;
    for (long i = c->idx - 20; i <= c->idx + 40; i++) {
        if (i < 0 || i >= trkHead) continue;
        TrackPt *t = TP(i);
        float dx = c->pos.x - t->p.x, dz = c->pos.z - t->p.z, d = dx*dx + dz*dz;
        if (d < bd) { bd = d; best = i; }
    }
    c->idx = best;
    // use the segment the car is actually on: [best-1, best] if it hasn't reached the nearest sample yet
    TrackPt *a = TP(best), *b = TP(best + 1);
    if ((c->pos.x - a->p.x)*Fwd(b->yaw).x + (c->pos.z - a->p.z)*Fwd(b->yaw).z < 0 && best > 0) { b = a; a = TP(best - 1); }
    Vector3 f = Fwd(b->yaw), r = Right(b->yaw);
    float dx = c->pos.x - a->p.x, dz = c->pos.z - a->p.z;
    float t = Clampf((dx*f.x + dz*f.z)/SEG, 0, 1);
    c->lat = dx*r.x + dz*r.z;
    c->surfY = Lerpf(a->p.y, b->p.y, t);
    c->slope = (b->p.y - a->p.y)/SEG;
    c->trackYaw = b->yaw;
    c->surf = a->surf;
}

static void CarRespawn(Car *c, long idx)
{
    if (idx < 2) idx = 2;
    TrackPt *t = TP(idx);
    memset(c, 0, sizeof *c);
    c->idx = idx;
    c->pos = t->p;
    c->yaw = TP(idx + 1)->yaw;
    Vector3 f = Fwd(c->yaw);
    c->v = (Vector2){ f.x*14.0f, f.z*14.0f };
    c->ground = 1;
    CarLocate(c);
}

static void CarStep(Car *c, float dt)
{
    Vector3 f = Fwd(c->yaw), r = Right(c->yaw);
    float vL = c->v.x*f.x + c->v.y*f.z, vT = c->v.x*r.x + c->v.y*r.z;
    float speed = CarSpeed(c);
    int off = fabsf(c->lat) > ROAD_HW + CURB_W;

    if (c->ground) {
        float acc = c->throttle >= 0 ? c->throttle*ENGINE*(1.0f - Clampf(vL/VMAX, 0, 1))
                                     : c->throttle*BRAKE*(vL > 0 ? 1.0f : 0.3f);
        vL += acc*dt;
        vL -= vL*(0.02f + (off ? 0.9f : 0) + (c->drift ? 0.10f : 0))*dt;

        // steering: yaw-rate target, limited by lateral grip unless sliding
        float want = c->steer*CarMaxYawRate(c)*Clampf(speed/5.0f, 0, 1)*(vL < 0 ? -1.0f : 1.0f);
        c->yawRate += (want - c->yawRate)*(1 - expf(-dt*(c->drift ? 3.5f : 10.0f)));
        if (c->drift) {                                   // keep the slide below ~48 degrees
            float slip = WrapAngle(CarTravel(c) - c->yaw), lim = 48*DEG2RAD;
            if (fabsf(slip) > lim) c->yawRate += (slip - copysignf(lim, slip))*20.0f*dt;
        }
    } else c->yawRate *= expf(-dt*0.8f);

    Vector3 v = Add(Scl(f, vL), Scl(r, vT));             // world velocity before the heading changes
    c->yaw = WrapAngle(c->yaw + c->yawRate*dt);
    f = Fwd(c->yaw); r = Right(c->yaw);
    vL = Dot(v, f); vT = Dot(v, r);
    if (c->ground) {
        float grip = (c->drift ? DRIFT_GRIP : 8.5f)*SURF_GRIP[c->surf];
        if (off) grip *= 0.6f;
        float nT = vT*expf(-grip*dt);
        vL += fabsf(vT - nT)*0.35f*(vL >= 0 ? 1.0f : -1.0f);    // a slide keeps some of its momentum
        vT = nT;
    }
    v = Add(Scl(f, vL), Scl(r, vT));
    c->v = (Vector2){ v.x, v.z };
    c->pos.x += v.x*dt; c->pos.z += v.z*dt;

    CarLocate(c);
    Vector3 tf = Fwd(c->trackYaw);
    float along = c->v.x*tf.x + c->v.y*tf.z;
    float groundVy = c->slope*along;                      // vertical speed the road would impose
    if (c->ground) {
        if (groundVy < c->vy - GRAV*dt - 0.8f) {          // road falls away faster than gravity: airborne
            c->ground = 0; c->airT = 0;
            c->pos.y += c->vy*dt;
        } else { c->vy = groundVy; c->pos.y = c->surfY; }
    } else {
        c->vy -= GRAV*dt; c->pos.y += c->vy*dt; c->airT += dt;
        if (c->pos.y <= c->surfY) {
            c->pos.y = c->surfY; c->vy = groundVy; c->ground = 1;
            c->v.x *= 0.985f; c->v.y *= 0.985f;
        }
    }

    float pitchT = c->ground ? atanf(c->slope) : atan2f(c->vy, fmaxf(speed, 1.0f))*0.6f;
    c->pitch += (pitchT - c->pitch)*(1 - expf(-dt*(c->ground ? 14.0f : 3.0f)));
    float rollT = Clampf(-vT*0.012f + c->yawRate*speed*0.0035f, -0.10f, 0.10f);
    c->roll += (rollT - c->roll)*(1 - expf(-dt*6.0f));
    if (c->drift) c->driftT += dt;
}

// steering behaviours: path following (look-ahead seek on a racing line), arrive-style
// corner speed planning, and a handbrake flick into tight corners
// effective curvature: heading change over ~30 m, i.e. what the racing line really has to turn.
// A 20 degree kink barely needs a lift; a hairpin still reads as a hairpin.
static float KEff(long j) { return WrapAngle(TP(j + 8)->yaw - TP(j - 7)->yaw)/(15*SEG); }

static void CarAutopilot(Car *c)
{
    float speed = CarSpeed(c);
    // path following: feed-forward the road's curvature, then correct heading and lateral error
    // (a Stanley-style tracker). The racing line sits towards the inside of the coming turn.
    long ahead = c->idx + 2 + (long)(speed*0.10f/SEG);            // compensate the steering lag
    float kPath = KEff(ahead);
    float line = -Clampf(KEff(ahead + 8)*140.0f, -1, 1)*2.0f;
    float latErr = c->lat - line;                                // + = right of the line
    float pathYaw = TP(ahead)->yaw + atanf(0.9f*latErr/(speed + 4.0f));
    float kNear = 0, kNearSigned = 0;
    for (long j = c->idx; j < c->idx + 15; j++) if (fabsf(KEff(j)) > kNear) { kNearSigned = KEff(j); kNear = fabsf(kNearSigned); }
    if (!c->drift) {
        float yawRate = speed*kPath + 3.0f*WrapAngle(pathYaw - c->yaw);
        c->steer = Clampf(yawRate/fmaxf(CarMaxYawRate(c), 0.1f), -1, 1);
    } else {
        // in a slide the slip angle is what turns the car: the travel direction swings towards
        // the nose at DRIFT_GRIP*sin(slip). Work out the slip this corner needs, then point the nose there.
        float travel = CarTravel(c), g = DRIFT_GRIP*SURF_GRIP[c->surf];
        float travelRate = speed*kPath + 3.0f*WrapAngle(pathYaw - travel);
        float slip = asinf(Clampf(-travelRate/g, -0.8f, 0.8f));      // slip = travel - nose
        float yawRate = travelRate + 5.0f*WrapAngle(travel - slip - c->yaw);
        c->steer = Clampf(yawRate/fmaxf(CarMaxYawRate(c), 0.1f), -1, 1);
    }

    float vTarget = VMAX*0.95f;                                  // brake early enough for what's coming
    float horizon = fmaxf(40.0f, speed*2.4f);
    for (long j = c->idx; j < c->idx + (long)(horizon/SEG); j++) {
        float k = fabsf(KEff(j));
        if (k < 1e-4f) continue;
        float vCorner = sqrtf((c->drift ? 19.0f : 21.0f)*SURF_GRIP[TP(j)->surf]/k), d = (j - c->idx)*SEG;
        vTarget = fminf(vTarget, sqrtf(vCorner*vCorner + 2*14.0f*d));
    }
    vTarget = fmaxf(vTarget, 14.0f);
    c->throttle = Clampf((vTarget - speed)*0.35f, -1, 1);

    if (!c->drift && c->ground && speed > 18 && kNear > SURF_GRIP[c->surf]/90.0f) {   // tighter than ~90 m (more on loose)
        c->drift = 1; c->driftT = 0;
        c->yawRate += copysignf(1.0f, kNearSigned);             // flick it in
    }
    if (c->drift && c->driftT > 0.6f && (kNear < 1.0f/160.0f || speed < 12)) c->drift = 0;
}

#ifndef CAMLAB_SELFTEST
static void CarManual(Car *c)
{
    c->throttle = (float)((IsKeyDown(KEY_UP) || IsKeyDown(KEY_W)) - (IsKeyDown(KEY_DOWN) || IsKeyDown(KEY_S)));
    c->steer = (float)((IsKeyDown(KEY_LEFT) || IsKeyDown(KEY_A)) - (IsKeyDown(KEY_RIGHT) || IsKeyDown(KEY_D)));
    if (IsKeyPressed(KEY_SPACE) && c->ground && CarSpeed(c) > 8) {
        c->drift = 1; c->driftT = 0;
        c->yawRate += c->steer*0.6f;
    }
    c->handbrake = IsKeyDown(KEY_SPACE);
    if (c->drift && !c->handbrake && c->driftT > 0.3f &&
        fabsf(WrapAngle(CarTravel(c) - c->yaw)) < 8*DEG2RAD) c->drift = 0;
}
#endif


// ============================================================== camera profiles
enum { P_STRENGTH, P_FADE0, P_FADE1, P_KMIN, P_KMAX, P_DAMP, P_MAXANG, P_CAP, P_DIST, P_HEIGHT, P_FOV, NPARAM };
typedef struct { const char *col, *label, *fmt; float mn, mx, step, def; int group; } ParamDef;
static const ParamDef PD[NPARAM] = {
    { "Strength",       "Travel follow",          "%.2f",       0,   1,    0.01f, 0.70f, 0 },
    { "FadeInStartKmh", "Fade-in starts",         "%.0f km/h",  0,   150,  1,     14,    0 },
    { "FadeInFullKmh",  "Full effect at",         "%.0f km/h",  1,   250,  1,     43,    0 },
    { "StiffnessMin",   "Stiffness \xC2\xB7 sliding",  "%.1f",  1,   150,  0.5f,  30,    1 },
    { "StiffnessMax",   "Stiffness \xC2\xB7 gripping", "%.1f",  1,   300,  0.5f,  50,    1 },
    { "Damping",        "Damping",                "%.1f",       0.5f, 40,  0.1f,  11.5f, 1 },
    { "MaxAngle",       "Max angle",              "%.0f\xC2\xB0", 5, 180,  1,     35,    2 },
    { "CapStiffness",   "Cap stiffness",          "%.2f",       0,   1,    0.01f, 0.40f, 2 },
    { "Distance",       "Distance",               "%.1f m",     3,   16,   0.1f,  7.0f,  3 },   // SR3 frames the car close and low
    { "Height",         "Height",                 "%.1f m",     0.5f, 8,   0.1f,  2.3f,  3 },
    { "Fov",            "Field of view",          "%.0f\xC2\xB0", 30, 110, 1,     62,    3 },
};
#ifndef CAMLAB_SELFTEST
static const char *GROUPS[] = { "TRAVEL FOLLOW", "SPRING", "ANGLE LIMIT", "FRAMING" };
static const char *GROUPS_TIP[][2] = {
    { "Travel follow", "Where the camera looks: behind the car's nose, or along the way the car is really going. This is what shows the car sideways in a drift." },
    { "Spring", "How the camera catches up with the car: an invisible rubber band pulling it back behind, and a shock absorber that stops it wobbling." },
    { "Angle limit", "How far round the car the camera may swing, and how softly it slows down near that limit." },
    { "Framing", "Where the camera sits and how wide it sees. The game gets these too." },
};

// hover tooltips: what each slider does, in plain words
static const char *PARAM_TIP[NPARAM] = {
    "How much the camera looks where the car is GOING instead of where its nose points. "
    "0 = glued behind the bumper. Turn it up and, in a drift, the camera swings out so you see the car sideways.",
    "Below this speed the swing is switched off, so parking, reversing and crawling look normal.",
    "From this speed on the swing works at full strength. Between the two speeds it fades in gently.",
    "Think of an invisible rubber band pulling the camera back behind the car. "
    "This is how strong it is while the car slides or flies. Low = lazy, floaty swings.",
    "The same rubber band, while the tyres grip. High = the camera snaps back quickly after a corner.",
    "Stops the rubber band from wobbling. Low = the camera overshoots and sways back and forth. "
    "High = it settles smoothly, without bouncing.",
    "The farthest the camera may swing round the car. Stops it from showing the car completely side-on in a huge slide.",
    "How the camera feels as it nears that limit. Low = it slows down gently, like a soft spring. "
    "1 = it stops dead, like hitting a wall.",
    "How far behind the car the camera sits.",
    "How high above the road the camera floats.",
    "How wide the camera's lens is. Wider = more scenery and more sense of speed, but the car looks smaller.",
};

#define MAXPROF 32
// Profiles live in profiles.yaml, shared with the game's patch.ps1: CamLab edits them there and
// its "default:" key names the one PLAY.bat uses. defaults.yaml holds the factory values
// ("camlab.exe --make-defaults" copies the current profiles into it); Reset returns a profile
// to its "preset" entry in that file.
// v = live values on the car, base = what is saved on disk
typedef struct { char name[32], preset[32]; float v[NPARAM], base[NPARAM]; int builtin; } Profile;
static Profile prof[MAXPROF];
static int nprof = 0, sel = 0;
static char profPath[512], defaultsPath[512], defaultName[32];
// the camera name the game shows on View Change: font size in pixels at 1080p, 0 = off
static int overlayPx = 48, readOverlay = -1;
// whether View Change also offers the cameras the game hides (far chase, cockpit, wheel, ...)
static int showHidden = 1, readHidden = -1;
// the speedometer's unit (click it to switch); saved as speedUnits: km/h / mph
static int useMph = 0, readMph = -1;
static char status[96]; static float statusT = 0;

static void SetStatus(const char *s) { snprintf(status, sizeof status, "%s", s); statusT = 3.0f; }

static int ParamDirty(const Profile *p, int i) { return fabsf(p->v[i] - p->base[i]) > PD[i].step*0.5f; }
static int ProfileDirty(const Profile *p)
{
    for (int i = 0; i < NPARAM; i++) if (ParamDirty(p, i)) return 1;
    return 0;
}

// last-resort factory values, used when defaults.yaml is missing (e.g. a fresh clone)
static const struct { const char *name; float v[NPARAM]; } PRESETS[] = {
    { "Snappy", { 0.7f, 14, 43, 30, 50, 11.5f, 35, 0.25f, 7, 2.3f, 62 } },
};
#define NPRESETS ((int)(sizeof PRESETS/sizeof PRESETS[0]))

// The built-in profiles: SEGA Rally 3's own chase cameras. Locked and always on top, never
// written to the YAML files (except as "default:"); they can be made the default, launched,
// or copied with New as a template. Values from the game: no travel follow, a spring of
// 112.5 / 675 (its table values 15 / 90 times the x7.5 multiplier the patch removes; the live
// value read 364 on a grid), damping 15, no angle limit, and its own framing: 5.1 / 1.6 / 60
// in the patch's terms (measured in the game), and the far chase camera's x1.25 distance,
// x1.15 height of it.
#define NBUILTIN 2
static const char *BUILTIN_NAME[NBUILTIN] = { "SR3 Chase", "SR3 Chase Far" };
static const float BUILTIN_V[NBUILTIN][NPARAM] = {
    { 0, 14, 43, 112.5f, 675, 15, 180, 0.25f, 5.1f, 1.6f, 60 },
    { 0, 14, 43, 112.5f, 675, 15, 180, 0.25f, 6.4f, 1.8f, 60 },
};
// index of a built-in name (the old "Baseline" means SR3 Chase), else -1
static int BuiltinIndex(const char *n)
{
    if (strcasecmp(n, "Baseline") == 0) return 0;
    for (int i = 0; i < NBUILTIN; i++) if (strcasecmp(n, BUILTIN_NAME[i]) == 0) return i;
    return -1;
}
static int IsBaselineName(const char *n) { return BuiltinIndex(n) >= 0; }

static void Trim(char *s)
{
    char *b = s; while (*b == ' ' || *b == '\t') b++;
    memmove(s, b, strlen(b) + 1);
    size_t n = strlen(s); while (n && (s[n - 1] == ' ' || s[n - 1] == '\t')) s[--n] = 0;
}

static void CleanName(char *s)
{
    for (char *p = s; *p; p++) if (*p == ':' || *p == '#' || *p == '"' || *p == '\'' || (unsigned char)*p < 32) *p = ' ';
    Trim(s);
}

// YAML key -> parameter index (-1 = unknown, COL_PRESET = the preset name)
#define COL_PRESET (-3)
static int KeyParam(const char *key)
{
    if (strcasecmp(key, "preset") == 0) return COL_PRESET;
    for (int p = 0; p < NPARAM; p++) if (strcasecmp(key, PD[p].col) == 0) return p;
    return -1;
}

// ---- profile files: a small, strict YAML subset -------------------------------------------
//   default: Snappy
//   profiles:
//     Snappy:
//       strength: 0.7
//       ...
// Keys are case-insensitive; '#' starts a comment; profile names never contain ':' or '#'.
typedef struct { char name[32], preset[32]; float v[NPARAM]; int has[NPARAM]; } YamlProfile;

static void Unquote(char *s)
{
    Trim(s);
    size_t n = strlen(s);
    if (n >= 2 && (s[0] == '"' || s[0] == '\'') && s[n - 1] == s[0]) { memmove(s, s + 1, n - 2); s[n - 2] = 0; }
}

// returns the number of profiles read, or -1 when the file cannot be read
static int ReadProfilesYaml(const char *path, YamlProfile *out, int max, char *defName, size_t defSize)
{
    char *text = FileExists(path) ? LoadFileText(path) : NULL;
    if (!text) return -1;
    if (defName) defName[0] = 0;
    int n = 0, inProfiles = 0, profIndent = -1;
    YamlProfile *cur = NULL;
    for (char *line = strtok(text, "\r\n"); line; line = strtok(NULL, "\r\n")) {
        char *hash = strchr(line, '#');
        if (hash) *hash = 0;
        int indent = 0;
        while (line[indent] == ' ') indent++;
        char *body = line + indent, *colon = strchr(body, ':');
        if (!*body || !colon) continue;
        *colon = 0;
        char key[64], val[64];
        snprintf(key, sizeof key, "%s", body); Unquote(key);
        snprintf(val, sizeof val, "%s", colon + 1); Unquote(val);
        if (!key[0]) continue;
        if (indent == 0) {
            inProfiles = strcasecmp(key, "profiles") == 0;
            if (strcasecmp(key, "default") == 0 && defName) snprintf(defName, defSize, "%s", val);
            if (strcasecmp(key, "overlay") == 0 && defName) readOverlay = atoi(val);
            if (strcasecmp(key, "hiddenCameras") == 0 && defName)
                readHidden = !(strcasecmp(val, "false") == 0 || strcasecmp(val, "no") == 0 || strcasecmp(val, "off") == 0 || strcmp(val, "0") == 0);
            if (strcasecmp(key, "speedUnits") == 0 && defName) readMph = strcasecmp(val, "mph") == 0;
            cur = NULL;
            continue;
        }
        if (!inProfiles) continue;
        if (profIndent < 0) profIndent = indent;
        if (indent == profIndent) {                              // a new profile
            cur = NULL;
            if (n >= max) continue;
            cur = &out[n++];
            memset(cur, 0, sizeof *cur);
            snprintf(cur->name, sizeof cur->name, "%s", key);
            CleanName(cur->name);
            for (int i = 0; i < NPARAM; i++) cur->v[i] = PD[i].def;
        } else if (cur && indent > profIndent) {                 // one of its values
            int p = KeyParam(key);
            if (p == COL_PRESET) snprintf(cur->preset, sizeof cur->preset, "%s", val);
            else if (p >= 0) {
                char *end; float x = strtof(val, &end);
                if (end != val) { cur->v[p] = Clampf(x, PD[p].mn, PD[p].mx); cur->has[p] = 1; }
            }
        }
    }
    UnloadFileText(text);
    return n;
}

// YAML key for a parameter: its column name with a lower-case first letter (FadeInStartKmh -> fadeInStartKmh)
static void KeyName(int p, char *out, size_t size)
{
    snprintf(out, size, "%s", PD[p].col);
    if (out[0] >= 'A' && out[0] <= 'Z') out[0] = (char)(out[0] - 'A' + 'a');
}

static void WriteProfileYaml(FILE *f, const char *name, const float *v, const int *has, const char *preset)
{
    fprintf(f, "  %s:\n", name);
    for (int p = 0; p < NPARAM; p++) {
        if (has && !has[p]) continue;
        char key[40]; KeyName(p, key, sizeof key);
        if (p == P_DIST && has) fprintf(f, "    %s: %g    # framing: all three, or none for SR3's own\n", key, v[p]);
        else fprintf(f, "    %s: %g\n", key, v[p]);
    }
    if (preset && preset[0]) fprintf(f, "    preset: %s\n", preset);
}

// ---- factory values (defaults.yaml) -------------------------------------------------------
static YamlProfile factory[MAXPROF];
static int nfactory = 0;

static void LoadFactory(void)
{
    nfactory = ReadProfilesYaml(defaultsPath, factory, MAXPROF, NULL, 0);
    if (nfactory < 0) nfactory = 0;
}

// factory values of a profile: its preset's entry in defaults.yaml, else a compiled-in preset,
// else the plain defaults; returns 1 when a preset was found
static int FactoryValues(const Profile *p, float *out)
{
    int b = BuiltinIndex(p->preset);                   // the built-ins, and copies made from them
    if (b >= 0) { memcpy(out, BUILTIN_V[b], sizeof BUILTIN_V[b]); return 1; }
    for (int i = 0; i < NPARAM; i++) out[i] = PD[i].def;
    for (int k = 0; k < nfactory; k++)
        if (strcasecmp(factory[k].name, p->preset) == 0) { memcpy(out, factory[k].v, sizeof factory[k].v); return 1; }
    for (int k = 0; k < NPRESETS; k++)
        if (strcasecmp(PRESETS[k].name, p->preset) == 0) { memcpy(out, PRESETS[k].v, sizeof PRESETS[k].v); return 1; }
    return 0;
}
static float FactoryValue(const Profile *p, int i) { float f[NPARAM]; FactoryValues(p, f); return f[i]; }
static int AtFactory(const Profile *p, int i) { return fabsf(p->v[i] - FactoryValue(p, i)) <= PD[i].step*0.5f; }
static int ProfileAtFactory(const Profile *p)
{
    for (int i = 0; i < NPARAM; i++) if (!AtFactory(p, i)) return 0;
    return 1;
}

// puts the built-in profiles at the top of the list
static void InsertBaseline(void)
{
    if (nprof > MAXPROF - NBUILTIN) nprof = MAXPROF - NBUILTIN;
    memmove(&prof[NBUILTIN], &prof[0], sizeof(Profile)*nprof);
    for (int b = 0; b < NBUILTIN; b++) {
        Profile *p = &prof[b];
        memset(p, 0, sizeof *p);
        snprintf(p->name, sizeof p->name, "%s", BUILTIN_NAME[b]);
        snprintf(p->preset, sizeof p->preset, "%s", BUILTIN_NAME[b]);
        memcpy(p->v, BUILTIN_V[b], sizeof p->v);
        memcpy(p->base, BUILTIN_V[b], sizeof p->base);
        p->builtin = 1;
    }
    nprof += NBUILTIN;
}

// selects the game's default profile
static void SelectDefault(void)
{
    sel = 0;
    for (int i = 0; i < nprof; i++) if (strcmp(prof[i].name, defaultName) == 0) sel = i;
}

// the profile list when profiles.yaml is missing: the factory profiles
static void DefaultProfiles(void)
{
    nprof = 0;
    int n = nfactory > 0 ? nfactory : NPRESETS;
    for (int k = 0; k < n && nprof < MAXPROF; k++) {
        Profile *p = &prof[nprof++];
        memset(p, 0, sizeof *p);
        snprintf(p->name, sizeof p->name, "%s", nfactory > 0 ? factory[k].name : PRESETS[k].name);
        snprintf(p->preset, sizeof p->preset, "%s", p->name);
        FactoryValues(p, p->v);
        memcpy(p->base, p->v, sizeof p->v);
    }
    snprintf(defaultName, sizeof defaultName, "%s", nprof ? prof[0].name : "");
    InsertBaseline();
    sel = 0;
}

// ---- the profiles (profiles.yaml, shared with the game) -----------------------------------
static int LoadProfiles(void)
{
    static YamlProfile yp[MAXPROF];
    char def[32];
    int n = ReadProfilesYaml(profPath, yp, MAXPROF - NBUILTIN, def, sizeof def);
    if (n <= 0) return 0;
    int k = 0;
    for (int i = 0; i < n; i++) {
        if (IsBaselineName(yp[i].name)) continue;              // the name is taken by the built-in one
        Profile *p = &prof[k++];
        memset(p, 0, sizeof *p);
        snprintf(p->name, sizeof p->name, "%s", yp[i].name);
        snprintf(p->preset, sizeof p->preset, "%s", yp[i].preset[0] ? yp[i].preset : yp[i].name);
        memcpy(p->v, yp[i].v, sizeof p->v);                    // missing values are the defaults
        memcpy(p->base, p->v, sizeof p->v);
    }
    if (!k) return 0;
    nprof = k;
    snprintf(defaultName, sizeof defaultName, "%s", def[0] ? (IsBaselineName(def) ? BUILTIN_NAME[BuiltinIndex(def)] : def) : prof[0].name);
    if (readOverlay >= 0) overlayPx = readOverlay > 200 ? 200 : readOverlay;
    if (readHidden >= 0) showHidden = readHidden;
    if (readMph >= 0) useMph = readMph;
    InsertBaseline();
    if (sel >= nprof) sel = 0;
    return 1;
}

// writes every profile's SAVED values: unsaved slider tweaks stay unsaved
static int WriteProfiles(void)
{
    FILE *f = fopen(profPath, "w");
    if (!f) return 0;
    int hasDefault = 0;
    for (int n = 0; n < nprof; n++) if (strcmp(prof[n].name, defaultName) == 0) hasDefault = 1;
    fprintf(f, "# SEGA Rally 3 - chase camera profiles, edited by CamLab.\n"
               "# PLAY.bat uses the default profile; pick another by name:\n"
               "#   PLAY.bat Drone\n"
               "# Framing (distance, height, fov) is optional: leave all three out for SR3's own.\n"
               "# \"preset\" is the entry in defaults.yaml that Reset returns a profile to.\n\n"
               "# \"SR3 Chase\" and \"SR3 Chase Far\" (built into CamLab) are SEGA Rally 3's own cameras.\n"
               "# In a race, View Change cycles the game's cameras, every profile, then the debug ones.\n"
               "# \"overlay\" is the size of the camera name shown on a change (px at 1080p, 0 = off);\n"
               "# \"hiddenCameras\" adds the cameras the game hides to View Change;\n"
               "# \"speedUnits\" is CamLab's speedometer: km/h or mph.\n\n"
               "default: %s\noverlay: %d\nhiddenCameras: %s\nspeedUnits: %s\n\nprofiles:\n", hasDefault ? defaultName : (nprof > NBUILTIN ? prof[NBUILTIN].name : ""),
               overlayPx, showHidden ? "true" : "false", useMph ? "mph" : "km/h");
    for (int n = 0; n < nprof; n++)
        if (!prof[n].builtin) WriteProfileYaml(f, prof[n].name, prof[n].base, NULL, prof[n].preset);
    fclose(f);
    return 1;
}

static int SaveSelected(void)
{
    float keep[NPARAM];
    memcpy(keep, prof[sel].base, sizeof keep);
    memcpy(prof[sel].base, prof[sel].v, sizeof keep);
    // the game validates its values, so keep the saved set consistent
    if (prof[sel].base[P_KMIN] > prof[sel].base[P_KMAX]) { float t = prof[sel].base[P_KMIN]; prof[sel].base[P_KMIN] = prof[sel].base[P_KMAX]; prof[sel].base[P_KMAX] = t; }
    prof[sel].base[P_FADE1] = fmaxf(prof[sel].base[P_FADE1], prof[sel].base[P_FADE0] + 1);
    memcpy(prof[sel].v, prof[sel].base, sizeof keep);
    if (WriteProfiles()) return 1;
    memcpy(prof[sel].base, keep, sizeof keep);             // not written: still unsaved
    return 0;
}

// ---- the game ------------------------------------------------------------------------------
// Launch starts SEGA Rally 3 through PLAY.bat with a profile, exactly like "PLAY.bat <name>".
__declspec(dllimport) void *__stdcall ShellExecuteA(void *hwnd, const char *op, const char *file, const char *params, const char *dir, int show);
static int GameAvailable(void)
{
    char bat[520], ps[520];
    snprintf(bat, sizeof bat, "%sPLAY.bat", GetApplicationDirectory());
    snprintf(ps, sizeof ps, "%spatch.ps1", GetApplicationDirectory());
    return FileExists(bat) && FileExists(ps);
}
// The game gets every profile, the selected one as it is on screen (unsaved tweaks included),
// through a scratch file in %TEMP%: launching is for trying things out and never touches
// profiles.yaml. It starts on the selected profile; View Change cycles through the others.
static int LaunchGame(const Profile *p)
{
    const char *tmp = getenv("TEMP");
    char bat[520], yaml[520], args[640];
    snprintf(yaml, sizeof yaml, "%s\\SR3CamLab_launch.yaml", tmp ? tmp : GetApplicationDirectory());
    FILE *f = fopen(yaml, "w");
    if (!f) return 0;
    fprintf(f, "# Written by CamLab's Launch button: the profiles as they were on screen.\n\n"
               "default: %s\noverlay: %d\nhiddenCameras: %s\n\nprofiles:\n", p->name, overlayPx, showHidden ? "true" : "false");
    for (int n = 0; n < nprof; n++) {
        if (prof[n].builtin) continue;
        float v[NPARAM];
        memcpy(v, &prof[n] == p ? prof[n].v : prof[n].base, sizeof v);
        // the game validates its values, so hand it a consistent set (as SaveSelected does)
        if (v[P_KMIN] > v[P_KMAX]) { float t = v[P_KMIN]; v[P_KMIN] = v[P_KMAX]; v[P_KMAX] = t; }
        v[P_FADE1] = fmaxf(v[P_FADE1], v[P_FADE0] + 1);
        WriteProfileYaml(f, prof[n].name, v, NULL, NULL);
    }
    fclose(f);
    snprintf(bat, sizeof bat, "%sPLAY.bat", GetApplicationDirectory());
    snprintf(args, sizeof args, "\"%s\" -ProfilesFile \"%s\"", p->name, yaml);
    return (intptr_t)ShellExecuteA(NULL, "open", bat, args, GetApplicationDirectory(), 1) > 32;
}
#endif

// ============================================================== chase camera (swings into the slide)
typedef struct { float yaw, yawVel, k, eyeY, offset, placed; int init; Vector3 eye, look; } Cam;

// soft angle limit: free up to the knee, then resistance builds like a stiffening spring
static float SoftLimit(float a, float maxDeg, float cap)
{
    if (maxDeg >= 180) return a;
    float m = maxDeg*DEG2RAD, knee = cap*m, range = fmaxf(m - knee, 1e-4f), x = fabsf(a);
    if (x <= knee) return a;
    float u = (x - knee)/range;
    return copysignf(knee + range*u/sqrtf(1 + u*u), a);
}

static void CamUpdate(Cam *cm, const Car *c, const float *p, float dt)
{
    float speed = CarSpeed(c), heading = c->yaw, travel = CarTravel(c);
    float f0 = p[P_FADE0], f1 = fmaxf(p[P_FADE1], f0 + 1);
    float fade = Clampf((speed*3.6f - f0)/(f1 - f0), 0, 1);
    float slip = WrapAngle(travel - heading);
    float w = p[P_STRENGTH]*fade*Clampf(cosf(slip)*2, 0, 1);    // fades out in spins and when reversing
    float target = heading + w*slip;
    if (!cm->init) {
        cm->yaw = target; cm->yawVel = 0; cm->k = p[P_KMAX];
        cm->eyeY = c->pos.y + p[P_HEIGHT]; cm->init = 1;
    }
    float kT = (c->ground && !c->drift) ? p[P_KMAX] : p[P_KMIN];
    cm->k += (kT - cm->k)*(1 - expf(-dt/0.35f));
    float err = WrapAngle(cm->yaw - target);
    cm->yawVel += -cm->k*err*dt;
    cm->yawVel += -p[P_DAMP]*cm->yawVel*dt;
    cm->yaw = heading + WrapAngle(cm->yaw + cm->yawVel*dt - heading);
    cm->offset = WrapAngle(cm->yaw - heading);
    cm->placed = SoftLimit(cm->offset, p[P_MAXANG], p[P_CAP]);

    // Framing the way SR3 does it, measured in the game's memory (camera object and final view
    // matrix) and checked against frames captured from the game: the camera pivots on a point
    // 0.85 m behind the car's centre at roof height (1.4 m), sits Distance behind it and
    // Height - 1 m above it, and looks straight AT it. So more height (or less distance) looks
    // down more steeply. At speed the game's own target point trails the car, so the camera
    // looks closer to that point but not to the car: in frames captured at 0 and 200 km/h the
    // car is the same size on screen. So the distance doesn't change with speed here.
    float behind = p[P_DIST], up = p[P_HEIGHT] + 0.4f;
    Vector3 back = Fwd(heading + cm->placed), hf = Fwd(heading);
    Vector3 pivot = Add(c->pos, Scl(hf, -0.85f));
    cm->eyeY += (c->pos.y + up - cm->eyeY)*(1 - expf(-dt*7.0f));
    cm->eye = V3(pivot.x - back.x*behind, fmaxf(cm->eyeY, c->pos.y + 0.6f), pivot.z - back.z*behind);
    cm->look = V3(pivot.x, c->pos.y + 1.4f, pivot.z);
}

#ifndef CAMLAB_SELFTEST
// ============================================================== palette
static const Color C_FOG     = { 233, 214, 200, 255 };
static const Color C_GRASS1  = { 120, 148, 102, 255 };
static const Color C_GRASS2  = { 113, 141,  96, 255 };
static const char *SURF_NAME[SURF_COUNT] = { "TARMAC", "GRAVEL", "MUD", "SNOW" };
static const Color C_SURF[SURF_COUNT][2] = {                    // two shades per surface, alternating
    { {  80,  84,  94, 255 }, {  75,  79,  89, 255 } },           // tarmac
    { { 176, 152, 120, 255 }, { 169, 146, 114, 255 } },           // gravel
    { { 128, 100,  78, 255 }, { 121,  94,  73, 255 } },           // mud
    { { 228, 232, 238, 255 }, { 219, 224, 232, 255 } },           // snow
};
static const Color C_CURB_R  = { 214,  90,  74, 255 };
static const Color C_CURB_W  = { 238, 236, 230, 255 };
static const Color C_LINE    = { 240, 236, 222, 255 };
static const Color C_BANK    = { 134, 150, 104, 255 };
static const Color C_POST    = { 246, 244, 238, 255 };
static const Color C_CAR     = { 255, 134,  74, 255 };
static const Color C_CABIN   = {  52,  60,  80, 255 };
static const Color C_MOUNT   = { 118, 138, 178, 255 };

static const Color UI_BG     = {  20,  22,  28, 228 };
static const Color UI_TEXT   = { 236, 238, 244, 255 };
static const Color UI_SUB    = { 158, 164, 178, 255 };
static const Color UI_FAINT  = { 104, 110, 124, 255 };
static const Color UI_ACCENT = { 255, 138,  76, 255 };

// ============================================================== flat-shaded renderer
// vector helpers only the renderer needs
static float Smooth01(float t) { t = Clampf(t, 0, 1); return t*t*(3 - 2*t); }
static Vector3 Sub(Vector3 a, Vector3 b) { return V3(a.x - b.x, a.y - b.y, a.z - b.z); }
static Vector3 Cross(Vector3 a, Vector3 b) { return V3(a.y*b.z - a.z*b.y, a.z*b.x - a.x*b.z, a.x*b.y - a.y*b.x); }
static float Len(Vector3 a) { return sqrtf(Dot(a, a)); }
static Vector3 Norm(Vector3 a) { float l = Len(a); return l > 1e-6f ? Scl(a, 1.0f/l) : a; }

#define FOG0 90.0f
#define FOG1 620.0f
static Vector3 gEye, gOrg, LIGHT;
static int triCount = 0;

// Depth. rlgl has no polygon offset, so declare the few GL 1.1 entry points we need straight
// from opengl32 (already linked). Overlays that lie ON another surface (road markings, the
// car's shadow) share its exact plane - geometry is never nudged - and are drawn in their own
// pass with a polygon-offset tier plus the base plane's slope factor: equal slopes cannot
// invert the order, and the units tier wins where the slope term vanishes (head-on, far away).
#define GL_POLYGON_OFFSET_FILL 0x8037
#if defined(_WIN32)
#define CL_GLIMPORT __declspec(dllimport)
#define CL_GLAPI    __stdcall
#else
#define CL_GLIMPORT
#define CL_GLAPI
#endif
extern CL_GLIMPORT void CL_GLAPI glEnable(unsigned int cap);
extern CL_GLIMPORT void CL_GLAPI glDisable(unsigned int cap);
extern CL_GLIMPORT void CL_GLAPI glPolygonOffset(float factor, float units);
#define DEPTH_SLOPE_GROUND  (-2.0f)    // shared slope factor of everything lying on the road
#define DEPTH_TIER_SHADOW   (-24.0f)   // car shadow: units above the road it lies on
#define CLIP_NEAR 0.5f                 // nothing gets closer to the camera than the car's bumper
#define CLIP_FAR  1500.0f              // sky dome and mountains sit at 730-800 m

// Render-origin shift: the stage runs forever, so absolute coordinates grow without bound and
// float precision on the GPU would degrade the further you drive. Vertices are submitted
// relative to a 1 km-aligned origin near the camera; lighting and fog stay in world space.
static void Vtx(Vector3 p, Color c) { rlColor4ub(c.r, c.g, c.b, c.a); rlVertex3f(p.x - gOrg.x, p.y, p.z - gOrg.z); }

static void OverlayBegin(float units, int writeDepth)
{
    rlEnd(); rlDrawRenderBatchActive();                  // flush the base geometry before the state change
    glEnable(GL_POLYGON_OFFSET_FILL);
    glPolygonOffset(DEPTH_SLOPE_GROUND, units);
    if (!writeDepth) rlDisableDepthMask();
    rlBegin(RL_TRIANGLES); triCount = 0;
}
static void OverlayEnd(void)
{
    rlEnd(); rlDrawRenderBatchActive();                  // the overlay must be drawn while the offset is on
    glDisable(GL_POLYGON_OFFSET_FILL);
    rlEnableDepthMask();
    rlBegin(RL_TRIANGLES); triCount = 0;
}
static void Tri(Vector3 a, Vector3 b, Vector3 c, Color col)
{
    if (++triCount > 9000) { rlEnd(); rlDrawRenderBatchActive(); rlBegin(RL_TRIANGLES); triCount = 1; }
    Vtx(a, col); Vtx(b, col); Vtx(c, col);
}
static Color Lit(Color base, Vector3 a, Vector3 b, Vector3 c, float fogOverride)
{
    Vector3 n = Norm(Cross(Sub(b, a), Sub(c, a)));
    Vector3 ctr = Scl(Add(Add(a, b), c), 1.0f/3.0f), toEye = Sub(gEye, ctr);
    if (Dot(n, toEye) < 0) n = Scl(n, -1);                      // two-sided: light the side we see
    float s = 0.60f + 0.40f*fmaxf(0, Dot(n, LIGHT));
    float fg = fogOverride >= 0 ? fogOverride : Smooth01((Len(toEye) - FOG0)/(FOG1 - FOG0));
    return (Color){ (unsigned char)Lerpf(base.r*s, C_FOG.r, fg), (unsigned char)Lerpf(base.g*s, C_FOG.g, fg),
                    (unsigned char)Lerpf(base.b*s, C_FOG.b, fg), base.a };
}
static void QuadLit(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Color base)
{
    Color k = Lit(base, a, b, c, -1);
    Tri(a, b, c, k); Tri(a, c, d, k);
}
static void BoxLit(Vector3 c, Vector3 ax, Vector3 ay, Vector3 az, Color col)
{
    static const int F[6][4] = { {0,1,3,2}, {4,5,7,6}, {0,1,5,4}, {2,3,7,6}, {0,2,6,4}, {1,3,7,5} };
    Vector3 p[8];
    for (int i = 0; i < 8; i++)
        p[i] = Add(Add(Add(c, Scl(ax, (i & 1) ? 1.0f : -1.0f)), Scl(ay, (i & 2) ? 1.0f : -1.0f)), Scl(az, (i & 4) ? 1.0f : -1.0f));
    for (int f = 0; f < 6; f++) QuadLit(p[F[f][0]], p[F[f][1]], p[F[f][2]], p[F[f][3]], col);
}

static Vector3 SkyPt(float r, float az, float el) { return Add(gEye, V3(r*cosf(el)*sinf(az), r*sinf(el), r*cosf(el)*cosf(az))); }

static void DrawSky(void)
{
    static const float el[] = { -30, 0, 4, 10, 19, 32, 52, 90 };
    static const Color bc[] = { { 233,214,200,255 }, { 229,211,202,255 }, { 210,205,214,255 }, { 178,190,214,255 },
                                { 143,168,207,255 }, { 112,144,196,255 }, {  88,121,184,255 } };
    rlDrawRenderBatchActive();
    rlDisableDepthTest(); rlDisableDepthMask();
    rlBegin(RL_TRIANGLES); triCount = 0;
    const int S = 40; const float R = 800;
    for (int b = 0; b < 7; b++)
        for (int s = 0; s < S; s++) {
            float a0 = s*2*PI/S, a1 = (s + 1)*2*PI/S, e0 = el[b]*DEG2RAD, e1 = el[b + 1]*DEG2RAD;
            Vector3 p00 = SkyPt(R, a0, e0), p10 = SkyPt(R, a1, e0), p01 = SkyPt(R, a0, e1), p11 = SkyPt(R, a1, e1);
            Tri(p00, p10, p11, bc[b]); Tri(p00, p11, p01, bc[b]);
        }
    Vector3 sc = Add(gEye, Scl(LIGHT, 760)), u = Norm(Cross(LIGHT, V3(0, 1, 0))), w = Cross(u, LIGHT);
    for (int ring = 0; ring < 2; ring++) {                            // sun: soft halo + flat disc
        float rad = ring ? 30.0f : 70.0f; Color col = ring ? (Color){ 255, 243, 222, 255 } : (Color){ 255, 236, 205, 70 };
        for (int s = 0; s < 20; s++) {
            float a0 = s*2*PI/20, a1 = (s + 1)*2*PI/20;
            Tri(sc, Add(sc, Add(Scl(u, cosf(a0)*rad), Scl(w, sinf(a0)*rad))), Add(sc, Add(Scl(u, cosf(a1)*rad), Scl(w, sinf(a1)*rad))), col);
        }
    }
    rlEnd(); rlDrawRenderBatchActive();
    rlEnableDepthMask(); rlEnableDepthTest();
}

// distant mountains fade towards the cool sky just above the horizon, not the warm ground haze
static Color Haze(Color c)
{
    const Color h = { 184, 194, 216, 255 };
    return (Color){ (unsigned char)Lerpf(c.r, h.r, 0.5f), (unsigned char)Lerpf(c.g, h.g, 0.5f), (unsigned char)Lerpf(c.b, h.b, 0.5f), 255 };
}

static void DrawMountains(void)
{
    enum { N = 56 };
    for (int i = 0; i < N; i++) {
        unsigned hsh = (unsigned)i*2654435761u; hsh ^= hsh >> 15;
        float a = (i + 0.5f)*2*PI/N, h = 45.0f + (hsh % 1000)*0.10f, half = PI/N*1.35f;
        Vector3 peak = V3(gEye.x + sinf(a)*730, h, gEye.z + cosf(a)*730);
        Vector3 l = V3(gEye.x + sinf(a - half)*780, 0, gEye.z + cosf(a - half)*780);
        Vector3 r = V3(gEye.x + sinf(a + half)*780, 0, gEye.z + cosf(a + half)*780);
        Vector3 m = V3(gEye.x + sinf(a)*800, 0, gEye.z + cosf(a)*800);
        Tri(l, peak, m, Haze(Lit(C_MOUNT, l, peak, m, 0)));
        Tri(m, peak, r, Haze(Lit(C_MOUNT, m, peak, r, 0)));
    }
}

static void DrawGround(void)
{
    const float T = 40; const int N = 19;
    int gx = (int)floorf(gEye.x/T), gz = (int)floorf(gEye.z/T);
    for (int i = -N; i <= N; i++)
        for (int j = -N; j <= N; j++) {
            float x0 = (gx + i)*T, z0 = (gz + j)*T;
            QuadLit(V3(x0, 0, z0), V3(x0 + T, 0, z0), V3(x0 + T, 0, z0 + T), V3(x0, 0, z0 + T),
                    ((gx + i + gz + j) & 1) ? C_GRASS1 : C_GRASS2);
        }
}

static Vector3 Edge(const TrackPt *t, float off, float dy)
{
    Vector3 r = Right(t->yaw);
    return V3(t->p.x + r.x*off, t->p.y + dy, t->p.z + r.z*off);
}

// The road surface of one segment is built from lateral strips: verge/curb, road, the centre-line
// strip, road, verge/curb. Everything that lies on the road uses these exact triangles: the centre
// line redraws its strip bit-identically, and the shadow is clipped onto them.
enum { STRIP_EDGE_L, STRIP_ROAD_L, STRIP_CENTRE, STRIP_ROAD_R, STRIP_EDGE_R, STRIPS };
static const float STRIP_X[STRIPS + 1] = { -(ROAD_HW + CURB_W), -ROAD_HW, -0.14f, 0.14f, ROAD_HW, ROAD_HW + CURB_W };

// the two triangles of strip s of segment i (same vertex order everywhere they are used)
static void StripTris(long i, int s, Vector3 t[2][3])
{
    TrackPt *a = TP(i), *b = TP(i + 1);
    Vector3 a0 = Edge(a, STRIP_X[s], 0), a1 = Edge(a, STRIP_X[s + 1], 0);
    Vector3 b0 = Edge(b, STRIP_X[s], 0), b1 = Edge(b, STRIP_X[s + 1], 0);
    t[0][0] = a0; t[0][1] = a1; t[0][2] = b1;
    t[1][0] = a0; t[1][1] = b1; t[1][2] = b0;
}

static void StripDraw(long i, int s, Color base)
{
    Vector3 t[2][3];
    StripTris(i, s, t);
    for (int k = 0; k < 2; k++) Tri(t[k][0], t[k][1], t[k][2], Lit(base, t[k][0], t[k][1], t[k][2], -1));
}

// How far the embankment of sample i reaches out on side s (-1 left, +1 right). On the inside
// of a curve it must stay short of the curve's centre, or neighbouring bank quads fold over
// each other and z-fight; it is a function of the sample alone, so adjacent quads agree.
static float BankSpread(long i, int s)
{
    const float E = ROAD_HW + CURB_W;
    float spread = E + TP(i)->p.y*1.8f, kmax = 0;
    for (long j = i - 12; j <= i + 12; j++) {
        float k = TP(j)->k;
        if (k*(float)s < 0) kmax = fmaxf(kmax, fabsf(k));     // this side is the inside of the curve
    }
    if (kmax > 1e-4f) spread = fminf(spread, fmaxf(E + 0.5f, 0.8f/kmax));
    return spread;
}

static void DrawTrack(long center)
{
    const float E = ROAD_HW + CURB_W;
    for (long i = center - 30; i < center + 330; i++) {
        if (i < 0 || i + 1 > trkHead) continue;
        TrackPt *a = TP(i), *b = TP(i + 1);
        int tarmac = a->surf == SURF_TARMAC;
        Color road = C_SURF[a->surf][(i/12) & 1];
        // tarmac gets red/white curbs and a centre line; loose surfaces a darker, rougher verge
        Color edge = tarmac ? (((i/2) & 1) ? C_CURB_R : C_CURB_W)
                            : (Color){ (unsigned char)(road.r*0.82f), (unsigned char)(road.g*0.82f), (unsigned char)(road.b*0.82f), 255 };
        for (int s = 0; s < STRIPS; s++) StripDraw(i, s, (s == STRIP_EDGE_L || s == STRIP_EDGE_R) ? edge : road);
        for (int s = -1; s <= 1; s += 2) {                         // embankment down to the ground
            QuadLit(Edge(a, s*E, 0), Edge(b, s*E, 0), Edge(b, s*BankSpread(i + 1, s), -b->p.y),
                    Edge(a, s*BankSpread(i, s), -a->p.y), C_BANK);
            if (i % 20 == 0) {
                Vector3 f = Fwd(a->yaw), up = V3(0, 1, 0), r = Right(a->yaw);
                BoxLit(Edge(a, s*(E + 1.4f), 0.6f), Scl(f, 0.13f), Scl(up, 0.6f), Scl(r, 0.13f), C_POST);
            }
        }
    }
}

// centre-line dashes: the centre strip redrawn with its exact vertices, so its depth is
// bit-identical and GL_LEQUAL (raylib's default) seats it - no offset, no nudge
static void DrawRoadMarkings(long center)
{
    for (long i = center - 30; i < center + 330; i++) {
        if (i < 0 || i + 1 > trkHead) continue;
        if (TP(i)->surf == SURF_TARMAC && (i/3) % 2 == 0) StripDraw(i, STRIP_CENTRE, C_LINE);
    }
}

// clip polygon (xz) against the half-plane dot(p - o, n) <= d; returns the new vertex count
static int ClipHalf(Vector3 *in, int n, Vector3 *out, Vector3 o, Vector3 axis, float d)
{
    int m = 0;
    for (int k = 0; k < n; k++) {
        Vector3 p = in[k], q = in[(k + 1) % n];
        float dp = (p.x - o.x)*axis.x + (p.z - o.z)*axis.z - d, dq = (q.x - o.x)*axis.x + (q.z - o.z)*axis.z - d;
        if (dp <= 0) out[m++] = p;
        if ((dp < 0) != (dq < 0) && dp != dq) { float t = dp/(dp - dq); out[m++] = Add(p, Scl(Sub(q, p), t)); }
    }
    return m;
}

// Shadow quad (centre o, forward f, right r, half sizes) laid onto the road: clipped against
// every road/verge triangle below it, each piece lifted onto that triangle's own plane.
static void ShadowOnRoad(long center, Vector3 o, Vector3 f, Vector3 r, float hz, float hx, Color col)
{
    for (long i = center - 12; i <= center + 12; i++) {
        if (i < 0 || i + 1 > trkHead) continue;
        for (int s = 0; s < STRIPS; s++) {
            Vector3 t[2][3];
            StripTris(i, s, t);
            for (int k = 0; k < 2; k++) {
                Vector3 A = t[k][0], B = t[k][1], C = t[k][2], p0[8] = { A, B, C }, p1[8];
                int n = ClipHalf(p0, 3, p1, o, f, hz);
                n = ClipHalf(p1, n, p0, o, Scl(f, -1), hz);
                n = ClipHalf(p0, n, p1, o, r, hx);
                n = ClipHalf(p1, n, p0, o, Scl(r, -1), hx);
                if (n < 3) continue;
                Vector3 nrm = Cross(Sub(B, A), Sub(C, A));
                if (fabsf(nrm.y) < 1e-6f) continue;
                for (int v = 0; v < n; v++)                              // exactly on the triangle's plane
                    p0[v].y = A.y - (nrm.x*(p0[v].x - A.x) + nrm.z*(p0[v].z - A.z))/nrm.y;
                for (int v = 1; v + 1 < n; v++) Tri(p0[0], p0[v], p0[v + 1], col);
            }
        }
    }
}

static void CarBasis(const Car *c, Vector3 *f, Vector3 *u, Vector3 *r)
{
    Vector3 f0 = Fwd(c->yaw), r0 = Right(c->yaw), up = V3(0, 1, 0);
    float cp = cosf(c->pitch), sp = sinf(c->pitch), cr = cosf(c->roll), sr = sinf(c->roll);
    Vector3 ff = Add(Scl(f0, cp), Scl(up, sp)), uu = Sub(Scl(up, cp), Scl(f0, sp));
    *f = ff;
    *r = Add(Scl(r0, cr), Scl(uu, sr));
    *u = Sub(Scl(uu, cr), Scl(r0, sr));
}

// ---- the car: a low-poly rally hatchback -------------------------------------------------
// Local frame: x to the right, y up from the ground contact, z forward; ~4.3 m x 1.9 m.
typedef struct { Vector3 o, f, u, r; } CarFrame;
static Vector3 CarPt(const CarFrame *k, float x, float y, float z)
{
    return Add(k->o, Add(Scl(k->r, x), Add(Scl(k->u, y), Scl(k->f, z))));
}

// a cross-section of a lofted part: position along the car, half width, bottom and top heights
typedef struct { float z, hw, y0, y1; } Section;

// Lofts consecutive sections into a closed shell. With `glass`, the sides, the end caps and
// the steep tops (windscreen, rear window) are glass and only the flat top (roof) is body.
static void Loft(const CarFrame *k, const Section *s, int n, Color body, const Color *glass)
{
    Color side = glass ? *glass : body;
    for (int i = 0; i + 1 < n; i++) {
        const Section *a = &s[i], *b = &s[i + 1];
        Vector3 aTL = CarPt(k, -a->hw, a->y1, a->z), aTR = CarPt(k, a->hw, a->y1, a->z);
        Vector3 bTL = CarPt(k, -b->hw, b->y1, b->z), bTR = CarPt(k, b->hw, b->y1, b->z);
        Vector3 aBL = CarPt(k, -a->hw, a->y0, a->z), aBR = CarPt(k, a->hw, a->y0, a->z);
        Vector3 bBL = CarPt(k, -b->hw, b->y0, b->z), bBR = CarPt(k, b->hw, b->y0, b->z);
        int steep = fabsf(b->y1 - a->y1) > 0.35f*fabsf(b->z - a->z);
        QuadLit(aTL, aTR, bTR, bTL, glass && steep ? *glass : body);           // top
        QuadLit(aTL, bTL, bBL, aBL, side);                                     // left
        QuadLit(aTR, aBR, bBR, bTR, side);                                     // right
        QuadLit(aBL, bBL, bBR, aBR, body);                                     // underside
    }
    const Section *e[2] = { &s[0], &s[n - 1] };                               // nose and tail caps
    for (int j = 0; j < 2; j++)
        QuadLit(CarPt(k, -e[j]->hw, e[j]->y0, e[j]->z), CarPt(k, e[j]->hw, e[j]->y0, e[j]->z),
                CarPt(k, e[j]->hw, e[j]->y1, e[j]->z), CarPt(k, -e[j]->hw, e[j]->y1, e[j]->z), side);
}

// an octagonal wheel standing on the ground, axle along x; the hub is its own inner ring of
// the side wall (not a face on top of it), so nothing is coplanar
static void Wheel(const CarFrame *k, float x, float z, float radius, float width)
{
    const Color tyre = { 38, 40, 46, 255 }, hub = { 150, 154, 162, 255 };
    Vector3 ring[2][8];
    for (int side = 0; side < 2; side++)
        for (int j = 0; j < 8; j++) {
            float a = (j + 0.5f)*PI/4;
            ring[side][j] = CarPt(k, x + (side ? width : -width)*0.5f, radius + radius*sinf(a), z + radius*cosf(a));
        }
    for (int j = 0; j < 8; j++) QuadLit(ring[0][j], ring[0][(j + 1) % 8], ring[1][(j + 1) % 8], ring[1][j], tyre);
    for (int side = 0; side < 2; side++) {
        Vector3 c = CarPt(k, x + (side ? width : -width)*0.5f, radius, z);
        for (int j = 0; j < 8; j++) {
            Vector3 p = ring[side][j], q = ring[side][(j + 1) % 8];
            Vector3 hp = Add(c, Scl(Sub(p, c), 0.55f)), hq = Add(c, Scl(Sub(q, c), 0.55f));
            QuadLit(hp, p, q, hq, tyre);
            Tri(c, hp, hq, Lit(hub, c, hp, hq, -1));
        }
    }
}

static void DrawCar(const Car *c)
{
    CarFrame k;
    CarBasis(c, &k.f, &k.u, &k.r);
    k.o = c->pos;
    static const Section body[] = {                        // nose -> tail
        {  2.15f, 0.82f, 0.32f, 0.62f },                   // bumper
        {  1.85f, 0.93f, 0.30f, 0.80f },                   // front of the bonnet
        {  0.55f, 0.93f, 0.34f, 0.92f },                   // base of the windscreen
        { -1.85f, 0.93f, 0.34f, 0.94f },
        { -2.15f, 0.86f, 0.36f, 0.90f },                   // tail
    };
    static const Section cabin[] = {                       // glasshouse, its bottom seated inside the body
        {  0.55f, 0.84f, 0.86f, 0.92f },                   // windscreen base
        { -0.20f, 0.74f, 0.86f, 1.42f },                   // roof front
        { -1.35f, 0.74f, 0.86f, 1.44f },                   // roof rear
        { -1.90f, 0.82f, 0.86f, 1.02f },                   // hatch window base
    };
    const Color glass = C_CABIN, dark = { 34, 36, 42, 255 };
    Loft(&k, body, 5, C_CAR, NULL);
    Loft(&k, cabin, 4, C_CAR, &glass);
    // the tyres stand 7 cm proud of the body sides: clearly apart, never face-to-face
    for (int sx = -1; sx <= 1; sx += 2)
        for (int sz = -1; sz <= 1; sz += 2) Wheel(&k, sx*0.86f, sz*1.35f, 0.34f, 0.28f);
    // roof spoiler on two struts (their ends buried in the cabin and in the wing)
    BoxLit(CarPt(&k, 0, 1.50f, -1.50f), Scl(k.f, 0.17f), Scl(k.u, 0.03f), Scl(k.r, 0.80f), dark);
    for (int sx = -1; sx <= 1; sx += 2)
        BoxLit(CarPt(&k, sx*0.50f, 1.38f, -1.55f), Scl(k.f, 0.04f), Scl(k.u, 0.10f), Scl(k.r, 0.03f), dark);
    // head and tail lights poke 2 cm out of the end caps
    for (int sx = -1; sx <= 1; sx += 2) {
        BoxLit(CarPt(&k, sx*0.58f, 0.50f, 2.13f), Scl(k.f, 0.04f), Scl(k.u, 0.07f), Scl(k.r, 0.16f), (Color){ 250, 246, 226, 255 });
        BoxLit(CarPt(&k, sx*0.64f, 0.72f, -2.13f), Scl(k.f, 0.04f), Scl(k.u, 0.07f), Scl(k.r, 0.15f), (Color){ 210, 40, 36, 255 });
    }
}

// the car's shadow: an overlay in the road's plane (drawn inside OverlayBegin/End)
static void DrawShadow(const Car *c)
{
    // cast along the sun direction: it slides away from the car as soon as it leaves the
    // ground, and only softens a little with height, so a jump is always readable
    float air = fmaxf(c->pos.y - c->surfY, 0), h = Clampf(air/8.0f, 0, 1);
    Vector3 f = Fwd(c->yaw), r = Right(c->yaw);
    float ox = -LIGHT.x/LIGHT.y*air, oz = -LIGHT.z/LIGHT.y*air;
    for (int layer = 0; layer < 2; layer++) {
        float grow = layer ? 0.35f : 0.0f, sx = 0.95f + h*0.4f + grow, sz = 2.15f + h*0.4f + grow;
        unsigned char a = (unsigned char)((layer ? 70 : 150)*(1 - 0.45f*h));
        Color col = { 16, 18, 28, a };
        ShadowOnRoad(c->idx, V3(c->pos.x + ox, 0, c->pos.z + oz), f, r, sz, sx, col);
    }
}

// ============================================================== UI (immediate mode, DPI aware)
static float S = 1;                                  // UI scale = monitor DPI scale
#define U(x) ((x)*S)
typedef struct { Font f; float size; } UFont;
static UFont fReg, fSemi, fSmall, fBig, fTitle;

static int cps[128]; static int ncps = 0;
static UFont LoadUFont(const char *file, float size)
{
    UFont u = { GetFontDefault(), size };
    const char *win = getenv("WINDIR");
    char path[512];
    snprintf(path, sizeof path, "%s\\Fonts\\%s", win ? win : "C:\\Windows", file);
    if (FileExists(path)) {
        u.f = LoadFontEx(path, (int)roundf(size*S), cps, ncps);
        SetTextureFilter(u.f.texture, TEXTURE_FILTER_BILINEAR);
    }
    return u;
}
// the UI fonts at the current scale S (again after S changes)
static void LoadFonts(void)
{
    UFont *all[] = { &fReg, &fSemi, &fSmall, &fTitle, &fBig };
    for (int i = 0; i < 5; i++)
        if (all[i]->f.texture.id && all[i]->f.texture.id != GetFontDefault().texture.id) UnloadFont(all[i]->f);
    fReg   = LoadUFont("segoeui.ttf", 15);
    fSemi  = LoadUFont("seguisb.ttf", 14);
    fSmall = LoadUFont("segoeui.ttf", 12.5f);
    fTitle = LoadUFont("seguisb.ttf", 20);
    fBig   = LoadUFont("seguisb.ttf", 46);
}
static void TxtSp(const UFont *f, const char *s, float x, float y, float sp, Color c) { DrawTextEx(f->f, s, (Vector2){ floorf(x), floorf(y) }, f->size*S, sp, c); }
static void Txt(const UFont *f, const char *s, float x, float y, Color c) { TxtSp(f, s, x, y, 0, c); }
static float TxtWSp(const UFont *f, const char *s, float sp) { return MeasureTextEx(f->f, s, f->size*S, sp).x; }
static float TxtW(const UFont *f, const char *s) { return TxtWSp(f, s, 0); }
static void RoundRect(Rectangle r, float rad, Color c)
{
    float m = fminf(r.width, r.height);
    if (m <= 0) return;
    DrawRectangleRounded(r, Clampf(2*rad/m, 0, 1), 8, c);
}
static Color Mix(Color a, Color b, float t)
{
    return (Color){ (unsigned char)Lerpf(a.r, b.r, t), (unsigned char)Lerpf(a.g, b.g, t), (unsigned char)Lerpf(a.b, b.b, t), (unsigned char)Lerpf(a.a, b.a, t) };
}

static struct {
    int active, renaming, pressedOn;
    float scroll, contentH;
    Rectangle panel;
    char buf[32]; int caretBlink;
    double lastClickT; int lastClickRow;
    int tipId, tipSeen, tipCand; float tipT;             // tooltip: shown id, hover time, this frame's offer
    Rectangle tipAnchor; char tipTitle[48], tipBody[320];
    float dragGrab;                                      // scrollbar: where the thumb was grabbed
} ui = { .active = -1, .renaming = -1, .pressedOn = -1, .lastClickRow = -1, .tipId = -1 };

// draws text word-wrapped to maxW; returns the height used (draw = 0 only measures)
static float WrapText(const UFont *f, const char *text, float x, float y, float maxW, Color c, int draw)
{
    char line[256] = "", word[64];
    float lh = f->size*S*1.32f, h = 0;
    const char *p = text;
    while (*p) {
        int n = 0;
        while (*p == ' ') p++;
        while (*p && *p != ' ' && n < (int)sizeof word - 1) word[n++] = *p++;
        word[n] = 0;
        if (!n) break;
        char trial[256];
        snprintf(trial, sizeof trial, "%s%s%s", line, line[0] ? " " : "", word);
        if (line[0] && TxtW(f, trial) > maxW) {
            if (draw) Txt(f, line, x, y + h, c);
            h += lh;
            snprintf(line, sizeof line, "%s", word);
        } else snprintf(line, sizeof line, "%s", trial);
    }
    if (line[0]) { if (draw) Txt(f, line, x, y + h, c); h += lh; }
    return h;
}

// ---- tooltips ------------------------------------------------------------------------------
// Anything can offer a tooltip while it is hovered (the last offer of a frame wins, so a small
// element inside a bigger one overrides it); it shows after a short hover. Panel tooltips sit
// to the left of the panel, pointing at their row; everything else gets one below or above.
static void TipsBegin(void) { ui.tipSeen = 0; }
static void Tip(int id, Rectangle anchor, const char *title, const char *body)
{
    if (ui.active >= 0 || ui.pressedOn >= 0) return;                    // not while dragging or clicking
    ui.tipSeen = 1; ui.tipCand = id; ui.tipAnchor = anchor;
    snprintf(ui.tipTitle, sizeof ui.tipTitle, "%s", title);
    snprintf(ui.tipBody, sizeof ui.tipBody, "%s", body);
}
static int Hover(Rectangle r);
static void PanelTip(int id, Rectangle r, const char *title, const char *body) { if (Hover(r)) Tip(id, r, title, body); }
static void HudTip(int id, Rectangle r, const char *title, const char *body)
{
    if (CheckCollisionPointRec(GetMousePosition(), r) && !CheckCollisionPointRec(GetMousePosition(), ui.panel)) Tip(id, r, title, body);
}

static void DrawTooltip(void)
{
    if (!ui.tipSeen) { ui.tipId = -1; return; }
    if (ui.tipCand != ui.tipId) { ui.tipId = ui.tipCand; ui.tipT = 0; }  // only the frame's winner restarts the timer
    ui.tipT += GetFrameTime();
    if (ui.tipT < 0.45f) return;
    float a = Clampf((ui.tipT - 0.45f)/0.12f, 0, 1);                  // quick fade-in
    float w = U(270), pad = U(14), tw = w - 2*pad;
    float h = pad + fSemi.size*S + U(6) + WrapText(&fSmall, ui.tipBody, 0, 0, tw, UI_TEXT, 0) + pad - U(4);
    float SW = (float)GetScreenWidth(), SH = (float)GetScreenHeight();
    Rectangle an = ui.tipAnchor;
    float acx = an.x + an.width/2, acy = an.y + an.height/2, x, y;
    Color bg = { 30, 33, 42, (unsigned char)(245*a) };
    if (ui.panel.width > 0 && CheckCollisionPointRec((Vector2){ acx, acy }, ui.panel)) {
        x = ui.panel.x - w - U(12);                                      // left of the panel, pointing right
        y = Clampf(acy - U(24), U(18), SH - h - U(18));
        RoundRect((Rectangle){ x, y, w, h }, U(12), bg);
        float cy = Clampf(acy, y + U(14), y + h - U(14));
        DrawTriangle((Vector2){ x + w, cy - U(7) }, (Vector2){ x + w, cy + U(7) }, (Vector2){ x + w + U(7), cy }, bg);
    } else {
        int below = an.y + an.height + U(10) + h < SH - U(8);          // below the element, else above it
        x = Clampf(acx - w/2, U(8), SW - w - U(8));
        y = below ? an.y + an.height + U(10) : an.y - U(10) - h;
        RoundRect((Rectangle){ x, y, w, h }, U(12), bg);
        float px = Clampf(acx, x + U(14), x + w - U(14));
        if (below) DrawTriangle((Vector2){ px, y - U(7) }, (Vector2){ px - U(7), y }, (Vector2){ px + U(7), y }, bg);
        else DrawTriangle((Vector2){ px - U(7), y + h }, (Vector2){ px, y + h + U(7) }, (Vector2){ px + U(7), y + h }, bg);
    }
    Txt(&fSemi, ui.tipTitle, x + pad, y + pad - U(2), (Color){ UI_ACCENT.r, UI_ACCENT.g, UI_ACCENT.b, (unsigned char)(255*a) });
    WrapText(&fSmall, ui.tipBody, x + pad, y + pad + fSemi.size*S + U(4), tw, (Color){ 225, 229, 238, (unsigned char)(255*a) }, 1);
}

static int Hover(Rectangle r) { return CheckCollisionPointRec(GetMousePosition(), r) && CheckCollisionPointRec(GetMousePosition(), ui.panel); }

// small circular-arrow "reset" button; returns 1 when clicked
static int ResetIcon(int id, Vector2 c, float r)
{
    Rectangle hit = { c.x - r - U(4), c.y - r - U(4), 2*r + U(8), 2*r + U(8) };
    int hov = Hover(hit), clicked = 0;
    if (hov && IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) ui.pressedOn = id;
    if (ui.pressedOn == id && IsMouseButtonReleased(MOUSE_BUTTON_LEFT)) { clicked = hov; ui.pressedOn = -1; }
    if (hov) DrawCircleV(c, r + U(4), (Color){ 255, 255, 255, 22 });
    Color col = hov ? UI_TEXT : UI_ACCENT;
    DrawRing(c, r - U(1.5f), r, 60, 330, 24, col);                       // open circle...
    float a = 60*DEG2RAD, rm = r - U(0.75f), sz = U(3.4f);                // ...with an arrowhead at its open end,
    Vector2 at = { c.x + cosf(a)*rm, c.y + sinf(a)*rm };                  // pointing back along the arc
    Vector2 dir = { sinf(a), -cosf(a) }, nrm = { cosf(a), sinf(a) };
    Vector2 tip = { at.x + dir.x*sz, at.y + dir.y*sz };
    Vector2 b1 = { at.x + nrm.x*sz*0.85f, at.y + nrm.y*sz*0.85f }, b2 = { at.x - nrm.x*sz*0.85f, at.y - nrm.y*sz*0.85f };
    DrawTriangle(tip, b1, b2, col);
    DrawTriangle(tip, b2, b1, col);                                      // either winding, so it always shows
    return clicked;
}

static void Slider(int id, float x, float y, float w, int p)
{
    Profile *pr = &prof[sel];
    float *v = &pr->v[p];
    Rectangle row = { x, y - U(2), w, U(34) };
    int hov = Hover(row);
    Rectangle tr = { x, y + U(23), w, U(4) };

    char val[32];
    if (p == P_MAXANG && *v >= 180) snprintf(val, sizeof val, "off");
    else snprintf(val, sizeof val, PD[p].fmt, *v);
    float vw = TxtW(&fReg, val);
    Vector2 rc = { x + w - vw - U(12), y + fReg.size*S*0.55f };           // reset micro-button, left of the value
    int unsaved = ParamDirty(pr, p);                                     // differs from the last save
    Rectangle rhit = { rc.x - U(10), rc.y - U(10), U(20), U(20) };
    int onReset = unsaved && CheckCollisionPointRec(GetMousePosition(), rhit);
    int locked = pr->builtin;                                            // Baseline: shown, not editable

    if (locked) {
        if (hov) Tip(100 + p, row, PD[p].label, TextFormat("%s %s uses SEGA Rally 3's own value, so this slider is locked. New makes an editable copy.", PARAM_TIP[p], pr->name));
        float tl = Clampf((*v - PD[p].mn)/(PD[p].mx - PD[p].mn), 0, 1);   // the game's spring is off the scale
        Txt(&fReg, PD[p].label, x, y, UI_FAINT);
        Txt(&fReg, val, x + w - vw, y, UI_FAINT);
        RoundRect(tr, U(2), (Color){ 255, 255, 255, 16 });
        RoundRect((Rectangle){ tr.x, tr.y, tr.width*tl, tr.height }, U(2), (Color){ 255, 255, 255, 46 });
        DrawCircleV((Vector2){ tr.x + tr.width*tl, tr.y + tr.height/2 }, U(5.5f), (Color){ 150, 154, 164, 255 });
        return;
    }
    if (hov && !onReset && IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && ui.renaming < 0) ui.active = id;
    if (ui.active == id) {
        if (IsMouseButtonDown(MOUSE_BUTTON_LEFT)) {
            float t = Clampf((GetMousePosition().x - tr.x)/tr.width, 0, 1);
            float nv = roundf((PD[p].mn + t*(PD[p].mx - PD[p].mn))/PD[p].step)*PD[p].step;
            *v = Clampf(nv, PD[p].mn, PD[p].mx);
        } else ui.active = -1;
    }
    if (hov && ui.active < 0) {
        float wh = GetMouseWheelMove();
        if (wh != 0 && (IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT)))
            *v = Clampf(roundf((*v + wh*PD[p].step)/PD[p].step)*PD[p].step, PD[p].mn, PD[p].mx);
        if (IsMouseButtonPressed(MOUSE_BUTTON_RIGHT)) *v = pr->base[p];
    }
    int act = ui.active == id;
    if (hov) {
        if (onReset) Tip(200 + p, row, "Undo", "Puts this slider back to its last saved value (the white tick on the track). Right-clicking the slider does the same.");
        else Tip(100 + p, row, PD[p].label, PARAM_TIP[p]);
    }
    Txt(&fReg, PD[p].label, x, y, (hov || act) ? UI_TEXT : Mix(UI_SUB, UI_TEXT, 0.35f));
    Txt(&fReg, val, x + w - vw, y, unsaved ? UI_ACCENT : UI_TEXT);            // orange = not saved yet
    if (unsaved && ResetIcon(200 + p, rc, U(5.5f))) *v = pr->base[p];
    float t = (*v - PD[p].mn)/(PD[p].mx - PD[p].mn);
    RoundRect(tr, U(2), (Color){ 255, 255, 255, 26 });
    RoundRect((Rectangle){ tr.x, tr.y, tr.width*t, tr.height }, U(2), act ? UI_ACCENT : Mix(UI_ACCENT, UI_SUB, 0.15f));
    if (unsaved) {                                                       // tick marking the saved value
        float tb = (pr->base[p] - PD[p].mn)/(PD[p].mx - PD[p].mn);
        DrawRectangleRec((Rectangle){ tr.x + tr.width*tb - U(1), tr.y - U(3), U(2), tr.height + U(6) }, (Color){ 255, 255, 255, 110 });
    }
    Vector2 knob = { tr.x + tr.width*t, tr.y + tr.height/2 };
    DrawCircleV(knob, U(act ? 8.5f : (hov ? 7.5f : 6.5f)), (Color){ 255, 255, 255, 255 });
    DrawCircleV(knob, U(act ? 4.0f : 3.2f), UI_ACCENT);
}

enum { BTN_GHOST, BTN_ACCENT, BTN_GREEN, BTN_BLUE };
static const Color UI_GREEN = { 76, 196, 120, 255 };
static const Color UI_BLUE  = { 64, 140, 255, 255 };
static const Color UI_TPL   = { 96, 160, 255, 255 };   // the templates

static int Button(int id, Rectangle r, const char *label, int kind, int enabled)
{
    int hov = enabled && Hover(r), clicked = 0;
    if (hov && IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) ui.pressedOn = id;
    if (ui.pressedOn == id && IsMouseButtonReleased(MOUSE_BUTTON_LEFT)) { clicked = hov; ui.pressedOn = -1; }
    int down = ui.pressedOn == id && IsMouseButtonDown(MOUSE_BUTTON_LEFT);
    Color bg, tc;
    if (kind == BTN_GHOST) { bg = (Color){ 255, 255, 255, (unsigned char)(down ? 44 : hov ? 30 : 16) }; tc = UI_TEXT; }
    else {
        Color base = kind == BTN_GREEN ? UI_GREEN : kind == BTN_BLUE ? UI_BLUE : UI_ACCENT;
        bg = down ? Mix(base, (Color){ 0, 0, 0, 255 }, 0.15f) : hov ? Mix(base, (Color){ 255, 255, 255, 255 }, 0.14f) : base;
        tc = (Color){ 24, 22, 20, 255 };
    }
    if (!enabled) { bg = (Color){ 255, 255, 255, 8 }; tc = UI_FAINT; }
    RoundRect(r, U(7), bg);
    float tw = TxtW(&fSemi, label);
    Txt(&fSemi, label, r.x + (r.width - tw)/2, r.y + (r.height - fSemi.size*S)/2 - U(1), tc);
    return clicked;
}

static void StartRename(void) { if (prof[sel].builtin) return; ui.renaming = sel; snprintf(ui.buf, sizeof ui.buf, "%s", prof[sel].name); }
static void CommitRename(void)
{
    if (ui.renaming < 0) return;
    CleanName(ui.buf);
    if (IsBaselineName(ui.buf)) { SetStatus("that name is reserved"); ui.renaming = -1; return; }
    if (ui.buf[0] && strcmp(ui.buf, prof[ui.renaming].name) != 0) {
        snprintf(prof[ui.renaming].name, sizeof prof[0].name, "%s", ui.buf);
        SetStatus(WriteProfiles() ? "renamed" : "could not write the file");
    }
    ui.renaming = -1;
}

static void RenameInput(void)
{
    if (ui.renaming < 0) return;
    int ch;
    while ((ch = GetCharPressed()) > 0)
        if (ch >= 32 && ch < 127 && ch != ',' && ch != '"' && strlen(ui.buf) < sizeof ui.buf - 1) {
            size_t n = strlen(ui.buf); ui.buf[n] = (char)ch; ui.buf[n + 1] = 0;
        }
    if ((IsKeyPressed(KEY_BACKSPACE) || IsKeyPressedRepeat(KEY_BACKSPACE)) && ui.buf[0]) ui.buf[strlen(ui.buf) - 1] = 0;
    if (IsKeyPressed(KEY_ENTER) || IsKeyPressed(KEY_KP_ENTER)) CommitRename();
    else if (IsKeyPressed(KEY_ESCAPE)) ui.renaming = -1;
}

static void AddProfile(void)
{
    if (nprof >= MAXPROF) { SetStatus("Profile limit reached"); return; }
    Profile np = prof[sel];
    np.builtin = 0;                                         // a copy of a built-in is editable; its preset stays the built-in
    for (int n = 1; n < 1000; n++) {
        snprintf(np.name, sizeof np.name, "Profile %d", n);
        int clash = 0;
        for (int i = 0; i < nprof; i++) if (strcmp(prof[i].name, np.name) == 0) clash = 1;
        if (!clash) break;
    }
    memcpy(np.base, np.v, sizeof np.v);                     // a new profile starts from what's on the car
    memmove(&prof[sel + 2], &prof[sel + 1], sizeof(Profile)*(nprof - sel - 1));
    prof[sel + 1] = np; nprof++; sel++;
    WriteProfiles();
    StartRename();
}

// A factory profile (one whose preset is in defaults.yaml) can be edited, saved and renamed,
// but the last profile carrying each factory preset cannot be removed; copies made with New can.
static int ProfileProtected(int i)
{
    float tmp[NPARAM];
    if (prof[i].builtin) return 1;
    if (!FactoryValues(&prof[i], tmp)) return 0;
    for (int j = 0; j < nprof; j++)
        if (j != i && strcasecmp(prof[j].preset, prof[i].preset) == 0) return 0;
    return 1;
}

static void RemoveProfile(void)
{
    if (nprof <= 1 || ProfileProtected(sel)) return;
    memmove(&prof[sel], &prof[sel + 1], sizeof(Profile)*(nprof - sel - 1));
    nprof--; if (sel >= nprof) sel = nprof - 1;
    SetStatus(WriteProfiles() ? "removed" : "could not write the file");
}

// a checkbox row; returns 1 when clicked
static int Checkbox(int id, float x, float y, float w, const char *label, int on, const char *tipTitle, const char *tipBody)
{
    Rectangle row = { x, y - U(2), w, U(24) };
    int hov = Hover(row), clicked = 0;
    if (hov && IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && ui.active < 0 && ui.renaming < 0) ui.pressedOn = id;
    if (ui.pressedOn == id && IsMouseButtonReleased(MOUSE_BUTTON_LEFT)) { clicked = hov; ui.pressedOn = -1; }
    if (hov) Tip(id, row, tipTitle, tipBody);
    Rectangle box = { x, y + U(1), U(16), U(16) };
    if (on) {
        RoundRect(box, U(4), hov ? Mix(UI_ACCENT, (Color){ 255, 255, 255, 255 }, 0.14f) : UI_ACCENT);
        Vector2 a = { box.x + U(3.5f), box.y + U(8.5f) }, b = { box.x + U(6.8f), box.y + U(11.8f) }, c = { box.x + U(12.5f), box.y + U(4.5f) };
        DrawLineEx(a, b, U(2.2f), (Color){ 24, 22, 20, 255 });
        DrawLineEx(b, c, U(2.2f), (Color){ 24, 22, 20, 255 });
    } else {
        RoundRect(box, U(4), (Color){ 255, 255, 255, (unsigned char)(hov ? 30 : 16) });
        DrawRectangleRoundedLinesEx(box, 0.5f, 8, U(1.2f), (Color){ 255, 255, 255, 60 });
    }
    Txt(&fReg, label, x + U(26), y, hov ? UI_TEXT : Mix(UI_SUB, UI_TEXT, 0.35f));
    return clicked;
}

// size of the camera name the game shows on View Change; saved when the drag ends
static int OverlaySlider(float x, float y, float w)
{
    const int id = 950, mx = 120;
    static int before = -1;
    Rectangle row = { x, y - U(2), w, U(34) }, tr = { x, y + U(23), w, U(4) };
    int hov = Hover(row), saved = 0;
    if (hov && IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && ui.active < 0 && ui.renaming < 0) { ui.active = id; before = overlayPx; }
    if (ui.active == id) {
        if (IsMouseButtonDown(MOUSE_BUTTON_LEFT)) {
            float t = Clampf((GetMousePosition().x - tr.x)/tr.width, 0, 1);
            overlayPx = 2*(int)roundf(t*mx/2);
        } else { ui.active = -1; saved = overlayPx != before; }
    }
    if (hov) Tip(id, row, "Camera name",
                 "How big the game shows the camera's name when you press View Change, for 2 seconds in the middle of the screen. Off hides it.");
    char val[16];
    if (overlayPx > 0) snprintf(val, sizeof val, "%d px", overlayPx); else snprintf(val, sizeof val, "off");
    int act = ui.active == id;
    Txt(&fReg, "Camera name size", x, y, (hov || act) ? UI_TEXT : Mix(UI_SUB, UI_TEXT, 0.35f));
    Txt(&fReg, val, x + w - TxtW(&fReg, val), y, UI_TEXT);
    float t = (float)overlayPx/mx;
    RoundRect(tr, U(2), (Color){ 255, 255, 255, 26 });
    RoundRect((Rectangle){ tr.x, tr.y, tr.width*t, tr.height }, U(2), act ? UI_ACCENT : Mix(UI_ACCENT, UI_SUB, 0.15f));
    Vector2 knob = { tr.x + tr.width*t, tr.y + tr.height/2 };
    DrawCircleV(knob, U(act ? 8.5f : (hov ? 7.5f : 6.5f)), (Color){ 255, 255, 255, 255 });
    DrawCircleV(knob, U(act ? 4.0f : 3.2f), UI_ACCENT);
    return saved;
}

// one row of the Templates or Profiles list
static void ProfileRow(int i, float x, float y, float w, float rh)
{
    Rectangle r = { x - U(8), y, w + U(16), rh };
    int hov = Hover(r) && ui.renaming != i;
    if (i == sel) {
        RoundRect(r, U(8), (Color){ UI_ACCENT.r, UI_ACCENT.g, UI_ACCENT.b, 34 });
        RoundRect((Rectangle){ r.x, r.y + U(8), U(3), rh - U(16) }, U(1.5f), UI_ACCENT);
    } else if (hov) RoundRect(r, U(8), (Color){ 255, 255, 255, 12 });
    if (ui.renaming == i) {
        Rectangle tb = { r.x + U(6), r.y + U(3), r.width - U(12), rh - U(6) };
        RoundRect(tb, U(6), (Color){ 0, 0, 0, 90 });
        DrawRectangleRoundedLinesEx(tb, Clampf(2*U(6)/tb.height, 0, 1), 8, U(1.2f), UI_ACCENT);
        Txt(&fReg, ui.buf, tb.x + U(10), tb.y + (tb.height - fReg.size*S)/2 - U(1), UI_TEXT);
        if ((ui.caretBlink++/30) % 2 == 0) {
            float cx = tb.x + U(10) + TxtW(&fReg, ui.buf) + U(1);
            DrawRectangle((int)cx, (int)(tb.y + U(6)), (int)fmaxf(1, U(1.5f)), (int)(tb.height - U(12)), UI_ACCENT);
        }
        if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && !CheckCollisionPointRec(GetMousePosition(), tb)) CommitRename();
    } else {
        float ty = r.y + (rh - fReg.size*S)/2 - U(1), nx = r.x + U(16) + TxtW(&fReg, prof[i].name);
        Color nameC = i == sel ? UI_TEXT : Mix(UI_SUB, UI_TEXT, 0.3f);
        if (prof[i].builtin) nameC = i == sel ? UI_TPL : Mix(UI_TPL, UI_SUB, 0.25f);
        Txt(&fReg, prof[i].name, r.x + U(16), ty, nameC);
        if (hov && prof[i].builtin)
            Tip(40 + i, r, prof[i].name, BuiltinIndex(prof[i].name) == 0
                ? "SEGA Rally 3's own chase camera, exactly as the game ships (no swing, the game's stiff spring "
                  "and framing). Press New to start your own profile from it."
                : "SEGA Rally 3's far chase camera, the same as SR3 Chase from further back (the game's far view, "
                  "x1.25 distance and x1.15 height). Press New to start your own profile from it.");
        else if (hov) {
            char body[320];
            snprintf(body, sizeof body, "Click to put the %s profile on the car, double-click to rename it.%s%s", prof[i].name,
                     ProfileProtected(i) ? " A factory profile: you can change it, but not remove it." : "",
                     ProfileDirty(&prof[i]) ? " The orange dot means it has unsaved changes." : "");
            Tip(40 + i, r, prof[i].name, body);
        }
        if (ProfileDirty(&prof[i])) { DrawCircleV((Vector2){ nx + U(8), r.y + rh/2 }, U(2.6f), UI_ACCENT); nx += U(12); }
        if (strcmp(prof[i].name, defaultName) == 0) {                   // the game's current default
            float tw = TxtW(&fSmall, "default") + U(12);
            Rectangle tag = { nx + U(8), r.y + U(6), tw, rh - U(12) };
            RoundRect(tag, U(4), (Color){ UI_GREEN.r, UI_GREEN.g, UI_GREEN.b, 40 });
            Txt(&fSmall, "default", nx + U(14), r.y + (rh - fSmall.size*S)/2 - U(1), UI_GREEN);
            PanelTip(80, tag, "Default", TextFormat("The game uses the %s profile when you start PLAY.bat without naming one. Make default moves the tag.", prof[i].name));
            nx += U(8) + tw;
        }
        // reset to factory values, shown only when there is something to reset
        int canReset = !ProfileAtFactory(&prof[i]);
        Vector2 rc = { nx + U(16), r.y + rh/2 };
        Rectangle rhit = { rc.x - U(10), rc.y - U(10), U(20), U(20) };
        int onReset = canReset && Hover(rhit);
        if (canReset && ResetIcon(300 + i, rc, U(5.5f))) {
            sel = i;
            SetStatus(FactoryValues(&prof[i], prof[i].v) ? "factory values" : "default values");
        }
        if (onReset) Tip(81, rhit, "Factory reset", TextFormat("Puts every slider of the %s profile back to its factory values (from defaults.yaml). Nothing is saved until you press Save.", prof[i].name));
        char meta[48];
        snprintf(meta, sizeof meta, "%.2f \xC2\xB7 %.0f/%.0f", prof[i].v[P_STRENGTH], prof[i].v[P_KMIN], prof[i].v[P_KMAX]);
        float mw = TxtW(&fSmall, meta), mx = r.x + r.width - U(14) - mw;
        Txt(&fSmall, meta, mx, r.y + (rh - fSmall.size*S)/2, UI_FAINT);
        PanelTip(82, (Rectangle){ mx, r.y, mw, rh }, "At a glance", "Travel follow, then the spring's stiffness while sliding / while gripping.");
        if (hov && !onReset && IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && ui.renaming < 0) {
            double now = GetTime();
            if (ui.lastClickRow == i && now - ui.lastClickT < 0.35 && !prof[i].builtin) { sel = i; StartRename(); }
            sel = i; ui.lastClickRow = i; ui.lastClickT = now;
        }
    }
}

static void DrawPanel(void)
{
    float W = (float)GetScreenWidth(), H = (float)GetScreenHeight();
    float pw = U(340), px = W - pw - U(18), py = U(18), ph = H - U(36);
    ui.panel = (Rectangle){ px, py, pw, ph };
    RoundRect(ui.panel, U(16), UI_BG);
    DrawRectangleRoundedLinesEx(ui.panel, Clampf(2*U(16)/fminf(pw, ph), 0, 1), 8, U(1), (Color){ 255, 255, 255, 14 });

    if (CheckCollisionPointRec(GetMousePosition(), ui.panel) && !IsKeyDown(KEY_LEFT_SHIFT) && !IsKeyDown(KEY_RIGHT_SHIFT))
        ui.scroll -= GetMouseWheelMove()*U(48);
    ui.scroll = Clampf(ui.scroll, 0, fmaxf(0, ui.contentH - ph));

    BeginScissorMode((int)px, (int)py, (int)pw, (int)ph);
    float x = px + U(24), w = pw - U(48), y = py + U(22) - ui.scroll, y0 = y;
    Txt(&fTitle, "Chase camera", x, y, UI_TEXT);
    PanelTip(10, (Rectangle){ x, y, TxtW(&fTitle, "Chase camera"), fTitle.size*S }, "Chase camera",
             "The camera that follows the car. Tune it here while the car drives; the same profiles set the camera in SEGA Rally 3.");
    y += fTitle.size*S + U(2);
    Txt(&fSmall, "tuned live on the car", x, y, UI_SUB);
    PanelTip(11, (Rectangle){ x, y, TxtW(&fSmall, "tuned live on the car"), fSmall.size*S }, "Live",
             "Every slider change shows up on the car straight away. Nothing is written to disk until you press Save.");
    y += U(24);

    int group = -1;
    for (int p = 0; p < NPARAM; p++) {
        if (PD[p].group != group) {
            group = PD[p].group;
            if (p) y += U(6);
            TxtSp(&fSmall, GROUPS[group], x, y, U(1.4f), UI_FAINT);
            PanelTip(20 + group, (Rectangle){ x, y, TxtWSp(&fSmall, GROUPS[group], U(1.4f)), fSmall.size*S }, GROUPS_TIP[group][0], GROUPS_TIP[group][1]);
            y += U(20);
        }
        Slider(100 + p, x, y, w, p);
        y += U(36);
    }

    y += U(4);
    DrawRectangle((int)x, (int)y, (int)w, (int)fmaxf(1, U(1)), (Color){ 255, 255, 255, 18 });
    y += U(16);
    // the templates: SEGA Rally 3's own cameras, to copy from
    float rh = U(28);
    TxtSp(&fSmall, "TEMPLATES", x, y, U(1.4f), UI_FAINT);
    PanelTip(29, (Rectangle){ x, y, TxtWSp(&fSmall, "TEMPLATES", U(1.4f)), fSmall.size*S }, "Templates",
             "SEGA Rally 3's own cameras, exactly as the game ships. Pick one and press New to start your own profile from it.");
    y += U(20);
    for (int i = 0; i < nprof; i++) if (prof[i].builtin) { ProfileRow(i, x, y, w, rh); y += rh + U(2); }
    y += U(14);
    // header: status of the selected profile; below it Reload / Save / Make default
    int selDirty = ProfileDirty(&prof[sel]);
    float gap4 = U(8), bwS = (w - 2*gap4)*0.28f, bh4 = U(30), hy = y + U(20);
    Rectangle reloadR = { x, hy, bwS, bh4 }, saveR = { x + bwS + gap4, hy, bwS, bh4 };
    Rectangle applyR = { x + 2*(bwS + gap4), hy, w - 2*(bwS + gap4), bh4 };
    TxtSp(&fSmall, "PROFILES", x, y, U(1.4f), UI_FAINT);
    const char *st = statusT > 0 ? status : selDirty ? "unsaved" : "saved";
    Color stc = statusT > 0 ? UI_SUB : selDirty ? UI_ACCENT : UI_FAINT;
    float hx = x + TxtWSp(&fSmall, "PROFILES", U(1.4f)) + U(22);
    DrawCircleV((Vector2){ hx - U(8), y + fSmall.size*S*0.55f }, U(2.2f), stc);
    Txt(&fSmall, st, hx, y, stc);
    PanelTip(30, (Rectangle){ x, y, TxtWSp(&fSmall, "PROFILES", U(1.4f)), fSmall.size*S }, "Profiles",
             "Saved camera setups. They live in profiles.yaml, which the game reads too, so what you save here is what you get in SEGA Rally 3.");
    PanelTip(31, (Rectangle){ hx - U(12), y, TxtW(&fSmall, st) + U(12), fSmall.size*S }, "Status",
             "Whether the selected profile has changes you haven't saved yet (orange), or what just happened.");
    if (Button(7, reloadR, "Reload", BTN_GHOST, selDirty)) {                // back to the last save
        memcpy(prof[sel].v, prof[sel].base, sizeof prof[sel].v);
        SetStatus("last saved values");
    }
    PanelTip(32, reloadR, "Reload", "Throws away the slider changes you haven't saved and goes back to the last saved values.");
    if (Button(4, saveR, "Save", selDirty ? BTN_ACCENT : BTN_GHOST, selDirty)) {
        CommitRename();
        SetStatus(SaveSelected() ? "saved" : "could not write the file");
    }
    PanelTip(33, saveR, "Save", TextFormat("Writes the %s profile's sliders to profiles.yaml, so the game and CamLab both use them from now on.", prof[sel].name));
    if (Button(5, applyR, "Make default", BTN_GREEN, !prof[sel].builtin)) {   // save + make it the game's default
        CommitRename();
        char keep[32]; snprintf(keep, sizeof keep, "%s", defaultName);
        snprintf(defaultName, sizeof defaultName, "%s", prof[sel].name);
        if (prof[sel].builtin ? WriteProfiles() : SaveSelected()) SetStatus("game default set");
        else { snprintf(defaultName, sizeof defaultName, "%s", keep); SetStatus("could not write the file"); }
    }
    PanelTip(34, applyR, "Make default", prof[sel].builtin ? "Templates can't be the default. Press New to make a profile from this one first." : TextFormat("Saves the %s profile and makes it the one the game uses when you start PLAY.bat without a profile name. It gets the green \"default\" tag.", prof[sel].name));
    y = hy + bh4 + U(12);

    for (int i = 0; i < nprof; i++) if (!prof[i].builtin) { ProfileRow(i, x, y, w, rh); y += rh + U(2); }

    y += U(10);
    float gap = U(8), bw3 = (w - 2*gap)/3, bh = U(32);
    Rectangle newR = { x, y, bw3, bh }, renR = { x + (bw3 + gap), y, bw3, bh }, rmR = { x + 2*(bw3 + gap), y, bw3, bh };
    int base = prof[sel].builtin;
    if (Button(1, newR, "New", BTN_GHOST, nprof < MAXPROF)) AddProfile();
    PanelTip(35, newR, "New", base ? TextFormat("Makes an editable copy of %s to use as a template, and lets you name it. Its reset icon returns it to %s.", prof[sel].name, prof[sel].name)
                                   : "Makes a copy of the selected profile, sliders as they are now, and lets you name it.");
    if (Button(2, renR, "Rename", BTN_GHOST, !base)) StartRename();
    PanelTip(36, renR, "Rename", base ? "The SR3 cameras are built in, so they can't be renamed."
                                      : "Gives the selected profile a new name. Double-clicking a profile does the same.");
    int keep = ProfileProtected(sel);
    if (Button(6, rmR, "Remove", BTN_GHOST, nprof > 1 && !keep)) RemoveProfile();
    PanelTip(37, rmR, "Remove", base ? "The SR3 cameras are built in, so they can't be removed."
                              : keep ? "This is a factory profile, so it can't be removed. You can still change it, save it or rename it."
                                     : "Deletes the selected profile from profiles.yaml.");
    y += bh + gap;
    Rectangle launchR = { x, y, w, bh };
    int game = GameAvailable();
    if (Button(8, launchR, "Launch", BTN_BLUE, game && !base)) {                  // play SR3 with the sliders as they are
        CommitRename();
        SetStatus(LaunchGame(&prof[sel]) ? "starting SEGA Rally 3..." : "could not start the game");
    }
    PanelTip(38, launchR, "Launch", !game ? "Needs PLAY.bat and patch.ps1 next to camlab.exe."
                                  : base ? "Templates can't be launched. They are the game's own cameras: in a race, View Change reaches them anyway."
                                  : TextFormat("Starts SEGA Rally 3 with the %s profile exactly as the sliders are now, unsaved changes included. Nothing gets saved, so experiment away.", prof[sel].name));
    y += bh + U(18);
    TxtSp(&fSmall, "IN-GAME", x, y, U(1.4f), UI_FAINT);
    PanelTip(39, (Rectangle){ x, y, TxtWSp(&fSmall, "IN-GAME", U(1.4f)), fSmall.size*S }, "In-game",
             "In a race, the game's View Change button cycles through every camera: Baseline, each profile, then the in-car views.");
    y += U(20);
    if (OverlaySlider(x, y, w)) SetStatus(WriteProfiles() ? "saved" : "could not write the file");
    y += U(36) + U(6);
    if (Checkbox(960, x, y, w, "Show debug cameras", showHidden, "Show debug cameras",
                 "Adds the cameras SEGA Rally 3 has but hides in a race to View Change, after your profiles: the far "
                 "chase, cockpit (also from the driver's seat), wheel, car rotate and free cams (orange \"Debug:\" "
                 "names). Off gives just the game's three cameras and your profiles.")) {
        showHidden = !showHidden;
        SetStatus(WriteProfiles() ? "saved" : "could not write the file");
    }
    y += U(20) + U(22);                                                 // the track, then the same margin as the top
    ui.contentH = y - y0 + U(22) + U(4);                                // including the top padding
    EndScissorMode();

    // scrollbar, only when the panel does not fit: drag the thumb or click the track
    if (ui.contentH > ph + 1) {
        float maxScroll = ui.contentH - ph;
        Rectangle track = { px + pw - U(10), py + U(14), U(4), ph - U(28) };
        float thumbH = fmaxf(U(28), track.height*ph/ui.contentH);
        float thumbY = track.y + (track.height - thumbH)*(ui.scroll/maxScroll);
        Rectangle hit = { track.x - U(6), track.y, track.width + U(10), track.height };
        int hov = CheckCollisionPointRec(GetMousePosition(), hit), drag = ui.active == 900;
        if (hov && IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && ui.active < 0) {
            float my = GetMousePosition().y;
            if (my < thumbY || my > thumbY + thumbH)                        // track click: centre the thumb there
                ui.scroll = Clampf((my - thumbH/2 - track.y)/(track.height - thumbH)*maxScroll, 0, maxScroll);
            ui.active = 900;
            ui.dragGrab = GetMousePosition().y - (track.y + (track.height - thumbH)*(ui.scroll/maxScroll));
        }
        if (drag) {
            if (IsMouseButtonDown(MOUSE_BUTTON_LEFT))
                ui.scroll = Clampf((GetMousePosition().y - ui.dragGrab - track.y)/(track.height - thumbH)*maxScroll, 0, maxScroll);
            else ui.active = -1;
        }
        thumbY = track.y + (track.height - thumbH)*(ui.scroll/maxScroll);
        RoundRect(track, U(2), (Color){ 255, 255, 255, (unsigned char)(hov || drag ? 22 : 10) });
        RoundRect((Rectangle){ track.x, thumbY, track.width, thumbH }, U(2),
                  drag ? UI_ACCENT : (Color){ 255, 255, 255, (unsigned char)(hov ? 150 : 90) });
    }
}

// raylib (5.5, GLFW) turns a DPI change of the window (the display mode switching while a
// game runs fullscreen, or moving to another monitor) into a scale on all 2D drawing, even
// without FLAG_WINDOW_HIGHDPI, while the mouse stays unscaled: the UI drifts away from the
// clicks. CamLab scales its UI itself, so drop that scale wherever raylib applies it.
static void NoScreenScale(void) { rlLoadIdentity(); }

// raylib's TakeScreenshot() scales the read-back by the DPI factor, which is wrong for a
// DPI-aware window without FLAG_WINDOW_HIGHDPI, so read the real framebuffer ourselves
static int SaveShot(const char *path)
{
    int w = GetRenderWidth(), h = GetRenderHeight();
    unsigned char *px = rlReadScreenPixels(w, h);
    if (!px) return 0;
    Image img = { px, w, h, 1, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8 };
    int ok = ExportImage(img, path);
    RL_FREE(px);
    return ok;
}

static float Pill(float x, float y, const char *label, Color bg, Color fg)
{
    float tw = TxtW(&fSmall, label), h = U(22), w = tw + U(18);
    RoundRect((Rectangle){ x, y, w, h }, h/2, bg);
    TxtSp(&fSmall, label, x + U(9), y + (h - fSmall.size*S)/2 - U(1), 0, fg);
    return w;
}

static void DrawHUD(const Car *c, const Cam *cm, int autopilot, int paused)
{
    char sp[16];
    const char *unit = useMph ? "mph" : "km/h";
    snprintf(sp, sizeof sp, "%d", (int)roundf(CarSpeed(c)*(useMph ? 2.23694f : 3.6f)));
    char line[96];
    snprintf(line, sizeof line, "camera %+.0f\xC2\xB0   slip %+.0f\xC2\xB0", cm->placed*RAD2DEG, WrapAngle(CarTravel(c) - c->yaw)*RAD2DEG);
    float x = U(18), y = U(18), pad = U(20);
    float pillsW = TxtW(&fSmall, "AUTOPILOT") + TxtW(&fSmall, "GRAVEL") + TxtW(&fSmall, "DRIFT") + TxtW(&fSmall, "AIR") + 4*U(18) + 3*U(6);
    float cardW = fmaxf(fmaxf(TxtW(&fBig, "000") + U(8) + TxtW(&fSemi, "km/h"), TxtW(&fSmall, "camera +00\xC2\xB0   slip +00\xC2\xB0")), pillsW) + 2*pad;
    float cardH = U(10) + fBig.size*S + U(4) + U(22) + U(12) + fSmall.size*S + U(16);
    RoundRect((Rectangle){ x, y, cardW, cardH }, U(16), UI_BG);
    float cx = x + pad, cy = y + U(10);
    Txt(&fBig, sp, cx, cy, UI_TEXT);
    Txt(&fSemi, unit, cx + TxtW(&fBig, sp) + U(8), cy + fBig.size*S - fSemi.size*S - U(9), UI_SUB);
    Rectangle spR = { cx, cy, TxtW(&fBig, sp) + U(8) + TxtW(&fSemi, unit), fBig.size*S };
    HudTip(60, spR, "Speed", useMph ? "How fast the car is going. On a real SEGA Rally 3 stage a fast lap averages about 112 mph. "
                                      "Click to show km/h."
                                    : "How fast the car is going. On a real SEGA Rally 3 stage a fast lap averages about 180 km/h. "
                                      "Click to show mph.");
    if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT) && CheckCollisionPointRec(GetMousePosition(), spR)
        && !CheckCollisionPointRec(GetMousePosition(), ui.panel) && ui.renaming < 0) {
        useMph = !useMph;
        SetStatus(WriteProfiles() ? "saved" : "could not write the file");
    }
    cy += fBig.size*S + U(4);
    float px = cx, pw;
    pw = Pill(px, cy, autopilot ? "AUTOPILOT" : "MANUAL", (Color){ 255, 255, 255, 22 }, UI_SUB);
    HudTip(61, (Rectangle){ px, cy, pw, U(22) }, autopilot ? "Autopilot" : "Manual",
           autopilot ? "The computer is driving, drifting like a player would. Press M to take the wheel."
                     : "You're driving: W/S (or the arrows) for throttle and brake, A/D to steer, Space for the handbrake. Press M to hand back to the autopilot.");
    px += pw + U(6);
    if (c->drift) {
        pw = Pill(px, cy, "DRIFT", UI_ACCENT, (Color){ 30, 22, 18, 255 });
        HudTip(62, (Rectangle){ px, cy, pw, U(22) }, "Drift", "The car is sliding sideways. Watch how the camera swings out to show it.");
        px += pw + U(6);
    }
    pw = Pill(px, cy, SURF_NAME[c->surf], (Color){ 255, 255, 255, 12 }, UI_SUB);
    HudTip(63, (Rectangle){ px, cy, pw, U(22) }, "Surface",
           "What the road is made of here. Tarmac grips best; on gravel, mud and snow the car slides more.");
    px += pw + U(6);
    if (!c->ground && c->airT > 0.08f) {
        pw = Pill(px, cy, "AIR", (Color){ 236, 238, 244, 255 }, (Color){ 30, 32, 40, 255 });
        HudTip(64, (Rectangle){ px, cy, pw, U(22) }, "Air", "The car jumped off a crest and is flying. Its shadow shows how high.");
    }
    cy += U(22) + U(12);
    Txt(&fSmall, line, cx, cy, UI_SUB);
    HudTip(65, (Rectangle){ cx, cy, TxtW(&fSmall, line), fSmall.size*S }, "Camera and slip",
           "Camera: how far the camera has swung round from straight behind the car. Slip: the angle between where the car points and where it's actually going.");

    // key hints
    const char *keys[][2] = { { "Tab", "panel" }, { "M", "autopilot" }, { "R", "respawn" }, { "P", "pause" }, { "F12", "screenshot" },
                              { "Right-click", "reset slider" }, { "WASD", "drive" }, { "Space", "handbrake" } };
    static const char *keyTip[] = {
        "Shows or hides the camera panel, for a clean view of the car.",
        "Switches between the autopilot and driving yourself.",
        "Puts the car back on the road, facing the right way.",
        "Freezes everything. Handy to look at the camera angle mid-drift.",
        "Saves a picture of the window next to camlab.exe.",
        "Right-click a slider to put it back to its last saved value.",
        "W or Up: throttle, S or Down: brake, A and D (or the arrows): steer.",
        "Pulls the handbrake to kick the car into a slide.",
    };
    int nk = autopilot ? 6 : 8;
    float hx = U(18), hy = (float)GetScreenHeight() - U(18) - U(38), hw = U(14);
    for (int i = 0; i < nk; i++) hw += TxtW(&fSmall, keys[i][0]) + U(12) + U(6) + TxtW(&fSmall, keys[i][1]) + U(16);
    RoundRect((Rectangle){ hx, hy, hw - U(2), U(38) }, U(12), UI_BG);
    hx += U(14);
    for (int i = 0; i < nk; i++) {
        float kw = TxtW(&fSmall, keys[i][0]) + U(12);
        HudTip(66 + i, (Rectangle){ hx - U(4), hy, kw + U(6) + TxtW(&fSmall, keys[i][1]) + U(12), U(38) }, keys[i][0], keyTip[i]);
        RoundRect((Rectangle){ hx, hy + U(8), kw, U(22) }, U(5), (Color){ 255, 255, 255, 26 });
        Txt(&fSmall, keys[i][0], hx + U(6), hy + U(8) + (U(22) - fSmall.size*S)/2 - U(1), UI_TEXT);
        hx += kw + U(6);
        Txt(&fSmall, keys[i][1], hx, hy + U(8) + (U(22) - fSmall.size*S)/2 - U(1), UI_SUB);
        hx += TxtW(&fSmall, keys[i][1]) + U(16);
    }
    if (paused) {
        const char *m = "PAUSED";
        float mw = TxtW(&fTitle, m) + U(40);
        Rectangle r = { (GetScreenWidth() - mw)/2, (float)GetScreenHeight()*0.42f, mw, U(46) };
        RoundRect(r, U(12), UI_BG);
        TxtSp(&fTitle, m, r.x + U(20), r.y + (r.height - fTitle.size*S)/2 - U(1), 0, UI_TEXT);
        HudTip(90, r, "Paused", "Everything is frozen. Press P to carry on.");
    }
}

// ============================================================== main
// ---- application icon ---------------------------------------------------------------------
// Drawn procedurally so the project stays a single source file: build.bat runs
// "camlab.exe --write-icon camlab.ico", compiles it into a GLFW_ICON resource (which GLFW
// picks up for the window and taskbar) and relinks. A tiny chase view: sunset sky, ground,
// road to the horizon and the orange car, on a rounded tile.
typedef struct { float r, g, b, a; } RGBAf;

static RGBAf Over(RGBAf dst, Color c, float cov)
{
    float a = cov*c.a/255.0f;
    return (RGBAf){ dst.r + (c.r - dst.r)*a, dst.g + (c.g - dst.g)*a, dst.b + (c.b - dst.b)*a, dst.a + (1 - dst.a)*a };
}

// colour of the icon at (x, y) in unit coordinates, y down; alpha 0 outside the tile
static RGBAf IconSample(float x, float y)
{
    RGBAf px = { 0, 0, 0, 0 };
    // rounded tile
    const float in = 0.04f, rad = 0.20f;
    float cx = Clampf(x, in + rad, 1 - in - rad), cy = Clampf(y, in + rad, 1 - in - rad);
    if ((x - cx)*(x - cx) + (y - cy)*(y - cy) > rad*rad) return px;
    const float hz = 0.50f;
    if (y < hz) {                                                   // sky: zenith blue to warm horizon
        float t = Smooth01((y - in)/(hz - in));
        Color sky = { (unsigned char)Lerpf(84, 236, t), (unsigned char)Lerpf(118, 214, t), (unsigned char)Lerpf(184, 200, t), 255 };
        px = Over(px, sky, 1);
    } else px = Over(px, (Color){ 104, 136, 92, 255 }, 1);          // ground
    // road: a trapezoid from the bottom edge to a point on the horizon, gently curving right
    float t = (y - hz)/(1 - hz);
    if (t > 0) {
        float centre = 0.5f + 0.10f*(1 - t)*(1 - t) - 0.02f, half = 0.03f + 0.40f*t;
        if (fabsf(x - centre) < half) px = Over(px, (Color){ 78, 82, 94, 255 }, 1);
        if (fabsf(x - centre) < half && fabsf(x - centre) > half - 0.035f*t - 0.004f)
            px = Over(px, (Color){ 214, 90, 74, 255 }, 1);          // curbs
        if (fabsf(x - centre) < 0.004f + 0.012f*t && fmodf(t*6.0f, 1.0f) < 0.5f)
            px = Over(px, (Color){ 240, 236, 222, 255 }, 1);        // centre line
    }
    // the hatchback from behind: shadow, tyres, body, glasshouse with its rear window, spoiler,
    // tail lights
    // drawn in its own coordinates (u, v), scaled up around the rear wheels' contact line
    const float k = 1.3f;
    float u = 0.5f + (x - 0.5f)/k, v = 0.86f + (y - 0.86f)/k, dx = fabsf(u - 0.5f);
    const Color tyreC = { 38, 40, 46, 255 }, dark = { 34, 36, 42, 255 };
    if (dx/0.23f + fabsf(v - 0.845f)/0.035f < 1.4f) px = Over(px, (Color){ 16, 18, 28, 120 }, 1);
    if (dx > 0.12f && dx < 0.19f && v > 0.74f && v < 0.855f) px = Over(px, tyreC, 1);
    if (dx < 0.18f && v > 0.62f && v < 0.79f) px = Over(px, (Color){ 226, 112, 58, 255 }, 1);
    if (dx < 0.18f && v > 0.765f && v < 0.79f) px = Over(px, dark, 1);                       // bumper
    float cabT = 0.48f, cabB = 0.62f, s = Clampf((v - cabT)/(cabB - cabT), 0, 1);
    if (v > cabT && v <= cabB && dx < 0.125f + 0.045f*s) {
        px = Over(px, (Color){ 240, 128, 70, 255 }, 1);                                         // pillars and roof
        if (v > cabT + 0.035f && v < cabB - 0.012f && dx < 0.10f + 0.045f*s) px = Over(px, (Color){ 58, 66, 86, 255 }, 1);
    }
    if (dx < 0.155f && v > 0.455f && v < 0.48f) px = Over(px, dark, 1);                       // spoiler
    if (dx > 0.105f && dx < 0.165f && v > 0.655f && v < 0.695f) px = Over(px, (Color){ 214, 44, 38, 255 }, 1);
    return px;
}

// writes a multi-size .ico (32-bit BMP entries, 8x8 supersampled); returns 1 on success
static int WriteIcon(const char *path)
{
    static const int SIZES[] = { 16, 24, 32, 48, 64, 128, 256 };
    enum { N = 7, SS = 8 };
    FILE *f = fopen(path, "wb");
    if (!f) return 0;
    unsigned char hdr[6] = { 0, 0, 1, 0, N, 0 };
    fwrite(hdr, 1, 6, f);
    unsigned offset = 6 + 16*N;
    for (int k = 0; k < N; k++) {                                   // directory
        int s = SIZES[k];
        unsigned bytes = 40 + s*s*4 + ((s + 31)/32)*4*s;
        unsigned char e[16] = { (unsigned char)(s == 256 ? 0 : s), (unsigned char)(s == 256 ? 0 : s), 0, 0, 1, 0, 32, 0 };
        memcpy(e + 8, &bytes, 4); memcpy(e + 12, &offset, 4);
        fwrite(e, 1, 16, f);
        offset += bytes;
    }
    for (int k = 0; k < N; k++) {                                   // images: BITMAPINFOHEADER + BGRA (bottom-up) + AND mask
        int s = SIZES[k];
        unsigned char bih[40] = { 0 };
        unsigned v32 = 40; memcpy(bih, &v32, 4);
        int w = s, h = s*2; memcpy(bih + 4, &w, 4); memcpy(bih + 8, &h, 4);
        bih[12] = 1; bih[14] = 32;
        fwrite(bih, 1, 40, f);
        for (int row = s - 1; row >= 0; row--)
            for (int col = 0; col < s; col++) {
                RGBAf acc = { 0, 0, 0, 0 };
                for (int sy = 0; sy < SS; sy++)
                    for (int sx = 0; sx < SS; sx++) {
                        RGBAf c = IconSample((col + (sx + 0.5f)/SS)/s, (row + (sy + 0.5f)/SS)/s);
                        acc.r += c.r*c.a; acc.g += c.g*c.a; acc.b += c.b*c.a; acc.a += c.a;
                    }
                float a = acc.a/(SS*SS);
                unsigned char px[4] = { 0, 0, 0, 0 };
                if (acc.a > 0) {                                     // premultiplied average -> straight alpha
                    px[0] = (unsigned char)Clampf(acc.b/acc.a, 0, 255); px[1] = (unsigned char)Clampf(acc.g/acc.a, 0, 255);
                    px[2] = (unsigned char)Clampf(acc.r/acc.a, 0, 255); px[3] = (unsigned char)Clampf(a*255 + 0.5f, 0, 255);
                }
                fwrite(px, 1, 4, f);
            }
        int maskRow = ((s + 31)/32)*4;
        unsigned char zero[32] = { 0 };
        for (int row = 0; row < s; row++) fwrite(zero, 1, (size_t)maskRow, f);
    }
    fclose(f);
    return 1;
}

// the same .ico from a picture instead (the build uses res/icon.png when there is one): cropped to a
// square and scaled to each size, stored as 32-bit bitmaps like the drawn icon
static int WriteIconFromPng(const char *path, const char *src)
{
    static const int SIZES[] = { 16, 24, 32, 48, 64, 128, 256 };
    enum { N = 7 };
    Image img = LoadImage(src);
    if (!img.data) return 0;
    int side = img.width < img.height ? img.width : img.height;
    ImageCrop(&img, (Rectangle){ (float)((img.width - side)/2), (float)((img.height - side)/2), (float)side, (float)side });
    ImageFormat(&img, PIXELFORMAT_UNCOMPRESSED_R8G8B8A8);
    FILE *f = fopen(path, "wb");
    if (!f) { UnloadImage(img); return 0; }
    unsigned char hdr[6] = { 0, 0, 1, 0, N, 0 };
    fwrite(hdr, 1, 6, f);
    unsigned offset = 6 + 16*N;
    for (int k = 0; k < N; k++) {                                   // directory
        int sz = SIZES[k];
        unsigned bytes = 40 + sz*sz*4 + ((sz + 31)/32)*4*sz;
        unsigned char e[16] = { (unsigned char)(sz == 256 ? 0 : sz), (unsigned char)(sz == 256 ? 0 : sz), 0, 0, 1, 0, 32, 0 };
        memcpy(e + 8, &bytes, 4); memcpy(e + 12, &offset, 4);
        fwrite(e, 1, 16, f);
        offset += bytes;
    }
    for (int k = 0; k < N; k++) {                                   // images: BITMAPINFOHEADER + BGRA (bottom-up) + AND mask
        int sz = SIZES[k];
        Image im = ImageCopy(img);
        while (im.width/2 >= sz*2) ImageResize(&im, im.width/2, im.height/2);   // halve first: smoother small sizes
        ImageResize(&im, sz, sz);
        const unsigned char *px = im.data;
        unsigned char bih[40] = { 0 };
        unsigned v32 = 40; memcpy(bih, &v32, 4);
        int w = sz, h = sz*2; memcpy(bih + 4, &w, 4); memcpy(bih + 8, &h, 4);
        bih[12] = 1; bih[14] = 32;
        fwrite(bih, 1, 40, f);
        for (int row = sz - 1; row >= 0; row--)
            for (int col = 0; col < sz; col++) {
                const unsigned char *c = px + (row*sz + col)*4;
                unsigned char bgra[4] = { c[2], c[1], c[0], c[3] };
                fwrite(bgra, 1, 4, f);
            }
        unsigned char zero[32] = { 0 };
        for (int row = 0; row < sz; row++) fwrite(zero, 1, (size_t)(((sz + 31)/32)*4), f);
        UnloadImage(im);
    }
    fclose(f);
    UnloadImage(img);
    return 1;
}

// camlab.exe --make-defaults: overwrite defaults.yaml (the factory values) with the current
// profiles from profiles.yaml, and point every profile at its own entry, so Reset returns it
// to exactly what it is now.
static int MakeDefaults(void)
{
    if (!LoadProfiles()) return 0;
    FILE *f = fopen(defaultsPath, "w");
    if (!f) return 0;
    fprintf(f, "# CamLab's factory profiles - DO NOT EDIT THIS FILE BY HAND.\n"
               "# Reset returns a profile to its entry here. It is regenerated from profiles.yaml\n"
               "# by \"camlab.exe --make-defaults\", which overwrites any hand edits.\n\n"
               "profiles:\n");
    for (int n = 0; n < nprof; n++) {
        if (prof[n].builtin) continue;
        WriteProfileYaml(f, prof[n].name, prof[n].base, NULL, NULL);
        snprintf(prof[n].preset, sizeof prof[n].preset, "%s", prof[n].name);
    }
    fclose(f);
    return WriteProfiles();
}

int main(int argc, char **argv)
{
    SetTraceLogLevel(LOG_WARNING);
    int shots = 0, makeDefaults = 0; unsigned seed = (unsigned)time(NULL);
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--shots") == 0) shots = 1;                 // dev: capture 5 frames and quit
        else if (strcmp(argv[i], "--make-defaults") == 0) makeDefaults = 1;
        else if (strcmp(argv[i], "--write-icon") == 0 && i + 1 < argc)   // used by build.bat: drawn, or from a picture
            return (i + 2 < argc ? WriteIconFromPng(argv[i + 1], argv[i + 2]) : WriteIcon(argv[i + 1])) ? 0 : 1;
        else if (strcmp(argv[i], "--seed") == 0 && i + 1 < argc) seed = (unsigned)strtoul(argv[++i], NULL, 10);
    }

    snprintf(profPath, sizeof profPath, "%sprofiles.yaml", GetApplicationDirectory());
    // profiles.yaml is shared with the game's patch.ps1; defaults.yaml holds the factory values
    snprintf(defaultsPath, sizeof defaultsPath, "%sdefaults.yaml", GetApplicationDirectory());
    if (makeDefaults) { LoadFactory(); return MakeDefaults() ? 0 : 1; }   // no window

    SetConfigFlags(FLAG_MSAA_4X_HINT | FLAG_VSYNC_HINT | FLAG_WINDOW_RESIZABLE);
    InitWindow(1280, 720, "CamLab \xE2\x80\x94 SEGA Rally 3 chase camera");
    SetExitKey(KEY_NULL);
    rlSetClipPlanes(CLIP_NEAR, CLIP_FAR);
    S = fmaxf(1.0f, GetWindowScaleDPI().x);
    {
        int mon = GetCurrentMonitor(), mw = GetMonitorWidth(mon), mh = GetMonitorHeight(mon);
        float want = S;
        if (1600*want > mw*0.92f) want = mw*0.92f/1600;
        if (900*want > mh*0.88f) want = fminf(want, mh*0.88f/900);
        int ww = (int)(1600*want), wh = (int)(900*want);
        SetWindowSize(ww, wh);
        SetWindowPosition((mw - ww)/2, (mh - wh)/2);
        SetWindowMinSize((int)(800*want), (int)(480*want));   // the panel scrolls when it does not fit
        if (want < S) S = fmaxf(1.0f, want);
    }
    for (int c = 32; c < 127; c++) cps[ncps++] = c;
    cps[ncps++] = 0xB0; cps[ncps++] = 0xB7; cps[ncps++] = 0x2014; cps[ncps++] = 0x2022;
    LoadFonts();

    LoadFactory();
    DefaultProfiles();
    LoadProfiles();
    SelectDefault();

    LIGHT = Norm(V3(0.45f, 0.58f, 0.68f));
    TrackInit(seed);
    Car car; CarRespawn(&car, 20);
    Cam cam = { 0 };
    int autopilot = 1, paused = 0, showPanel = 1;
    float acc = 0, shotT = 0; int shotN = 0;
    const float STEP = 1.0f/120.0f;

    while (!WindowShouldClose()) {
        float dt = fminf(GetFrameTime(), 0.05f);
        if (statusT > 0) statusT -= dt;

        if (ui.renaming >= 0) RenameInput();
        else {
            if (IsKeyPressed(KEY_TAB)) showPanel = !showPanel;
            if (IsKeyPressed(KEY_M)) autopilot = !autopilot;
            if (IsKeyPressed(KEY_P)) paused = !paused;
            if (IsKeyPressed(KEY_R)) { CarRespawn(&car, car.idx + 4); cam.init = 0; }
            if (IsKeyPressed(KEY_F12)) {
                char name[600]; snprintf(name, sizeof name, "%scamlab_%ld.png", GetApplicationDirectory(), (long)time(NULL));
                SetStatus(SaveShot(name) ? "screenshot saved next to the .exe" : "screenshot failed");
            }
        }

        while (trkHead < car.idx + 800) GenOne();
        if (!paused) {
            if (autopilot) CarAutopilot(&car);
            else if (ui.renaming < 0) CarManual(&car);
            else { car.throttle = 0; car.steer = 0; }
            acc += dt;
            while (acc >= STEP) {
                CarStep(&car, STEP);
                CamUpdate(&cam, &car, prof[sel].v, STEP);
                acc -= STEP;
            }
            if (fabsf(car.lat) > 28 || car.pos.y < -5) { CarRespawn(&car, car.idx + 4); cam.init = 0; }
            if (autopilot && CarSpeed(&car) < 1.0f) { car.stuckT += dt; if (car.stuckT > 2.5f) { CarRespawn(&car, car.idx + 4); cam.init = 0; } }
            else car.stuckT = 0;
        }
        if (!cam.init) CamUpdate(&cam, &car, prof[sel].v, 0);

        gEye = cam.eye;
        gOrg = V3(floorf(cam.eye.x/1024.0f)*1024.0f, 0, floorf(cam.eye.z/1024.0f)*1024.0f);   // render origin
        Camera3D c3 = { 0 };
        c3.position = Sub(cam.eye, gOrg); c3.target = Sub(cam.look, gOrg); c3.up = V3(0, 1, 0);
        c3.fovy = prof[sel].v[P_FOV]; c3.projection = CAMERA_PERSPECTIVE;

        BeginDrawing();
        NoScreenScale();
        ClearBackground(C_FOG);
        BeginMode3D(c3);
        rlDisableBackfaceCulling();
        DrawSky();
        rlBegin(RL_TRIANGLES); triCount = 0;
        DrawMountains();
        DrawGround();
        DrawTrack(car.idx);
        DrawRoadMarkings(car.idx);              // same vertices as their road strip: LEQUAL seats them
        DrawCar(&car);
        OverlayBegin(DEPTH_TIER_SHADOW, 0);     // on the road's planes, above it by the offset tier
        DrawShadow(&car);
        OverlayEnd();
        rlEnd();
        rlDrawRenderBatchActive();
        rlEnableBackfaceCulling();
        EndMode3D();
        NoScreenScale();

        TipsBegin();
        if (!showPanel) ui.panel = (Rectangle){ 0 };
        DrawHUD(&car, &cam, autopilot, paused);
        if (showPanel) DrawPanel();
        DrawTooltip();
        EndDrawing();
        // once the panel has been laid out, make the window tall enough to show all of it. On
        // a small screen (1080p) the UI first shrinks a little (to 85% at most) so it fits; past
        // that the panel scrolls.
        static int fitPass = 0;
        if (fitPass < 2 && showPanel && ui.contentH > 0) {
            int mon = GetCurrentMonitor(), mh = GetMonitorHeight(mon), mw = GetMonitorWidth(mon);
            int need = (int)ceilf(ui.contentH + U(36));
            int most = (int)(mh*0.92f - 32*GetWindowScaleDPI().y);   // room for the title bar and taskbar
            float smaller = fmaxf(0.85f, S*(float)most/need);
            if (fitPass == 0 && need > most && smaller < S - 0.01f) { S = smaller; LoadFonts(); fitPass = 1; }   // lay out again first
            else {
                fitPass = 2;
                int h = need < most ? need : most;
                if (h > GetScreenHeight()) {
                    SetWindowSize(GetScreenWidth(), h);
                    SetWindowPosition((mw - GetScreenWidth())/2, (mh - h)/2);
                }
            }
        }

        if (shots) {
            shotT += dt;
            if (shotT > 3.5f) {
                shotT = 0;
                char name[32]; snprintf(name, sizeof name, "shot_%d.png", shotN);
                SaveShot(name);
                if (++shotN >= 5) break;
            }
        }
    }
    CloseWindow();
    return 0;
}

#else
// ============================================================== headless self-test (not shipped)
int main(int argc, char **argv)
{
    unsigned seed = argc > 1 ? (unsigned)strtoul(argv[1], NULL, 10) : 7;
    TrackInit(seed);
    Car car; CarRespawn(&car, 20);
    Cam cam = { 0 };
    float p[NPARAM]; for (int i = 0; i < NPARAM; i++) p[i] = PD[i].def;
    const float STEP = 1.0f/120.0f;
    double t = 0, spdSum = 0, offT = 0, driftT = 0, maxAir = 0, maxLat = 0, maxCam = 0, maxOff = 0;
    int drifts = 0, jumps = 0, resets = 0, wasDrift = 0, wasGround = 1; float maxSpd = 0;
    double slipSum = 0, camWide = 0;
    long startIdx = car.idx;
    while (t < 600) {
        while (trkHead < car.idx + 800) GenOne();
        CarAutopilot(&car);
        for (int s = 0; s < 2; s++) { CarStep(&car, STEP); CamUpdate(&cam, &car, p, STEP); }
        t += 2*STEP;
        float spd = CarSpeed(&car);
        spdSum += spd*2*STEP; if (spd > maxSpd) maxSpd = spd;
        if (fabsf(car.lat) > ROAD_HW + CURB_W) offT += 2*STEP;
        if (car.drift) { driftT += 2*STEP; slipSum += fabsf(WrapAngle(CarTravel(&car) - car.yaw))*2*STEP; }
        if (fabsf(cam.placed) > 15*DEG2RAD) camWide += 2*STEP;
        if (car.drift && !wasDrift) drifts++;
        if (!car.ground && wasGround) jumps++;
        if (!car.ground && car.airT > maxAir) maxAir = car.airT;
        wasDrift = car.drift; wasGround = car.ground;
        if (fabsf(car.lat) > maxLat) maxLat = fabsf(car.lat);
        if (fabsf(cam.placed) > maxCam) maxCam = fabsf(cam.placed);
        if (fabsf(cam.offset) > maxOff) maxOff = fabsf(cam.offset);
        if (fabsf(car.lat) > 28 || car.pos.y < -5 || isnan(car.pos.x)) { resets++; CarRespawn(&car, car.idx + 4); cam.init = 0; }
    }
    printf("seed %u: 10 min, %.1f km driven\n", seed, (car.idx - startIdx)*SEG/1000.0);
    printf("  speed avg %.0f km/h, max %.0f km/h\n", spdSum/t*3.6, maxSpd*3.6);
    printf("  off-road %.1f%% of the time, max lateral %.1f m, resets %d\n", offT/t*100, maxLat, resets);
    printf("  drifts %d (%.0f%% of the time), launches %d, longest air %.2f s\n", drifts, driftT/t*100, jumps, maxAir);
    printf("  average slip while sliding %.0f deg\n", driftT > 0 ? slipSum/driftT*RAD2DEG : 0);
    printf("  camera: swung past 15 deg %.0f%% of the time, max spring offset %.0f deg, max placed %.0f deg (cap %.0f)\n",
           camWide/t*100, maxOff*RAD2DEG, maxCam*RAD2DEG, p[P_MAXANG]);
    return 0;
}
#endif
