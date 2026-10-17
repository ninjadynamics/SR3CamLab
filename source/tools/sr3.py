"""Helpers for reading and disassembling SEGA Rally 3's Rally.exe (v3.8.4.1).
Set SR3_EXE to the full path of Rally.exe before importing."""
import struct, re, sys, os
from capstone import *
EXE = os.environ.get("SR3_EXE", "")
if not EXE or not os.path.isfile(EXE):
    sys.exit(r"Set SR3_EXE to the full path of Rally.exe (v3.8.4.1), e.g. set SR3_EXE=C:\TeknoParrot\GAME\Sega Rally 3\Rally\Rally.exe")
data = open(EXE,'rb').read()
BASE=0x400000
# sections: (va, vsize, raw, rawsize)
SECS=[(0x1000,0x272c80,0x1000,0x273000),(0x274000,0x92066,0x274000,0x93000),(0x307000,0x44585c,0x307000,0x24000)]
def off(va):
    r=va-BASE
    for v,vs,raw,rs in SECS:
        if v<=r<v+rs: return raw+(r-v)
    return None
def rd(va,n):
    o=off(va); return data[o:o+n]
def f32(va): return struct.unpack('<f',rd(va,4))[0]
def u32(va): return struct.unpack('<I',rd(va,4))[0]
md=Cs(CS_ARCH_X86,CS_MODE_32); md.detail=False
TEXT_END=BASE+0x1000+0x272c80
def dis(va,n=60,stop_ret=False):
    code=rd(va,n*8)
    out=[]
    for i in md.disasm(code,va):
        s=f"{i.address:08x}: {i.mnemonic} {i.op_str}"
        # annotate float consts
        for m in re.findall(r'0x[0-9a-f]{6,8}',i.op_str):
            a=int(m,16)
            if 0x674000<=a<0x707000+0x24000 and off(a) is not None:
                try:
                    v=f32(a); s+=f"   ; [{m}]={v:g}"
                except: pass
            if 0x674000<=a<0x707000:
                bs=rd(a,40)
                if bs and all(32<=c<127 for c in bs[:5]):
                    s+="   ; \""+bs.split(b'\0')[0].decode('latin1')+"\""
        out.append(s)
        if len(out)>=n: break
        if stop_ret and i.mnemonic=='ret': break
    return "\n".join(out)
def find_str(s):
    b=s.encode()+b'\0'
    res=[]; i=0
    while True:
        i=data.find(b,i)
        if i<0: break
        res.append(i+BASE); i+=1  # rdata raw==rva
    return res
def xrefs(va, sec_text_only=True):
    b=struct.pack('<I',va); res=[]; i=0x1000
    end=0x1000+0x273000 if sec_text_only else len(data)
    while True:
        i=data.find(b,i,end)
        if i<0: break
        res.append(i+BASE); i+=1
    return res
def calls_to(target):
    # find E8 rel32 calls
    res=[]
    t=data[0x1000:0x274000]
    for m in re.finditer(b'\xe8',t):
        p=m.start()+0x1000
        rel=struct.unpack('<i',data[p+1:p+5])[0]
        if p+5+rel+BASE==target: res.append(p+BASE)
    return res
def func_start(va):
    # walk back to find padding CC/90 boundary followed by push/sub
    o=off(va)
    while o>0x1000:
        if data[o-1] in (0xcc,) and data[o]!=0xcc: return o+BASE
        o-=1
    return None
