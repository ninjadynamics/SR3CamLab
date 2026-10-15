/* Real worker/event lifetimes, fake D3D COM objects: never opens a GPU/device. */
#include <stdio.h>
#include "capture.c"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FAIL capture line %d: %s\n",__LINE__,#x); ExitProcess(1); } } while(0)
typedef struct FakeSurface { IDirect3DSurface9 com; LONG refs; } FakeSurface;
static IDirect3DDevice9 device;
static IDirect3DDevice9Vtbl deviceVtbl;
static IDirect3DSurface9Vtbl surfaceVtbl;
static FakeSurface back, resolved, systemSurface;
static int failAt, useMsaa, wrongFormat, badPitch, calls, resolvedCopies;
static DWORD renderThread;
static HANDLE copyEntered, copyGate;
static unsigned char sample[24] = {1,2,3,4,5,6,7,8,99,99,99,99,9,10,11,12,13,14,15,16,99,99,99,99};
static void onRender(void) { CHECK(GetCurrentThreadId() == renderThread); calls++; }
static ULONG WINAPI releaseSurface(IDirect3DSurface9 *self) { FakeSurface *s=(FakeSurface*)self; onRender(); CHECK(s->refs>0); return --s->refs; }
static HRESULT WINAPI getDesc(IDirect3DSurface9 *self,D3DSURFACE_DESC *out) {
    (void)self; onRender(); if(failAt==2)return E_FAIL;
    memset(out,0,sizeof(*out));out->Width=2;out->Height=2;
    out->Format=wrongFormat?D3DFMT_R5G6B5:D3DFMT_X8R8G8B8;
    out->MultiSampleType=useMsaa?D3DMULTISAMPLE_4_SAMPLES:D3DMULTISAMPLE_NONE;return S_OK;
}
static HRESULT WINAPI lockSurface(IDirect3DSurface9 *self,D3DLOCKED_RECT *out,const RECT *rect,DWORD flags) {
    onRender();CHECK(self==&systemSurface.com && !rect && flags==D3DLOCK_READONLY);
    if(failAt==7)return E_FAIL;out->pBits=sample;out->Pitch=badPitch?4:12;return S_OK;
}
static HRESULT WINAPI unlockSurface(IDirect3DSurface9 *self) {onRender();CHECK(self==&systemSurface.com);return failAt==8?E_FAIL:S_OK;}
static HRESULT WINAPI getBack(IDirect3DDevice9 *self,UINT chain,UINT index,D3DBACKBUFFER_TYPE type,IDirect3DSurface9 **out) {
    onRender();CHECK(self==&device && !chain && !index && type==D3DBACKBUFFER_TYPE_MONO);
    if(failAt==1)return D3DERR_DEVICELOST;back.refs++;*out=&back.com;return S_OK;
}
static HRESULT WINAPI createTarget(IDirect3DDevice9 *self,UINT w,UINT h,D3DFORMAT format,D3DMULTISAMPLE_TYPE ms,DWORD quality,BOOL lockable,IDirect3DSurface9 **out,HANDLE *shared) {
    onRender();CHECK(self==&device && w==2 && h==2 && format==D3DFMT_X8R8G8B8 && ms==D3DMULTISAMPLE_NONE && !quality && !lockable && !shared);
    if(failAt==3)return E_FAIL;resolved.refs++;*out=&resolved.com;return S_OK;
}
static HRESULT WINAPI stretch(IDirect3DDevice9 *self,IDirect3DSurface9 *src,const RECT *sr,IDirect3DSurface9 *dst,const RECT *dr,D3DTEXTUREFILTERTYPE filter) {
    onRender();CHECK(self==&device && src==&back.com && dst==&resolved.com && !sr && !dr && filter==D3DTEXF_NONE);
    resolvedCopies++;return failAt==4?E_FAIL:S_OK;
}
static HRESULT WINAPI createSystem(IDirect3DDevice9 *self,UINT w,UINT h,D3DFORMAT format,D3DPOOL pool,IDirect3DSurface9 **out,HANDLE *shared) {
    onRender();CHECK(self==&device && w==2 && h==2 && format==D3DFMT_X8R8G8B8 && pool==D3DPOOL_SYSTEMMEM && !shared);
    if(failAt==5)return E_FAIL;systemSurface.refs++;*out=&systemSurface.com;return S_OK;
}
static HRESULT WINAPI readTarget(IDirect3DDevice9 *self,IDirect3DSurface9 *src,IDirect3DSurface9 *dst) {
    onRender();CHECK(self==&device && src==(useMsaa?&resolved.com:&back.com) && dst==&systemSurface.com);
    if(copyGate){SetEvent(copyEntered);CHECK(WaitForSingleObject(copyGate,2000)==WAIT_OBJECT_0);}
    return failAt==6?D3DERR_DEVICELOST:S_OK;
}
typedef struct Result {void *pixels;int w,h,ok;DWORD error;} Result;
static DWORD WINAPI grab(void *arg) {
    Result *r=arg;r->pixels=(void*)1;r->w=r->h=99;
    r->ok=sr3rt_grab_backbuffer(&r->pixels,&r->w,&r->h);r->error=GetLastError();return 0;
}
static void waitQueued(void) {
    DWORD start=GetTickCount();while(!pendingCapture){CHECK(GetTickCount()-start<1000);Sleep(1);}
}
static void join(HANDLE thread) {CHECK(WaitForSingleObject(thread,2000)==WAIT_OBJECT_0);CloseHandle(thread);}
static void clean(void) {CHECK(back.refs==1 && !resolved.refs && !systemSurface.refs && !pendingCapture);}
static Result serviced(void) {
    Result r={0};HANDLE thread=CreateThread(NULL,0,grab,&r,0,NULL);CHECK(thread);waitQueued();
    renderThread=GetCurrentThreadId();sr3_capture_present(&device);join(thread);clean();return r;
}
static void failed(Result r) {CHECK(!r.ok && !r.pixels && !r.w && !r.h && r.error);}
static void valid(Result r) {
    static const unsigned char expected[]={1,2,3,255,5,6,7,255,9,10,11,255,13,14,15,255};
    CHECK(r.ok && r.w==2 && r.h==2 && !r.error && !memcmp(r.pixels,expected,sizeof(expected)));
    CHECK(HeapFree(GetProcessHeap(),0,r.pixels));
}
static DWORD WINAPI presentThread(void *unused) {(void)unused;renderThread=GetCurrentThreadId();sr3_capture_present(&device);return 0;}
int main(void) {
    Result r={0},other={0};HANDLE worker,renderer;int i,before;
    device.lpVtbl=&deviceVtbl;back.com.lpVtbl=resolved.com.lpVtbl=systemSurface.com.lpVtbl=&surfaceVtbl;back.refs=1;
    surfaceVtbl.Release=releaseSurface;surfaceVtbl.GetDesc=getDesc;surfaceVtbl.LockRect=lockSurface;surfaceVtbl.UnlockRect=unlockSurface;
    deviceVtbl.GetBackBuffer=getBack;deviceVtbl.CreateRenderTarget=createTarget;deviceVtbl.StretchRect=stretch;
    deviceVtbl.CreateOffscreenPlainSurface=createSystem;deviceVtbl.GetRenderTargetData=readTarget;
    grab(&r);failed(r);CHECK(r.error==ERROR_NOT_READY);
    CHECK(!sr3rt_grab_backbuffer(NULL,&r.w,&r.h) && GetLastError()==ERROR_INVALID_PARAMETER && !r.w && !r.h);
    sr3_capture_enable();before=calls;sr3_capture_present(&device);CHECK(calls==before);
    valid(serviced());useMsaa=1;valid(serviced());CHECK(resolvedCopies==1);
    for(i=1;i<=8;i++){failAt=i;failed(serviced());}failAt=0;useMsaa=0;
    wrongFormat=1;failed(serviced());wrongFormat=0;badPitch=1;failed(serviced());badPitch=0;
    /* No frame: bounded timeout cancels the queued request; busy is immediate. */
    worker=CreateThread(NULL,0,grab,&r,0,NULL);CHECK(worker);waitQueued();grab(&other);failed(other);CHECK(other.error==ERROR_BUSY);
    join(worker);failed(r);CHECK(r.error==ERROR_TIMEOUT);clean();before=calls;sr3_capture_present(&device);CHECK(calls==before);
    /* Caller can time out while readback is in flight. The render thread owns
       its own request/event lifetime, cleans up afterwards, and accepts reuse. */
    copyEntered=CreateEventW(NULL,TRUE,FALSE,NULL);copyGate=CreateEventW(NULL,TRUE,FALSE,NULL);CHECK(copyEntered && copyGate);
    worker=CreateThread(NULL,0,grab,&r,0,NULL);CHECK(worker);waitQueued();renderer=CreateThread(NULL,0,presentThread,NULL,0,NULL);CHECK(renderer);
    CHECK(WaitForSingleObject(copyEntered,1000)==WAIT_OBJECT_0);join(worker);failed(r);CHECK(r.error==ERROR_TIMEOUT);
    SetEvent(copyGate);join(renderer);CloseHandle(copyEntered);CloseHandle(copyGate);copyGate=NULL;clean();valid(serviced());
    puts("Capture: padded BGRA, MSAA resolve, COM failures, busy, queued/in-flight timeout and cleanup PASS (mock D3D, no GPU)");return 0;
}
