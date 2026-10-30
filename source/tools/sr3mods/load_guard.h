#pragma once
/* Race-load and exit guard (load_guard.c). Starts its own thread; dumps go to
 * the given folder, beside sr3mods.log. SR3LAB_GUARD=0 leaves it off. */
void lg_start(const char *folder);
