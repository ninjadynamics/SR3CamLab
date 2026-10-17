/* Optional sr3mods.dll boundary; call after startup, never from DllMain. MIT. */
#ifndef SR3_PATCH_LOADER_H
#define SR3_PATCH_LOADER_H
#include <windows.h>
#include <stddef.h>
/* mode: 0 auto, 1 required, 2 disabled. Return 1 started, 0 skipped, -1 failed.
   The caller owns once-only dispatch. A loaded module stays loaded for life. */
int sr3_load_patches(HMODULE owner,const char *settings_path_acp,int mode,char *error,size_t cap);
#endif
