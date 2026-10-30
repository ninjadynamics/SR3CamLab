#pragma once
#include "patchcore.h"
#include "frontend_model.h"
int fe_native_install(GameMem *,const FeCatalog *);
int fe_native_view(const FeMenu *);
void fe_native_cursor(int cursor,int direction);
int fe_native_busy(void);
int fe_native_blocked(void);
void fe_native_activate(void);
void fe_native_leave(void);
void fe_native_detach_view(void);
