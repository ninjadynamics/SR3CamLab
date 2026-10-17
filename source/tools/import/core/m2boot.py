"""Run the srallyc i960 program from its reset vector in the Python interpreter (i960.py) to find how work RAM is
initialised (the palette source table at RAM 0x5FB89C in particular).   python m2boot.py [max million steps]"""
import sys, struct, time, pickle, os
import i960

def main(maxm=40):
    m = i960.Mem(); c = i960.Cpu(m)
    w = struct.unpack_from('<8I', m.prog, 0); print('IMI words', ['%08x' % x for x in w])
    start = w[3]; prcb = w[1]
    print('start ip %x prcb %x' % (start, prcb))
    c.ip = start; c.r[1] = 0x005f0000; c.r[31] = 0x005effc0
    t = time.time(); last = {}; hot = {}
    watch = 0x5fb89c
    while c.halt is None and c.steps < maxm * 1000000:
        ip = c.ip
        if c.steps % 2000000 == 0:
            print('  %dM steps ip %x ram bytes %d, 0x5fb89c written %s, t %.0fs' % (c.steps // 1000000, ip, len(m.ram), watch in m.ram, time.time() - t)); sys.stdout.flush()
        c.step()
        if watch in m.ram and (watch + 0x40) in m.ram and c.steps % 500000 == 0: break
    print('halt:', c.halt, 'steps', c.steps, 'ip %x' % c.ip)
    print('unmapped reads by page:', sorted(((hex(a), n) for a, n in m.unk.items()), key=lambda x: -x[1])[:12])
    pages = {}
    for a in m.ram: pages[a >> 16] = pages.get(a >> 16, 0) + 1
    print('ram pages written:', [(hex(p << 16), n) for p, n in sorted(pages.items())][:40])
    pickle.dump(dict(ram=m.ram, log=m.log, regs=c.r, ip=c.ip), open(os.path.join(i960.M2, 'boot_state.pkl'), 'wb'))
    print('\n'.join(i960.dis(c.ip - 24, 14, m)))

if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
