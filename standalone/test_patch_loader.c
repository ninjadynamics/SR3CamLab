#define WIN32_LEAN_AND_MEAN
#include "patch_loader.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
    char error[512]="",acp[4096];WCHAR wide[4096];int result;
    if(argc!=4)return 2;
    /* test_entry uses UTF-8 argv; the production launcher uses Win32 ACP. */
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,argv[3],-1,wide,4096) ||
       !WideCharToMultiByte(CP_ACP,0,wide,-1,acp,sizeof(acp),NULL,NULL))return 3;
    result=sr3_load_patches(NULL,acp,atoi(argv[1]),error,sizeof(error));
    printf("Patch loader: result=%d %s\n",result,error);
    return result==atoi(argv[2])?0:1;
}
