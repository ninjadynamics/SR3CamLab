#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include "texture_rebind.h"

/* Test-only storage avoids a random ASLR/heap collision with the game's pool.
   The hook instructions and descriptor traversal are the production code. */
Sr3ResourceDescriptor sr3_texture_test_pool[20000];

__attribute__((naked)) static int invoke_hook(Sr3ResourceDescriptor *current,uint32_t *row,uint32_t old,uint32_t replacement){
    __asm__("pushl %ebx\n\tpushl %ebp\n\tpushl %esi\n\tpushl %edi\n\t"
            "movl 20(%esp),%edx\n\tmovl 24(%esp),%ebp\n\t"
            "movl 28(%esp),%edi\n\tmovl 32(%esp),%eax\n\t"
            "movl $0x11223344,%ebx\n\tmovl $0x55667788,%esi\n\t"
            "stc\n\tcall _sr3_texture_rebind_hook\n\tpopl %ecx\n\t"
            "jnc 1f\n\tcmpl %edi,%ecx\n\tjne 1f\n\t"
            "cmpl 32(%esp),%eax\n\tjne 1f\n\t"
            "cmpl 20(%esp),%edx\n\tjne 1f\n\t"
            "cmpl 24(%esp),%ebp\n\tjne 1f\n\t"
            "cmpl $0x11223344,%ebx\n\tjne 1f\n\t"
            "cmpl $0x55667788,%esi\n\tjne 1f\n\t"
            "movl $1,%eax\n\tjmp 2f\n\t"
            "1: xorl %eax,%eax\n\t"
            "2: popl %edi\n\tpopl %esi\n\tpopl %ebp\n\tpopl %ebx\n\tret");
}
int main(void){
    Sr3ResourceDescriptor *pool=sr3_texture_test_pool;
    uint32_t row[2]={1,0x12340000};
    pool[0].resource=pool[1].resource=pool[2].resource=0x12340000;
    pool[0].kind_size=pool[1].kind_size=0x50040000;
    pool[2].kind_size=0x60040000;
    pool[19999].resource=0x12340000;pool[19999].kind_size=0x50000000;
    if(!invoke_hook(&pool[1],row,0x12340000,0x23450000) ||
       row[1]!=0x23450000 || pool[0].resource!=0x23450000 ||
       pool[1].resource!=0x23450000 || pool[19999].resource!=0x23450000 ||
       pool[2].resource!=0x12340000 || pool[0].kind_size!=0x50040000 ||
       sr3_rebind_texture(pool,20000,0x12340000,0x23450000)!=0 ||
       sr3_rebind_texture(pool,20000,0x23450000,0)!=0){
        fputs("Texture alias or hook register/stack contract failed.\n",stderr);return 1;
    }
    puts("Texture aliases and x86 hook stack/register/flags contract passed.");return 0;
}
