#include <stdio.h>
#include <string.h>
#include "pc_json.h"
#include "frontend_model.h"
static const char *const game_keys[]={"src","sr2","daytona","daytona2","scud"};
static const char *const slot_names[]={"Tropical4","Canyon4","Alpine4","Lakeside4","Desert4","Stadium4"};
static int string_(const Pj *p,char *dst,unsigned cap,int optional){
    const char *s=pj_str(p);size_t n=strlen(s);
    if((!optional&&(!p||p->type!=PJ_STR||!n))||n>=cap)return 0;
    memcpy(dst,s,n+1);return 1;
}
static int video_(const Pj *p,char *dst,unsigned cap){
    unsigned i;if(!string_(p,dst,cap,1))return 0;
    if(!dst[0])return 1;
    if(strstr(dst,".."))return 0;
    for(i=0;dst[i];++i)if(!((dst[i]>='a'&&dst[i]<='z')||(dst[i]>='A'&&dst[i]<='Z')||
       (dst[i]>='0'&&dst[i]<='9')||dst[i]=='_'||dst[i]=='-'||dst[i]=='.'))return 0;
    return i>4&&!_stricmp(dst+i-4,".wmv");
}
int fe_catalog_load(const char *path,FeCatalog *c,char *error,int cap){
    Pj *root=pj_load(path,error,cap),*games,*tracks,*v;int i,j,ok=0;
    memset(c,0,sizeof(*c));if(!root)return 0;
    if(!pj_get(root,"version")||pj_get(root,"version")->num!=1)goto done;
    games=pj_get(root,"games");tracks=pj_get(root,"tracks");
    if(!games||games->type!=PJ_ARR||games->n!=FE_GAMES||!tracks||tracks->type!=PJ_ARR||tracks->n<1||tracks->n>FE_MAX_TRACKS)goto done;
    for(i=0;i<FE_GAMES;++i){FeGame *g=&c->games[i];Pj *row=pj_at(games,i);
        if(!string_(pj_get(row,"key"),g->key,sizeof(g->key),0)||strcmp(g->key,game_keys[i])||
           !string_(pj_get(row,"title"),g->title,sizeof(g->title),0)||!video_(pj_get(row,"video"),g->video,sizeof(g->video))||
           !string_(pj_get(row,"status"),g->status,sizeof(g->status),1))goto done;
    }
    for(i=0;i<tracks->n;++i){FeTrack *t=&c->tracks[i];Pj *row=pj_at(tracks,i);char dir[8];
        if(!string_(pj_get(row,"key"),t->key,sizeof(t->key),0)||!string_(pj_get(row,"title"),t->title,sizeof(t->title),0)||
           !string_(pj_get(row,"source_game"),t->game,sizeof(t->game),0)||!string_(pj_get(row,"slot"),t->slot,sizeof(t->slot),0)||
           !string_(pj_get(row,"directory"),dir,sizeof(dir),0)||strlen(dir)!=1||
           !(dir[0]=='s'||(dir[0]>='1'&&dir[0]<='9'))||!video_(pj_get(row,"video"),t->video,sizeof(t->video))||
           !string_(pj_get(row,"status"),t->status,sizeof(t->status),1))goto done;
        v=pj_get(row,"native_id");if(!v||v->type!=PJ_NUM||v->num<0||v->num>5||v->num!=(int)v->num)goto done;
        t->native_id=(int)v->num;t->directory=dir[0];
        if(strcmp(t->slot,slot_names[t->native_id]))goto done;
        v=pj_get(row,"available");if(!v||(v->type!=PJ_TRUE&&v->type!=PJ_FALSE))goto done;
        t->available=v->type==PJ_TRUE;
        for(j=0;j<i;++j)if(!strcmp(t->key,c->tracks[j].key)||
            (!strcmp(t->slot,c->tracks[j].slot)&&t->directory==c->tracks[j].directory))goto done;
        for(j=0;j<FE_GAMES;++j)if(!strcmp(t->game,game_keys[j]))break;
        if(j==FE_GAMES&&strcmp(t->game,"revo")&&strcmp(t->game,"sr3"))goto done;
        if(j<FE_GAMES&&t->available)c->games[j].available=1;
    }
    c->count=tracks->n;ok=1;
done:
    pj_free(root);if(!ok){memset(c,0,sizeof(*c));snprintf(error,(size_t)cap,"Invalid frontend track catalog");}return ok;
}
int fe_menu_track(const FeCatalog *c,const FeMenu *m,int position){
    int i,n=0;if(position<0)return -1;
    for(i=0;i<c->count;++i)if(!m->classic||!strcmp(c->tracks[i].game,c->games[m->game].key)){
        if(n++==position)return i;
    }
    return -1;
}
int fe_menu_count(const FeCatalog *c,const FeMenu *m){
    int i,n=0;if(m->page==FE_GAME_MENU)return FE_GAMES;
    if(m->page!=FE_TRACK_MENU)return 0;
    for(i=0;i<c->count;++i)if(!m->classic||!strcmp(c->tracks[i].game,c->games[m->game].key))++n;
    return n;
}
void fe_menu_begin(FeMenu *m,int classic){memset(m,0,sizeof(*m));m->classic=classic;m->page=classic?FE_GAME_MENU:FE_TRACK_MENU;m->track=-1;m->await_release=1;}
int fe_menu_step(const FeCatalog *c,FeMenu *m,unsigned buttons,unsigned now){
    int count=fe_menu_count(c,m),edge=(int)buttons&~m->previous,direction=(buttons&FE_RIGHT)?1:(buttons&FE_LEFT)?-1:0;
    int tap=((buttons&FE_TAP_RIGHT)?1:0)-((buttons&FE_TAP_LEFT)?1:0);
    m->previous=(int)buttons;m->moved=0;
    if(m->await_release){if(!(buttons&(FE_LEFT|FE_RIGHT|FE_SELECT|FE_BACK)))m->await_release=0;return FE_IDLE;}
    if(m->pending||!m->page)return FE_IDLE;
    if(edge&FE_BACK){
        m->queued=m->confirm=0;
        if(m->classic&&m->page==FE_TRACK_MENU){m->page=FE_GAME_MENU;m->cursor=m->game;m->await_release=1;return FE_CHANGED;}
        m->page=FE_NONE;return FE_CANCELLED;
    }
    /* Every counted press is one card at once. A held direction repeats only
       while the cards keep up, so releasing does not coast several cards on. */
    if(tap){if(m->queued*tap<8)m->queued+=tap;m->direction=tap;m->repeat_at=now+350;}
    else if(direction!=m->direction){m->direction=direction;m->repeat_at=now+350;}
    else if(direction&&!m->queued&&!m->busy&&!(m->blocked&(direction>0?FE_RIGHT:FE_LEFT))&&(int)(now-m->repeat_at)>=0){m->queued=direction;m->repeat_at=now+120;}
    if(edge&FE_SELECT)m->confirm=1;
    if(m->queued&&count){
        int d=m->queued>0?1:-1;
        if(m->blocked&(d>0?FE_RIGHT:FE_LEFT))return FE_IDLE;
        m->moved=d;m->queued-=d;
        m->cursor=(m->cursor+d+count)%count;return FE_CHANGED;
    }
    m->queued=0;
    /* A Select pressed behind queued cards confirms the card they reach. */
    if(m->confirm){
        m->confirm=0;
        if(!count)return FE_IDLE;
        if(m->page==FE_GAME_MENU){
            if(!c->games[m->cursor].available)return FE_IDLE;
            m->game=m->cursor;m->cursor=0;m->page=FE_TRACK_MENU;m->await_release=1;return FE_CHANGED;
        }
        m->track=fe_menu_track(c,m,m->cursor);
        if(m->track>=0&&c->tracks[m->track].available){m->pending=1;return FE_CHOSEN;}
    }
    return FE_IDLE;
}
