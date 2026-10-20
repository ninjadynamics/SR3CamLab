/* Optional real-device smoke test; hidden 64x64 window, no game/assets. */
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <string.h>
#include "pom.h"
#include "pom_bytecode.h"
static void step(const char *s){puts(s);fflush(stdout);}
static LONG WINAPI fault(EXCEPTION_POINTERS *e){
 HMODULE m=0;char path[MAX_PATH]={0};GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,(LPCSTR)e->ExceptionRecord->ExceptionAddress,&m);GetModuleFileNameA(m,path,sizeof(path));
 printf("EXCEPTION %08lx at %p (%s + %lx), access=%lu address=%p\n",e->ExceptionRecord->ExceptionCode,e->ExceptionRecord->ExceptionAddress,path,(unsigned long)((ULONG_PTR)e->ExceptionRecord->ExceptionAddress-(ULONG_PTR)m),(unsigned long)e->ExceptionRecord->ExceptionInformation[0],(void*)e->ExceptionRecord->ExceptionInformation[1]);fflush(stdout);return EXCEPTION_CONTINUE_SEARCH;
}
static void *read_file(const char *path,UINT *size) {
 FILE *f=fopen(path,"rb");void *bytes;if(!f)return 0;fseek(f,0,SEEK_END);*size=(UINT)ftell(f);rewind(f);bytes=HeapAlloc(GetProcessHeap(),0,*size);if(!bytes || fread(bytes,1,*size,f)!=*size){fclose(f);return 0;}fclose(f);return bytes;
}
static int marked_draw(IDirect3DDevice9 *d) {
 unsigned long before=sr3_pom_stats().replaced;int enabled,gain;sr3_pom_controls(&enabled,&gain);
 UINT n;void *vcode=read_file("original-vs.bin",&n),*pcode=read_file("original-ps.bin",&n);IDirect3DVertexShader9 *vs=0,*savedvs=0;IDirect3DPixelShader9 *ps=0,*savedps=0;
 IDirect3DTexture9 *white=0,*normal=0;D3DLOCKED_RECT lock;IDirect3DVertexDeclaration9 *decl=0;HRESULT hr;UINT level;
 D3DVERTEXELEMENT9 elements[]={{0,0,D3DDECLTYPE_FLOAT4,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_POSITION,0},{0,16,D3DDECLTYPE_FLOAT3,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_NORMAL,0},{0,28,D3DDECLTYPE_FLOAT3,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_BINORMAL,0},{0,40,D3DDECLTYPE_FLOAT4,D3DDECLMETHOD_DEFAULT,D3DDECLUSAGE_TEXCOORD,0},D3DDECL_END()};
 float vertex[3][14]={{-1,-1,.5f,1,0,0,1,1,0,0,0,0,.5f,.5f},{-1,1,.5f,1,0,0,1,1,0,0,0,1,.5f,.5f},{1,-1,.5f,1,0,0,1,1,0,0,1,0,.5f,.5f}};
 float identity[16]={1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};float vc[28][4]={{0}},pc[32][4]={{0}};
 if(!vcode || !pcode)return 20;
 if(FAILED(IDirect3DDevice9_CreateVertexShader(d,vcode,&vs)) || FAILED(IDirect3DDevice9_CreatePixelShader(d,pcode,&ps)))return 21;
 HeapFree(GetProcessHeap(),0,vcode);HeapFree(GetProcessHeap(),0,pcode);
 if(FAILED(IDirect3DDevice9_CreateTexture(d,1,1,1,0,D3DFMT_A8R8G8B8,D3DPOOL_MANAGED,&white,0)))return 22;
 if(FAILED(IDirect3DTexture9_LockRect(white,0,&lock,0,0)))return 23;*(DWORD*)lock.pBits=0xffffffff;IDirect3DTexture9_UnlockRect(white,0);
 if(FAILED(IDirect3DDevice9_CreateTexture(d,256,256,0,0,D3DFMT_DXT5,D3DPOOL_MANAGED,&normal,0)))return 24;
 for(level=0;level<IDirect3DTexture9_GetLevelCount(normal);++level) {
  D3DSURFACE_DESC desc;UINT y,x;IDirect3DTexture9_GetLevelDesc(normal,level,&desc);if(FAILED(IDirect3DTexture9_LockRect(normal,level,&lock,0,0)))return 25;
  for(y=0;y<(desc.Height+3)/4;y++)for(x=0;x<(desc.Width+3)/4;x++){
   BYTE block[16]={200,40,0,0,0,0,0,0,0x1f,0x84,0x1e,0x84,0,0,0,0};memcpy((BYTE*)lock.pBits+y*lock.Pitch+x*16,block,16);
  }IDirect3DTexture9_UnlockRect(normal,level);
 }
 memcpy(vc,identity,sizeof(identity));memcpy(vc[8],identity,sizeof(identity));memcpy(vc[18],identity,sizeof(identity));vc[16][2]=2;vc[17][2]=1;vc[23][2]=1;vc[24][0]=vc[24][1]=vc[24][2]=vc[24][3]=1;vc[26][2]=vc[26][3]=1;
 pc[0][0]=pc[0][1]=pc[0][2]=.5f;pc[1][0]=pc[1][1]=pc[1][2]=.5f;pc[3][0]=1;pc[10][0]=pc[10][1]=.008f;pc[10][2]=SR3_POM_MARKER;pc[12][1]=.0001f;pc[12][2]=2;pc[31][0]=1;
 IDirect3DDevice9_SetVertexShaderConstantF(d,0,&vc[0][0],28);IDirect3DDevice9_SetPixelShaderConstantF(d,0,&pc[0][0],32);
 IDirect3DDevice9_CreateVertexDeclaration(d,elements,&decl);IDirect3DDevice9_SetVertexDeclaration(d,decl);IDirect3DDevice9_SetVertexShader(d,vs);IDirect3DDevice9_SetPixelShader(d,ps);
 IDirect3DDevice9_SetTexture(d,0,(IDirect3DBaseTexture9*)white);IDirect3DDevice9_SetTexture(d,1,(IDirect3DBaseTexture9*)normal);IDirect3DDevice9_SetTexture(d,3,(IDirect3DBaseTexture9*)white);IDirect3DDevice9_SetTexture(d,4,(IDirect3DBaseTexture9*)white);IDirect3DDevice9_SetTexture(d,5,(IDirect3DBaseTexture9*)white);
 IDirect3DDevice9_SetRenderState(d,D3DRS_CULLMODE,D3DCULL_NONE);
 IDirect3DDevice9_BeginScene(d);hr=IDirect3DDevice9_DrawPrimitiveUP(d,D3DPT_TRIANGLELIST,1,vertex,sizeof(vertex[0]));IDirect3DDevice9_EndScene(d);
 printf("Marked draw=%08lx replaced=%lu rejected=%lu failures=%lu\n",hr,sr3_pom_stats().replaced,sr3_pom_stats().rejected,sr3_pom_stats().failures);fflush(stdout);
 if(FAILED(hr) || sr3_pom_stats().replaced!=before+(enabled && gain>0?1:0) || sr3_pom_stats().restore_failures)return 26;
 IDirect3DDevice9_GetVertexShader(d,&savedvs);IDirect3DDevice9_GetPixelShader(d,&savedps);if(savedvs!=vs || savedps!=ps)return 27;
 IDirect3DVertexShader9_Release(savedvs);IDirect3DPixelShader9_Release(savedps);
 IDirect3DDevice9_SetVertexShader(d,0);IDirect3DDevice9_SetPixelShader(d,0);IDirect3DDevice9_SetVertexDeclaration(d,0);
 IDirect3DDevice9_SetTexture(d,0,0);IDirect3DDevice9_SetTexture(d,1,0);IDirect3DDevice9_SetTexture(d,3,0);IDirect3DDevice9_SetTexture(d,4,0);IDirect3DDevice9_SetTexture(d,5,0);
 IDirect3DVertexShader9_Release(vs);IDirect3DPixelShader9_Release(ps);IDirect3DVertexDeclaration9_Release(decl);IDirect3DTexture9_Release(white);IDirect3DTexture9_Release(normal);return 0;
}

int main(void){
 HMODULE lib;IDirect3D9 *(WINAPI *create)(UINT);IDirect3D9 *d3d;IDirect3DDevice9 *d=0;HWND w;D3DPRESENT_PARAMETERS pp={0};HRESULT hr;
 Sr3PomConfig cfg={sr3_pom_vs_code,sr3_pom_ps_code,sr3_pom_original_vs_hash,sr3_pom_original_ps_hash,SR3_POM_ORIGINAL_VS_SIZE,SR3_POM_ORIGINAL_PS_SIZE,0};
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);AddVectoredExceptionHandler(1,fault);
 w=CreateWindowExA(0,"STATIC","POM hidden smoke test",WS_POPUP,0,0,64,64,0,0,GetModuleHandleA(0),0);if(!w)return 2;
 lib=LoadLibraryA("d3d9.dll");if(!lib)return 3;create=(void*)GetProcAddress(lib,"Direct3DCreate9");d3d=create(D3D_SDK_VERSION);if(!d3d)return 4;
 pp.Windowed=TRUE;pp.SwapEffect=D3DSWAPEFFECT_DISCARD;pp.hDeviceWindow=w;pp.BackBufferWidth=pp.BackBufferHeight=64;pp.BackBufferFormat=D3DFMT_X8R8G8B8;pp.PresentationInterval=D3DPRESENT_INTERVAL_IMMEDIATE;
 hr=IDirect3D9_CreateDevice(d3d,0,D3DDEVTYPE_HAL,w,0x54,&pp,&d);printf("CreateDevice %08lx\n",hr);fflush(stdout);if(FAILED(hr))return 5;
 step("Attach");if(!sr3_pom_attach(d,&cfg))return 6;
 step("Clear");IDirect3DDevice9_Clear(d,0,0,D3DCLEAR_TARGET,0xff102030,1,0);
 step("BeginScene");IDirect3DDevice9_BeginScene(d);
 step("Fixed pipeline draw");{struct {float x,y,z,rhw;DWORD color;} v[3]={{0,0,0,1,0xffffffff},{32,0,0,1,0xffffffff},{0,32,0,1,0xffffffff}};IDirect3DDevice9_SetFVF(d,D3DFVF_XYZRHW|D3DFVF_DIFFUSE);IDirect3DDevice9_DrawPrimitiveUP(d,D3DPT_TRIANGLELIST,1,v,sizeof(v[0]));}
 step("EndScene");IDirect3DDevice9_EndScene(d);step("Present");IDirect3DDevice9_Present(d,0,0,0,0);
 step("Compile paired GPU shaders");{IDirect3DVertexShader9 *vs=0;IDirect3DPixelShader9 *ps=0;hr=IDirect3DDevice9_CreateVertexShader(d,sr3_pom_vs_code,&vs);printf("VS=%08lx\n",hr);if(FAILED(hr))return 7;hr=IDirect3DDevice9_CreatePixelShader(d,sr3_pom_ps_code,&ps);printf("PS=%08lx\n",hr);if(FAILED(hr))return 8;IDirect3DVertexShader9_Release(vs);IDirect3DPixelShader9_Release(ps);}
 step("Actual marked POM draw");{int code=marked_draw(d);if(code)return code;}
 step("Real state-block recording and replay");{
  IDirect3DStateBlock9 *block=0;void *before=(void*)d->lpVtbl->DrawPrimitiveUP;
  printf("Before state block: table=%p draw=%p end=%p\n",d->lpVtbl,(void*)d->lpVtbl->DrawPrimitiveUP,(void*)d->lpVtbl->EndStateBlock);
  hr=IDirect3DDevice9_BeginStateBlock(d);printf("Begin=%08lx table=%p draw=%p end=%p\n",hr,d->lpVtbl,(void*)d->lpVtbl->DrawPrimitiveUP,(void*)d->lpVtbl->EndStateBlock);
  IDirect3DDevice9_SetRenderState(d,D3DRS_ZENABLE,FALSE);hr=IDirect3DDevice9_EndStateBlock(d,&block);
  printf("End=%08lx table=%p draw=%p before=%p\n",hr,d->lpVtbl,(void*)d->lpVtbl->DrawPrimitiveUP,before);fflush(stdout);
  if(block){IDirect3DStateBlock9_Apply(block);IDirect3DStateBlock9_Release(block);}
  {int code=marked_draw(d);if(code)return code;}
 }
 step("Complete state snapshot/capture/apply");{
  IDirect3DStateBlock9 *block=0;
  if(FAILED(IDirect3DDevice9_CreateStateBlock(d,D3DSBT_ALL,&block)))return 29;
  if(FAILED(IDirect3DStateBlock9_Capture(block)) || FAILED(IDirect3DStateBlock9_Apply(block)))return 30;
  IDirect3DStateBlock9_Release(block);
  {int code=marked_draw(d);if(code)return code;}
 }
 step("Live controls and HUD restoration");{int e,n,i;sr3_pom_adjust(0);sr3_pom_adjust(1);sr3_pom_controls(&e,&n);if(e || n!=7)return 31;
  sr3_pom_overlay(d);{int code=marked_draw(d);if(code)return code;}
  sr3_pom_adjust(0);for(i=0;i<4;i++)sr3_pom_adjust(1);sr3_pom_overlay(d);
  {int code=marked_draw(d);if(code)return code;}
 }
 step("HUD with offscreen post-process target bound");{
  IDirect3DSurface9 *back=0,*offscreen=0,*after=0;
  if(FAILED(IDirect3DDevice9_GetRenderTarget(d,0,&back)) || FAILED(IDirect3DDevice9_CreateRenderTarget(d,64,64,D3DFMT_X8R8G8B8,D3DMULTISAMPLE_NONE,0,FALSE,&offscreen,0)))return 32;
  IDirect3DDevice9_SetRenderTarget(d,0,offscreen);sr3_pom_overlay(d);IDirect3DDevice9_GetRenderTarget(d,0,&after);
  if(after!=offscreen || sr3_pom_stats().restore_failures)return 33;
  IDirect3DSurface9_Release(after);IDirect3DDevice9_SetRenderTarget(d,0,back);IDirect3DSurface9_Release(offscreen);IDirect3DSurface9_Release(back);
 }
 step("Non-final Release and redraw");IDirect3DDevice9_AddRef(d);if(!IDirect3DDevice9_Release(d))return 28;{int code=marked_draw(d);if(code)return code;}
 step("Reset");sr3_pom_before_reset(d);hr=IDirect3DDevice9_Reset(d,&pp);printf("Reset=%08lx\n",hr);if(FAILED(hr))return 40;
 step("Recreate after Reset");{int code=marked_draw(d);if(code)return code;}
 step("Release");{ULONG left=IDirect3DDevice9_Release(d);printf("Device references after final Release: %lu\n",left);if(left)return 41;}if(IDirect3D9_Release(d3d))return 42;DestroyWindow(w);FreeLibrary(lib);step("PASS real-device smoke");return 0;
}
