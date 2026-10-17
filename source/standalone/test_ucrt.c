#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <stdint.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"UCRT check failed at line %d: %s\n",__LINE__,#x);return 1;}}while(0)
static int scan(const char *text,const char *fmt,...){int r;va_list a;va_start(a,fmt);r=vsscanf(text,fmt,a);va_end(a);return r;}
int main(void){
    char small[4],large[128];unsigned long long u=0;int n=0;float f=0;FILE *file;
    CHECK(snprintf(small,sizeof(small),"hello%d",12)==7);
    CHECK(!memcmp(small,"hel\0",4));
    CHECK(snprintf(NULL,0,"hello%d",12)==7);
    CHECK(snprintf(large,sizeof(large),"%llu / %lld",UINT64_MAX,INT64_MIN)==43);
    CHECK(!strcmp(large,"18446744073709551615 / -9223372036854775808"));
    CHECK(scan("18446744073709551615 -9 0.25","%llu %d %f",&u,&n,&f)==3);
    CHECK(u==UINT64_MAX && n==-9 && f==0.25f);
    file=tmpfile();CHECK(file);
    CHECK(fprintf(file,"value=%d",42)==8);rewind(file);
    CHECK(fgets(large,sizeof(large),file)!=NULL);CHECK(!strcmp(large,"value=42"));fclose(file);
    puts("UCRT bridge: truncation, size query, 64-bit formatting, scanning and file output pass.");return 0;
}
