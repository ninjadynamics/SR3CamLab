/* Screenshot bridge between the mod worker and the game's render thread. MIT. */
#ifndef SR3_CAPTURE_H
#define SR3_CAPTURE_H
#ifndef COBJMACROS
#define COBJMACROS
#endif
#include <windows.h>
#include <d3d9.h>

/* Worker-thread API: waits at most 2000 ms for the next Present/readback.
   Returns 1 with top-down, tightly packed BGRA8 (opaque alpha), or 0 with all
   supplied outputs cleared and GetLastError set. Caller frees pixels with
   HeapFree(GetProcessHeap(), 0, pixels). Never call from the rendering thread.
   No D3D surface/device survives the serviced request, including across Reset. */
int __cdecl sr3rt_grab_backbuffer(void **bgra, int *width, int *height);
void sr3_capture_enable(void);
/* Optional request-only diagnostic; stage 0 queued, 1 claimed, 2 described,
   3 readback started, 4 readback complete, 5 pixels copied. */
void sr3_capture_set_log(void (*fn)(DWORD error, DWORD elapsed, LONG stage));
void sr3_capture_present(IDirect3DDevice9 *device);
void sr3_capture_frame_hook(void);
#endif
