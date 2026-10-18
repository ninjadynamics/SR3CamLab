"""Read the verified PS3 Daytona USA assets without installing or running the game.

Inputs: retail PS3 PKG, rom.psarc, or an extracted game/ROM directory.
The Windows package reader uses the system CNG AES provider (no Node/pip dependency).
Format references: RPCS3 Crypto/unpkg.h, unpkg.cpp and key_vault.h.
No SEGA data is distributed here. Unknown revisions fail before output is written.
"""
from pathlib import Path
import ctypes
import hashlib
import os
import struct
import zlib

CODE_SHA256 = 'a5eb9b0d9f078e9e1ed85deedb6b6025d76cc1979af59435d7aec1740de0a8ee'
EXPECTED = {
    'rom_code1.bin': (0x40000, CODE_SHA256),
    'rom_data.bin': (0x900000, '29f64ce058f5bc32ae4743a1abf83bc4b23f822645dd358d3f450269dc76f854'),
    'rom_pol.bin': (0x1000000, '35e83053b690fb291e752a8e1000596be70061d6757080a10fac4191effe0f6c'),
    'rom_tex.bin': (0x800000, 'd433f8817e9c4bc35ca69629a8dc51b7c7f611b86b295fa1d0d0acdec6a7b068'),
    'rom_copro.bin': (0x200000, 'e1d3378acef811a633e1cd997f2bb395da29cc39b89a78bd96886a4fdd3c00b2'),
}


def checked_slice(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError('Archive entry exceeds its container')
    return data[offset:offset + size]


class WindowsAES:
    """AES-ECB for package counter blocks. CNG owns the key object memory."""
    def __init__(self, key):
        if os.name != 'nt':
            raise ValueError('PKG reading currently requires Windows; use an extracted rom.psarc on other systems')
        from ctypes import wintypes as w
        self.lib = ctypes.WinDLL('bcrypt'); self.alg = ctypes.c_void_p(); self.key = ctypes.c_void_p()
        signatures = {
            'BCryptOpenAlgorithmProvider': [ctypes.POINTER(ctypes.c_void_p), w.LPCWSTR, w.LPCWSTR, w.ULONG],
            'BCryptSetProperty': [ctypes.c_void_p, w.LPCWSTR, ctypes.c_void_p, w.ULONG, w.ULONG],
            'BCryptGenerateSymmetricKey': [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, w.ULONG, ctypes.c_void_p, w.ULONG, w.ULONG],
            'BCryptEncrypt': [ctypes.c_void_p, ctypes.c_void_p, w.ULONG, ctypes.c_void_p, ctypes.c_void_p, w.ULONG, ctypes.c_void_p, w.ULONG, ctypes.POINTER(w.ULONG), w.ULONG],
            'BCryptDestroyKey': [ctypes.c_void_p],
            'BCryptCloseAlgorithmProvider': [ctypes.c_void_p, w.ULONG],
        }
        for name, args in signatures.items():
            fn = getattr(self.lib, name); fn.argtypes = args; fn.restype = w.LONG
        try:
            self.check(self.lib.BCryptOpenAlgorithmProvider(ctypes.byref(self.alg), 'AES', None, 0))
            mode = ctypes.create_unicode_buffer('ChainingModeECB')
            self.check(self.lib.BCryptSetProperty(self.alg, 'ChainingMode', mode, ctypes.sizeof(mode), 0))
            self.check(self.lib.BCryptGenerateSymmetricKey(self.alg, ctypes.byref(self.key), None, 0, key, len(key), 0))
        except Exception:
            self.close(); raise

    @staticmethod
    def check(status):
        if status: raise OSError('Windows AES failed: 0x%08x' % (status & 0xffffffff))

    def encrypt(self, data):
        from ctypes import wintypes as w
        out = ctypes.create_string_buffer(len(data)); written = w.ULONG()
        self.check(self.lib.BCryptEncrypt(self.key, data, len(data), None, None, 0, out, len(data), ctypes.byref(written), 0))
        if written.value != len(data): raise ValueError('Incomplete AES block output')
        return out.raw

    def close(self):
        if self.key: self.lib.BCryptDestroyKey(self.key); self.key = None
        if self.alg: self.lib.BCryptCloseAlgorithmProvider(self.alg, 0); self.alg = None


def pkg_psarc(path):
    """Decrypt only the package directory and rom.psarc, not music/executables."""
    with open(path, 'rb') as f:
        header = f.read(128)
        if len(header) != 128 or header[:4] != b'\x7fPKG' or struct.unpack_from('>HH', header, 4) != (0x8000, 1):
            raise ValueError('Expected a retail PS3 PKG')
        count = struct.unpack_from('>I', header, 20)[0]
        pkg_size, data_off, data_size = struct.unpack_from('>QQQ', header, 24)
        if not 0 < count <= 100000 or count * 32 > data_size or data_off < 128 or data_off + data_size > pkg_size or pkg_size > os.fstat(f.fileno()).st_size:
            raise ValueError('Invalid package bounds')
        aes = WindowsAES(bytes.fromhex('2e7b71d7c9c9a14ea3221f188828b8f8'))
        nonce = int.from_bytes(header[112:128], 'big')
        def read(off, size):
            if off < 0 or size < 0 or off + size > data_size or size > 128 * 1024 * 1024:
                raise ValueError('Invalid PKG entry bounds')
            result = bytearray()
            while size:
                take = min(size, 1024 * 1024); skip = off % 16; block = off // 16
                ctr = b''.join(((nonce + block + i) % (1 << 128)).to_bytes(16, 'big') for i in range((skip + take + 15) // 16))
                mask = aes.encrypt(ctr)[skip:skip + take]
                f.seek(data_off + off); encrypted = f.read(take)
                if len(encrypted) != take: raise ValueError('Truncated PKG')
                result.extend(x ^ y for x, y in zip(encrypted, mask)); off += take; size -= take
            return bytes(result)
        try:
            entries = read(0, count * 32); found = []
            for i in range(count):
                no, ns, off, size, typ, _ = struct.unpack_from('>IIQQII', entries, i * 32)
                if not 0 < ns <= 4096: raise ValueError('Invalid PKG filename')
                name = read(no, ns).rstrip(b'\0').decode('utf-8')
                if name == 'USRDIR/ps3/rom.psarc':
                    if typ != 0x80000003: raise ValueError('Unsupported PSARC package entry')
                    found.append((off, size))
            if len(found) != 1: raise ValueError('Package must contain exactly one Daytona USRDIR/ps3/rom.psarc')
            return read(*found[0])
        finally:
            aes.close()


def psarc_roms(data):
    if len(data) < 32: raise ValueError('Truncated PSARC')
    magic, version, compression, toc, stride, count, block_size, flags = struct.unpack_from('>4sI4s5I', data)
    if magic != b'PSAR' or version != 0x10004 or compression != b'zlib' or stride != 30 or block_size != 65536 or flags != 0:
        raise ValueError('Unsupported PSARC layout')
    if not 1 < count <= 10000 or not 32 + count * stride <= toc <= len(data) or (toc - 32 - count * stride) % 2:
        raise ValueError('Invalid PSARC directory')
    sizes = [int.from_bytes(data[i:i+2], 'big') or block_size for i in range(32 + count * stride, toc, 2)]
    def entry(i):
        raw = data[32 + i * stride:32 + (i+1) * stride]
        idx = int.from_bytes(raw[16:20], 'big'); length = int.from_bytes(raw[20:25], 'big'); off = int.from_bytes(raw[25:30], 'big')
        if length > 32 * 1024 * 1024 or off < toc: raise ValueError('Invalid PSARC entry')
        result = bytearray()
        while len(result) < length:
            if idx >= len(sizes): raise ValueError('Missing PSARC block')
            size = sizes[idx]; chunk = checked_slice(data, off, size)
            expected = min(block_size, length - len(result))
            if size == expected:
                decoded = chunk
            else:
                dec = zlib.decompressobj(); decoded = dec.decompress(chunk, expected + 1)
                if not dec.eof or dec.unused_data or dec.unconsumed_tail: raise ValueError('Invalid compressed PSARC block')
            if len(decoded) != expected: raise ValueError('PSARC decompressed size mismatch')
            result.extend(decoded); off += size; idx += 1
        return bytes(result)
    names = entry(0).decode('utf-8').splitlines()
    if len(names) != count - 1 or len(names) != len(set(names)): raise ValueError('Invalid PSARC manifest')
    result = {}
    for i, name in enumerate(names, 1):
        if name.startswith('daytona_rom/') and name[12:] in EXPECTED:
            result[name[12:]] = entry(i)
    return result


def read_source(path):
    path = Path(path)
    if path.is_dir():
        # A direct ROM folder, extracted PSARC tree, or extracted game root.
        for folder in (path, path/'daytona_rom', path/'rom/daytona_rom'):
            if all((folder/name).is_file() for name in EXPECTED):
                return {name: (folder/name).read_bytes() for name in EXPECTED}
        candidates = [p for p in (path/'rom.psarc', path/'ps3/rom.psarc', path/'USRDIR/ps3/rom.psarc', path/'PS3_GAME/USRDIR/ps3/rom.psarc') if p.is_file()]
        if len(candidates) != 1: raise ValueError('Select the Daytona PKG, rom.psarc, or an extracted game directory')
        path = candidates[0]
    if path.suffix.lower() == '.pkg': return psarc_roms(pkg_psarc(path))
    if path.suffix.lower() == '.psarc': return psarc_roms(path.read_bytes())
    if path.suffix.lower() == '.iso':
        raise ValueError('Raw ISO input is not supported: the verified PS3 release is a PSN .pkg. Use that PKG or an extracted game directory containing USRDIR/ps3/rom.psarc.')
    raise ValueError('Expected a PS3 Daytona .pkg, rom.psarc, or extracted game directory')


def build_regions(path):
    roms = read_source(path)
    for name, (size, digest) in EXPECTED.items():
        data = roms.get(name, b'')
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Unsupported or damaged PS3 Daytona revision: %s. Only the verified NPUB30493 asset set is supported; no output was written.' % name)
    # Restore the Model 2 address space used by the shared decoders.
    tex = roms['rom_tex.bin']
    return {
        'maincpu': roms['rom_code1.bin'], 'main_data': roms['rom_data.bin'],
        'polygons': roms['rom_pol.bin'],
        'textures': tex[:0x400000] + bytes(0x400000) + tex[0x400000:] + bytes(0x400000),
        'copro_data': roms['rom_copro.bin'] * 2,
    }
