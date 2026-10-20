#ifndef SR3_POM_NATIVE_H
#define SR3_POM_NATIVE_H
#include <windows.h>
#include <d3d9.h>
void sr3_pom_native_init(int enabled);
int sr3_pom_native_configure(const char *yaml_path);
int sr3_pom_native_adjust(int delta);
void sr3_pom_native_controls(int *enabled,int *tenths);
void sr3_pom_native_frame(IDirect3DDevice9 *device);
void sr3_pom_native_reset(void);
int sr3_pom_native_applied(void);
#endif
