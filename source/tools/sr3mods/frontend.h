#pragma once
#include "patchcore.h"
#include "input.h"
int fe_install(GameMem *,const char *mod);
int fe_input(const Sr3Input *);
void fe_key(unsigned key);
int fe_frame(void *device);
void fe_reset(void);
