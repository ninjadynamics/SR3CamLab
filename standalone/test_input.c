#include <stdio.h>
#include "input.h"
#define CHECK(x) do {if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);return 1;}} while(0)
int main(void) {
    Sr3Input in={0};unsigned char p[15];int i;unsigned previous=0;
    sr3_report(p,&in,4096);
    CHECK(p[1]==128 && p[2]==128 && p[3]==0 && p[4]==0 && p[6]==0 && p[7]==12);
    CHECK(sr3_axis(-32768,4096)==0 && sr3_axis(32767,4096)==255);
    CHECK(sr3_axis(-4096,4096)==128 && sr3_axis(4096,4096)==128);
    for(i=-32768;i<=32767;i++){unsigned current=sr3_axis(i,4096);CHECK(current>=previous && current<=255);previous=current;}
    in.gas=255;in.brake=127;in.buttons=SR3_START|SR3_VIEW|SR3_HANDBRAKE|SR3_UP|SR3_DOWN;
    sr3_report(p,&in,0);CHECK(p[3]==127 && p[4]==255 && p[6]==31);
    in.gas=999;in.brake=999;sr3_report(p,&in,0);CHECK(p[3]==255 && p[4]==255);
    CHECK(sr3_tp_axis(-32768)==0 && sr3_tp_axis(0)==127 && sr3_tp_axis(32767)==254);
    for(i=-32768;i<=32767;i++)CHECK(sr3_tp_axis(i)==(unsigned)((i+32767)/257));
    {short axes[6]={0};
        axes[3]=-15000;CHECK(sr3_binding(22,axes,0,15000));CHECK(!sr3_binding(23,axes,0,15000));
        axes[3]=-14999;CHECK(!sr3_binding(22,axes,0,15000));
        axes[2]=-15000;CHECK(sr3_binding(20,axes,0,15000));CHECK(!sr3_binding(21,axes,0,15000));
        for(i=1;i<=15;i++){CHECK(sr3_binding(i,axes,1u<<(i-1),15000));CHECK(!sr3_binding(i,axes,0,15000));}
        axes[4]=1;CHECK(sr3_binding(24,axes,0,15000));CHECK(!sr3_binding(25,axes,0,15000));
    }
    puts("Input report: center, endpoints, full-range monotonicity, deadzone, pedals and buttons pass.");return 0;
}
