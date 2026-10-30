"""Read an sr3lab-*.dmp written by load_guard.c: threads, their registers and
the code addresses found on their stacks, mapped to modules.

    python -B minidump_threads.py <dump> [--exe game/Rally/Rally.exe]

With --exe, Rally.exe addresses are checked against the executable's bytes:
an address preceded by a CALL is marked as a return address. The rest is a
plain stack scan, so stale values can appear. Nothing is launched.
"""
import argparse
import struct
from pathlib import Path

THREADS, MODULES, MEMORY, HANDLES, THREAD_INFO = 3, 4, 5, 12, 17


class Dump:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        sig, _, count, rva = struct.unpack_from('<4sIII', self.data, 0)
        if sig != b'MDMP':
            raise ValueError('not a minidump')
        self.streams = {}
        for i in range(count):
            kind, size, at = struct.unpack_from('<III', self.data, rva + 12 * i)
            self.streams[kind] = (at, size)
        self.modules = self._modules()
        self.ranges = self._memory()
        self.threads = self._threads()

    def _string(self, rva):
        n = struct.unpack_from('<I', self.data, rva)[0]
        return self.data[rva + 4:rva + 4 + n].decode('utf-16-le')

    def _modules(self):
        if MODULES not in self.streams:
            return []
        at, _ = self.streams[MODULES]
        out = []
        for i in range(struct.unpack_from('<I', self.data, at)[0]):
            base, size, _, _, name = struct.unpack_from('<QIIII', self.data, at + 4 + 108 * i)
            out.append((base, size, self._string(name)))
        return out

    def _memory(self):
        if MEMORY not in self.streams:
            return []
        at, _ = self.streams[MEMORY]
        return [struct.unpack_from('<QII', self.data, at + 4 + 16 * i)
                for i in range(struct.unpack_from('<I', self.data, at)[0])]

    def _threads(self):
        at, _ = self.streams[THREADS]
        out = []
        for i in range(struct.unpack_from('<I', self.data, at)[0]):
            tid, suspend, _, _, teb, start, size, rva, csize, crva = struct.unpack_from('<IIIIQQIIII', self.data, at + 4 + 48 * i)
            ctx = self.data[crva:crva + csize]
            regs = dict(zip(('ebp', 'eip', 'esp'), (struct.unpack_from('<I', ctx, o)[0] for o in (0xB4, 0xB8, 0xC4)))) if csize >= 0xC8 else {}
            out.append(dict(id=tid, suspend=suspend, stack=(start, self.data[rva:rva + size]), regs=regs))
        return out

    def module(self, address):
        for base, size, name in self.modules:
            if base <= address < base + size:
                return base, name
        return None

    def covers(self, address, size=1):
        return any(start <= address and address + size <= start + n for start, n, _ in self.ranges)

    def read(self, address, size):
        for start, n, rva in self.ranges:
            if start <= address and address + size <= start + n:
                return self.data[rva + address - start:rva + address - start + size]
        return None


def called(image, base, address):
    """True if the instruction ending at address is a CALL in the PE image."""
    o = address - base
    if o < 6 or o > len(image):
        return False
    return image[o - 5] == 0xE8 or (image[o - 2] == 0xFF and image[o - 1] & 0x38 == 0x10) or \
        (image[o - 3] == 0xFF and image[o - 2] & 0x38 == 0x10) or (image[o - 6] == 0xFF and image[o - 5] & 0x38 == 0x10)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dump')
    ap.add_argument('--exe', help='Rally.exe, to confirm return addresses')
    ap.add_argument('--depth', type=int, default=24)
    args = ap.parse_args()
    d = Dump(args.dump)
    image = None
    if args.exe:
        import pefile
        pe = pefile.PE(args.exe)
        image = (pe.OPTIONAL_HEADER.ImageBase, pe.get_memory_mapped_image())
    print(f'{len(d.threads)} threads, {len(d.modules)} modules, {len(d.ranges)} memory ranges')
    for t in d.threads:
        r = t['regs']
        where = d.module(r.get('eip', 0))
        print(f"\nthread {t['id']} suspend={t['suspend']} eip={r.get('eip', 0):08x} "
              f"({where[1].split(chr(92))[-1] + '+%x' % (r['eip'] - where[0]) if where else '?'}) esp={r.get('esp', 0):08x}")
        start, stack = t['stack']
        shown = 0
        for off in range(max(0, r.get('esp', start) - start), len(stack) - 3, 4):
            value = struct.unpack_from('<I', stack, off)[0]
            m = d.module(value)
            if not m:
                continue
            name = m[1].split('\\')[-1]
            mark = ''
            if image and name.lower() == 'rally.exe':
                if not called(image[1], image[0], value):
                    continue
                mark = ' (after CALL)'
            print(f'  [{start + off:08x}] {value:08x} {name}+{value - m[0]:x}{mark}')
            shown += 1
            if shown >= args.depth:
                break


if __name__ == '__main__':
    main()
