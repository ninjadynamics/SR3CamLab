"""Compile our paired shader and generate its header; no game access required."""
from pathlib import Path
import ctypes as C, struct, hashlib, json
HERE=Path(__file__).resolve().parent
# Identities audited from the supported game's T_Lpse_Tdnl_Sds technique.
ORIGINAL = {'vs': {'bytes': 1936, 'sha256': '46612cf059d2259679a2e448335c33b5cc0d238a24819bdc0adfd8e2aa189f7f'}, 'ps': {'bytes': 1760, 'sha256': 'c12c105798dc05db66a18390bb20b5e251ebff03da1d349ab435cf8f005447be'}}

def data(p):
 vt=C.cast(C.cast(p,C.POINTER(C.c_void_p))[0],C.POINTER(C.c_void_p))
 ptr=C.WINFUNCTYPE(C.c_void_p,C.c_void_p)(vt[3])(p)
 n=C.WINFUNCTYPE(C.c_size_t,C.c_void_p)(vt[4])(p)
 raw=C.string_at(ptr,n);C.WINFUNCTYPE(C.c_ulong,C.c_void_p)(vt[2])(p);return raw

def compile_shader(source,profile):
 fn=C.WinDLL('d3dcompiler_47.dll').D3DCompile
 fn.argtypes=[C.c_void_p,C.c_size_t,C.c_char_p,C.c_void_p,C.c_void_p,C.c_char_p,C.c_char_p,C.c_uint,C.c_uint,C.POINTER(C.c_void_p),C.POINTER(C.c_void_p)]
 fn.restype=C.c_long;raw=source.encode();code=C.c_void_p();errors=C.c_void_p()
 hr=fn(raw,len(raw),b'URL-POM',None,None,b'main',profile.encode(),1<<15,0,C.byref(code),C.byref(errors))
 msg=data(errors).decode(errors='replace') if errors.value else ''
 if hr<0:raise RuntimeError(msg)
 return data(code)

def generate():
 header='/* Generated from our HLSL. Original game code is NOT embedded. */\n';result={}
 for kind,name in [('vs','pom_vs.hlsl'),('ps','pom.hlsl')]:
  blob=compile_shader((HERE/'shaders'/name).read_text(),kind+'_3_0')
  words=struct.unpack('<%dI'%(len(blob)//4),blob)
  header+='static const DWORD sr3_pom_'+kind+'_code[] = {\n'+''.join(','.join('0x%08xu'%v for v in words[i:i+8])+',\n' for i in range(0,len(words),8))+'};\n'
  header+='static const BYTE sr3_pom_original_'+kind+'_hash[32] = {'+','.join('0x%02x'%x for x in bytes.fromhex(ORIGINAL[kind]['sha256']))+'};\n'
  header+='#define SR3_POM_ORIGINAL_'+kind.upper()+'_SIZE '+str(ORIGINAL[kind]['bytes'])+'u\n'
  result[kind]={'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}
 return header,result
if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');args=a.parse_args()
 header,result=generate();target=HERE/'pom_bytecode.h'
 if args.check:
  if not target.exists() or target.read_text()!=header:raise SystemExit('POM header stale; run compile_pom.py')
 else:target.write_text(header)
 print(json.dumps(result,indent=2))
