#ifndef SR3_POM_H
#define SR3_POM_H
#include <windows.h>
#include <d3d9.h>
/* Reserved gf3ReflCol.z value; x/y are bounded UV depth, not metres. */
#define SR3_POM_MARKER (1.0f/1024.0f)
typedef struct Sr3PomConfig {
 const DWORD *vs, *ps;
 const BYTE *original_vs_hash, *original_ps_hash;
 UINT original_vs_size, original_ps_size;
 void (*notify)(int event); /* optional, once per event: 1 active, 2 identity, 3 map, 4 setup, 5 restore */
} Sr3PomConfig;
typedef struct Sr3PomStats { double identify_ms,build_ms,cleanup_ms; unsigned long resource_clears,pair_misses,map_misses,shader_builds; unsigned long draws, candidates, replaced, rejected, failures, restore_failures, hud_calls, hud_draws, hud_stage; HRESULT hud_error; int fps_tenths,global_tenths,pom_enabled; } Sr3PomStats;
/* Render thread only; one game device. Disabled unless runtime explicitly calls attach. */
int sr3_pom_attach(IDirect3DDevice9 *device,const Sr3PomConfig *config);
void sr3_pom_before_reset(IDirect3DDevice9 *device);
Sr3PomStats sr3_pom_stats(void);
/* Window-thread controls only change atomic integers; D3D stays on render thread. */
int sr3_pom_adjust(int delta); /* 0 toggle internally, +/-1 global gain in 0.1 steps, clamped 0..1 */
void sr3_pom_controls(int *enabled,int *tenths);
void sr3_pom_overlay(IDirect3DDevice9 *device);
#endif
