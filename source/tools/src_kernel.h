/* Shared SRC equations. Inputs use metres/frame, radians/frame and mass-1000
   force units. Helpers fsin/fsqrt/fabsf_/clampf/fpow and PI belong to the caller.
   This is a force kernel, not a complete suspension/engine/collision simulation.
   See docs/kb/29_src_steering_code.md for original i960 addresses. */
#ifndef SR3_SRC_KERNEL_H
#define SR3_SRC_KERNEL_H

static float src_steering(float counts, float previous, float frames)
{
    float target = 0.84f * clampf(counts, -80.0f, 80.0f) / 80.0f;
    return previous + (1.0f - fpow(0.1f, frames)) * (target - previous);
}

/* Standard Celica/Delta engine branch 0x3A5A0..0x3A860, before the
   post-tyre effects writes at 0x38150 / 0x382E0. Effective ratio is final
   drive times engaged gear; zero denotes the shift/neutral branch.
   Hidden-car RPM feedback is separate and is not represented here. */
static float src_wheelspin(float speed, float rpm, float effective_ratio,
                           float forward_speed)
{
    if (rpm <= 1000.0f || forward_speed <= 0.0f || effective_ratio <= 0.0f)
        return 0.0f;
    float r = speed * 60.0f;
    r = r * 60.0f;
    r = (float)(((double)r / 1.8849555921538759) * effective_ratio);
    return clampf(fabsf_((rpm - r) / rpm), 0.0f, 1.0f);
}

/* Drive force from the RPM selected earlier in 0x3A320. The caller owns
   RPM feedback, gear changes and the shift throttle override. The torque table
   has at least 82 entries (original AT 0x5D8F20, MT 0x5D90C0).
   Brake input follows 0x3B128's integer half-count before normalization. */
static float src_drive_force(float speed, float rpm, float ratio, float throttle,
                             int brake_byte, float forward_speed, float gravity,
                             const float *curve)
{
    float brake = (float)((brake_byte - 48) / 2) / 64.0f;
    brake *= 1000.0f * gravity;
    if (brake < 0.0f) brake = 0.0f;
    if (forward_speed < 0.0f) brake = -brake;
    if (ratio <= 0.0f) return -brake;
    rpm = clampf(rpm, 0.0f, 8800.0f);
    float inertia = 0.0002f + 0.0002f / ratio;
    int index = (int)(((double)rpm / 100.0) / 1.1);
    float fraction = (float)(((int)rpm % 100) / 100.0);
    float torque = curve[index] + (curve[index + 1] - curve[index]) * fraction;
    float scale = throttle * 2.75f;
    scale *= gravity;
    torque *= scale;
    float next = clampf(rpm + (torque - 0.02f) / inertia, 0.0f, 8800.0f);
    float rolling = speed * 60.0f;
    rolling *= 60.0f;
    rolling = forward_speed < 0.0f ? 0.0f : (float)(((double)rolling / 1.8849555921538759) * ratio);
    float force = ((next - rolling) * inertia) * ratio;
    force = (float)((double)force / 0.3);
    return force - brake;
}

/* Original automatic gearbox at 0x3B008: 31-frame minimum between
   changes, 7920 RPM upshift only below 0.1 wheelspin, throttle-dependent downshift.
   Caller passes the force-stage wheelspin saved by the previous engine tick. */
static int src_auto_gear(int gear, unsigned int *age, float rpm, float spin, float throttle)
{
    unsigned int old_age = *age;
    if (*age < 31) ++*age;
    if (old_age <= 29) return gear;
    int next = gear;
    if ((double)rpm > 7920.000000000001 && spin < 0.1f) ++next;
    else if ((double)rpm < (double)throttle * 2750.0 + 3300.0000000000005) --next;
    if (next < 1) next = 1;
    if (next > 4) next = 4;
    if (next != gear) *age = 0;
    return next;
}

/* Engine feedback at 0x3AA38, after the tyre friction circle. Both axle
   longitudinal forces are in the axle frames, before rotating the front axle.
   Standard engaged-gear branch only; shifts/neutral have separate state. */
static float src_engine_feedback(float rpm, float ratio, float throttle,
                                  float drive, float axle_force)
{
    if (ratio <= 0.0f) return 0.0f;
    float inertia = 0.0002f + 0.0002f / ratio;
    float scale = rpm < 6000.0f && throttle > 0.8f ? rpm / 6000.0f : 1.0f;
    return (0.3f * 1.15f * (drive - axle_force * scale) / ratio) / inertia;
}

/* Next frame's engaged-gear RPM selection in 0x3A320. The 200 RPM cap is
   per original physics frame; caller must run at the original tick rate. */
static float src_engine_rpm(float previous_rpm, float speed, float ratio,
                             float forward_speed, float feedback)
{
    float rolling = speed * 60.0f;
    rolling *= 60.0f;
    rolling = forward_speed < 0.0f ? 0.0f : (float)(((double)rolling / 1.8849555921538759) * ratio);
    float target = clampf(rolling + feedback, 0.0f, 8800.0f);
    return previous_rpm + clampf(target - previous_rpm, -200.0f, 200.0f);
}

/* Compression sums are SRC contact depths, not normalized SR3 travel. */
static float src_load_transfer(float front, float rear, float previous,
                               float lag_up, float lag_down, float frames)
{
    float sum = front + rear;
    if (sum == 0.0f) return 0.0f;
    float raw = (front - rear) / sum;
    float lag = raw > previous ? lag_up : lag_down;
    float result = raw - fpow(lag, frames) * (raw - previous);
    if (result > 0.0f) result += 0.08f * fsin(PI * result);
    return result;
}

/* SRC's tyre force for one axle (kb 29 section 7); returns the side force, fx in / out */
static float src_tyre(float sig, float axle_speed, float fmax, float k, float *fx, float c, float wsp)
{
    float a = fabsf_(sig) * k; if (a > PI / 2) a = PI / 2;
    float fy = fmax * fsin(a);
    float tot = fsqrt(fy * fy + *fx * *fx) * (1.0f + wsp);
    if (tot > fmax) {
        float q = fmax / tot, f = c * fsqrt(q) + (1.0f - c) * q * q;
        fy = fy * f * 1.1f; *fx = *fx * f;
    }
    if (sig >= 0.0f) fy = -fy;
    float ls = fabsf_(sig) * axle_speed;
    if (ls < 0.02f) fy *= ls / 0.02f;
    return fy;
}


static float src_yaw(float previous, float torque, float dbeta,
                     float kb, float kw, float frames)
{
    float w = clampf(previous + frames * torque / 1146.0f, -0.1f, 0.1f);
    return w - kb * dbeta - (1.0f - fpow(1.0f - kw, frames)) * w;
}
#endif
