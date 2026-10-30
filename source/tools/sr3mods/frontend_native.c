/* Expand the game's own track-card scene and selector. No separate renderer. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "frontend_native.h"
#include "frontend_video.h"
#define BANK_MAX 38
typedef struct {unsigned next,id,unused[4];const char *folder;} UiNode;
typedef struct {unsigned unused[2];UiNode nodes[BANK_MAX];} UiLibrary;
typedef void (__thiscall *Clear)(void *);
typedef void (__thiscall *Add)(void *,const char *,int,int,int,int);
typedef void (__stdcall *Build)(void *);
static const FeCatalog *catalog;
static const FeMenu *view;
static UiLibrary library;
static char folders[BANK_MAX][16];
static unsigned entries[BANK_MAX],scene,selector,total;
static int video_handles[BANK_MAX];
static unsigned hint;
static char saved_hint[512];
static int constructing;
static __attribute__((used)) unsigned original_fill;
static unsigned original_video;
/* Carousel position of a card is index*spacing+phase. 61D960 builds each
   card's reshuffle path for one side of the centre only (7287E0/728750 right,
   728900/728870 left), clamping beyond it to the centre. Jumps of several
   cards therefore park every crossing card in front. Each step here moves one
   card; a step past either end first moves the covered card from the opposite
   end of the list beside the selection. Component tests replace these. */
static uintptr_t carousel_owner=0x9d6e50,right_path=0x7287e0,left_path=0x728900;
static void (__stdcall *notify)(int)=(void (__stdcall *)(int))0x62a930;
static int order[BANK_MAX],bank[BANK_MAX],shown;
static unsigned card(unsigned node){return *(unsigned *)(uintptr_t)(node+0xc);}
static float *real(unsigned object,unsigned offset){return (float *)(uintptr_t)(object+offset);}
static unsigned active(void){
    unsigned owner=*(unsigned *)carousel_owner,s;if(!owner)return 0;
    s=*(unsigned *)(uintptr_t)(owner+0x1d4);return s?s:*(unsigned *)(uintptr_t)(owner+0x1d0);
}
static void path(unsigned c,uintptr_t from){
    unsigned n=*(unsigned *)(from+0x80);if(n>=2&&n<=16)memcpy((void *)(uintptr_t)(c+0x140),(const void *)from,0x8c);
}
static void link(void){
    unsigned prev=scene+0xa4,tail=scene+0xa8,node;int i;
    for(i=0;i<shown;++i){node=entries[bank[order[i]]];*(unsigned *)(uintptr_t)prev=node;*(unsigned *)(uintptr_t)(node+4)=prev;prev=node;
        *(unsigned *)(uintptr_t)(card(node)+0x80)=(unsigned)i;}
    *(unsigned *)(uintptr_t)prev=tail;*(unsigned *)(uintptr_t)(tail+4)=prev;
}
/* Every card's at-rest position and path agree with selected index 0. */
static void rest(void){
    float spacing=*real(scene,0xdc);unsigned i;
    *real(scene,0x98)=*real(scene,0x9c)=*real(scene,0xd8)=0;
    *(unsigned *)(uintptr_t)(scene+0xb4)=0;*(unsigned *)(uintptr_t)(scene+0x88)=0;
    for(i=0;i<total;++i){unsigned child=*(unsigned *)(uintptr_t)(card(entries[i])+0xb0);if(child)*(unsigned *)(uintptr_t)(child+0x104)=0;}
    for(i=0;i<(unsigned)shown;++i){unsigned c=card(entries[bank[order[i]]]);path(c,right_path);*real(c,0x90)=(float)i*spacing;}
}
/* direction>0 moves the first card behind the last; direction<0 the reverse.
   Phase, target and selection shift with the indices, so only the moved card's
   position changes, from one covered stack to the other. */
static void rotate(int direction){
    int i,moved;float spacing=*real(scene,0xdc),shift=direction>0?spacing:-spacing,phase;
    if(direction>0){moved=order[0];memmove(order,order+1,(size_t)(shown-1)*sizeof *order);order[shown-1]=moved;}
    else{moved=order[shown-1];memmove(order+1,order,(size_t)(shown-1)*sizeof *order);order[0]=moved;}
    link();
    *real(scene,0x98)+=shift;*real(scene,0x9c)+=shift;*real(scene,0xd8)+=shift;
    *(int *)(uintptr_t)(scene+0x88)-=direction;
    path(card(entries[bank[moved]]),direction>0?right_path:left_path);
    phase=*real(scene,0x9c);
    for(i=0;i<shown;++i)*real(card(entries[bank[order[i]]]),0x90)=(float)i*spacing+phase;
}
static int ours(void){return scene&&view&&active()==scene&&*real(scene,0xdc)>0;}
/* Nonzero while the cards are more than one card behind their target. */
int fe_native_busy(void){
    float left;
    if(!ours()||!*(unsigned *)(uintptr_t)(scene+0xb4))return 0;
    left=*real(scene,0x9c)-*real(scene,0x98);if(left<0)left=-left;
    return left>*real(scene,0xdc);
}
/* A wrap step moves the card at the opposite end of the list. During fast
   input that card can still be on screen; the step waits until the card in
   front is two past it, so its neighbour covers it. Ordinary steps never wait. */
int fe_native_blocked(void){
    int at,out=0;float seen;
    if(!ours()||shown<3)return 0;
    at=*(int *)(uintptr_t)(scene+0x88);seen=-*real(scene,0x9c)/ *real(scene,0xdc);
    if(at+1>=shown&&seen<2.f)out|=FE_RIGHT;
    if(at<1&&seen>(float)(shown-3))out|=FE_LEFT;
    return out;
}
__attribute__((naked)) static void stock_fill(void *object){__asm__("pushl %edi\n\tmovl 8(%esp),%edi\n\tcall *_original_fill\n\tpopl %edi\n\tret");}
__attribute__((naked)) void fe_native_activate(void){__asm__("pushl %edi\n\tmovl $11,%edi\n\tmovl $0x62ddd0,%eax\n\tcall *%eax\n\tpopl %edi\n\tret");}
static const char *title(unsigned i){return i<(unsigned)catalog->count?catalog->tracks[i].title:catalog->games[i-catalog->count].title;}
static const char *status(unsigned i,int *available){
    if(i<(unsigned)catalog->count){*available=catalog->tracks[i].available;return catalog->tracks[i].status;}
    *available=catalog->games[i-catalog->count].available;return catalog->games[i-catalog->count].status;
}
static void add_title(void *object,Add add,const char *label,int id){
    char format[256],display[192];unsigned n=0;int available;const char *s=status((unsigned)id,&available);
    if(!available){snprintf(display,sizeof display,"%s [%s]",label,s[0]?s:"Not installed");label=display;}
    /* Native AddEntry treats its label as a printf format. Catalog titles are
       literal text, including any percent signs in future imported names. */
    while(*label&&n+2<sizeof format){if(*label=='%')format[n++]='%';format[n++]=*label++;}format[n]=0;
    add(object,format,id,-1,0,0);
}
static __attribute__((used,noinline)) void fill(void *object){
    void **v=*(void ***)object;int i,n;
    if(!constructing&&!view){stock_fill(object);return;}
    ((Clear)v[0x58/4])(object);
    if(constructing){for(i=0;i<(int)total;++i)add_title(object,(Add)v[0x54/4],title(i),i);return;}
    n=view?fe_menu_count(catalog,view):catalog->count;
    for(i=0;i<n;++i){int id=view&&view->page==FE_GAME_MENU?catalog->count+i:view?fe_menu_track(catalog,view,i):i;
        if(id>=0)add_title(object,(Add)v[0x54/4],title((unsigned)id),id);
    }
    selector=(unsigned)(uintptr_t)object;
}
__attribute__((naked)) static void fill_bridge(void){__asm__("pushl %edi\n\tcall _fill\n\taddl $4,%esp\n\tret");}
/* Scene constructor's caller and callee both pop their single pointer. Only
 * this UI construction sees virtual nodes; gameplay's library is untouched. */
static void __stdcall build(void *object){
    unsigned *db=(unsigned *)(uintptr_t)*(unsigned*)0xb2a850;unsigned saved=db[2],p;int i;
    constructing=1;db[2]=(unsigned)(uintptr_t)&library;
    ((Build)(uintptr_t)0x62d1c0)(object);
    db[2]=saved;constructing=0;scene=(unsigned)(uintptr_t)object;
    p=*(unsigned *)(uintptr_t)(scene+0xa4);
    for(i=0;i<(int)total&&p&&*(unsigned *)(uintptr_t)p;++i){entries[i]=p;p=*(unsigned *)(uintptr_t)p;}
    if(i!=(int)total){pc_logf("Native frontend: scene/list mismatch (%d/%u).",i,total);scene=0;return;}
    pc_logf("Native frontend: built %u stock-style card nodes.",total);
}
static unsigned * __cdecl video(unsigned *out,const char *name){
    unsigned id;char path[260],root[260],*p;const char *file;
    if(name&&strlen(name)==17&&!strncmp(name,"TRACKSLIDE_URL_",15)&&name[15]>='0'&&name[15]<='9'&&name[16]>='0'&&name[16]<='9'&&(id=(unsigned)(name[15]-'0')*10+(unsigned)(name[16]-'0'))<total){
        file=id<(unsigned)catalog->count?catalog->tracks[id].video:catalog->games[id-catalog->count].video;
        if(!file[0])file="classic.wmv";
        GetModuleFileNameA(NULL,root,sizeof root);p=strrchr(root,'\\');if(!p){*out=-1u;return out;}*p=0;
        snprintf(path,sizeof path,"%s\\frontend\\PC\\Videos\\%s",root,file);
        *out=(unsigned)fe_video_register(path);
        video_handles[id]=(int)*out;
        pc_logf("Native preview: %s -> %u (%s)",name,*out,path);return out;
    }
    return ((unsigned *(__cdecl *)(unsigned *,const char *))(uintptr_t)original_video)(out,name);
}
static unsigned lookup(unsigned hash){unsigned result;__asm__ volatile("call *%2":"=a"(result):"a"(hash),"r"(0x54bf40):"ecx","edx","memory");return result;}
static void set_hint(const char *label){
#ifndef FE_NATIVE_TEST
    typedef void (__thiscall *SetText)(void *,const char *);
    if(!hint&&label){
        unsigned hash=((unsigned (__fastcall *)(const char *))(uintptr_t)0x54a810)("ID_TEXT_MODESELECT_WHEEL");
        unsigned object=lookup(hash);
        /* This native text widget stores its localization key at A8 and
           exposes the ANSI setter at vtable+48. Refuse another widget ABI. */
        if(object&&*(unsigned *)(uintptr_t)(*(unsigned *)(uintptr_t)object+0x48)==0x614940){
            hint=object;memcpy(saved_hint,(void *)(uintptr_t)(object+0xa8),sizeof saved_hint);saved_hint[511]=0;
        }
    }
    if(hint){unsigned *v=*(unsigned **)(uintptr_t)hint;((SetText)(uintptr_t)v[0x48/4])((void *)(uintptr_t)hint,label?label:saved_hint);if(!label)hint=0;}
#else
    (void)label;
#endif
}
void fe_native_detach_view(void){fe_video_menu(NULL,0);set_hint(NULL);view=NULL;selector=0;}
void fe_native_leave(void){
    unsigned i,prev,tail,card;fe_video_menu(NULL,0);set_hint(NULL);view=NULL;
    if(!scene)return;
    /* Return every persistent node to the owning scene. The native destructor
       can then release the entire bank, including cards omitted by a submenu. */
    prev=scene+0xa4;tail=scene+0xa8;
    for(i=0;i<total;++i){unsigned node=entries[i];*(unsigned *)(uintptr_t)prev=node;*(unsigned *)(uintptr_t)(node+4)=prev;prev=node;
        card=*(unsigned *)(uintptr_t)(node+0xc);*(unsigned *)(uintptr_t)(card+0x80)=i;}
    *(unsigned *)(uintptr_t)prev=tail;*(unsigned *)(uintptr_t)(tail+4)=prev;
    *(unsigned *)(uintptr_t)(scene+0x88)=0;
    *(unsigned *)(uintptr_t)(scene+0xbc)=0;*(unsigned *)(uintptr_t)(scene+0xc0)=total-1;
}
void fe_native_cursor(int cursor,int direction){
    unsigned *p=(unsigned *)(uintptr_t)selector;int at,to=-1,i;
    if(!p||!scene||cursor<0||cursor>=(int)p[0xc0/4]||cursor>=shown)return;
    if((int)p[0x94/4]!=cursor){p[0x98/4]=p[0x94/4];p[0x94/4]=(unsigned)cursor;p[0xa0/4]=0;p[0x88/4]|=3;p[0xb0/4]|=1;}
    at=*(int *)(uintptr_t)(scene+0x88);
    if(direction&&shown>=3&&active()==scene&&at>=0&&at<shown&&order[at]==(cursor-direction+shown)%shown){
        if(at+direction<0||at+direction>=shown){rotate(direction);at-=direction;}
        to=at+direction;
    }else for(i=0;i<shown;++i)if(order[i]==cursor)to=i;
    if(to<0||order[to]!=cursor)return;
    /* Native callbacks normally notify the 3D carousel separately from the
       text selector. Publishing only the selector index leaves cards still. */
    notify(to);
}
int fe_native_view(const FeMenu *menu){
    int i,handles[BANK_MAX],n=fe_menu_count(catalog,menu),first;
    if(!scene||n<1||n>BANK_MAX)return 0;
    for(i=0;i<n;++i){int id=menu->page==FE_GAME_MENU?catalog->count+i:fe_menu_track(catalog,menu,i);
        if(id<0||id>=(int)total)return 0;
        bank[i]=id;handles[i]=video_handles[id];
    }
    /* A rewired view starts at rest with the cursor's card selected first.
       Rebuilding at a nonzero cursor would otherwise be a multi-card jump, and
       a previous view's phase, paths or selection could show another card. */
    view=menu;shown=n;first=menu->cursor>=0&&menu->cursor<n?menu->cursor:0;
    for(i=0;i<n;++i)order[i]=(first+i)%n;
    link();rest();
    *(int *)(uintptr_t)(scene+0xbc)=0;*(int *)(uintptr_t)(scene+0xc0)=n-1;
    {
#ifdef FE_NATIVE_TEST
     unsigned object=selector;
#else
     /* Classic has already loaded this native page/selector. Reuse its text
        widgets for both submenu levels rather than targeting an inactive page. */
     unsigned hash=((unsigned (__fastcall *)(const char *))(uintptr_t)0x54a810)(menu->classic?"ID_SELECTOR_CARSELECT":"ID_SELECTOR_TRACKSELECT");unsigned object=lookup(hash);
#endif
     if(!object)return 0;
     fill((void *)(uintptr_t)object);
     *(unsigned *)(uintptr_t)(object+0x94)=0;*(unsigned *)(uintptr_t)(object+0x98)=0;
     *(unsigned *)(uintptr_t)(object+0xa0)=0;
     fe_native_cursor(first,0);}
    fe_video_menu(handles,(unsigned)n);
    set_hint(menu->page==FE_GAME_MENU?"Select Game":"Select Track");
    pc_logf("Native frontend view: page=%d count=%d selector=%08X cursor=%d",menu->page,n,selector,menu->cursor);
    return 1;
}
static int patch(GameMem *m,unsigned at,unsigned to,unsigned bytes,unsigned cave,int call){
    unsigned char out[16];int rel;memset(out,0x90,sizeof out);out[0]=call?0xe8:0xe9;rel=(int)(to-at-5);memcpy(out+1,&rel,4);
    (void)cave;return m->write(m,at,out,bytes,0);
}
int fe_native_install(GameMem *m,const FeCatalog *c){
    unsigned i,rel,cave;unsigned char b[16],tramp[16];
    static const unsigned char fill_bytes[]={0x83,0xec,0x40,0x6a,0x3f},video_bytes[]={0x53,0x55,0x8b,0x6c,0x24,0x10},build_call[]={0xe8,0xe8,0xf5,0xff,0xff};
    /* Notify reads the active carousel through 9D6E50; 61D960 copies the
       right/left reshuffle paths that rest() and rotate() assign. */
    static const unsigned char notify_bytes[]={0xa1,0x50,0x6e,0x9d,0x00},right_bytes[]={0xbe,0xe0,0x87,0x72,0x00},left_bytes[]={0xbe,0x00,0x89,0x72,0x00};
    catalog=c;total=(unsigned)c->count+FE_GAMES;if(total>BANK_MAX)return 0;
    if(!m->read(m,0x600660,b,5)||memcmp(b,fill_bytes,5)||!m->read(m,0x61c2c0,b,6)||memcmp(b,video_bytes,6)||!m->read(m,0x62dbd3,b,5)||memcmp(b,build_call,5))return 0;
    if(!m->read(m,0x62a930,b,5)||memcmp(b,notify_bytes,5)||!m->read(m,0x61deae,b,5)||memcmp(b,right_bytes,5)||!m->read(m,0x61deb5,b,5)||memcmp(b,left_bytes,5))return 0;
    for(i=0;i<total;++i){snprintf(folders[i],sizeof folders[i],"URL_%02u",i);library.nodes[i].id=i;library.nodes[i].folder=folders[i];library.nodes[i].next=i+1<total?(unsigned)(uintptr_t)&library.nodes[i+1]:0;}
    cave=m->alloc(m,32);if(!cave)return 0;
    memcpy(tramp,video_bytes,6);tramp[6]=0xe9;rel=0x61c2c6-(cave+11);memcpy(tramp+7,&rel,4);
    if(!m->write(m,cave,tramp,11,1))return 0;
    original_video=cave;
    memcpy(tramp,fill_bytes,5);tramp[5]=0xe9;rel=0x600665-(cave+16+10);memcpy(tramp+6,&rel,4);
    if(!m->write(m,cave+16,tramp,10,1))return 0;
    original_fill=cave+16;
    if(!patch(m,0x600660,(unsigned)(uintptr_t)fill_bridge,5,0,0)||!patch(m,0x61c2c0,(unsigned)(uintptr_t)video,6,0,0)||!patch(m,0x62dbd3,(unsigned)(uintptr_t)build,5,0,1))return 0;
    return 1;
}
