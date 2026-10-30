#pragma once
void pc_frontend_enable(void);
int pc_frontend_enabled(void);
unsigned pc_frontend_select(int native_id,char directory);
int pc_frontend_status(unsigned request);
void pc_frontend_cancel(void);
