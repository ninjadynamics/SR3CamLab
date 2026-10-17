/* Shared texture replacement during the game's attract transition. MIT. */
#ifndef SR3_TEXTURE_REBIND_H
#define SR3_TEXTURE_REBIND_H
#include <stddef.h>
#include <stdint.h>
typedef struct {
    uint32_t resource, next, kind_size, reserved[2];
} Sr3ResourceDescriptor;
static size_t sr3_rebind_texture(Sr3ResourceDescriptor *pool,size_t count,uint32_t old,uint32_t replacement){
    size_t i,changed=0;
    if(!old || !replacement || old==replacement)return 0;
    for(i=0;i<count;i++){
        if((pool[i].kind_size>>28)==5 && pool[i].resource==old){
            pool[i].resource=replacement;changed++;
        }
    }
    return changed;
}
void sr3_texture_rebind_hook(void);
#endif
