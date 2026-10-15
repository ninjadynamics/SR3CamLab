#ifndef SR3_LAUNCH_H
#define SR3_LAUNCH_H
#include "settings.h"
int sr3_settings_path(char *path,size_t cap);
int sr3_launch(const char *yaml,const Sr3Settings *s,char *error,size_t cap);
/* -1 follows patches.watchdog (default on), 0 off, 1 explicit watched launch. */
int sr3_launch_mode(const char *yaml,const Sr3Settings *s,int watch,char *error,size_t cap);
#endif
