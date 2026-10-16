/* One-shot D3D9 readback. No encoder, per-frame allocation, or GPU work unless
   requested. Only the Present thread touches D3D. MIT. */
#define WIN32_LEAN_AND_MEAN
#include "capture.h"
#include <stdint.h>
#include <string.h>
#ifndef SR3_CAPTURE_WAIT_MS
#define SR3_CAPTURE_WAIT_MS 2000
#endif

typedef struct CaptureRequest {
    volatile LONG refs;
    HANDLE done;
    void *pixels;
    int width, height;
    DWORD error;
    volatile LONG stage;
} CaptureRequest;
static PVOID volatile pendingCapture;
static volatile LONG captureEnabled;
static void (*captureLog)(DWORD, DWORD, LONG);
void sr3_capture_set_log(void (*fn)(DWORD, DWORD, LONG)) { captureLog = fn; }

static void releaseRequest(CaptureRequest *r) {
    if (!InterlockedDecrement(&r->refs)) {
        if (r->pixels) HeapFree(GetProcessHeap(), 0, r->pixels);
        CloseHandle(r->done);
        HeapFree(GetProcessHeap(), 0, r);
    }
}
void sr3_capture_enable(void) { InterlockedExchange(&captureEnabled, 1); }

int __cdecl sr3rt_grab_backbuffer(void **bgra, int *width, int *height) {
    CaptureRequest *r; DWORD error, waited, started; int ok = 0;
    if (bgra) *bgra = NULL;
    if (width) *width = 0;
    if (height) *height = 0;
    if (!bgra || !width || !height) { SetLastError(ERROR_INVALID_PARAMETER); return 0; }
    if (!InterlockedCompareExchange(&captureEnabled, 0, 0)) { SetLastError(ERROR_NOT_READY); return 0; }
    r = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*r));
    if (!r) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    r->done = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!r->done) { error = GetLastError(); HeapFree(GetProcessHeap(), 0, r); SetLastError(error); return 0; }
    r->refs = 2; /* Caller + queued request (transferred to the Present thread). */
    if (InterlockedCompareExchangePointer(&pendingCapture, r, NULL)) {
        releaseRequest(r); releaseRequest(r); SetLastError(ERROR_BUSY); return 0;
    }
    started = GetTickCount();
    waited = WaitForSingleObject(r->done, SR3_CAPTURE_WAIT_MS);
    if (waited == WAIT_OBJECT_0) {
        error = r->error;
        if (!error) {
            *bgra = r->pixels; *width = r->width; *height = r->height;
            r->pixels = NULL; ok = 1;
        }
    } else {
        error = waited == WAIT_TIMEOUT ? ERROR_TIMEOUT : GetLastError();
        /* Cancel only if Present has not claimed it. Otherwise that thread
           retains its reference and cleans up even after this caller returns. */
        if (InterlockedCompareExchangePointer(&pendingCapture, NULL, r) == r) releaseRequest(r);
    }
    if (captureLog) captureLog(error, GetTickCount() - started, InterlockedCompareExchange(&r->stage, 0, 0));
    releaseRequest(r); SetLastError(error); return ok;
}

static DWORD readBackbuffer(IDirect3DDevice9 *device, CaptureRequest *r) {
    IDirect3DSurface9 *back = NULL, *resolved = NULL, *system = NULL, *source;
    D3DSURFACE_DESC desc; D3DLOCKED_RECT locked;
    SIZE_T stride, bytes; UINT y, x; DWORD error = ERROR_READ_FAULT;
    int isLocked = 0;
    if (!device || FAILED(IDirect3DDevice9_GetBackBuffer(device, 0, 0, D3DBACKBUFFER_TYPE_MONO, &back))) goto done;
    if (FAILED(IDirect3DSurface9_GetDesc(back, &desc))) goto done;
    if (desc.Format != D3DFMT_A8R8G8B8 && desc.Format != D3DFMT_X8R8G8B8) { error = ERROR_NOT_SUPPORTED; goto done; }
    if (!desc.Width || !desc.Height || desc.Width > 16384 || desc.Height > 16384) { error = ERROR_INVALID_DATA; goto done; }
    stride = (SIZE_T)desc.Width * 4; bytes = stride * desc.Height;
    if (bytes > 256u * 1024u * 1024u) { error = ERROR_NOT_ENOUGH_MEMORY; goto done; }
    InterlockedExchange(&r->stage, 2);
    source = back;
    if (desc.MultiSampleType != D3DMULTISAMPLE_NONE) {
        if (FAILED(IDirect3DDevice9_CreateRenderTarget(device, desc.Width, desc.Height, desc.Format,
            D3DMULTISAMPLE_NONE, 0, FALSE, &resolved, NULL))) goto done;
        if (FAILED(IDirect3DDevice9_StretchRect(device, back, NULL, resolved, NULL, D3DTEXF_NONE))) goto done;
        source = resolved;
    }
    if (FAILED(IDirect3DDevice9_CreateOffscreenPlainSurface(device, desc.Width, desc.Height,
        desc.Format, D3DPOOL_SYSTEMMEM, &system, NULL))) goto done;
    InterlockedExchange(&r->stage, 3);
    if (FAILED(IDirect3DDevice9_GetRenderTargetData(device, source, system))) goto done;
    InterlockedExchange(&r->stage, 4);
    if (FAILED(IDirect3DSurface9_LockRect(system, &locked, NULL, D3DLOCK_READONLY))) goto done;
    isLocked = 1;
    if (!locked.pBits || (int64_t)locked.Pitch < (int64_t)stride) { error = ERROR_INVALID_DATA; goto done; }
    r->pixels = HeapAlloc(GetProcessHeap(), 0, bytes);
    if (!r->pixels) { error = ERROR_NOT_ENOUGH_MEMORY; goto done; }
    for (y = 0; y < desc.Height; y++) {
        unsigned char *to = (unsigned char *)r->pixels + y * stride;
        memcpy(to, (const unsigned char *)locked.pBits + (SIZE_T)y * locked.Pitch, stride);
        for (x = 0; x < desc.Width; x++) to[x * 4 + 3] = 255;
    }
    InterlockedExchange(&r->stage, 5);
    r->width = (int)desc.Width; r->height = (int)desc.Height; error = ERROR_SUCCESS;
done:
    if (isLocked && FAILED(IDirect3DSurface9_UnlockRect(system))) error = ERROR_READ_FAULT;
    if (system) IDirect3DSurface9_Release(system);
    if (resolved) IDirect3DSurface9_Release(resolved);
    if (back) IDirect3DSurface9_Release(back);
    return error;
}
void sr3_capture_present(IDirect3DDevice9 *device) {
    CaptureRequest *r;
    /* The ordinary frame pays one pointer load and branch, no locked operation. */
    if (!pendingCapture) return;
    r = InterlockedExchangePointer(&pendingCapture, NULL);
    if (!r) return;
    InterlockedExchange(&r->stage, 1);
    r->error = readBackbuffer(device, r);
    SetEvent(r->done);
    releaseRequest(r);
}

/* Replaces MOV EAX,[7ED10C] after EndScene, before Present. Preserve the
   original instruction contract, including flags and floating-point state.
   No COM objects are retained, and the game still invokes its current Present.
   Private fixed-address device storage is supplied by the native mock test. */
#if defined(__GNUC__) && defined(__i386__)
__attribute__((naked)) void sr3_capture_frame_hook(void) {
    __asm__("pushfl\n\tcmpl $0,_pendingCapture\n\tje 1f\n\tpushal\n\t"
            "movl %esp,%ebp\n\tsubl $528,%esp\n\tandl $-16,%esp\n\t"
            "fxsave (%esp)\n\tsubl $16,%esp\n\t"
            "movl 0x7ed10c,%eax\n\tmovl %eax,(%esp)\n\t"
            "call _sr3_capture_present\n\t"
            "addl $16,%esp\n\tfxrstor (%esp)\n\t"
            "movl %ebp,%esp\n\tpopal\n\t1: popfl\n\t"
            "movl 0x7ed10c,%eax\n\tret");
}
#else
#error Screenshot frame hook requires the supported x86 GCC build.
#endif
