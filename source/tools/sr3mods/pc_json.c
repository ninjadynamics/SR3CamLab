/* pc_json: see pc_json.h. A recursive descent over the text, one allocation per value.
 * This can actually be done with a library (cJSON, jsmn, yyjson) the following way:
 *     cJSON *v = cJSON_Parse(text); cJSON *s = cJSON_GetObjectItemCaseSensitive(v, "slots");
 * It's done this way because the files are a few KB read once per race, a vendored library would be ten times this
 * file, and none of them looks keys up case-insensitively as PowerShell does (pj_get), which sr3mods.ps1 relies on. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_json.h"
#define DIGITS(q) ((q) >= '0' && (q) <= '9')

typedef struct { const char *p, *start; char *err; int cap; } St;
static void ws(St *s) { while (*s->p == ' ' || *s->p == '\t' || *s->p == '\r' || *s->p == '\n') s->p++; }
static Pj *fail(St *s, const char *why) { if (s->err && !s->err[0]) snprintf(s->err, s->cap, "JSON: %s at byte %d", why, (int)(s->p - s->start)); return NULL; }
static Pj *node(int t) { Pj *v = (Pj *)calloc(1, sizeof *v); if (v) v->type = t; return v; }
static void put8(char **o, unsigned c) {                     /* a code point as UTF-8 */
    char *q = *o;
    if (c < 0x80) *q++ = (char)c;
    else if (c < 0x800) { *q++ = (char)(0xC0 | c >> 6); *q++ = (char)(0x80 | (c & 63)); }
    else if (c < 0x10000) { *q++ = (char)(0xE0 | c >> 12); *q++ = (char)(0x80 | (c >> 6 & 63)); *q++ = (char)(0x80 | (c & 63)); }
    else { *q++ = (char)(0xF0 | c >> 18); *q++ = (char)(0x80 | (c >> 12 & 63)); *q++ = (char)(0x80 | (c >> 6 & 63)); *q++ = (char)(0x80 | (c & 63)); }
    *o = q;
}
static int hex4(const char *p, unsigned *v) {
    int i; *v = 0;
    for (i = 0; i < 4; i++) { char c = p[i]; *v <<= 4; if (c >= '0' && c <= '9') *v |= c - '0'; else if (c >= 'a' && c <= 'f') *v |= c - 'a' + 10; else if (c >= 'A' && c <= 'F') *v |= c - 'A' + 10; else return 0; }
    return 1;
}
static char *string(St *s) {                                 /* s->p at the opening quote */
    const char *q = ++s->p; size_t n = 0; char *out, *o;
    while (*q && *q != '"') { if (*q == '\\' && q[1]) q++; q++; n++; }
    if (*q != '"') { fail(s, "unterminated string"); return NULL; }
    out = o = (char *)malloc(n * 4 + 1);
    while (*s->p != '"') {
        char c = *s->p++;
        if (c != '\\') { *o++ = c; continue; }
        c = *s->p++;
        switch (c) {
        case 'n': *o++ = '\n'; break; case 't': *o++ = '\t'; break; case 'r': *o++ = '\r'; break; case 'b': *o++ = '\b'; break; case 'f': *o++ = '\f'; break;
        case 'u': { unsigned u, l; if (!hex4(s->p, &u)) { free(out); fail(s, "bad \\u escape"); return NULL; } s->p += 4;
                    if (u >= 0xD800 && u < 0xDC00 && s->p[0] == '\\' && s->p[1] == 'u' && hex4(s->p + 2, &l) && l >= 0xDC00 && l < 0xE000) { u = 0x10000 + ((u - 0xD800) << 10) + (l - 0xDC00); s->p += 6; }
                    put8(&o, u); break; }
        default: *o++ = c;
        }
    }
    s->p++; *o = 0; return out;
}
static Pj *value(St *s, int depth);
static Pj *members(St *s, int depth, int obj) {
    Pj *v = node(obj ? PJ_OBJ : PJ_ARR), **tail; char close = obj ? '}' : ']';
    if (!v) return fail(s, "out of memory");
    tail = &v->kid; s->p++; ws(s);
    if (*s->p == close) { s->p++; return v; }
    for (;;) {
        char *key = NULL; Pj *m;
        ws(s);
        if (obj) {
            if (*s->p != '"' || !(key = string(s))) { pj_free(v); return fail(s, "a key expected"); }
            ws(s);
            if (*s->p++ != ':') { free(key); pj_free(v); return fail(s, "':' expected"); }
        }
        if (!(m = value(s, depth + 1))) { free(key); pj_free(v); return NULL; }
        m->key = key; *tail = m; tail = &m->next; v->n++;
        ws(s);
        if (*s->p == ',') { s->p++; continue; }
        if (*s->p == close) { s->p++; return v; }
        pj_free(v); return fail(s, obj ? "',' or '}' expected" : "',' or ']' expected");
    }
}
static Pj *value(St *s, int depth) {
    ws(s);
    if (depth > 64) return fail(s, "nested too deep");
    switch (*s->p) {
    case '{': return members(s, depth, 1);
    case '[': return members(s, depth, 0);
    case '"': { char *t = string(s); Pj *v; if (!t) return NULL; v = node(PJ_STR); v->text = t; return v; }
    case 't': if (!strncmp(s->p, "true", 4)) { s->p += 4; return node(PJ_TRUE); } break;
    case 'f': if (!strncmp(s->p, "false", 5)) { s->p += 5; return node(PJ_FALSE); } break;
    case 'n': if (!strncmp(s->p, "null", 4)) { s->p += 4; return node(PJ_NULL); } break;
    default:
        if (*s->p == '-' || DIGITS(*s->p)) {        /* JSON's grammar: -? (0 | [1-9][0-9]*) (.[0-9]+)? ([eE][+-]?[0-9]+)?, so "01" or "1." fail as in ConvertFrom-Json */
            const char *b = s->p; Pj *v; size_t n;
            if (*s->p == '-') s->p++;
            if (*s->p == '0') s->p++;
            else if (DIGITS(*s->p)) while (DIGITS(*s->p)) s->p++;
            else return fail(s, "a number expected");
            if (*s->p == '.') { s->p++; if (!DIGITS(*s->p)) return fail(s, "digits expected after the point"); while (DIGITS(*s->p)) s->p++; }
            if (*s->p == 'e' || *s->p == 'E') { s->p++; if (*s->p == '+' || *s->p == '-') s->p++; if (!DIGITS(*s->p)) return fail(s, "digits expected in the exponent"); while (DIGITS(*s->p)) s->p++; }
            n = (size_t)(s->p - b); v = node(PJ_NUM); v->text = (char *)malloc(n + 1); memcpy(v->text, b, n); v->text[n] = 0;
            v->num = strtod(v->text, NULL); return v;
        }
    }
    return fail(s, "a value expected");
}
Pj *pj_parse(const char *text, char *err, int cap) {
    St s; Pj *v;
    s.p = s.start = text; s.err = err; s.cap = cap; if (err && cap) err[0] = 0;
    if (!strncmp(s.p, "\xEF\xBB\xBF", 3)) s.p += 3;
    v = value(&s, 0);
    if (!v) return NULL;
    ws(&s);
    if (*s.p) { pj_free(v); return fail(&s, "text after the value"); }
    return v;
}
Pj *pj_load(const char *path, char *err, int cap) {
    FILE *f = fopen(path, "rb"); long n; char *b; Pj *v;
    if (!f) { if (err && cap) snprintf(err, cap, "cannot open %s", path); return NULL; }
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    b = (char *)malloc((size_t)n + 1);
    if (!b || fread(b, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(b); if (err && cap) snprintf(err, cap, "cannot read %s", path); return NULL; }
    fclose(f); b[n] = 0; v = pj_parse(b, err, cap); free(b); return v;
}
void pj_free(Pj *v) {
    while (v) { Pj *n = v->next; pj_free(v->kid); free(v->key); free(v->text); free(v); v = n; }
}
Pj *pj_get(const Pj *o, const char *key) {
    Pj *m;
    if (!o || o->type != PJ_OBJ) return NULL;
    for (m = o->kid; m; m = m->next) if (m->key && !_stricmp(m->key, key)) return m;
    return NULL;
}
Pj *pj_at(const Pj *a, int i) {
    Pj *m;
    if (!a || a->type != PJ_ARR) return NULL;
    for (m = a->kid; m && i > 0; m = m->next) i--;
    return m;
}
const char *pj_str(const Pj *v) {
    if (!v) return "";
    switch (v->type) { case PJ_STR: case PJ_NUM: return v->text; case PJ_TRUE: return "True"; case PJ_FALSE: return "False"; default: return ""; }
}
int pj_truthy(const Pj *v) {
    if (!v) return 0;
    switch (v->type) { case PJ_TRUE: return 1; case PJ_NUM: return v->num != 0; case PJ_STR: return v->text[0] != 0; case PJ_ARR: return v->n != 0; case PJ_OBJ: return 1; default: return 0; }
}
