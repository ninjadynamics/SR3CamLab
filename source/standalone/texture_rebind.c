#include "texture_rebind.h"

#ifdef SR3_TEXTURE_REBIND_TEST
extern Sr3ResourceDescriptor sr3_texture_test_pool[20000];
#define TEXTURE_POOL sr3_texture_test_pool
#else
#define TEXTURE_POOL ((Sr3ResourceDescriptor*)0x813418)
#endif

/* The identity guard in runtime.c limits these addresses to the supported EXE.
   The pool contains 20,000 fixed 20-byte descriptors. The game's rebuild
   updates only its current descriptor, despite software-shared texture refs. */
void sr3_texture_rebind_apply(uint32_t old,uint32_t replacement){
    sr3_rebind_texture(TEXTURE_POOL,20000,old,replacement);
}

/* Replaces 89 45 04 57 89 02 at 0x631DE2 with CALL + NOP.
   Preserve every register and flags, reproduce both stores and the original
   PUSH EDI. Duplicate the return address so RET leaves that argument on stack.
   No COM call or refcount change: only aliases of the replaced texture move. */
#ifdef _MSC_VER
__declspec(naked) void sr3_texture_rebind_hook(void){
    __asm {
        mov [ebp+4],eax
        mov [edx],eax
        pushfd
        pushad
        push eax
        push edi
        call sr3_texture_rebind_apply
        add esp,8
        popad
        popfd
        push dword ptr [esp]
        mov [esp+4],edi
        ret
    }
}
#else
__attribute__((naked)) void sr3_texture_rebind_hook(void){
    __asm__("movl %eax,4(%ebp)\n\t"
            "movl %eax,(%edx)\n\t"
            "pushfl\n\tpushal\n\t"
            "pushl %eax\n\tpushl %edi\n\t"
            "call _sr3_texture_rebind_apply\n\t"
            "addl $8,%esp\n\tpopal\n\tpopfl\n\t"
            "pushl (%esp)\n\tmovl %edi,4(%esp)\n\tret");
}
#endif
