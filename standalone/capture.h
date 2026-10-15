/* Screenshot bridge between the mod worker and the game's render thread. MIT. */
#ifndef SR3_CAPTURE_H
#define SR3_CAPTURE_H
#ifndef COBJMACROS
#define COBJMACROS
#endif
#include <windows.h>
#include <d3d9.h>

/* Worker-thread API: waits at most 250 ms for the next Present/readback.
   Returns 1 with top-down, tightly packed BGRA8 (opaque alpha), or 0 with all
   supplied outputs cleared and GetLastError set. Caller frees pixels with
   HeapFree(GetProcessHeap(), 0, pixels). Never call from the rendering thread.
   No D3D surface/device survives the serviced request, including across Reset. */
int __cdecl sr3rt_grab_backbuffer(void **bgra, int *width, int *height);
void sr3_capture_enable(void);
void sr3_capture_present(IDirect3DDevice9 *device);
#endif
