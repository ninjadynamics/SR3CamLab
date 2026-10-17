/* Define only the documented COM identifier used by SDL's file-dialog code.
 * Windows headers supply its value; no Windows binary data is copied. MIT.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <initguid.h>
DEFINE_GUID(IID_IShellItem,0x43826d1e,0xe718,0x42ee,0xbc,0x55,0xa1,0xe2,0x61,0xc3,0x7b,0xfe);
