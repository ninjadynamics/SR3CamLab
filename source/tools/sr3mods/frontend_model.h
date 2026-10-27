#pragma once
#define FE_MAX_TRACKS 128
#define FE_GAMES 5
typedef struct {char key[64],title[128],game[16],slot[24],video[128],status[32];int native_id,available;char directory;} FeTrack;
typedef struct {char key[16],title[64],video[128],status[32];int available;} FeGame;
typedef struct {FeGame games[FE_GAMES];FeTrack tracks[FE_MAX_TRACKS];int count;} FeCatalog;
enum {FE_NONE,FE_GAME_MENU,FE_TRACK_MENU};
enum {FE_LEFT=1,FE_RIGHT=2,FE_SELECT=4,FE_BACK=8};
enum {FE_IDLE,FE_CHANGED,FE_CHOSEN,FE_CANCELLED};
typedef struct {int page,classic,cursor,game,track,await_release,pending,previous,direction;unsigned repeat_at;} FeMenu;
int fe_catalog_load(const char *path,FeCatalog *catalog,char *error,int capacity);
int fe_menu_count(const FeCatalog *,const FeMenu *);
int fe_menu_track(const FeCatalog *,const FeMenu *,int position);
void fe_menu_begin(FeMenu *,int classic);
int fe_menu_step(const FeCatalog *,FeMenu *,unsigned buttons,unsigned now);
