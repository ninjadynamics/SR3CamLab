"""numpy's .npy / .npz files without numpy: the stack's processes hand each other their arrays in these files, and the
ones that no longer import numpy read and write them with this module, in plain Python.

An array is an Arr: dtype (numpy's descr string: '<f8' '<f4' '<i4' '<i8' '|u1' '|b1' '|V48' ...), shape (a tuple, C order)
and buf (the raw bytes: bytes, bytearray, or an mmap for big files). C helpers take Arr.ptr().

    a = npyio.load(path [, mmap=True])        d = npyio.loadz(path)       (a dict of Arr; members stored or deflated)
    npyio.save(path, a)                       npyio.savez(path, name=a, ...)   (stored, fixed timestamps: the same bytes each time)
                                              npyio.savez_compressed(path, name=a, ...)   (deflated, as np.savez_compressed)
    npyio.text(s) / npyio.string(a)           a str as np.savez stores one ('<U..', 0-d) and back
    npyio.scalar(v)                           an int / float as np.savez stores one (0-d)

numpy itself would be np.load / np.save / np.savez; it isn't used because the toolchain zip doesn't carry numpy (13 MB)
any more for the processes that are done with it. save() writes the header exactly as numpy 1.24 does (the dict repr,
padded with spaces to a multiple of 64 bytes, a newline), so a file written here is byte for byte the one np.save writes."""
import ast, ctypes, mmap as _mmap, os, struct, zipfile

ITEMSIZE = {'f8': 8, 'f4': 4, 'f2': 2, 'i8': 8, 'i4': 4, 'i2': 2, 'i1': 1, 'u8': 8, 'u4': 4, 'u2': 2, 'u1': 1, 'b1': 1}
CODE = {'f8': 'd', 'f4': 'f', 'i8': 'q', 'i4': 'i', 'i2': 'h', 'i1': 'b', 'u8': 'Q', 'u4': 'I', 'u2': 'H', 'u1': 'B', 'b1': '?'}   # struct / memoryview

_EMPTY = (ctypes.c_char * 16)()                                       # what ptr() gives for an array of no elements

def itemsize(dtype):
    k = dtype[1:]
    return int(k[1:]) if k[0] in 'VS' else (4 * int(k[1:]) if k[0] == 'U' else ITEMSIZE[k])      # ('U': numpy's text, 4 bytes a character)

def text(s):
    """a Python str as numpy stores one in an .npz (np.savez(f, k=s): a 0-d '<U<len>' array, UTF-32 little-endian)"""
    return Arr('<U%d' % max(1, len(s)), (), bytearray(s.encode('utf-32-le') or bytes(4)))

def string(a):
    """the str of such an array (str(np.load(f)[k]))"""
    return bytes(a.buf[:a.nbytes]).decode('utf-32-le').rstrip('\0')

def scalar(v):
    """a Python int or float as np.savez stores it: a 0-d array of numpy's default type for it (int32 on Windows while it fits, else
    int64; float64)"""
    if isinstance(v, float): return Arr('<f8', (), bytearray(struct.pack('<d', v)))
    return Arr('<i4', (), bytearray(struct.pack('<i', v))) if -2 ** 31 <= v < 2 ** 31 else Arr('<i8', (), bytearray(struct.pack('<q', v)))

class Arr:
    """dtype (descr), shape (tuple), buf (raw bytes, C order). Use .view() for element access, .ptr() for C."""
    __slots__ = ('dtype', 'shape', 'buf', '_keep')
    def __init__(self, dtype, shape, buf=None):
        self.dtype = dtype; self.shape = tuple(int(s) for s in shape); self._keep = None
        n = self.nbytes
        self.buf = bytearray(n) if buf is None else buf
        if len(self.buf) < n: raise ValueError('%s %s needs %d bytes, got %d' % (dtype, self.shape, n, len(self.buf)))
    @property
    def size(self):
        n = 1
        for s in self.shape: n *= s
        return n
    @property
    def itemsize(self): return itemsize(self.dtype)
    @property
    def nbytes(self): return self.size * self.itemsize
    def view(self):
        """a flat memoryview of the elements (numbers for the numeric dtypes)"""
        m = memoryview(self.buf)[:self.nbytes]
        k = self.dtype[1:]
        return m.cast(CODE[k]) if k in CODE else m
    def tolist(self): return self.view().tolist()
    def ptr(self):
        """the address of the data for a C helper; the buffer must be writable (bytearray, or an mmap opened copy-on-write)"""
        if not self.nbytes: return ctypes.addressof(_EMPTY)              # (an empty array: a valid address C never reads; from_buffer needs a byte)
        if isinstance(self.buf, bytes): self.buf = bytearray(self.buf)
        c = (ctypes.c_char * self.nbytes).from_buffer(self.buf); self._keep = c
        return ctypes.addressof(c)
    def __repr__(self): return 'Arr(%s, %s)' % (self.dtype, self.shape)
    def __reduce__(self): return (_arr, (self.dtype, self.shape, bytearray(memoryview(self.buf)[:self.nbytes])))      # (pickles: nfpickle.py)

def _arr(dtype, shape, data):
    """an Arr from a pickle (nfpickle.py writes numpy arrays this way)"""
    return Arr(dtype, shape, data)

def header(dtype, shape):
    """numpy 1.24's .npy header, version 1.0: magic, version, length, the dict, spaces to a multiple of 64, newline"""
    shp = '(%d,)' % shape[0] if len(shape) == 1 else '(' + ', '.join('%d' % s for s in shape) + ')'
    d = "{'descr': '%s', 'fortran_order': False, 'shape': %s, }" % (dtype, shp)
    pad = 64 - (10 + len(d) + 1) % 64
    if pad == 64: pad = 0
    h = (d + ' ' * pad + '\n').encode('latin-1')
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(h)) + h

def _parse(b, where):
    """(dtype, shape, data offset) from the start of an .npy file"""
    if b[:6] != b'\x93NUMPY': raise ValueError('%s: not an .npy file' % where)
    major = b[6]
    if major == 1: n = struct.unpack_from('<H', b, 8)[0]; o = 10
    else: n = struct.unpack_from('<I', b, 8)[0]; o = 12
    h = ast.literal_eval(bytes(b[o:o + n]).decode('latin-1'))
    if h['fortran_order']: raise ValueError('%s: Fortran order is not supported' % where)
    if not isinstance(h['descr'], str): raise ValueError('%s: structured arrays are not supported' % where)
    dt = h['descr']
    if dt[0] == '>' and itemsize(dt) > 1: raise ValueError('%s: big-endian data is not supported' % where)
    if dt[0] == '=': dt = '<' + dt[1:]
    return dt, tuple(h['shape']), o + n

def load(path, mmap=False):
    """an .npy file -> Arr; mmap=True maps it copy-on-write (nothing read until used; writes stay private)"""
    with open(path, 'rb') as f:
        head = f.read(4096); dt, shape, off = _parse(head, path)
        if mmap:
            m = _mmap.mmap(f.fileno(), 0, access=_mmap.ACCESS_COPY)
            a = Arr(dt, shape, memoryview(m)[off:]); a._keep = m; return a
        f.seek(off); return Arr(dt, shape, bytearray(f.read()))

def frombytes(b, where='?'):
    dt, shape, off = _parse(b, where); return Arr(dt, shape, bytearray(b[off:]))

def save(path, a):
    with open(path, 'wb') as f:
        f.write(header(a.dtype, a.shape)); f.write(memoryview(a.buf)[:a.nbytes])

def loadz(path):
    """an .npz file -> {name: Arr} (np.savez's stored members and np.savez_compressed's deflated ones)"""
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith('.npy'): out[n[:-4]] = frombytes(z.read(n), '%s(%s)' % (path, n))
    return out

def savez(path, **arrays):
    """{name: Arr} -> an .npz file numpy reads; stored, members in the order given, every timestamp 1980-01-01"""
    _savez(path, zipfile.ZIP_STORED, arrays)

def savez_compressed(path, **arrays):
    """np.savez_compressed: as savez, the members deflated as numpy's are (zipfile's default level): the same file numpy writes (its
    ZipFile.open(name, 'w') also stamps 1980-01-01 and mode 0600; checked on the bake's carshade.npz, 2026-10-15)"""
    _savez(path, zipfile.ZIP_DEFLATED, arrays)

def _savez(path, method, arrays):
    with zipfile.ZipFile(path, 'w', method, allowZip64=True) as z:
        for n, a in arrays.items():
            zi = zipfile.ZipInfo(n + '.npy', (1980, 1, 1, 0, 0, 0)); zi.compress_type = method; zi.external_attr = 0o600 << 16
            with z.open(zi, 'w', force_zip64=True) as o:
                o.write(header(a.dtype, a.shape)); o.write(memoryview(a.buf)[:a.nbytes])

def array(dtype, shape, values):
    """an Arr filled from a flat sequence of numbers"""
    a = Arr(dtype, shape); v = a.view()
    for i, x in enumerate(values): v[i] = x
    return a
