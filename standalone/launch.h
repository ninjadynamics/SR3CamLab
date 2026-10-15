#ifndef SR3_LAUNCH_H
#define SR3_LAUNCH_H
#include "settings.h"
#include <wchar.h>
typedef struct {
    char settings[SR3_PATH], preview[SR3_PATH];
    int watchdog, preview_tab;
} Sr3LaunchOptions;
int sr3_parse_options(const wchar_t *command,int companion,Sr3LaunchOptions *out,char *error,size_t cap);
int sr3_current_options(int companion,Sr3LaunchOptions *out,char *error,size_t cap);
void sr3_option_error(const char *error);
int sr3_settings_path(char *path,size_t cap);
int sr3_launch(const char *yaml,const Sr3Settings *s,char *error,size_t cap);
/* -1 follows patches.watchdog (default on), 0 off, 1 explicit watched launch. */
int sr3_launch_mode(const char *yaml,const Sr3Settings *s,int watch,char *error,size_t cap);
#endif
