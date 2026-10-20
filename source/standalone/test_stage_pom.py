"""Regression for SR3 local dependency order and last-chunk root semantics."""
import struct
from stage_pom import add_dependency_before_users, sbfw

def chunk(kind, cid, refs=()):
 return sbfw.Ch(kind,cid,b''.join(struct.pack('<I',v) for v in refs),[],range(0,len(refs)*4,4))

f=sbfw.SbfFile();f.chunks=[chunk(4,1),chunk(2,2,[1,4]),chunk(12,3,[2])]
root=f.chunks[-1];original=f.chunks[:];normal=chunk(4,4)
assert add_dependency_before_users(f,normal)==3
assert [c.id for c in f.chunks]==[1,4,2,3] and f.chunks[-1] is root
assert [c for c in f.chunks if c is not normal]==original
for bad in ('duplicate','unused','forward'):
 g=sbfw.SbfFile();g.chunks=[chunk(2,2,[4]),chunk(12,3,[2])]
 n=chunk(4,4)
 if bad=='duplicate':g.chunks.insert(0,chunk(4,4))
 if bad=='unused':n=chunk(4,5)
 if bad=='forward':g.chunks.insert(0,chunk(2,1,[3]))
 try:add_dependency_before_users(g,n)
 except ValueError:pass
 else:raise AssertionError(bad+' was accepted')
print('PASS: dependency inserted before first user, root preserved, original order retained; duplicate/unused/forward references rejected.')
