/* Copyright (c) 2026 Ninja Dynamics. MIT.
 * C99 stdio entry points which are inline/compatibility-library functions in
 * Windows SDKs, rather than exports of the 32-bit Windows UCRT DLL.
 * The OS UCRT owns FILE, locale, allocation and thread state. No private CRT.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <corecrt_stdio_config.h>

int vsnprintf(char *buffer,size_t size,const char *format,va_list args) {
    return __stdio_common_vsprintf(_CRT_INTERNAL_PRINTF_STANDARD_SNPRINTF_BEHAVIOR,buffer,size,format,NULL,args);
}
int snprintf(char *buffer,size_t size,const char *format,...) {
    int result;va_list args;va_start(args,format);
    result=vsnprintf(buffer,size,format,args);va_end(args);return result;
}
int vfprintf(FILE *file,const char *format,va_list args) {
    return __stdio_common_vfprintf(0,file,format,NULL,args);
}
int fprintf(FILE *file,const char *format,...) {
    int result;va_list args;va_start(args,format);
    result=vfprintf(file,format,args);va_end(args);return result;
}
int printf(const char *format,...) {
    int result;va_list args;va_start(args,format);
    result=vfprintf(stdout,format,args);va_end(args);return result;
}
int vsscanf(const char *text,const char *format,va_list args) {
    return __stdio_common_vsscanf(0,text,(size_t)-1,format,NULL,args);
}
char *itoa(int value,char *buffer,int radix) {return _itoa(value,buffer,radix);}
