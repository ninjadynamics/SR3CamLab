#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include "frontend_model.h"
static const char fixture[]=
"{\"version\":1,\"games\":["
"{\"key\":\"src\",\"title\":\"SEGA Rally Championship\"},"
"{\"key\":\"sr2\",\"title\":\"SEGA Rally 2\"},"
"{\"key\":\"daytona\",\"title\":\"Daytona USA\"},"
"{\"key\":\"daytona2\",\"title\":\"Daytona USA 2\"},"
"{\"key\":\"scud\",\"title\":\"Scud Race\"}],\"tracks\":["
"{\"key\":\"Tropical4/s\",\"title\":\"Tropical\",\"source_game\":\"sr3\",\"slot\":\"Tropical4\",\"native_id\":0,\"directory\":\"s\",\"available\":true},"
"{\"key\":\"Desert4/1\",\"title\":\"Mountain R4\",\"source_game\":\"src\",\"slot\":\"Desert4\",\"native_id\":4,\"directory\":\"1\",\"available\":true},"
"{\"key\":\"Desert4/5\",\"title\":\"Daytona WIP\",\"source_game\":\"daytona\",\"slot\":\"Desert4\",\"native_id\":4,\"directory\":\"5\",\"available\":false}]}";
static FeCatalog catalog;
static FeMenu menu;
#define CHECK(x,c) do{if(!(x))ExitProcess(c);}while(0)
static void save(const char *path,const char *data){DWORD written;HANDLE f=CreateFileA(path,GENERIC_WRITE,0,0,CREATE_ALWAYS,0,0);CHECK(f!=INVALID_HANDLE_VALUE,90);CHECK(WriteFile(f,data,(DWORD)strlen(data),&written,0),91);CloseHandle(f);}
void frontend_model_test_entry(void){
    char folder[MAX_PATH],path[MAX_PATH],error[256],bad[sizeof(fixture)];char *p;
    CHECK(GetTempPathA(sizeof(folder),folder)&&GetTempFileNameA(folder,"url",0,path),1);
    save(path,fixture);CHECK(fe_catalog_load(path,&catalog,error,sizeof(error)),2);
    CHECK(catalog.count==3&&catalog.games[0].available&&!catalog.games[1].available&&!catalog.games[2].available,3);
    fe_menu_begin(&menu,1);CHECK(fe_menu_count(&catalog,&menu)==5,4);
    CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,0)==FE_IDLE&&menu.page==FE_GAME_MENU,5);
    fe_menu_step(&catalog,&menu,0,10);
    CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,20)==FE_CHANGED&&menu.page==FE_TRACK_MENU,6);
    CHECK(fe_menu_count(&catalog,&menu)==1&&fe_menu_track(&catalog,&menu,0)==1,7);
    CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,30)==FE_IDLE&&!menu.pending,8);
    fe_menu_step(&catalog,&menu,0,40);
    CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,50)==FE_CHOSEN&&menu.track==1&&menu.pending,9);
    CHECK(fe_menu_step(&catalog,&menu,FE_BACK,60)==FE_IDLE,10);
    menu.pending=0;fe_menu_step(&catalog,&menu,0,70);
    CHECK(fe_menu_step(&catalog,&menu,FE_BACK,80)==FE_CHANGED&&menu.page==FE_GAME_MENU,11);
    fe_menu_step(&catalog,&menu,0,90);fe_menu_step(&catalog,&menu,FE_RIGHT,100);fe_menu_step(&catalog,&menu,0,110);
    CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,120)==FE_IDLE&&menu.page==FE_GAME_MENU,12);
    CHECK(fe_menu_step(&catalog,&menu,FE_BACK,130)==FE_CANCELLED,13);
    fe_menu_begin(&menu,0);fe_menu_step(&catalog,&menu,0,0);
    CHECK(fe_menu_count(&catalog,&menu)==3,14);
    CHECK(fe_menu_step(&catalog,&menu,FE_RIGHT,10)==FE_CHANGED&&menu.cursor==1,15);
    CHECK(fe_menu_step(&catalog,&menu,FE_RIGHT,100)==FE_IDLE&&menu.cursor==1,16);
    CHECK(fe_menu_step(&catalog,&menu,FE_RIGHT,360)==FE_CHANGED&&menu.cursor==2,17);
    fe_menu_step(&catalog,&menu,0,370);CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,380)==FE_IDLE,18);
    fe_menu_step(&catalog,&menu,0,390);fe_menu_step(&catalog,&menu,FE_LEFT,400);fe_menu_step(&catalog,&menu,0,410);
    CHECK(fe_menu_step(&catalog,&menu,FE_SELECT,420)==FE_CHOSEN&&menu.track==1,19);
    memcpy(bad,fixture,sizeof(bad));p=strstr(bad,"\"native_id\":4");CHECK(p!=0,20);p[strlen("\"native_id\":")]='5';
    save(path,bad);CHECK(!fe_catalog_load(path,&catalog,error,sizeof(error))&&catalog.count==0,21);
    DeleteFileA(path);ExitProcess(0);
}
