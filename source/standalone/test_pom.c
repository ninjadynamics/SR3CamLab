#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <string.h>
#include "pom.h"
#define CHECK(x) do {if(!(x)){printf("POM test failed at %d: %s\n",__LINE__,#x);return 1;}}while(0)
static IDirect3DVertexShader9 orig_vs,private_vs,other_vs;
static IDirect3DPixelShader9 orig_ps,private_ps;
static IDirect3DTexture9 map;
static IDirect3DVertexShader9 *bound_vs=&orig_vs;
static IDirect3DPixelShader9 *bound_ps=&orig_ps;
static int refs_vs=1,refs_ps=1,refs_private_vs,refs_private_ps,refs_other=1,refs_map=1;
static float control[4]={9,8,7,6};
static float observed_gain, observed_enabled;
static DWORD samplers[2][14];static float relief[4];static int expected_active,draws,draw_bad,fail_ps,fail_create,fail_get,recording;
static int sampler_writes,constant_reads;
static int fail_sampler,fail_restore,old_caps;static int shader_queries;static UINT map_levels=9;static D3DFORMAT map_format=D3DFMT_DXT5;
static const DWORD dummy_code[]={0x12345678};
static const BYTE expected_hash[32]={0x1a,0x2d,0xe6,0x90,0x56,0x85,0x87,0xe6,0xcd,0x9a,0xdb,0xd7,0xd9,0xf6,0x5e,0xf2,0x69,0xbe,0xcd,0x2f,0x89,0xfb,0x89,0xc2,0x24,0x97,0x5b,0x0c,0x59,0x44,0xb9,0x73};
static ULONG WINAPI va(IDirect3DVertexShader9 *s){return s==&orig_vs?++refs_vs:s==&private_vs?++refs_private_vs:++refs_other;}
static ULONG WINAPI vr(IDirect3DVertexShader9 *s){return s==&orig_vs?--refs_vs:s==&private_vs?--refs_private_vs:--refs_other;}
static HRESULT WINAPI vf(IDirect3DVertexShader9 *s,void *out,UINT *n){BYTE bad[4]={0,0,0,0};++shader_queries;if(out)memcpy(out,s==&other_vs?(const void*)bad:(const void*)dummy_code,4);*n=4;return S_OK;}
static ULONG WINAPI pa(IDirect3DPixelShader9 *s){return s==&orig_ps?++refs_ps:++refs_private_ps;}
static ULONG WINAPI pr(IDirect3DPixelShader9 *s){return s==&orig_ps?--refs_ps:--refs_private_ps;}
static HRESULT WINAPI pf(IDirect3DPixelShader9 *s,void *out,UINT *n){(void)s;++shader_queries;if(out)memcpy(out,dummy_code,4);*n=4;return S_OK;}
static ULONG WINAPI tr(IDirect3DTexture9 *t){(void)t;return --refs_map;}
static D3DRESOURCETYPE WINAPI tt(IDirect3DTexture9 *t){(void)t;return D3DRTYPE_TEXTURE;}
static DWORD WINAPI tl(IDirect3DTexture9 *t){(void)t;return map_levels;}
static HRESULT WINAPI td(IDirect3DTexture9 *t,UINT level,D3DSURFACE_DESC *d){(void)t;(void)level;memset(d,0,sizeof(*d));d->Width=d->Height=256;d->Format=map_format;return S_OK;}
static HRESULT WINAPI caps(IDirect3DDevice9 *d,D3DCAPS9 *c){(void)d;memset(c,0,sizeof(*c));c->VertexShaderVersion=D3DVS_VERSION(3,0);c->MaxAnisotropy=16;c->TextureFilterCaps=D3DPTFILTERCAPS_MINFANISOTROPIC;c->PixelShaderVersion=D3DPS_VERSION(old_caps?2:3,0);return S_OK;}
static ULONG WINAPI release(IDirect3DDevice9 *d){(void)d;return 0;}
static HRESULT WINAPI constants(IDirect3DDevice9 *d,UINT start,float *v,UINT n){(void)d;++constant_reads;if(n!=1)return E_FAIL;if(start==30){memcpy(v,control,sizeof(control));return S_OK;}if(start!=10)return E_FAIL;memcpy(v,relief,sizeof(relief));return S_OK;}
static HRESULT WINAPI sc(IDirect3DDevice9 *d,UINT start,const float *v,UINT n){(void)d;if(start!=30 || n!=1)return E_FAIL;memcpy(control,v,sizeof(control));return S_OK;}
static HRESULT WINAPI gv(IDirect3DDevice9 *d,IDirect3DVertexShader9 **s){(void)d;*s=bound_vs;if(*s)va(*s);return S_OK;}
static HRESULT WINAPI gp(IDirect3DDevice9 *d,IDirect3DPixelShader9 **s){(void)d;*s=bound_ps;if(*s)pa(*s);return S_OK;}
static HRESULT WINAPI sv(IDirect3DDevice9 *d,IDirect3DVertexShader9 *s){(void)d;if(fail_restore && s==&orig_vs){fail_restore=0;return E_FAIL;}bound_vs=s;return S_OK;}
static HRESULT WINAPI sp(IDirect3DDevice9 *d,IDirect3DPixelShader9 *s){(void)d;if(fail_ps){fail_ps=0;return E_FAIL;}bound_ps=s;return S_OK;}
static HRESULT WINAPI gs(IDirect3DDevice9 *d,DWORD stage,D3DSAMPLERSTATETYPE state,DWORD *v){(void)d;if(fail_get){fail_get=0;return E_FAIL;}if(stage>1)return E_FAIL;*v=samplers[stage][state];return S_OK;}
static HRESULT WINAPI ss(IDirect3DDevice9 *d,DWORD stage,D3DSAMPLERSTATETYPE state,DWORD v){(void)d;++sampler_writes;if(stage>1)return E_FAIL;if(fail_sampler){fail_sampler=0;return E_FAIL;}samplers[stage][state]=v;return S_OK;}
static HRESULT WINAPI gt(IDirect3DDevice9 *d,DWORD stage,IDirect3DBaseTexture9 **t){(void)d;if(stage!=1)return E_FAIL;*t=(IDirect3DBaseTexture9*)&map;++refs_map;return S_OK;}
static HRESULT WINAPI cv(IDirect3DDevice9 *d,const DWORD *code,IDirect3DVertexShader9 **s){(void)d;(void)code;if(fail_create){fail_create=0;return E_FAIL;}*s=&private_vs;++refs_private_vs;return S_OK;}
static HRESULT WINAPI cp(IDirect3DDevice9 *d,const DWORD *code,IDirect3DPixelShader9 **s){(void)d;(void)code;*s=&private_ps;++refs_private_ps;return S_OK;}
static HRESULT record_draw(void){++draws;observed_gain=control[0];observed_enabled=control[1];if(expected_active){if(bound_vs!=&private_vs || bound_ps!=&private_ps || samplers[1][D3DSAMP_SRGBTEXTURE] || samplers[1][D3DSAMP_MINFILTER]!=D3DTEXF_LINEAR || samplers[0][D3DSAMP_MAGFILTER]!=D3DTEXF_LINEAR || samplers[0][D3DSAMP_MINFILTER]!=D3DTEXF_ANISOTROPIC)draw_bad=1;}else if(bound_vs==&private_vs || bound_ps==&private_ps)draw_bad=1;return D3DERR_DEVICELOST;}
static HRESULT WINAPI dp(IDirect3DDevice9 *d,D3DPRIMITIVETYPE t,UINT a,UINT b){(void)d;(void)t;(void)a;(void)b;return record_draw();}
static HRESULT WINAPI di(IDirect3DDevice9 *d,D3DPRIMITIVETYPE t,INT a,UINT b,UINT c,UINT e,UINT f){(void)d;(void)t;(void)a;(void)b;(void)c;(void)e;(void)f;return record_draw();}
static HRESULT WINAPI du(IDirect3DDevice9 *d,D3DPRIMITIVETYPE t,UINT a,const void *v,UINT b){(void)d;(void)t;(void)a;(void)v;(void)b;return record_draw();}
static HRESULT WINAPI diu(IDirect3DDevice9 *d,D3DPRIMITIVETYPE t,UINT a,UINT b,UINT c,const void *idx,D3DFORMAT fmt,const void *v,UINT s){(void)d;(void)t;(void)a;(void)b;(void)c;(void)idx;(void)fmt;(void)v;(void)s;return record_draw();}
static HRESULT WINAPI bb(IDirect3DDevice9 *d){(void)d;recording=1;return S_OK;}
static HRESULT WINAPI eb(IDirect3DDevice9 *d,IDirect3DStateBlock9 **out){(void)d;recording=0;*out=0;return S_OK;}
int main(void){
 IDirect3DDevice9 d;IDirect3DDevice9Vtbl dv={0};IDirect3DVertexShader9Vtbl vv={0};IDirect3DPixelShader9Vtbl pv={0};IDirect3DTexture9Vtbl tv={0};
 Sr3PomConfig config={dummy_code,dummy_code,expected_hash,expected_hash,4,4,0};Sr3PomStats stats;DWORD saved[2][14];int queries;
 vv.AddRef=va;vv.Release=vr;vv.GetFunction=vf;orig_vs.lpVtbl=private_vs.lpVtbl=other_vs.lpVtbl=&vv;
 pv.AddRef=pa;pv.Release=pr;pv.GetFunction=pf;orig_ps.lpVtbl=private_ps.lpVtbl=&pv;
 tv.Release=tr;tv.GetType=tt;tv.GetLevelCount=tl;tv.GetLevelDesc=td;map.lpVtbl=&tv;
 dv.GetDeviceCaps=caps;dv.Release=release;dv.GetPixelShaderConstantF=constants;dv.SetPixelShaderConstantF=sc;dv.GetVertexShader=gv;dv.GetPixelShader=gp;dv.SetVertexShader=sv;dv.SetPixelShader=sp;
 dv.GetSamplerState=gs;dv.SetSamplerState=ss;dv.GetTexture=gt;dv.CreateVertexShader=cv;dv.CreatePixelShader=cp;dv.DrawPrimitive=dp;dv.DrawIndexedPrimitive=di;dv.DrawPrimitiveUP=du;dv.DrawIndexedPrimitiveUP=diu;dv.BeginStateBlock=bb;dv.EndStateBlock=eb;d.lpVtbl=&dv;
 samplers[1][D3DSAMP_SRGBTEXTURE]=1;samplers[1][D3DSAMP_MINFILTER]=D3DTEXF_ANISOTROPIC;samplers[1][D3DSAMP_MAGFILTER]=D3DTEXF_POINT;samplers[1][D3DSAMP_MIPFILTER]=D3DTEXF_POINT;memcpy(saved,samplers,sizeof(saved));
 old_caps=1;CHECK(!sr3_pom_attach(&d,&config) && d.lpVtbl==&dv);old_caps=0;
 CHECK(sr3_pom_attach(&d,&config));{int e,n,i;sr3_pom_controls(&e,&n);CHECK(e==1 && n==6);sr3_pom_adjust(0);sr3_pom_controls(&e,&n);CHECK(!e);for(i=0;i<100;i++)sr3_pom_adjust(1);sr3_pom_controls(&e,&n);CHECK(n==10);for(i=0;i<100;i++)sr3_pom_adjust(-1);sr3_pom_controls(&e,&n);CHECK(n==0);for(i=0;i<10;i++)sr3_pom_adjust(1);sr3_pom_adjust(0);}CHECK(sr3_pom_attach(&d,&config));CHECK(d.lpVtbl==&dv && dv.DrawPrimitive!=dp); /* native table identity retained */
 CHECK(IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1)==D3DERR_DEVICELOST);CHECK(shader_queries==0 && draws==1);
 relief[0]=relief[1]=0.012f;relief[2]=SR3_POM_MARKER;expected_active=1;
 CHECK(IDirect3DDevice9_DrawIndexedPrimitive(&d,D3DPT_TRIANGLELIST,0,0,3,0,1)==D3DERR_DEVICELOST);
 CHECK(!draw_bad && bound_vs==&orig_vs && bound_ps==&orig_ps && !memcmp(saved,samplers,sizeof(saved)) && control[0]==9 && control[1]==8 && control[2]==7 && control[3]==6);
 {IDirect3DDevice9 other={&dv};expected_active=0;IDirect3DDevice9_DrawPrimitive(&other,D3DPT_TRIANGLELIST,0,1);CHECK(IDirect3DDevice9_Release(&other)==0 && dv.DrawPrimitive!=dp);expected_active=1;}
 queries=shader_queries;
 IDirect3DDevice9_DrawPrimitiveUP(&d,D3DPT_TRIANGLELIST,1,0,48);IDirect3DDevice9_DrawIndexedPrimitiveUP(&d,D3DPT_TRIANGLELIST,0,3,1,0,D3DFMT_INDEX16,0,48);
 CHECK(shader_queries==queries && !draw_bad); /* immutable shader identity cached */
 expected_active=0;fail_ps=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);
 CHECK(!draw_bad && bound_vs==&orig_vs && bound_ps==&orig_ps && !memcmp(saved,samplers,sizeof(saved)) && control[0]==9 && control[1]==8 && control[2]==7 && control[3]==6);
 fail_get=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(!draw_bad);
 sr3_pom_before_reset(&d);map_format=D3DFMT_DXT1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);map_format=D3DFMT_DXT5;
 sr3_pom_before_reset(&d);map_levels=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);map_levels=9;
 bound_vs=&other_vs;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);bound_vs=&orig_vs;CHECK(!draw_bad);
 IDirect3DDevice9_BeginStateBlock(&d);IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);{IDirect3DStateBlock9 *block;IDirect3DDevice9_EndStateBlock(&d,&block);}CHECK(!draw_bad && !recording);
 relief[2]=0;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);relief[2]=SR3_POM_MARKER; /* state-block Apply is read from actual device */
 sr3_pom_before_reset(&d);CHECK(refs_vs==1 && refs_ps==1 && refs_private_vs==0 && refs_private_ps==0 && refs_other==1 && refs_map==1);
 fail_create=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(!draw_bad);
 expected_active=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(!draw_bad);
 stats=sr3_pom_stats();CHECK(stats.replaced==4 && stats.failures==3 && stats.rejected==3 && stats.restore_failures==0);
 expected_active=0;fail_sampler=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);
 CHECK(!draw_bad && bound_vs==&orig_vs && !memcmp(saved,samplers,sizeof(saved)));
 expected_active=1;fail_restore=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);
 stats=sr3_pom_stats();CHECK(stats.restore_failures==1);bound_vs=&orig_vs;expected_active=0;
 IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(!draw_bad && sr3_pom_stats().replaced==stats.replaced);
 sr3_pom_before_reset(&d);expected_active=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(!draw_bad);
 /* Approved family gains can exceed the old .05 UV gate. */
 relief[0]=relief[1]=.09f;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==1 && !draw_bad);
 expected_active=0;relief[0]=relief[1]=.26f;{unsigned long count=sr3_pom_stats().replaced;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(sr3_pom_stats().replaced==count && !draw_bad);}expected_active=1;
 /* Verify values seen by an actual intercepted draw, plus restoration. */
 relief[0]=relief[1]=.008f;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==1 && observed_enabled==1 && control[0]==9);
 relief[0]=relief[1]=.012f;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==1 && control[0]==9);
 {int i;for(i=0;i<5;i++)sr3_pom_adjust(-1);}
 IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==.5f);
 relief[0]=relief[1]=.008f;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==.5f);
 {int i;for(i=0;i<35;i++)sr3_pom_adjust(1);}
 IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==1);
 sr3_pom_adjust(0);expected_active=0;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(control[1]==8 && !draw_bad);sr3_pom_adjust(0);expected_active=1;
 /* Alternating immutable shader pairs must not rehash on every draw. */
 bound_vs=&other_vs;expected_active=0;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);
 bound_vs=&orig_vs;expected_active=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);queries=shader_queries;
 {int i;for(i=0;i<4;i++){bound_vs=&other_vs;expected_active=0;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);bound_vs=&orig_vs;expected_active=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);}}
 CHECK(shader_queries==queries && !draw_bad);
 /* Read actual state, but avoid redundant setter/restore calls. */
 samplers[1][D3DSAMP_SRGBTEXTURE]=0;samplers[1][D3DSAMP_MINFILTER]=samplers[1][D3DSAMP_MAGFILTER]=samplers[1][D3DSAMP_MIPFILTER]=D3DTEXF_LINEAR;
 samplers[0][D3DSAMP_MINFILTER]=D3DTEXF_ANISOTROPIC;samplers[0][D3DSAMP_MAGFILTER]=samplers[0][D3DSAMP_MIPFILTER]=D3DTEXF_LINEAR;samplers[0][D3DSAMP_MAXANISOTROPY]=8;
 sampler_writes=0;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(!sampler_writes && !draw_bad);
 {int i,reads=constant_reads,writes=sampler_writes,queries=shader_queries;unsigned long replaced=sr3_pom_stats().replaced;
 for(i=0;i<100;i++)sr3_pom_adjust(-1);expected_active=0;
 IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);
 IDirect3DDevice9_DrawIndexedPrimitive(&d,D3DPT_TRIANGLELIST,0,0,3,0,1);
 IDirect3DDevice9_DrawPrimitiveUP(&d,D3DPT_TRIANGLELIST,1,0,48);
 IDirect3DDevice9_DrawIndexedPrimitiveUP(&d,D3DPT_TRIANGLELIST,0,3,1,0,D3DFMT_INDEX16,0,48);
 CHECK(!draw_bad && constant_reads==reads && sampler_writes==writes && shader_queries==queries && sr3_pom_stats().replaced==replaced);
 CHECK(bound_vs==&orig_vs && bound_ps==&orig_ps && control[0]==9 && control[1]==8);
 for(i=0;i<100;i++)sr3_pom_adjust(1);expected_active=1;IDirect3DDevice9_DrawPrimitive(&d,D3DPT_TRIANGLELIST,0,1);CHECK(observed_gain==1 && !draw_bad && sr3_pom_stats().replaced==replaced+1);}
 puts("POM zero baseline: all four native draw routes, zero constant reads/state writes/replacements, clean re-enable PASS.");
 puts("POM optimizations: alternating-pair cache and zero redundant sampler writes pass.");
 puts("POM material controls: global1, half gain, safe1x cap, OFF and draw-state restoration pass.");
 CHECK(IDirect3DDevice9_Release(&d)==0);CHECK(dv.DrawPrimitive==dp && dv.Release==release);CHECK(refs_vs==1 && refs_ps==1 && refs_private_vs==0 && refs_private_ps==0 && refs_other==1 && refs_map==1);
 puts("POM: all draw routes, exact identity, marker bypass, partial failure restoration, state blocks, maps, reset/recreate and COM cleanup passed.");return 0;
}
