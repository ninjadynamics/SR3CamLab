"""sr3mods.ps1's live loop and pc_live.c in lockstep (Bruno, 2026-10-15: the .ps1 and the .dll in lockstep, automated):

    python live_lockstep.py [--exe <livetest.exe>] [--keep] [--only <scenario>]   (build.py runs it after every build)

Each scenario is a scripted fake game: its memory, the files of a game folder (switch.json, track folders, card videos,
arcade_times.bin, shadow.txt, road.txt, shader.txt, the stream file, car files, handling.json in the mod folder) and the
frames (menus, entries, the current track, View Change, the highlighted card, the pad, the keys, the window in front).
Both run it on their own copy of the folders:
  sr3mods.ps1  through live_ps1.ps1 (its own code, [Sr3Mem] swapped for a fake, the outside world faked)
  pc_live.c    through livetest.exe (the code sr3mods.dll and sr3mods.exe run, on livetest.c's fake GameMem)
and the traces must be the same line for line: every write (address, keep-writable, bytes), suspend / resume,
allocation, log line, screen grab with its JSON, and the frame marks; then handling.json (by value) and
classic_mode.txt. The two fakes are the same game: livetest.c and live_ps1.ps1 say how it answers."""
import json, os, re, shutil, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
PS = open(os.path.join(REPO, 'sr3mods.ps1'), encoding='utf-8-sig').read()

def i32(v): return struct.pack('<i', v) if v < 0x80000000 else struct.pack('<I', v)
def f32(*v): return struct.pack('<%df' % len(v), *v)
def sz(t, n): b = t.encode('ascii'); return b + bytes(n - len(b))
def hexvar(name): return bytes.fromhex(re.search(r"\$%s = '([0-9a-f]*)'" % re.escape(name), PS).group(1))

class Game:
    """A fake game: memory (address -> bytes), the game folder's files, the mod folder's files, the frames."""
    def __init__(self, name):
        self.name, self.mem, self.after, self.files, self.mod, self.frames, self.t, self.next_handle = name, [], [], {}, {}, [], 0, 14
        self.reinstall, self.between = None, []        # a second run of the install (PLAY.bat again on the running game): its settings; writes before it
    def put(self, va, b): self.mem.append([va, b.hex()])
    def putb(self, off, b): self.after.append([off, b.hex()])
    def file(self, rel, data=b'x'): self.files[rel] = data if isinstance(data, bytes) else data.encode('utf-8')
    def frame(self, menu, count, track, view=0, hi=-1, pad=0, keys=(), front=0, mode_val=-1, car_sel=-1, dt=15, set=(), setb=()):
        held = lambda on: i32(0x7F80FF if on else 0).hex()                                  # the game's logical input: low 15 bits = held now
        s = [[0x9D6E3C, bytes([menu]).hex()], [0x9C442C, i32(count).hex()], [0x30000100, sz(track, 32).hex()],
             [0x9DBB0C, held(view or pad & 0x1000)], [0x9DBBA4, held(pad & 0x10)]] + [[a, b.hex()] for a, b in set]   # View Change (entry 15), START (53)
        sb = [[0x226C, i32(hi).hex()], [0x2278, i32(mode_val).hex()], [0x227C, i32(car_sel).hex()]] + [[a, b.hex()] for a, b in setb]
        self.frames.append(dict(t=self.t, pad=pad, keys=list(keys), front=front, set=s, setb=sb)); self.t += dt
    def json(self):
        d = dict(name=self.name, mem=self.mem, after=self.after, between=self.between, frames=self.frames, next_handle=self.next_handle)
        if self.reinstall is not None: d['reinstall'] = self.reinstall
        return d

TRACK_IDS = {'Tropical4': 0x5001, 'Canyon4': 0x5008, 'Alpine4': 0x500F, 'Lakeside4': 0x5016, 'Desert4': 0x501D, 'Stadium4': 0x5024}
def base_game(g, cars_lib=True):
    """The parts of a freshly started SR3 the live loop looks at, all as the game has them."""
    blk = re.search(r"^\$MenuTimerSites = \[ordered\]@\{\n(.*?)^\}$", PS, re.M | re.S).group(1)
    for a, v in re.findall(r"(0x[0-9A-Fa-f]+) = (\d+)", re.sub(r'#.*', '', blk)): g.put(int(a, 16), i32(int(v)))
    g.put(0x61827A, hexvar('TimerDrawOrig'))
    for s, e, b in re.findall(r"@\((0x[0-9A-Fa-f]+), (\d+), '([0-9a-f]+)'\)", re.search(r"^\$CarListSites = (.*)$", PS, re.M).group(1)): g.put(int(s, 16), bytes.fromhex(b))
    g.put(0x599D78, bytes.fromhex('3bc87510')); g.put(0x61C30B, hexvar('CardHookExit'))
    g.put(0x9D6E50, i32(0)); g.put(0x9D6E3C, i32(0))
    g.put(0x5C6144, hexvar('CarPathBytes')); g.put(0x5CFF32, hexvar('SteerBytes')); g.put(0x678878, i32(0x45C820))
    for a in (0x6C631D, 0x6C6371, 0x6C6176): g.put(a, b's')
    for s, b, e in re.findall(r"@\((0x[0-9A-Fa-f]+), '([0-9a-f]+)', (0x[0-9A-Fa-f]+)\)", re.search(r"^\$TrackDirHooks = (.*)$", PS, re.M).group(1)): g.put(int(s, 16), bytes.fromhex(b))
    for a in (0x6C607B, 0x6C60A3, 0x6D57C3, 0x6E034F, 0x6E03A3, 0x6E055B): g.put(a, b's')
    g.put(0x6BCF0F, b'D')
    for a in (0x6BD79E, 0x6D96E6, 0x6E2AB2, 0x6E336E, 0x6E5A36): g.put(a, b'R')
    g.put(0x6CF084, sz('SP_Tropical', 12)); g.put(0x6CF098, sz('SP_Alpine', 12)); g.put(0x6CF0AC, sz('SP_Canyon', 12))
    g.put(0x610E10, i32(0x6CF084)); g.put(0x610E3B, i32(0x6CF098)); g.put(0x610E67, i32(0x6CF0AC))
    g.put(0x6D5EF0, sz('%s%s', 8)); g.put(0x6D5E7C, sz('%s%s', 8)); g.put(0x6D5EA0, sz('%s%s%s', 8))
    g.put(0x644EA5, i32(0x6D5EF0)); g.put(0x6451C5, i32(0x6D5E7C)); g.put(0x63382B, i32(0x6D5EA0))
    names = {14: 'TRO', 15: 'ALP', 16: 'CAN', 2: 'classic', 13: 'static'}                   # the card videos the game loaded
    for k, e in enumerate(range(0x728630, 0x728750, 16)): g.put(e, i32(0x30000400) + i32(0x30000400) + i32(0) + i32(k))
    g.put(0x30000400, sz('other.wmv', 16))
    for k in range(20):
        nm = names.get(k, 'v%d' % k); path = '.\\frontend\\PC\\Videos\\' + ('LANG_ENGLISH_%s.wmv' % nm if nm in ('TRO', 'ALP', 'CAN') else nm + '.wmv')
        g.put(0xAD2F90 + 0x16C * k + 4, i32(1 if k < 18 else 0)); g.put(0xAD2F90 + 0x16C * k + 0xC, sz(path, 256))
    g.put(0x30000000, bytes(0x40)); g.put(0x9DBDB0, i32(0x30000000)); g.put(0x30000018, i32(0x30000100)); g.put(0x30000100, bytes(64))
    g.put(0xB2A850, i32(0x31000000)); g.put(0x31000000, i32(0x32000000) + i32(0x32000000) + i32(0x31000100) + i32(0x33000000) + i32(0x34000000))
    n = 0x31000108
    for k, (t, i) in enumerate(TRACK_IDS.items()):                                            # the track list: {next, id, ..., +0x18 -> name}
        g.put(n, i32(n + 0x100 if k < len(TRACK_IDS) - 1 else 0) + i32(i) + bytes(0x10) + i32(n + 0x20) + bytes(4) + sz(t, 32)); n += 0x100
    g.put(0x33000000, bytes(4 + 0xC60 * 6)); g.put(0x34000000, i32(0) + i32(4))
    if cars_lib:                                                                              # the car library: ten cars, then the Hornet (id 10)
        n = 0x32000008; g.put(0x32000000, bytes(8))
        for k in range(11):
            g.put(n, i32(n + 0x80 if k < 10 else 0) + i32(k) + bytes(0x38) + sz('LANG_ID_HORNET' if k == 10 else 'LANG_ID_X%d' % k, 32) + bytes(0x20)); n += 0x80
    g.put(0xA65794, i32(0)); g.put(0x9DBAD0, bytes(90 * 4)); g.put(0x9C442C, i32(0))
    g.put(0x728CF4, i32(0x10A2C)); g.put(0x9DBDA0, bytes(0x10))
    g.put(0x9F106C, f32(0.001953125, 10.0)); g.put(0x5A5467, bytes([0xE8, 0xF4, 0x84, 0xF6, 0xFF]))
    g.put(0x4EEF70, bytes([0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF0])); g.put(0x4EE920, bytes([0x83, 0xEC, 0x3C, 0x8B, 0x00, 0x6B]))
    g.putb(0x226C, i32(-1)); g.putb(0x2278, i32(-1)); g.putb(0x227C, i32(-1)); g.putb(0x2260, i32(3))
    return g

def switch_json(slots, art=True): return json.dumps(dict(art=art, slots=slots), indent=2)
def sc_switch():
    g = base_game(Game('switch'))
    g.file('Main_release/tracks/_SR3Extras/switch.json', switch_json({
        'Canyon4': dict(title='Canyon', speech='SP_Canyon', tracks=[dict(title='Arctic', dir='1', video='CA1', speech='SP_SEGARALLYREVO'),
                    dict(title='Safari été \U0001F600', dir=2, video='CA2', speech='SP_SEGARALLYREVOLUTION', ambience='ID_TRACK_DESERT_2', music='id_track_desert_1', events='ID_TRACK_DESERT_2',
                         tune=dict(stream=3, offset=1000, bytes=2000, loopstart=400))]),
        'Alpine4': dict(title='Alpine', speech='SP_Alpine', tracks=[dict(title='Lakeside', dir='1', video='AL1', speech='SP_Lakeside'), dict(title='Gone', dir='3', video='AL3'),
                    dict(title='Bad tune', dir='2', video='', tune=dict(stream=3, offset=5000, bytes=2000, loopstart=400))]),
        'Desert4': dict(title='Desert', tracks=dict(title='Mountain 1995', dir='5', video='MTN'))}))
    for d in ('track1/Canyon4', 'track2/Canyon4', 'track1/Alpine4', 'track2/Alpine4', 'track5/Desert4'): g.file('Main_release/%s/keep' % d)
    for v in ('LANG_ENGLISH_CA1', 'LANG_ENGLISH_CA2', 'LANG_ENGLISH_AL1', 'classic_MTN'): g.file('frontend/PC/Videos/%s.wmv' % v)
    g.file('Audio/EnglishStreamData.stm', bytes(4096))
    g.file('Main_release/track1/Canyon4/arcade_times.bin', bytes(range(256)) * 12 + bytes(0xC60 - 3072))
    g.file('Main_release/track2/Canyon4/shadow.txt', ' 0.0002   30 noblur\n'); g.file('Main_release/track1/Alpine4/shadow.txt', 'NaN 30')
    g.file('Main_release/track1/Canyon4/road.txt', 'Hide All\r\n'); g.file('Main_release/track2/Alpine4/road.txt', 'show')
    g.file('Main_release/track1/Alpine4/shader.txt', 'untextured')
    g.put(0x9C4EC0, i32(0x35000000) + i32(0x35100000) + i32(0x35200000))                    # the stream header, its two tables (stream 3)
    g.put(0x35100000 + 600, bytes(0xC0) + i32(3) + i32(0x400)); g.put(0x35200000 + 600, bytes(0xC0) + i32(3) + i32(77777))
    g.put(0x35000400, bytes(0xC0) + i32(2) + i32(32000) + i32(500000) + i32(1000) + i32(1))
    S = 0x36000000                                                                            # the uber effect, for the shader test
    g.put(0x9F1280, i32(2)); g.put(0x9F1084, i32(0x37000000) + i32(0) + i32(S + 0xACB0)); g.put(0x37000000, sz('other.fx', 18)); g.put(S + 0xACB0, sz('ubershadergame.fx', 18))
    g.put(S, i32(0x02D604CD)); g.put(S + 0x70EC, i32(S + 0xABFC)); g.put(S + 0xABFC, i32(S + 0x1122B8) + bytes(12) + i32(0x11110000)); g.put(S + 0x1122B8, i32(0xFFFF0300))
    g.put(S + 0x8DFC + 0x10, i32(0x22220000))
    g.put(0x728710 + 12, i32(-1))                                                              # Tropical's card video not loaded yet: the block is asked to load them
    F = g.frame
    F(0, 0, 'Tropical4')                                                                      # attract
    for v in (0, 1, 0): F(1, 3, 'Tropical4', v, mode_val=0)                                  # mode menu on Championship: no popup once Classic is known
    for v in (0, 1, 0, 1, 0): F(1, 3, 'Tropical4', v, mode_val=2)                            # on Classic (not known yet: shown on every entry)
    F(1, 6, 'Tropical4'); F(1, 6, 'Tropical4', 1); F(1, 6, 'Tropical4'); F(1, 2, 'Tropical4')
    F(1, 3, 'Tropical4', hi=TRACK_IDS['Tropical4']); F(1, 3, 'Tropical4', hi=TRACK_IDS['Canyon4'])
    for v in (1, 1, 0, 1, 0, 1, 0): F(1, 3, 'Tropical4', v, hi=TRACK_IDS['Canyon4'])        # -> Arctic, Safari, own
    F(1, 3, 'Tropical4', 1, hi=TRACK_IDS['Canyon4']); F(1, 3, 'Tropical4', 0, hi=0x7777)    # Arctic; an id the list doesn't have
    for v in (0, 1, 0, 1, 0, 1, 0): F(1, 3, 'Tropical4', v, hi=TRACK_IDS['Alpine4'])        # Lakeside, Bad tune, own
    F(1, 3, 'Tropical4', 1, hi=TRACK_IDS['Alpine4']); F(1, 3, 'Tropical4', 0, hi=TRACK_IDS['Alpine4'])
    F(1, 3, 'Canyon4', hi=TRACK_IDS['Canyon4']); F(0, 3, 'Canyon4'); F(0, 0, 'Canyon4')     # Canyon (Arctic) confirmed: the race
    F(0, 0, 'Alpine4'); F(0, 0, 'Alpine4'); F(0, 0, 'Tropical4')                              # Alpine (Lakeside): shader, NaN shadow
    F(1, 3, 'Canyon4', mode_val=2); F(1, 3, 'Canyon4', 1, mode_val=2); F(1, 3, 'Canyon4', mode_val=2)   # a new game: Classic -> Mountain
    F(1, 6, 'Canyon4'); F(1, 2, 'Canyon4'); F(1, 2, 'Desert4'); F(0, 0, 'Desert4'); F(0, 0, 'Desert4')   # Classic learnt; race on track5
    F(1, 3, 'Desert4', mode_val=0); F(1, 3, 'Desert4', mode_val=2); F(1, 3, 'Desert4', 1, mode_val=2); F(1, 3, 'Desert4', mode_val=2)
    for k in range(140): F(1, 3, 'Desert4', mode_val=1)                                      # the popup counts down and goes
    return g

def sc_start():
    g = base_game(Game('start'))
    mgr = 0x38000000; drawn = mgr + 0x18 + 0x610; car = 0x38100000
    g.put(0x9F05F0, i32(0)); g.put(0x9EB970, f32(*[0.1 * k + (1 / 3.0 if k == 12 else 0) for k in range(16)])); g.put(0x9EBDA8, f32(1.0471976))
    g.put(0x9EB4EC, i32(mgr)); g.put(mgr + 0x18 + 0x184, i32(drawn)); g.put(drawn, i32(0x6EB808))
    g.put(mgr + 0x18 + 0x22C, i32(4) + i32(1) + i32(mgr + 0x18 + 0x500) + i32(drawn) + i32(mgr + 0x18 + 0x700) + i32(mgr + 0x18 + 0x800))
    g.put(mgr + 0x18 + 0x190, i32(drawn)); g.put(mgr + 0x18 + 0x1C8, i32(car))
    g.put(car + 0xAC, f32(12.5, -3.25, 1234.56789)); g.put(car + 0x135C + 0x20, f32(0.0, -0.0, 1.0))
    g.put(0x7ECE10, i32(0x27) + i32(0x27)); g.put(0x728598, i32(6)); g.put(0x9DB490, bytes(8) + i32(1) + bytes(0x10)); g.put(0x9C4A08, struct.pack('<q', 123456789))
    g.put(0x9DB4F4, i32(0)); g.put(0x9DB820, i32(1)); g.put(0x9DD61C, i32(1))
    F = g.frame; START, VIEW = 0x10, 0x1000
    F(1, 3, 'Tropical4'); F(1, 3, 'Tropical4', pad=START); F(1, 3, 'Tropical4')              # START in the menus: nothing
    F(0, 0, 'Canyon4')                                                                       # the race
    for k in range(10): F(0, 0, 'Canyon4', pad=START)                                        # a short press: a picture when let go
    for k in range(120): F(0, 0, 'Canyon4')                                                  # saved 1.5 s later, the name shown 3 s
    for k in range(90): F(0, 0, 'Canyon4', pad=START)                                        # held too long: nothing
    F(0, 0, 'Canyon4'); F(0, 0, 'Canyon4', pad=START); F(0, 0, 'Canyon4'); F(1, 3, 'Canyon4')   # a picture dropped: the menus came
    F(0, 0, 'Canyon4')
    for k in range(85): F(0, 0, 'Canyon4', pad=VIEW)                                        # VIEW CHANGE held: the championship left
    F(0, 0, 'Canyon4', set=[(0x9DB4F4, i32(0)), (0x7ECE14, i32(0x1B))])                     # the game takes it
    F(0, 0, 'Canyon4', set=[(0x7ECE10, i32(0x1B))]); F(0, 0, 'Canyon4', set=[(0x7ECE10, i32(0x2A))])
    for k in range(300): F(0, 0, 'Canyon4')                                                  # the fade never finishes: let go after 4 s
    F(0, 0, 'Canyon4', set=[(0x7ECE10, i32(0x3)), (0x7ECE14, i32(0x3))])                     # on its way to the menus
    F(0, 0, 'Canyon4', set=[(0x7ECE10, i32(0x27)), (0x7ECE14, i32(0x27)), (0x728598, i32(5))])
    for k in range(85): F(0, 0, 'Canyon4', pad=VIEW)                                        # a Quick Race the game does not take: withdrawn after 2 s
    for k in range(150): F(0, 0, 'Canyon4')
    F(0, 0, 'Canyon4', set=[(0x728598, i32(2))])
    for k in range(85): F(0, 0, 'Canyon4', pad=VIEW)                                        # the attract demo: no race
    m = mgr + 0x18; cock = m + 0x1A38                                                       # pictures whose camera has a name: the patched cockpit (flag 0x80000000) ...
    F(0, 0, 'Canyon4', set=[(m + 0x184, i32(cock)), (m + 0x230, i32(1)), (m + 0x238, i32(cock)), (cock, i32(0x6EBDF0))], setb=[(0x225C, i32(1))])
    for k in range(5): F(0, 0, 'Canyon4', pad=START)
    for k in range(150): F(0, 0, 'Canyon4')                                                  # (pictures at least 2 s apart)
    F(0, 0, 'Canyon4', set=[(m + 0x230, i32(0)), (m + 0x234, i32(cock))])                   # ... and slot 0 of the camera list (the block's own name)
    for k in range(5): F(0, 0, 'Canyon4', pad=START)
    for k in range(110): F(0, 0, 'Canyon4')
    return g

def sc_handling():
    g = base_game(Game('handling'))
    for c in ('c4', 'rsfocus', 'subaruimpreza', 'sx4', 'mitsubishievo', '207', 'st205', 'delta_hf', 'bowler', 'enduro'):
        g.file('Main_release/car1/%sbespoke_data.sbf' % c)
        if c not in ('207', 'enduro'): g.file('Main_release/car2/%sbespoke_data.sbf' % c)
    g.file('Main_release/cars/Hornetgravel_data.sbf'); g.file('Main_release/cars/st205gravel_data.sbf'); g.file('Main_release/car1/hornetgravel_data.sbf')
    g.file('SurfacePairEffect1/surfacepairdata_xdata.sbf')
    g.mod['handling.json'] = json.dumps({'version': 1, 'default': 'SR3', 'cars': {'ST205': 'src', 'Delta_HF': 'src', '207': 'realism', 'Enduro': 'realism', 'hornet': 'src', 'C4': 'mine'},
                                         'flavors': {'src': {'digit': '1', 'grip_file': True}, 'realism': {'digit': 2, 'grip_file': True}, 'mine': {'digit': '7'}, 'sr3': {'digit': '1'}, 'odd': {'digit': 'x'}}})
    W = 0x10A2C; F = g.frame
    F(1, 6, 'Tropical4'); F(1, 6, 'Tropical4', car_sel=6, front=W, keys=[0x32])             # car select on ST205: key 2 (SRC)
    F(1, 6, 'Tropical4', car_sel=6, front=W); F(1, 6, 'Tropical4', car_sel=5, front=W, keys=[0x63])   # 207: keypad 3 (Realism: no file in car2)
    F(1, 6, 'Tropical4', car_sel=10, front=W, keys=[0x31])                                   # the Hornet: 1 (SR3's own)
    F(1, 6, 'Tropical4', car_sel=10, front=W); F(1, 6, 'Tropical4', car_sel=10, front=W, keys=[0x33])   # 3 (Realism: no Hornet file)
    F(1, 6, 'Tropical4', car_sel=10, front=W, keys=[0x30]); F(1, 6, 'Tropical4', car_sel=2, front=1, keys=[0x32])   # 0 = show; a key with another window in front
    F(1, 2, 'Tropical4', front=W, set=[(0x9DBDA0 + 0xC, i32(0x32000008 + 0x80 * 6))])         # the player's car: ST205
    for k in range(5): F(1, 2, 'Tropical4', front=W)
    F(0, 0, 'Tropical4', front=W)                                                            # the race: every car on SRC
    F(0, 0, 'Tropical4', front=W, keys=[0x60]); F(0, 0, 'Tropical4', front=W, keys=[0x62])   # in a race: the player's car
    for k in range(200): F(0, 0, 'Tropical4', front=W)
    F(1, 6, 'Tropical4', front=W, set=[(0x9DBDA0 + 0xC, i32(0x32000008 + 0x80 * 10))])        # the Hornet now
    F(1, 6, 'Tropical4', car_sel=0, front=W, keys=[0x31, 0x32])                              # two keys at once
    F(0, 0, 'Tropical4', front=W)
    F(0, 0, 'Tropical4', front=W, keys=[0x91]); F(0, 0, 'Tropical4', front=1, keys=[0x11, 0x91])   # Scroll Lock alone; Ctrl+Scroll Lock with another window in front: nothing
    F(0, 0, 'Tropical4', front=W, keys=[0x11]); F(0, 0, 'Tropical4', front=W, keys=[0x11, 0x91]); F(0, 0, 'Tropical4', front=W, keys=[0x11, 0x91])   # Ctrl+Scroll Lock: the watchdog, once per press
    for k in range(200): F(0, 0, 'Tropical4', front=W)
    F(0, 0, 'Tropical4', front=W, keys=[0x11, 0x91])                                          # again later
    return g

def sc_late():
    g = base_game(Game('late'), cars_lib=False)
    g.put(0x9D6E3C, i32(1)); g.put(0x9D6E50, i32(0x3A000000))                                 # a game already in its menus when the launcher got ready
    g.put(0x72870C, i32(-1)); g.next_handle = 12                                               # the stand-in card video not loaded yet
    g.file('frontend/PC/Videos/HORNET.wmv')
    for d in ('Main_release/car2/c4bespoke_data.sbf',): g.file(d)                              # a built flavor (Realism), no handling.json
    g.file('Main_release/tracks/_SR3Extras/switch.json', '{"slots": {"Canyon4": {"title": "Canyon", "tracks": [{"title": "Arctic", "dir": "1"}]}}, "art": "no"}')
    g.file('Main_release/tracks/_SR3Extras/classic_mode.txt', ' -3 ')
    g.file('Main_release/track1/Canyon4/keep')
    F = g.frame
    F(1, 3, 'Tropical4'); F(1, 3, 'Tropical4'); F(0, 0, 'Tropical4', set=[(0x9D6E50, i32(0))]); F(0, 0, 'Tropical4')
    F(1, 3, 'Tropical4'); F(1, 3, 'Tropical4', hi=TRACK_IDS['Canyon4']); F(1, 3, 'Tropical4', 1, hi=TRACK_IDS['Canyon4'])
    F(0, 0, 'Canyon4'); F(0, 0, 'Canyon4')
    return g

def sc_odd():
    """unexpected bytes everywhere: every patch refuses, says so, and the loop still runs"""
    g = base_game(Game('odd'))
    g.put(0x61827A, bytes(6)); g.put(0x600790, bytes(5)); g.put(0x6006F0, bytes([0xE9, 0, 0, 0, 0])); g.put(0x61C30B, bytes(15))
    g.put(0x5C6144, bytes([0xE8, 1, 2, 3, 4])); g.put(0x5CFF32, bytes([0xE8, 9, 9, 9, 9])); g.put(0x678878, i32(0x40000000))
    g.put(0x6C631D, b'q'); g.put(0x5C5770, bytes(6)); g.put(0x4EEF70, bytes([0x55, 1, 2, 3, 4, 5]))
    g.put(0x648333, i32(120000)); g.put(0x6480FA, i32(0x7FFFFFFF))
    g.file('Main_release/car1/c4bespoke_data.sbf'); g.file('SurfacePairEffect1/surfacepairdata_xdata.sbf')
    g.mod['handling.json'] = '{"default": "src", "flavors": {"src": {"digit": "1", "grip_file": true}}'      # broken JSON
    g.file('Main_release/tracks/_SR3Extras/switch.json', switch_json({'Canyon4': dict(title='Canyon', tracks=[dict(title='Arctic', dir='1', video='ZZ9')])}, art=False))
    g.file('Main_release/track1/Canyon4/road.txt', 'hide'); g.file('Main_release/track1/Canyon4/shader.txt', 'untextured-own')
    g.file('Main_release/track1/Canyon4/shadow.txt', '0.5 30'); g.file('Main_release/track1/Canyon4/arcade_times.bin', bytes(100))
    F = g.frame
    F(1, 6, 'Tropical4'); F(1, 2, 'Tropical4'); F(1, 3, 'Tropical4', hi=TRACK_IDS['Canyon4']); F(1, 3, 'Tropical4', 1, hi=TRACK_IDS['Canyon4'])
    F(1, 3, 'Canyon4', hi=TRACK_IDS['Canyon4']); F(0, 0, 'Canyon4'); F(0, 0, 'Canyon4')
    return g

# ---- the re-attach path: the game patched (the first run, not traced), then PLAY.bat again with other settings (traced)
CAVE, SITE1 = 0x673C80, 0x5F72DD
def again(name, **settings):
    g = Game(name); g.reinstall = settings; g.frames = []; return g
def sc_retune(): return again('retune', profile='Chase', overlay=120, mouse=0.02, blend=0)        # the block kept, its settings rewritten, the blend's hook taken out
def sc_reblend(): return again('reblend', profile='SR3 Chase Far', blend=1.5, canary=True)
def sc_newer():                                                                                     # a newer build's block: a fresh one, the old one's state carried over
    g = again('newer', profile='Drone'); mgr = 0x3B000000
    g.after = [[0x1000, '90'], [0x58, i32(mgr).hex()], [0x2240 + 0x18, i32(0x12345678).hex()], [0x2180, (i32(0x1111) * 12).hex()], [0xF98, (b'\x01' * 16).hex()]]
    g.between = [[mgr + 0x1A38, i32(0x6EBDF0).hex()], [mgr + 0x1A38 + 0x194, i32(0x20000000 + 0x2240).hex()]]
    return g
def sc_older():                                                                                     # an older build: a hook site neither the game's nor this build's
    g = again('older', profile='Daytona'); g.between = [[SITE1, 'e9aabbccdd']]; return g
def sc_foreign():                                                                                   # someone else's bytes: refused, nothing written
    g = again('foreign'); g.between = [[CAVE, '5a5a5a5a'], [SITE1, 'e9aabbccdd']]; return g
def sc_alt():                                                                                       # another profiles file (hiddenCameras false: fewer slots)
    g = again('altfile'); tmp = os.path.join(tempfile.gettempdir(), 'live_lockstep_alt_profiles.yaml')
    src = open(os.path.join(REPO, 'profiles.yaml'), encoding='utf-8').read().splitlines()
    open(tmp, 'w', newline='\n').write('\n'.join([l for l in src if not l.lower().startswith('hiddencameras')] + ['hiddenCameras: false', '']))
    g.reinstall = dict(profiles_file=tmp, profile='Chase Far'); return g
DECISIONS = ('L Camera patch was already applied', 'L An older build of the camera patch', 'L Unexpected bytes at ')   # the install's log lines both word alike

def sc_srcport_old():
    g = sc_handling(); g.name = 'srcport_old'; g.frames = g.frames[:2]
    g.put(0x678878, i32(0x39000000)); g.put(0x390023E0, i32(0x50435253))
    return g

def sc_srcport_foreign():
    g = sc_handling(); g.name = 'srcport_foreign'; g.frames = g.frames[:2]
    g.put(0x678878, i32(0x39000000)); g.put(0x390023E0, i32(0x12345678))
    return g

SCENARIOS = [sc_switch, sc_start, sc_handling, sc_late, sc_odd, sc_retune, sc_reblend, sc_newer, sc_older, sc_foreign, sc_alt,
             sc_srcport_old, sc_srcport_foreign]

def lay_out(g, root):
    game, mod = os.path.join(root, 'game'), os.path.join(root, 'mod')
    for d in (game, mod): os.makedirs(d, exist_ok=True)
    for rel, data in g.files.items():
        p = os.path.join(game, *rel.split('/')); os.makedirs(os.path.dirname(p), exist_ok=True)
        if not rel.endswith('/keep'): open(p, 'wb').write(data)
    for rel, data in g.mod.items(): open(os.path.join(mod, rel), 'w', newline='\n', encoding='utf-8').write(data)
    sc = os.path.join(root, 'scenario.json'); json.dump(g.json(), open(sc, 'w'))
    return sc, os.path.join(game, 'Rally.exe'), mod

def norm(path, root):
    t = open(path, encoding='utf-8', errors='replace').read() if os.path.exists(path) else ''
    return [l.replace(root, '<ROOT>') for l in t.replace('\r\n', '\n').split('\n') if l]

def main(argv):
    exe = argv[argv.index('--exe') + 1] if '--exe' in argv else os.path.join(HERE, 'build', 'livetest.exe')
    only = argv[argv.index('--only') + 1] if '--only' in argv else None
    tmp = tempfile.mkdtemp(prefix='live_lockstep_'); bad = 0; n = 0
    for make in SCENARIOS:
        g = make()
        if only and g.name != only: continue
        n += 1; ra, rb = os.path.join(tmp, g.name, 'ps1'), os.path.join(tmp, g.name, 'c')
        sa, ea, ma = lay_out(g, ra); sb, eb, mb = lay_out(g, rb)
        ta, tb = os.path.join(ra, 'trace.txt'), os.path.join(rb, 'trace.txt')
        pa = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', os.path.join(HERE, 'live_ps1.ps1'), '-Scenario', sa, '-GameExe', ea, '-ModDir', ma, '-Out', ta], capture_output=True, text=True)
        pb = subprocess.run([exe, sb, eb, mb, os.path.join(REPO, 'profiles.yaml'), tb], capture_output=True, text=True)
        A, B = norm(ta, ra), norm(tb, rb)
        if g.reinstall is not None:                                    # the install's other log lines are worded differently (sr3mods.ps1's for PLAY.bat, sr3mods' for its callers)
            A = [l for l in A if not l.startswith('L ') or l.startswith(DECISIONS)]; B = [l for l in B if not l.startswith('L ') or l.startswith(DECISIONS)]
        if not A: A = ['(no trace from sr3mods.ps1: %s)' % (pa.stdout + pa.stderr).strip()[-800:]]
        if not B: B = ['(no trace from livetest.exe, exit %d: %s)' % (pb.returncode, (pb.stdout + pb.stderr).strip()[-400:])]
        diff = []
        for label, trace in (('ps1', A), ('c', B)):
            writes = [s for s in trace if s.startswith('W 678878 ')]
            expected = ['W 678878 0 20c84500'] if g.name == 'srcport_old' else []
            if writes != expected: diff.append('%s: unexpected SRC vehicle-step writes %r' % (label, writes))
            if any('SRC turning: in (' in s or 'SRC turning: already in' in s for s in trace):
                diff.append('%s: disabled SRC port was installed or retained' % label)
        if A != B:
            k = next((i for i in range(min(len(A), len(B))) if A[i] != B[i]), min(len(A), len(B)))
            fr = next((A[i] for i in range(k, -1, -1) if i < len(A) and A[i].startswith('F ')), 'F 0')
            diff.append('trace line %d (after %s): ps1 %s | c %s' % (k + 1, fr, A[k][:300] if k < len(A) else '(end)', B[k][:300] if k < len(B) else '(end)'))
        for rel, how in (('mod/handling.json', 'json'), ('game/Main_release/tracks/_SR3Extras/classic_mode.txt', 'text')):
            fa, fb = os.path.join(ra, *rel.split('/')), os.path.join(rb, *rel.split('/'))
            va = open(fa, encoding='utf-8-sig').read() if os.path.exists(fa) else None; vb = open(fb, encoding='utf-8-sig').read() if os.path.exists(fb) else None
            if how == 'json' and va and vb:
                try: va, vb = json.loads(va), json.loads(vb)
                except ValueError: pass
            if va != vb: diff.append('%s: ps1 %r | c %r' % (rel, str(va)[:200], str(vb)[:200]))
        if diff: bad += 1; print('DIFFERENT %-9s (%d / %d trace lines)' % (g.name, len(A), len(B))); [print('   ' + d) for d in diff]
        else: print('same      %-9s (%d trace lines, %d frames)' % (g.name, len(A), len(g.frames)))
    if '--keep' in argv: print('kept: ' + tmp)
    else: shutil.rmtree(tmp, ignore_errors=True)
    print('LIVE LOCKSTEP: %d scenarios, %d the same, %d different' % (n, n - bad, bad))
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
