/* Draw-scoped, opt-in relief. No engine addresses, shared technique edits or polling. */
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <wincrypt.h>
#include <d3d9.h>
#include <string.h>
#include <stdio.h>
#include "pom.h"

typedef struct PairCache {IDirect3DVertexShader9 *vs;IDirect3DPixelShader9 *ps;int ok;} PairCache;
#define PAIR_CACHE_SIZE 16
typedef struct Pom {
 IDirect3DDevice9 *device;
 IDirect3DDevice9Vtbl original;
 IDirect3DDevice9Vtbl *table;
 Sr3PomConfig config;
 Sr3PomStats stats;
 IDirect3DVertexShader9 *vs;
 IDirect3DPixelShader9 *ps;
 PairCache pairs[PAIR_CACHE_SIZE];unsigned pair_next;
 UINT map_width,map_height;
 IDirect3DBaseTexture9 *checked_map;UINT checked_width,checked_height;
 LARGE_INTEGER fps_start,fps_frequency;unsigned fps_frames;int fps_tenths,fps_gain;
 int pair_ok, busy, cleaning, recording, disabled;
 unsigned notices;
 DWORD anisotropy;
 IDirect3DTexture9 *hud;int hud_on,hud_tenths;
 volatile LONG enabled, tenths;
} Pom;
static Pom p;
static void notice(int event) {
 unsigned mask=1u<<event;if(!(p.notices&mask)){p.notices|=mask;if(p.config.notify)p.config.notify(event);}
}
static const D3DSAMPLERSTATETYPE states[] = {D3DSAMP_SRGBTEXTURE,D3DSAMP_MINFILTER,D3DSAMP_MAGFILTER,D3DSAMP_MIPFILTER};
static const D3DSAMPLERSTATETYPE color_states[] = {D3DSAMP_MINFILTER,D3DSAMP_MAGFILTER,D3DSAMP_MIPFILTER,D3DSAMP_MAXANISOTROPY};
static const DWORD linear_states[] = {0,D3DTEXF_LINEAR,D3DTEXF_LINEAR,D3DTEXF_LINEAR};
typedef struct Saved { IDirect3DVertexShader9 *vs; IDirect3DPixelShader9 *ps; DWORD sampler[4], color_sampler[4]; float controls[4]; int touched; unsigned sampler_mask,color_mask; } Saved;

static void resources(void) {
 LARGE_INTEGER clock0,clock1;QueryPerformanceCounter(&clock0);
 IDirect3DVertexShader9 *vs=p.vs;int i;
 IDirect3DPixelShader9 *ps=p.ps;
 if(p.cleaning)return;
 ++p.stats.resource_clears;p.cleaning=1;p.vs=0;p.ps=0;p.pair_ok=0;
 if(p.checked_map){IDirect3DBaseTexture9_Release(p.checked_map);p.checked_map=0;}
 if(p.hud){IDirect3DTexture9_Release(p.hud);p.hud=0;}
 if(vs)IDirect3DVertexShader9_Release(vs);
 if(ps)IDirect3DPixelShader9_Release(ps);
 for(i=0;i<PAIR_CACHE_SIZE;i++){PairCache entry=p.pairs[i];memset(&p.pairs[i],0,sizeof(entry));if(entry.vs)IDirect3DVertexShader9_Release(entry.vs);if(entry.ps)IDirect3DPixelShader9_Release(entry.ps);}
 p.pair_next=0;
 p.cleaning=0;QueryPerformanceCounter(&clock1);p.stats.cleanup_ms+=1000.0*(clock1.QuadPart-clock0.QuadPart)/p.fps_frequency.QuadPart;
}
void sr3_pom_before_reset(IDirect3DDevice9 *d) { if(d==p.device){resources();p.fps_start.QuadPart=0;p.fps_frames=0;p.fps_tenths=-1;p.disabled=0;p.recording=0;} }
Sr3PomStats sr3_pom_stats(void) {Sr3PomStats result=p.stats;result.fps_tenths=p.fps_tenths;sr3_pom_controls(&result.pom_enabled,&result.global_tenths);return result;}
void sr3_pom_controls(int *enabled,int *tenths) {
 *enabled=InterlockedCompareExchange(&p.enabled,0,0);*tenths=InterlockedCompareExchange(&p.tenths,0,0);
}
int sr3_pom_adjust(int delta) {
 LONG old,next;if(!p.device)return 0;
 if(!delta){do{old=InterlockedCompareExchange(&p.enabled,0,0);}while(InterlockedCompareExchange(&p.enabled,!old,old)!=old);}
 else {do{old=InterlockedCompareExchange(&p.tenths,0,0);next=old+(delta>0?1:-1);if(next<0)next=0;if(next>10)next=10;}while(InterlockedCompareExchange(&p.tenths,next,old)!=old);}
 return 1;
}

static int sha_matches(const BYTE *data,UINT size,const BYTE expected[32]) {
 HCRYPTPROV provider=0;HCRYPTHASH hash=0;BYTE actual[32];DWORD n=sizeof(actual);int ok=0;
 if(!CryptAcquireContextA(&provider,0,0,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))return 0;
 if(CryptCreateHash(provider,CALG_SHA_256,0,0,&hash) && CryptHashData(hash,data,size,0) &&
    CryptGetHashParam(hash,HP_HASHVAL,actual,&n,0) && n==32)ok=!memcmp(actual,expected,32);
 if(hash)CryptDestroyHash(hash);CryptReleaseContext(provider,0);return ok;
}
static int pair_matches(IDirect3DVertexShader9 *vs,IDirect3DPixelShader9 *ps) {
 LARGE_INTEGER clock0,clock1;BYTE bytes[16384];UINT n=0;int ok=0;
 if(!vs || !ps)return 0;
 {unsigned i;for(i=0;i<PAIR_CACHE_SIZE;i++)if(p.pairs[i].vs==vs && p.pairs[i].ps==ps)return p.pairs[i].ok;}
 QueryPerformanceCounter(&clock0);++p.stats.pair_misses;
 if(SUCCEEDED(IDirect3DVertexShader9_GetFunction(vs,0,&n)) && n==p.config.original_vs_size && n<=sizeof(bytes) &&
    SUCCEEDED(IDirect3DVertexShader9_GetFunction(vs,bytes,&n)) && n==p.config.original_vs_size && sha_matches(bytes,n,p.config.original_vs_hash)) {
  n=0;
  ok=SUCCEEDED(IDirect3DPixelShader9_GetFunction(ps,0,&n)) && n==p.config.original_ps_size && n<=sizeof(bytes) &&
     SUCCEEDED(IDirect3DPixelShader9_GetFunction(ps,bytes,&n)) && n==p.config.original_ps_size && sha_matches(bytes,n,p.config.original_ps_hash);
 }
 {PairCache *entry=&p.pairs[p.pair_next++%PAIR_CACHE_SIZE];
  if(entry->vs)IDirect3DVertexShader9_Release(entry->vs);if(entry->ps)IDirect3DPixelShader9_Release(entry->ps);
  entry->vs=vs;entry->ps=ps;entry->ok=ok;IDirect3DVertexShader9_AddRef(vs);IDirect3DPixelShader9_AddRef(ps);}
 QueryPerformanceCounter(&clock1);p.stats.identify_ms+=1000.0*(clock1.QuadPart-clock0.QuadPart)/p.fps_frequency.QuadPart;
 return ok;
}
static int map_valid(IDirect3DDevice9 *d) {
 IDirect3DBaseTexture9 *base=0;D3DSURFACE_DESC desc;int ok=0;UINT levels,n=1,side;
 if(FAILED(IDirect3DDevice9_GetTexture(d,1,&base)) || !base)return 0;
 if(base==p.checked_map){p.map_width=p.checked_width;p.map_height=p.checked_height;IDirect3DBaseTexture9_Release(base);return 1;}
 ++p.stats.map_misses;
 if(IDirect3DBaseTexture9_GetType(base)==D3DRTYPE_TEXTURE &&
    SUCCEEDED(IDirect3DTexture9_GetLevelDesc((IDirect3DTexture9*)base,0,&desc))) {
  side=desc.Width>desc.Height?desc.Width:desc.Height;while(side>1){side>>=1;++n;}
  levels=IDirect3DBaseTexture9_GetLevelCount(base);p.map_width=desc.Width;p.map_height=desc.Height;
  ok=desc.Format==D3DFMT_DXT5 && desc.Width && desc.Height && desc.Width<=2048 && desc.Height<=2048 &&
     !(desc.Width&(desc.Width-1)) && !(desc.Height&(desc.Height-1)) && levels==n;
 }
 if(ok){if(p.checked_map)IDirect3DBaseTexture9_Release(p.checked_map);p.checked_map=base;p.checked_width=p.map_width;p.checked_height=p.map_height;}
 else IDirect3DBaseTexture9_Release(base);return ok;
}
/* The game owns each height texture. Native D3D9 private IUnknown data
   ties compiled shaders to that texture's lifetime, with no back-reference
   to the texture. Ordinary device Release still performs the full cleanup.
   Texture destruction frees the cache through D3D9's normal COM ownership. */
static const GUID cache_vs={0x713e046a,0x573e,0x41ac,{0xac,0x58,0x3a,0x89,0x1c,0x9b,0xd1,0x12}};
static const GUID cache_ps={0x35c27119,0x55ed,0x48ce,{0x82,0x7f,0x3e,0xe2,0x47,0x89,0x56,0xa4}};
static const GUID cache_tag={0xd997833a,0xb57a,0x4512,{0x85,0x0e,0x14,0x03,0x9a,0x87,0x65,0x93}};
static unsigned cache_generation;
static int shaders(IDirect3DDevice9 *d) {
 IDirect3DBaseTexture9 *map=p.checked_map;DWORD size;unsigned tag=0;int cache=map && map->lpVtbl->GetPrivateData && map->lpVtbl->SetPrivateData;
 if(cache){size=sizeof(tag);if(FAILED(IDirect3DBaseTexture9_GetPrivateData(map,&cache_tag,&tag,&size)) || size!=sizeof(tag))tag=0;
  if(tag==cache_generation){
   if(!p.vs){size=sizeof(p.vs);if(FAILED(IDirect3DBaseTexture9_GetPrivateData(map,&cache_vs,&p.vs,&size)))p.vs=0;}
   if(!p.ps){size=sizeof(p.ps);if(FAILED(IDirect3DBaseTexture9_GetPrivateData(map,&cache_ps,&p.ps,&size)))p.ps=0;}
  }
 }
 if(!p.vs){++p.stats.shader_builds;if(FAILED(IDirect3DDevice9_CreateVertexShader(d,p.config.vs,&p.vs)))return 0;}
 if(!p.ps){++p.stats.shader_builds;if(FAILED(IDirect3DDevice9_CreatePixelShader(d,p.config.ps,&p.ps)))return 0;}
 if(cache && tag!=cache_generation){
  /* Passing the interface itself is required for D3DSPD_IUNKNOWN. */
  HRESULT a=IDirect3DBaseTexture9_SetPrivateData(map,&cache_vs,p.vs,sizeof(p.vs),D3DSPD_IUNKNOWN);
  HRESULT b=IDirect3DBaseTexture9_SetPrivateData(map,&cache_ps,p.ps,sizeof(p.ps),D3DSPD_IUNKNOWN);
  if(SUCCEEDED(a) && SUCCEEDED(b))IDirect3DBaseTexture9_SetPrivateData(map,&cache_tag,&cache_generation,sizeof(cache_generation),0);
  else {IDirect3DBaseTexture9_FreePrivateData(map,&cache_vs);IDirect3DBaseTexture9_FreePrivateData(map,&cache_ps);}
 }
 return 1;
}
static void end(IDirect3DDevice9 *d,Saved *s) {
 int i,bad=0;
 if(s->touched) {
  if(FAILED(IDirect3DDevice9_SetVertexShader(d,s->vs)))bad=1;
  if(FAILED(IDirect3DDevice9_SetPixelShader(d,s->ps)))bad=1;
  for(i=0;i<4;++i){
   if((s->sampler_mask&(1u<<i)) && FAILED(IDirect3DDevice9_SetSamplerState(d,1,states[i],s->sampler[i])))bad=1;
   if((s->color_mask&(1u<<i)) && FAILED(IDirect3DDevice9_SetSamplerState(d,0,color_states[i],s->color_sampler[i])))bad=1;
  }
  if(FAILED(IDirect3DDevice9_SetPixelShaderConstantF(d,30,s->controls,1)))bad=1;
  if(bad){++p.stats.restore_failures;p.disabled=1;notice(5);}
 }
 if(s->vs)IDirect3DVertexShader9_Release(s->vs);
 if(s->ps)IDirect3DPixelShader9_Release(s->ps);
 p.busy=0;
}
static int begin(IDirect3DDevice9 *d,Saved *s) {
 float relief[4],controls[4];int i,enabled,tenths;
 memset(s,0,sizeof(*s));++p.stats.draws;
 if(d!=p.device || p.disabled || p.recording || p.busy || p.cleaning)return 0;
 /* True baseline: no shader inspection, map validation or state changes. */
 sr3_pom_controls(&enabled,&tenths);if(!enabled || tenths==0)return 0;
 if(FAILED(IDirect3DDevice9_GetPixelShaderConstantF(d,10,relief,1)) || relief[2]!=SR3_POM_MARKER ||
    !(relief[0]>=0 && relief[0]<=0.25f && relief[1]>=0 && relief[1]<=0.25f) || !(relief[0]+relief[1]>0))return 0;
 ++p.stats.candidates;p.busy=1;
 if(FAILED(IDirect3DDevice9_GetVertexShader(d,&s->vs)) || FAILED(IDirect3DDevice9_GetPixelShader(d,&s->ps)))goto failed;
 if(!pair_matches(s->vs,s->ps)){++p.stats.rejected;notice(2);end(d,s);return 0;}
 if(!map_valid(d)){++p.stats.rejected;notice(3);end(d,s);return 0;}
 for(i=0;i<4;++i){
  if(FAILED(IDirect3DDevice9_GetSamplerState(d,1,states[i],&s->sampler[i])))goto failed;
  if(FAILED(IDirect3DDevice9_GetSamplerState(d,0,color_states[i],&s->color_sampler[i])))goto failed;
 }
 if(FAILED(IDirect3DDevice9_GetPixelShaderConstantF(d,30,s->controls,1)))goto failed;
 {LARGE_INTEGER clock0,clock1;QueryPerformanceCounter(&clock0);
 if(!shaders(d))goto failed;
 QueryPerformanceCounter(&clock1);p.stats.build_ms+=1000.0*(clock1.QuadPart-clock0.QuadPart)/p.fps_frequency.QuadPart;}
 s->touched=1;
 if(FAILED(IDirect3DDevice9_SetVertexShader(d,p.vs)) || FAILED(IDirect3DDevice9_SetPixelShader(d,p.ps)))goto failed;
 for(i=0;i<4;++i)if(s->sampler[i]!=linear_states[i]){s->sampler_mask|=1u<<i;if(FAILED(IDirect3DDevice9_SetSamplerState(d,1,states[i],linear_states[i])))goto failed;}
 /* Identical albedo filtering in ON and OFF makes the live comparison honest. */
 for(i=0;i<4;++i){DWORD value=i==0?(p.anisotropy>1?D3DTEXF_ANISOTROPIC:D3DTEXF_LINEAR):i==3?p.anisotropy:D3DTEXF_LINEAR;
  if(s->color_sampler[i]!=value){s->color_mask|=1u<<i;if(FAILED(IDirect3DDevice9_SetSamplerState(d,0,color_states[i],value)))goto failed;}
 }
 /* Approved per-material depths are already encoded in the track. */
 controls[0]=tenths*.1f;
 controls[1]=(float)enabled;controls[2]=(float)p.map_width;controls[3]=(float)p.map_height;
 if(FAILED(IDirect3DDevice9_SetPixelShaderConstantF(d,30,controls,1)))goto failed;
 ++p.stats.replaced;notice(1);return 1;
failed:
 ++p.stats.failures;notice(4);end(d,s);return 0;
}
static HRESULT WINAPI draw(IDirect3DDevice9 *d,D3DPRIMITIVETYPE type,UINT start,UINT count) {
 Saved s;int active=begin(d,&s);HRESULT hr=p.original.DrawPrimitive(d,type,start,count);if(active)end(d,&s);return hr;
}
static HRESULT WINAPI indexed(IDirect3DDevice9 *d,D3DPRIMITIVETYPE type,INT base,UINT min,UINT nv,UINT start,UINT count) {
 Saved s;int active=begin(d,&s);HRESULT hr=p.original.DrawIndexedPrimitive(d,type,base,min,nv,start,count);if(active)end(d,&s);return hr;
}
static HRESULT WINAPI draw_up(IDirect3DDevice9 *d,D3DPRIMITIVETYPE type,UINT count,const void *v,UINT stride) {
 Saved s;int active=begin(d,&s);HRESULT hr=p.original.DrawPrimitiveUP(d,type,count,v,stride);if(active)end(d,&s);return hr;
}
static HRESULT WINAPI indexed_up(IDirect3DDevice9 *d,D3DPRIMITIVETYPE type,UINT min,UINT nv,UINT count,const void *idx,D3DFORMAT fmt,const void *v,UINT stride) {
 Saved s;int active=begin(d,&s);HRESULT hr=p.original.DrawIndexedPrimitiveUP(d,type,min,nv,count,idx,fmt,v,stride);if(active)end(d,&s);return hr;
}
static void unhook(void);
static int rehook(void);
static int hook_current(IDirect3DDevice9 *d);
static HRESULT WINAPI begin_block(IDirect3DDevice9 *d) {
 HRESULT hr;
 if(d!=p.device)return p.original.BeginStateBlock(d);
 /* Native D3D rewrites the table in-place on Begin/EndStateBlock. Let it
    transition with native entries, then wrap the resulting recording table. */
 unhook();hr=p.original.BeginStateBlock(d);
 if(SUCCEEDED(hr))p.recording=1;
 if(!hook_current(d)){p.disabled=1;notice(4);}
 return hr;
}
static HRESULT WINAPI end_block(IDirect3DDevice9 *d,IDirect3DStateBlock9 **out) {
 HRESULT hr;
 if(d!=p.device)return p.original.EndStateBlock(d,out);
 unhook();hr=p.original.EndStateBlock(d,out);
 if(SUCCEEDED(hr))p.recording=0;
 if(!hook_current(d)){p.disabled=1;notice(4);}
 return hr;
}
static ULONG WINAPI release_device(IDirect3DDevice9 *d) {
 ULONG n;
 if(d!=p.device || p.busy || p.cleaning)return p.original.Release(d);
 /* The driver can allocate its extended table with the device. Restore its
    slots BEFORE Release can free that memory, then reattach only if alive. */
 resources();unhook();
 n=p.original.Release(d);
 if(!n)p.device=0;
 else if(!rehook()){p.disabled=1;p.device=0;}
 return n;
}
/* Keep the driver's complete table and identity. Native D3D uses private entries
   beyond the public IDirect3DDevice9 prefix, even in calls such as Clear. */
typedef struct Hook {void **slot;void *replacement;void *original;} Hook;
static Hook hooks[7];static int hook_count;
/* Protect each native vtable page once per transition, not twice per slot.
   Restore before Release exactly as before: no inferred reference thresholds. */
static int write_hooks(int install,int count) {
 void *pages[7];DWORD protections[7];unsigned page_count=0,i,j;SYSTEM_INFO info;
 GetSystemInfo(&info);
 for(i=0;i<(unsigned)count;i++) {
  void *page=(void*)((ULONG_PTR)hooks[i].slot&~((ULONG_PTR)info.dwPageSize-1));
  for(j=0;j<page_count && pages[j]!=page;j++);
  if(j==page_count)pages[page_count++]=page;
 }
 for(i=0;i<page_count;i++)if(!VirtualProtect(pages[i],info.dwPageSize,PAGE_READWRITE,&protections[i])) {
  DWORD ignored;while(i){--i;VirtualProtect(pages[i],info.dwPageSize,protections[i],&ignored);}return 0;
 }
 for(i=0;i<(unsigned)count;i++) {
  Hook *h=&hooks[i];
  if(install)InterlockedExchangePointer(h->slot,h->replacement);
  else InterlockedCompareExchangePointer(h->slot,h->original,h->replacement);
 }
 for(i=0;i<page_count;i++){DWORD ignored;VirtualProtect(pages[i],info.dwPageSize,protections[i],&ignored);}
 return 1;
}
static void unhook(void) {
 if(!hook_count)return;
 if(write_hooks(0,hook_count))hook_count=0;
}
static int rehook(void) {
 if(!write_hooks(1,7))return 0;
 hook_count=7;return 1;
}
static int hook_current(IDirect3DDevice9 *d) {
 int i;p.original=*d->lpVtbl;p.table=(IDirect3DDevice9Vtbl*)d->lpVtbl;
 #define HOOK(N,F) hooks[i++]=(Hook){(void**)&p.table->N,(void*)(F),(void*)p.original.N}
 i=0;HOOK(DrawPrimitive,draw);HOOK(DrawIndexedPrimitive,indexed);HOOK(DrawPrimitiveUP,draw_up);HOOK(DrawIndexedPrimitiveUP,indexed_up);
 HOOK(BeginStateBlock,begin_block);HOOK(EndStateBlock,end_block);HOOK(Release,release_device);
 #undef HOOK
 return rehook();
}
int sr3_pom_attach(IDirect3DDevice9 *d,const Sr3PomConfig *config) {
 D3DCAPS9 caps;
 if(!d || !config || !config->vs || !config->ps || !config->original_vs_hash || !config->original_ps_hash)return 0;
 if(p.device)return d==p.device;
 if(FAILED(IDirect3DDevice9_GetDeviceCaps(d,&caps)) || caps.VertexShaderVersion<D3DVS_VERSION(3,0) ||
    caps.PixelShaderVersion<D3DPS_VERSION(3,0))return 0;
 if(!++cache_generation)++cache_generation;
 memset(&p,0,sizeof(p));p.original=*d->lpVtbl;p.table=(IDirect3DDevice9Vtbl*)d->lpVtbl;p.config=*config;

 p.enabled=1;p.tenths=6;p.fps_tenths=-1;QueryPerformanceFrequency(&p.fps_frequency);
 p.anisotropy=(caps.TextureFilterCaps&D3DPTFILTERCAPS_MINFANISOTROPIC)?(caps.MaxAnisotropy<8?caps.MaxAnisotropy:8):1;
 if(!p.anisotropy)p.anisotropy=1;
 p.device=d;
 if(!hook_current(d)){p.device=0;return 0;}
 return 1;
}

#include "pom_overlay.h"
