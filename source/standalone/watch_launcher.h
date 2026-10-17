/* External recorder host, shared by the two patch fronts. MIT. */
#pragma once
#include <windows.h>
#include <stddef.h>
/* Success means running/already owned; attachment is confirmed in the host log. */
int sr3_watch_start(HANDLE game, const char *absolute_mod_utf8, char *error, size_t cap);
/* The host creates the game suspended, attaches, then resumes it. */
int sr3_watch_launch(const char *exe_utf8, const char *yaml_utf8, const char *mod_utf8, char *error, size_t cap);
void sr3_watch_poll(void (*log)(const char *));
/* Drain after game exit; never terminate a recorder still finishing its dump. */
void sr3_watch_finish(void (*log)(const char *));
