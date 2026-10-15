/* SR3Lab standalone runtime. Copyright (c) 2026 Ninja Dynamics. MIT.
 * One x86 DLL; static SDL3; no TeknoParrot process, driver or service.
 * See INVESTIGATION.md for executable identity and interface observations.
 */
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#define SDL_MAIN_HANDLED
#include <windows.h>
#include <d3d9.h>
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdint.h>
#include "input.h"

static HMODULE module, realInput;
static HANDLE logfile=INVALID_HANDLE_VALUE;
static char root[MAX_PATH], config[MAX_PATH], saves[MAX_PATH];
static INIT_ONCE once=INIT_ONCE_STATIC_INIT;
static CRITICAL_SECTION inputLock;
static HWND gameWindow;
static WNDPROC oldWindowProc;
static SDL_Gamepad *pad;
static int sdlStarted, width=1280, height=720, windowed=1, deadzone=4096;
static int backgroundInput, freeplay=1, cores=4, controllerIndex=0;
static int startButton=SDL_GAMEPAD_BUTTON_START, viewButton=SDL_GAMEPAD_BUTTON_SOUTH;
static int handButton=SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER;
static int upButton=SDL_GAMEPAD_BUTTON_NORTH, downButton=SDL_GAMEPAD_BUTTON_WEST;
static DWORD lastSearch, lastReportLog;
static volatile LONG outputCommand;
static IDirect3D9 *(WINAPI *systemCreate9)(UINT);
static HRESULT (WINAPI *systemCreateDevice)(IDirect3D9*,UINT,D3DDEVTYPE,HWND,DWORD,D3DPRESENT_PARAMETERS*,IDirect3DDevice9**);
static HRESULT (WINAPI *systemReset)(IDirect3DDevice9*,D3DPRESENT_PARAMETERS*);
static BOOL WINAPI cabinetRead(HANDLE,LPVOID,DWORD,LPDWORD,LPOVERLAPPED);
static void *cabinetReadPointer=cabinetRead;

static void logline(const char *format,...) {
    char buffer[2048]; DWORD written; int size; va_list args;
    if(logfile==INVALID_HANDLE_VALUE) return;
    va_start(args,format); size=vsnprintf(buffer,sizeof(buffer),format,args); va_end(args);
    if(size<0) return;
    if(size>=(int)sizeof(buffer)) size=sizeof(buffer)-1;
    WriteFile(logfile,buffer,(DWORD)size,&written,NULL);
}
static int integer(const char *section,const char *key,int def,int lo,int hi) {
    int v=(int)GetPrivateProfileIntA(section,key,def,config);
    return v<lo?lo:v>hi?hi:v;
}
static BOOL writeMemory(void *where,const void *bytes,SIZE_T size) {
    DWORD old,ignored;
    if(!VirtualProtect(where,size,PAGE_EXECUTE_READWRITE,&old)) return FALSE;
    memcpy(where,bytes,size);
    FlushInstructionCache(GetCurrentProcess(),where,size);
    return VirtualProtect(where,size,old,&ignored);
}
static BOOL replacePointer(void *where,void *value) {return writeMemory(where,&value,sizeof(value));}
static uint32_t crc32(const unsigned char *p,size_t size) {
    uint32_t crc=~0u; size_t i; int bit;
    for(i=0;i<size;i++){crc^=p[i];for(bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1)));}
    return ~crc;
}
static void findPad(void) {
    int count=0; SDL_JoystickID *ids=SDL_GetGamepads(&count);
    if(ids && count>controllerIndex) pad=SDL_OpenGamepad(ids[controllerIndex]);
    SDL_free(ids);
    if(pad) logline("Controller: %s\n",SDL_GetGamepadName(pad));
}
static BOOL CALLBACK initialize(PINIT_ONCE ignored,PVOID parameter,PVOID *context) {
    char path[MAX_PATH]; DWORD_PTR available,systemMask,chosen=0; int i,n;
    (void)ignored;(void)parameter;(void)context;
    width=integer("Display","Width",1280,640,7680);
    height=integer("Display","Height",720,480,4320);
    windowed=integer("Display","Windowed",1,0,1);
    deadzone=integer("Input","Deadzone",4096,0,30000);
    backgroundInput=integer("Input","Background",0,0,1);
    controllerIndex=integer("Input","ControllerIndex",0,0,15);
    startButton=integer("Input","StartButton",startButton,0,SDL_GAMEPAD_BUTTON_COUNT-1);
    viewButton=integer("Input","ViewButton",viewButton,0,SDL_GAMEPAD_BUTTON_COUNT-1);
    handButton=integer("Input","HandbrakeButton",handButton,0,SDL_GAMEPAD_BUTTON_COUNT-1);
    upButton=integer("Input","ShiftUpButton",upButton,0,SDL_GAMEPAD_BUTTON_COUNT-1);
    downButton=integer("Input","ShiftDownButton",downButton,0,SDL_GAMEPAD_BUTTON_COUNT-1);
    freeplay=integer("Game","Freeplay",1,0,1);
    cores=integer("Runtime","Cores",4,0,32);
    if(cores && GetProcessAffinityMask(GetCurrentProcess(),&available,&systemMask)) {
        for(i=0,n=0;i<32 && n<cores;i++) if(available&((DWORD_PTR)1<<i)){chosen|=(DWORD_PTR)1<<i;n++;}
        if(chosen && !SetProcessAffinityMask(GetCurrentProcess(),chosen)) logline("Affinity failed: %lu\n",GetLastError());
    }
    InitializeCriticalSection(&inputLock);
    GetSystemDirectoryA(path,sizeof(path));strcat_s(path,sizeof(path),"\\dinput8.dll");
    realInput=LoadLibraryA(path);
    logline("SR3Lab initialized: %dx%d %s, SDL %d, controller index %d\n",width,height,windowed?"windowed":"fullscreen",SDL_GetVersion(),controllerIndex);
    return TRUE;
}
static void ready(void) {InitOnceExecuteOnce(&once,initialize,NULL,NULL);}
static int key(int vk) {return (GetAsyncKeyState(vk)&0x8000)!=0;}
static unsigned trigger(Sint16 v) {return v>0?((unsigned)v*255+16383)/32767:0;}
static BOOL WINAPI cabinetRead(HANDLE file,LPVOID data,DWORD size,LPDWORD read,LPOVERLAPPED overlapped) {
    Sr3Input in={0}; DWORD now,pid=0; SDL_Event event; int active; static int coinWasDown;
    (void)file;(void)overlapped;
    if(read) *read=0;
    if(!data || size!=15){SetLastError(ERROR_INVALID_PARAMETER);return FALSE;}
    ready();
    /* This call runs on the game's input thread. SDL is owned by that thread. */
    EnterCriticalSection(&inputLock);
    if(!sdlStarted){
        SDL_SetMainReady();
        SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS,"1");
        sdlStarted=SDL_Init(SDL_INIT_GAMEPAD)?1:-1;
        if(sdlStarted>0){findPad();logline("SDL controller polling ready\n");}
        else logline("SDL controller init failed: %s (keyboard still available)\n",SDL_GetError());
    }
    now=GetTickCount();
    if(sdlStarted>0){
        while(SDL_PollEvent(&event)){}
        if(pad && !SDL_GamepadConnected(pad)){logline("Controller disconnected\n");SDL_CloseGamepad(pad);pad=NULL;lastSearch=0;}
        if(!pad && (DWORD)(now-lastSearch)>=1000){lastSearch=now;findPad();}
    }
    GetWindowThreadProcessId(GetForegroundWindow(),&pid);
    active=backgroundInput || pid==GetCurrentProcessId();
    if(active){
        if(pad){
            in.steering=SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_LEFTX);
            in.gas=trigger(SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_RIGHT_TRIGGER));
            in.brake=trigger(SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_LEFT_TRIGGER));
            if(SDL_GetGamepadButton(pad,(SDL_GamepadButton)startButton)) in.buttons|=SR3_START;
            if(SDL_GetGamepadButton(pad,(SDL_GamepadButton)viewButton)) in.buttons|=SR3_VIEW;
            if(SDL_GetGamepadButton(pad,(SDL_GamepadButton)handButton)) in.buttons|=SR3_HANDBRAKE;
            if(SDL_GetGamepadButton(pad,(SDL_GamepadButton)upButton) || SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_RIGHTY)<-16384) in.buttons|=SR3_UP;
            if(SDL_GetGamepadButton(pad,(SDL_GamepadButton)downButton) || SDL_GetGamepadAxis(pad,SDL_GAMEPAD_AXIS_RIGHTY)>16384) in.buttons|=SR3_DOWN;
            if(SDL_GetGamepadButton(pad,SDL_GAMEPAD_BUTTON_DPAD_LEFT))in.steering=-32768;
            if(SDL_GetGamepadButton(pad,SDL_GAMEPAD_BUTTON_DPAD_RIGHT))in.steering=32767;
        }
        if(key(VK_LEFT))in.steering=-32768;
        if(key(VK_RIGHT))in.steering=32767;
        if(key(VK_UP))in.gas=255;
        if(key(VK_DOWN))in.brake=255;
        if(key(VK_RETURN))in.buttons|=SR3_START;
        if(key('V'))in.buttons|=SR3_VIEW;
        if(key(VK_SPACE))in.buttons|=SR3_HANDBRAKE;
        if(key('E'))in.buttons|=SR3_UP;
        if(key('Q'))in.buttons|=SR3_DOWN;
        if(!freeplay && key('5') && !coinWasDown && *(volatile unsigned char*)0xb41748<255) ++*(volatile unsigned char*)0xb41748;
        coinWasDown=key('5');
    } else coinWasDown=0;
    sr3_report(data,&in,deadzone);
    if((DWORD)(now-lastReportLog)>=5000){lastReportLog=now;logline("Input alive: focus=%d pad=%d steering=%d gas=%u brake=%u buttons=%02x\n",active,pad!=NULL,in.steering,in.gas,in.brake,in.buttons);}
    if(read)*read=15;
    LeaveCriticalSection(&inputLock);
    /* Pace the HID reader which otherwise spins on a synchronous virtual device. */
    Sleep(4);
    return TRUE;
}

HRESULT WINAPI DirectInput8Create(HINSTANCE instance,DWORD version,REFIID iid,LPVOID *out,LPVOID outer) {
    typedef HRESULT(WINAPI *Fn)(HINSTANCE,DWORD,REFIID,LPVOID*,LPVOID);
    Fn fn; ready();fn=realInput?(Fn)GetProcAddress(realInput,"DirectInput8Create"):NULL;
    return fn?fn(instance,version,iid,out,outer):E_FAIL;
}
void WINAPI Out32(short port,short value) {(void)port;InterlockedExchange(&outputCommand,(unsigned short)value);}
DWORD WINAPI SR3LabGetOutput(void) {return (DWORD)InterlockedCompareExchange(&outputCommand,0,0);}
static HMODULE WINAPI loadLibrary(LPCSTR name) {
    if(name && (!_stricmp(name,"./inpout32.dll") || !_stricmp(name,".\\inpout32.dll") || !_stricmp(name,"inpout32.dll"))) {
        /* Game only resolves Out32; keep all cabinet output in this user-mode DLL. */
        HMODULE retained=NULL;
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,(LPCSTR)(uintptr_t)Out32,&retained);
        return retained;
    }
    return LoadLibraryA(name);
}
static UINT WINAPI profileInt(LPCSTR section,LPCSTR keyName,INT def,LPCSTR filename) {
    ready();
    if(section && keyName){
        if(!_stricmp(section,"Graphics")){
            if(!_stricmp(keyName,"HorizontalResolution"))return width;
            if(!_stricmp(keyName,"VerticalResolution"))return height;
        }
        if(!_stricmp(keyName,"Freeplay"))return freeplay;
        if(!_stricmp(section,"CalibrationData")){
            if(!_stricmp(keyName,"AccelUp") || !_stricmp(keyName,"BrakeUp") || !_stricmp(keyName,"SteeringLeft"))return 0;
            if(!_stricmp(keyName,"AccelDown") || !_stricmp(keyName,"BrakeDown") || !_stricmp(keyName,"SteeringRight"))return 255;
        }
        if(!_stricmp(section,"Network") && !_stricmp(keyName,"Enabled"))return 0;
    }
    return GetPrivateProfileIntA(section,keyName,def,filename);
}
static HANDLE WINAPI createFile(LPCSTR name,DWORD access,DWORD sharing,LPSECURITY_ATTRIBUTES sa,DWORD how,DWORD flags,HANDLE templ) {
    char path[MAX_PATH]; const char *base=name?strrchr(name,'\\'):NULL;
    if(base && (strstr(name,"ShellData\\")!=NULL) &&
       (!_stricmp(base+1,"HighScoreData.txt") || !_stricmp(base+1,"HighScoreCounter.txt"))){
        snprintf(path,sizeof(path),"%s\\%s",saves,base+1);name=path;
    }
    return CreateFileA(name,access,sharing,sa,how,flags,templ);
}
static LRESULT CALLBACK windowProc(HWND w,UINT msg,WPARAM wp,LPARAM lp) {
    if(msg==WM_KEYDOWN && wp==VK_ESCAPE){PostMessageA(w,WM_CLOSE,0,0);return 0;}
    return CallWindowProcA(oldWindowProc,w,msg,wp,lp);
}
static HWND WINAPI createWindow(DWORD ex,LPCSTR cls,LPCSTR title,DWORD style,int x,int y,int w,int h,HWND parent,HMENU menu,HINSTANCE instance,LPVOID arg) {
    HWND result;int ours=(uintptr_t)cls>65535 && !strcmp(cls,"RacingClass");ready();
    if(ours){
        RECT r={0,0,width,height};style=windowed?WS_OVERLAPPEDWINDOW:WS_POPUP;
        AdjustWindowRectEx(&r,style,FALSE,ex);w=r.right-r.left;h=r.bottom-r.top;
        x=windowed?40:0;y=windowed?40:0;parent=NULL;title="SEGA Rally 3 - SR3Lab";
    }
    result=CreateWindowExA(ex,cls,title,style,x,y,w,h,parent,menu,instance,arg);
    if(ours && result){gameWindow=result;oldWindowProc=(WNDPROC)SetWindowLongPtrA(result,GWLP_WNDPROC,(LONG_PTR)windowProc);}
    return result;
}
static BOOL WINAPI clipCursor(const RECT *rect) {(void)rect;return TRUE;}
static BOOL WINAPI cursorPosition(int x,int y) {(void)x;(void)y;return TRUE;}
static HCURSOR WINAPI setCursor(HCURSOR cursor) {return SetCursor(cursor?cursor:LoadCursorA(NULL,IDC_ARROW));}
static void presentation(D3DPRESENT_PARAMETERS *p) {
    p->BackBufferWidth=width;p->BackBufferHeight=height;
    if(windowed){p->Windowed=TRUE;p->FullScreen_RefreshRateInHz=0;}
}
static HRESULT WINAPI resetDevice(IDirect3DDevice9 *self,D3DPRESENT_PARAMETERS *p) {presentation(p);return systemReset(self,p);}
static HRESULT WINAPI createDevice(IDirect3D9 *self,UINT adapter,D3DDEVTYPE type,HWND window,DWORD flags,D3DPRESENT_PARAMETERS *p,IDirect3DDevice9 **out) {
    HRESULT hr;presentation(p);hr=systemCreateDevice(self,adapter,type,window,flags,p,out);
    logline("D3D CreateDevice: 0x%08lx %ux%u windowed=%d\n",(unsigned long)hr,p->BackBufferWidth,p->BackBufferHeight,p->Windowed);
    if(SUCCEEDED(hr) && out && *out){
        if((*out)->lpVtbl->Reset!=resetDevice){systemReset=(*out)->lpVtbl->Reset;replacePointer((void*)&(*out)->lpVtbl->Reset,resetDevice);}
        ShowWindow(window,SW_SHOW);
    }
    return hr;
}
static IDirect3D9 *WINAPI create9(UINT sdk) {
    IDirect3D9 *result;ready();result=systemCreate9(sdk);
    if(result && result->lpVtbl->CreateDevice!=createDevice){systemCreateDevice=result->lpVtbl->CreateDevice;replacePointer((void*)&result->lpVtbl->CreateDevice,createDevice);}
    return result;
}
static int WINAPI message(HWND window,LPCSTR text,LPCSTR title,UINT flags) {logline("%s: %s\n",title?title:"Message",text?text:"");return MessageBoxA(window,text,title,flags);}

BOOL WINAPI DllMain(HINSTANCE self,DWORD reason,LPVOID reserved) {
    unsigned char *base;IMAGE_NT_HEADERS *pe;char path[MAX_PATH];
    const unsigned char yes[]={0xb8,1,0,0,0,0xc3};
    const unsigned char nops[15]={0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90,0x90};
    (void)reserved;
    if(reason!=DLL_PROCESS_ATTACH)return TRUE;
    module=self;DisableThreadLibraryCalls(self);
    GetModuleFileNameA(self,root,sizeof(root));
    if(!strrchr(root,'\\'))return FALSE;*strrchr(root,'\\')=0;
    snprintf(config,sizeof(config),"%s\\sr3lab.ini",root);
    snprintf(saves,sizeof(saves),"%s\\SR3LabSave",root);CreateDirectoryA(saves,NULL);
    snprintf(path,sizeof(path),"%s\\sr3lab.log",root);
    logfile=CreateFileA(path,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    base=(unsigned char*)GetModuleHandleA(NULL);
    pe=(IMAGE_NT_HEADERS*)(base+((IMAGE_DOS_HEADER*)base)->e_lfanew);
    if((uintptr_t)base!=0x400000 || pe->FileHeader.Machine!=IMAGE_FILE_MACHINE_I386 ||
       pe->OptionalHeader.SizeOfImage!=0x750000 || crc32(base+0x1000,0x273000)!=0xdd097484){
        logline("REFUSED: unsupported or already modified Rally.exe. No game patches applied.\n");return FALSE;
    }
    /* Complete text identity was checked above, before any mutation. No SEGA code is shipped. */
    if(!writeMemory((void*)0x57b2f0,yes,sizeof(yes)) ||
       !writeMemory((void*)0x57b670,nops,15) || !writeMemory((void*)0x57b684,nops,3) ||
       !replacePointer((void*)0x57b696,&cabinetReadPointer))return FALSE;
    systemCreate9=*(void**)0x674380;
    if(!replacePointer((void*)0x674380,create9) || !replacePointer((void*)0x674200,loadLibrary) ||
       !replacePointer((void*)0x6741d8,profileInt) || !replacePointer((void*)0x6740f8,createFile) ||
       !replacePointer((void*)0x6742cc,createWindow) || !replacePointer((void*)0x674280,clipCursor) ||
       !replacePointer((void*)0x674278,cursorPosition) || !replacePointer((void*)0x674270,setCursor) ||
       !replacePointer((void*)0x67426c,message))return FALSE;
    logline("SR3Lab attached: supported text CRC dd097484. Process %lu.\n",GetCurrentProcessId());
    return TRUE;
}
