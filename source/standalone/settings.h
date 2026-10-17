/* SR3Lab settings shared by the DLL, launcher and companion. MIT. */
#ifndef SR3_SETTINGS_H
#define SR3_SETTINGS_H
#include <stddef.h>
#define SR3_PATH 1024
#define SR3_PATCH_FIELDS 9
typedef struct {
    int version;
    char game_path[SR3_PATH];
    int width, height, windowed, hud_adjust, vsync, refresh_rate;
    int freeplay, language, music, sfx, voice, attract_music;
    int controller, deadzone, threshold, background, steering, invert, gas, brake;
    int start, view, handbrake, up, down, coin, dpad, curve, cores;
    /* Empty slots mean omitted. Preserve plugin scalars through companion saves;
       sr3mods.dll owns their semantics, except enabled (auto/on/off) below. */
    char patches[SR3_PATCH_FIELDS][SR3_PATH];
    unsigned patches_present;
} Sr3Settings;
typedef struct {
    const char *section, *key, *label;
    size_t offset;
    int min, max, initial, step;
    const char *const *choices;
} Sr3Field;
extern const Sr3Field sr3_fields[];
extern const int sr3_field_count;
extern const char *const sr3_buttons[];
extern const char *const sr3_axes[];
extern const char *const sr3_languages[];
extern const char *const sr3_patch_keys[SR3_PATCH_FIELDS];
const char *sr3_patch_value(const Sr3Settings *s, const char *key);
void sr3_defaults(Sr3Settings *s);
/* Strict two-level scalar YAML schema: rejects unknown/duplicate keys and invalid values. */
int sr3_load(const char *path, Sr3Settings *s, char *error, size_t cap);
/* Plugin ABI helper: strict UTF-8 filename, opened with the wide Windows API. */
int sr3_load_utf8(const char *path, Sr3Settings *s, char *error, size_t cap);
int sr3_save(const char *path, const Sr3Settings *s, char *error, size_t cap);
int sr3_validate(const Sr3Settings *s, char *error, size_t cap);
int *sr3_value(Sr3Settings *s, int field);
unsigned long sr3_fingerprint(const char *path);
#endif
