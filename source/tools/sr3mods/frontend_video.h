#pragma once
typedef struct GameMem GameMem;
/* Native-only frontend extension. All decoder/texture operations run on the
 * game thread. The old GameMem clients retain their virtual 20-record view. */
int fe_video_install(GameMem *memory);
unsigned fe_video_memory_address(unsigned address,unsigned size);
int fe_video_adjust_camera(const void *source,unsigned size,void *destination);
void fe_video_ready(void);
void fe_video_tick(void);
void fe_video_menu(const int *handles, unsigned count);
int fe_video_register(const char *path);
void *fe_video_texture(int handle);
void fe_video_reset(void);
/* Open frontend preview decoders; nonzero keeps the release sweep running. */
int fe_video_open(void);
/* Milliseconds since the race loading animation was last drawn (~0 if never). */
unsigned fe_video_loading_age(void);
int fe_video_hooked(void);
