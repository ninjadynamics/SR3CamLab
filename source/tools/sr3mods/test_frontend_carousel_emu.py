"""Replay the native track-card carousel during wraps and rapid input.

The supported executable's carousel-node initializer, selection (622270),
reshuffle-path builder (61D960), per-frame phase update (622E40) and painter
ordering (61DF50) run in Unicorn. Only the matrix copy, a backdrop loader and
a sound-free helper are stubbed. The list/phase operations mirror
frontend_native.c (rest, rotate, cursor and busy); test_frontend_native.c
checks that C code against the same rules.

It demonstrates the original defect: a multi-card jump from rest gives every
crossing card a one-sided path, which clamps it to the centre, in front of the
moving cards. It then checks one-card ring steps fed as the plugin feeds them:
taps at once, a wrap held only while the card it moves could be on screen,
holds only while the cards are within one card. The selected card ends in
front, no other card is parked in front, and no visible card jumps except the
native snap of a reversal mid-slide (stock behaviour, counted separately).
No game is launched or installed.
"""
from pathlib import Path
import random
import struct
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDI

R = Path(__file__).resolve().parents[3]
pe = pefile.PE(str(R / 'game/Rally/Rally.exe'))
BASE = pe.OPTIONAL_HEADER.ImageBase
IM = pe.get_memory_mapped_image()
H, STACK, END, TLS = 0x20000000, 0x30000000, 0x3ff00000, 0x1000
RIGHT, LEFT, SPACING = 0x7287e0, 0x728900, 60.0
REGS = {'eax': UC_X86_REG_EAX, 'ecx': UC_X86_REG_ECX, 'edi': UC_X86_REG_EDI}


class Carousel:
    def __init__(self, n):
        m = self.m = Uc(UC_ARCH_X86, UC_MODE_32)
        m.mem_map(0, 0x10000)                       # fs base 0: fs:[2c] -> TLS
        m.mem_map(BASE, (len(IM) + 0xfff) & ~0xfff); m.mem_write(BASE, IM)
        m.mem_map(H, 0x400000); m.mem_map(STACK, 0x100000); m.mem_map(END, 0x1000)
        self.wr(0x2c, TLS); self.wr(TLS, TLS + 0x100)
        self.heap, self.us = H, 1_000_000_000
        cam = self.alloc(0x200); self.wr(0x9d6f58, cam)
        for off in (0xc, 0x10, 0xc8, 0xd0): self.wf(cam + off, 1.0)
        self.wf(cam + 0xd4, 2.0); self.wf(cam + 0xd8, 3.0)
        stubs = {0x62ad10: 0, 0x61c060: 4, 0x61afe0: 0}
        def stub(mu, at, size, user):
            sp = mu.reg_read(UC_X86_REG_ESP)
            mu.reg_write(UC_X86_REG_EIP, self.rd(sp)); mu.reg_write(UC_X86_REG_ESP, sp + 4 + stubs[at])
        for at in stubs: m.hook_add(UC_HOOK_CODE, stub, begin=at, end=at)
        self.n, self.scene = n, self.alloc(0x200)
        self.call(0x62b120, eax=self.scene, cleanup=0)
        self.wr(self.scene + 0x100, 1); self.wr(self.scene + 0x13c, 11)
        self.wf(self.scene + 0x11c, 1e-5); self.wf(self.scene + 0x10c, 1e-5)
        self.cards, self.links, self.items = [], [], []
        for i in range(n):
            c, item, link = self.alloc(0x200), self.alloc(0x200), self.alloc(16)
            self.call(0x62b120, eax=c, cleanup=0)
            self.wr(c + 0xb0, item); self.wr(c + 0xb8, self.scene); self.wr(c + 0xf8, 1); self.wf(c + 0xfc, -0.1)
            self.wr(c + 0x114, 1); self.wr(c + 0x100, 1); self.wr(c + 0x13c, 12)
            self.wf(c + 0x11c, 1e-5); self.wf(c + 0x10c, 1e-5); self.wr(link + 12, c)
            self.cards.append(c); self.items.append(item); self.links.append(link)
        self.out, self.count = self.alloc(0x400), self.alloc(4)
        self.link(list(range(n)))
        self.call(0x622270, eax=self.scene, edi=0, cleanup=0)
        self.call(0x622e40, (0.0, 3, 1, 1, 0), ecx=self.scene)

    def rd(self, a): return struct.unpack('<I', self.m.mem_read(a, 4))[0]
    def rf(self, a): return struct.unpack('<f', self.m.mem_read(a, 4))[0]
    def wr(self, a, v): self.m.mem_write(a, struct.pack('<I', v & 0xffffffff))
    def wf(self, a, v): self.m.mem_write(a, struct.pack('<f', v))
    def alloc(self, n):
        a = self.heap; self.heap += (n + 0x3f) & ~0x3f; return a

    def call(self, at, args=(), cleanup=None, **regs):
        sp = STACK + 0x80000 - 4 * len(args) - 4
        self.m.mem_write(sp, struct.pack('<I', END) + b''.join(
            struct.pack('<f', a) if isinstance(a, float) else struct.pack('<I', a & 0xffffffff) for a in args))
        self.m.reg_write(UC_X86_REG_ESP, sp)
        for name, v in regs.items(): self.m.reg_write(REGS[name], v)
        self.m.emu_start(at, END, count=5_000_000)
        assert self.m.reg_read(UC_X86_REG_ESP) == sp + 4 + (4 * len(args) if cleanup is None else cleanup), hex(at)

    # frontend_native.c mirror -------------------------------------------
    def link(self, order):
        prev, tail = self.scene + 0xa4, self.scene + 0xa8
        for pos, local in enumerate(order):
            node = self.links[local]; self.wr(prev, node); self.wr(node + 4, prev); prev = node
            self.wr(self.cards[local] + 0x80, pos)
        self.wr(prev, tail); self.wr(tail + 4, prev); self.order = list(order)

    def path(self, local, template):
        self.m.mem_write(self.cards[local] + 0x140, bytes(self.m.mem_read(template, 0x8c)))

    def view(self, cursor):
        s = self.scene; self.link([(cursor + k) % self.n for k in range(self.n)])
        for off in (0x98, 0x9c, 0xd8): self.wf(s + off, 0.0)
        self.wr(s + 0xb4, 0); self.wr(s + 0x88, 0)
        for pos, local in enumerate(self.order):
            self.path(local, RIGHT); self.wf(self.cards[local] + 0x90, pos * SPACING)
        self.cursor = cursor; self.select(0)

    def rotate(self, direction):
        s = self.scene
        order = self.order[1:] + self.order[:1] if direction > 0 else self.order[-1:] + self.order[:-1]
        self.link(order)
        for off in (0x98, 0x9c, 0xd8): self.wf(s + off, self.rf(s + off) + direction * SPACING)
        self.wr(s + 0x88, self.rd(s + 0x88) - direction)
        self.path(order[-1] if direction > 0 else order[0], RIGHT if direction > 0 else LEFT)
        phase = self.rf(s + 0x9c)
        for pos, local in enumerate(order): self.wf(self.cards[local] + 0x90, pos * SPACING + phase)

    def step(self, direction):
        self.cursor = (self.cursor + direction) % self.n
        at = self.rd(self.scene + 0x88)
        if self.n >= 3 and not 0 <= at + direction < self.n: self.rotate(direction); at -= direction
        assert self.order[at + direction] == self.cursor
        self.select(at + direction)

    def busy(self):
        s = self.scene
        return self.rd(s + 0xb4) and abs(self.rf(s + 0x9c) - self.rf(s + 0x98)) > SPACING

    def blocked(self, direction):
        at, seen = self.rd(self.scene + 0x88), -self.rf(self.scene + 0x9c) / SPACING
        if self.n < 3: return False
        return seen < 2 if direction > 0 and at + 1 >= self.n else seen > self.n - 3 if direction < 0 and at < 1 else False

    # native ---------------------------------------------------------------
    def select(self, position):
        """62A930 -> 628DF0 reaches 622270 for the active carousel."""
        self.call(0x622270, eax=self.scene, edi=position, cleanup=0)

    def frame(self):
        """62B7B3 per-frame update, then the 622DE0 painter list (last = front)."""
        self.us += 16_667; self.m.mem_write(0x9c4a10, struct.pack('<Q', self.us))
        self.call(0x622e40, (0.0, 0, 1, 1, 0), ecx=self.scene)
        self.wr(self.count, 0)
        self.call(0x61df50, (0, 1, 1, 0) + (0.0,) * 8 + (0, self.out + 0x300, self.out, self.count), ecx=self.scene)
        drawn = [self.items.index(self.rd(self.out + 4 * i)) for i in range(self.rd(self.count))]
        # The card is translated along one direction by its path value: 0 is
        # the centre, +/-1 the right/left stacks.
        return [(local, self.rf(self.items[local] + 0x144) / SPACING) for local in drawn], self.rd(self.scene + 0xb4)


def watch(car, frames=400, inputs=None, hold=None):
    """Run frames, feeding input as the plugin does; report the worst artifacts."""
    inputs = sorted(inputs or []); queued = t = 0; i = 0; previous = None
    parked = {}; longest = jumps = reversals = waited = longest_wait = 0; repeat_at = 350
    for _ in range(frames):
        while i < len(inputs) and inputs[i][0] <= t: queued += inputs[i][1]; i += 1
        if hold and t < hold[0] and not queued and not car.busy() and not car.blocked(hold[1]) and t >= repeat_at:
            queued = hold[1]; repeat_at = t + 120
        reversal = False
        if queued:
            d = 1 if queued > 0 else -1
            if car.blocked(d): waited += 1; longest_wait = max(longest_wait, waited)
            else:
                waited = 0
                reversal = (car.rf(car.scene + 0x98) - car.rf(car.scene + 0x9c)) * d > 0
                car.step(d); queued -= d
        drawn, animating = car.frame(); t += 1000 / 60
        centre = {local for local, c in drawn[:-1] if abs(c) < 0.1}
        for local in centre: parked[local] = parked.get(local, 0) + 1
        for local in set(parked) - centre: longest = max(longest, parked.pop(local))
        if previous:
            before = dict(previous)
            for local, c in drawn:
                if abs(c - before[local]) < 0.25: continue
                j = [x for x, _ in previous].index(local)
                if not any(abs(o - before[local]) < 0.06 for _, o in previous[j + 1:]):
                    if reversal: reversals += 1
                    else: jumps += 1
        previous = drawn
        if i >= len(inputs) and not queued and (not hold or t > hold[0]) and not animating: break
    front, c = drawn[-1]
    settled = front == car.cursor and abs(c) < 1e-3 and all(abs(abs(o) - 1) < 0.03 for _, o in drawn[:-1])
    return dict(settled=settled, parked=max([longest] + list(parked.values())), jumps=jumps,
                reversals=reversals, wait=longest_wait, after=t - (hold[0] if hold else 0))


def main():
    # Original: 62A930(0) from the last of five cards is a four-card jump.
    car = Carousel(5); car.view(0)
    for _ in range(4): car.step(1); watch(car)
    car.cursor = 0; car.select(0)
    worst = {}
    for _ in range(80):
        drawn, animating = car.frame()
        for local, c in drawn[:-1]:
            if abs(c) < 1e-3: worst[local] = worst.get(local, 0) + 1
        if not animating: break
    assert worst.get(1, 0) > 20 and drawn[-2][0] == 1, worst
    print('PASS: native four-card jump reproduces SR2 parked in front for %d frames' % worst[1])
    # Ring: both endpoint wraps are single native steps, taken at once.
    for n, start, direction in ((5, 4, 1), (5, 0, -1), (9, 8, 1), (3, 0, -1)):
        car = Carousel(n); car.view(start)
        r = watch(car, inputs=[(0, direction)])
        assert r['settled'] and r['parked'] <= 2 and not r['jumps'] and not r['reversals'] and not r['wait'], (n, start, r)
    # Taps, reversals and holds at many speeds, including repeated wraps.
    rng = random.Random(28)
    cases = snaps = wait = coast = 0
    for n in (3, 4, 5, 9, 14):
        for _ in range(12):
            t, inputs = 0, []
            for _ in range(rng.randint(1, 12)):
                t += rng.choice((20, 40, 60, 90, 120, 200, 400)); inputs.append((t, rng.choice((1, -1, 1))))
            car = Carousel(n); start = rng.randrange(n); car.view(start)
            r = watch(car, frames=2000, inputs=inputs)
            assert r['settled'] and car.cursor == (start + sum(d for _, d in inputs)) % n, (n, inputs)
            assert r['parked'] <= 3 and not r['jumps'], (n, inputs, r)
            cases += 1; snaps += r['reversals']; wait = max(wait, r['wait'])
        for direction in (1, -1):
            car = Carousel(n); car.view(0)
            r = watch(car, frames=2000, hold=(2500, direction))
            assert r['settled'] and r['parked'] <= 2 and not r['jumps'] and r['after'] < 500, (n, direction, r)
            coast = max(coast, r['after'])
    print('PASS: one-card ring wraps and %d tap/hold sequences settle on the cursor; no parked card, no jump '
          '(%d native reversal snaps; longest wrap wait %d frames; hold settles %.0f ms after release)' % (cases, snaps, wait, coast))


if __name__ == '__main__': main()
