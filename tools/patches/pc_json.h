/* A small JSON reader for patchcore (switch.json, handling.json, classic.json): the whole document into one tree.
 * PowerShell's ConvertFrom-Json is what patches.ps1 used; this reads the same files the same way for what patchcore
 * asks of them: objects (keys in file order), arrays, strings (\uXXXX turned into UTF-8), numbers (their text kept as
 * written, and as a double), true, false, null. */
#pragma once
enum { PJ_NULL, PJ_FALSE, PJ_TRUE, PJ_NUM, PJ_STR, PJ_ARR, PJ_OBJ };
typedef struct Pj Pj;
struct Pj {
    int type, n;                     /* n: members of an array or object */
    char *key;                       /* the member's key inside an object, else NULL */
    char *text;                      /* a string's value, a number's text */
    double num;
    Pj *kid, *next;                  /* first member, next sibling */
};
Pj *pj_parse(const char *text, char *err, int cap);          /* NULL = not JSON (err says where) */
Pj *pj_load(const char *path, char *err, int cap);           /* a file, UTF-8 with or without its BOM */
void pj_free(Pj *v);
Pj *pj_get(const Pj *obj, const char *key);                  /* a member by key (case-insensitive, as PowerShell's properties) */
Pj *pj_at(const Pj *arr, int i);
const char *pj_str(const Pj *v);                             /* "$($x)": a string's text, a number's text, "True"/"False", "" for null */
int pj_truthy(const Pj *v);                                  /* PowerShell's [bool]: false for null, false, 0, "" and an empty array */
