/* Synthetic sr3mods front for test_play.ps1; never opens another process. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
    char path[1024],code[32];int i;FILE *f;
    if(!GetEnvironmentVariableA("SR3_PLAY_TEST_LOG",path,sizeof path))return 91;
    f=fopen(path,"wb");if(!f)return 92;
    for(i=1;i<argc;i++)fprintf(f,"%s\n",argv[i]);fclose(f);
    return GetEnvironmentVariableA("SR3_PLAY_TEST_EXIT",code,sizeof code)?atoi(code):0;
}
