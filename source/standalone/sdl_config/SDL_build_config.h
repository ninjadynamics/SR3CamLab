/* SR3Lab's SDL 3.4.16 configuration, based on SDL's supported Windows header.
 * This wrapper is ours (MIT); the included upstream header keeps its license.
 * No configure/CMake-generated files or local SDK feature probes are needed.
 */
#ifndef SDL_build_config_h_
#include <SDL_build_config_windows.h>

#define SDL_AUDIO_DISABLED 1
#define SDL_VIDEO_DISABLED 1
#define SDL_RENDER_DISABLED 1
#define SDL_GPU_DISABLED 1
#define SDL_CAMERA_DISABLED 1

#undef SDL_AUDIO_DRIVER_WASAPI
#undef SDL_AUDIO_DRIVER_DSOUND
#undef SDL_AUDIO_DRIVER_DISK
#undef SDL_VIDEO_DRIVER_WINDOWS
#undef SDL_VIDEO_DRIVER_OFFSCREEN
#undef SDL_VIDEO_OPENGL
#undef SDL_VIDEO_OPENGL_WGL
#undef SDL_VIDEO_OPENGL_ES2
#undef SDL_VIDEO_OPENGL_EGL
#undef SDL_VIDEO_VULKAN
#undef SDL_VIDEO_RENDER_D3D
#undef SDL_VIDEO_RENDER_D3D11
#undef SDL_VIDEO_RENDER_D3D12
#undef SDL_VIDEO_RENDER_OGL
#undef SDL_VIDEO_RENDER_OGL_ES2
#undef SDL_VIDEO_RENDER_VULKAN
#undef SDL_VIDEO_RENDER_GPU
#undef SDL_GPU_D3D11
#undef SDL_GPU_D3D12
#undef SDL_GPU_VULKAN
#undef SDL_CAMERA_DRIVER_MEDIAFOUNDATION
/* GameInput is an optional C++ backend; HIDAPI, XInput, RawInput, DirectInput
 * and WGI cover the controllers here without another compiler frontend. */
#undef HAVE_GAMEINPUT_H
#undef SDL_JOYSTICK_GAMEINPUT

/* UCRT x86 exports double math functions; SDL supplies float fallbacks.
 * Do not import nonexistent float entry points from the OS DLL. */
#undef HAVE_ACOSF
#undef HAVE_ASINF
#undef HAVE_ATANF
#undef HAVE_ATAN2F
#undef HAVE_CEILF
#undef HAVE_COSF
#undef HAVE_FLOORF
#undef HAVE_FMODF
#undef HAVE_LOGF
#undef HAVE_LOG10F
#undef HAVE_MODFF
#undef HAVE_SINF
#undef HAVE_SQRTF
#undef HAVE_TANF

/* Present in the Windows 10 UCRT; no MinGW compatibility libraries needed. */
#define HAVE_STRTOLL 1
#define HAVE_STRTOULL 1
#define HAVE_VSSCANF 1
#define HAVE_LROUND 1
#define HAVE_LROUNDF 1
#define HAVE_ROUND 1
#define HAVE_ROUNDF 1
#define HAVE_SCALBN 1
#define HAVE_SCALBNF 1
#define HAVE_TRUNC 1
#define HAVE_TRUNCF 1
#define HAVE__FSEEKI64 1
#endif
