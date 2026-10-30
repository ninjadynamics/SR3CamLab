#define FE_NATIVE_TEST
#include <stdarg.h>
#include "frontend_native.c"
void pc_logf(const char *s,...){(void)s;}
int fe_video_register(const char *s){(void)s;return 20;}
void fe_video_menu(const int *handles,unsigned count){(void)handles;(void)count;}
static FeCatalog test_catalog;
static unsigned test_scene[128],test_selector[1024],links[BANK_MAX][4],cards[BANK_MAX][128],children[BANK_MAX][128];
static unsigned owner[128],owner_ptr,right_t[36],left_t[36];
static void *vtable[32];
static int notified;
static void __thiscall clear_(void *obj){unsigned *p=obj;p[0xc0/4]=0;}
static void __thiscall add_(void *obj,const char *label,int id,int a,int b,int c){unsigned *p=obj;unsigned i=p[0xc0/4]++;(void)a;(void)b;(void)c;strcpy((char*)obj+0xc4+i*0x50,label);p[(0x104+i*0x50)/4]=(unsigned)id;}
#define CHECK(x,n) do{if(!(x))ExitProcess(n);}while(0)
static float *f(unsigned *object,unsigned offset){return (float *)&object[offset/4];}
/* 62A930 -> 622270 -> 61D960: selection index and target phase for one card. */
static void __stdcall native_select(int to){
    int from=(int)test_scene[0x88/4];notified=to;test_scene[0x88/4]=(unsigned)to;
    *f(test_scene,0x98)-=(float)(to-from)**f(test_scene,0xdc);
}
static int local_id(const FeMenu *menu,int i){return menu->page==FE_GAME_MENU?test_catalog.count+i:fe_menu_track(catalog,menu,i);}
static unsigned *card_of(const FeMenu *menu,int local){return cards[local_id(menu,local)];}
/* The native list is a rotation of the logical order. Card indices equal list
   positions, and the native target phase agrees with the selected index. */
static void check_list(const FeMenu *menu,int n,int first){unsigned p=test_scene[0xa4/4],prev=scene+0xa4;int i;
    for(i=0;i<n;++i){unsigned *node=(unsigned *)(uintptr_t)p;int local=(first+i)%n;
        CHECK(p==entries[local_id(menu,local)]&&node[1]==prev&&order[i]==local,3);
        CHECK(*(unsigned *)(uintptr_t)(node[3]+0x80)==(unsigned)i,5);prev=p;p=node[0];}
    CHECK(p==scene+0xa8&&test_scene[0xac/4]==prev,6);
    CHECK(*f(test_scene,0x98)==-(float)test_scene[0x88/4]**f(test_scene,0xdc),40);
}
static void check_view(FeMenu *menu,int expected){int i;
    test_scene[0x98/4]=0x3f000000;test_scene[0x9c/4]=0x3e800000;test_scene[0xd8/4]=0x3f000000;test_scene[0xb4/4]=1;test_scene[0x88/4]=3;
    for(i=0;i<BANK_MAX;++i){children[i][0x104/4]=1;cards[i][0x140/4]=0xdead;}
    CHECK(fe_native_view(menu),1);CHECK(test_selector[0xc0/4]==(unsigned)expected,2);
    for(i=0;i<expected;++i)CHECK(test_selector[(0x104+i*0x50)/4]==(unsigned)local_id(menu,i),4);
    check_list(menu,expected,menu->cursor);
    CHECK(test_selector[0x94/4]==(unsigned)menu->cursor&&notified==0&&test_scene[0x88/4]==0,7);
    CHECK(!test_scene[0x9c/4]&&!test_scene[0xd8/4]&&!test_scene[0xb4/4],13);
    for(i=0;i<(int)total;++i)CHECK(!children[i][0x104/4],14);
    for(i=0;i<expected;++i){unsigned *c=card_of(menu,(menu->cursor+i)%expected);
        CHECK(!memcmp(c+0x140/4,right_t,0x8c)&&*f(c,0x90)==(float)i*60.f,15);}
}
static void step(FeMenu *menu,int direction,int n){
    menu->cursor=(menu->cursor+direction+n)%n;notified=-1;fe_native_cursor(menu->cursor,direction);
    CHECK(notified>=0&&order[notified]==menu->cursor&&test_selector[0x94/4]==(unsigned)menu->cursor,20);
}
void frontend_native_test_entry(void){int i,before[BANK_MAX];FeMenu menu;
    catalog=&test_catalog;test_catalog.count=9;total=14;scene=(unsigned)(uintptr_t)test_scene;selector=(unsigned)(uintptr_t)test_selector;
    notify=native_select;owner[0x1d0/4]=scene;owner_ptr=(unsigned)(uintptr_t)owner;carousel_owner=(uintptr_t)&owner_ptr;
    right_t[0x80/4]=left_t[0x80/4]=11;right_t[1]=0x11;left_t[1]=0x22;right_path=(uintptr_t)right_t;left_path=(uintptr_t)left_t;
    *f(test_scene,0xdc)=60.f;
    vtable[0x58/4]=(void*)clear_;vtable[0x54/4]=(void*)add_;test_selector[0]=(unsigned)(uintptr_t)vtable;
    for(i=0;i<14;++i){entries[i]=(unsigned)(uintptr_t)links[i];links[i][3]=(unsigned)(uintptr_t)cards[i];cards[i][0xb0/4]=(unsigned)(uintptr_t)children[i];}
    for(i=0;i<5;++i)snprintf(test_catalog.games[i].key,16,"game%d",i);
    for(i=0;i<9;++i){snprintf(test_catalog.tracks[i].title,128,"Track %d",i);strcpy(test_catalog.tracks[i].game,i==4?"game0":i==5||i==6?"game1":"sr3");}
    fe_menu_begin(&menu,1);
    selector=0;CHECK(!fe_native_view(&menu),11);
    selector=(unsigned)(uintptr_t)test_selector;check_view(&menu,5);
    /* Four ordinary steps, then Right on the last card is one more step: the
       first card is moved behind the last instead of a four-card jump back. */
    for(i=1;i<5;++i){step(&menu,1,5);CHECK(notified==i,21);check_list(&menu,5,0);}
    test_scene[0x9c/4]=test_scene[0x98/4];*f(test_scene,0xd8)=-180.f;
    step(&menu,1,5);CHECK(menu.cursor==0&&notified==4,22);check_list(&menu,5,1);
    CHECK(*f(test_scene,0x9c)==-180.f&&*f(test_scene,0xd8)==-120.f,23);
    CHECK(!memcmp(cards[9]+0x140/4,right_t,0x8c)&&*f(cards[9],0x90)==4*60.f-180.f,24);
    for(i=0;i<5;++i)CHECK(*f(card_of(&menu,order[i]),0x90)==(float)i*60.f-180.f,25);
    /* Left returns without rotation; Left past the first card mirrors Right. */
    step(&menu,-1,5);CHECK(menu.cursor==4&&notified==3,26);check_list(&menu,5,1);
    for(i=0;i<3;++i)step(&menu,-1,5);
    CHECK(menu.cursor==1&&notified==0,27);
    step(&menu,-1,5);CHECK(menu.cursor==0&&notified==0,28);check_list(&menu,5,0);
    CHECK(!memcmp(cards[9]+0x140/4,left_t,0x8c),29);
    step(&menu,-1,5);CHECK(menu.cursor==4&&notified==0,30);check_list(&menu,5,4);
    CHECK(!memcmp(cards[13]+0x140/4,left_t,0x8c),31);
    /* A selection the plugin did not make is never rotated around. */
    memcpy(before,order,sizeof before);test_scene[0x88/4]=2;step(&menu,1,5);
    CHECK(!memcmp(before,order,sizeof before)&&notified==1,32);
    owner[0x1d4/4]=0x1234;test_scene[0x88/4]=0;menu.cursor=0;memcpy(before,order,sizeof before);step(&menu,-1,5);
    CHECK(!memcmp(before,order,sizeof before)&&notified==0,33);owner[0x1d4/4]=0;
    /* Holds wait while cards are over one card behind. A wrap waits only
       while the card it moves could be on screen (front card under two past it). */
    test_scene[0xb4/4]=1;*f(test_scene,0x98)=-120.f;*f(test_scene,0x9c)=-59.f;CHECK(fe_native_busy(),34);
    *f(test_scene,0x9c)=-61.f;CHECK(!fe_native_busy(),35);
    *f(test_scene,0x9c)=0.f;owner[0x1d4/4]=0x1234;CHECK(!fe_native_busy()&&!fe_native_blocked(),36);owner[0x1d4/4]=0;
    test_scene[0xb4/4]=0;CHECK(!fe_native_busy(),37);
    test_scene[0x88/4]=4;*f(test_scene,0x9c)=-110.f;CHECK(fe_native_blocked()==FE_RIGHT,42);
    *f(test_scene,0x9c)=-120.f;CHECK(!fe_native_blocked(),43);
    test_scene[0x88/4]=0;*f(test_scene,0x9c)=-130.f;CHECK(fe_native_blocked()==FE_LEFT,44);
    *f(test_scene,0x9c)=-120.f;CHECK(!fe_native_blocked(),45);
    test_scene[0x88/4]=2;*f(test_scene,0x9c)=-240.f;CHECK(!fe_native_blocked(),46);
    /* Two cards cannot sit on both sides: wrap is an ordinary one-card swap. */
    menu.page=FE_TRACK_MENU;menu.game=1;menu.cursor=0;check_view(&menu,2);
    step(&menu,1,2);CHECK(notified==1,38);step(&menu,1,2);CHECK(notified==0,39);check_list(&menu,2,0);
    *f(test_scene,0x9c)=-500.f;CHECK(!fe_native_blocked(),47);
    menu.page=FE_TRACK_MENU;menu.game=0;menu.cursor=0;check_view(&menu,1);
    fe_menu_begin(&menu,0);menu.cursor=8;check_view(&menu,9);
    step(&menu,1,9);CHECK(menu.cursor==0&&notified==1,41);check_list(&menu,9,8);
    fe_menu_begin(&menu,1);menu.cursor=3;check_view(&menu,5);
    menu.page=FE_TRACK_MENU;menu.game=0;menu.cursor=0;check_view(&menu,1);
    /* Repeated subset changes must preserve every bank node for re-entry. */
    for(i=0;i<100;++i){fe_menu_begin(&menu,i&1);menu.cursor=i%5;check_view(&menu,(i&1)?5:9);}
    fe_native_cursor(99,1);CHECK(test_selector[0x94/4]==(unsigned)menu.cursor,8);
    {unsigned head=test_scene[0xa4/4];fe_native_detach_view();CHECK(view==NULL&&selector==0&&test_scene[0xa4/4]==head&&!fe_native_busy(),12);}
    fe_native_leave();{unsigned p=test_scene[0xa4/4];for(i=0;i<14;++i){CHECK(p==entries[i],9);p=*(unsigned *)(uintptr_t)p;}CHECK(p==scene+0xa8&&view==NULL,10);}
    ExitProcess(0);
}
