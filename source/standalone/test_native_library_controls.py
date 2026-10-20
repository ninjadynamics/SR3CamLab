from pathlib import Path
import sys,types,struct,shutil
r=Path(r'F:\Jogos\Ultimate Race Lab');s=r/'source/standalone';o=r/'scratchpad/pom-native-library-20261020'
sys.path[:0]=[str(s),str(r/'source/tools/import/core')];import native_build as nb,sbfw

f=sbfw.read_sbf(str(o/'shaderlib3_uber_data.sbf'))
for c in f.kinds(3):
 name='controls' if c.id==0xc1b0f001 else 'uber'
 (o/(name+'.fixture')).write_bytes(struct.pack('<II',len(c.data),len(c.fix))+struct.pack('<%dI'%len(c.fix),*c.fix)+c.data)
args=types.SimpleNamespace(out=o/'runtime',gcc='C:/mingw64/bin/gcc.exe',jobs=4,sdl_source=r/'toolchain/deps/SDL',raylib_source=r/'toolchain/deps/raylib');b=nb.Build(args)
sources=[(n,s/n) for n in ['test_pom_native.c','pom_native.c','test_entry.c','ucrt_stdio.c']]+[('builtins.c',r/'source/tools/x86/builtins.c')]
objs=b.compile('native-controls-test',sources,b.x86+['-I'+str(s),'-DPOM_REGISTRY_BASE=0x30000000u'],b.own_headers);exe=b.link32('test_pom_native.exe',objs,'_test_entry')
result=nb.run([exe],cwd=o);(o/'controls-test.log').write_text(result);print(result)
