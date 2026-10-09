"""SEGA Rally 2 (Model 3) sound-board data parser.
Everything here was worked out from the user's ROMs:
  sound program  epr-20636.21 (byte-swapped -> big-endian 68K image, mapped at 0x600000)
  samples        mpr-20614.22 + mpr-20615.24 (byte-swapped, mapped at 0x800000): raw signed 8-bit PCM
  header @0x8000 of the program: pointers to the tables used below
  sample table   @0xA62A: u32 count, then {u32 start(68K addr), u32 length (bit31 = loop flag), u32 loop start}
  tone table     @0x84D8: u16 count-1, then 12-byte entries {u16 sample, u16 SCSP pitch (OCT/FNS), u16 flags, u16, u16, u16}
  request table  @0x9192: groups 0x10.. ; each sound = tiny track: C0 pp, then notes {pp? key vel [bank delay16]} .. (0x80|bank) FF 2F 00
  names + request codes (A0 group number) come from the MAIN program ROM (crom.bin @0xE2C4C / 0xE3168).
Voice clips: bank 1/2 notes; voice index v = (bank-1)*128 + key - 0x1B  ->  tone entry 155+v.
"""
import struct, pickle, os, wave
import numpy as np
S = r"C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/sr_classic"
O = S + "/out/snd/"
prog = open(O + "sndprog.bin", "rb").read()
rom = np.fromfile(O + "samples.bin", dtype=np.int8)
names, cmds = pickle.load(open(O + "soundnames.pkl", "rb"))

def sample_table():
    T = 0xA62A
    n = struct.unpack_from(">I", prog, T)[0]
    out = []
    for i in range(n):
        a, l, b = struct.unpack_from(">III", prog, T + 4 + 12 * i)
        out.append(dict(idx=i, addr=a, rom=a - 0x800000, length=l & 0x7FFFFFFF, loop=bool(l >> 31), loop_start=b - 0x800000))
    return out

def tone_table():
    E = 0x84DA
    n = struct.unpack_from(">H", prog, 0x84D8)[0] + 1
    return [struct.unpack_from(">6H", prog, E + 12 * k) for k in range(n)]

def pitch_to_rate(p):
    octv = (p >> 11) & 0xF
    if octv & 8: octv -= 16
    fns = p & 0x3FF
    return 44100.0 * (2.0 ** octv) * (1 + fns / 1024.0)

def requests():
    """returns {(group, number): [(prog, key, vel, bank, delay_after or None), ...]}"""
    B = 0x9192
    w = lambda o: struct.unpack_from(">H", prog, o)[0]
    ng = w(B)
    out = {}
    for gi in range(ng + 1):
        go = w(B + 2 + 2 * gi)
        cnt = w(B + go)
        if cnt == 0xFFFF: continue
        for i in range(cnt + 1):
            p = B + w(B + go + 2 + 2 * i)
            notes = []
            raw_start = p
            if prog[p] != 0xC0:
                out[(0x10 + gi, i)] = (None, prog[p:p + 16].hex()); continue
            p += 1
            ok = True
            while True:
                pp, key, vel, b = prog[p], prog[p + 1], prog[p + 2], prog[p + 3]
                if b & 0x80:
                    notes.append((pp, key, vel, b & 0x7F, None)); p += 4
                    ok = prog[p:p + 3] == b"\xff\x2f\x00"
                    break
                # delay: MIDI-style variable length quantity
                q = p + 4; d = 0
                while True:
                    d = (d << 7) | (prog[q] & 0x7F)
                    if not prog[q] & 0x80: q += 1; break
                    q += 1
                notes.append((pp, key, vel, b, d)); p = q
                if len(notes) > 8: ok = False; break
            out[(0x10 + gi, i)] = (notes if ok else None, prog[raw_start:raw_start + 24].hex())
    return out

def name_map():
    return {(c[1], c[2]): n for n, c in zip(names, cmds) if c[0] == 0xA0}

def pcm16(s):
    a = rom[s["rom"]: s["rom"] + s["length"]].astype(np.int16) * 256
    return a

def write_wav(path, data, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(round(rate))); w.writeframes(np.asarray(data, dtype="<i2").tobytes())

if __name__ == "__main__":
    st = sample_table(); tt = tone_table(); rq = requests(); nm = name_map()
    print("samples", len(st), "tones", len(tt), "requests", len(rq), "unparsed", sum(1 for v in rq.values() if v[0] is None))
    for k, v in rq.items():
        if v[0] is None: print("  unparsed %02X/%02X %s %s" % (k[0], k[1], nm.get(k), v[1]))
    # check delay vs sample duration for voice notes
    rows = []
    for (g, i), (notes, raw) in sorted(rq.items()):
        if notes is None or g < 0x17: continue
        for (pp, key, vel, bank, d) in notes:
            v = (bank - 1) * 128 + key - 0x1B
            t = tt[155 + v]; s = st[t[0]]
            if d is not None: rows.append((d, s["length"] / pitch_to_rate(t[1]) * 1000, nm.get((g, i))))
    r = np.array([(a, b) for a, b, _ in rows])
    print("delay(ticks) vs clip ms: n=%d median ratio %.3f min %.3f max %.3f" % (len(r), np.median(r[:, 0] / r[:, 1]), (r[:, 0] / r[:, 1]).min(), (r[:, 0] / r[:, 1]).max()))
    for x in rows[:8]: print("   ", x)
