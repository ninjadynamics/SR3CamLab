"""Synthetic archive tests; no game data or downloadable fixtures required."""
import os
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from unittest.mock import patch
import daytona_ps3 as ps3


def archive(payload):
    names = b'daytona_rom/rom_code1.bin'
    entries = [names, payload]; chunks = []; toc = 32 + 30*2 + 2*2; offset = toc; table = bytearray(); sizes = []
    for i, data in enumerate(entries):
        compressed = zlib.compress(data)
        block = compressed if len(compressed) < len(data) else data
        table += bytes(16) + struct.pack('>I', i) + len(data).to_bytes(5, 'big') + offset.to_bytes(5, 'big')
        sizes.append(len(block)); chunks.append(block); offset += len(block)
    return struct.pack('>4sI4s5I', b'PSAR', 0x10004, b'zlib', toc, 30, 2, 65536, 0) + table + struct.pack('>2H', *sizes) + b''.join(chunks)


class ArchiveTests(unittest.TestCase):
    def test_compressed_and_uncompressed_blocks(self):
        for payload in (b'xyz', b'a'*4000):
            self.assertEqual(ps3.psarc_roms(archive(payload)), {'rom_code1.bin': payload})

    def test_bad_entry_offset(self):
        data = bytearray(archive(b'abc')); data[87:92] = (99999).to_bytes(5, 'big')
        with self.assertRaises(ValueError): ps3.psarc_roms(data)

    def test_decompression_size_is_checked(self):
        data = bytearray(archive(b'a'*4000)); data[82:87] = (3).to_bytes(5, 'big')
        with self.assertRaises(ValueError): ps3.psarc_roms(data)

    def test_truncated_and_unsupported_archives(self):
        for data in (b'', archive(b'x')[:40], b'WRNG'+archive(b'x')[4:]):
            with self.assertRaises(ValueError): ps3.psarc_roms(data)

    def test_unknown_revision_rejected(self):
        with patch.object(ps3, 'read_source', return_value={'rom_code1.bin': b'unknown'}):
            with self.assertRaisesRegex(ValueError, 'Unsupported or damaged'): ps3.build_regions('unused')

    def test_iso_explains_real_source(self):
        with self.assertRaisesRegex(ValueError, 'verified PS3 release is a PSN'): ps3.read_source('unused.iso')

    @unittest.skipUnless(os.name == 'nt', 'Windows CNG')
    def test_aes_known_answer(self):
        aes = ps3.WindowsAES(bytes.fromhex('000102030405060708090a0b0c0d0e0f'))
        try:
            self.assertEqual(aes.encrypt(bytes.fromhex('00112233445566778899aabbccddeeff')).hex(), '69c4e0d86a7b0430d8cdb78070b4c55a')
        finally: aes.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows CNG')
    def test_package_random_access_unaligned_entry(self):
        # Deliberately unaligned name/data tests counter offset and partial blocks.
        name = b'USRDIR/ps3/rom.psarc'; payload = archive(b'test'*100)
        body = struct.pack('>IIQQII', 37, len(name), 83, len(payload), 0x80000003, 0)
        body = body.ljust(37, b'\0') + name
        body = body.ljust(83, b'\0') + payload
        nonce = bytes(range(16)); counter = int.from_bytes(nonce, 'big')
        aes = ps3.WindowsAES(bytes.fromhex('2e7b71d7c9c9a14ea3221f188828b8f8'))
        try: mask = aes.encrypt(b''.join((counter+i).to_bytes(16,'big') for i in range((len(body)+15)//16)))
        finally: aes.close()
        encrypted = bytes(a^b for a,b in zip(body,mask)); header = bytearray(128)
        struct.pack_into('>4sHH', header, 0, b'\x7fPKG', 0x8000, 1)
        struct.pack_into('>IQQQ', header, 20, 1, 128+len(body), 128, len(body)); header[112:128] = nonce
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'synthetic.pkg'; path.write_bytes(header+encrypted)
            self.assertEqual(ps3.pkg_psarc(path), payload)
            path.write_bytes(header+encrypted[:-10])
            with self.assertRaises(ValueError): ps3.pkg_psarc(path)


if __name__ == '__main__': unittest.main()
