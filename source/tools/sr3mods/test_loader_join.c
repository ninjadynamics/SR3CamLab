/* Real x86 Windows regression of the captured second-race circular wait.
   This creates a hidden test window, never starts Rally or displays a UI. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "patchcore.h"
#include "loader_join.h"

static unsigned char site[20], native[71];
static unsigned writes, read_fail, write_fail;
static int read_mock(GameMem *m, unsigned va, void *dst, unsigned n) {
    unsigned i; const unsigned char *p; (void)m;
    if (read_fail) return 0;
    if (va==LOADER_JOIN_SITE && n==20) p=site;
    else if (va==LOADER_NATIVE_JOIN && n==71) p=native;
    else return 0;
    for (i=0;i<n;++i) ((unsigned char *)dst)[i]=p[i];
    return 1;
}
static int write_mock(GameMem *m, unsigned va, const void *src, unsigned n, int keep) {
    unsigned i; (void)m; ++writes;
    if (va!=LOADER_JOIN_SITE || n!=20 || keep || write_fail) return 0;
    for (i=0;i<n;++i) site[i]=((const unsigned char *)src)[i];
    return 1;
}
static GameMem memory = {read_mock,write_mock};
static void reset_bytes(void) {
    unsigned i;
    for (i=0;i<20;++i) site[i]=loader_join_original[i];
    for (i=0;i<71;++i) native[i]=loader_native_join_original[i];
    writes=read_fail=write_fail=0;
}
#define CHECK(condition, code) do { if (!(condition)) ExitProcess(code); } while (0)
static volatile LONG received, dispatched_keys, worker_done;
static __attribute__((used)) volatile unsigned observed_native_exit;
static HWND receiver;
static HANDLE ready;
static DWORD WINAPI sender(LPVOID arg) {
    COPYDATASTRUCT cd; unsigned payload=0x12345678u; (void)arg;
    cd.dwData=0x51u; cd.cbData=sizeof payload; cd.lpData=&payload;
    SetEvent(ready);
    if (SendMessageA(receiver, WM_COPYDATA, 0, (LPARAM)&cd)!=0xA6) return 92;
    InterlockedExchange(&worker_done,1);
    return 0x1357;
}
static DWORD WINAPI already_done(LPVOID arg) { (void)arg; return 0x2468; }
static LRESULT CALLBACK receive(HWND w, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg==WM_COPYDATA) {
        COPYDATASTRUCT *cd=(COPYDATASTRUCT *)lp;
        if (cd->dwData==0x51u && cd->cbData==4 && *(unsigned *)cd->lpData==0x12345678u) {
            InterlockedIncrement(&received); return 0xA6;
        }
        return 0;
    }
    if (msg==WM_KEYDOWN) InterlockedIncrement(&dispatched_keys);
    return DefWindowProcA(w,msg,wp,lp);
}
/* Exercise the actual DLL thunk, its register ABI and the original native
   join bytes, including the real GetExitCodeThread/CloseHandle calls. */
static __attribute__((naked)) unsigned invoke_join(unsigned *group) {
    __asm__ __volatile__(
        "pushl %ebx\n\tpushl %esi\n\tpushl %edi\n\tpushl %ebp\n\t"
        "movl 20(%esp), %esi\n\t"
        "movl $0x11223344, %ebx\n\tmovl $0x22334455, %edi\n\t"
        "movl $0x33445566, %ebp\n\tmovl $0x44556677, %ecx\n\t"
        "call _loader_join_thunk\n\t"
        "movl %ecx, _observed_native_exit\n\t"
        "cmpl $0x11223344, %ebx\n\tjne 1f\n\t"
        "cmpl $0x22334455, %edi\n\tjne 1f\n\t"
        "cmpl $0x33445566, %ebp\n\tjne 1f\n\t"
        "cmpl 20(%esp), %esi\n\tjne 1f\n\t"
        "xorl %eax, %eax\n\tjmp 2f\n\t1: movl $1, %eax\n\t"
        "2: popl %ebp\n\tpopl %edi\n\tpopl %esi\n\tpopl %ebx\n\tret\n\t");
}
/* A bounded external watchdog prevents a regression from hanging the build.
   Only the hidden test process can be exited; the game is never involved. */
static DWORD WINAPI timeout_guard(LPVOID arg) {
    (void)arg; Sleep(15000); ExitProcess(93); return 0;
}
void loader_test_entry(void) {
    unsigned i,j,rel,group[3]; DWORD flags,tid; HANDLE thread,guard;
    WNDCLASSA wc={0}; MSG message;
    reset_bytes(); CHECK(loader_install_message_wait(&memory)==1 && writes==1,1);
    CHECK(loader_install_message_wait(&memory)==2 && writes==1,2);
    for (i=0;i<20;++i) if ((i<6) || (i>=10 && i<16)) CHECK(site[i]==loader_join_original[i],3);
    for (i=5;i<20;i+=10) {
        rel=0; for(j=0;j<4;++j) rel|=(unsigned)site[i+1+j]<<(j*8);
        CHECK(LOADER_JOIN_SITE+i+5+rel==(unsigned)(uintptr_t)loader_join_thunk,4);
    }
    reset_bytes(); read_fail=1; CHECK(!loader_install_message_wait(&memory) && !writes,5);
    reset_bytes(); write_fail=1; CHECK(!loader_install_message_wait(&memory) && writes==1,6);
    CHECK(loader_bytes_equal(site,loader_join_original,20),7);
    for(i=0;i<20;++i) {
        reset_bytes(); site[i]^=1; CHECK(!loader_install_message_wait(&memory) && !writes,8);
    }
    for(i=0;i<71;++i) {
        reset_bytes(); native[i]^=1; CHECK(!loader_install_message_wait(&memory) && !writes,9);
    }
    /* Execute the guarded native success path in otherwise unused test VA. */
    CHECK(VirtualAlloc((void *)0x580000,0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE)==(void *)0x580000,10);
    CHECK(VirtualAlloc((void *)0x670000,0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)==(void *)0x670000,11);
    for(i=0;i<71;++i) ((unsigned char *)LOADER_NATIVE_JOIN)[i]=loader_native_join_original[i];
    *(uintptr_t *)0x6741C8=(uintptr_t)WaitForSingleObject;
    *(uintptr_t *)0x6741C4=(uintptr_t)GetExitCodeThread;
    *(uintptr_t *)0x674208=(uintptr_t)CloseHandle;
    FlushInstructionCache(GetCurrentProcess(),(void *)LOADER_NATIVE_JOIN,71);
    guard=CreateThread(NULL,0,timeout_guard,NULL,0,NULL); CHECK(guard!=NULL,12); CloseHandle(guard);
    wc.lpfnWndProc=receive; wc.hInstance=GetModuleHandleA(NULL); wc.lpszClassName="SR3LoaderJoinRegression";
    CHECK(RegisterClassA(&wc)!=0,13);
    receiver=CreateWindowExA(0,wc.lpszClassName,"",0,0,0,0,0,HWND_MESSAGE,NULL,wc.hInstance,NULL);
    CHECK(receiver!=NULL,14);
    ready=CreateEventA(NULL,TRUE,FALSE,NULL); CHECK(ready!=NULL,15);
    for(i=0;i<3;++i) {
        ResetEvent(ready); worker_done=0;
        CHECK(PostMessageA(receiver,WM_KEYDOWN,VK_RETURN,0x1234),16);
        thread=CreateThread(NULL,0,sender,NULL,0,&tid); CHECK(thread!=NULL,17);
        CHECK(WaitForSingleObject(ready,1000)==WAIT_OBJECT_0,18);
        /* Reproduce the old failure without waiting forever. The worker cannot
           finish until this thread services its synchronous WM_COPYDATA. */
        CHECK(WaitForSingleObject(thread,30)==WAIT_TIMEOUT,19);
        CHECK(received==(LONG)i && worker_done==0,20);
        group[0]=tid; group[1]=(unsigned)(uintptr_t)thread; group[2]=0xAABBCCDDu;
        CHECK(invoke_join(group)==0,21);
        CHECK(observed_native_exit==0x1357,32);
        CHECK(received==(LONG)i+1 && worker_done==1,22);
        CHECK(group[0]==tid && group[1]==0 && group[2]==0xAABBCCDDu,23);
        CHECK(!GetHandleInformation(thread,&flags) && GetLastError()==ERROR_INVALID_HANDLE,24);
        CHECK(dispatched_keys==0,25);
        CHECK(PeekMessageA(&message,receiver,WM_KEYDOWN,WM_KEYDOWN,PM_REMOVE) && message.wParam==VK_RETURN && message.lParam==0x1234,26);
    }
    thread=CreateThread(NULL,0,already_done,NULL,0,&tid); CHECK(thread!=NULL,27);
    CHECK(WaitForSingleObject(thread,1000)==WAIT_OBJECT_0,28);
    group[0]=tid; group[1]=(unsigned)(uintptr_t)thread;
    CHECK(invoke_join(group)==0 && group[1]==0,29);
    CHECK(observed_native_exit==0x2468,33);
    CHECK(loader_wait_for_thread(NULL)==WAIT_FAILED,30);
    CHECK(loader_wait_for_thread((HANDLE)0xDEAD)==WAIT_FAILED,31);
    CloseHandle(ready); DestroyWindow(receiver);
    ExitProcess(0);
}
