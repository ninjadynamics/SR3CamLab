/* SR3Lab, Copyright (c) 2026 Ninja Dynamics. MIT license (../LICENSE). */
#ifndef SR3LAB_INPUT_H
#define SR3LAB_INPUT_H
#include <stdint.h>
#include <string.h>
enum { SR3_START=1, SR3_VIEW=2, SR3_HANDBRAKE=4, SR3_UP=8, SR3_DOWN=16 };
typedef struct {
    int steering;                 /* -32768 .. 32767 */
    unsigned gas, brake;          /* 0 .. 255 */
    unsigned buttons;
} Sr3Input;
/* TP's SR3 XInput conversion divides the biased signed sample by 257.
   Integer truncation deliberately preserves its center (127) and upper end (254). */
static unsigned sr3_tp_axis(int value) {
    if(value < -32768)value=-32768;
    if(value > 32767)value=32767;
    return (unsigned)((value+32767)/257);
}
/* Canonical binding IDs from settings.c: buttons 1..15, signed axes 16..23,
   triggers 24..25. SDL axis Y is negative upward. */
static int sr3_binding(int binding,const short axes[6],unsigned buttons,int threshold) {
    int value;
    if(binding<1 || binding>25)return 0;
    if(binding<=15)return (buttons & (1u<<(binding-1)))!=0;
    if(binding>=24)return axes[binding-20]>0;
    value=axes[(binding-16)/2];
    return binding%2?value>=threshold:value<=-threshold;
}
static unsigned sr3_axis(int value, int deadzone) {
    int magnitude, scaled;
    if (value < -32768) value=-32768;
    if (value > 32767) value=32767;
    if (deadzone < 0) deadzone=0;
    if (deadzone > 30000) deadzone=30000;
    magnitude=value<0 ? -value : value;
    if (magnitude<=deadzone) return 128;
    scaled=(magnitude-deadzone)*(value<0?128:127)/((value<0?32768:32767)-deadzone);
    return (unsigned)(value<0?128-scaled:128+scaled);
}
static void sr3_report(unsigned char report[15], const Sr3Input *input, int deadzone) {
    memset(report,0,15);
    report[1]=report[2]=(unsigned char)sr3_axis(input->steering,deadzone);
    report[3]=(unsigned char)(input->brake>255?255:input->brake);
    report[4]=(unsigned char)(input->gas>255?255:input->gas);
    report[6]=(unsigned char)(input->buttons&31);
    report[7]=12;                 /* cabinet's two always-on status bits */
}
#endif
