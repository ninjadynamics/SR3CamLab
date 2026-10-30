#pragma once
#define FE_MAX_TRACKS 128
#define FE_GAMES 5
typedef struct {char key[64],title[128],game[16],slot[24],video[128],status[32];int native_id,available;char directory;} FeTrack;
typedef struct {char key[16],title[64],video[128],status[32];int available;} FeGame;
typedef struct {FeGame games[FE_GAMES];FeTrack tracks[FE_MAX_TRACKS];int count;} FeCatalog;
enum {FE_NONE,FE_GAME_MENU,FE_TRACK_MENU};
/* LEFT/RIGHT are held levels; TAP bits are counted presses for this step. */
enum {FE_LEFT=1,FE_RIGHT=2,FE_SELECT=4,FE_BACK=8,FE_TAP_LEFT=16,FE_TAP_RIGHT=32};
enum {FE_IDLE,FE_CHANGED,FE_CHOSEN,FE_CANCELLED};
/* Set by the caller each step: busy while the cards are more than one card
   behind (holds wait); blocked holds FE_LEFT/FE_RIGHT steps that cannot be
   shown yet. moved is the one-card direction of a same-page FE_CHANGED. */
typedef struct {int page,classic,cursor,game,track,await_release,pending,previous,direction;unsigned repeat_at;int queued,busy,blocked,moved,confirm;} FeMenu;
int fe_catalog_load(const char *path,FeCatalog *catalog,char *error,int capacity);
int fe_menu_count(const FeCatalog *,const FeMenu *);
int fe_menu_track(const FeCatalog *,const FeMenu *,int position);
void fe_menu_begin(FeMenu *,int classic);
int fe_menu_step(const FeCatalog *,FeMenu *,unsigned buttons,unsigned now);
