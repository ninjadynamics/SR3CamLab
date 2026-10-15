/* pc_host: the world outside the game's memory for pc_live, the same for patches.ps1 and both front ends (patches.dll
 * inside the game, sr3mods.exe outside): the clock, the pad, the keys, the window in front, the screen grab.
 *   pad:  XInput pad 0 (xinput1_4.dll, as patches.ps1's Sr3Pad; 1_3 / 9_1_0 where 1_4 is missing), 0 without one.
 *   shot: the whole primary screen through GDI (patches.ps1's CopyFromScreen), PNG by WIC (Windows' own codecs), the
 *         shot's JSON in a tEXt chunk "SR3Lab" after IHDR (Add-PngText). GDI sees the desktop: a game in exclusive
 *         fullscreen can come out black from inside or outside alike (windowed / borderless is fine).
 * This can actually be done with stb_image_write the following way:
 *     stbi_write_png(path, w, h, 4, bgra, w * 4);      (after swapping B and R)
 * it's done with WIC because it ships with Windows (nothing to vendor: lean), runs SIMD-optimised zlib, and its encoder
 * takes the BGR rows GDI gives without a copy. */
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <objbase.h>
#include <wincodec.h>
#include <stdlib.h>
#include <string.h>
#include "patchcore.h"

long long ph_now(GameMem *m) { FILETIME u, l; (void)m; GetSystemTimeAsFileTime(&u); FileTimeToLocalFileTime(&u, &l); return ((long long)l.dwHighDateTime << 32) | l.dwLowDateTime; }
void ph_sleep(GameMem *m, int ms) { (void)m; Sleep((DWORD)ms); }
typedef struct { DWORD packet; WORD buttons; BYTE lt, rt; SHORT lx, ly, rx, ry; } XState;
typedef DWORD (WINAPI *XGet)(DWORD, XState *);
unsigned ph_pad(GameMem *m) {
    static XGet get; static int tried; XState s;
    (void)m;
    if (!tried) {
        static const char *const dll[3] = {"xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"}; int i; tried = 1;
        for (i = 0; i < 3 && !get; i++) { HMODULE h = LoadLibraryA(dll[i]); if (h) get = (XGet)(void (*)(void))GetProcAddress(h, "XInputGetState"); }
    }
    memset(&s, 0, sizeof s);
    return get && get(0, &s) == 0 ? s.buttons : 0;
}
int ph_key(GameMem *m, int vk) { (void)m; return (GetAsyncKeyState(vk) & 0x8000) != 0; }
unsigned ph_front(GameMem *m) { (void)m; return (unsigned)(uintptr_t)GetForegroundWindow(); }

/* ---------------------------------------------------------------- the screen grab */
static HBITMAP held; static void *bits; static int gw, gh;
static const GUID CLSID_WICImagingFactory_ = {0xcacaf262, 0x9370, 0x4615, {0xa1, 0x3b, 0x9f, 0x55, 0x39, 0xda, 0x4c, 0x0a}};
static const GUID IID_IWICImagingFactory_ = {0xec5ec8a9, 0xc395, 0x4314, {0x9c, 0x77, 0x54, 0xd7, 0xa9, 0x35, 0xff, 0x70}};
static const GUID GUID_ContainerFormatPng_ = {0x1b7cfaf4, 0x713f, 0x473c, {0xbb, 0xcd, 0x61, 0x37, 0x42, 0x5f, 0xae, 0xaf}};
static const GUID GUID_WICPixelFormat32bppBGR_ = {0x6fddc324, 0x4e03, 0x4bfe, {0xb1, 0x85, 0x3d, 0x77, 0x76, 0x8d, 0xc9, 0x0e}};
static const GUID GUID_WICPixelFormat24bppBGR_ = {0x6fddc324, 0x4e03, 0x4bfe, {0xb1, 0x85, 0x3d, 0x77, 0x76, 0x8d, 0xc9, 0x0c}};
static int grab(void) {
    HDC scr = GetDC(NULL), dc; BITMAPINFO bi; HGDIOBJ old;
    if (!scr) return 0;
    gw = GetSystemMetrics(SM_CXSCREEN); gh = GetSystemMetrics(SM_CYSCREEN);
    memset(&bi, 0, sizeof bi); bi.bmiHeader.biSize = sizeof bi.bmiHeader; bi.bmiHeader.biWidth = gw; bi.bmiHeader.biHeight = -gh;   /* top-down rows */
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
    dc = CreateCompatibleDC(scr); held = CreateDIBSection(scr, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    if (!dc || !held) { if (dc) DeleteDC(dc); ReleaseDC(NULL, scr); if (held) DeleteObject(held); held = NULL; return 0; }
    old = SelectObject(dc, held);
    BitBlt(dc, 0, 0, gw, gh, scr, 0, 0, SRCCOPY | CAPTUREBLT);
    SelectObject(dc, old); DeleteDC(dc); ReleaseDC(NULL, scr);
    return 1;
}
static unsigned crc32_(const unsigned char *p, size_t n) { unsigned c = 0xFFFFFFFFu; int k; while (n--) { c ^= *p++; for (k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1; } return ~c; }
static void be32(unsigned char *o, unsigned v) { o[0] = (unsigned char)(v >> 24); o[1] = (unsigned char)(v >> 16); o[2] = (unsigned char)(v >> 8); o[3] = (unsigned char)v; }
static int save_png(const char *path, const char *info) {
    IWICImagingFactory *f = NULL; IWICBitmap *bmp = NULL; IWICBitmapEncoder *enc = NULL; IWICBitmapFrameEncode *fr = NULL; IStream *st = NULL;
    HGLOBAL hg; unsigned char *png; SIZE_T n; int ok = 0; HRESULT hr; WICPixelFormatGUID pf = GUID_WICPixelFormat24bppBGR_; HRESULT co = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    if (!held) return 0;
    hr = CoCreateInstance(&CLSID_WICImagingFactory_, NULL, CLSCTX_INPROC_SERVER, &IID_IWICImagingFactory_, (void **)&f);
    if (SUCCEEDED(hr)) hr = IWICImagingFactory_CreateBitmapFromMemory(f, (UINT)gw, (UINT)gh, &GUID_WICPixelFormat32bppBGR_, (UINT)gw * 4, (UINT)gw * 4 * (UINT)gh, (BYTE *)bits, &bmp);
    if (SUCCEEDED(hr)) hr = CreateStreamOnHGlobal(NULL, TRUE, &st);
    if (SUCCEEDED(hr)) hr = IWICImagingFactory_CreateEncoder(f, &GUID_ContainerFormatPng_, NULL, &enc);
    if (SUCCEEDED(hr)) hr = IWICBitmapEncoder_Initialize(enc, st, WICBitmapEncoderNoCache);
    if (SUCCEEDED(hr)) hr = IWICBitmapEncoder_CreateNewFrame(enc, &fr, NULL);
    if (SUCCEEDED(hr)) hr = IWICBitmapFrameEncode_Initialize(fr, NULL);
    if (SUCCEEDED(hr)) hr = IWICBitmapFrameEncode_SetSize(fr, (UINT)gw, (UINT)gh);
    if (SUCCEEDED(hr)) hr = IWICBitmapFrameEncode_SetPixelFormat(fr, &pf);
    if (SUCCEEDED(hr)) hr = IWICBitmapFrameEncode_WriteSource(fr, (IWICBitmapSource *)bmp, NULL);
    if (SUCCEEDED(hr)) hr = IWICBitmapFrameEncode_Commit(fr);
    if (SUCCEEDED(hr)) hr = IWICBitmapEncoder_Commit(enc);
    if (SUCCEEDED(hr) && SUCCEEDED(GetHGlobalFromStream(st, &hg)) && (png = (unsigned char *)GlobalLock(hg))) {
        wchar_t w[1100]; HANDLE fh; DWORD wr_;
        n = GlobalSize(hg);
        { STATSTG s; if (SUCCEEDED(IStream_Stat(st, &s, STATFLAG_NONAME))) n = (SIZE_T)s.cbSize.QuadPart; }
        MultiByteToWideChar(CP_UTF8, 0, path, -1, w, 1100);
        fh = CreateFileW(w, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (fh != INVALID_HANDLE_VALUE) {
            ok = WriteFile(fh, png, 33, &wr_, NULL);                                          /* signature + IHDR */
            if (info && n > 33 && !memcmp(png + 12, "IHDR", 4)) {                             /* tEXt "SR3Lab": Latin-1, as Add-PngText */
                size_t L = strlen(info), k = 0; unsigned char *c = (unsigned char *)malloc(2 * L + 24); const unsigned char *s = (const unsigned char *)info;
                memcpy(c + 4, "tEXtSR3Lab", 10); k = 14; c[k++] = 0;                         /* length, type, keyword, 0, text, CRC */
                while (*s) {
                    unsigned cp = *s++;
                    if (cp >= 0x80) { int more = cp >= 0xF0 ? 3 : cp >= 0xE0 ? 2 : 1; cp &= 0x3Fu >> more; while (more-- && (*s & 0xC0) == 0x80) cp = cp << 6 | (*s++ & 0x3F); }
                    if (cp > 0xFFFF) c[k++] = '?';                                           /* (two UTF-16 units: two '?', as .NET's Latin-1) */
                    c[k++] = cp <= 0xFF ? (unsigned char)cp : '?';
                }
                be32(c, (unsigned)(k - 8)); be32(c + k, crc32_(c + 4, k - 4));
                ok = ok && WriteFile(fh, c, (DWORD)(k + 4), &wr_, NULL); free(c);
            }
            ok = ok && WriteFile(fh, png + 33, (DWORD)(n - 33), &wr_, NULL);
            CloseHandle(fh);
        }
        GlobalUnlock(hg);
    }
    if (fr) IWICBitmapFrameEncode_Release(fr);
    if (enc) IWICBitmapEncoder_Release(enc);
    if (st) IStream_Release(st);
    if (bmp) IWICBitmap_Release(bmp);
    if (f) IWICImagingFactory_Release(f);
    if (SUCCEEDED(co)) CoUninitialize();
    return ok;
}
int ph_shot(GameMem *m, int act, const char *path, const char *info) {
    (void)m;
    if (act == 1) { if (held) DeleteObject(held); held = NULL; return grab(); }
    if (act == 2) return save_png(path, info);
    if (held) DeleteObject(held);
    held = NULL; return 1;
}
