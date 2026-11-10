"""The parametric EQ (docs/modules/peq.md): the player's filter (patch/peq_player.c) run inside the patched hciplayer under Unicorn, its libc
routed to Python through hciplayer's own PLT slots, and compared with a Python model of the same RBJ cascade; the APO / AutoEQ parser and the
state record (patch/peq.c) in demo's payload; the Equalizer page (patch/peq_ui.c); and the record the page writes played by the player."""
import math, os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_F12, UC_MIPS_REG_F14, UC_MIPS_REG_CP0_STATUS
import mod_player
import pod_settings as ST
import peq_graph as G

PODCASTS = sibling('podcasts')
STATE, STATE_TMP, KILL, EQ_DIR = '/mnt/data/m1plus/playback-eq', '/mnt/data/m1plus/playback-eq.tmp', '/mnt/mmc/m1plus-off', '/mnt/mmc/EQ'
FLOAT, REINIT, GAIN_SET, GAIN_GET, CMDLINE = 0x1d, 0x10000100, 0x40001d00, 0x40001d01, 0x20000300
BANDS, NAME = 30, 64
GRAPHIC_F = (31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
STOCK_GAINS, MPCTX = 0xb10df4, 0xaf9e30
FR = 1 << 29 | 1 << 26   # CP0 Status: CU1 and FR (the payloads are -mfp64)
AUTOEQ = b'''Preamp: -6.2 dB
Filter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.70
Filter 2: ON PK Fc 2000 Hz Gain -3.1 dB Q 1.41
Filter 3: ON HSC Fc 10000 Hz Gain 2.0 dB Q 0.70
Filter 4: ON PK Fc 140 Hz Gain -1.5 dB Q 0.50
Filter 5: OFF PK Fc 0 Hz Gain 0.0 dB Q 0.00
'''
AUTOEQ_BANDS = [(1, 1, 105, 5.5, 0.7), (1, 0, 2000, -3.1, 1.41), (1, 2, 10000, 2.0, 0.7), (1, 0, 140, -1.5, 0.5)]


# ---- the record (patch/peq.h): peq_band 32 bytes, peq_preset 992, peq_state 1152 (the 10-Band EQ's curve, preamp, gain[10], custom[10] after the name), the file PEQ_MAGIC + the state
def pack_preset(bands, preamp=0.0, automatic=2, balance=0.0, bypass=0):
    out = struct.pack('<iid', len(bands), bypass, preamp)
    full = list(bands) + [(0, 0, 1000.0, 0.0, 1.41)] * (BANDS - len(bands))
    out += b''.join(struct.pack('<iiddd', e, t, f, g, q) for e, t, f, g, q in full)
    return out + struct.pack('<dii', balance, automatic, 0)


def pack_state(mode, preset, name=b'', curve=0, preamp=-1, gain=None, custom=None):
    """mode 0 the 10-Band EQ (curve 0 Flat .. 8 Jazz, 9 Custom; preamp -1 Auto, 0..12 a cut in dB; its ten gains), 1 a preset file."""
    return (b'M1PEQ02\0' + struct.pack('<i4x', mode) + preset + name.ljust(NAME, b'\0')
            + struct.pack('<ii20f', curve, preamp, *(list(gain or [0.0] * 10) + list(custom or [0.0] * 10))))


def tenband(gain, preamp=-1, curve=9, custom=None):
    return pack_state(0, pack_preset([]), b'', curve, preamp, gain, custom)


STATE_SIZE = 8 + 1152   # PEQ_MAGIC + peq_state
NAME_OF = lambda rec: rec[-NAME - 88:-88].rstrip(b'\0')   # the preset file's name in a record
CURVES = [[0] * 10, [3, 1, 0, -2, -4, -4, -2, 0, 1, 2], [-2, 0, 2, 4, -2, -2, 0, 0, 4, 4], [-2, 3, 4, 1, -2, -2, 0, 0, 4, 4],
          [-2, 0, 2, 1, 0, 0, 0, 0, -2, -4], [-6, 0, 0, 0, 0, 0, 2, 0, 2, 0], [-4, 0, 2, 1, 0, 0, 0, 0, -4, -6],
          [0, 3, 3, 2, 0, 0, 0, 0, 1, 1], [0, 0, 0, 2, 2, 2, 0, 1, 2, 2], [0] * 10]   # Flat, Pop, Rock, Dance, Blues, Metal, Vocal, Classical, Jazz, Custom (stock's rows 4..11 of demo's 12 x 10 float table at 0x74b5bc)


def unpack_preset(raw):
    count, bypass, preamp = struct.unpack_from('<iid', raw, 0)
    bands = [struct.unpack_from('<iiddd', raw, 16 + 32 * i) for i in range(count)]
    balance, automatic, _ = struct.unpack_from('<dii', raw, 16 + 32 * BANDS)
    return dict(count=count, bypass=bypass, preamp=preamp, bands=bands, balance=balance, automatic=automatic)


# ---- the Python model of patch/peq.c's engine
def design(t, f, g, q, rate):
    a, w = 10 ** (g / 40), 2 * math.pi * f / rate
    c, alpha = math.cos(w), math.sin(w) / (2 * q)
    r = 2 * math.sqrt(a) * alpha
    if t == 0: b0, b1, b2, a0, a1, a2 = 1 + alpha * a, -2 * c, 1 - alpha * a, 1 + alpha / a, -2 * c, 1 - alpha / a
    elif t == 1:
        b0, b1, b2 = a * ((a + 1) - (a - 1) * c + r), 2 * a * ((a - 1) - (a + 1) * c), a * ((a + 1) - (a - 1) * c - r)
        a0, a1, a2 = (a + 1) + (a - 1) * c + r, -2 * ((a - 1) + (a + 1) * c), (a + 1) + (a - 1) * c - r
    else:
        b0, b1, b2 = a * ((a + 1) + (a - 1) * c + r), -2 * a * ((a - 1) + (a + 1) * c), a * ((a + 1) + (a - 1) * c - r)
        a0, a1, a2 = (a + 1) - (a - 1) * c + r, 2 * ((a - 1) - (a + 1) * c), (a + 1) - (a - 1) * c - r
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def compiled(bands, rate):
    return [(design(t, f, g, q, rate), e) for e, t, f, g, q in bands if e and g and f < rate / 2]


def response(cs, rate, f):
    w = 2 * math.pi * f / rate
    z1, z2 = complex(math.cos(w), -math.sin(w)), complex(math.cos(2 * w), -math.sin(2 * w))
    l = r = 1.0
    for (b0, b1, b2, a1, a2), e in cs:
        m = abs((b0 + b1 * z1 + b2 * z2) / (1 + a1 * z1 + a2 * z2)) ** 2
        if e != 3: l *= m
        if e != 2: r *= m
    return l, r


def auto_gain(bands, rate):
    """peq.c peak(): the loudest |H|^2 of either side over DC, Nyquist, 1024 log points and the band centres; Auto plays its inverse square root."""
    cs, ny, best = compiled(bands, rate), rate / 2, 1.0
    for k in range(-2, 1024 + len(bands)):
        f = 0 if k == -2 else ny if k == -1 else ny ** (k / 1023) if k < 1024 else bands[k - 1024][2]
        if f >= ny and k != -1: continue
        best = max(best, *response(cs, rate, f))
    best = 1 if best < 1.0000230261 else min(best, 1e6)
    return best ** -0.5


def model(bands, rate, nch, x, preamp_lin=1.0):
    """The cascade on interleaved float32 x, each channel from zero memory, then the preamp: float32 out."""
    cs, out = compiled(bands, rate), list(x)
    for ch in range(nch):
        z = [[0.0, 0.0] for _ in cs]
        for i in range(ch, len(x), nch):
            v = x[i]
            for k, ((b0, b1, b2, a1, a2), e) in enumerate(cs):
                if e > 1 and e - 1 != ch + 1: continue
                y = b0 * v + z[k][0] + 1e-18 - 1e-18
                z[k][0] = b1 * v - a1 * y + z[k][1]
                z[k][1] = b2 * v - a2 * y
                v = y
            out[i] = struct.unpack('<f', struct.pack('<f', v * preamp_lin))[0]
    return out


def f32(xs): return [struct.unpack('<f', struct.pack('<f', v))[0] for v in xs]


def tone(n, nch, rate, freqs=(997.0, 61.0, 7000.0), amp=0.2):
    return f32([sum(amp * math.sin(2 * math.pi * fr * i / rate + c) for fr in freqs) for i in range(n) for c in range(nch)])


# ---- hciplayer under Unicorn
class Player:
    """The patched /usr/bin/hciplayer's LOAD segments; each libc import peq_player.c uses is a PLT slot pointing at a trap here."""
    TRAP, RET, STACK, HEAP = 0x00fe0000, 0x00ff0000, 0x7ffe0000, 0x40000000

    def __init__(self, files=None):
        self.data = open(os.path.join(WORK, 'rootfs', mod_player.REL), 'rb').read()
        self.u = u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        for _, (t, o, v, _, f, m, _, _) in pod.segments(self.data):
            if t != 1: continue
            start = v & ~0xfff
            u.mem_map(start, ((v + m + 0xfff) & ~0xfff) - start)
            u.mem_write(v, self.data[o:o + f])
        u.mem_map(self.STACK & ~0xfffff, 0x200000)
        u.mem_map(self.HEAP, 0x1000000)
        u.mem_map(self.TRAP, 0x1000)
        u.reg_write(UC_MIPS_REG_CP0_STATUS, u.reg_read(UC_MIPS_REG_CP0_STATUS) | FR)
        self.heap, self.files, self.handles, self.calls = self.HEAP, dict(files or {}), {}, []
        self.clock = 100000   # ms, what clock_gettime(CLOCK_MONOTONIC) answers
        manifest = json.load(open(os.path.join(WORK, 'playerbuild', 'manifest.json')))
        self.manifest, self.traps = manifest, {}
        for i, (name, slot) in enumerate(sorted(manifest['libc_slots'].items())):
            at = self.TRAP + 8 * i
            self.traps[at] = name
            u.mem_write(slot, struct.pack('<I', at))
        u.hook_add(UC_HOOK_CODE, self._trap, begin=self.TRAP, end=self.TRAP + 0xfff)

    def word(self, a): return struct.unpack('<I', self.u.mem_read(a, 4))[0]
    def setword(self, a, v): self.u.mem_write(a, struct.pack('<I', v & 0xffffffff))

    def malloc(self, n):
        a = self.heap; self.heap = (self.heap + n + 15) & ~15
        self.u.mem_write(a, bytes(n)); return a

    def cstr(self, s):
        s = s.encode() if isinstance(s, str) else s
        a = self.malloc(len(s) + 1); self.u.mem_write(a, s + b'\0'); return a

    def read_cstr(self, a):
        out = b''
        while True:
            c = bytes(self.u.mem_read(a + len(out), 64)); i = c.find(b'\0')
            if i >= 0: return out + c[:i]
            out += c

    def _trap(self, u, address, size, _):
        name = self.traps[address]
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        d = lambda r: struct.unpack('<d', struct.pack('<Q', u.reg_read(r) & (2 ** 64 - 1)))[0]
        ret, fret = 0, None
        if name == 'memset': u.mem_write(a0, bytes([a1 & 0xff]) * a2); ret = a0
        elif name == 'memcpy': u.mem_write(a0, bytes(u.mem_read(a1, a2))); ret = a0
        elif name == 'memcmp':
            x, y = bytes(u.mem_read(a0, a2)), bytes(u.mem_read(a1, a2)); ret = (x > y) - (x < y)
        elif name == 'strcmp':
            x, y = self.read_cstr(a0), self.read_cstr(a1); ret = (x > y) - (x < y)
        elif name == 'strlen': ret = len(self.read_cstr(a0))
        elif name == 'calloc': ret = self.malloc(a0 * a1)
        elif name == 'free': self.calls.append(('free', a0))
        elif name == 'fopen':
            path = self.read_cstr(a0).decode(); self.calls.append(('fopen', path))
            if path in self.files: ret = self.malloc(4); self.handles[ret] = [self.files[path], 0]
        elif name == 'fread':
            data, pos = self.handles[a3]; chunk = data[pos:pos + a1 * a2]
            if chunk: u.mem_write(a0, chunk)
            self.handles[a3][1] += len(chunk); ret = len(chunk) // a1
        elif name == 'fclose': self.handles.pop(a0)
        elif name == 'clock_gettime':
            assert a0 == 1, 'CLOCK_MONOTONIC'
            u.mem_write(a1, struct.pack('<ii', self.clock // 1000, self.clock % 1000 * 1000000))
        elif name in ('pow', 'cos', 'sin'):
            x, y = d(UC_MIPS_REG_F12), d(UC_MIPS_REG_F14)
            fret = {'pow': math.pow, 'cos': lambda a, _: math.cos(a), 'sin': lambda a, _: math.sin(a)}[name](x, y)
        else: raise AssertionError(f'unmocked libc {name}')
        if fret is not None: u.reg_write(UC_MIPS_REG_F0, struct.unpack('<Q', struct.pack('<d', fret))[0])
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def call(self, fn, *args):
        u = self.u
        u.reg_write(UC_MIPS_REG_SP, self.STACK); u.reg_write(UC_MIPS_REG_RA, self.RET); u.reg_write(UC_MIPS_REG_T9, fn)
        for r, v in zip((UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3), args): u.reg_write(r, v & 0xffffffff)
        u.emu_start(fn, self.RET)
        assert u.reg_read(UC_MIPS_REG_PC) == self.RET, 'did not return'
        return struct.unpack('<i', struct.pack('<I', u.reg_read(UC_MIPS_REG_V0)))[0]

    # the filter, as hciplayer's af_add and its playback loop use it
    def open(self):
        af = self.malloc(48)
        self.opened = self.call(self.word(mod_player.EQ_OPEN_SLOT), af)
        return af

    def reinit(self, af, rate, nch=2, fmt=FLOAT, bps=4):
        d = self.malloc(24); self.u.mem_write(d, struct.pack('<6i', 0, 0, rate, nch, fmt, bps))
        r = self.call(self.word(af + 4), af, REINIT, d)
        return r, struct.unpack('<6i', bytes(self.u.mem_read(d, 24))), struct.unpack('<6i', bytes(self.u.mem_read(self.word(af + 20), 24)))

    def gains(self, af, gains, cmd=GAIN_SET, channel=0):
        g = self.malloc(40); self.u.mem_write(g, struct.pack('<10f', *gains))
        ext = self.malloc(8); self.u.mem_write(ext, struct.pack('<Ii', g, channel))
        return self.call(self.word(af + 4), af, cmd, ext), struct.unpack('<10f', bytes(self.u.mem_read(g, 40)))

    def play(self, af, samples, rate, nch=2, fmt=FLOAT, bps=4, raw=None):
        body = raw if raw is not None else struct.pack(f'<{len(samples)}f', *samples)
        buf = self.malloc(len(body)); self.u.mem_write(buf, body)
        d = self.malloc(24); self.u.mem_write(d, struct.pack('<Iiiiii', buf, len(body), rate, nch, fmt, bps))
        back = self.call(self.word(af + 12), af, d) & 0xffffffff
        out = bytes(self.u.mem_read(buf, len(body)))
        return back == d, (out if raw is not None else list(struct.unpack(f'<{len(samples)}f', out)))

    def stock_gains(self, gains): self.u.mem_write(STOCK_GAINS, struct.pack('<10f', *gains))

    def codec(self, drv=None, name=None):
        """mpctx -> sh_audio (+0x2c) -> codec (+4) -> name (+0x3d0), driver (+0x3e0)."""
        sh, codec = self.malloc(0x40), self.malloc(0x400)
        if drv: self.setword(codec + 0x3e0, self.cstr(drv))
        if name: self.setword(codec + 0x3d0, self.cstr(name))
        self.setword(sh + 4, codec)
        mp = self.mpctx(); self.setword(mp + 0x2c, sh)

    def mpctx(self):
        mp = self.word(MPCTX)
        if not mp: mp = self.malloc(0x40); self.setword(MPCTX, mp)
        return mp

    def ended(self, eof=1):
        """mpctx -> d_audio (+0x34) -> eof (+0x1c): the demuxer reached the end of the file."""
        mp = self.mpctx(); ds = self.word(mp + 0x34)
        if not ds: ds = self.malloc(0x80); self.setword(mp + 0x34, ds)
        self.setword(ds + 0x1c, eof)

    def leave(self, af):
        self.call(self.word(af + 8), af)


def near(a, b, tol=2e-6): return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def rms(xs, nch, ch, skip=0):
    v = xs[skip * nch + ch::nch]
    return math.sqrt(sum(s * s for s in v) / len(v))


def player_tests(ctx):
    expect = ctx.expect
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', mod_player.REL), 'rb').read()
    built = open(os.path.join(WORK, 'rootfs', mod_player.REL), 'rb').read()
    w = mod_player.word
    expect(pod.sha(stock) == mod_player.PLAYER_SHA, 'the stock hciplayer is the pinned one')
    expect(w(built, mod_player.EQ_OPEN_SLOT) != mod_player.STOCK_OPEN and w(stock, mod_player.EQ_OPEN_SLOT) == mod_player.STOCK_OPEN,
           'the equalizer af_info open slot points into the payload, not at stock af_equalizer')
    expect(all(w(built, a) == new and w(stock, a) == old for a, old, new in mod_player.RATE_GATES), 'both 48 kHz gates are patched as pinned')
    expect(all(w(built, a) == old for a, old, _ in mod_player.PINS), 'every pinned stock word is unchanged')
    segs = pod.segments(built)
    expect(segs[-1][1][:3] == (1, segs[-1][1][1], mod_player.PLAYER_BASE) and segs[-1][1][6] == 7, 'the spare PT_NULL is the payload LOAD at 0xe10000, RWX')
    diff = [i for i in range(0, len(stock), 4) if stock[i:i + 4] != built[i:i + 4]]
    want = {pod.fileoff(stock, a) for a in [mod_player.EQ_OPEN_SLOT] + [a for a, _, _ in mod_player.RATE_GATES]}
    phdr = segs[-1][0]
    expect(set(diff) - set(range(phdr, phdr + 32)) == want, f'only the open slot, the two gates and the program header change in the stock bytes ({[hex(i) for i in diff][:8]})')

    # open: control, uninit and play set, mul 1, data and setup allocated
    p = Player()
    af = p.open()
    expect(p.opened == 1 and all(mod_player.PLAYER_BASE <= p.word(af + o) < mod_player.PLAYER_BASE + 0x10000 for o in (4, 8, 12)),
           'peq_open: AF_OK, control / uninit / play in the payload')
    expect(struct.unpack('<d', bytes(p.u.mem_read(af + 40, 8)))[0] == 1.0 and p.word(af + 16) and p.word(af + 20), 'mul 1, setup and data allocated')
    expect(('fopen', KILL) in p.calls, 'the open looks for the kill switch')

    # no record, stock gains flat: bit-exact
    r, _, data = p.reinit(af, 44100)
    expect(r == 1 and data[2:] == (44100, 2, FLOAT, 4), 'float stereo at 44.1 kHz is accepted as it comes')
    x = tone(512, 2, 44100)
    same, y = p.play(af, x, 44100)
    expect(same and y == x, 'flat graphic gains and no record: every sample untouched')

    # the 10-Band EQ: the record's ten gains as peaking bands, Q 1.41, with its preamp (stock's gains are not read)
    gains = [0, 3, 0, -2, 0, 6, 0, 0, -4, 1.5]
    tb = [(1, 0, f, g, 1.41) for f, g in zip(GRAPHIC_F, gains)]
    for what, pre, lin in (('Auto', -1, auto_gain(tb, 48000)), ('0 dB', 0, 1.0), ('-6 dB', 6, 10 ** (-6 / 20)), ('-12 dB', 12, 10 ** (-12 / 20))):
        p = Player({STATE: tenband(gains, pre)}); p.stock_gains([2] * 10); af = p.open(); p.reinit(af, 48000)
        x = tone(1024, 2, 48000)
        _, y = p.play(af, x, 48000)
        want = model(tb, 48000, 2, x, lin)
        expect(near(y, want), f'10-Band EQ, preamp {what}: the record\'s ten gains as peaking bands match the model, stock\'s gains ignored (max err {max(abs(a - b) for a, b in zip(y, want)):.2e})')
    expect(('fopen', STATE) in p.calls, 'the reinit reads the record')
    expect(auto_gain(tb, 48000) < 1 and abs(20 * math.log10(auto_gain(tb, 48000)) + 6.0) < 1.0, 'Auto cuts by about the largest boost (6 dB here)')
    p = Player({STATE: tenband([0.0] * 10, -1)}); af = p.open(); p.reinit(af, 44100)
    x = tone(512, 2, 44100)
    same, y = p.play(af, x, 44100)
    expect(same and y == x, 'a flat 10-Band curve with Auto: every sample untouched (Auto never boosts)')

    # a preset record: its bands and its own preamp, at 44.1, 96 and 192 kHz (the 10 kHz shelf too; a band at or past Nyquist skipped)
    for rate in (44100, 96000, 192000, 32000):
        rec = pack_state(1, pack_preset(AUTOEQ_BANDS + [(1, 0, 18000, 4.0, 2.0)], preamp=-6.2, automatic=2), b'x.txt')
        p = Player({STATE: rec}); p.stock_gains(gains); af = p.open()
        r, _, _ = p.reinit(af, rate)
        x = tone(1024, 2, rate)
        _, y = p.play(af, x, rate)
        want = model(AUTOEQ_BANDS + [(1, 0, 18000, 4.0, 2.0)], rate, 2, x, 10 ** (-6.2 / 20))
        expect(r == 1 and near(y, want), f'{rate} Hz: the record\'s preset and its preamp match the model (max err {max(abs(a - b) for a, b in zip(y, want)):.2e})')

    # Auto preamp: the cut for this rate's own peak
    bands = [(1, 0, 1000, 9.0, 1.0), (1, 1, 80, 6.0, 0.7)]
    for rate in (44100, 96000):
        p = Player({STATE: pack_state(1, pack_preset(bands, preamp=0, automatic=1))}); af = p.open(); p.reinit(af, rate)
        x = tone(1024, 2, rate)
        _, y = p.play(af, x, rate)
        g = auto_gain(bands, rate)
        expect(near(y, model(bands, rate, 2, x, g)), f'{rate} Hz Auto: the preamp is -{-20 * math.log10(g):.2f} dB, the model\'s peak cut')

    # left / right only bands and balance
    bands = [(2, 0, 1000, 6.0, 1.0), (3, 0, 3000, -6.0, 1.0)]
    p = Player({STATE: pack_state(1, pack_preset(bands, preamp=-1.0, automatic=2, balance=2.0))}); af = p.open(); p.reinit(af, 48000)
    x = tone(512, 2, 48000)
    _, y = p.play(af, x, 48000)
    want = f32([v * (10 ** (-2 / 20) if i % 2 == 0 else 1) for i, v in enumerate(model(bands, 48000, 2, x))])
    want = f32([v * 10 ** (-1 / 20) for v in want])
    expect(near(y, want, 5e-6), 'a left-only and a right-only band, and balance turning the left down')

    # the gain command: channel 0 rereads the record (here: a 10-Band one written while playing; the gains the command carries are not used), through the 20 ms ramp
    p = Player({STATE: tenband([0.0] * 10, 0)}); af = p.open(); p.reinit(af, 48000)
    x = tone(48000 // 10, 2, 48000, freqs=(1000.0,))
    _, y0 = p.play(af, x, 48000)
    r, _ = p.gains(af, [0, 0, 0, 0, 0, 6, 0, 0, 0, 0], channel=1)
    _, y1 = p.play(af, x, 48000)
    expect(r == 1 and y1 == x, 'GAIN SET on channel 1 changes nothing (channel 0 rereads)')
    p.files[STATE] = tenband([0, 0, 0, 0, 0, 6, 0, 0, 0, 0], 0)
    r, _ = p.gains(af, [0] * 10)
    _, y2 = p.play(af, x, 48000)
    l, _ = response(compiled([(1, 0, f, g, 1.41) for f, g in zip(GRAPHIC_F, [0, 0, 0, 0, 0, 6, 0, 0, 0, 0])], 48000), 48000, 1000)
    ratio = rms(y2, 2, 0, skip=2400) / rms(x, 2, 0, skip=2400)
    expect(r == 1 and abs(20 * math.log10(ratio) - 10 * math.log10(l)) < 0.05, f'GAIN SET on channel 0: the new curve plays (+{20 * math.log10(ratio):.2f} dB at 1 kHz, model {10 * math.log10(l):.2f})')
    first = [abs(a - b) for a, b in zip(y2[:20], x[:20])]
    expect(max(first) < 0.01, 'the change starts at the old curve: the 20 ms ramp, not a jump')
    p.files[STATE] = pack_state(1, pack_preset([(1, 0, 1000, -12.0, 1.0)], automatic=2))
    p.gains(af, [0] * 10)
    _, y3 = p.play(af, x, 48000)
    l, _ = response(compiled([(1, 0, 1000, -12.0, 1.0)], 48000), 48000, 1000)
    ratio = rms(y3, 2, 0, skip=2400) / rms(x, 2, 0, skip=2400)
    expect(abs(20 * math.log10(ratio) - 10 * math.log10(l)) < 0.05, f'a record written while playing plays after the next gain command ({20 * math.log10(ratio):.2f} dB)')
    r, back = p.gains(af, [1] * 10, cmd=GAIN_GET)
    expect(r == 1 and back == (0.0,) * 10, 'GAIN GET answers ten zeros')
    expect(p.call(p.word(af + 4), af, CMDLINE, 0) == 1 and p.call(p.word(af + 4), af, 0x12345, 0) == -1, 'the command line is accepted and ignored; unknown commands are AF_UNKNOWN')

    # DSD and the kill switch: everything passes, whatever the record says
    rec = pack_state(1, pack_preset([(1, 0, 1000, 12.0, 1.0)], automatic=2))
    for what, setup in (('dsdiff driver', lambda p: p.codec(drv='dsdiff')), ('FFmpeg ffdsd codec', lambda p: p.codec(name='ffdsd_msbf')),
                        ('kill switch', lambda p: p.files.update({KILL: b''}))):
        p = Player({STATE: rec}); setup(p); af = p.open()
        r, din, data = p.reinit(af, 352800, fmt=0x0a, bps=4)
        raw = bytes(range(256)) * 8
        same, out = p.play(af, None, 352800, fmt=0x0a, raw=raw)
        expect(r == 1 and din[4] == 0x0a and data[4] == 0x0a and out == raw, f'{what}: the format is accepted as it is and the bytes pass untouched')
        r, _ = p.gains(af, [6] * 10)
        same, out = p.play(af, None, 352800, fmt=0x0a, raw=raw)
        expect(r == 1 and out == raw, f'{what}: a gain command changes nothing')
    p = Player({STATE: rec}); p.codec(drv='ad_flac', name='ffflac'); af = p.open(); p.reinit(af, 48000)
    _, y = p.play(af, tone(256, 2, 48000), 48000)
    expect(y != tone(256, 2, 48000), 'another codec (ffflac) is equalized')

    # the chain: integer input asks for float; channels and rates out of range pass
    p = Player(); af = p.open()
    r, din, data = p.reinit(af, 44100, fmt=0x0a, bps=2)
    expect(r == 0 and din[4:] == (FLOAT, 4) and data[4:] == (FLOAT, 4), '16-bit input: AF_FALSE, the chain is asked for float')
    r, _, _ = p.reinit(af, 44100, nch=9)
    expect(r == -2, 'nine channels: AF_ERROR')
    p = Player({STATE: rec}); af = p.open(); p.reinit(af, 768000)
    x = tone(128, 2, 768000)
    _, y = p.play(af, x, 768000)
    expect(y == x, 'a rate past 384 kHz passes untouched')

    # the record: bad magic, short, long, invalid values all read as none (Flat, Auto)
    good = pack_state(1, pack_preset([(1, 0, 1000, 12.0, 1.0)], automatic=2))
    tbad = [('curve 10', pack_state(0, pack_preset([]), b'', 10)), ('curve -1', pack_state(0, pack_preset([]), b'', -1)), ('preamp 13', tenband([0.0] * 10, 13)),
            ('preamp -2', tenband([0.0] * 10, -2)), ('gain 13 dB', tenband([13.0] + [0.0] * 9)), ('custom gain -13 dB', tenband([0.0] * 10, -1, 9, [-13.0] + [0.0] * 9)),
            ('gain NaN', tenband([float('nan')] + [0.0] * 9))]
    for what, rec in tbad + [(w_, r_) for w_, r_ in (('old magic (the previous record)', b'M1PEQ01\0' + good[8:]), ('short', good[:-1]), ('long', good + b'\0'),
                      ('mode 2', good[:8] + struct.pack('<i', 2) + good[12:]), ('gain 30 dB', pack_state(1, pack_preset([(1, 0, 1000, 30.0, 1.0)]))),
                      ('unterminated name', good[:-NAME - 88] + b'x' * NAME + good[-88:]))]:
        p = Player({STATE: rec}); af = p.open(); p.reinit(af, 48000)
        x = tone(256, 2, 48000)
        _, y = p.play(af, x, 48000)
        expect(y == x, f'a {what} record reads as none: Flat, Auto')

    # uninit frees what open allocated
    p = Player(); af = p.open(); data, setup = p.word(af + 20), p.word(af + 16)
    p.call(p.word(af + 8), af)
    expect(('free', data) in p.calls and ('free', setup) in p.calls and p.word(af + 16) == 0 and p.word(af + 20) == 0, 'uninit frees data and setup')


# ---- the parser and the record in demo's payload
def demo_machine():
    m = PODCASTS.PM()
    m.u.reg_write(UC_MIPS_REG_CP0_STATUS, m.u.reg_read(UC_MIPS_REG_CP0_STATUS) | FR)
    return m


def parse(m, text):
    buf = m.alloc(len(text) + 1); m.u.mem_write(buf, text + b'\0')
    out, err = m.alloc(1000), m.alloc(12)
    m.u.mem_write(err, b'\xaa' * 12)
    ok = m.call(PSYMS['peq_parse'], buf, len(text), count=1 << 40, a2=out, a3=err)
    line, reason = m.word(err), m.word(err + 4)
    m.skipped = m.word(err + 8)
    return ok, unpack_preset(bytes(m.u.mem_read(out, 992))), (line, m.read_cstr(reason) if ok == 0 and reason else '')


def parser_tests(ctx):
    expect = ctx.expect
    m = demo_machine()
    ok, p, _ = parse(m, AUTOEQ)
    got = [(e, t, round(f, 6), round(g, 6), round(q, 6)) for e, t, f, g, q in p['bands']]
    expect(ok == 1 and p['count'] == 4 and got == [tuple(map(lambda v: round(v, 6), b)) for b in AUTOEQ_BANDS],
           f'an AutoEQ file: its four ON filters (LSC, PK, HSC, PK), the blank OFF slot skipped ({got})')
    expect(abs(p['preamp'] + 6.2) < 1e-9 and p['automatic'] == 2 and p['bypass'] == 0, 'its Preamp: is kept as given (automatic 2)')
    ok, p, _ = parse(m, b'\xef\xbb\xbfFilter: ON PK Fc 1000 Hz Gain 3 dB Q 1\r\n# comment\n\nFilter 2: ON PK Fc 2,5e3 Hz Gain -1.5 dB Q 0.7\n')
    expect(ok == 1 and p['count'] == 2 and p['automatic'] == 1 and abs(p['bands'][1][2] - 2500) < 1e-9,
           'a BOM, CRLF, comments, an unnumbered filter, a decimal comma with an exponent; no Preamp: means Auto')
    ok, p, _ = parse(m, b'Preamp: -3 dB\nChannel: L\nPreamp: -2 dB\nFilter: ON PK Fc 100 Hz Gain 2 dB Q 1\nChannel: R\nFilter: ON PK Fc 200 Hz Gain 2 dB Q 1\nChannel: all\nFilter: ON PK Fc 300 Hz Gain 2 dB Q 1\n')
    expect(ok == 1 and [b[0] for b in p['bands']] == [2, 3, 1] and abs(p['preamp'] + 3) < 1e-9 and abs(p['balance'] - 2) < 1e-9,
           'Channel: scopes the filters after it; a left preamp becomes the common preamp and a balance')
    ok, p, _ = parse(m, b'Filter: ON LS Fc 100 Hz Gain 6 dB\nFilter: ON HS Fc 8000 Hz Gain -4 dB Q 0.71\n')
    a = 10 ** (6 / 40); q0 = 1 / math.sqrt((a + 1 / a) * (1 / 0.9 - 1) + 2)
    a2 = 10 ** (-4 / 40); f2 = 8000 / 10 ** (4 / 80 * ((1 / 0.71 ** 2 - 2) / (a2 + 1 / a2) + 1))
    expect(ok == 1 and abs(p['bands'][0][4] - q0) < 1e-9 and abs(p['bands'][0][2] - 100) < 1e-9 and abs(p['bands'][1][2] - f2) < 1e-6,
           'APO shelves: no Q is slope 0.9; LS/HS with Q move the corner to the centre')
    for text, line, reason in ((b'Filter: ON PK Fc 1000 Hz Gain 3 dB\n', 1, 'peaking filter requires Q'),
                               (b'\n\nFilter: ON PK Fc 30000 Hz Gain 3 dB Q 1\n', 3, 'range: 20..20000 Hz, -24..24 dB, Q 0.1..10'),
                               (b'Filter: ON XX Fc 1000 Hz Gain 3 dB Q 1\n', 0, 'no usable filter'),
                               (b'Device: foo\nFilter: ON LP Fc 1000 Hz\n', 0, 'no usable filter'),
                               (b'', 0, 'no usable filter'),
                               (b'Preamp: -3 dB\nFilter: OFF PK Fc 1000 Hz Gain 3 dB Q 1\n', 0, 'no usable filter'),
                               (b'Filter: ON PK Fc 1000 Hz Gain 3 dB Q 1 Q\n', 1, 'unsupported filter form'),
                               (b'Filter: ON PK Fc 1000 Hz Gain 3 dB Q 1\nFilter 2: ON PK Fc 1e Hz Gain 3 dB Q 1\n', 2, 'invalid frequency or gain number'),
                               (b'Filter: ON PK Fc 1000 Hz Gain 3 dB Q 1\nFilter: ON PK ' + b'1 ' * 20 + b'\n', 2, 'unsupported filter form'),
                               (b'Filter: ON PK Fc 1000 Hz Gain 3 dB Q 1\nChannel: L C\nPreamp: -1 dB\nPreamp: -70 dB\n', 4, 'preamp outside -60..24 dB or invalid number'),
                               (b'Filter: ON PK Fc 0x10 Hz Gain 3 dB Q 1\n', 1, 'invalid frequency or gain number'),
                               (b'Preamp: -70 dB\n', 1, 'preamp outside -60..24 dB or invalid number'),
                               (b''.join(b'Filter: ON PK Fc 1000 Hz Gain 1 dB Q 1\n' for _ in range(31)), 31, 'more than 30 bands')):
        ok, _, err = parse(m, text)
        expect(ok == 0 and err == (line, reason), f'refused: {reason!r} on line {line} (got {err})')

    # lenient: what the engine has no band for is left out and counted, the rest plays
    lenient = (b'Preamp: -4.5 dB\nInclude: other.txt\nDevice: Speakers\nFilter 1: ON PK Fc 100 Hz Gain 2 dB Q 1\nFilter 2: ON LP Fc 12000 Hz\n'
               b'Filter 3: ON HPQ Fc 20 Hz Q 0.7\nFilter 4: OFF NO Fc 50 Hz\nFilter 5: ON PK Fc 200 Hz Gain -3 dB Q 2\n'
               b'Filter 6: ON LSQ Fc 90 Hz Gain 2 dB Q 0.7\nFilter 7: ON BP Fc 1000 Hz Q 1 Gain 3 dB Extra 1 2 3\n')
    ok, p, _ = parse(m, lenient)
    expect(ok == 1 and p['count'] == 2 and [round(b[2]) for b in p['bands']] == [100, 200] and abs(p['preamp'] + 4.5) < 1e-9 and m.skipped == 6,
           f'unsupported commands (Include, Device) and filter types (LP, HPQ, LSQ, BP) are skipped and counted, the OFF one is not, the supported bands play ({m.skipped} skipped, {ok}, {p["count"]}, {[round(b[2]) for b in p["bands"]]}, {p["preamp"]})')
    ok, p, _ = parse(m, b'Preamp: -3 dB\nChannel: C LFE\nPreamp: -2 dB\nFilter: ON PK Fc 100 Hz Gain 2 dB Q 1\nFilter: OFF PK Fc 100 Hz Gain 2 dB Q 1\nChannel: all\nFilter: ON PK Fc 300 Hz Gain 2 dB Q 1\n')
    expect(ok == 1 and p['count'] == 1 and abs(p['preamp'] + 3) < 1e-9 and p['balance'] == 0 and m.skipped == 2 and p['bands'][0][0] == 1,
           'a channel set with no band (C, LFE): its preamp and ON filters are skipped (not applied to the wrong side), Channel: all scopes again')
    ok, p, _ = parse(m, AUTOEQ)
    expect(ok == 1 and m.skipped == 0, 'a clean file skips nothing')
    ok, p, _ = parse(m, b'Include: ' + b'a ' * 30 + b'\nFilter: ON PK Fc 1000 Hz Gain 3 dB Q 1\n')
    expect(ok == 1 and p['count'] == 1 and m.skipped == 1, 'a command line with more tokens than a filter has is skipped, not refused')

    # the record: saved whole (tmp, fsync, rename), read back; anything else reads as none
    st = m.alloc(1152)
    m.u.mem_write(st, pack_state(1, pack_preset(AUTOEQ_BANDS, -6.2), b'HD 600.txt')[8:])
    r = m.call(PSYMS['peq_state_save'], st, count=1 << 30)
    names = [c[0] for c in m.calls]
    expect(r == 0 and m.fs.get(STATE) == pack_state(1, pack_preset(AUTOEQ_BANDS, -6.2), b'HD 600.txt') and STATE_TMP not in m.fs,
           'peq_state_save: the magic and the record, under the tmp name, then renamed')
    expect(names.index('fsync') < names.index('rename'), 'fsynced before the rename')
    back = m.alloc(1152)
    r = m.call(PSYMS['peq_state_load'], back, count=1 << 30)
    expect(r == 1 and bytes(m.u.mem_read(back, 1152)) == m.fs[STATE][8:], 'peq_state_load reads it back')
    m.fs[STATE] = m.fs[STATE][:-1]
    r = m.call(PSYMS['peq_state_load'], back, count=1 << 30)
    expect(r == 0 and m.word(back) == 0 and unpack_preset(bytes(m.u.mem_read(back + 8, 992)))['count'] == 10, 'a short record reads as none: the 10-Band EQ (mode 0), the default preset')
    expect(struct.unpack_from('<ii20f', bytes(m.u.mem_read(back + 1064, 88))) == (0, -1) + (0.0,) * 20, 'none: curve Flat, preamp Auto, zero gains')
    # the 10-Band EQ's fields: saved whole and read back; the curve table and peq_set_curve
    rec = tenband([1.5, -2, 0, 0, 3, 0, 0, 0, 0, -12], 4, 9, [1.5, -2, 0, 0, 3, 0, 0, 0, 0, -12])
    m.u.mem_write(st, rec[8:])
    expect(m.call(PSYMS['peq_state_save'], st, count=1 << 30) == 0 and m.fs[STATE] == rec, 'peq_state_save: a 10-Band record with Custom gains and a fixed preamp')
    m.u.mem_write(back, b'\xff' * 1152)
    expect(m.call(PSYMS['peq_state_load'], back, count=1 << 30) == 1 and bytes(m.u.mem_read(back, 1152)) == rec[8:], 'peq_state_load reads the 10-Band record back')
    for bad in (tenband([0.0] * 10, 13), tenband([0.0] * 10, -2), tenband([13.0] + [0.0] * 9), pack_state(0, pack_preset([]), b'', 10), pack_state(0, pack_preset([]), b'', -1)):
        m.u.mem_write(st, bad[8:])
        expect(m.call(PSYMS['peq_state_save'], st, count=1 << 30) == 0xffffffff and m.fs[STATE] == rec, 'a record with a curve, preamp or gain out of range is not saved and the file is kept')
    # the genre table: ours equals stock's rows 4..11 in demo (V2.1: reset_user_eq 0x4d8490 copies 12 x 10 floats from 0x74b5bc)
    demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', 'release', 'bin', 'demo'), 'rb').read()
    off = pod.fileoff(demo, 0x74b5bc)
    table = [list(struct.unpack_from('<10f', demo, off + 40 * r)) for r in range(12)]
    expect(table[4:12] == [list(map(float, r_)) for r_ in CURVES[1:9]] and all(not any(table[r]) for r in range(4)), 'the genre gains in the test are stock\'s own table rows 4..11 (rows 0..3 are zero)')
    for c, want in enumerate(CURVES):
        m.u.mem_write(st, rec[8:])
        m.call(PSYMS['peq_set_curve'], st, c, count=1 << 30)
        got = struct.unpack_from('<ii20f', bytes(m.u.mem_read(st + 1064, 88)))
        custom = [1.5, -2, 0, 0, 3, 0, 0, 0, 0, -12]
        expect(got[0] == c and list(got[2:12]) == (custom if c == 9 else want) and list(got[12:]) == custom, f'peq_set_curve({c}): the curve id and its ten gains (Custom: the user\'s), custom[] kept')
    m.u.mem_write(st, rec[8:]); m.call(PSYMS['peq_set_curve'], st, 77, count=1 << 30)
    expect(struct.unpack_from('<i', bytes(m.u.mem_read(st + 1064, 4)))[0] == 0 and not any(struct.unpack_from('<10f', bytes(m.u.mem_read(st + 1072, 40)))), 'an unknown curve id becomes Flat')
    m.u.mem_write(st, struct.pack('<i', 5))
    expect(m.call(PSYMS['peq_state_save'], st, count=1 << 30) == 0xffffffff, 'an invalid record is not saved')
    m.u.mem_write(st, struct.pack('<i', 1)); m.fail.add(('rename', STATE))
    expect(m.call(PSYMS['peq_state_save'], st, count=1 << 30) == 0xffffffff and STATE_TMP not in m.fs, 'a failed rename: -1, the tmp file removed')


# ---- the Equalizer page
ROWS = O['PQ_FIRST'] + O['PQ_ROWS']


def page(files=(), flag=0, state=None, card=True):
    m = demo_machine()
    m.card_mounted = card
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag]))
    m.setword(pod.DATA['EQ_MODE'][0], 4)
    m.folder(EQ_DIR)
    for name, data in files: m.put(f'{EQ_DIR}/{name}', data)
    if state is not None: m.fs[STATE] = state
    for i in range(ROWS):
        for base in ('pod_row', 'pod_label', 'pod_check'):
            if base != 'pod_check' or i: m.widget(f'{base}{i}')
        if 0 < i < ROWS - 1: m.lookups[(m.widgets[f'pod_row{i}'], 'pod_hair')] = m.alloc(0x80)   # a hairline on every row but the card's last (the asset's)
    for n in ('pod_switch0', 'pod_scrollview', 'pod_note0_t', 'pod_note1', 'pod_gap0', 'pod_value1', f'pod_row{ROWS}', f'pod_value{ROWS}', f'pod_row{ROWS + 1}', f'pod_value{ROWS + 1}'): m.widget(n)
    m.lookups[(m.widgets['pod_note1'], 'pod_note1_t')] = m.alloc(0x80)
    m.call(PSYMS['peq_opened'], m.window, count=1 << 30)
    return m


def shown(m): return [i for i in range(O['PQ_FIRST'], ROWS) if m.props.get((m.widgets[f'pod_row{i}'], 'visible'))]
def labels(m): return {m.widgets[f'pod_label{i}']: i for i in range(ROWS)}
def texts(m): return [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] in labels(m)]
def marks(m): return [i for i in range(1, ROWS) if m.props.get((m.widgets[f'pod_check{i}'], 'visible'))]
def piece(m, i, state='normal'): return m.props.get((m.widgets[f'pod_row{i}'], f'style:{state}:bg_image'))
def hair(m, i):
    w = m.lookups.get((m.widgets[f'pod_row{i}'], 'pod_hair'))
    return None if w is None else m.props.get((w, 'visible'))
def switch(m): return [c[2] for c in m.calls if c[0] == 'image_base_set_image' and c[1] == m.widgets['pod_switch0']][-1:]
def tap(m, i):
    fn, ctx = m.bound[(m.widgets[f'pod_row{i}'], O['EVT_CLICK'])]
    return m.call(fn, a0=ctx, count=1 << 30)


def page_tests(ctx):
    expect = ctx.expect
    files = [('Sennheiser HD 600.txt', AUTOEQ), ('akg k371.TXT', b'Filter: ON PK Fc 3000 Hz Gain -2 dB Q 2\n'), ('notes.md', b'x'), ('.hidden.txt', AUTOEQ),
             ('broken.txt', b'Filter: ON PK Fc 1000 Hz Gain 3 dB\n')]
    m = page(files)
    expect(texts(m) == ['akg k371', 'broken', 'Sennheiser HD 600'] and shown(m) == [2, 3, 4],
           f'the .txt files of /mnt/mmc/EQ, any case, sorted, no dot files, shown without the extension ({texts(m)})')
    expect(m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == ST.layout(pod_pages.peq_items(3))[1], 'the list is as tall as the layouter makes the column (the model\'s)')
    expect(marks(m) == [1] and switch(m) == ['sset_off'], 'no record: the check is on 10-Band EQ; the switch shows stock\'s flag (off)')
    expect(ptext(m, 'pod_value1') == ['Flat'] and ptext(m, f'pod_value{ROWS}') == ['Flat'], 'no record: the picker row and the bottom card\'s 10-Band EQ link show the curve name, Flat')
    for curve, name in ((2, 'Rock'), (9, 'Custom')):
        m2 = page(files, state=pack_state(0, pack_preset([]), b'', curve, -1, CURVES[curve]))
        expect(ptext(m2, 'pod_value1') == [name] and ptext(m2, f'pod_value{ROWS}') == [name], f'a {name} record: its name in grey on the picker row and the link row')
    m2 = page(files, flag=1, state=pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt', 2, -1, CURVES[2]))
    expect(marks(m2) == [4] and ptext(m2, 'pod_value1') == ['Rock'], 'a preset plays: its row is checked, the 10-Band row still names its curve (Rock) without a check')
    expect(m.props.get((m.widgets['pod_note1'], 'visible')) == 0 and m.props.get((m.widgets['pod_gap0'], 'visible')) == 1, 'no hint when there are presets: the gap before the bottom card shows instead')
    expect(ptext(m, f'pod_value{ROWS + 1}') == ['3'], f'the Presets row\'s grey count is the number of .txt files ({ptext(m, f"pod_value{ROWS + 1}")})')
    expect(not any(c[0] in ('widget_move', 'widget_restack') for c in m.calls), 'the rows are not moved: the stock layouter stacks the visible ones in order')

    # a preset: parsed, saved, stock's switch turned on as its own handler does, the mode's gains sent
    m.calls = []
    tap(m, 4)
    rec = m.fs.get(STATE, b'')
    expect(len(rec) == STATE_SIZE and struct.unpack_from('<i', rec, 8)[0] == 1 and NAME_OF(rec) == b'Sennheiser HD 600.txt', 'the record: PEQ_FILE and the file\'s name')
    p = unpack_preset(rec[16:16 + 992])
    expect(p['count'] == 4 and abs(p['preamp'] + 6.2) < 1e-9, 'the record holds the parsed preset')
    seq = [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
    expect(seq == [('write_int_config', 1, 'PLAYSET', 'EQFLAG'), ('set_equalizer_value', 4, 1)], f'the switch was off: on, saved, then mcl-seteq with the mode ({seq})')
    expect(marks(m) == [4] and switch(m) == ['sset_on'], 'the preset is marked, the switch on')
    m.calls = []
    tap(m, 2)
    seq = [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
    expect(seq == [('set_equalizer_value', 4, 1)] and marks(m) == [2], 'with the switch on: only the gains sent again, which the player rereads the record on')
    m.calls = []
    tap(m, 3)
    toasts = [c[1] for c in m.calls if c[0] == 'toast']
    expect(toasts == ['Cannot read this preset'] and not [c for c in m.calls if c[0] in ('rename', 'image_base_set_image')], 'a file the parser refuses: the message box, nothing saved, the marks as they were')
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 1 and NAME_OF(m.fs[STATE]) == b'akg k371.TXT' and not [c for c in m.calls if c[0] == 'set_equalizer_value'],
           'the record still holds the last good preset')
    m.calls = []
    tap(m, 1)
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 0 and marks(m) == [1] and ('set_equalizer_value', 4, 1) in m.calls, '10-Band EQ: mode 0 saved, the gains sent')
    m.calls = []
    tap(m, 0)
    expect(m.u.mem_read(pod.DATA['EQ_FLAG'][0], 1)[0] == 0 and [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
           == [('write_int_config', 0, 'PLAYSET', 'EQFLAG'), ('set_equalizer_value', 4, 0)] and switch(m) == ['sset_off'],
           'the switch row is stock\'s switch: flag off, saved, and set_equalizer_value closes the equalizer')

    # the Presets card's row opens the Presets page (patch/peqlib.c) and changes nothing else; the Download from AutoEq row is on that page (presets_page_tests)
    m.calls = []
    fn, c = m.bound[(m.widgets[f'pod_row{ROWS + 1}'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(('window_open', 'm1plus_peqlib') in m.calls and ('window_open', 'm1plus_autoeq') not in m.calls and not [x for x in m.calls if x[0] in ('rename', 'set_equalizer_value')],
           'the Presets row opens the Presets page\'s window and changes nothing else')

    # the 10-Band EQ link row opens the editor (patch/tenband.c; its own tests are tenband_drag_tests to tenband_preamp_tests) and changes nothing
    m.calls = []; before = dict(m.fs)
    expect((m.widgets[f'pod_row{ROWS}'], O['EVT_CLICK']) in m.bound, 'the bottom card\'s 10-Band EQ link row is bound')
    tap(m, ROWS)
    expect(('window_open', 'm1plus_tenband') in m.calls and not [c for c in m.calls if c[0] in ('rename', 'set_equalizer_value', 'write_int_config', 'toast')] and m.fs == before, 'the 10-Band EQ link row opens the editor\'s window and changes nothing')

    # a preset row has no chevron zone: a tap at any x selects the preset and opens no page
    m = page(files)
    register_peqpage(m)
    def tap_at(m, i, x):
        e = m.alloc(0x40); m.setword(e + O['PE_X'], x)
        fn, ctx = m.bound[(m.widgets[f'pod_row{i}'], O['EVT_CLICK'])]
        return m.call(fn, a0=ctx, a1=e, count=1 << 40)
    for x in (0, 100, 247, 248, 266, 300, 309):
        m.fs.pop(STATE, None); m.calls = []; tap_at(m, 4, x)
        expect(len(m.fs.get(STATE, b'')) == STATE_SIZE and not [c for c in m.calls if c[0] == 'window_open'], f'a tap at x {x} on a preset row selects it, no page opens')
    m.calls = []
    tap(m, 4)
    expect(len(m.fs.get(STATE, b'')) == STATE_SIZE and ('window_open', 'm1plus_peqpage') not in m.calls, 'a click that carries no pointer event is a tap on the body')
    m.calls = []; tap_at(m, 3, 280)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Cannot read this preset'] and ('window_open', 'm1plus_peqpage') not in m.calls, 'a preset that does not parse: the message box, no page')
    m.fs.pop(STATE, None); m.calls = []; tap_at(m, 1, 300)
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 0 and ('window_open', 'm1plus_peqpage') not in m.calls, '10-Band EQ: any x selects it')

    # a record from before: its file is marked; a failed save keeps it
    m = page(files, flag=1, state=pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt'))
    expect(marks(m) == [4] and switch(m) == ['sset_on'], 'the saved preset\'s row is marked')
    m.fail.add(('rename', STATE)); m.calls = []
    tap(m, 2)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Not saved'] and marks(m) == [4] and not [c for c in m.calls if c[0] == 'set_equalizer_value'],
           'a failed save: the message box, the old record and mark stay, nothing sent')
    m = page(files, flag=1, state=pack_state(1, pack_preset(AUTOEQ_BANDS), b'gone.txt'))
    expect(marks(m) == [], 'a preset no longer on the card: no row is marked (the record still plays it)')

    # no presets, the card out, too many files
    for what, kw in (('an empty folder', {}), ('the card out', {'files': files, 'card': False})):
        m = page(**kw)
        expect(shown(m) == [] and m.props.get((m.widgets['pod_note1'], 'visible')) == 1 and piece(m, 1) == 'pod_cd_single' and hair(m, 1) == 0 and marks(m) == [1]
               and m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == ST.layout(pod_pages.peq_items(0))[1],
               f'{what}: no preset rows, 10-Band EQ a single card with no hairline, the hint under it, the column as the model says')
        expect(m.props.get((m.widgets['pod_gap0'], 'visible')) == 0, f'{what}: no gap between the hint and the bottom card (the note is the space)')
    # the picker card's pieces: the card is 10-Band EQ and the shown rows; its first row is a top piece, its last a bottom piece with no hairline (the lit twin when pressed)
    for k in (1, 2, 3, O['PQ_ROWS']):
        m = page([(f'p{i:02d}.txt', AUTOEQ) for i in range(k)])
        want = ST.peq_pieces(k)
        got = [piece(m, i).removeprefix('pod_cd_') for i in range(1, 2 + k)]
        expect(got == want and want[0] == 'top' and want[-1] == 'bot' and all(w == 'mid' for w in want[1:-1]), f'{k} presets: the card is {want} ({got})')
        expect(all(piece(m, i, 'pressed') == piece(m, i) + '_down' and all(piece(m, i, s) == piece(m, i) for s in ('over', 'focused', 'disable')) for i in range(1, 2 + k)),
               f'{k} presets: every state has the row\'s piece, the pressed one its lit twin')
        expect([hair(m, i) for i in range(1, 2 + k)] == [1] * k + [0] if k < O['PQ_ROWS'] else [hair(m, i) for i in range(1, 2 + k)] == [1] * k + [None],
               f'{k} presets: a hairline under every row of the card but the last')
        expect(m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == ST.layout(pod_pages.peq_items(k))[1] and m.props.get((m.widgets['pod_note1'], 'visible')) == 0, f'{k} presets: the column\'s height, no hint')
    # a preset added while the page is away: the card is re-pieced when it is back (the last row was a bottom piece with no hairline, now a middle one with)
    m = page(files[:1])
    expect(piece(m, 2) == 'pod_cd_bot' and hair(m, 2) == 0, 'one preset: its row closes the card')
    m.put(f'{EQ_DIR}/zz.txt', AUTOEQ)
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(piece(m, 2) == 'pod_cd_mid' and hair(m, 2) == 1 and piece(m, 3) == 'pod_cd_bot' and hair(m, 3) == 0 and shown(m) == [2, 3], 'a second preset: the first row is a middle piece with its hairline, the new row closes the card')
    m = page(many := [(f'p{i:02d}.txt', AUTOEQ) for i in range(70, 0, -1)])
    expect(texts(m) == [f'p{i:02d}' for i in range(1, O['PQ_ROWS'] + 1)] and len(shown(m)) == O['PQ_ROWS'], f'{len(many)} files: the first {O["PQ_ROWS"]} by name')

    # back in front: the folder read again
    m = page(files[:1])
    m.put(f'{EQ_DIR}/zz.txt', AUTOEQ); m.calls = []
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(texts(m) == ['Sennheiser HD 600', 'zz'], 'back in front: a file added since shows')
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30); m.calls = []
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(not [x for x in m.calls if x[0] == 'opendir'], 'after the destroy the page state is gone: nothing runs')

    # Settings > Playback > EQ's value (patch/m1plus.c value_text): the playing preset's name, or the 10-Band EQ's curve key (Flat with no record)
    for what, rec, want in (('a preset', pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt'), 'Sennheiser HD 600'),
                            ('10-Band EQ, Flat', pack_state(0, pack_preset([])), 'Flat'), ('10-Band EQ, Jazz', pack_state(0, pack_preset([]), b'', 8), 'Jazz'),
                            ('10-Band EQ, Custom', pack_state(0, pack_preset([]), b'', 9), 'Custom'), ('no record', None, 'Flat')):
        m = demo_machine()
        if rec: m.fs[STATE] = rec
        buf = m.alloc(64)
        r = m.call(PSYMS['peq_playing_name'], buf, 64, count=1 << 30)
        expect((m.read_cstr(buf) if r else None) == want, f'peq_playing_name with {what}: {want!r}')

    # not our asset: nothing bound
    m = demo_machine()
    for n in ('pod_row0', 'pod_switch0'): m.widget(n)
    m.call(PSYMS['peq_opened'], m.window, count=1 << 30)
    expect(not [b for b in m.bound if b[1] == O['EVT_CLICK']], 'a page without the rows binds nothing')


# ---- demo writes, hciplayer plays
def cross_tests(ctx):
    expect = ctx.expect
    m = page([('HD 600.txt', AUTOEQ)])
    tap(m, 2)
    p = Player({STATE: m.fs[STATE]}); af = p.open(); p.reinit(af, 44100)
    x = tone(1024, 2, 44100)
    _, y = p.play(af, x, 44100)
    expect(near(y, model(AUTOEQ_BANDS, 44100, 2, x, 10 ** (-6.2 / 20))), 'the record the page writes from an AutoEQ file plays as the model of that file')
    tb = tenband([2.0] * 10, 3, 9, [2.0] * 10)   # a 10-Band record (Custom, all +2 dB, -3 dB preamp): a file selected over it keeps its fields, a tap on the 10-Band EQ row only switches the mode back
    m = page([('HD 600.txt', AUTOEQ)], state=tb)
    tap(m, 2)
    expect(m.fs[STATE][8:12] == struct.pack('<i', 1) and m.fs[STATE][-88:] == tb[-88:], 'selecting a file keeps the 10-Band EQ\'s curve, gains and preamp in the record')
    tap(m, 1)
    expect(m.fs[STATE][8:12] == struct.pack('<i', 0) and m.fs[STATE][-88:] == tb[-88:], 'a tap on the 10-Band EQ row keeps the record\'s curve, gains and preamp')
    p = Player({STATE: m.fs[STATE]}); p.stock_gains([5] * 10); af = p.open(); p.reinit(af, 44100)
    _, y = p.play(af, x, 44100)
    expect(near(y, model([(1, 0, f, 2.0, 1.41) for f in GRAPHIC_F], 44100, 2, x, 10 ** (-3 / 20))), 'after 10-Band EQ the player plays the record\'s gains and preamp (not stock\'s)')


def asset_tests(ctx):
    """ui/m1plus_peq.bin: stock rows, the payload's names, hidden preset rows that take no touch, insensitive marks, and the texts fitting in every language."""
    import awtk_style
    from awtk_text import Ttf, StbText
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    tree = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.PEQ_PAGE.key + '.bin'), 'rb').read())
    rows = [tree.find(f'pod_row{i}') for i in range(ROWS)]
    tbr, lib = tree.find(f'pod_row{ROWS}'), tree.find(f'pod_row{ROWS + 1}')
    expect(all(r is not None and r.type == 'list_item' and r.get('style') == 'list_item_style' for r in rows) and tree.find(f'pod_row{ROWS + 2}') is None
           and lib is not None and lib.type == 'list_item' and lib.get('style') == 'list_item_style' and tbr is not None and tbr.type == 'list_item' and tbr.get('style') == 'list_item_style',
           f'{ROWS} stock list_item rows and the two link rows (10-Band EQ, Presets) after them, no more')
    for r_, what, label_, piece_ in ((tbr, 'Edit 10-Band EQ', ROWS, 'top'), (lib, 'Presets', ROWS + 1, 'bot')):
        kids = {w_.name: w_ for w_ in r_.walk()}
        expect(r_.get('visible') != 'false' and r_.get('sensitive') != 'false' and pod_i18n.shown_english(tree.find(f'pod_label{label_}')) == what
               and 'pod_chevron' in kids and f'pod_value{label_}' in kids and 'pod_icon' not in kids and (r_.get('style:normal:bg_image'), r_.get('style:pressed:bg_image')) == (f'pod_cd_{piece_}', f'pod_cd_{piece_}_down'),
               f'the {what} row is a link of the bottom card ({piece_} piece) with its label, a grey value and a chevron, no glyph, shown and tappable')
        expect(tree.find(f'pod_value{label_}').get('text') in (None, '') and tree.find(f'pod_value{label_}').get('sensitive') == 'false', f'the {what} value starts empty (the payload sets it) and takes no touch')
    gap1 = tree.find('pod_gap0')
    dsd = tree.find('pod_note2')   # the grey DSD note at the page's end, under the bottom card (always shown; note 0 is the output line, note 1 the hint)
    outl = tree.find('pod_note0')
    expect(outl is not None and outl.get('visible') != 'false' and tree.find('pod_gap1') is None and pod_i18n.shown_english(tree.find('pod_note0_t')) == 'For Headphones' and outl.y >= tree.find('pod_row0').y + ST.ROW_H
           and outl.y + outl.h <= rows[1].y, 'the grey output line "For Headphones" sits between the switch card and the picker card, shown')
    expect(gap1 is not None and gap1.get('visible') != 'false' and ST.item_h(pod_pages.GAP) == gap1.h and dsd is not None and dsd.get('visible') != 'false' and dsd.get('sensitive') == 'false'
           and pod_i18n.shown_english(tree.find('pod_note2_t')) == 'EQ is not applied to DSD.' and dsd.y >= lib.y + lib.h and tree.find('pod_note3') is None, 'the gap before the bottom card is there; the DSD note ends the page, shown')
    expect(all(r.get('visible') == 'false' and r.get('sensitive') == 'false' for r in rows[O['PQ_FIRST']:ROWS]) and all(r.get('visible') != 'false' for r in rows[:O['PQ_FIRST']]),
           'the preset rows start hidden and insensitive (a hidden row still takes touches); the switch and 10-Band EQ rows show')
    chev_ok = [[c for c in rows[i].children if c.name == 'pod_chevron'] for i in range(ROWS)]
    expect(all(not c_ for c_ in chev_ok), 'no row of the picker (the switch, 10-Band EQ, a preset) has a chevron: a preset row only selects')
    pchecks = [tree.find(f'pod_check{i}') for i in range(O['PQ_FIRST'], ROWS)]
    gcheck = tree.find('pod_check1')
    expect((gcheck.x, gcheck.y) == ST.accessory('check')[:2] and all((c_.x, c_.y, c_.w, c_.h) == ST.accessory('check') for c_ in pchecks),
           'every check, a preset\'s too, sits at the right edge where the chevron used to be')
    checks = [tree.find(f'pod_check{i}') for i in range(1, ROWS)]
    expect(tree.find('pod_check0') is None and all(c_ is not None and c_.get('sensitive') == 'false' and c_.get('visible') == 'false' for c_ in checks),
           'every row but the switch has the picker check, hidden and insensitive (the row takes the tap)')
    sw = tree.find('pod_switch0')
    expect(sw is not None and sw.get('sensitive') == 'false' and sw.get('image') == 'sset_off', 'the switch image is insensitive')
    labs = [tree.find(f'pod_label{i}') for i in range(ROWS)]
    expect(pod_i18n.shown_english(labs[0]) == 'Equalizer' and pod_i18n.shown_english(labs[1]) == '10-Band EQ'
           and all(lab_.get('text') == '' and lab_.get('tr_text') is None for lab_ in labs[O['PQ_FIRST']:]), 'the two fixed rows are translated; the preset rows carry no text')
    expect(all(lab_.x + lab_.w <= c_.x for lab_, c_ in zip(labs[1:], checks)) and labs[0].x + labs[0].w <= sw.x, 'no label runs under its check or the switch')
    cv = tree.find('pod_value1')
    expect(cv is not None and cv.get('sensitive') == 'false' and cv.get('text') in (None, '') and (cv.x, cv.w) == ST.curve_box() and labs[1].x + labs[1].w + ST.VALUE_LABEL_GAP <= cv.x and cv.x + cv.w <= checks[0].x
           and cv.get('visible') != 'false' and not [i for i in range(2, ROWS) if tree.find(f'pod_value{i}') is not None], 'the 10-Band EQ picker row has a grey curve name (a box of its own) between its label and the check; no other picker row has one')
    note, hint = tree.find('pod_note1'), tree.find('pod_note1_t')
    expect(note is not None and note.get('visible') == 'false' and note.get('sensitive') == 'false' and hint is not None and hint.type == 'label' and hint.get('sensitive') == 'false'
           and note.h == ST.item_h(pod_pages.PEQ_HINT) and hint.h == ST.NOTE_LABEL_H + 2 * ST.WRAP_LINE, 'the hint is a note starting hidden and insensitive: a wrapping label three lines tall')
    expect([ (r.get('style:normal:bg_image'), r.get('style:pressed:bg_image')) for r in (rows[0], rows[1], rows[2], rows[-1])] ==
           [('pod_cd_single', 'pod_cd_single_down'), ('pod_cd_top', 'pod_cd_top_down'), ('pod_cd_mid', 'pod_cd_mid_down'), ('pod_cd_bot', 'pod_cd_bot_down')],
           'the asset\'s pieces are those of the full card (the payload sets the shown rows\' own)')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    th = awtk_style.parse(open(os.path.join(raw, 'styles', 'default.bin'), 'rb').read())
    row_px = th.find('hscroll_label', 'srlabel_leftwhite21_style', 'normal')[0].get('font_size')
    width = lambda text, px: StbText(font, px).layout(text)[1]
    over = []
    for loc in pod_i18n.LOCALES:
        for i in (0, 1):
            t = pod_i18n.TEXT[pod_i18n.shown_english(labs[i])][loc]
            if width(t, row_px) > labs[i].w: over.append((loc, t, width(t, row_px), labs[i].w))
        t = pod_i18n.TEXT[pod_pages.PEQ_HINT.text][loc]
        lines, line = 1, ''   # greedy wrap at the label's width (the text starts 2 px in): by words, by characters in a text with no spaces
        for tok in re.findall(r'\S+\s*', t) if ' ' in t else list(t):
            if line and width(line + tok.rstrip(), ST.NOTE_PX) > hint.w - 4: lines, line = lines + 1, tok
            else: line += tok
        if lines > 3: over.append((loc, 'hint', lines, width(t, ST.NOTE_PX)))
        for key, row_i in (('Edit 10-Band EQ', ROWS), ('Presets', ROWS + 1)):
            t = pod_i18n.TEXT[key][loc]
            if width(t, row_px) > tree.find(f'pod_label{row_i}').w: over.append((loc, t, width(t, row_px), tree.find(f'pod_label{row_i}').w))
        for key in ('Flat', 'Pop', 'Rock', 'Dance', 'Blues', 'Metal', 'Vocal', 'Classical', 'Jazz', 'Custom'):   # the grey curve name: in its picker box, and in the link row's value box
            t = pod_i18n.TEXT[key][loc]
            if width(t, ST.VALUE_PX) > min(ST.curve_box()[1], ST.value_box()[1]): over.append((loc, t, width(t, ST.VALUE_PX), ST.curve_box()[1]))
    expect(not over, f'Equalizer, 10-Band EQ, the hint, the link rows and the curve names fit in all 13 languages ({over[:3]})')

# ---- the preset page (patch/peqpage.c, tools/peq_graph.py)
PLONG = b"""Device: Sennheiser HD 800
Preamp: -3.5 dB
Filter 1: ON LSC Fc 80 Hz Gain 14.0 dB Q 0.70
Filter 2: ON PK Fc 250 Hz Gain -3.5 dB Q 1.2
Channel: L
Filter 3: ON PK Fc 1800 Hz Gain 6 dB Q 0.9
Channel: R
Filter 4: ON PK Fc 1800 Hz Gain -2 dB Q 0.9
Channel: all
Filter 5: ON HSC Fc 8000 Hz Gain -6.5 dB Q 0.7
Filter 6: ON PK Fc 12500 Hz Gain 3.25 dB Q 1.41
Filter 7: ON LP Fc 20000 Hz
Filter 8: OFF PK Fc 100 Hz Gain 3 dB Q 1
"""
PBANDS = 'pod_graph pod_gr_top pod_gr_bot pod_note0 pod_gap1 label_title'.split()


def register_peqpage(m, drop=()):
    """The preset page's widgets by name, as the machine's window has them once m1plus.c open_page has opened it."""
    for n in PBANDS:
        if n not in drop: m.widget(n)
    m.lookups[(m.widgets['pod_note0'], 'pod_note0_t')] = m.alloc(0x80)
    m.setword(m.widgets['label_title'] + O['W_W'], 200)   # the navbar title's room: az_fit cuts a longer name
    for i in range(O['GR_BANDS'] + 1):
        for base in ('pod_row', 'pod_value'): m.widget(f'{base}{i}')
        if i:
            for base in ('pod_label', 'pod_sub'): m.widget(f'{base}{i}')
        if i < O['GR_BANDS']: m.lookups[(m.widgets[f'pod_row{i}'], 'pod_hair')] = m.alloc(0x80)   # (the asset's last band row has none, nor has the preamp row's card: only a hairline per band row but the last)
    del m.lookups[(m.widgets['pod_row0'], 'pod_hair')]
    if 'pod_row31' not in drop:
        for k in (1, 2): m.widget(f'pod_row{O["GR_BANDS"] + k}')   # the Rename / Delete Preset card (31 Delete, 32 Rename)


def ppage(files, name, bitmap_ok=True, drop=(), count=False):
    """The Equalizer page's chevron zone as the payload runs it: peqpage_show parses the file and (through m1plus.c open_page, the real one) opens the page, whose widgets are registered here by name."""
    m = demo_machine()
    m.card_mounted = True
    m.bitmap_ok = bitmap_ok
    m.folder(EQ_DIR)
    for fn, data in files: m.put(f'{EQ_DIR}/{fn}', data)
    register_peqpage(m, drop)
    m.name = name
    if count: m.count()
    m.shown = m.call(PSYMS['peqpage_show'], m.cstr(name), count=1 << 40)
    return m


def u8(t): return t.encode('latin-1').decode('utf-8')   # (the harness reads C strings as latin-1)
def ptexts(m, base, i): return [u8(c[2]) for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[f'{base}{i}']]
def ptext(m, name): return [u8(c[2]) for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[name]]
def pbitmap(m):
    (b, (data, w, h)), = m.bitmaps.items()
    px = struct.unpack(f'<{w * h}I', m.u.mem_read(data, w * h * 4))
    return b, w, h, px


def preset_page_tests(ctx):
    expect = ctx.expect
    files = [('Long.txt', PLONG), ('Sennheiser HD 600.txt', AUTOEQ), ('broken.txt', b'Filter: ON PK Fc 1000 Hz Gain 3 dB\n')]
    m0 = demo_machine()
    ok, preset, _ = parse(m0, PLONG)
    bands = preset['bands']
    expect(ok == 1 and m0.skipped == 2 and [b[0] for b in bands] == [1, 1, 2, 3, 1, 1, 0] and preset['automatic'] == 2 and abs(preset['preamp'] + 3.5) < 1e-9, f'the test preset parses as expected: six playing bands (L and R ones) and an OFF filter the record keeps, two lines skipped ({m0.skipped})')
    # the Python models agree: the page's (tools/peq_graph.py) and this file's RBJ cascade
    cs = compiled(bands, 48000)
    worst = max(abs(G.left_db(bands, f) - 10 * math.log10(response(cs, 48000, f)[0])) for f in (20, 100, 1000, 1800, 8000, 12500, 20000))
    expect(worst < 1e-9, f'peq_graph.left_db is the cascade\'s left response ({worst:.2e} dB)')

    m = ppage(files, 'Long.txt', count=True)
    expect(m.shown == 1 and ('window_open', 'm1plus_peqpage') in m.calls, 'peqpage_show on a preset: the page opens')
    expect(m.icount < 8_000_000, f'opening the page (parse, curve, bitmap) costs {m.icount:,} payload instructions, once')
    rows = G.band_rows(bands)
    expect(rows == [('80 Hz', '+14.0 dB', 'Low shelf · Q 0.7'), ('250 Hz', '−3.5 dB', 'Peak · Q 1.2'), ('1.8 kHz', '+6.0 dB', 'Peak · Q 0.9 · L'), ('1.8 kHz', '−2.0 dB', 'Peak · Q 0.9 · R'),
                    ('8 kHz', '−6.5 dB', 'High shelf · Q 0.7'), ('12.5 kHz', '+3.3 dB', 'Peak · Q 1.41')], f'the model\'s band rows (the formats of the page): {rows}')
    got = [(ptexts(m, 'pod_label', i), ptexts(m, 'pod_value', i), ptexts(m, 'pod_sub', i)) for i in range(1, 7)]
    expect(got == [([a], [b], [c]) for a, b, c in rows], f'a band row per band that plays (the OFF filter the parser kept has none), in the file\'s order: frequency, gain, grey line (shelf, peak, one side: L / R) ({got})')
    expect(ptexts(m, 'pod_value', 0) == ['−3.5 dB'], f'the preamp row: the file\'s Preamp ({ptexts(m, "pod_value", 0)})')
    expect(ptext(m, 'label_title') == ['Long'], f'the navbar title is the preset\'s name without .txt ({ptext(m, "label_title")})')
    vis = {i: m.props.get((m.widgets[f'pod_row{i}'], 'visible')) for i in range(1, O['GR_BANDS'] + 1)}
    sens = {c[1]: c[2] for c in m.calls if c[0] == 'widget_set_sensitive'}
    expect([i for i, v in vis.items() if v] == [1, 2, 3, 4, 5, 6] and all(sens.get(m.widgets[f'pod_row{i}']) == 1 for i in range(1, 7)) and not [i for i in range(7, 31) if m.widgets[f'pod_row{i}'] in sens]
           and m.widgets['pod_row0'] not in sens, 'six rows shown and made sensitive (a tap opens the band page), the others never touched, the preamp row untouched (no touch)')
    pcs = [piece(m, i) for i in range(1, 7)]
    expect([p_.removeprefix('pod_cd_') for p_ in pcs] == ST.peqp_pieces(6) == ['top', 'mid', 'mid', 'mid', 'mid', 'bot'], f'the band card is top, middle.., bottom ({pcs})')
    expect(all(piece(m, i, 'pressed') == piece(m, i) + '_down' for i in range(1, 7)) and [hair(m, i) for i in range(1, 7)] == [1, 1, 1, 1, 1, 0], 'every state has the row\'s piece; a hairline under every row but the last')
    expect(ptext(m, 'pod_gr_top') == ['+18'] and ptext(m, 'pod_gr_bot') == ['−18'], f'a +14 dB boost: the scale goes to +18 / −18 ({ptext(m, "pod_gr_top")})')
    nt = m.lookups[(m.widgets['pod_note0'], 'pod_note0_t')]
    note = [c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == nt]
    expect(note == ['2 lines not supported were skipped.'] and m.props.get((m.widgets['pod_note0'], 'visible')) == 1
           and m.props.get((m.widgets['pod_gap1'], 'visible')) == 0, f'the skipped lines: the note shows in place of the gap before the Rename / Delete card ({note})')

    # the graph: one bitmap, the card baked in, against the model pixel by pixel; the curve against the response
    expect([c for c in m.calls if c[0] == 'bitmap_create_ex'] == [('bitmap_create_ex', 300, 170)] and len(m.bitmaps) == 1, 'one 300 x 170 bitmap')
    b, w, h, px = pbitmap(m)
    db, rng = G.curve(bands)
    model_px = G.render(db, rng)
    off = [(x, y) for y in range(h) for x in range(w) if abs((px[y * w + x] >> 24) - model_px[y][x][0]) > 1 or abs((px[y * w + x] & 255) - model_px[y][x][1]) > 2]
    expect(rng == 18 and not off, f'the bitmap is the model\'s pixel for pixel (range {rng}; {len(off)} differ: {off[:3]})')
    expect(px[0] >> 24 == 0 and px[299] >> 24 == 0 and px[169 * 300] >> 24 == 0 and px[170 * 300 - 1] >> 24 == 0 and px[150] >> 24 == 255 and px[85 * 300] >> 24 == 255, 'the card\'s four corners are cut in the alpha, its edges opaque')
    cols = []
    for c in range(G.PW):
        col = [(px[y * w + G.PX0 + c] & 255, y) for y in range(G.PY0, G.PY0 + G.PH)]
        cols.append(max(col)[1] + 0.5)
    want = [G.PY0 + G.PH // 2 + 0.5 - v * (G.PH / 2) / rng for v in db]
    bad = [c for c in range(G.PW) if abs(cols[c] - min(max(want[c], G.PY0 + 0.5), G.PY0 + G.PH - 0.5)) > 1.2 + abs(want[min(c + 1, G.PW - 1)] - want[max(c - 1, 0)]) / 2]
    expect(not bad, f'the brightest pixel of each of the {G.PW} columns is on the curve peq_response gives (within a pixel and the slope; off at {bad[:5]})')
    # the grid: the 0 dB line and the three frequency lines, where nothing but the fill could be
    zero = px[(G.PY0 + G.PH // 2) * w + G.PX0 + 3] & 255
    expect(zero >= G.GREY_ZERO and (px[(G.PY0 + 1) * w + G.PX0 + G.GRID_X[2]] & 255) == G.GREY_GRID and (px[G.PY0 * w + G.PX0 + 3] & 255) == G.GREY_GRID, f'the grid: the 0 dB line ({zero}), the lines at 100 Hz / 1 kHz / 10 kHz and the scale\'s ends')
    # painted by one blit in the graph view's EVT_BEFORE_PAINT, nothing more
    fn, c = m.bound[(m.widgets['pod_graph'], O['EVT_BEFORE_PAINT'])]
    canvas, ev = m.alloc(0x100), m.alloc(0x40)
    m.setword(ev + O['EVENT_PAINT_CANVAS'], canvas); m.blits.clear()
    m.call(fn, a0=c, a1=ev, count=1 << 30)
    expect(m.blits == [(b, (0, 0, 300, 170), (10, 0, 300, 170))] and m.names() == ['canvas_draw_image'], f'paint: one canvas_draw_image of the whole bitmap at the card\'s x ({m.blits}, {m.names()})')
    m.call(fn, a0=c, a1=0, count=1 << 30)
    expect(m.names() == [], 'an event without a canvas paints nothing')
    expect(not [x for x in m.bound if x[1] in (O['EVT_SCROLL'],)] and not m.timers, 'no timer, no scroll handler')
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(('bitmap_destroy', b) in m.calls and not m.bitmaps, 'destroy: the bitmap goes')
    fn, c = m.bound[(m.widgets['pod_graph'], O['EVT_BEFORE_PAINT'])]
    m.blits.clear(); m.call(fn, a0=c, a1=ev, count=1 << 30)
    expect(not m.blits, 'a paint after the destroy draws nothing')

    # a short preset with Auto preamp: the cut the player applies at 48 kHz; the scale stays +12 / −12; no note
    m = ppage(files, 'Sennheiser HD 600.txt')
    ok, p2, _ = parse(m0, AUTOEQ)
    expect(p2['automatic'] == 2, 'AUTOEQ has a Preamp line')
    expect(ptexts(m, 'pod_value', 0) == ['−6.2 dB'] and ptext(m, 'pod_gr_top') == ['+12'] and ptext(m, 'pod_gr_bot') == ['−12'] and ptext(m, 'label_title') == ['Sennheiser HD 600'], 'a preset with a Preamp line: its value; +12 / −12')
    expect([ptexts(m, 'pod_label', i) for i in range(1, 5)] == [['105 Hz'], ['2 kHz'], ['10 kHz'], ['140 Hz']] and ptexts(m, 'pod_sub', 3) == ['High shelf · Q 0.7'], 'AutoEQ\'s bands: a shelf is a shelf, kHz from 1000')
    expect(m.props.get((m.widgets['pod_note0'], 'visible')) == 0 and m.props.get((m.widgets['pod_gap1'], 'visible')) == 1 and [piece(m, i).removeprefix('pod_cd_') for i in range(1, 5)] == ST.peqp_pieces(4), 'no skipped line: the note is hidden, the gap before the Rename / Delete card shown; four bands: top, mid, mid, bot')
    auto = b'Filter 1: ON PK Fc 1000 Hz Gain 6 dB Q 1\nFilter 2: ON LSC Fc 100 Hz Gain 3 dB Q 0.7\n'
    m = ppage([('auto.txt', auto)], 'auto.txt')
    ok, p3, _ = parse(m0, auto)
    cut = 20 * math.log10(auto_gain(p3['bands'], 48000))
    expect(p3['automatic'] == 1 and ptexts(m, 'pod_value', 0) == ['Auto · ' + G.gain_text(cut)] and cut < -5, f'no Preamp line: "Auto · {G.gain_text(cut)}", the cut the player makes at 48 kHz ({ptexts(m, "pod_value", 0)})')
    expect(ptexts(m, 'pod_sub', 1) == ['Peak · Q 1'] and ptexts(m, 'pod_value', 1) == ['+6.0 dB'] and [piece(m, i).removeprefix('pod_cd_') for i in range(1, 3)] == ['top', 'bot'], 'a Q of 1 is "Q 1"; two bands')
    one = b'Preamp: 2 dB\nFilter 1: ON PK Fc 999.96 Hz Gain 0 dB Q 10\nFilter 2: ON LP Fc 20000\n'
    m = ppage([('one.txt', one)], 'one.txt')
    expect(ptexts(m, 'pod_label', 1) == ['1 kHz'] and ptexts(m, 'pod_value', 1) == ['0.0 dB'] and ptexts(m, 'pod_sub', 1) == ['Peak · Q 10'] and ptexts(m, 'pod_value', 0) == ['+2.0 dB']
           and piece(m, 1) == 'pod_cd_single' and hair(m, 1) == 0, 'one band: a single piece with no hairline, "0.0 dB", Q 10, a boosted preamp with its sign')
    nt = m.lookups[(m.widgets['pod_note0'], 'pod_note0_t')]
    expect([c[2] for c in m.calls if c[0] == 'widget_set_text_utf8' and c[1] == nt] == ['1 line not supported was skipped.'], 'one skipped line: the singular')
    # the range: 12, 18, 24 and a curve past 24 clamped
    for what, text, want in (('+5 dB', b'Preamp: 0 dB\nFilter 1: ON PK Fc 1000 Hz Gain 5 dB Q 1\n', 12), ('+12.5 dB', b'Preamp: 0 dB\nFilter 1: ON PK Fc 1000 Hz Gain 12.5 dB Q 1\n', 18),
                             ('-20 dB', b'Preamp: 0 dB\nFilter 1: ON PK Fc 1000 Hz Gain -20 dB Q 1\n', 24),
                             ('three +12 dB at 1 kHz (+36)', b'Filter 1: ON PK Fc 1000 Hz Gain 12 dB Q 1\nFilter 2: ON PK Fc 1000 Hz Gain 12 dB Q 1\nFilter 3: ON PK Fc 1000 Hz Gain 12 dB Q 1\n', 24)):
        m = ppage([('r.txt', text)], 'r.txt')
        okp, pp, _ = parse(m0, text)
        db, rng = G.curve(pp['bands'])
        _, w, h, px = pbitmap(m)
        mp = G.render(db, rng)
        same = all(abs((px[y * w + x] >> 24) - mp[y][x][0]) <= 1 and abs((px[y * w + x] & 255) - mp[y][x][1]) <= 2 for y in range(h) for x in range(w))
        expect(rng == want and ptext(m, 'pod_gr_top') == [f'+{want}'] and ptext(m, 'pod_gr_bot') == [f'−{want}'] and same, f'{what}: the scale is ±{want} dB ({ptext(m, "pod_gr_top")}) and the bitmap is the model\'s')
    # the 30 band limit: every row used, the last without a hairline (the asset's has none)
    many = ''.join(f'Filter {i + 1}: ON PK Fc {100 + 50 * i} Hz Gain {(i % 5) - 2} dB Q 2\n' for i in range(30)).encode()
    m = ppage([('many.txt', many)], 'many.txt')
    expect(all(ptexts(m, 'pod_label', i) == [f'{100 + 50 * (i - 1)} Hz' if 100 + 50 * (i - 1) < 1000 else G.freq_text(100 + 50 * (i - 1))] for i in range(1, 31)) and [piece(m, i).removeprefix('pod_cd_') for i in range(1, 31)] == ST.peqp_pieces(30)
           and [hair(m, i) for i in (1, 29)] == [1, 1] and hair(m, 30) is None, '30 bands: every row named, the card\'s pieces, a hairline on all but the last (which has none)')

    # refusals: nothing opens
    for what, kw in (('a file that does not parse', {'name': 'broken.txt'}), ('a file that is gone', {'name': 'gone.txt'}), ('a name too long', {'name': 'x' * 70 + '.txt'})):
        m = ppage(files, **kw)
        say = [c[1] for c in m.calls if c[0] == 'toast']
        expect(m.shown == 0 and ('window_open', 'm1plus_peqpage') not in m.calls and (say == ['Cannot read this preset'] or what == 'a name too long') and not m.bitmaps, f'{what}: refused, nothing opens ({say})')
    # not our asset: a page missing a widget binds and draws nothing, and the next open starts clean
    m = ppage(files, 'Long.txt', drop=('pod_gr_top',))
    expect(m.shown == 1 and not m.bitmaps and not [x for x in m.bound if x[1] in (O['EVT_BEFORE_PAINT'], O['EVT_DESTROY'])], 'an asset without the scale labels: nothing is drawn or bound')
    m = ppage(files, 'Long.txt', bitmap_ok=False)
    expect(m.shown == 1 and not m.bitmaps and ptexts(m, 'pod_value', 1) == ['+14.0 dB'], 'no memory for the bitmap: the rows are there, the card stays empty')
    fn, c = m.bound[(m.widgets['pod_graph'], O['EVT_BEFORE_PAINT'])]
    m.blits.clear(); m.call(fn, a0=c, a1=m.alloc(0x40), count=1 << 30)
    expect(not m.blits, '... and a paint draws nothing')
    m = demo_machine()
    for n in PBANDS: m.widget(n)
    m.call(PSYMS['peqpage_opened'], m.window, count=1 << 30)
    expect(not [c for c in m.calls if c[0] in ('widget_set_text_utf8', 'widget_set_visible', 'widget_on')], 'opened without a preset parsed first (not through the Equalizer page): nothing')


def settings_value_row(settings):
    """The value label of the first Settings row of kind 'value' (a grey value and a chevron): the geometry a band row's gain copies."""
    for page in pod_pages.PAGES:
        for i, r in enumerate(page.rows):
            if pod_pages.row_kind(r) == 'value':
                w = settings.page_tree(page).find(f'pod_value{i}')
                if w is not None: return w
    raise AssertionError('no value row')


def layout_peqp_tests(ctx):
    """The page under demo's own layouter and hit test (as test/pod/settings.py does the cards pages)."""
    expect, P = ctx.expect, pod_pages
    settings = sibling('settings')
    page = P.PEQP_PAGE
    t = settings.page_tree(page)
    sv = t.find('pod_scrollview')
    for n, skipped in ((1, 0), (4, 2), (30, 1)):
        items = P.peqp_items(n, skipped > 0)
        placed, end = ST.layout(items)
        m = settings.SL(page)
        flags = lambda name, extra: m.u.mem_write(m.kid[name] + 0x24, struct.pack('<H', F_ENABLE | extra))
        for i in range(1, n + 1): flags(f'pod_row{i}', F_VISIBLE | F_SENSITIVE)   # (a tap on a band row opens the band page)
        if skipped: flags('pod_note0', F_VISIBLE); flags('pod_gap1', 0)
        m.mark(); m.relayout()
        names = ['pod_top', 'pod_graph', 'pod_gap0', 'pod_row0', 'pod_sec0'] + [f'pod_row{i}' for i in range(1, n + 1)] + (['pod_note0'] if skipped else ['pod_gap1']) + ['pod_row32', 'pod_row31', 'pod_end']
        got = [(nm,) + m.box(nm) for nm in names]
        tag = f'{n} bands{" and a note" if skipped else ""}'
        expect([(x, y, h) for _, x, y, _, h in got] == [(0, y, ST.item_h(it)) for it, y in placed], f'{tag}: demo\'s layouter stacks the model\'s column (graph {ST.GRAPH_H} high, the preamp card, the header, {n} rows, the note or the gap, and the Rename / Delete card)')
        expect(m.vh() == end and end == sum(ST.item_h(it) for it, _ in placed), f'{n} bands: virtual_h {m.vh()} is the model\'s {end}')
        pcs = ST.pieces(items)
        expect(ST.peqp_pieces(n) == pcs[1:-2] and pcs[0] == 'single' and pcs[-2:] == ['top', 'bot'] and (pcs[0] == 'single') and items[-3] is (P.PEQP_NOTE if skipped else P.GAP) and items[-1] is P.PEQP_DELETE and items[-2] is P.PEQP_RENAME,
               f'{tag}: the preamp row is a single piece, the bands one card, Rename and Delete Preset a top and a bottom piece')
        # touches: the band rows, Rename and Delete take a tap; the preamp row, the graph, the gaps and the notes reach nothing actionable
        node_tree = asset_tree(os.path.join(settings.UI, page.key + '.bin'))
        for nm, x_, y_, w_, h_ in got:
            nd = node(node_tree, nm); nd.x, nd.y, nd.w, nd.h = x_, y_, w_, h_
            if nm.startswith('pod_row') and nm != 'pod_row0': nd.flags |= F_VISIBLE
            if nm == 'pod_note0' and skipped: nd.flags |= F_VISIBLE
            if nm in ('pod_row31', 'pod_row32') or (nm.startswith('pod_row') and 1 <= int(nm[7:]) <= n): nd.flags |= F_VISIBLE | F_SENSITIVE
        mm = Machine()
        for nm, x_, y_, w_, h_ in got:
            if y_ + h_ > 400: continue
            for x in (30, 160, 290):
                path = stock_target(mm, node_tree, x, 50 + y_ + h_ // 2)
                if nm in ('pod_row31', 'pod_row32') or (nm.startswith('pod_row') and nm != 'pod_row0'): expect(nm in path, f'{tag}: a tap at x {x} on {nm} reaches it ({path})')
                else: expect(not any(c.startswith('pod_row') for c in path) and path[-1] in ('pod_scrollview', 'pod_listview', page.name), f'{tag}: a tap at x {x} on {nm} reaches nothing actionable ({path})')
    # the asset
    kids = [c.name for c in sv.children]
    expect(kids[:5] == ['pod_top', 'pod_graph', 'pod_gap0', 'pod_row0', 'pod_sec0'] and kids[-5:] == ['pod_note0', 'pod_gap1', 'pod_row32', 'pod_row31', 'pod_end'] and len(kids) == 5 + 30 + 5,
           f'the asset\'s column: the graph, a gap, the preamp row, the header, 30 band rows, the note, a gap, Rename and Delete Preset ({kids[:8]})')
    gr = sv.children[1]
    expect(gr.get('sensitive') == 'false' and gr.h == ST.GRAPH_H and all(gr.get(f'style:{s_}:bg_color') == '#00000000' for s_ in ('normal', 'disable', 'focused')),
           'the graph view is insensitive and transparent (the bitmap drawn in its before-paint shows under its labels)')
    labs = {c.name: c for c in gr.children}
    expect(sorted(labs) == sorted(['pod_gr_top', 'pod_gr_mid', 'pod_gr_bot', 'pod_gr_f100', 'pod_gr_f1k', 'pod_gr_f10k', 'pod_gr_hz']) and all(c.get('sensitive') == 'false' for c in labs.values()), 'the graph\'s seven labels, none sensitive')
    # each label centres on its grid line (card x PX0 + 58 / 141 / 224) and the scale labels on theirs
    expect([labs[n_].x + labs[n_].w // 2 - ST.CM - G.PX0 for n_ in ('pod_gr_f100', 'pod_gr_f1k', 'pod_gr_f10k')] == list(G.GRID_X) and
           [labs[n_].y + labs[n_].h // 2 for n_ in ('pod_gr_top', 'pod_gr_mid', 'pod_gr_bot')] == [G.PY0, G.PY0 + G.PH // 2, G.PY0 + G.PH], 'the frequency labels sit under their grid lines, the scale labels on theirs')
    byname = {c.name: c for c in sv.children if c.name.startswith('pod_row')}
    rows = [byname[f'pod_row{i}'] for i in range(31)]
    dele, ren = byname['pod_row31'], byname['pod_row32']
    pre = rows[0]
    expect(pre.get('sensitive') == 'false' and pre.get('visible') != 'false' and pod_i18n.shown_english(next(c for c in pre.children if c.name == 'pod_label0')) == 'Preamp'
           and not [c for c in pre.children if c.name in ('pod_chevron', 'pod_check0')] and (pre.get('style:normal:bg_image'), pre.get('style:pressed:bg_image')) == ('pod_cd_single', 'pod_cd_single_down'), 'the preamp row: a single piece, a value, no chevron, no touch')
    pv = next(c for c in pre.children if c.name == 'pod_value0')
    expect(pv.x + pv.w == ST.band_right() == ST.CHEV_INSET * 0 + ST.chevron_left() - ST.VALUE_GAP, 'the preamp value ends where every value on the page ends (the band gains\'): a gap before the chevron\'s column')
    expect(all(r.get('visible') == 'false' and r.get('sensitive') == 'false' for r in rows[1:]) and len(rows) == 31, 'the band rows start hidden and insensitive')
    r1 = rows[1]
    lab, val, sub = (next(c for c in r1.children if c.name == f'pod_{k}1') for k in ('label', 'value', 'sub'))
    chev = next(c for c in r1.children if c.name == 'pod_chevron')
    sizes = lambda w: (w.get('style:normal:font_size'), w.get('style:normal:text_color'), w.get('style:normal:text_align_h'))
    expect((lab.y, lab.h, sub.y, sub.h) == (ST.BAND_TITLE_Y, ST.BAND_TITLE_H, ST.BAND_SUB_Y, ST.BAND_SUB_H) and lab.x == sub.x == ST.CM + ST.PAD and lab.w == sub.w == val.x - ST.BAND_GAIN_GAP - lab.x
           and sizes(lab)[0] == str(ST.BAND_TITLE_PX) and sizes(sub) == (str(ST.BAND_SUB_PX), '#AAAAAA', 'left') and ST.BAND_SUB_PX < ST.BAND_TITLE_PX
           and chev.x == ST.chevron_left() and not [c for c in r1.children if c.name in ('pod_check1', 'pod_switch1')],
           'a band row: the frequency (20 px white) on the first line, the grey 16 px line under it (the Podcasts cells\' pair), the chevron of a row that opens a page')
    # the gain is a value row's value: 18 px grey, the full row high (centred like the chevron), ending VALUE_GAP before the chevron, as Settings' value rows
    sval = settings_value_row(settings)
    expect((val.y, val.h) == (0, ST.ROW_H) == (sval.y, sval.h) and val.x + val.w == ST.band_right() == sval.x + sval.w and sizes(val) == (str(ST.VALUE_PX), ST.GREY, 'right') == sizes(sval)
           and abs(chev.y + chev.h / 2 - (val.y + val.h / 2)) <= 1 and val.x + val.w + ST.VALUE_GAP == chev.x,
           'a band row\'s gain is the geometry of a Settings value row: 18 px grey, right aligned 8 px before the chevron, centred on the row (the chevron\'s own centre)')
    expect(all(c.get('sensitive') == 'false' for r in rows for c in r.children), 'nothing inside a row takes a touch (the row does)')
    # Rename and Delete Preset: one card, a top and a bottom piece
    labr, labd = [c for c in ren.children if c.name == 'pod_label32'], [c for c in dele.children if c.name == 'pod_label31']
    expect(dele.get('visible') != 'false' and dele.get('sensitive') != 'false' and ren.get('visible') != 'false' and ren.get('sensitive') != 'false' and [c.name for c in dele.children] == ['pod_label31'] and [c.name for c in ren.children] == ['pod_label32', 'pod_hair']
           and (ren.get('style:normal:bg_image'), ren.get('style:pressed:bg_image')) == ('pod_cd_top', 'pod_cd_top_down') and (dele.get('style:normal:bg_image'), dele.get('style:pressed:bg_image')) == ('pod_cd_bot', 'pod_cd_bot_down')
           and labd[0].get('sensitive') != 'true' and pod_i18n.shown_english(labd[0]) == 'Delete Preset' and pod_i18n.shown_english(labr[0]) == 'Rename Preset'
           and all(labd[0].get(f'style:{s_}:text_color') == '#FF6B6B' for s_ in ('normal', 'disable', 'focused')) and not labr[0].get('style:normal:text_color') == '#FF6B6B' and sv.children[-4].name == 'pod_gap1' and sv.children[-4].get('visible') != 'false',
           'Rename Preset (white) above Delete Preset (red): always shown and tappable, one card of a top and a bottom piece with a hairline between, after a gap, no glyph, no chevron')
    note = sv.children[-5]
    expect(note.get('visible') == 'false' and note.h == ST.item_h(P.PEQP_NOTE) and note.children[0].type == 'label', 'the note starts hidden: a wrapping label two lines tall')
    expect([c.name for c in sv.children if c.name.startswith('pod_sec')] == ['pod_sec0'] and pod_i18n.shown_english(sv.children[4].children[0]) == 'Bands', 'the Bands header')
    expect(P.PEQP_PAGE.rows == [] and P.PAGES[P.PEQP_PAGE_INDEX] is P.PEQP_PAGE and t.find('label_title') is not None, 'the page exports no rows; its navbar title is the payload\'s')
    expect(not [c for c in t.children if c.name.startswith('ps_')], 'no save sheet on the Preset page')


def layout_peqlib_tests(ctx):
    """The Presets page under demo's own layouter, and the asset against the model (tools/pod_settings.py LIB_ROW_H)."""
    expect, P = ctx.expect, pod_pages
    settings = sibling('settings')
    page = P.PEQLIB_PAGE
    t = settings.page_tree(page)
    PQ = O['PQ_ROWS']
    for na, nc in ((0, 0), (1, 0), (0, 1), (3, 2), (PQ, PQ)):
        items = [P.PEQLIB_DOWNLOAD] + ([P.PEQLIB_AUTOEQ] + [P.PEQLIB_ROW] * na if na else []) + ([P.PEQLIB_CARD] + [P.PEQLIB_ROW] * nc if nc else [])
        placed, end = ST.layout(items)
        m = settings.SL(page)
        flags = lambda name, extra: m.u.mem_write(m.kid[name] + 0x24, struct.pack('<H', F_ENABLE | extra))
        for i in range(na): flags(f'pod_row{1 + i}', F_VISIBLE)
        for i in range(nc): flags(f'pod_row{PQ + 1 + i}', F_VISIBLE)
        if na: flags('pod_sec0', F_VISIBLE)
        if nc: flags('pod_sec1', F_VISIBLE)
        m.mark(); m.relayout()
        names = ['pod_top', 'pod_row0'] + (['pod_sec0'] + [f'pod_row{1 + i}' for i in range(na)] if na else []) + (['pod_sec1'] + [f'pod_row{PQ + 1 + i}' for i in range(nc)] if nc else []) + ['pod_end']
        got = [(nm,) + m.box(nm) for nm in names]
        expect([(x, y, h) for _, x, y, _, h in got] == [(0, y, ST.item_h(it)) for it, y in placed], f'{na} AutoEq and {nc} On Card files: demo\'s layouter stacks the model\'s column (the download row, a header and 60 px rows per section)')
        expect(m.vh() == end == lib_vh(na, nc), f'{na} + {nc} files: virtual_h {m.vh()} is the model\'s {end} (what peqlib.c sets: {lib_vh(na, nc)})')
    sv = t.find('pod_scrollview')
    kids = [c.name for c in sv.children]
    expect(kids == ['pod_top', 'pod_row0', 'pod_sec0'] + [f'pod_row{i}' for i in range(1, PQ + 1)] + ['pod_sec1'] + [f'pod_row{i}' for i in range(PQ + 1, 2 * PQ + 1)] + ['pod_end'], 'the asset\'s column: the download row, the AutoEq header and 64 slots, the On Card header and 64 slots')
    dl = sv.children[1]
    expect(dl.h == ST.ROW_H and dl.get('visible') != 'false' and dl.get('sensitive') != 'false' and pod_i18n.shown_english(next(c for c in dl.children if c.name == 'pod_label0')) == 'Download from AutoEq'
           and (dl.get('style:normal:bg_image'), dl.get('style:pressed:bg_image')) == ('pod_cd_single', 'pod_cd_single_down') and [c.name for c in dl.children if c.name in ('pod_icon', 'pod_chevron')] == ['pod_icon', 'pod_chevron'],
           'the download row: 52 px, a single card with the glyph, its label and a chevron, shown and tappable')
    expect([pod_i18n.shown_english(sv.children[i].children[0]) for i in (2, 3 + PQ)] == ['AutoEq', 'On Card'] and all(sv.children[i].get('visible') == 'false' for i in (2, 3 + PQ)), 'the two headers, AutoEq and On Card, start hidden')
    rows = [c for c in sv.children if c.name.startswith('pod_row')][1:]
    expect(len(rows) == 2 * PQ and all(r.h == ST.LIB_ROW_H and r.get('visible') == 'false' and r.get('sensitive') == 'false' and r.type == 'list_item' and r.get('style') == 'list_item_style' for r in rows),
           'the 48 file slots are 60 px list items, hidden and insensitive')
    ok = True
    for k, r in enumerate(rows):
        i = k + 1
        j = k % PQ
        want = ('top' if j == 0 else 'bot' if j == PQ - 1 else 'mid')
        lab, sub = (next((c for c in r.children if c.name == f'pod_{b}{i}'), None) for b in ('label', 'sub'))
        chev = [c for c in r.children if c.name == 'pod_chevron']
        hair = [c for c in r.children if c.name == 'pod_hair']
        lx, lw = ST.label_box('lib', False)
        ok = ok and lab is not None and sub is not None and (r.get('style:normal:bg_image'), r.get('style:pressed:bg_image')) == ST.piece_images(want, tall=True) \
            and (lab.x, lab.w, lab.y, lab.h) == (lx, lw, ST.LIB_TITLE_Y, ST.LIB_TITLE_H) and (sub.x, sub.w, sub.y, sub.h) == (lx, lw, ST.LIB_SUB_Y, ST.LIB_SUB_H) and sub.get('style:normal:text_color') == '#AAAAAA' and sub.get('style:normal:font_size') == str(ST.BAND_SUB_PX) and lab.get('style:normal:font_size') == str(ST.BAND_TITLE_PX) \
            and len(chev) == 1 and (chev[0].x, chev[0].y, chev[0].w, chev[0].h) == ST.accessory('chevron', ST.LIB_ROW_H) and chev[0].get('sensitive') == 'false' \
            and bool(hair) == (want != 'bot') and all((h_.x, h_.y, h_.w, h_.h) == (lx, ST.LIB_ROW_H - 1, ST.CM + ST.CARD_W - lx, 1) for h_ in hair) \
            and not [c for c in r.children if c.name in ('pod_icon', 'pod_check%d' % i)] and sub.get('sensitive') == 'false'
    expect(ok, 'every slot: the tall piece of a full section card (top, middles, bottom), the name (20 px) at y 8, the grey 16 px line at y 32, the chevron centred in 60 px, a hairline but on the last')
    expect(P.PAGES[P.PEQLIB_PAGE_INDEX] is P.PEQLIB_PAGE and P.PEQLIB_PAGE_INDEX == 53 == P.PAGES.index(P.PEQBAND_PAGE) - 5 and P.PEQLIB_PAGE.rows == [] and t.find('label_title') is not None
           and P.row_kind(P.PEQLIB_ROW) == 'lib' and P.row_kind(P.PEQP_DELETE) == 'delete', 'the Presets page is PAGES[53] (the editor and its two pages follow), exports no rows; its navbar title is the payload\'s')


def widths_tests(ctx):
    """The page's strings fit in 13 languages: the Preamp label, a band row's grey line, the preamp value, the skipped note."""
    import awtk_style
    from awtk_text import Ttf, StbText
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    width = lambda text, px: StbText(font, px).layout(text)[1]
    tree = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.PEQP_PAGE.key + '.bin'), 'rb').read())
    th = awtk_style.parse(open(os.path.join(raw, 'styles', 'default.bin'), 'rb').read())
    row_px = th.find('hscroll_label', 'srlabel_leftwhite21_style', 'normal')[0].get('font_size')
    pre_lab = tree.find('pod_label0')
    sub = tree.find('pod_sub1')
    note_t = tree.find('pod_note0_t')
    del_lab = tree.find('pod_label31')
    lib = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.PEQLIB_PAGE.key + '.bin'), 'rb').read())
    lib_sub, lib_dl = lib.find('pod_sub1'), lib.find('pod_label0')
    over = []
    for loc in pod_i18n.LOCALES:
        T = lambda k: pod_i18n.TEXT[k][loc]
        if width(T('Preamp'), row_px) > pre_lab.w: over.append((loc, 'Preamp', width(T('Preamp'), row_px), pre_lab.w))
        if width(T('Bands'), ST.HDR_PX) > ST.HDR_W: over.append((loc, 'Bands'))
        for key in ('For Headphones', 'For Line Out', 'For USB DAC'):   # the Equalizer page's output line: one line in the note's label
            if width(T(key), ST.NOTE_PX) > ST.HDR_W: over.append((loc, key, width(T(key), ST.NOTE_PX)))
        if width(T('Delete Preset'), row_px) > del_lab.w: over.append((loc, 'Delete Preset', width(T('Delete Preset'), row_px), del_lab.w))
        for hdr in ('AutoEq', 'On Card'):
            if width(T(hdr), ST.HDR_PX) > ST.HDR_W: over.append((loc, hdr))
        if width(T('Download from AutoEq'), row_px) > lib_dl.w: over.append((loc, 'Download from AutoEq', width(T('Download from AutoEq'), row_px), lib_dl.w))
        for kind in ('Over-ear', 'In-ear', 'Earbud'):   # a long source name in front of the kind's word, and the On card line
            line = 'oratory1990 · ' + T(kind)
            if width(line, ST.BAND_SUB_PX) > lib_sub.w - 4: over.append((loc, line, width(line, ST.BAND_SUB_PX), lib_sub.w))
        if width(T('On card'), ST.BAND_SUB_PX) > lib_sub.w - 4: over.append((loc, 'On card'))
        value = T('Auto') + ' · ' + '−24.0 dB'
        if width(value, ST.VALUE_PX) > ST.PREAMP_W - 4: over.append((loc, 'preamp value', value, width(value, ST.VALUE_PX)))
        for kind in ('Low shelf', 'High shelf', 'Peak'):
            line = T(kind) + ' · Q 10 · L'
            if width(line, ST.BAND_SUB_PX) > sub.w - 4: over.append((loc, line, width(line, ST.BAND_SUB_PX), sub.w))
        for key in ('%d line not supported was skipped.', '%d lines not supported were skipped.'):
            t = T(key).replace('%d', '30')
            lines, line = 1, ''
            for tok in re.findall(r'\S+\s*', t) if ' ' in t else list(t):
                if line and width(line + tok.rstrip(), ST.NOTE_PX) > note_t.w - 4: lines, line = lines + 1, tok
                else: line += tok
            if lines > 2: over.append((loc, key, lines))
    expect(not over, f'the preset page\'s and the Presets page\'s strings fit in all 13 languages ({over[:3]})')
    t_w = width('20000 Hz', row_px) + width('+24.0 dB', row_px)
    expect(t_w < ST.RIGHT - (ST.CM + ST.PAD), f'a band row\'s longest first line ("20000 Hz" and "+24.0 dB", {t_w} px) fits the row')
    expect(width('10.5 kHz', row_px) <= tree.find('pod_label1').w, 'a frequency fits its label')
    # the 10-Band editor and its two pages (patch/tenband.c): the row labels, the grey values, the curve names, the slider texts, in every language
    ed = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.TENBAND_PAGE.key + '.bin'), 'rb').read())
    pa = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.TENPREAMP_PAGE.key + '.bin'), 'rb').read())
    cu = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.TENCURVE_PAGE.key + '.bin'), 'rb').read())
    over = []
    lw_curve, lw_pre = ed.find('pod_label0').w, ed.find('pod_label1').w
    for loc in pod_i18n.LOCALES:
        T = lambda k: pod_i18n.TEXT[k][loc]
        for key, box in (('Curve', lw_curve), ('Preamp', lw_pre)):
            if width(T(key), row_px) > box: over.append((loc, key, width(T(key), row_px), box))
        for name in pod_pages.TENCURVE_NAMES:
            if width(T(name), ST.VALUE_PX) > ST.PREAMP_W - 4: over.append((loc, name, 'value'))
            if width(T(name), row_px) > cu.find(f'pod_label{pod_pages.TENCURVE_NAMES.index(name)}').w: over.append((loc, name, 'row'))
        auto = T('Auto') + ' · −12.0 dB'
        if width(auto, ST.VALUE_PX) > ST.PREAMP_W - 4: over.append((loc, auto, width(auto, ST.VALUE_PX)))
        if width('−0.0 dB', ST.VALUE_PX) > ST.curve_box()[1] or width(T('Auto'), row_px) > pa.find('pod_label0').w: over.append((loc, 'Auto row'))
        for n in range(13):
            txt = ('−' if n else '') + T('%d dB').replace('%d', str(n))
            if width(txt, row_px) > pa.find('pod_label1').w: over.append((loc, txt))
        for txt in ('−11.5', '+11.5', '+12', '−12', '16k'):
            if width(txt, TBM.LABEL_PX) > TBM.PILL_W - 4: over.append((loc, txt, 'pill'))
        for key in REGION_TEXTS:
            if width(T(key), ST.HDR_PX) > 272: over.append((loc, key, width(T(key), ST.HDR_PX)))
        t = T(pod_pages.TENPREAMP_PAGE.layout[1].text)   # the Preamp page's note: at most two lines in its label (greedy, as the skipped-lines note)
        lines, line = 1, ''
        for tok in re.findall(r'\S+\s*', t) if ' ' in t else list(t):
            if line and width(line + tok.rstrip(), ST.NOTE_PX) > pa.find('pod_note0_t').w - 4: lines, line = lines + 1, tok
            else: line += tok
        if lines > 2: over.append((loc, 'Preamp note', lines))
        if width(T(pod_pages.DSD_NOTE.text), ST.NOTE_PX) > ed.find('pod_note0_t').w - 4: over.append((loc, 'DSD note', width(T(pod_pages.DSD_NOTE.text), ST.NOTE_PX)))   # one line, at the end of the editor
    expect(not over, f'the editor\'s and its pages\' strings fit in all 13 languages: Curve and Preamp in their 98 px label boxes, a curve name or "Auto · −12.0 dB" in the 150 px value, the picker rows, the slider values in the pill ({over[:3]})')
    # preset editing (patch/peqpage.c, patch/peqband.c): Rename, the unsaved-changes dialog, the band page
    bp = awtk_ui.parse(open(os.path.join(raw, 'ui', pod_pages.PEQBAND_PAGE.key + '.bin'), 'rb').read())
    ren_lab = tree.find('pod_label32')
    dlg_t, dlg_b = bp.find('pq_title'), bp.find('pq_item0')
    over = []
    for loc in pod_i18n.LOCALES:
        T = lambda k: pod_i18n.TEXT[k][loc]
        for key, px, box in (('Rename Preset', 21, ren_lab.w), ('Save Changes?', 20, dlg_t.w - 4), ('Frequency', 18, bp.find('pod_hs_n0').w), ('Gain', 18, bp.find('pod_hs_n1').w),
                             ('Peak', 14, 90), ('Low shelf', 14, 90), ('High shelf', 14, 90), ('Tap a value to type it exactly.', ST.NOTE_PX, bp.find('pod_note0_t').w - 4)):
            if width(T(key), px) > box: over.append((loc, key, width(T(key), px), box))
        for key in pod_ui.PQD_KEYS:
            if width(T(key), 18) > dlg_b.w - 24: over.append((loc, key, width(T(key), 18), dlg_b.w))
        if width(T('Band %d').replace('%d', '30'), 20) > 110: over.append((loc, 'Band %d'))
    expect(not over, f'Rename, the unsaved-changes dialog and the band page\'s strings fit in all 13 languages ({over[:3]})')



def carry_tests(ctx):
    """Filter memory across a gapless join (patch/peq_player.c carry): two instances, the old one's uninit before the new one's open."""
    expect = ctx.expect
    bands = [(1, 1, 100, 9.0, 0.7), (1, 0, 1000, -4.0, 1.0), (1, 2, 9000, 3.0, 0.7)]
    rec = pack_state(1, pack_preset(bands, preamp=-6.0, automatic=2))
    other = pack_state(1, pack_preset([(1, 1, 100, -6.0, 0.7)], preamp=0.0, automatic=2))
    N, K = 9000, 4000
    x48 = tone(N, 2, 48000, freqs=(61.0, 997.0), amp=0.3)
    x44 = tone(N, 2, 44100, freqs=(61.0, 997.0), amp=0.3)
    cut = 2 * K

    def first(rate=48000, files=None, x=None, nch=2):
        p = Player(files if files is not None else {STATE: rec})
        af = p.open(); p.reinit(af, rate, nch=nch)
        _, y = p.play(af, (x or x48)[:cut], rate, nch=nch)
        return p, af, y

    def second(p, af, rate=48000, x=None, nch=2, gap=20, files=None, played=True):
        """The old instance goes, the next opens and plays the rest of the signal."""
        p.leave(af)
        p.clock += gap
        if files is not None: p.files.update(files)
        af2 = p.open(); r, *_ = p.reinit(af2, rate, nch=nch)
        _, y = p.play(af2, (x or x48)[cut:], rate, nch=nch)
        return af2, y

    # the reference: one instance, the signal in two blocks
    p = Player({STATE: rec}); af = p.open(); p.reinit(af, 48000)
    _, c1 = p.play(af, x48[:cut], 48000)
    _, c2 = p.play(af, x48[cut:], 48000)
    want = model(bands, 48000, 2, x48, 10 ** (-6.0 / 20))
    expect(near(c1 + c2, want), 'the continuous reference matches the model')
    zero = model(bands, 48000, 2, x48[cut:], 10 ** (-6.0 / 20))
    expect(max(abs(a - b) for a, b in zip(c2[:200], zero[:200])) > 0.02, 'the signal is one where a cold start is audible')

    # a track played to its end hands its memory to the next one: bit-exact continuation
    p, af, y1 = first(); p.ended()
    _, y2 = second(p, af)
    expect(y1 == c1 and y2 == c2, 'a gapless join continues the filter state: the second file equals one continuous run, bit for bit')

    # not at its end (a skip, a stop): the next starts from zero
    p, af, _ = first(); p.ended(0)
    _, y2 = second(p, af)
    expect(near(y2, zero), 'the track did not reach its end (a skip): the next starts from zero memory')
    p, af, _ = first()
    _, y2 = second(p, af)
    expect(near(y2, zero), 'no demuxer at all (no mpctx): the next starts from zero memory')

    # one try: a third instance starts from zero
    p, af, _ = first(); p.ended()
    af2, _ = second(p, af)
    p.ended(0); p.leave(af2); af3 = p.open(); p.reinit(af3, 48000)
    _, y3 = p.play(af3, x48[cut:], 48000)
    expect(near(y3, zero), 'the carried memory is taken once: the instance after the next starts from zero')

    # an instance that never played does not eat it (the chain rebuilt before the first block)
    p, af, _ = first(); p.ended()
    p.leave(af); p.clock += 10
    idle = p.open(); p.reinit(idle, 48000); p.leave(idle)
    af3 = p.open(); p.reinit(af3, 48000)
    _, y3 = p.play(af3, x48[cut:], 48000)
    expect(y3 == c2, 'an instance that never played leaves the carried memory for the next')

    # a rebuild before the first block (REINIT twice) still adopts
    p, af, _ = first(); p.ended(); p.leave(af)
    af2 = p.open(); p.reinit(af2, 48000); p.reinit(af2, 48000)
    _, y2 = p.play(af2, x48[cut:], 48000)
    expect(y2 == c2, 'a second REINIT before the first block keeps the carried memory for it')

    # too old: a pause, a stop, the album's end
    for gap, what in ((3000, '3 s'), (60000, 'a minute')):
        p, af, _ = first(); p.ended()
        _, y2 = second(p, af, gap=gap)
        expect(near(y2, zero), f'a join {what} later starts from zero memory')
    p, af, _ = first(); p.ended()
    _, y2 = second(p, af, gap=2900)
    expect(y2 == c2, 'a join 2.9 s later still continues')
    p, af, _ = first(); p.ended()
    _, y2 = second(p, af, gap=-5)
    expect(near(y2, zero), 'a clock that went back starts from zero memory')

    # a different rate, channel count or curve starts from zero
    p, af, _ = first(x=x44, rate=44100); p.ended()
    _, y2 = second(p, af, rate=48000)
    expect(near(y2, zero), 'a rate change (44.1 to 48 kHz) resets')
    p, af, _ = first(); p.ended()
    mono = tone(N, 1, 48000, freqs=(61.0, 997.0), amp=0.3)
    _, y2 = second(p, af, nch=1, x=mono)
    expect(near(y2, model(bands, 48000, 1, mono[cut:], 10 ** (-6.0 / 20))), 'a channel count change (stereo to mono) resets')
    p, af, _ = first(); p.ended()
    _, y2 = second(p, af, files={STATE: other})
    expect(near(y2, model([(1, 1, 100, -6.0, 0.7)], 48000, 2, x48[cut:])), 'a different preset between the files starts from zero memory')
    bandsb = [(1, 1, 100, 9.0, 0.7), (1, 0, 1000, -4.0, 1.0), (1, 2, 9000, 3.0, 0.7)]
    p, af, _ = first(); p.ended()
    _, y2 = second(p, af, files={STATE: pack_state(1, pack_preset(bandsb, preamp=-5.0, automatic=2))})
    expect(near(y2, model(bandsb, 48000, 2, x48[cut:], 10 ** (-5.0 / 20))), 'a preamp-only change counts as a different curve: zero memory')

    # a curve change after the join keeps the crossfade path, from the carried memory
    p, af, _ = first(); p.ended(); p.leave(af)
    af2 = p.open(); p.reinit(af2, 48000)
    _, ya = p.play(af2, x48[cut:cut + 400], 48000)
    p.files[STATE] = other
    p.gains(af2, [0] * 10)
    _, yb = p.play(af2, x48[cut + 400:], 48000)
    expect(ya == c2[:400], 'the join continues, then a preset change follows')
    expect(max(abs(a - b) for a, b in zip(yb[:4], c2[400:404])) < 0.005, 'the preset change after the join: the ramp starts at the old curve')
    expect(near(yb[-400:], model([(1, 1, 100, -6.0, 0.7)], 48000, 2, x48)[-400:], 5e-3), 'and ends on the new curve')

    # a preset changed before the first block is a different curve at the join: zero memory
    p, af, _ = first(); p.ended(); p.leave(af)
    af2 = p.open(); p.reinit(af2, 48000)
    p.files[STATE] = other
    p.gains(af2, [0] * 10)
    _, y2 = p.play(af2, x48[cut:], 48000)
    expect(max(abs(a - b) for a, b in zip(y2[:4], zero[:4])) < 0.005 and y2 != c2, 'a preset change between the open and the first block starts the ramp from zero memory')

    # a settled curve only: a ramp or a pending change at the end hands nothing on
    p, af, _ = first(); p.ended()
    p.files[STATE] = other; p.gains(af, [0] * 10)
    _, y2 = second(p, af, files={STATE: rec})
    expect(near(y2, zero), 'an instance with a curve change pending at its end starts the next from zero')

    # pass-through: bypass, DSD and the kill switch never carry in or out
    p, af, _ = first(); p.ended(); p.leave(af)
    p.codec(drv='dsdiff'); p.clock += 10
    afd = p.open(); p.reinit(afd, 352800, fmt=0x0a, bps=4)
    raw = bytes(range(256)) * 8
    _, out = p.play(afd, None, 352800, fmt=0x0a, raw=raw); p.leave(afd)
    expect(out == raw, 'DSD after a PCM track passes untouched')
    p.setword(MPCTX, 0); p.ended(); p.clock += 10
    af3 = p.open(); p.reinit(af3, 48000)
    _, y3 = p.play(af3, x48[cut:], 48000)
    expect(near(y3, zero), 'a DSD track between two PCM tracks drops the carried memory')
    p, af, _ = first(); p.ended(); p.leave(af)
    p.files[KILL] = b''; p.clock += 10
    afk = p.open(); r, *_ = p.reinit(afk, 48000)
    _, out = p.play(afk, x48[cut:], 48000)
    expect(out == x48[cut:], 'the kill switch passes the file untouched after a PCM track')
    del p.files[KILL]; p.leave(afk)
    af3 = p.open(); p.reinit(af3, 48000)
    _, y3 = p.play(af3, x48[cut:], 48000)
    expect(near(y3, zero), 'the kill switch drops the carried memory')
    flat = pack_state(1, pack_preset([], bypass=1))
    p, af, y1 = first(files={STATE: flat}); p.ended()
    expect(y1 == x48[:cut], 'a bypass preset leaves the first file untouched')
    _, y2 = second(p, af)
    expect(y2 == x48[cut:], 'a bypass preset leaves the next file untouched too')
    p, af, _ = first(files={STATE: flat}); p.ended(); p.leave(af)
    p.files[STATE] = rec; p.clock += 10
    af3 = p.open(); p.reinit(af3, 48000)
    _, y3 = p.play(af3, x48[cut:], 48000)
    expect(near(y3, zero), 'nothing is carried out of a bypassed track')

    # non-finite memory is not handed on
    p, af, _ = first(); p.ended()
    z = p.word(af + 16) + 1200   # peq_dsp.current.z: after the 30 coefficient sets
    p.u.mem_write(z, struct.pack('<d', float('nan')))
    _, y2 = second(p, af)
    expect(near(y2, zero) and all(math.isfinite(v) for v in y2), 'a non-finite filter state is dropped, not carried')

    # the player's own memory layout the poke above relies on
    p, af, _ = first()
    live = struct.unpack('<d', bytes(p.u.mem_read(p.word(af + 16) + 1200, 8)))[0]
    expect(live != 0.0, 'the engine\'s filter memory sits 1200 bytes into the instance (peq_engine.c is 30 x 40 bytes)')


# ---- the Presets page (patch/peqlib.c) and Delete Preset (patch/peqpage.c, patch/peq_ui.c peq_delete)
LIB_SLOTS = 2 * O['PQ_ROWS']


def register_lib(m):
    """The Presets page's widgets by name, as the machine's window has them once m1plus.c open_page has opened it (the asset's last row of a section has no hairline)."""
    for i in range(LIB_SLOTS + 1):
        m.widget(f'pod_row{i}')
        if i:
            for base in ('pod_label', 'pod_sub'): m.widget(f'{base}{i}')
            m.lookups[(m.widgets[f'pod_row{i}'], 'pod_hair')] = m.alloc(0x80)
    for i in (O['PQ_ROWS'], LIB_SLOTS): m.lookups.pop((m.widgets[f'pod_row{i}'], 'pod_hair'), None)
    for n in ('pod_sec0', 'pod_sec1', 'pod_scrollview'): m.widget(n)


def libpage(files, card=True):
    """The Presets page opened by peqlib_open (the Equalizer's Presets row's handler) over a card holding files."""
    m = demo_machine()
    m.card_mounted = card
    m.folder(EQ_DIR)
    for name, data in files: m.put(f'{EQ_DIR}/{name}', data)
    register_lib(m)
    m.opened = m.call(PSYMS['peqlib_open'], count=1 << 40)
    return m


def lib_vh(na, nc):
    items = [pod_pages.PEQLIB_DOWNLOAD] + ([pod_pages.PEQLIB_AUTOEQ] + [pod_pages.PEQLIB_ROW] * na if na else []) + ([pod_pages.PEQLIB_CARD] + [pod_pages.PEQLIB_ROW] * nc if nc else [])
    return ST.layout(items)[1]


def stamped(path, body=AUTOEQ): return b'# AutoEq: ' + path.encode() + b'\n' + body
def tall(m, i, state='normal'): return (piece(m, i, state) or '').removeprefix('pod_cdl_')
def vis(m, name): return m.props.get((m.widgets[name], 'visible'))
def tap_row(m, i):
    fn, c = m.bound[(m.widgets[f'pod_row{i}'], O['EVT_CLICK'])]
    return m.call(fn, a0=c, count=1 << 40)


def presets_page_tests(ctx):
    expect = ctx.expect
    files = [('Beta Phones.txt', stamped('oratory1990/over-ear/Beta%20Phones')), ('alpha.txt', AUTOEQ), ('Zed IEM.txt', stamped('Rtings/Foo%20in-ear/Zed%20IEM')),
             ('broken.txt', b'Filter: ON PK Fc 1000 Hz Gain 3 dB\n'), ('Cee.txt', stamped('crinacle/Some%20Dir/Cee')), ('earb.txt', stamped('oratory1990/earbud/Earb')),
             ('notes.md', b'x'), ('.hidden.txt', stamped('oratory1990/over-ear/Hid'))]

    # (1) the Equalizer's Presets row opens the page, which is filled from the card
    m = page(files)
    register_lib(m)
    expect(ptext(m, f'pod_value{ROWS + 1}') == ['6'], 'the Equalizer\'s Presets count: six .txt files (not the .md, not the dot file)')
    m.calls = []
    tap(m, ROWS + 1)
    expect(('window_open', 'm1plus_peqlib') in m.calls and (m.widgets['pod_row0'], O['EVT_CLICK']) in m.bound, 'the Equalizer\'s Presets row opens m1plus_peqlib, whose rows bind')

    # (2) the sections: AutoEq-stamped files first, the others under On Card, each sorted by name without the extension
    m = libpage(files)
    expect(m.opened == 1 and ('window_open', 'm1plus_peqlib') in m.calls, 'peqlib_open opens the page')
    ae, oc = [1, 2, 3, 4], [O['PQ_ROWS'] + 1, O['PQ_ROWS'] + 2]
    expect([vis(m, f'pod_row{i}') for i in range(1, LIB_SLOTS + 1)] == [1 if i in ae + oc else 0 for i in range(1, LIB_SLOTS + 1)], 'four AutoEq rows and two On Card rows shown, the other slots hidden')
    expect([m.props.get((m.widgets[f'pod_row{i}'], 'sensitive')) for i in range(1, LIB_SLOTS + 1)] == [1 if i in ae + oc else 0 for i in range(1, LIB_SLOTS + 1)], 'shown rows are sensitive, hidden rows insensitive')
    expect([ptexts(m, 'pod_label', i) for i in ae] == [['Beta Phones'], ['Cee'], ['earb'], ['Zed IEM']] and [ptexts(m, 'pod_label', i) for i in oc] == [['alpha'], ['broken']],
           f'names without .txt, sorted: AutoEq {[ptexts(m, "pod_label", i) for i in ae]}, On Card {[ptexts(m, "pod_label", i) for i in oc]}')
    expect([ptexts(m, 'pod_sub', i) for i in ae] == [['oratory1990 · Over-ear'], ['crinacle'], ['oratory1990 · Earbud'], ['Rtings · In-ear']] and [ptexts(m, 'pod_sub', i) for i in oc] == [['On card']] * 2,
           f'grey lines: "Source · Kind" from the stamp (the source alone when the directory names no kind), "On card" for the rest ({[ptexts(m, "pod_sub", i) for i in ae]})')
    expect(vis(m, 'pod_sec0') == 1 and vis(m, 'pod_sec1') == 1, 'both headers show')
    expect([tall(m, i) for i in ae] == ['top', 'mid', 'mid', 'bot'] and [tall(m, i) for i in oc] == ['top', 'bot'], f'pieces per section: {[tall(m, i) for i in ae]} / {[tall(m, i) for i in oc]}')
    expect(all(piece(m, i, 'pressed') == piece(m, i) + '_down' and all(piece(m, i, s) == piece(m, i) for s in ('over', 'focused', 'disable')) and piece(m, i).startswith('pod_cdl_') for i in ae + oc),
           'every state has the row\'s tall piece, the pressed one its lit twin')
    expect([hair(m, i) for i in ae] == [1, 1, 1, 0] and [hair(m, i) for i in oc] == [1, 0], 'a hairline under every row but the last of its section')
    expect(m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == lib_vh(4, 2), f'virtual_h is the model\'s column ({m.props[(m.widgets["pod_scrollview"], "virtual_h")]} vs {lib_vh(4, 2)})')
    # the same model as the layouter's: the count is what tools/pod.py exports
    expect(lib_vh(0, 0) == ST.layout([pod_pages.PEQLIB_DOWNLOAD])[1] and lib_vh(1, 0) - lib_vh(0, 0) == ST.HDR_H + ST.LIB_ROW_H and lib_vh(4, 2) == lib_vh(0, 0) + 2 * ST.HDR_H + 6 * ST.LIB_ROW_H, 'the model: base + a header and 60 px per row of each non-empty section')

    # a section with one file is a single piece with no hairline; an empty section has no header
    m = libpage([('only.txt', AUTOEQ)])
    expect(vis(m, 'pod_sec0') == 0 and vis(m, 'pod_sec1') == 1 and vis(m, f'pod_row{O["PQ_ROWS"] + 1}') == 1 and vis(m, 'pod_row1') == 0, 'only an On Card file: the AutoEq header and slots hidden')
    expect(tall(m, O['PQ_ROWS'] + 1) == 'single' and hair(m, O['PQ_ROWS'] + 1) == 0 and m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == lib_vh(0, 1), 'one file: a single piece, no hairline, the column of base + header + row')
    m = libpage([('ae.txt', stamped('oratory1990/over-ear/Ae'))])
    expect(vis(m, 'pod_sec0') == 1 and vis(m, 'pod_sec1') == 0 and vis(m, 'pod_row1') == 1 and tall(m, 1) == 'single' and ptexts(m, 'pod_sub', 1) == ['oratory1990 · Over-ear']
           and m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == lib_vh(1, 0), 'only an AutoEq file: the On Card header hidden')
    for what, kw in (('an empty folder', {'files': []}), ('the card out', {'files': files, 'card': False})):
        m = libpage(**kw)
        expect(vis(m, 'pod_sec0') == 0 and vis(m, 'pod_sec1') == 0 and not [i for i in range(1, LIB_SLOTS + 1) if vis(m, f'pod_row{i}')] and m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == lib_vh(0, 0),
               f'{what}: no header, no file row, just the download row')
    # an edited AutoEq file (a Save marked it) is still listed under AutoEq with the same grey line
    m = libpage([('ed.txt', b'# AutoEq edited: oratory1990/over-ear/Ed\n' + AUTOEQ)])
    expect(vis(m, 'pod_sec0') == 1 and vis(m, 'pod_sec1') == 0 and ptexts(m, 'pod_sub', 1) == ['oratory1990 · Over-ear'], 'an edited AutoEq file: listed under AutoEq, Source · Kind')
    # the source is shown decoded (the stamp itself stays percent-encoded); a malformed '%' stays, a cut never ends mid character
    m = libpage([('a.txt', stamped('Super%20Review/over-ear/X')), ('b.txt', stamped('a%2fb%E6%AD%8C%2/in-ear/Y')), ('c.txt', stamped('50%/earbud/Z')), ('d.txt', stamped('x%zz%/Dir/W')),
                 ('e.txt', stamped('歌' * 30 + '%E6%AD%8C' * 3 + '/Dir/V'))])
    subs = [ptexts(m, 'pod_sub', i) for i in range(1, 6)]
    expect(subs[:4] == [['Super Review · Over-ear'], ['a/b歌%2 · In-ear'], ['50% · Earbud'], ['x%zz%']], f'the grey line decodes %XX of either case and leaves a malformed % as it is ({subs[:4]})')
    expect(subs[4] == ['歌' * 31], f'a decoded source over the line\'s room is cut at a whole character ({subs[4]})')
    u = m.alloc(16)
    def dec(s, size, pad=b'\xaa'):
        m.u.mem_write(u, pad * 16); b = s.encode(); sb = m.alloc(len(b) + 1); m.u.mem_write(sb, b + b'\0')
        r = m.call(PSYMS['pod_url_decode'], u, size, a2=sb, a3=len(b))
        raw = bytes(m.u.mem_read(u, 16)); return r, raw[:raw.find(b'\0')], raw[size:] == pad * (16 - size)
    expect(dec('a%20b', 16)[:2] == (3, b'a b') and dec('%41%4a%4A', 16)[:2] == (3, b'AJJ') and dec('%', 16)[:2] == (1, b'%') and dec('a%2', 16)[:2] == (3, b'a%2') and dec('%g1%1g', 16)[:2] == (6, b'%g1%1g')
           and dec('%2541', 16)[:2] == (3, b'%41') and dec('', 16)[:2] == (0, b''), 'pod_url_decode: %XX of either case, a malformed or short % as it is, no second pass')
    expect(dec('abcdef', 4) == (3, b'abc', True) and dec('a%20bcd', 3) == (2, b'a ', True) and dec('x', 1) == (0, b'', True), 'pod_url_decode: never writes past size, always NUL terminated')

    # a stamp-looking first line that is not a stamp is a file of the user's
    m = libpage([('a.txt', b'# AutoEq: nosource\n' + AUTOEQ), ('b.txt', b'# AutoEq: /x/y\n' + AUTOEQ), ('c.txt', b'# AutoEq: s//n\n' + AUTOEQ), ('d.txt', b'# autoeq: s/over-ear/n\n' + AUTOEQ)])
    expect(vis(m, 'pod_sec0') == 0 and vis(m, 'pod_sec1') == 1 and [ptexts(m, 'pod_sub', O['PQ_ROWS'] + i) for i in range(1, 5)] == [['On card']] * 4, 'a malformed stamp (no Kind, no Source, an empty Kind, wrong case) is a file of the user\'s')
    # more than PQ_ROWS (64) files: the first 64 by name, split; the Equalizer's count is the total
    many = [(f'p{i:02d}.txt', AUTOEQ if i % 2 else stamped('oratory1990/over-ear/P')) for i in range(70)]
    m = libpage(many)
    expect(len([i for i in range(1, LIB_SLOTS + 1) if vis(m, f'pod_row{i}')]) == O['PQ_ROWS'], f'70 files: the first {O["PQ_ROWS"]} by name show')
    m = page(many)
    expect(ptext(m, f'pod_value{ROWS + 1}') == ['70'] and len(shown(m)) == O['PQ_ROWS'], 'the Equalizer\'s Presets count is every .txt file (70) while its picker lists 64')
    m = page([])
    expect(ptext(m, f'pod_value{ROWS + 1}') == ['0'], 'no file: the count is 0')

    # a tap on a file row opens that file's Preset page; the download row opens the AutoEq search page
    m = libpage(files)
    for row, name in ((1, 'Beta Phones.txt'), (3, 'earb.txt'), (O['PQ_ROWS'] + 1, 'alpha.txt')):
        m.calls = []; tap_row(m, row)
        expect(('window_open', 'm1plus_peqpage') in m.calls and [c for c in m.calls if c[0] == 'fopen' and c[1] == f'{EQ_DIR}/{name}'],
               f'a tap on row {row} opens the Preset page of {name} (the file is read)')
    m.calls = []; tap_row(m, 1)
    expect(('window_open', 'm1plus_peqpage') in m.calls, 'a parsing file: the Preset page\'s window opens')
    m.calls = []; tap_row(m, O['PQ_ROWS'] + 2)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Cannot read this preset'] and ('window_open', 'm1plus_peqpage') not in m.calls, 'a file that does not parse: the message box, no page')
    m = libpage(files)
    m.calls = []; tap_row(m, 0)
    expect(('window_open', 'm1plus_autoeq') in m.calls, 'Download from AutoEq opens its window (Radio\'s search top, the field under the bar)')

    # back in front: the card is read again (a download, a delete)
    m = libpage(files[:2])
    expect([vis(m, f'pod_row{i}') for i in (1, 2)] == [1, 0] and vis(m, 'pod_sec1') == 1, 'one AutoEq file and one other')
    m.put(f'{EQ_DIR}/Alpha2.txt', stamped('oratory1990/over-ear/Alpha2'))
    del m.fs[f'{EQ_DIR}/alpha.txt']
    m.calls = []
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, count=1 << 30)
    expect([ptexts(m, 'pod_label', i) for i in (1, 2)] == [['Alpha2'], ['Beta Phones']] and vis(m, 'pod_row2') == 1 and vis(m, 'pod_sec1') == 0 and vis(m, f'pod_row{O["PQ_ROWS"] + 1}') == 0
           and tall(m, 1) == 'top' and tall(m, 2) == 'bot' and m.props[(m.widgets['pod_scrollview'], 'virtual_h')] == lib_vh(2, 0), 'back in front: the new file shows, the removed one and the empty On Card header are gone, pieces and height follow')
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30); m.calls = []
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(not [x for x in m.calls if x[0] == 'opendir'], 'after the destroy nothing runs')
    fn, c = m.bound[(m.widgets['pod_row1'], O['EVT_CLICK'])]
    m.calls = []; m.call(fn, a0=c, count=1 << 30)
    expect(not [x for x in m.calls if x[0] in ('window_open', 'open')], 'after the destroy a tap on a row opens nothing')
    # not our asset
    m = demo_machine()
    m.card_mounted = True; m.folder(EQ_DIR)
    for n in ('pod_row0', 'pod_row1', 'pod_label1'): m.widget(n)
    m.call(PSYMS['peqlib_open'], count=1 << 40)
    expect(not [b for b in m.bound if b[1] == O['EVT_CLICK']], 'a page missing rows binds nothing')

    # (3) Delete Preset
    def delete_page(state=None, flag=1, name='Sennheiser HD 600.txt'):
        m = ppage([(name, AUTOEQ), ('keep.txt', AUTOEQ)], name)
        m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag])); m.setword(pod.DATA['EQ_MODE'][0], 4)
        if state is not None: m.fs[STATE] = state
        m.calls = []
        return m
    path = f'{EQ_DIR}/Sennheiser HD 600.txt'
    playing = pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt')
    expect((m := delete_page(playing)).shown == 1 and m.props.get((m.widgets['pod_row31'], 'visible')) is None and (m.widgets['pod_row31'], O['EVT_CLICK']) in m.bound,
           'the Preset page binds the Delete Preset row (always shown: the payload never hides it)')
    m.confirm_yes = True
    tap_row(m, 31)
    seq = [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
    expect(('confirm', 'Delete Preset?', 1) in m.calls and ('unlink', path) in m.calls and path not in m.fs and f'{EQ_DIR}/keep.txt' in m.fs, 'Yes: the confirm asks "Delete Preset?", the file is unlinked, others stay')
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 0 and NAME_OF(m.fs[STATE]) == b'' and seq == [('write_int_config', 0, 'PLAYSET', 'EQFLAG'), ('set_equalizer_value', 4, 0)]
           and m.u.mem_read(pod.DATA['EQ_FLAG'][0], 1)[0] == 0, f'it was the playing preset: the record is Graphic EQ with an empty name, stock\'s Equalizer flag off and the gains sent ({seq})')
    expect(('window_close', m.window) in m.calls and ('navigator_back',) not in m.calls and not [c for c in m.calls if c[0] == 'toast'], 'then this page closes (window_close: the dialog may still be the top window), no message')
    m = delete_page(pack_state(1, pack_preset(AUTOEQ_BANDS), b'keep.txt'))
    m.confirm_yes = True; tap_row(m, 31)
    expect(('unlink', path) in m.calls and m.fs[STATE] == pack_state(1, pack_preset(AUTOEQ_BANDS), b'keep.txt') and not [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')] and ('window_close', m.window) in m.calls,
           'another preset plays: the file goes, the record and the Equalizer are untouched')
    m = delete_page(None)
    m.confirm_yes = True; tap_row(m, 31)
    expect(('unlink', path) in m.calls and STATE not in m.fs and not [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')], 'no record at all: the file goes and nothing else is written')
    m = delete_page(playing)
    tap_row(m, 31)
    expect(('confirm', 'Delete Preset?', 1) in m.calls and not [c for c in m.calls if c[0] in ('unlink', 'navigator_back', 'window_close', 'toast', 'write_int_config', 'set_equalizer_value')] and path in m.fs and m.fs[STATE] == playing,
           'No: nothing is deleted, written or closed; the page stays')
    m = delete_page(playing)
    m.confirm_yes = True; m.fail.add(('unlink', path)); tap_row(m, 31)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Failed To Delete Preset'] and path in m.fs and m.fs[STATE] == playing and not [c for c in m.calls if c[0] in ('navigator_back', 'window_close')]
           and not [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')], 'unlink fails: the message box, the file and the record stay, the page stays')
    # a destroyed page: a tap does nothing
    m = delete_page(playing)
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30); m.calls = []
    m.confirm_yes = True; tap_row(m, 31)
    expect(not [c for c in m.calls if c[0] in ('confirm', 'unlink')], 'after the destroy the Delete row does nothing')
    # an asset without the Delete row is not ours
    m = ppage([('Long.txt', PLONG)], 'Long.txt', drop=('pod_row31',))
    expect(m.shown == 1 and not [x for x in m.bound if x[1] in (O['EVT_BEFORE_PAINT'], O['EVT_DESTROY'])] and not m.bitmaps, 'a Preset page asset without pod_row31 binds and draws nothing')


# ---- Preset editing: the band page (patch/peqband.c) with its unsaved-changes dialog, and the Preset page's Save, Save As, Revert and Rename (patch/peqpage.c)
STAMPED = b'# AutoEq: oratory1990/over-ear/Sennheiser HD 600\n' + AUTOEQ
BALANCED = b'Preamp: -3 dB\nChannel: L\nPreamp: -2 dB\nChannel: all\nFilter 1: ON PK Fc 1000 Hz Gain 3 dB Q 1\nChannel: R\nFilter 2: ON PK Fc 2000 Hz Gain -4 dB Q 2\nChannel: all\nFilter 3: ON LSC Fc 100 Hz Gain 2 dB Q 0.7\n'
BAND_NAMES = 'pod_graph pod_gr_top pod_gr_bot pod_seg pod_hsl pod_scrollview label_title btn_bprev btn_bnext btn_return btn_backtoplayer pq_scrim pq_card pq_name pq_item0 pq_item1 pq_item2 pq_item3 bk_scrim bk_card bk_title bk_range bk_val bk_unit bk_caret bk_unitk bk_sign bk_dot bk_del bk_cancel bk_done'.split() + [f'bk_k{d}' for d in range(10)] + [f'pod_seg_l{k}' for k in range(3)] + [f'pod_hs_v{k}' for k in range(3)]
HD = 'Sennheiser HD 600.txt'
HD_PATH = f'{EQ_DIR}/{HD}'
TRK0 = 10 + 14   # the slider tracks' left end in the view (card x 10, track x 14)


def epage(files, name=HD, state=None, flag=1, bitmap_ok=False):
    """The Preset page of a file as peqpage_show opens it, with the band page's window ready (its own widgets by name) and no keyboard window (the test calls what the keyboard would)."""
    m = demo_machine()
    m.card_mounted = True
    m.bitmap_ok = bitmap_ok
    m.folder(EQ_DIR)
    for fn, data in files: m.put(f'{EQ_DIR}/{fn}', data)
    register_peqpage(m)
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag])); m.setword(pod.DATA['EQ_MODE'][0], 4)
    if state is not None: m.fs[STATE] = state
    m.windows['m1plus_keyboard'] = 0
    m.band_win = m.alloc(0x80)
    m.windows['m1plus_peqband'] = m.band_win
    m.bw = {}
    for n in BAND_NAMES:
        m.bw[n] = m.alloc(0x80)
        m.lookups[(m.band_win, n)] = m.bw[n]
    m.setword(m.bw['label_title'] + O['W_W'], 200)
    m.name = name
    m.shown = m.call(PSYMS['peqpage_show'], m.cstr(name), count=1 << 40)
    m.hist = list(m.calls)   # every call since the page opened (machine.call keeps the last one's only)
    orig = m.call
    def call(*a, **k):
        r = orig(*a, **k)
        m.hist.extend(m.calls)
        return r
    m.call = call
    return m


def fire(m, w, kind, *args, **kw):
    fn, c = m.bound[(w, O[kind])]
    return m.call(fn, a0=c, count=1 << 40, **kw) if not args else m.call(fn, a0=c, a1=args[0], count=1 << 40)


def pev(m, w, kind, x, y, t=0):
    e = m.alloc(0x40)
    m.setword(e + 8, t); m.setword(e + O['PE_X'], x); m.setword(e + O['PE_Y'], y)
    fn, c = m.bound[(w, O[kind])]
    return m.call(fn, a0=c, a1=e, count=1 << 40)


def hsaves(m): return len([c for c in m.hist if c[0] == 'rename' and c[2] == STATE])
def hsent(m): return len([c for c in m.hist if c[0] == 'set_equalizer_value'])
def hptexts(m, base, i): return [u8(c[2]) for c in m.hist if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[f'{base}{i}']]
def hptext(m, name): return [u8(c[2]) for c in m.hist if c[0] == 'widget_set_text_utf8' and c[1] == m.widgets[name]]
def rec_preset(m): return unpack_preset(m.fs[STATE][16:16 + 992])
def rec_mode(m): return struct.unpack_from('<i', m.fs[STATE], 8)[0]
def btext(m, name): return [u8(c[2]) for c in m.hist if c[0] == 'widget_set_text_utf8' and c[1] == m.bw[name]]
def toasts(m): return [c[1] for c in m.hist if c[0] == 'toast']
def shown_now(m, name): return m.props.get((m.widgets[name], 'visible'))
def band_win_open(m): return ('window_open', 'm1plus_peqband') in m.hist


def open_band(m, k):
    """A tap on the Preset page's band row k (1-based): the band page opens on it."""
    m.hist.clear()
    fire(m, m.widgets[f'pod_row{k}'], 'EVT_CLICK')


def ask(m, how='btn_return', band=1):
    """Leave the band page by Back (or Now Playing: how) with the edits as they are: opens the band page first when it is not up. The dialog is whatever the payload shows."""
    if (m.bw['btn_return'], O['EVT_CLICK']) not in m.bound: open_band(m, band)
    fire(m, m.bw[how], 'EVT_CLICK')


def dialog_up(m): return m.props.get((m.bw['pq_card'], 'visible')) == 1 and m.props.get((m.bw['pq_scrim'], 'visible')) == 1


def went_back(m): return ('navigator_back',) in m.hist


def drag_to(m, row, t, t0=1000, steps=(), release=True):
    """A drag on slider row `row` (0 frequency, 1 gain, 2 Q): down at track position t, through `steps` (position, time) and the release."""
    y = row * 50 + 38
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_DOWN', TRK0 + round(t * 272), y, t0)
    for tt, ms in steps: pev(m, m.bw['pod_hsl'], 'EVT_POINTER_MOVE', TRK0 + round(tt * 272), y, ms)
    if release: pev(m, m.bw['pod_hsl'], 'EVT_POINTER_UP', TRK0 + round((steps[-1][0] if steps else t) * 272), y, (steps[-1][1] if steps else t0) + 5)


def freq_of(t):
    f = 20 * 1000 ** t
    step = 0.1 if f < 100 else 1 if f < 1000 else 10 if f < 10000 else 100
    return min(max(int(f / step + 0.5) * step, 20), 20000)


def gain_of(t):
    g = (2 * t - 1) * 12 * 10
    return int(g + (-0.5 if g < 0 else 0.5)) / 10


def q_of(t): return min(max(int(0.1 * 100 ** t * 100 + 0.5) / 100, 0.1), 10)


def t_of_pos(x): return min(max((x - TRK0) / 272, 0), 1)


def edit_band_tests(ctx):
    expect = ctx.expect
    base = unpack_preset(pack_preset(AUTOEQ_BANDS, preamp=-6.2))
    # ---- the band page opens on its band, from the working preset
    m = epage([(HD, AUTOEQ)], bitmap_ok=True)
    expect(m.shown == 1 and not band_win_open(m), 'the Preset page of an unedited preset: no band page yet')
    expect([(w, 'EVT_CLICK') in [(k[0], 'EVT_CLICK') for k in m.bound if k[1] == O['EVT_CLICK']] for w in (m.widgets['pod_row1'], m.widgets['pod_row4'])] == [True, True] and (m.widgets['pod_row5'], O['EVT_CLICK']) not in m.bound,
           'a click handler on each band row (and not on the empty ones)')
    open_band(m, 2)
    expect(band_win_open(m) and btext(m, 'label_title') == ['Band 2'] and btext(m, 'pod_hs_v0') == ['2 kHz'] and btext(m, 'pod_hs_v1') == ['−3.1 dB'] and btext(m, 'pod_hs_v2') == ['1.41'],
           f'the band page of band 2 (2 kHz, -3.1 dB, Q 1.41): title "Band 2" and the three values ({btext(m, "label_title")}, {btext(m, "pod_hs_v0")}, {btext(m, "pod_hs_v1")}, {btext(m, "pod_hs_v2")})')
    cols = [m.props.get((m.bw[f'pod_seg_l{k}'], 'style:normal:text_color')) for k in range(3)]
    expect(cols == ['#000000', '#FFFFFF', '#FFFFFF'], f'the Peak segment is black on its pill, the others white ({cols})')
    bms = [(w, h) for _, (d, w, h) in m.bitmaps.items()]
    expect(sorted(bms) == sorted([(300, 170), (300, 170), (300, 40), (94, 34), (300, 150), (272, 4), (22, 22), (16, 16)]) and not [c for c in m.hist if c[0] == 'bitmap_create_ex' and (c[1], c[2]) == (300, 170)][2:], f'the page makes the Preset page\'s graph, its own graph and the control, card, fill, thumb and ring bitmaps ({bms})')
    expect(m.fs.get(STATE) is None and rec_mode.__name__ and not [c for c in m.hist if c[0] == 'set_equalizer_value'], 'opening the page saves and sends nothing')
    # painting: the graph with its ring, the control, the card
    canvas, ev = m.alloc(0x100), m.alloc(0x40)
    m.setword(ev + O['EVENT_PAINT_CANVAS'], canvas)
    m.blits.clear(); fire(m, m.bw['pod_graph'], 'EVT_BEFORE_PAINT', ev)
    ring = [b for b in m.blits if b[1][2:] == (16, 16)]
    expect(len(m.blits) == 2 and len(ring) == 1 and m.blits[0][2] == (10, 0, 300, 170), f'the graph view paints the card and, over it, the ring ({m.blits})')
    cx, cy = ring[0][2][0] + 8 - 10 - G.PX0, ring[0][2][1] + 8
    db, rng = G.curve(unpack_preset(pack_preset(AUTOEQ_BANDS, preamp=-6.2))['bands'])
    expect(abs(cx - (83 * math.log10(2000 / 20) - 0.5)) <= 1 and abs(cy - (G.PY0 + G.PH / 2 + 0.5 - db[cx] * (G.PH / 2) / rng)) < 1.5, f'the ring is on the curve at 2 kHz (column {cx}, y {cy})')
    m.blits.clear(); fire(m, m.bw['pod_seg'], 'EVT_BEFORE_PAINT', ev)
    expect(m.blits[0][2:] == ((10, 10, 300, 40)) or [b[2] for b in m.blits] == [(10, 10, 300, 40), (13, 13, 94, 34)], f'the control: the container, then the Peak pill at the first segment ({[b[2] for b in m.blits]})')
    m.blits.clear(); fire(m, m.bw['pod_hsl'], 'EVT_BEFORE_PAINT', ev)
    t_f, t_g, t_q = math.log10(2000 / 20) / 3, (-3.1 + 12) / 24, math.log10(1.41 / 0.1) / 2
    px = lambda t: round(t * 272)
    want = [(10, 0, 300, 150)] + [d for r, t in enumerate((t_f, t_g, t_q)) for d in ((24, r * 50 + 36, px(t), 4), (24 + px(t) - 11, r * 50 + 38 - 11, 22, 22))]
    expect([b[2] for b in m.blits] == want, f'the card, then for each row the fill to the thumb and the round thumb ({[b[2] for b in m.blits]})')
    expect([b[1] for b in m.blits][1] == (0, 0, px(t_f), 4), 'the fill is the first px of the one white track bitmap')

    # ---- a drag on the Gain slider plays at once and is saved at most every 150 ms, and once more at the release
    m.hist.clear()
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_DOWN', TRK0 + px(0.5), 88, 1000)
    expect(('widget_grab', m.window, m.bw['pod_hsl']) in m.hist or ('widget_grab',) == m.hist and False or any(c[0] == 'widget_grab' and c[2] == m.bw['pod_hsl'] for c in m.hist), 'a touch on a track grabs the touch')
    expect(rec_mode(m) == 1 and NAME_OF(m.fs[STATE]) == HD.encode() and abs(rec_preset(m)['bands'][1][3] - gain_of(0.5)) < 1e-9 and rec_preset(m)['bands'][0] == base['bands'][0], f'the first touch sets the gain ({gain_of(0.5)}) and plays it: the record is the preset of this file with that band changed')
    n_save = hsaves(m)
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_MOVE', TRK0 + px(0.55), 88, 1040)
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_MOVE', TRK0 + px(0.6), 88, 1090)
    expect(hsaves(m) == n_save and abs(rec_preset(m)['bands'][1][3] - gain_of(0.5)) < 1e-9, 'moves within 150 ms are not saved')
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_MOVE', TRK0 + px(0.7), 88, 1200)
    expect(hsaves(m) == n_save + 1 and abs(rec_preset(m)['bands'][1][3] - gain_of(t_of_pos(TRK0 + px(0.7)))) < 1e-9, f'150 ms later the next step is saved ({rec_preset(m)["bands"][1][3]})')
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_MOVE', TRK0 + px(0.8), 88, 1250)
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_UP', TRK0 + px(0.8), 88, 1260)
    expect(hsaves(m) == n_save + 2 and abs(rec_preset(m)['bands'][1][3] - gain_of(t_of_pos(TRK0 + px(0.8)))) < 1e-9 and ('widget_ungrab', m.window, m.bw['pod_hsl']) in [(c[0], m.window, c[2]) for c in m.hist if c[0] == 'widget_ungrab'],
           f'the release saves the last step and lets go of the touch ({rec_preset(m)["bands"][1][3]})')
    expect(btext(m, 'pod_hs_v1')[-1] == G.gain_text(gain_of(t_of_pos(TRK0 + px(0.8)))) and hsent(m) >= 3 and [c for c in m.hist if c[0] == 'set_equalizer_value'][0][2] != 7, f'the value label follows ({btext(m, "pod_hs_v1")[-1]}) and the player is told each time')
    # the engine plays the edited band: the model of the preset with that gain
    g = gain_of(t_of_pos(TRK0 + px(0.8)))
    p = Player({STATE: m.fs[STATE]}); af = p.open(); p.reinit(af, 44100)
    x = tone(1024, 2, 44100)
    _, y = p.play(af, x, 44100)
    edited_bands = [AUTOEQ_BANDS[0], (1, 0, 2000, g, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]]
    expect(near(y, model(edited_bands, 44100, 2, x, 10 ** (-6.2 / 20))), 'the player plays the record the edit wrote: the model of the preset with the edited band (and its Preamp)')
    # frequency and Q sliders
    m.hist.clear()
    drag_to(m, 0, 0.7)
    expect(abs(rec_preset(m)['bands'][1][2] - freq_of(t_of_pos(TRK0 + px(0.7)))) < 1e-9 and btext(m, 'pod_hs_v0')[-1] == G.freq_text(rec_preset(m)['bands'][1][2]), f'the Frequency slider: three significant figures ({rec_preset(m)["bands"][1][2]} Hz)')
    drag_to(m, 2, 0.5)
    expect(abs(rec_preset(m)['bands'][1][4] - q_of(t_of_pos(TRK0 + px(0.5)))) < 1e-9 and btext(m, 'pod_hs_v2')[-1] == '1', f'the Q slider: hundredths ({rec_preset(m)["bands"][1][4]})')
    drag_to(m, 1, 0.9, steps=[(1.5, 1100)])   # past the track's right end
    hi_g = rec_preset(m)['bands'][1][3]
    drag_to(m, 1, 0.1, steps=[(-0.5, 1100)])
    expect((hi_g, rec_preset(m)['bands'][1][3]) == (12.0, -12.0), f'a drag past either end clamps to the slider\'s range, +-12 dB ({hi_g})')
    # the extremes of the frequency: 20 Hz and 20 kHz
    drag_to(m, 0, 0.0); lo = rec_preset(m)['bands'][1][2]
    drag_to(m, 0, 1.0); hi = rec_preset(m)['bands'][1][2]
    expect((lo, hi) == (20.0, 20000.0), f'the track\'s ends are 20 Hz and 20 kHz ({lo}, {hi})')

    # ---- a tap on a value opens the number keypad (never the QWERTY keyboard)
    def tap_row(r):
        pev(m, m.bw['pod_hsl'], 'EVT_POINTER_DOWN', 100, r * 50 + 10, 3000); pev(m, m.bw['pod_hsl'], 'EVT_POINTER_UP', 100 + 3, r * 50 + 12, 3040)

    def click(name): fire(m, m.bw[name], 'EVT_CLICK')

    def tap_keys(text):
        for ch in text: click({'.': 'bk_dot', 'D': 'bk_del', 'S': 'bk_sign', 'U': 'bk_unitk'}.get(ch) or f'bk_k{ch}')

    def sheet_up(): return m.props.get((m.bw['bk_card'], 'visible')) == 1 and m.props.get((m.bw['bk_scrim'], 'visible')) == 1 and m.props.get((m.bw['bk_card'], 'sensitive')) == 1 and m.props.get((m.bw['bk_scrim'], 'sensitive')) == 1

    def shown_val(): return btext(m, 'bk_val')[-1]

    def band_val(field): return rec_preset(m)['bands'][1][field]

    def entry(r, keys, done=True):
        """Tap row r, press `keys` (digits, '.', D backspace, S sign, U unit), then Done (or not)."""
        tap_row(r); tap_keys(keys)
        if done: click('bk_done')

    m.hist.clear()
    expect(not sheet_up() and (m.bw['bk_scrim'], O['EVT_CLICK']) in m.bound, 'the keypad sheet is closed (hidden and insensitive) until a value is tapped')
    tap_row(0)
    expect(sheet_up() and not [c for c in m.hist if c[0] == 'widget_grab'], 'a tap on a row\'s name or value (its top 28 px) opens the keypad sheet with its dim, no drag')
    expect(btext(m, 'bk_title')[-1] == 'Frequency' and btext(m, 'bk_range')[-1] == 'Range 20 Hz \u2013 20 kHz' and shown_val() == '20' and btext(m, 'bk_unit')[-1] == 'kHz' and btext(m, 'bk_unitk')[-1] == 'kHz',
           f'Frequency 20000 Hz opens as 20 kHz with its range line ({btext(m, "bk_title")[-1]}, {btext(m, "bk_range")[-1]}, {shown_val()}, {btext(m, "bk_unit")[-1]})')
    expect(m.props.get((m.bw['bk_unitk'], 'visible')) == 1 and m.props.get((m.bw['bk_sign'], 'sensitive')) == 0 and m.props.get((m.bw['bk_sign'], 'style:normal:text_color')) == '#5A5A5E',
           'Frequency: the Hz / kHz key is shown, the minus key dimmed and insensitive')
    unit_at = [c for c in m.hist if c[0] == 'widget_move' and c[1] == m.bw['bk_unit']][-1]
    expect(unit_at[2:] == (10 + 300 - 14 - 34, 80), f'the kHz unit sits at the field\'s right ({unit_at})')
    expect(('window_open', 'm1plus_keyboard') not in m.hist, 'the keypad is not the keyboard page')
    # Cancel, the scrim: nothing changes
    n = hsaves(m); before = band_val(2)
    tap_keys('55'); click('bk_cancel')
    expect(not sheet_up() and band_val(2) == before and hsaves(m) == n, 'Cancel closes the sheet and changes nothing')
    tap_row(0); tap_keys('9'); click('bk_scrim')
    expect(not sheet_up() and band_val(2) == before and hsaves(m) == n, 'a tap on the dim closes the sheet and changes nothing')
    tap_row(0)
    expect(shown_val() == '20', 'reopened: the value as it is, not the cancelled text')
    # typing, backspace, Done
    tap_keys('DD')
    expect(shown_val() == '', 'backspace removes the characters (the number is empty)')
    tap_keys('2.6')
    expect(shown_val() == '2.6', f'typed 2.6 ({shown_val()})')
    tap_keys('D')
    expect(shown_val() == '2.', 'backspace takes the last character')
    tap_keys('6')
    sent = hsent(m)
    click('bk_done')
    expect(not sheet_up() and abs(band_val(2) - 2600) < 1e-9 and hsent(m) == sent + 1 and rec_mode(m) == 1 and btext(m, 'pod_hs_v0')[-1] == '2.6 kHz',
           f'Done applies 2.6 kHz = 2600 Hz, saves and plays at once ({band_val(2)}, {btext(m, "pod_hs_v0")[-1]})')
    # the unit key: the number reads in the other unit
    tap_row(0)
    expect(shown_val() == '2.6' and btext(m, 'bk_unit')[-1] == 'kHz', 'reopened in kHz')
    tap_keys('U')
    expect(btext(m, 'bk_unit')[-1] == 'Hz' and btext(m, 'bk_unitk')[-1] == 'Hz' and shown_val() == '2.6', 'the unit key switches the unit to Hz, the number stays')
    tap_keys('DDDD1300'); click('bk_done')
    expect(abs(band_val(2) - 1300) < 1e-9, f'1300 Hz ({band_val(2)})')
    tap_row(0)
    expect(btext(m, 'bk_unit')[-1] == 'kHz' and shown_val() == '1.3', f'1300 Hz opens as 1.3 kHz ({shown_val()})')
    tap_keys('DDDU105'); click('bk_done')
    expect(abs(band_val(2) - 105) < 1e-9, f'105 Hz ({band_val(2)})')
    tap_row(0)
    expect(btext(m, 'bk_unit')[-1] == 'Hz' and shown_val() == '105', f'a value under 1000 Hz opens in Hz ({shown_val()})')
    click('bk_cancel')
    # the range: clamped as the engine takes
    tap_row(0); tap_keys('DDDDU'); tap_keys('50'); click('bk_done')
    expect(band_val(2) == 20000.0, f'50 kHz is clamped to 20 kHz ({band_val(2)})')
    entry(0, 'DDDDDU10')
    expect(band_val(2) == 20.0, f'10 Hz is clamped to 20 Hz ({band_val(2)})')
    # Gain: the sign key, the range line, no unit key
    tap_row(1)
    expect(btext(m, 'bk_title')[-1] == 'Gain' and btext(m, 'bk_range')[-1] == 'Range \u221224 \u2013 +24 dB' and btext(m, 'bk_unit')[-1] == 'dB' and m.props.get((m.bw['bk_unitk'], 'visible')) == 0 and m.props.get((m.bw['bk_sign'], 'sensitive')) == 1
           and m.props.get((m.bw['bk_sign'], 'style:normal:text_color')) == '#FFFFFF', f'Gain: the engine\'s +-24 dB range, dB after the number, minus key on, no unit key ({btext(m, "bk_range")[-1]})')
    expect(shown_val() == '\u221212', f'a gain of -12 dB opens with its sign ({shown_val()})')
    tap_keys('S'); expect(shown_val() == '12', 'the minus key toggles the sign off')
    tap_keys('S'); expect(shown_val() == '\u221212', 'and on')
    tap_keys('DDD'); expect(shown_val() == '', 'backspace past the digits drops the sign')
    tap_keys('4.1S'); expect(shown_val() == '\u22124.1', 'sign after digits')
    click('bk_done')
    expect(abs(band_val(3) + 4.1) < 1e-9 and btext(m, 'pod_hs_v1')[-1] == '\u22124.1 dB', f'Done: -4.1 dB ({band_val(3)})')
    entry(1, 'DDD'); expect(not sheet_up() and abs(band_val(3) + 4.1) < 1e-9, 'a sign alone is no number: nothing changes')
    tap_row(1); tap_keys('DDDDD30'); click('bk_done'); expect(band_val(3) == 24.0, f'+30 dB is clamped to +24 ({band_val(3)})')
    tap_row(1); tap_keys('DDDDS30'); click('bk_done'); expect(band_val(3) == -24.0, f'-30 dB is clamped to -24 ({band_val(3)})')
    tap_row(1); tap_keys('DDDDDDD'); tap_keys('2.5S'); click('bk_done'); expect(band_val(3) == -2.5, f'-2.5 dB ({band_val(3)})')
    # Q: range, no unit, no sign
    tap_row(2)
    expect(btext(m, 'bk_title')[-1] == 'Q' and btext(m, 'bk_range')[-1] == 'Range 0.1 \u2013 10' and btext(m, 'bk_unit')[-1] == '' and m.props.get((m.bw['bk_unitk'], 'visible')) == 0 and m.props.get((m.bw['bk_sign'], 'sensitive')) == 0,
           'Q: its range, no unit, no unit key, minus key dimmed')
    tap_keys('S'); expect(shown_val() == '1', 'the minus key does nothing on Q')
    click('bk_cancel')
    for keys, want in (('DD99', 10.0), ('DDD0.01', 0.1), ('DDDDDD3.25', 3.25), ('DDDDDD.5', 0.5)):
        tap_row(2); tap_keys(keys); click('bk_done')
        expect(abs(band_val(4) - want) < 1e-9, f'Q typed {keys}: {band_val(4)} (clamped to 0.1 .. 10)')
    # the number's rules: one point, no leading zero, a point first makes 0., at most 7 characters, a trailing point is dropped
    tap_row(2); tap_keys('DDDD0'); tap_keys('0'); tap_keys('7'); expect(shown_val() == '7', f'no leading zero ({shown_val()})')
    tap_keys('D.'); expect(shown_val() == '0.', f'a point first reads 0. ({shown_val()})')
    tap_keys('.5.5'); expect(shown_val() == '0.55', f'only one point ({shown_val()})')
    tap_keys('1111111'); expect(len(shown_val()) == 7, f'at most 7 characters ({shown_val()})')
    click('bk_cancel')
    tap_row(2); tap_keys('DDDDD5.'); click('bk_done'); expect(abs(band_val(4) - 5.0) < 1e-9, f'a trailing point is dropped ({band_val(4)})')
    mem = band_val(4); n = hsaves(m)
    entry(2, 'DDDDDDD'); expect(not sheet_up() and band_val(4) == mem and hsaves(m) == n, 'Done with no number changes nothing')
    entry(2, 'DDDDDDD.'); expect(band_val(4) == 0.1, f'a point alone reads 0, clamped to 0.1 ({band_val(4)})')
    expect(('window_open', 'm1plus_keyboard') not in m.hist, 'value entry never opened the QWERTY keyboard')
    # Done plays: the record is the typed value and the player is told
    sent = hsent(m)
    tap_row(0); tap_keys('DDDD'); tap_keys('2000'); click('bk_done')
    expect(hsent(m) == sent + 1 and rec_mode(m) == 1 and abs(band_val(2) - 2000) < 1e-9, f'Done plays the typed value ({band_val(2)})')
    # a press that moves too far is no tap
    m.hist.clear()
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_DOWN', 100, 10, 4000); pev(m, m.bw['pod_hsl'], 'EVT_POINTER_UP', 100, 40, 4050)
    expect(('window_open', 'm1plus_keyboard') not in m.hist, 'a press that moves 30 px is a scroll, not a tap')
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_DOWN', 100, 10, 4100); pev(m, m.bw['pod_hsl'], 'EVT_POINTER_ABORT', 100, 10, 4110)
    pev(m, m.bw['pod_hsl'], 'EVT_POINTER_UP', 100, 10, 4120)
    expect(('window_open', 'm1plus_keyboard') not in m.hist, 'an abort forgets the press')
    # the type control
    m.hist.clear()
    pev(m, m.bw['pod_seg'], 'EVT_POINTER_DOWN', 10 + 250, 30, 5000); pev(m, m.bw['pod_seg'], 'EVT_POINTER_UP', 10 + 250, 30, 5040)
    expect(rec_preset(m)['bands'][1][1] == 2 and m.props.get((m.bw['pod_seg_l2'], 'style:normal:text_color')) == '#000000' and m.props.get((m.bw['pod_seg_l0'], 'style:normal:text_color')) == '#FFFFFF',
           'a tap on High shelf: the band is a high shelf, plays, and the label colours follow')
    pev(m, m.bw['pod_seg'], 'EVT_POINTER_DOWN', 10 + 150, 30, 5100); pev(m, m.bw['pod_seg'], 'EVT_POINTER_UP', 10 + 150, 30, 5140)
    expect(rec_preset(m)['bands'][1][1] == 1, 'Low shelf')
    n = hsaves(m)
    pev(m, m.bw['pod_seg'], 'EVT_POINTER_DOWN', 10 + 150, 30, 5200); pev(m, m.bw['pod_seg'], 'EVT_POINTER_UP', 10 + 150, 30, 5240)
    expect(hsaves(m) == n, 'the segment it is on: nothing saved')
    pev(m, m.bw['pod_seg'], 'EVT_POINTER_DOWN', 10 + 150, 30, 5300); pev(m, m.bw['pod_seg'], 'EVT_POINTER_UP', 10 + 20, 30, 5340)
    expect(hsaves(m) == n, 'a press that ends 130 px away is no tap')
    # previous / next
    m.hist.clear()
    fire(m, m.bw['btn_bnext'], 'EVT_CLICK')
    expect(btext(m, 'label_title')[-1] == 'Band 3' and btext(m, 'pod_hs_v0')[-1] == '10 kHz', 'Next: Band 3, its values')
    fire(m, m.bw['btn_bnext'], 'EVT_CLICK'); fire(m, m.bw['btn_bnext'], 'EVT_CLICK')
    expect(btext(m, 'label_title')[-1] == 'Band 1' and btext(m, 'pod_hs_v0')[-1] == '105 Hz', 'Next past the last band: Band 1')
    fire(m, m.bw['btn_bprev'], 'EVT_CLICK')
    expect(btext(m, 'label_title')[-1] == 'Band 4', 'Previous from the first: the last band')
    # back to the Preset page: the rows
    m.hist.clear()
    fire(m, m.window, 'EVT_WINDOW_TO_FG')
    got = hptexts(m, 'pod_value', 2)
    expect(got == [G.gain_text(rec_preset(m)['bands'][1][3])], f'back on the Preset page: the edited band\'s row ({got})')
    # destroy
    fn, c = m.bound[(m.band_win, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(len([c for c in m.hist if c[0] == 'bitmap_destroy']) == 7 and len(m.bitmaps) == 1, f'the band page\'s seven bitmaps (its graph too) go with it; the Preset page\'s stays ({len(m.bitmaps)})')


def edit_select_tests(ctx):
    expect = ctx.expect
    # ---- an edit of a preset that is not playing selects it; the Equalizer is switched on as a tap on a preset does
    m = epage([(HD, AUTOEQ), ('keep.txt', AUTOEQ)], state=pack_state(1, pack_preset(AUTOEQ_BANDS), b'keep.txt'), flag=0)
    open_band(m, 1)
    m.hist.clear()
    drag_to(m, 1, 0.9)
    seq = [c for c in m.hist if c[0] in ('write_int_config', 'set_equalizer_value')]
    expect(NAME_OF(m.fs[STATE]) == HD.encode() and rec_mode(m) == 1 and seq[0] == ('write_int_config', 1, 'PLAYSET', 'EQFLAG'), f'a band edit makes this file the preset that plays and switches stock\'s Equalizer on ({seq[:2]})')
    # a preset that plays already: the Preset page opens on what plays (the record), edited
    state = pack_state(1, pack_preset([AUTOEQ_BANDS[0], (1, 0, 2000, 4.0, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]], preamp=-6.2), HD.encode())
    m = epage([(HD, AUTOEQ)], state=state)
    expect(hptexts(m, 'pod_value', 2) == ['+4.0 dB'] and hptexts(m, 'pod_value', 1) == ['+5.5 dB'], f'a preset that plays edited opens on the record\'s bands ({hptexts(m, "pod_value", 2)})')
    ask(m)
    expect(dialog_up(m) and not went_back(m), 'and it is edited: Back from its band page asks')
    m = epage([(HD, AUTOEQ)], state=pack_state(1, pack_preset(AUTOEQ_BANDS, preamp=-6.2), HD.encode()))
    ask(m)
    expect(not dialog_up(m) and went_back(m), 'the same preset as its file: not edited, Back goes at once (the OFF filter the record keeps is no difference)')
    m = epage([(HD, AUTOEQ), ('keep.txt', AUTOEQ)], state=pack_state(1, pack_preset([(1, 0, 1000, 9.0, 1.0)]), b'keep.txt'))
    shown_gain = hptexts(m, 'pod_value', 1)
    ask(m)
    expect(not dialog_up(m) and went_back(m) and shown_gain == ['+5.5 dB'], 'another preset plays: this page shows its file, not edited')


def edit_dialog_tests(ctx):
    expect = ctx.expect
    m0 = demo_machine()
    state = pack_state(1, pack_preset([AUTOEQ_BANDS[0], (1, 0, 2000, 4.0, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]], preamp=-6.2), HD.encode())
    # ---- the unsaved-changes dialog: Back and Now Playing ask, Previous / Next do not
    m = epage([(HD, AUTOEQ)], state=state)
    open_band(m, 2)
    fire(m, m.bw['btn_bnext'], 'EVT_CLICK'); fire(m, m.bw['btn_bprev'], 'EVT_CLICK')
    expect(not dialog_up(m) and not went_back(m), 'Previous / Next inside the editing session never ask')
    m.hist.clear()
    fire(m, m.bw['btn_return'], 'EVT_CLICK')
    expect(dialog_up(m) and btext(m, 'pq_name') == ['Sennheiser HD 600'] and not went_back(m) and (m.bw['pq_card'], 1) in [(c[1], c[2]) for c in m.hist if c[0] == 'widget_set_sensitive'],
           f'Back with edits not saved: the dialog shows (shown and sensitive) with the preset\'s name, the page stays ({btext(m, "pq_name")})')
    fire(m, m.bw['pq_item3'], 'EVT_CLICK')
    expect(not dialog_up(m) and not went_back(m) and m.fs[HD_PATH] == AUTOEQ, 'Cancel closes it: the page stays, nothing changes')
    fire(m, m.bw['btn_return'], 'EVT_CLICK'); fire(m, m.bw['pq_scrim'], 'EVT_CLICK')
    expect(not dialog_up(m) and not went_back(m), 'a tap on the dim is Cancel')
    m.hist.clear()
    fire(m, m.bw['btn_backtoplayer'], 'EVT_CLICK')
    expect(dialog_up(m) and not [c for c in m.hist if c[0] in ('navigator_back', 'stock_backtoplayer_trampoline')], 'Now Playing with edits not saved asks too')
    fire(m, m.bw['pq_item3'], 'EVT_CLICK')
    m = epage([(HD, AUTOEQ)])
    ask(m)
    expect(not dialog_up(m) and went_back(m), 'Back with nothing to save goes at once')
    # a drag in progress is ended (its last step saved to the record) before the dialog asks
    m = epage([(HD, AUTOEQ)])
    open_band(m, 2)
    drag_to(m, 1, 0.9)
    fire(m, m.bw['btn_return'], 'EVT_CLICK')
    expect(dialog_up(m), 'edits made in this session ask as well')
    # Save: the file is rewritten atomically, then the page goes back
    m = epage([(HD, AUTOEQ)], state=state)
    ask(m)
    m.hist.clear()
    fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(not dialog_up(m) and went_back(m), 'Save closes the dialog and goes back')
    text = m.fs[HD_PATH].decode()
    expect(f'{EQ_DIR}/.save.tmp' not in m.fs and ('fsync', f'{EQ_DIR}/.save.tmp') in m.hist and ('rename', f'{EQ_DIR}/.save.tmp', HD_PATH) in m.hist
           and [c[0] for c in m.hist if c[0] in ('fsync', 'rename') and f'{EQ_DIR}/.save.tmp' in c[1:]] == ['fsync', 'rename'], 'Save: written to a temp file, fsynced, then renamed over the file (no temp left)')
    expect(text == 'Preamp: -6.2 dB\nFilter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.7\nFilter 2: ON PK Fc 2000 Hz Gain 4 dB Q 1.41\nFilter 3: ON HSC Fc 10000 Hz Gain 2 dB Q 0.7\nFilter 4: ON PK Fc 140 Hz Gain -1.5 dB Q 0.5\n', f'the file: the preamp, then the bands in their order as PK / LSC / HSC with Fc, Gain and Q ({text!r})')
    ok, back, _ = parse(m0, m.fs[HD_PATH])
    expect(ok == 1 and back['bands'] == [(1, 1, 105.0, 5.5, 0.7), (1, 0, 2000.0, 4.0, 1.41), (1, 2, 10000.0, 2.0, 0.7), (1, 0, 140.0, -1.5, 0.5)] and back['preamp'] == -6.2 and back['automatic'] == 2 and m0.skipped == 0, 'the payload\'s parser reads the saved file back as the same bands and preamp, nothing skipped')
    expect(rec_preset(m)['bands'][:4] == [tuple(b) for b in back['bands']] and NAME_OF(m.fs[STATE]) == HD.encode() and not toasts(m), 'the record plays the file\'s own preset, no message')
    # the page is not edited when opened again
    m2 = epage([(HD, m.fs[HD_PATH])], state=m.fs[STATE])
    ask(m2)
    expect(not dialog_up(m2) and went_back(m2), 'the saved preset opens as not edited')

    # Save marks an AutoEq stamp as edited (a second Save keeps the mark); an Auto preamp stays Auto (no Preamp line); a failing rename leaves the file
    no_pre = b'# AutoEq: x/y/z\nFilter 1: ON PK Fc 1000 Hz Gain 6 dB Q 1\nFilter 2: ON LSC Fc 100 Hz Gain 3 dB Q 0.7\n'
    st2 = pack_state(1, pack_preset([(1, 0, 1000, 5.0, 1.0), (1, 1, 100, 3.0, 0.7)], preamp=0.0, automatic=1), b'a.txt')
    m = epage([('a.txt', no_pre)], 'a.txt', state=st2)
    ask(m); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(m.fs[f'{EQ_DIR}/a.txt'].decode() == '# AutoEq edited: x/y/z\nFilter 1: ON PK Fc 1000 Hz Gain 5 dB Q 1\nFilter 2: ON LSC Fc 100 Hz Gain 3 dB Q 0.7\n', f'the AutoEq stamp becomes the edited marker; a preset with no Preamp line gets none ({m.fs[f"{EQ_DIR}/a.txt"]!r})')
    m = epage([(HD, AUTOEQ)], state=state)
    m.fail.add(('rename', HD_PATH)); ask(m); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(toasts(m) == ['Not saved'] and m.fs[HD_PATH] == AUTOEQ and f'{EQ_DIR}/.save.tmp' not in m.fs and ('unlink', f'{EQ_DIR}/.save.tmp') in m.hist and not went_back(m) and not dialog_up(m), f'a rename that fails: "Not saved", the file as it was, no temp file, the page stays ({toasts(m)}, {m.fs.get(HD_PATH)!r:.30}, {sorted(m.fs)}, {[c for c in m.hist if c[0] in ("unlink", "rename")]})')
    ask(m)
    expect(dialog_up(m), 'and it is still edited: Back asks again')
    m = epage([(HD, AUTOEQ)], state=state)
    m.fail.add(('fsync', f'{EQ_DIR}/.save.tmp')); ask(m); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(toasts(m) == ['Not saved'] and m.fs[HD_PATH] == AUTOEQ and f'{EQ_DIR}/.save.tmp' not in m.fs, 'an fsync that fails: nothing replaced')
    # Save with the Equalizer off does not switch it on
    m = epage([(HD, AUTOEQ)], state=state, flag=0)
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(m.fs[HD_PATH] != AUTOEQ and not [c for c in m.hist if c[0] in ('write_int_config', 'set_equalizer_value')], 'Save with stock\'s Equalizer off writes the file and the record, and does not switch it on')


def edit_revert_tests(ctx):
    expect = ctx.expect
    state = pack_state(1, pack_preset([AUTOEQ_BANDS[0], (1, 0, 2000, 4.0, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]], preamp=-6.2), HD.encode())
    # ---- Revert
    m = epage([(HD, AUTOEQ)], state=state)
    ask(m); m.hist.clear()
    fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(m.fs[HD_PATH] == AUTOEQ and rec_preset(m)['bands'][1][3] == -3.1 and hptexts(m, 'pod_value', 2)[-1] == '−3.1 dB' and hsent(m) == 1 and rec_mode(m) == 1 and went_back(m) and not dialog_up(m),
           "Don't Save: the file is untouched, its own bands play again, the rows follow, the player is told, the page goes back")
    # Revert of a file that no longer parses
    m = epage([(HD, AUTOEQ)], state=state)
    ask(m); m.fs[HD_PATH] = b'garbage'; m.hist.clear()
    fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(toasts(m) == ['Cannot read this preset'] and not went_back(m) and not dialog_up(m), 'a file that no longer parses: the message, the page stays')

    # Revert whose record write fails: "Not saved", the page stays with the edit unsaved (the dialog asks again), nothing is reported as discarded
    m = epage([(HD, AUTOEQ)], state=state)
    ask(m); m.fail.add(('rename', STATE)); m.hist.clear()
    fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(toasts(m) == ['Not saved'] and not went_back(m) and not dialog_up(m) and m.fs[STATE] == state, f"Don't Save with a failing record write: the message, the page stays, the record is as it was ({toasts(m)})")
    m.hist.clear(); ask(m)
    expect(dialog_up(m) and not went_back(m), "after a failed Don't Save the edit is still unsaved: Back asks again")


def edit_saveas_tests(ctx):
    expect = ctx.expect
    m0 = demo_machine()
    state = pack_state(1, pack_preset([AUTOEQ_BANDS[0], (1, 0, 2000, 4.0, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]], preamp=-6.2), HD.encode())
    # ---- Save As
    m = epage([(HD, AUTOEQ), ('Other.txt', AUTOEQ)], state=state)
    m.hist.clear()
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item1'], 'EVT_CLICK')
    kb = [c for c in m.hist if c == ('window_open', 'm1plus_keyboard')]
    expect(kb and not dialog_up(m) and not went_back(m), 'Save As New closes the dialog and opens the name entry; the page waits')
    fire(m, m.band_win, 'EVT_WINDOW_TO_FG')
    expect(not went_back(m), 'the name entry closed without a name: the page stays')
    ask(m); fire(m, m.bw['pq_item1'], 'EVT_CLICK')
    m.hist.clear()
    m.call(PSYMS['peqpage_named'], m.cstr('  My: Copy?.txt. '), count=1 << 40)
    new = f'{EQ_DIR}/My- Copy-.txt'
    ok, back, _ = parse(m0, m.fs.get(new, b''))
    expect(ok == 1 and back['bands'][1] == (1, 0, 2000.0, 4.0, 1.41) and m.fs[HD_PATH] == AUTOEQ and not toasts(m), f'Save As: a new file named as typed with the characters a card cannot hold made "-", the ".txt" typed dropped, the ends trimmed; the original is as it was ({[k for k in m.fs if k.startswith(EQ_DIR)]})')
    expect(NAME_OF(m.fs[STATE]) == b'My- Copy-.txt' and hptext(m, 'label_title')[-1] == 'My- Copy-' and f'{EQ_DIR}/.save.tmp' not in m.fs, 'the edited preset plays as the new file, the title is its name')
    m.hist.clear(); fire(m, m.band_win, 'EVT_WINDOW_TO_FG')
    expect(went_back(m), 'back from the name entry with the new file written: the page goes back (nothing is left unsaved)')
    # the new name is the file now: a Save writes it, not the original
    m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('Other'), count=1 << 40)
    expect(toasts(m) == ['Name already in use'] and m.fs[f'{EQ_DIR}/Other.txt'] == AUTOEQ, 'a name that exists is refused: "Name already in use", nothing written')
    m = epage([(HD, AUTOEQ), ('Other.txt', AUTOEQ)], state=state)
    m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('   '), count=1 << 40); m.call(PSYMS['peqpage_named'], m.cstr('.txt'), count=1 << 40); m.call(PSYMS['peqpage_named'], m.cstr(''), count=1 << 40)
    expect(not toasts(m) and sorted(k for k in m.fs if k.startswith(EQ_DIR)) == sorted([HD_PATH, f'{EQ_DIR}/Other.txt']), f'an empty name (or only spaces, or ".txt") does nothing ({toasts(m)}, {sorted(k for k in m.fs if k.startswith(EQ_DIR))})')
    m.call(PSYMS['peqpage_named'], m.cstr('.hidden'), count=1 << 40)
    expect(f'{EQ_DIR}/_hidden.txt' in m.fs, 'a leading dot becomes "_" (a dot file is not listed)')
    long_ = 'é' * 40
    m.call(PSYMS['peqpage_named'], m.cstr(long_), count=1 << 40)
    nm = [k for k in m.fs if k.startswith(EQ_DIR) and k.endswith('.txt') and 'é'.encode('latin-1', 'ignore') is not None and len(k) > len(EQ_DIR) + 40]
    expect(nm and all(len(k.split('/')[-1].encode('latin-1')) <= 63 for k in nm), f'a long name is cut on a character boundary so that file name and ".txt" fit the 63 bytes the Equalizer lists ({[len(k.split("/")[-1].encode("latin-1")) for k in nm]})')
    # the 64 files cap
    files64 = [(f'p{i:02d}.txt', AUTOEQ) for i in range(63)] + [(HD, AUTOEQ)]
    m = epage(files64, state=state)
    m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('one more'), count=1 << 40)
    expect(toasts(m) == ['Preset limit reached'] and f'{EQ_DIR}/one more.txt' not in m.fs, 'with 64 files on the card Save As is refused: "Preset limit reached"')
    m = epage(files64[1:], state=state)
    m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('one more'), count=1 << 40)
    expect(not toasts(m) and f'{EQ_DIR}/one more.txt' in m.fs, 'with 63 files the 64th is made')
    m = epage([(HD, AUTOEQ)], state=state)
    m.fail.add(('rename', f'{EQ_DIR}/Fail.txt')); m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('Fail'), count=1 << 40)
    expect(toasts(m) == ['Not saved'] and f'{EQ_DIR}/Fail.txt' not in m.fs and f'{EQ_DIR}/.save.tmp' not in m.fs and not hptext(m, 'label_title'), 'a failed Save As: "Not saved", no file, the page keeps its name')


def edit_rename_tests(ctx):
    expect = ctx.expect
    m0 = demo_machine()
    state = pack_state(1, pack_preset([AUTOEQ_BANDS[0], (1, 0, 2000, 4.0, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]], preamp=-6.2), HD.encode())
    # ---- Rename
    m = epage([(HD, AUTOEQ), ('Other.txt', AUTOEQ)], state=pack_state(1, pack_preset(AUTOEQ_BANDS, preamp=-6.2), HD.encode()))
    m.hist.clear()
    fire(m, m.widgets['pod_row32'], 'EVT_CLICK')
    expect(('window_open', 'm1plus_keyboard') in m.hist, 'Rename Preset opens the keyboard')
    m.hist.clear(); m.call(PSYMS['peqpage_renamed'], m.cstr('HD 600 mine'), count=1 << 40)
    expect(('rename', HD_PATH, f'{EQ_DIR}/HD 600 mine.txt') in m.hist and HD_PATH not in m.fs and m.fs[f'{EQ_DIR}/HD 600 mine.txt'] == AUTOEQ and NAME_OF(m.fs[STATE]) == b'HD 600 mine.txt'
           and hptext(m, 'label_title')[-1] == 'HD 600 mine' and not [c for c in m.hist if c[0] in ('set_equalizer_value', 'write_int_config')], 'Rename: the file takes the new name, the record\'s name follows (the preset plays), the title; the player is not told')
    m.hist.clear(); m.call(PSYMS['peqpage_renamed'], m.cstr('Other'), count=1 << 40)
    expect(toasts(m) == ['Name already in use'] and not [c for c in m.hist if c[0] == 'rename'], 'a name that exists is refused')
    m.hist.clear(); m.call(PSYMS['peqpage_renamed'], m.cstr('HD 600 mine'), count=1 << 40); m.call(PSYMS['peqpage_renamed'], m.cstr(' '), count=1 << 40)
    expect(not [c for c in m.hist if c[0] == 'rename'] and not toasts(m), 'the same name, or none: nothing happens')
    m.hist.clear(); m.call(PSYMS['peqpage_renamed'], m.cstr('HD 600 MINE'), count=1 << 40)
    expect(('rename', f'{EQ_DIR}/HD 600 mine.txt', f'{EQ_DIR}/HD 600 MINE.txt') in m.hist, 'the same name in another case is allowed (the card ignores case)')
    m = epage([(HD, AUTOEQ)], state=pack_state(1, pack_preset([(1, 0, 500, 3.0, 1.0)]), b'other.txt'))
    m.call(PSYMS['peqpage_renamed'], m.cstr('New'), count=1 << 40)
    expect(f'{EQ_DIR}/New.txt' in m.fs and NAME_OF(m.fs[STATE]) == b'other.txt' and not [c for c in m.hist if c[0] == 'set_equalizer_value'], 'another preset plays: the record is left alone')
    m = epage([(HD, AUTOEQ)], state=None)
    m.fail.add(('rename', f'{EQ_DIR}/New.txt')); m.hist.clear(); m.call(PSYMS['peqpage_renamed'], m.cstr('New'), count=1 << 40)
    expect(toasts(m) == ['Not saved'] and HD_PATH in m.fs and not hptext(m, 'label_title'), f'a rename that fails: "Not saved", the page keeps its name ({toasts(m)}, {hptext(m, "label_title")})')
    # the output slots that name the preset follow the rename (a rename must not leave Line Out or USB pointing at a gone file)
    m = epage([(HD, AUTOEQ)], state=state)
    other = pack_state(1, pack_preset([(1, 0, 500, 3.0, 1.0)]), b'other.txt')
    m.fs[SLOT[0]] = state; m.fs[SLOT[1]] = state; m.fs[SLOT[2]] = other
    m.call(PSYMS['peqpage_renamed'], m.cstr('Renamed2'), count=1 << 40)
    expect(NAME_OF(m.fs[SLOT[0]]) == b'Renamed2.txt' and NAME_OF(m.fs[SLOT[1]]) == b'Renamed2.txt' and NAME_OF(m.fs[SLOT[2]]) == b'other.txt',
           'Rename: every output slot that named the preset follows, other slots are left alone')

    # a rename of an edited preset keeps the edits
    m = epage([(HD, AUTOEQ)], state=state)
    m.call(PSYMS['peqpage_renamed'], m.cstr('Renamed'), count=1 << 40)
    ask(m); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    ok, back, _ = parse(m0, m.fs[f'{EQ_DIR}/Renamed.txt'])
    expect(ok == 1 and back['bands'][1][3] == 4.0 and HD_PATH not in m.fs, 'a Save after a Rename writes the renamed file with the edits')


def edit_channels_tests(ctx):
    expect = ctx.expect
    m0 = demo_machine()
    state = pack_state(1, pack_preset([AUTOEQ_BANDS[0], (1, 0, 2000, 4.0, 1.41), AUTOEQ_BANDS[2], AUTOEQ_BANDS[3]], preamp=-6.2), HD.encode())
    px = lambda t: round(t * 272)
    # ---- channels, balance, OFF filters and skipped lines
    m = epage([('b.txt', BALANCED)], 'b.txt')
    ok, orig, _ = parse(m0, BALANCED)
    open_band(m, 2)
    drag_to(m, 1, 0.75)
    g2 = rec_preset(m)['bands'][1][3]
    fire(m, m.window, 'EVT_WINDOW_TO_FG')
    ask(m); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    text = m.fs[f'{EQ_DIR}/b.txt'].decode()
    ok2, back, _ = parse(m0, m.fs[f'{EQ_DIR}/b.txt'])
    want = [(e, t, f, g2 if i == 1 else g, q) for i, (e, t, f, g, q) in enumerate(orig['bands'])]
    expect(ok2 == 1 and back['bands'] == want and back['preamp'] == orig['preamp'] and back['balance'] == orig['balance'] == 2.0 and back['automatic'] == 2,
           f'channels and balance survive a Save: the R-only band keeps its side, the L preamp comes back as the balance ({back["bands"]}, balance {back["balance"]})')
    expect(text.count('Channel:') == 4 and 'Channel: L\nPreamp: -2 dB\nChannel: all\n' in text and 'Channel: R\nFilter 2' in text, f'the text: "Channel:" wherever the side changes, the left preamp under Channel: L ({text!r})')
    m = epage([('Long.txt', PLONG)], 'Long.txt')
    open_band(m, 1); drag_to(m, 1, 0.8); fire(m, m.window, 'EVT_WINDOW_TO_FG')
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    text = m.fs[f'{EQ_DIR}/Long.txt'].decode()
    ok, back, _ = parse(m0, m.fs[f'{EQ_DIR}/Long.txt'])
    expect(ok == 1 and m0.skipped == 0 and 'Device' not in text and 'LP' not in text and 'OFF' not in text and len(back['bands']) == 6 and back['preamp'] == -3.5,
           f'a Save rewrites the supported lines only: the Device line, the LP filter and the OFF filter are not written back ({len(back["bands"])} bands, {m0.skipped} skipped)')
    expect(m.props.get((m.widgets['pod_note0'], 'visible')) == 0 and m.props.get((m.widgets['pod_gap1'], 'visible')) == 1, 'the skipped-lines note goes after a Save (nothing is skipped in the file any more)')
    # a file with no Preamp line and a balance cannot exist; a Preamp of 0 is written as "Preamp: 0 dB" (it stays a file with a preamp)
    m = epage([('z.txt', b'Preamp: 0 dB\nFilter 1: ON PK Fc 1000 Hz Gain 3 dB Q 1\n')], 'z.txt')
    open_band(m, 1); drag_to(m, 1, 0.8); fire(m, m.window, 'EVT_WINDOW_TO_FG')
    ask(m); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(m.fs[f'{EQ_DIR}/z.txt'].startswith(b'Preamp: 0 dB\n'), 'a Preamp of 0 dB is still written (the file stays "as given", not Auto)')
    # numbers: four decimals, trimmed
    m = epage([('n.txt', b'Preamp: -0.00004 dB\nFilter 1: ON PK Fc 1234.56789 Hz Gain -0.12345 dB Q 0.70711\n')], 'n.txt')
    open_band(m, 1); pev(m, m.bw['pod_seg'], 'EVT_POINTER_DOWN', 10 + 50, 30, 1); pev(m, m.bw['pod_seg'], 'EVT_POINTER_UP', 10 + 50, 30, 2)   # the same Peak: no edit
    expect(not m.fs.get(STATE), 'a tap on the segment it is on is no edit')
    pev(m, m.bw['pod_seg'], 'EVT_POINTER_DOWN', 10 + 150, 30, 3); pev(m, m.bw['pod_seg'], 'EVT_POINTER_UP', 10 + 150, 30, 4)
    fire(m, m.window, 'EVT_WINDOW_TO_FG'); ask(m); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(m.fs[f'{EQ_DIR}/n.txt'] == b'Preamp: 0 dB\nFilter 1: ON LSC Fc 1234.5679 Hz Gain -0.1235 dB Q 0.7071\n', f'numbers are written to four decimals, zeros trimmed, a tiny negative is "0" ({m.fs[f"{EQ_DIR}/n.txt"]!r})')
    # a Preset page destroyed: the band page has nothing to edit and nothing to ask about
    m = epage([(HD, AUTOEQ)], state=state)
    open_band(m, 2)
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30); m.hist.clear()
    m.call(PSYMS['peqpage_named'], m.cstr('X'), count=1 << 40)
    fire(m, m.bw['btn_return'], 'EVT_CLICK')
    expect(not [c for c in m.hist if c[0] in ('window_open', 'rename')] and f'{EQ_DIR}/X.txt' not in m.fs and went_back(m) and not dialog_up(m), 'after the Preset page is destroyed its name callbacks do nothing and Back goes back without asking')
    # not our asset: a band page without the dialog still has its way out
    m = epage([(HD, AUTOEQ)], state=state)
    del m.lookups[(m.band_win, 'pq_card')]
    open_band(m, 2)
    fire(m, m.bw['btn_return'], 'EVT_CLICK')
    expect(went_back(m) and not dialog_up(m), 'a band page asset without the dialog binds Back and goes back at once')
    # Now Playing from the band page with nothing unsaved goes to the player (no dialog)
    m = epage([(HD, AUTOEQ)])
    open_band(m, 2)
    fire(m, m.bw['btn_backtoplayer'], 'EVT_CLICK')
    expect(not dialog_up(m) and not went_back(m), 'Now Playing with nothing to save leaves for the player at once')
    # no memory for the bitmaps: the band page still edits
    m = epage([(HD, AUTOEQ)], bitmap_ok=False)
    open_band(m, 2)
    drag_to(m, 1, 0.9)
    expect(abs(rec_preset(m)['bands'][1][3] - gain_of(t_of_pos(TRK0 + px(0.9)))) < 1e-9, 'with no memory for the bitmaps the sliders still work (nothing is painted)')


# ---- the 10-Band editor, its Curve and Preamp pages (patch/tenband.c, tools/tenband_model.py)
import tenband_model as TBM
TBW = ['pod_graph', 'pod_gr_top', 'pod_gr_bot', 'pod_sliders', 'pod_scrollview', 'pod_row0', 'pod_row1', 'pod_row2', 'pod_row3', 'pod_value0', 'pod_value1', 'pod_region'] + [f'pod_sl_{k}{c}' for c in range(10) for k in 'vf']
GREY_VAL = '#8A8A8A'
REGION_TEXTS = ['Sub bass · rumble', 'Mid bass · punch and warmth', 'Lower mids · body and fullness', 'Upper mids · shouty if too much', 'Treble · detail and sparkle', 'Air · openness']
REGIONS = [REGION_TEXTS[i] for i in (0, 1, 1, 2, 2, 3, 3, 3, 4, 5)]   # by band: 31, 63, 125, 250, 500, 1k, 2k, 4k, 8k, 16k Hz


def tbands(gain): return [(1, 0, f, float(g), 1.41) for f, g in zip(GRAPHIC_F, gain)]
def rec_fields(rec): return struct.unpack_from('<ii20f', rec, STATE_SIZE - 88)   # curve, preamp, gain[10], custom[10]
def saves(m): return len([c for c in m.calls if c[0] == 'rename'])
def sent(m): return len([c for c in m.calls if c[0] == 'set_equalizer_value'])


def tpage(state=None, flag=1, bitmap_ok=True, drop=()):
    """The editor as m1plus.c open_page and tenband_opened leave it: the record, stock's switch, the asset's widgets by name."""
    m = demo_machine()
    m.bitmap_ok = bitmap_ok
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag])); m.setword(pod.DATA['EQ_MODE'][0], 4)
    if state is not None: m.fs[STATE] = state
    for n in TBW:
        if n not in drop: m.widget(n)
    m.count()
    m.opened = m.call(PSYMS['tenband_open'], count=1 << 40)
    return m


def sl_event(m, kind, cx, cy, t=0):
    """A pointer event of the slider view at card x cx, card y cy (the view's own coordinates: the list is at x 0 and the card 10 px in; the widgets here sit at the origin, so screen = view coordinates)."""
    e = m.alloc(0x40)
    m.setword(e + 8, t); m.setword(e + O['PE_X'], TBM.CARD_X + cx); m.setword(e + O['PE_Y'], cy)
    fn, ctx = m.bound[(m.widgets['pod_sliders'], O[kind])]
    return m.call(fn, a0=ctx, a1=e, count=1 << 40)


def bmp(m, i):
    h = list(m.bitmaps)[i]
    data, w, hh = m.bitmaps[h]
    return h, w, hh, struct.unpack(f'<{w * hh}I', m.u.mem_read(data, w * hh * 4))


def same_bitmap(px, w, h, model):
    return [(x, y) for y in range(h) for x in range(w) if abs((px[y * w + x] >> 24) - model[y][x][0]) > 1 or abs((px[y * w + x] & 255) - model[y][x][1]) > 2]


def vtexts(m): return [(ptext(m, f'pod_sl_v{c}') or [None])[-1] for c in range(10)]


def tenband_drag_tests(ctx):
    expect = ctx.expect
    # the touch maths
    m = demo_machine()
    cols = [(x, m.call(PSYMS['tenband_col'], x, count=1 << 20)) for x in (-9, 0, 4, 5, 33, 34, 62, 63, 150, 5 + 29 * 9, 5 + 29 * 10 - 1, 295, 299, 400)]
    expect(all(c == TBM.col(x) for x, c in cols) and [c for _, c in cols] == [0, 0, 0, 0, 0, 1, 1, 2, 5, 9, 9, 9, 9, 9], f'the column under x: ten columns of {TBM.COL_W} px from x {TBM.X0}, the first and last take what is beside them ({[c for _, c in cols]})')
    sg = lambda v: v - (1 << 32) if v >> 31 else v
    steps = [(y, sg(m.call(PSYMS['tenband_step'], y & 0xffffffff, count=1 << 20))) for y in (-50, 0, 40, 41, 42, 43, 87, 88, 89, 90, 91, 92, 93, 112, 136, 137, 140, 170)]
    d = dict(steps)
    expect(all(s == TBM.step(y) for y, s in steps) and d[40] == d[0] == d[-50] == 24 and d[136] == d[137] == d[170] == -24 and d[88] == d[87] == d[89] == 0 and d[90] == d[91] == -1 and d[92] == d[93] == -2 and d[112] == -12,
           f'the finger\'s height is a half-decibel step: +12 at the top of the track (and above), 0 around the middle, -12 at the bottom, two pixels a step, clamped ({steps})')
    expect([TBM.step(TBM.y_of_step(s)) for s in range(-24, 25)] == list(range(-24, 25)), 'a step\'s own y reads back as that step')

    # the page opens on a Rock record
    rock = [float(g) for g in CURVES[2]]
    m = tpage(tenband(rock, -1, 2))
    expect(m.opened == 1 and ('window_open', 'm1plus_tenband') in m.calls, 'tenband_open opens the editor\'s window')
    expect(m.icount < 10_000_000, f'opening the editor (record, three small bitmaps, the card, the graph, the texts) costs {m.icount:,} payload instructions, once')
    sizes = [(w, h) for _, (d_, w, h) in m.bitmaps.items()]
    expect(sizes == [(300, 170), (24, 13), (34, 18), (300, 170)], f'four bitmaps: the slider card, a thumb, the value pill, the graph card ({sizes})')
    _, w, h, px = bmp(m, 0)
    off = same_bitmap(px, w, h, TBM.bitmap(TBM.card_px, w, h))
    expect(not off, f'the slider card\'s bitmap is the model\'s pixel for pixel ({len(off)} differ: {off[:3]})')
    expect(px[0] >> 24 == 0 and px[299] >> 24 == 0 and px[170 * 300 - 1] >> 24 == 0 and px[85 * 300] >> 24 == 255, 'its corners are cut in the alpha, its edges opaque')
    cx0 = TBM.center_x(0)
    track = [px[y * 300 + cx0] & 255 for y in range(170)]
    expect(track[TBM.Y0 + 8] > 55 and track[TBM.Y0 + TBM.SPAN - 8] > 55 and track[TBM.Y0 - 6] == 28 and track[TBM.Y0 + TBM.SPAN + 6] == 28, 'the track is a groove from +12 dB to -12 dB, nothing above or below it')
    _, w, h, px = bmp(m, 1)
    expect(not same_bitmap(px, w, h, TBM.bitmap(TBM.thumb_px, w, h)), 'the thumb is the model\'s')
    _, w, h, px = bmp(m, 2)
    expect(not same_bitmap(px, w, h, TBM.bitmap(TBM.pill_px, w, h)), 'the pill is the model\'s')
    _, w, h, px = bmp(m, 3)
    db, rng = G.curve(tbands(rock))
    expect(not same_bitmap(px, w, h, G.render(db, rng)) and ptext(m, 'pod_gr_top') == [f'+{rng}'], f'the graph card is the preset page\'s drawing of the ten bands (range {rng}), no preamp')
    expect(vtexts(m) == [TBM.gain_text(g) for g in rock] == ['−2', '0', '+2', '+4', '−2', '−2', '0', '0', '+4', '+4'], f'the values above the sliders, no unit: {vtexts(m)}')
    cut = 20 * math.log10(auto_gain(tbands(rock), 48000))
    expect(ptext(m, 'pod_value0') == ['Rock'] and ptext(m, 'pod_value1') == ['Auto · ' + G.gain_text(cut)] and -6 < cut < -4, f'the Curve row\'s grey name and the Preamp row\'s Auto cut ({ptext(m, "pod_value1")})')
    # painted: the card, a thumb per column at its gain (no pill at rest)
    fn, c = m.bound[(m.widgets['pod_sliders'], O['EVT_BEFORE_PAINT'])]
    canvas, ev = m.alloc(0x100), m.alloc(0x40)
    m.setword(ev + O['EVENT_PAINT_CANVAS'], canvas); m.blits.clear()
    m.call(fn, a0=c, a1=ev, count=1 << 30)
    card, thumb = list(m.bitmaps)[0], list(m.bitmaps)[1]
    want = [(card, (0, 0, 300, 170), (10, 0, 300, 170))] + [(thumb, (0, 0, 24, 13), (10 + TBM.center_x(i) - 12, TBM.thumb_y(g), 24, 13)) for i, g in enumerate(rock)]
    expect(m.blits == want, f'paint: the card, then a thumb per column at its gain\'s height ({m.blits[:3]})')
    m.blits.clear(); m.call(fn, a0=c, a1=0, count=1 << 30)
    expect(not m.blits, 'an event without a canvas paints nothing')
    fn, c = m.bound[(m.widgets['pod_graph'], O['EVT_BEFORE_PAINT'])]
    m.blits.clear(); m.call(fn, a0=c, a1=ev, count=1 << 30)
    expect(m.blits == [(list(m.bitmaps)[3], (0, 0, 300, 170), (10, 0, 300, 170))], 'the graph card is one blit too')
    # with the sliders' widgets bound: the touch, the rows, the window
    expect(all((m.widgets['pod_sliders'], O[k]) in m.bound for k in ('EVT_POINTER_DOWN', 'EVT_POINTER_MOVE', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT')) and not m.timers and not [x for x in m.bound if x[1] == O['EVT_SCROLL']],
           'the slider view takes DOWN, MOVE, UP and ABORT; no timer, no scroll handler')

    # a drag on a built-in curve: the 2 kHz column to +5 dB
    m.calls = []
    x6 = TBM.center_x(6)
    sl_event(m, 'EVT_POINTER_DOWN', x6, TBM.y_of_step(10), 1000)
    rec = m.fs[STATE]; cur, pre, gain, custom = rec_fields(rec)[0], rec_fields(rec)[1], list(rec_fields(rec)[2:12]), list(rec_fields(rec)[12:])
    expect(('widget_grab', m.window, m.widgets['pod_sliders']) in m.calls and m.props.get((m.widgets['pod_scrollview'], 'yslidable')) == 0,
           'DOWN grabs the touch at the window (the moves and the release come to the view, never to the page\'s scroll_view) and turns the page\'s scrolling off for the gesture')
    expect(cur == 9 and gain[6] == 5.0 and gain == rock[:6] + [5.0] + rock[7:] and custom == gain and pre == -1 and struct.unpack_from('<i', rec, 8)[0] == 0,
           f'the first step saves at once: Rock was copied into Custom (the curve reads Custom), 2 kHz +5, the preamp left Auto ({cur}, {gain})')
    expect(saves(m) == 1 and sent(m) == 1 and ptext(m, 'pod_value0')[-1:] == ['Custom'] and ptext(m, 'pod_sl_v6')[-1:] == ['+5'], 'one save and one gain command; the Curve row reads Custom; the value shows +5')
    expect(m.props.get((m.widgets['pod_sl_v6'], 'style:normal:text_color')) == '#000000' and m.props.get((m.widgets['pod_sl_f6'], 'style:normal:text_color')) == '#FFFFFF'
           and all(m.props.get((m.widgets['pod_sl_v6'], f'style:{s}:text_color')) == '#000000' for s in ('disable', 'focused')) and m.props.get((m.widgets['pod_sl_v5'], 'style:normal:text_color')) is None,
           'while dragged the column\'s value is black (on the white pill) and its frequency white')
    m.blits.clear(); fn, c = m.bound[(m.widgets['pod_sliders'], O['EVT_BEFORE_PAINT'])]; m.call(fn, a0=c, a1=ev, count=1 << 30)
    pill = list(m.bitmaps)[2]
    expect(m.blits[-1] == (pill, (0, 0, 34, 18), (10 + x6 - 17, 10, 34, 18)) and m.blits[7][2][1] == TBM.thumb_y(5.0) and len(m.blits) == 12, 'the pill is blitted behind the dragged value, the thumb follows the finger')
    # moves: inside the send interval only the picture follows; later ones save again
    m.calls = []; m.icount = 0
    sl_event(m, 'EVT_POINTER_MOVE', x6 + 3, TBM.y_of_step(9), 1020)
    expect(saves(m) == 0 and ptext(m, 'pod_sl_v6') == ['+4.5'] and m.props.get((m.widgets['pod_sliders'], 'x')) is None, 'a move within 150 ms: the value follows, nothing is saved')
    sl_event(m, 'EVT_POINTER_MOVE', x6 + 3, TBM.y_of_step(9) - 1, 1030)
    expect(saves(m) == 0 and not ptext(m, 'pod_sl_v6'), 'a move that leaves the step where it is changes nothing')
    sl_event(m, 'EVT_POINTER_MOVE', x6 - 60, TBM.y_of_step(-7), 1200)
    expect(saves(m) == 1 and rec_fields(m.fs[STATE])[2 + 6] == -3.5 and ptext(m, 'pod_sl_v6')[-1] == '−3.5' and sent(m) == 1 and sum(1 for c in m.calls if c[0] == 'bitmap_lock_buffer_for_write') == 1,
           'a move 150 ms later: saved and sent again; sideways does not change the column (the one DOWN took); the graph is drawn again')
    expect(m.icount < 5_000_000, f'a step that saves and draws the graph costs {m.icount:,} payload instructions')
    m.calls = []
    sl_event(m, 'EVT_POINTER_MOVE', x6, TBM.y_of_step(24), 1230)
    expect(saves(m) == 0 and ptext(m, 'pod_sl_v6') == ['+12'] and m.props.get((m.widgets['pod_sliders'], 'dirty')) is None, '+12 at the top')
    sl_event(m, 'EVT_POINTER_MOVE', x6, -40 & 0xffffffff, 1240)
    expect(not ptext(m, 'pod_sl_v6') and saves(m) == 0, 'above the card: still +12 (clamped: no change)')
    sl_event(m, 'EVT_POINTER_MOVE', x6, 500, 1250)
    expect(ptext(m, 'pod_sl_v6') == ['−12'], 'below it: clamped at −12')
    sl_event(m, 'EVT_POINTER_MOVE', x6, TBM.y_of_step(-5), 1255)
    m.calls = []
    sl_event(m, 'EVT_POINTER_UP', x6, TBM.y_of_step(-5), 1260)
    f = rec_fields(m.fs[STATE])
    expect(saves(m) == 1 and sent(m) == 1 and f[2 + 6] == -2.5 and f[12 + 6] == -2.5 and f[0] == 9, 'the release saves the last step (-2.5) when it has not been saved')
    expect(('widget_ungrab', m.window, m.widgets['pod_sliders']) in m.calls and m.props.get((m.widgets['pod_scrollview'], 'yslidable')) == 1
           and m.props.get((m.widgets['pod_sl_v6'], 'style:normal:text_color')) == GREY_VAL and m.props.get((m.widgets['pod_sl_f6'], 'style:normal:text_color')) == GREY_VAL, 'the release lets go of the touch, scrolling is back on, the labels grey again')
    expect(ptext(m, 'pod_value1')[-1].startswith('Auto · ') and [c for c in m.calls if c[0] == 'bitmap_lock_buffer_for_write'], 'at the end the graph and the Preamp row\'s Auto cut follow the gains')
    m.calls = []
    sl_event(m, 'EVT_POINTER_MOVE', x6, TBM.y_of_step(3), 3000)
    expect(not m.calls or not [c for c in m.calls if c[0] in ('rename', 'widget_set_text_utf8')], 'a move after the release does nothing')
    # a second edit on Custom: no copy, the other bands keep their values
    m.calls = []
    x2 = TBM.center_x(2)
    sl_event(m, 'EVT_POINTER_DOWN', x2, TBM.y_of_step(-4), 5000)
    sl_event(m, 'EVT_POINTER_UP', x2, TBM.y_of_step(-4), 5010)
    f = rec_fields(m.fs[STATE])
    expect(list(f[2:12]) == rock[:2] + [-2.0] + rock[3:6] + [-2.5] + rock[7:] and list(f[12:]) == list(f[2:12]) and f[0] == 9, 'on Custom a move changes its band alone: gain[] and custom[] agree, the curve stays Custom')

def tenband_edit_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # a touch that leaves the band where it is leaves a built-in curve alone
    m = tpage(tenband(rock, -1, 2))
    m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(2), TBM.y_of_step(4), 100)
    sl_event(m, 'EVT_POINTER_UP', TBM.center_x(2), TBM.y_of_step(4), 110)
    expect(saves(m) == 0 and m.fs[STATE] == tenband(rock, -1, 2) and ptext(m, 'pod_value0') == ['Rock'] and not [c for c in m.calls if c[0] == 'set_equalizer_value'], 'a touch on a built-in curve that lands on the band\'s own value: no copy, no save, still Rock')
    # beside the card: nothing; the edge columns take the touch beside them
    m.calls = []
    for cx in (-4, 300, 305):
        sl_event(m, 'EVT_POINTER_DOWN', cx, 80, 200)
    expect(not [c for c in m.calls if c[0] in ('widget_grab', 'rename')], 'a touch in the 10 px beside the card does nothing')
    sl_event(m, 'EVT_POINTER_DOWN', 296, TBM.y_of_step(-8), 300)
    sl_event(m, 'EVT_POINTER_UP', 296, TBM.y_of_step(-8), 310)
    expect(rec_fields(m.fs[STATE])[2 + 9] == -4.0, 'a touch at the card\'s right edge moves the last band (16 kHz)')
    # a failed save: the page goes back to the record
    m = tpage(tenband(rock, -1, 2))
    m.fail.add(('rename', STATE)); m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(0), TBM.y_of_step(6), 100)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Not saved'] and not [c for c in m.calls if c[0] == 'set_equalizer_value'] and m.fs[STATE] == tenband(rock, -1, 2) and ptext(m, 'pod_value0')[-1] == 'Rock' and ptext(m, 'pod_sl_v0')[-1] == '−2',
           'a failed save: the message box, nothing sent, the record and the page as they were')
    sl_event(m, 'EVT_POINTER_UP', TBM.center_x(0), TBM.y_of_step(6), 110)
    # ABORT ends a gesture like UP
    m = tpage(tenband(rock, -1, 2))
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(1), TBM.y_of_step(8), 100)
    m.calls = []
    sl_event(m, 'EVT_POINTER_MOVE', TBM.center_x(1), TBM.y_of_step(9), 110)
    sl_event(m, 'EVT_POINTER_ABORT', 0, 0, 120)
    expect(('widget_ungrab', m.window, m.widgets['pod_sliders']) in m.calls and m.props.get((m.widgets['pod_scrollview'], 'yslidable')) == 1 and rec_fields(m.fs[STATE])[2 + 1] == 4.5, 'an abort saves what was done and lets go')

def tenband_switch_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # the switch off: editing turns stock's Equalizer on (as a preset does)
    m = tpage(tenband(rock, -1, 2), flag=0); m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(1), TBM.y_of_step(8), 100)
    expect(m.u.mem_read(pod.DATA['EQ_FLAG'][0], 1)[0] == 1 and ('write_int_config', 1, 'PLAYSET', 'EQFLAG') in m.calls, f'with the Equalizer off ({m.u.mem_read(pod.DATA["EQ_FLAG"][0], 1)[0]}, {[c for c in m.calls if c[0] in ("write_int_config", "set_equalizer_value")]}) an edit turns it on, as a tap on a preset does')
    # a preset file played: the first edit makes the 10-Band EQ the mode
    m = tpage(pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt', 2, -1, rock)); m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(1), TBM.y_of_step(8), 100)
    sl_event(m, 'EVT_POINTER_UP', TBM.center_x(1), TBM.y_of_step(8), 110)
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 0 and NAME_OF(m.fs[STATE]) == b'', 'an edit while a preset file plays: the record plays the 10-Band EQ (mode 0, no file)')


def tenband_replace_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # the replace message: once, at the release of the drag whose move switched from a preset file; never mid-drag (the message box would take the touch)
    toasts = lambda m: [c[1] for c in m.calls if c[0] == 'toast']
    m = tpage(pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt', 2, -1, rock)); m.calls = []
    x1 = TBM.center_x(1)
    sl_event(m, 'EVT_POINTER_DOWN', x1, TBM.y_of_step(8), 100)
    sl_event(m, 'EVT_POINTER_MOVE', x1, TBM.y_of_step(9), 120)
    sl_event(m, 'EVT_POINTER_MOVE', x1, TBM.y_of_step(10), 400)
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 0 and not toasts(m), 'the move that switches to the 10-Band EQ shows no message while the finger is down')
    sl_event(m, 'EVT_POINTER_UP', x1, TBM.y_of_step(10), 410)
    expect(toasts(m) == ['Switched to 10-Band EQ'], f'the release shows "Switched to 10-Band EQ" once ({toasts(m)})')
    m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', x1, TBM.y_of_step(4), 1000)
    sl_event(m, 'EVT_POINTER_MOVE', x1, TBM.y_of_step(5), 1200)
    sl_event(m, 'EVT_POINTER_UP', x1, TBM.y_of_step(5), 1300)
    expect(not toasts(m), 'later moves, with the 10-Band EQ already playing, show no message')
    m = tpage(tenband(rock, -1, 2)); m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', x1, TBM.y_of_step(8), 100)
    sl_event(m, 'EVT_POINTER_UP', x1, TBM.y_of_step(8), 110)
    expect(not toasts(m), 'no message when the 10-Band EQ played already')
    m = tpage(pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt', 2, -1, rock)); m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', x1, TBM.y_of_step(0), 100)
    sl_event(m, 'EVT_POINTER_UP', x1, TBM.y_of_step(0), 110)   # a touch that leaves the band where it is: nothing switches, nothing is said
    expect(not toasts(m) and struct.unpack_from('<i', m.fs[STATE], 8)[0] == 1, 'a touch that moves no band replaces nothing and says nothing')
    m = tpage(pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt', 2, -1, rock))
    m.fail.add(('rename', STATE)); m.calls = []
    sl_event(m, 'EVT_POINTER_DOWN', x1, TBM.y_of_step(8), 100)
    sl_event(m, 'EVT_POINTER_UP', x1, TBM.y_of_step(8), 110)
    expect(toasts(m) == ['Not saved'], 'a failed save keeps the preset and says only "Not saved", not "Switched to 10-Band EQ"')


def tenband_rows_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # the region line: the dragged band's range while the finger is down, empty after the release
    m = tpage(tenband(rock, -1, 2))
    expect(not ptext(m, 'pod_region') or ptext(m, 'pod_region')[-1] == '', 'at rest the region line is empty')
    for c in range(10):
        m.calls = []
        sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(c), TBM.y_of_step(8), 100)
        shown = ptext(m, 'pod_region')[-1:]
        sl_event(m, 'EVT_POINTER_UP', TBM.center_x(c), TBM.y_of_step(8), 110)
        expect(shown == [REGIONS[c]] and ptext(m, 'pod_region')[-1:] == [''], f'band {c}: the region line reads "{REGIONS[c]}" while dragged, empty after the release ({shown})')

    # the rows: Curve and Preamp open their pages, Back in front reads the record again
    m = tpage(tenband(rock, -1, 2)); m.calls = []
    for row, name in ((0, 'm1plus_tencurve'), (1, 'm1plus_tenpreamp')):
        fn, c = m.bound[(m.widgets[f'pod_row{row}'], O['EVT_CLICK'])]
        m.call(fn, a0=c, count=1 << 30)
        expect(('window_open', name) in m.calls, f'row {row} opens {name}')
    m.fs[STATE] = tenband([1.0] * 10, 3, 9, [1.0] * 10); m.calls = []
    fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
    m.call(fn, a0=c, count=1 << 40)
    expect(ptext(m, 'pod_value0') == ['Custom'] and ptext(m, 'pod_value1') == ['−3 dB'] and vtexts(m) == ['+1'] * 10 and [c for c in m.calls if c[0] == 'bitmap_lock_buffer_for_write'],
           'back in front: the record again (Custom, a fixed -3 dB preamp, the values +1), the graph drawn again')

def tenband_reopen_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # opened twice (Now Playing > pull-down > Playback Settings > Equalizer while an editor sits underneath): the second editor replaces the first, whose four bitmaps are freed and window closed; its late destroy leaves the new one alone
    m = tpage(tenband(rock, -1, 2)); first = m.window; fn1, c1 = m.bound[(first, O['EVT_DESTROY'])]
    m.windows['m1plus_tenband'] = second = 0x20002000; m.calls = []; d0 = m.destroyed
    expect(m.call(PSYMS['tenband_open'], count=1 << 40) == 1 and ('window_close', first) in m.calls and len(m.bitmaps) == 4 and m.destroyed - d0 == 4,
           f'the second open frees the first editor\'s four bitmaps (not leaked: {len(m.bitmaps)} live, {m.destroyed - d0} freed) and closes its window')
    m.calls = []; m.call(fn1, a0=c1, count=1 << 30)
    expect(len(m.bitmaps) == 4 and not [x for x in m.calls if x[0] == 'bitmap_destroy'], 'the first window\'s late destroy leaves the second editor alone')
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(1), TBM.y_of_step(8), 100); sl_event(m, 'EVT_POINTER_UP', TBM.center_x(1), TBM.y_of_step(8), 110)
    expect(rec_fields(m.fs[STATE])[2 + 1] == 4.0, '... and the second editor still works: a touch sets a band')
    fn2, c2 = m.bound[(second, O['EVT_DESTROY'])]
    m.call(fn2, a0=c2, count=1 << 30)
    expect(not m.bitmaps, 'the second editor\'s own destroy frees its bitmaps')
    # destroy: the bitmaps go, nothing runs after
    fn, c = m.bound[(m.window, O['EVT_DESTROY'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(not m.bitmaps and m.destroyed >= 4, 'destroy: the four bitmaps are freed')
    m.calls = []
    fn, c = m.bound[(m.widgets['pod_sliders'], O['EVT_POINTER_DOWN'])]
    sl_event(m, 'EVT_POINTER_DOWN', 100, 80, 1)
    expect(not [x for x in m.calls if x[0] in ('rename', 'widget_grab')], 'after the destroy a touch does nothing')

def tenband_memory_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # no memory: the sliders still work, nothing is drawn
    m = tpage(tenband(rock, -1, 2), bitmap_ok=False)
    expect(m.opened == 1 and not m.bitmaps and vtexts(m)[3] == '+4', 'no memory for the bitmaps: the labels are there')
    sl_event(m, 'EVT_POINTER_DOWN', TBM.center_x(1), TBM.y_of_step(8), 100); sl_event(m, 'EVT_POINTER_UP', TBM.center_x(1), TBM.y_of_step(8), 110)
    expect(rec_fields(m.fs[STATE])[2 + 1] == 4.0, '... and a touch still sets a band')
    ev = m.alloc(0x40)
    fn, c = m.bound[(m.widgets['pod_sliders'], O['EVT_BEFORE_PAINT'])]
    m.blits.clear(); m.call(fn, a0=c, a1=ev, count=1 << 30)
    expect(not m.blits, '... and a paint draws nothing')
    # not our asset
    m = tpage(tenband(rock, -1, 2), drop=('pod_sl_f7',))
    expect(m.opened == 1 and not m.bitmaps and not [x for x in m.bound if x[1] in (O['EVT_POINTER_DOWN'], O['EVT_DESTROY'])], 'an asset without a slider label binds and draws nothing')


def tenband_reset_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # Reset: a built-in curve at once, Custom after the confirm
    m = tpage(tenband(rock, 5, 2, [3.0] * 10)); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row2'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    f = rec_fields(m.fs[STATE])
    expect(not [x for x in m.calls if x[0] == 'confirm'] and f[0] == 0 and f[1] == -1 and not any(f[2:12]) and list(f[12:]) == [3.0] * 10 and sent(m) == 1,
           'Reset on Rock: no question, Flat, Auto, all zero; the Custom curve is kept (picking Custom again brings it back)')
    expect(ptext(m, 'pod_value0')[-1] == 'Flat' and ptext(m, 'pod_value1')[-1] == 'Auto · 0.0 dB' and vtexts(m) == ['0'] * 10, 'the page shows Flat, Auto · 0.0 dB, every slider at 0')
    m = tpage(tenband([1.0] * 10, 5, 9, [1.0] * 10)); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row2'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(('confirm', 'Reset 10-Band EQ?', 1) in m.calls and m.fs[STATE] == tenband([1.0] * 10, 5, 9, [1.0] * 10) and sent(m) == 0, 'Reset on Custom asks the stock confirm; No changes nothing')
    m.confirm_yes = True; m.calls = []
    m.call(fn, a0=c, count=1 << 30)
    f = rec_fields(m.fs[STATE])
    expect(f[0] == 0 and f[1] == -1 and not any(f[2:]) and sent(m) == 1 and vtexts(m) == ['0'] * 10 and ptext(m, 'pod_value0')[-1] == 'Flat', 'OK: Flat, Auto, both gain arrays zero; the page shows it')
    m = tpage(None); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row2'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(rec_fields(m.fs[STATE]) == (0, -1) + (0.0,) * 20 and ptext(m, 'pod_value0') == ['Flat'], 'no record: Flat; Reset on Flat saves Flat')


def tenband_curve_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # the Curve page: a check on the current curve, a tap picks, saves, goes back
    def cpage(state):
        m = demo_machine()
        if state is not None: m.fs[STATE] = state
        m.u.mem_write(pod.DATA['EQ_FLAG'][0], b'\x01'); m.setword(pod.DATA['EQ_MODE'][0], 4)
        for i in range(10):
            m.widget(f'pod_row{i}'); m.widget(f'pod_check{i}')
        m.opened = m.call(PSYMS['pod_open_tencurve'], count=1 << 30)
        return m
    marks_c = lambda m: [i for i in range(10) if m.props.get((m.widgets[f'pod_check{i}'], 'visible'))]
    m = cpage(tenband(rock, -1, 2))
    expect(m.opened == 0 and ('window_open', 'm1plus_tencurve') in m.calls and marks_c(m) == [2], 'the Curve page opens with a check on Rock')
    m = cpage(None)
    expect(marks_c(m) == [0], 'no record: Flat is checked')
    m = cpage(tenband([1.0] * 10, 5, 9, [1.0] * 10)); m.calls = []
    for i, name in ((6, 'Vocal'), (0, 'Flat'), (8, 'Jazz'), (9, 'Custom')):
        m.calls = []
        fn, c = m.bound[(m.widgets[f'pod_row{i}'], O['EVT_CLICK'])]
        m.call(fn, a0=c, count=1 << 30)
        f = rec_fields(m.fs[STATE])
        want = [1.0] * 10 if i == 9 else CURVES[i]
        expect(f[0] == i and list(f[2:12]) == [float(v) for v in want] and f[1] == 5 and list(f[12:]) == [1.0] * 10 and ('navigator_back',) in m.calls and sent(m) == 1 and saves(m) == 1,
               f'a tap on {name}: its gains loaded (Custom: the user\'s), the preamp and Custom kept, saved, the gain command sent, back')
    m = cpage(tenband(rock, -1, 2)); m.fail.add(('rename', STATE)); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row3'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Not saved'] and ('navigator_back',) not in m.calls, 'a failed save: the message box, the page stays')
    m = cpage(tenband(rock, -1, 2)); m.calls = []
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], b'\x00')
    fn, c = m.bound[(m.widgets['pod_row4'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(m.u.mem_read(pod.DATA['EQ_FLAG'][0], 1)[0] == 1 and rec_fields(m.fs[STATE])[0] == 4, 'with the Equalizer off a pick turns it on')
    m = cpage(tenband(rock, -1, 2))
    m.fs[STATE] = pack_state(1, pack_preset(AUTOEQ_BANDS), b'Sennheiser HD 600.txt', 2, -1, rock)
    fn, c = m.bound[(m.widgets['pod_row1'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(struct.unpack_from('<i', m.fs[STATE], 8)[0] == 0 and NAME_OF(m.fs[STATE]) == b'' and rec_fields(m.fs[STATE])[0] == 1, 'a pick while a preset file plays: the 10-Band EQ plays, the file is dropped')

    # a Curve page opened twice: the second replaces the first, whose late destroy leaves it alone and whose taps still pick
    m = cpage(tenband(rock, -1, 2)); first = m.window; fn1, c1 = m.bound[(first, O['EVT_DESTROY'])]
    m.windows['m1plus_tencurve'] = second = 0x20002000; m.calls = []
    m.call(PSYMS['pod_open_tencurve'], count=1 << 30)
    expect(('window_close', first) in m.calls and (second, O['EVT_DESTROY']) in m.bound, 'a second Curve page closes the first and binds its own destroy')
    m.call(fn1, a0=c1, count=1 << 30); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row6'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(rec_fields(m.fs[STATE])[0] == 6 and ('navigator_back',) in m.calls, '... the first one\'s late destroy left the second working: a tap picks and goes back')
    fn2, c2 = m.bound[(second, O['EVT_DESTROY'])]
    m.call(fn2, a0=c2, count=1 << 30); m.calls = []
    m.call(fn, a0=c, count=1 << 30)
    expect(not [x for x in m.calls if x[0] in ('rename', 'navigator_back')], '... and after its own destroy a tap does nothing')


def tenband_preamp_tests(ctx):
    expect = ctx.expect
    rock = [float(g) for g in CURVES[2]]
    # the Preamp page: Auto with its cut, 0 dB .. -12 dB
    def ppage_(state):
        m = demo_machine()
        if state is not None: m.fs[STATE] = state
        m.u.mem_write(pod.DATA['EQ_FLAG'][0], b'\x01'); m.setword(pod.DATA['EQ_MODE'][0], 4)
        for i in range(14):
            m.widget(f'pod_row{i}'); m.widget(f'pod_check{i}'); m.widget(f'pod_label{i}')
        m.widget('pod_value0')
        m.opened = m.call(PSYMS['pod_open_tenpreamp'], count=1 << 30)
        return m
    marks_p = lambda m: [i for i in range(14) if m.props.get((m.widgets[f'pod_check{i}'], 'visible'))]
    m = ppage_(tenband(rock, -1, 2))
    cut = 20 * math.log10(auto_gain(tbands(rock), 48000))
    labs = [(ptext(m, f'pod_label{i}') or [None])[-1] for i in range(1, 14)]
    expect(m.opened == 0 and ('window_open', 'm1plus_tenpreamp') in m.calls and marks_p(m) == [0] and ptext(m, 'pod_value0') == [G.gain_text(cut)], f'Auto is checked, its grey value the cut Auto makes now ({ptext(m, "pod_value0")})')
    expect(labs == ['0 dB'] + [f'−{n} dB' for n in range(1, 13)], f'the rows: 0 dB, −1 dB .. −12 dB (U+2212) ({labs})')
    m = ppage_(tenband(rock, 4, 2))
    expect(marks_p(m) == [5], 'a fixed -4 dB: its row (5) is checked')
    m = ppage_(tenband(rock, 0, 2))
    expect(marks_p(m) == [1], '0 dB: row 1')
    m = ppage_(None)
    expect(ptext(m, 'pod_value0') == ['0.0 dB'] and marks_p(m) == [0], 'a flat curve: Auto cuts 0.0 dB')
    m = ppage_(tenband(rock, -1, 2))
    for i, want in ((4, 3), (0, -1), (13, 12), (1, 0)):
        m.calls = []
        fn, c = m.bound[(m.widgets[f'pod_row{i}'], O['EVT_CLICK'])]
        m.call(fn, a0=c, count=1 << 30)
        f = rec_fields(m.fs[STATE])
        expect(f[1] == want and f[0] == 2 and list(f[2:12]) == [float(g) for g in rock] and ('navigator_back',) in m.calls and sent(m) == 1, f'a tap on row {i}: preamp {want}, curve and gains kept, saved, sent, back')
    m = ppage_(tenband(rock, -1, 2)); m.fail.add(('rename', STATE)); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row2'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Not saved'] and ('navigator_back',) not in m.calls, 'a failed save: the message box, the page stays')
    # a Preamp page opened twice: the same
    m = ppage_(tenband(rock, -1, 2)); first = m.window; fn1, c1 = m.bound[(first, O['EVT_DESTROY'])]
    m.windows['m1plus_tenpreamp'] = second = 0x20002000; m.calls = []
    m.call(PSYMS['pod_open_tenpreamp'], count=1 << 30)
    expect(('window_close', first) in m.calls and (second, O['EVT_DESTROY']) in m.bound, 'a second Preamp page closes the first and binds its own destroy')
    m.call(fn1, a0=c1, count=1 << 30); m.calls = []
    fn, c = m.bound[(m.widgets['pod_row4'], O['EVT_CLICK'])]
    m.call(fn, a0=c, count=1 << 30)
    expect(rec_fields(m.fs[STATE])[1] == 3 and ('navigator_back',) in m.calls, '... the first one\'s late destroy left the second working: a tap picks and goes back')
    fn2, c2 = m.bound[(second, O['EVT_DESTROY'])]
    m.call(fn2, a0=c2, count=1 << 30); m.calls = []
    m.call(fn, a0=c, count=1 << 30)
    expect(not [x for x in m.calls if x[0] in ('rename', 'navigator_back')], '... and after its own destroy a tap does nothing')
    m = demo_machine()
    for i in range(14): m.widget(f'pod_row{i}'); m.widget(f'pod_check{i}')
    m.call(PSYMS['pod_open_tenpreamp'], count=1 << 30)
    expect(not [x for x in m.bound if x[1] == O['EVT_CLICK']], 'a preamp page without its value label is not ours: nothing bound')


def spage(files=(), state=None, flag=1):
    """The 10-Band editor (tpage) with the card's EQ folder holding files [(name, bytes)], the Save as Preset row bound and no keyboard window (the test calls what the keyboard would)."""
    m = demo_machine()
    m.bitmap_ok = True
    m.folder(EQ_DIR)
    for fn, data in files: m.put(f'{EQ_DIR}/{fn}', data)
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag])); m.setword(pod.DATA['EQ_MODE'][0], 4)
    if state is not None: m.fs[STATE] = state
    m.windows['m1plus_keyboard'] = 0
    for n in TBW: m.widget(n)
    m.count()
    m.opened = m.call(PSYMS['tenband_open'], count=1 << 40)
    m.calls = []
    return m


SAVE_CUSTOM = [3.0, 0.0, -2.5, 0.0, 0.0, 1.0, 0.0, 0.0, -4.0, 0.5]
SAVE_TEXT = ('Preamp: -3 dB\n'
             'Filter 1: ON PK Fc 31 Hz Gain 3 dB Q 1.41\nFilter 2: ON PK Fc 63 Hz Gain 0 dB Q 1.41\n'
             'Filter 3: ON PK Fc 125 Hz Gain -2.5 dB Q 1.41\nFilter 4: ON PK Fc 250 Hz Gain 0 dB Q 1.41\n'
             'Filter 5: ON PK Fc 500 Hz Gain 0 dB Q 1.41\nFilter 6: ON PK Fc 1000 Hz Gain 1 dB Q 1.41\n'
             'Filter 7: ON PK Fc 2000 Hz Gain 0 dB Q 1.41\nFilter 8: ON PK Fc 4000 Hz Gain 0 dB Q 1.41\n'
             'Filter 9: ON PK Fc 8000 Hz Gain -4 dB Q 1.41\nFilter 10: ON PK Fc 16000 Hz Gain 0.5 dB Q 1.41\n').encode()


def save_preset_tests(ctx):
    """The 10-Band editor's Save as Preset (patch/tenband.c tenband_named, patch/peqpage.c peq_save_new): a new preset file, the record and the player left alone."""
    expect = ctx.expect
    rec = tenband(SAVE_CUSTOM, 3, 9, SAVE_CUSTOM)
    m = spage(state=rec)
    fire(m, m.widgets['pod_row3'], 'EVT_CLICK')
    expect(('window_open', 'm1plus_keyboard') in m.calls and m.fs[STATE] == rec, 'the Save as Preset row opens the name entry, and the tap writes nothing')
    m.calls = []
    m.call(PSYMS['tenband_named'], m.cstr('My Curve'), count=1 << 40)
    path = f'{EQ_DIR}/My Curve.txt'
    expect(m.fs.get(path) == SAVE_TEXT, f'the curve written as an APO preset: the preamp as "Preamp: -3 dB", ten PK bands at 31 Hz .. 16 kHz, Q 1.41, 0 dB bands included ({m.fs.get(path)!r})')
    expect(f'{EQ_DIR}/.save.tmp' not in m.fs and not [c for c in m.calls if c[0] == 'rename' and c[2] == STATE],
           'written through the temp file (fsynced, parsed back, renamed over nothing); the record is not rewritten')
    expect(m.fs[STATE] == rec and not [c for c in m.calls if c[0] == 'set_equalizer_value'] and not [c for c in m.calls if c[0] == 'toast' and c[1] != 'Saved as Preset'],
           'playback unchanged: the record, the Equalizer switch and the player are left as they were')
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Saved as Preset'], 'the message box says "Saved as Preset"')
    # Auto preamp: no Preamp line; a flat curve still writes its ten bands
    m = spage(state=tenband([0.0] * 10, -1, 0))
    m.call(PSYMS['tenband_named'], m.cstr('Flat'), count=1 << 40)
    flat = m.fs.get(f'{EQ_DIR}/Flat.txt', b'').decode()
    expect(flat.startswith('Filter 1: ON PK Fc 31 Hz Gain 0 dB Q 1.41\n') and flat.count('Filter ') == 10 and 'Preamp' not in flat, f'Auto: no Preamp line, and every band at 0 dB is written ({flat[:60]!r})')
    # a preamp of 0 dB is a fixed preamp (written); a name in use, the limit and a failed write
    m = spage(files=[('Rock.txt', AUTOEQ)], state=tenband([0.0] * 10, 0, 2))
    m.call(PSYMS['tenband_named'], m.cstr('Rock'), count=1 << 40)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Name already in use'] and m.fs[f'{EQ_DIR}/Rock.txt'] == AUTOEQ and not [c for c in m.calls if c[0] == 'rename'],
           'a name in use is refused: "Name already in use", the file is as it was')
    before = sorted(m.fs)
    m.calls = []
    for t in ('   ', '.txt', ''): m.call(PSYMS['tenband_named'], m.cstr(t), count=1 << 40)
    m.call(PSYMS['tenband_named'], m.cstr('.hidden'), count=1 << 40)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Saved as Preset'], 'blank names and ".txt" are refused silently (the one toast is the ".hidden" file\'s)')
    expect(sorted(k for k in m.fs if k not in before) == [f'{EQ_DIR}/_hidden.txt'], f'a leading dot becomes "_" ({sorted(k for k in m.fs if k not in before)})')
    expect(m.fs[f'{EQ_DIR}/_hidden.txt'].startswith(b'Preamp: 0 dB\n'), f'a fixed 0 dB preamp is written ({m.fs[f"{EQ_DIR}/_hidden.txt"][:30]!r})')
    m = spage(files=[(f'p{i:02d}.txt', AUTOEQ) for i in range(64)], state=rec)
    m.call(PSYMS['tenband_named'], m.cstr('One More'), count=1 << 40)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Preset limit reached'] and f'{EQ_DIR}/One More.txt' not in m.fs, 'with 64 files on the card: "Preset limit reached", nothing written')
    m = spage(state=rec)
    m.fail.add(('rename', f'{EQ_DIR}/Fail.txt'))
    m.call(PSYMS['tenband_named'], m.cstr('Fail'), count=1 << 40)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Not saved'] and f'{EQ_DIR}/Fail.txt' not in m.fs and f'{EQ_DIR}/.save.tmp' not in m.fs and m.fs[STATE] == rec and not [c for c in m.calls if c[0] == 'set_equalizer_value'],
           'a failed write: "Not saved", no file, no temp file, the record and the player as they were')


def layout_tenband_tests(ctx):
    """The three pages under demo's own layouter (as test/pod/settings.py does the cards pages) and the assets against the model."""
    expect, P = ctx.expect, pod_pages
    settings = sibling('settings')
    # the editor
    page = P.TENBAND_PAGE
    t = settings.page_tree(page)
    placed, end = ST.layout(page.layout)
    m = settings.SL(page)
    names = ['pod_top', 'pod_row0', 'pod_gap0', 'pod_graph', 'pod_regionbox', 'pod_sliders', 'pod_gap1', 'pod_row1', 'pod_row2', 'pod_gap2', 'pod_row3', 'pod_note0', 'pod_end']
    got = [(nm,) + m.box(nm) for nm in names]
    expect([(x, y, h) for _, x, y, _, h in got] == [(0, y, ST.item_h(it)) for it, y in placed], 'the editor: demo\'s layouter stacks the model\'s column (Curve card, graph, region box, sliders, Preamp and Reset card, Save as Preset card, DSD note)')
    expect(m.vh() == end == ST.CM + 4 * ST.ROW_H + 3 * ST.GAP_H + ST.GRAPH_H + ST.REGION_H + ST.SLIDERS_H + ST.item_h(P.DSD_NOTE) + ST.END_H, f'virtual_h {m.vh()} is the model\'s {end}')
    expect(ST.pieces(page.layout) == ['single', 'top', 'bot', 'single'] and ST.item_h(P.SLIDERS) == ST.SLIDERS_H == TBM.H == O['TB_H'], 'Curve is a card of its own, Preamp and Reset one card, Save as Preset a card of its own')
    sv = t.find('pod_scrollview')
    dsd = t.find('pod_note0')   # the grey one-line note at the end, after the Preamp / Reset card
    expect(page.layout[-1] is P.DSD_NOTE and dsd is not None and dsd.get('visible') != 'false' and pod_i18n.shown_english(t.find('pod_note0_t')) == 'EQ is not applied to DSD.' and dsd.y >= t.find('pod_row2').y + ST.ROW_H
           and P.PEQ_PAGE.layout[-1] is P.DSD_NOTE and P.peq_items(0)[-1] is P.DSD_NOTE and P.peq_items(2)[-1] is P.DSD_NOTE, 'the editor and the Equalizer page end with the grey note "EQ is not applied to DSD."')
    kids = [c.name for c in sv.children]
    expect(kids == names, f'the asset\'s column ({kids})')
    rg = sv.children[4].children
    expect(len(rg) == 1 and rg[0].name == 'pod_region' and rg[0].type == 'label' and rg[0].get('text') == '' and rg[0].get('sensitive') == 'false' and rg[0].h == ST.REGION_H and rg[0].get('style:normal:font_size') == '18'
           and all(rg[0].get(f'style:{s}:text_color') == ST.GREY for s in ('normal', 'disable', 'focused')) and rg[0].x + rg[0].w <= ST.CM + ST.CARD_W and ST.REGION_H - 18 >= 2 * 6,
           'the region line: an empty 18 px grey label in REGION_H (6 px clear above and below) between the graph and the sliders')
    sl = sv.children[5]
    expect(sl.type == 'view' and sl.get('sensitive') != 'false' and sl.h == ST.SLIDERS_H and all(sl.get(f'style:{s}:bg_color') == '#00000000' for s in ('normal', 'disable', 'focused')),
           'the slider view takes touches and is transparent (the bitmaps drawn in its before-paint show under the labels)')
    labs = {c.name: c for c in sl.children}
    expect(len(labs) == 20 and all(c.get('sensitive') == 'false' and c.type == 'label' for c in labs.values()), 'twenty labels, none sensitive: a value and a frequency a column')
    ok = True
    for c in range(10):
        v, f = labs[f'pod_sl_v{c}'], labs[f'pod_sl_f{c}']
        mid = ST.CM + TBM.center_x(c)
        ok = ok and v.x + v.w // 2 == mid and f.x + f.w // 2 == mid and (v.y, v.h) == (TBM.VAL_Y, TBM.VAL_H) and (f.y, f.h) == (TBM.FREQ_Y, TBM.FREQ_H) and v.w == f.w == TBM.LABEL_W \
            and v.get('text') == '' and f.get('text') == P.SLIDER_TEXTS[c] and v.get('style:normal:font_size') == str(TBM.LABEL_PX) and v.get('style:normal:text_color') == '#8A8A8A' and v.get('style:normal:text_align_h') == 'center'
    expect(ok, 'each value label sits over its column (empty in the asset), each frequency label under it (31 .. 16k), 11 px grey, centred')
    expect(TBM.thumb_y(12) >= TBM.VAL_Y + TBM.VAL_H and TBM.thumb_y(-12) + TBM.THUMB_H <= TBM.FREQ_Y and TBM.X0 * 2 + 10 * TBM.COL_W == 300 and all(v == O[k] for k, v in (
        ('TB_W', TBM.W), ('TB_H', TBM.H), ('TB_CARD_X', TBM.CARD_X), ('TB_R', TBM.R), ('TB_COLS', TBM.COLS), ('TB_COL_W', TBM.COL_W), ('TB_X0', TBM.X0), ('TB_Y0', TBM.Y0), ('TB_SPAN', TBM.SPAN), ('TB_PX_DB', TBM.PX_DB),
        ('TB_TRACK_W', TBM.TRACK_W), ('TB_THUMB_W', TBM.THUMB_W), ('TB_THUMB_H', TBM.THUMB_H), ('TB_VAL_Y', TBM.VAL_Y), ('TB_VAL_H', TBM.VAL_H), ('TB_FREQ_Y', TBM.FREQ_Y), ('TB_FREQ_H', TBM.FREQ_H),
        ('TB_PILL_W', TBM.PILL_W), ('TB_PILL_H', TBM.PILL_H), ('TB_LABEL_W', TBM.LABEL_W), ('TB_LABEL_PX', TBM.LABEL_PX))),
           'the thumbs at the ends clear the values and the frequencies; the model\'s numbers are patch/offsets.inc\'s')
    rows = [c for c in sv.children if c.name.startswith('pod_row')]
    cur, pre, rst, sav = rows
    lab = lambda r, i: next(c for c in r.children if c.name == f'pod_label{i}')
    expect([pod_i18n.shown_english(lab(r, i)) for i, r in enumerate(rows)] == ['Curve', 'Preamp', 'Reset', 'Save as Preset'] and all(r.get('sensitive') != 'false' and r.get('visible') != 'false' for r in rows)
           and [(r.get('style:normal:bg_image'), r.get('style:pressed:bg_image')) for r in rows] == [('pod_cd_single', 'pod_cd_single_down'), ('pod_cd_top', 'pod_cd_top_down'), ('pod_cd_bot', 'pod_cd_bot_down'), ('pod_cd_single', 'pod_cd_single_down')],
           'the rows Curve, Preamp, Reset, Save as Preset: shown and tappable, their card pieces')
    chev = lambda r: [c for c in r.children if c.name == 'pod_chevron']
    expect(len(chev(cur)) == len(chev(pre)) == 1 and not chev(rst) and not chev(sav) and not [c for r in rows for c in r.children if c.name == 'pod_icon'] and [bool([c for c in r.children if c.name == 'pod_hair']) for r in rows] == [False, True, False, False],
           'chevrons on Curve and Preamp, none on Reset or Save as Preset; no glyphs; a hairline between Preamp and Reset')
    vx, vw = ST.wvalue_box()
    vals = [next(c for c in r.children if c.name == f'pod_value{i}') for i, r in enumerate(rows[:2])]
    lx, lw = ST.label_box('wvalue', False)
    expect(all((v.x, v.w) == (vx, vw) and v.get('style:normal:text_align_h') == 'right' and v.get('style:normal:text_color') == '#AAAAAA' and v.get('sensitive') == 'false' for v in vals) and vx + vw == ST.chevron_left() - ST.VALUE_GAP
           and all((lab(r, i).x, lab(r, i).w) == (lx, lw) for i, r in enumerate(rows[:2])) and lx + lw + ST.VALUE_LABEL_GAP == vx, 'the grey values are PREAMP_W wide, right aligned before the chevron, the labels end before them')
    expect(P.PAGES[P.TENBAND_PAGE_INDEX] is page and page.rows == [] and page.title == '10-Band EQ' and t.find('label_title') is not None and P.row_kind(P.TB_RESET) == 'plain' and P.row_kind(P.TB_SAVE) == 'plain' and P.row_kind(P.TB_CURVE) == 'wvalue', 'page 50, no exported rows, the title; Reset and Save as Preset are plain')

    # the Curve page
    page = P.TENCURVE_PAGE
    t = settings.page_tree(page)
    m = settings.SL(page)
    names = ['pod_top'] + [f'pod_row{i}' for i in range(10)] + ['pod_end']
    placed, end = ST.layout(page.layout)
    expect([(x, y, h) for _, x, y, _, h in [(nm,) + m.box(nm) for nm in names]] == [(0, y, ST.item_h(it)) for it, y in placed] and m.vh() == end == ST.CM + 10 * ST.ROW_H + ST.END_H, 'the Curve page: ten 52 px rows in one card')
    sv = t.find('pod_scrollview')
    rows = [c for c in sv.children if c.name.startswith('pod_row')]
    expect([pod_i18n.shown_english(next(c for c in r.children if c.name == f'pod_label{i}')) for i, r in enumerate(rows)] == list(P.TENCURVE_NAMES) == ['Flat', 'Pop', 'Rock', 'Dance', 'Blues', 'Metal', 'Vocal', 'Classical', 'Jazz', 'Custom']
           and [r.get('style:normal:bg_image') for r in rows] == ['pod_cd_top'] + ['pod_cd_mid'] * 8 + ['pod_cd_bot'] and all(next(c for c in r.children if c.name == f'pod_check{i}').get('visible') == 'false' for i, r in enumerate(rows))
           and not [c for r in rows for c in r.children if c.name in ('pod_chevron', 'pod_icon', f'pod_value{rows.index(r)}')], 'the ten curves, in the record\'s order, one card, a hidden check each, no chevron, no glyph, no value')
    expect(P.PAGES[P.TENCURVE_PAGE_INDEX] is page and page.rows == [] and page.title == 'Curve' and t.find('label_title') is not None, 'page 55, no exported rows, titled Curve')

    # the Preamp page
    page = P.TENPREAMP_PAGE
    t = settings.page_tree(page)
    m = settings.SL(page)
    names = ['pod_top', 'pod_row0', 'pod_note0'] + [f'pod_row{i}' for i in range(1, 14)] + ['pod_end']
    placed, end = ST.layout(page.layout)
    expect([(x, y, h) for _, x, y, _, h in [(nm,) + m.box(nm) for nm in names]] == [(0, y, ST.item_h(it)) for it, y in placed] and m.vh() == end == ST.CM + 14 * ST.ROW_H + ST.item_h(page.layout[1]) + ST.END_H, 'the Preamp page: Auto in a card of its own, the grey note under it, then the thirteen rows in a second card')
    sv = t.find('pod_scrollview')
    rows = [c for c in sv.children if c.name.startswith('pod_row')]
    auto = rows[0]
    expect(pod_i18n.shown_english(next(c for c in auto.children if c.name == 'pod_label0')) == 'Auto' and any(c.name == 'pod_value0' and (c.x, c.w) == ST.curve_box() for c in auto.children)
           and not [c for r in rows[1:] for c in r.children if c.name.startswith('pod_value') or c.name in ('pod_chevron', 'pod_icon')] and [r.get('style:normal:bg_image') for r in rows] == ['pod_cd_single', 'pod_cd_top'] + ['pod_cd_mid'] * 11 + ['pod_cd_bot']
           and all(next(c for c in r.children if c.name == f'pod_label{i}').get('text') == '' for i, r in enumerate(rows) if i) and all(any(c.name == f'pod_check{i}' and c.get('visible') == 'false' for c in r.children) for i, r in enumerate(rows)),
           'Auto with a grey value before its check, then thirteen rows with no text in the asset (the payload writes them), a hidden check each, no chevrons')
    note = t.find('pod_note0')   # the grey note under Auto's card: what Auto is for, shown, between Auto and the first fixed value (its label wraps to two lines)
    expect(note is not None and note.get('visible') != 'false' and pod_i18n.shown_english(t.find('pod_note0_t')) == "Auto reduces the level to help prevent distortion from EQ boosts." and note.y >= rows[0].y + rows[0].h
           and note.y + note.h <= rows[1].y and isinstance(page.layout[1], P.Note) and page.layout[1].lines == 2 and not isinstance(page.layout[-1], P.Note), 'the Preamp page has its two-line note directly under Auto\'s card, before the second card')
    expect(P.PAGES[P.TENPREAMP_PAGE_INDEX] is page and P.TENPREAMP_PAGE_INDEX == P.PAGES.index(P.PEQBAND_PAGE) - 2 == 56 and page.rows == [] and page.title == 'Preamp' and P.TENPREAMP_STEPS == 13, 'page 56, the editor\'s last (AutoEq, 53, and the band page, 54, follow), no exported rows, titled Preamp')


def retire_tests(ctx):
    expect = ctx.expect
    stock_demo = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', pod.DEMO), 'rb').read()
    built = open(DEMO, 'rb').read()
    w = lambda b, a: struct.unpack_from('<I', b, pod.fileoff(b, a))[0]
    row, stub = pod.EQ_ROW, PSYMS['pod_eq_site']
    expect(all(w(stock_demo, a) == old and (a in (row, row + 4) or w(built, a) == old) for a, old, _ in pod.EQ_PINS), 'every pinned word of the Play Settings Equalizer row is stock\'s in the stock demo and unchanged in the build (but the two edited)')
    expect(w(stock_demo, row) == 0x8f84a708 and w(stock_demo, row + 4) == 0x1000ff93 and w(built, row) == pod.j(stub) and w(built, row + 4) == 0 and w(built, row + 8) == w(stock_demo, row + 8)
           and w(built, row - 4) == w(stock_demo, row - 4) and w(built, row + 12) == w(stock_demo, row + 12), 'the All Playback Settings Equalizer row @0x4a0210: `lw a0; b navigator_to` became `j pod_eq_site; nop`, its neighbours are stock\'s')
    expect([w(built, stub + 4 * i) for i in range(6)] == [pod.jal(PSYMS['peq_open'], stub), 0, 0x3c1c0000 | pod.GP >> 16, 0x379c0000 | pod.GP & 0xffff, pod.j(pod.EQ_ROW_RESUME), 0],
           'pod_eq_site: jal peq_open, $gp set, then j 0x4a0070 (the click handler\'s epilogue: s0-s2, ra and the frame come from stock\'s own stack slots)')
    expect(MANIFEST['hook_eq_row'] == {'addr': row, 'target': stub}, 'the manifest lists the Equalizer row hook')
    expect(w(built, 0x4d11d0) == w(stock_demo, 0x4d11d0), 'the page\'s init dispatch (strcmp "playset/equalizer_page" @0x4d11d0) is untouched: stock\'s page still exists, nothing opens it')


# ---- the EQ of each output (patch/peqout.c)
OUT_FILE = '/mnt/data/m1plus/playback-eq-output'
SLOT = {0: '/mnt/data/m1plus/playback-eq-headphones', 1: '/mnt/data/m1plus/playback-eq-lineout', 2: '/mnt/data/m1plus/playback-eq-usb'}
LO_BYTE = pod.DATA['LINEOUT_FLAG'][0]


def out_machine(state=None, flag=1, way=0, lo=0):
    m = demo_machine()
    m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([flag])); m.setword(pod.DATA['EQ_MODE'][0], 4)
    if state is not None: m.fs[STATE] = state
    m.out_way = way; m.u.mem_write(LO_BYTE, bytes([lo]))
    return m


def out_set(m, way=0, lo=0): m.out_way = way; m.u.mem_write(LO_BYTE, bytes([lo]))
def out_sync(m, notify=1): m.calls = []; return m.call(PSYMS['peqout_sync'], notify, count=1 << 30)
def out_rec(m):
    r = m.fs[OUT_FILE]
    return struct.unpack_from('<4i', r, 8), r[:8]
def osent(m): return [c for c in m.calls if c[0] in ('write_int_config', 'set_equalizer_value')]
def eq_flag(m): return m.u.mem_read(pod.DATA['EQ_FLAG'][0], 1)[0]


def output_tests(ctx):
    expect = ctx.expect
    rock = tenband(CURVES[2], 3, 2)
    pop = tenband(CURVES[1], -1, 1)
    # detection: the jacks, Line Out on the jacks, USB audio (also with Line Out set), Bluetooth (the headphone EQ)
    m = out_machine(rock)
    cur = lambda: m.call(PSYMS['peqout_current'], count=1 << 20)
    expect(cur() == 0, 'jacks, Line Out off: Headphones')
    out_set(m, 0, 1); expect(cur() == 1, 'jacks with the Line Out byte set: Line Out')
    out_set(m, 2, 1); expect(cur() == 2, 'USB audio (output way 2): USB DAC, even with the Line Out byte set')
    out_set(m, 1, 0); expect(cur() == 0, 'Bluetooth (output way 1) has no EQ of its own: Headphones')
    out_set(m, 1, 1); expect(cur() == 0, 'Bluetooth with the Line Out byte set: still Headphones')

    # the first run only notes the output (the migration: the one record plays everywhere): no switch, no slot, nothing sent
    m = out_machine(rock, flag=1)
    r = out_sync(m)
    expect(r == 0 and m.fs[STATE] == rock and out_rec(m) == ((0, 1, 1, 1), b'M1PEQO1\0') and not osent(m) and not [k for k in m.fs if k.startswith('/mnt/data/m1plus/playback-eq-') and k != OUT_FILE],
           'first run on the jacks: the record and the switch stay, the output file notes Headphones with the switch on for every output, no slot is written')
    expect(m.call(PSYMS['peqout_sync'], 1, count=1 << 30) == 0 and m.fs[STATE] == rock, 'an unchanged output changes nothing')

    # to Line Out: the old output's EQ is filed, the record stays (no Line Out slot yet: it starts as what plays), the player is told
    out_set(m, 0, 1); r = out_sync(m)
    expect(r == 1 and m.fs[SLOT[0]] == rock and m.fs[STATE] == rock and out_rec(m)[0] == (1, 1, 1, 1) and SLOT[1] not in m.fs, 'to Line Out: Headphones\' EQ filed, the record unchanged (no Line Out slot), the owner is Line Out')
    expect(osent(m) == [('set_equalizer_value', 4, 1)], f'the page thread tells the player to reread ({osent(m)})')
    # an edit at Line Out (the Pop curve, Equalizer off), then back to the jacks: the Rock curve returns and the switch comes on again
    m.fs[STATE] = pop; m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([0]))
    out_set(m, 0, 0); r = out_sync(m)
    expect(r == 1 and m.fs[STATE] == rock and m.fs[SLOT[1]] == pop and out_rec(m)[0] == (0, 1, 0, 1), 'back to Headphones: Line Out\'s Pop filed, the Rock record plays again, Line Out\'s switch kept off')
    expect(eq_flag(m) == 1 and osent(m) == [('write_int_config', 1, 'PLAYSET', 'EQFLAG'), ('set_equalizer_value', 4, 1)], f'Headphones had the switch on: stock\'s flag is set again and saved, then the player is told ({osent(m)})')
    out_set(m, 0, 1); r = out_sync(m)
    expect(r == 1 and m.fs[STATE] == pop and eq_flag(m) == 0 and osent(m) == [('write_int_config', 0, 'PLAYSET', 'EQFLAG'), ('set_equalizer_value', 4, 0)], f'Line Out again: Pop plays and the switch is off ({osent(m)})')
    # USB, then the notify flag: a track start (notify 0) swaps the record without telling the player when the switch does not change
    out_set(m, 2, 0); m.u.mem_write(pod.DATA['EQ_FLAG'][0], bytes([1])); m.fs[SLOT[2]] = rock; m.fs[STATE] = pop
    r = out_sync(m, 0)
    expect(r == 1 and m.fs[STATE] == rock and m.fs[SLOT[1]] == pop and out_rec(m)[0][0] == 2, 'to a USB DAC with a slot: Line Out\'s EQ filed, the USB slot plays')
    expect(osent(m) == [], 'no notify and the switch unchanged: the player is not sent a command from a track start or a restart')
    # the kill switch: nothing
    m = out_machine(rock); out_sync(m); m.present.add(KILL); out_set(m, 0, 1)
    expect(out_sync(m) == 0 and out_rec(m)[0][0] == 0 and m.fs[STATE] == rock, 'with /mnt/mmc/m1plus-off the output is not followed')
    # a slot that cannot be written keeps the old EQ, the owner and the record, and the next call tries again
    m = out_machine(rock); out_sync(m); out_set(m, 0, 1); m.fail.add(('rename', SLOT[0]))
    expect(out_sync(m) == 0 and m.fs[STATE] == rock and out_rec(m)[0][0] == 0 and not osent(m), 'the old output\'s EQ cannot be filed: nothing changes')
    m.fail.discard(('rename', SLOT[0]))
    expect(out_sync(m) == 1 and m.fs[SLOT[0]] == rock and out_rec(m)[0][0] == 1, 'the next call tries again and switches')
    # the owner cannot be written after the new slot replaced the record: the record goes back, so no output's curve is filed under another
    m = out_machine(rock); out_sync(m); m.fs[SLOT[1]] = pop; out_set(m, 0, 1); m.fail.add(('rename', OUT_FILE))
    expect(out_sync(m) == 0 and m.fs[STATE] == rock and out_rec(m)[0][0] == 0, 'a failed owner write: the record stays Headphones\' (rolled back), the owner is Headphones')
    m.fail.discard(('rename', OUT_FILE))
    out_set(m, 0, 0); out_sync(m); out_set(m, 0, 1)
    expect(out_sync(m) == 1 and m.fs[SLOT[0]] == rock and m.fs[STATE] == pop, 'back and forth after the failure: the headphone slot still holds the headphone curve')
    # a missing or unreadable playing record is never filed over a slot
    m = out_machine(None, flag=0); out_sync(m); m.fs[SLOT[1]] = pop; out_set(m, 0, 1); r = out_sync(m)
    expect(r == 1 and SLOT[0] not in m.fs and m.fs[STATE] == pop, 'no record while on Headphones: nothing is filed, Line Out\'s slot plays')
    m = out_machine(rock); out_sync(m); m.fs[SLOT[1]] = pop; m.fs[STATE] = b'junk'; out_set(m, 0, 1); r = out_sync(m)
    expect(r == 1 and SLOT[0] not in m.fs and m.fs[STATE] == pop, 'an unreadable record is not filed over the output\'s slot either')
    # an unreadable output file is a first run
    m = out_machine(rock); m.fs[OUT_FILE] = b'junk'; out_set(m, 0, 1); r = out_sync(m)
    expect(r == 0 and out_rec(m)[0][0] == 1 and m.fs[STATE] == rock, 'a damaged output file starts again from the output playing now')

    # the hooks that run it: stock's save_start_player (patch/radio.c; mclStartPlayer's hook and the status bar's timer are in radio.py and lineout.py)
    m = out_machine(rock); out_sync(m); out_set(m, 0, 1)
    m.fs[SLOT[1]] = pop
    m.calls = []
    m.call(PSYMS['rd_save_start'], 0, count=1 << 30)
    expect(m.fs[STATE] == pop and out_rec(m)[0][0] == 1, 'save_start_player (an output changed under a track): the new output\'s EQ is in place before stock restarts the track')

    # the page: the grey line says which output it edits and follows a change when the page is back in front
    pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=rock)
    lines = ptext(pg, 'pod_note0_t')
    expect(lines == ['For Headphones'], f'the Equalizer page says "For Headphones" under the switch ({lines})')
    for way, lo, want in ((0, 1, 'For Line Out'), (2, 0, 'For USB DAC'), (1, 0, 'For Headphones')):
        pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=rock); out_set(pg, way, lo); pg.calls = []
        fn, c = pg.bound[(pg.window, O['EVT_WINDOW_TO_FG'])]
        pg.call(fn, a0=c, count=1 << 30)
        expect(ptext(pg, 'pod_note0_t')[-1:] == [want], f'back in front with way {way}, Line Out {lo}: "{want}"')

    # an Equalizer page left open across an output change edits the output playing now, never the old output's copy
    pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=rock); pg.fs[SLOT[2]] = pop; out_set(pg, 2, 0); pg.calls = []
    pg.call(PSYMS['peqout_sync'], 1, count=1 << 30)
    expect(ptext(pg, 'pod_note0_t')[-1:] == ['For USB DAC'] and pg.fs[STATE] == pop, f'an open page follows a notified output change: the grey line says USB DAC ({ptext(pg, "pod_note0_t")})')
    tap(pg, 1)
    expect(pg.fs[STATE] == pop and pg.fs[SLOT[0]] == rock, '10-Band EQ tapped on the stale-looking page: USB keeps its Pop curve, the headphone slot keeps Rock')
    # the same with no notify reaching the page (the player thread's call switched the record under it)
    pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=rock); pg.fs[SLOT[2]] = pop; out_set(pg, 2, 0)
    pg.call(PSYMS['peqout_sync'], 0, count=1 << 30); tap(pg, 1)
    expect(pg.fs[STATE] == pop, '10-Band EQ tapped after a switch the page was never told of: the record of the output playing now is kept')
    pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=rock); pg.fs[SLOT[2]] = pop; out_set(pg, 2, 0)
    pg.calls = []; pg.call(PSYMS['peqout_sync'], 0, count=1 << 30)
    expect(ptext(pg, 'pod_note0_t') == [] and pg.fs[STATE] == pop, 'a switch without notify (the player thread) swaps the record but leaves the page to the UI thread')
    pg.call(PSYMS['peqout_sync'], 1, count=1 << 30)
    expect(ptext(pg, 'pod_note0_t')[-1:] == ['For USB DAC'], f'the next UI tick after a switch without notify shows the new output ({ptext(pg, "pod_note0_t")})')
    pg.call(PSYMS['peqout_sync'], 1, count=1 << 30); pg.call(PSYMS['peqout_sync'], 1, count=1 << 30)
    expect(pg.fs[STATE] == pop, 'later ticks change nothing more')

    # Delete Preset clears every output's slot that names the file, and that output's switch, as it does the playing record
    filed = pack_state(1, pack_preset(AUTOEQ_BANDS, preamp=-6.2), b'HD 600.txt')
    pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=filed); pg.fs[SLOT[2]] = rock; out_set(pg, 2, 0); pg.call(PSYMS['peqout_sync'], 1, count=1 << 30)
    expect(pg.fs[SLOT[0]] == filed and out_rec(pg)[0][0] == 2 and out_rec(pg)[0][1] == 1, 'setup: Headphones names the file with the switch on, USB plays Rock')
    pg.calls = []; ok = pg.call(PSYMS['peq_delete'], pg.cstr('HD 600.txt'), count=1 << 30)
    expect(ok == 1 and pg.fs[STATE] == rock and NAME_OF(pg.fs[SLOT[0]]) == b'' and struct.unpack_from('<i', pg.fs[SLOT[0]], 8)[0] == 0 and out_rec(pg)[0][1] == 0
           and not [c for c in pg.calls if c[0] == 'toast'], 'delete on USB: the headphone slot points at the 10-Band EQ and its switch is off, the USB record is untouched')
    out_set(pg, 0, 0); pg.call(PSYMS['peqout_sync'], 1, count=1 << 30)
    st = pg.fs[STATE]
    expect(struct.unpack_from('<i', st, 8)[0] == 0 and eq_flag(pg) == 0, 'back on Headphones: the deleted preset does not return and the Equalizer stays off')
    pg = page([('HD 600.txt', AUTOEQ)], flag=1, state=filed); pg.fs[SLOT[2]] = rock; out_set(pg, 2, 0); pg.call(PSYMS['peqout_sync'], 1, count=1 << 30)
    pg.fail.add(('rename', SLOT[0])); pg.calls = []; pg.call(PSYMS['peq_delete'], pg.cstr('HD 600.txt'), count=1 << 30)
    expect([c[1] for c in pg.calls if c[0] == 'toast'] == ['Not saved'], 'a slot that cannot be rewritten: "Not saved"')


def output_edit_tests(ctx):
    """An edit session that outlives an output change: Don't Save and Save act on the output that received the edits."""
    expect = ctx.expect
    pop = tenband(CURVES[1], -1, 1)
    orig = unpack_preset(pack_preset(AUTOEQ_BANDS, preamp=-6.2))

    def session():
        m = epage([(HD, AUTOEQ)], state=None, flag=1)
        out_sync(m)                                  # Headphones own the record
        open_band(m, 2); drag_to(m, 1, 0.9)          # an unsaved edit on Headphones
        edited = rec_preset(m)
        m.fs[SLOT[2]] = pop                          # USB has its own profile (Pop)
        out_set(m, 2, 0); out_sync(m)                # the switch to USB (the status bar's timer)
        return m, edited

    def slot_preset(m, k): return unpack_preset(m.fs[SLOT[k]][16:16 + 992])

    m, edited = session()
    expect(edited['bands'][1][3] != orig['bands'][1][3] and m.fs[STATE] == pop and slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3], 'setup: the edit is filed under Headphones, USB plays Pop')
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(m.fs[STATE] == pop and hsent(m) == 0 and went_back(m) and not toasts(m), f"Don't Save after switching to USB: USB's Pop and its playback are untouched ({toasts(m)})")
    expect(slot_preset(m, 0)['bands'][:4] == orig['bands'][:4] and NAME_OF(m.fs[SLOT[0]]) == HD.encode() and m.fs[HD_PATH] == AUTOEQ, "the Headphones slot has the file's own preset again, the file is untouched")
    out_set(m, 0, 0); out_sync(m)
    expect(rec_preset(m)['bands'][:4] == orig['bands'][:4] and NAME_OF(m.fs[STATE]) == HD.encode(), 'back on Headphones: the discarded edit is gone, the original preset plays')

    # the slot cannot be rewritten: "Not saved", the page stays unsaved, nothing else changed
    m, edited = session()
    ask(m); m.fail.add(('rename', SLOT[0])); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(toasts(m) == ['Not saved'] and not went_back(m) and m.fs[STATE] == pop and slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3], f"Don't Save with a failing slot write: the message, the page stays, USB and the slot untouched ({toasts(m)})")
    m.hist.clear(); ask(m)
    expect(dialog_up(m), 'and the edit is still unsaved: Back asks again')
    m.fail.discard(('rename', SLOT[0])); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(went_back(m) and slot_preset(m, 0)['bands'][:4] == orig['bands'][:4], 'tried again, it works')

    # a slot that no longer names the file (another preset was chosen for Headphones meanwhile) is left alone
    m, edited = session()
    other = pack_state(1, pack_preset([(1, 0, 1000, 1.0, 1.0)]), b'Other.txt'); m.fs[SLOT[0]] = other
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(went_back(m) and m.fs[SLOT[0]] == other and m.fs[STATE] == pop, "Don't Save: a slot naming another preset is not touched")

    # Save after the switch: the file is written, USB keeps Pop, the Headphones slot has the saved preset
    m, edited = session()
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(went_back(m) and m.fs[HD_PATH] != AUTOEQ and m.fs[STATE] == pop and hsent(m) == 0, 'Save after switching to USB: the file is written, USB keeps Pop and is not told')
    expect(slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3] and NAME_OF(m.fs[SLOT[0]]) == HD.encode(), 'the Headphones slot plays the saved preset')
    # USB already plays this file: its record takes the saved preset
    m, edited = session()
    m.fs[STATE] = pack_state(1, pack_preset(AUTOEQ_BANDS, preamp=-6.2), HD.encode())
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(NAME_OF(m.fs[STATE]) == HD.encode() and rec_preset(m)['bands'][1][3] == edited['bands'][1][3], 'Save while USB plays the same file: its record follows the saved file')

    # a live edit after the switch belongs to the new output: Don't Save then restores USB's record from the file
    m, edited = session()
    open_band(m, 2); drag_to(m, 1, 0.1, t0=5000)
    expect(NAME_OF(m.fs[STATE]) == HD.encode(), 'a live edit on USB makes the edit play on USB')
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(went_back(m) and rec_preset(m)['bands'][:4] == orig['bands'][:4], "Don't Save: the session belongs to USB now, its record has the file's preset")
    expect(slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3], 'the Headphones slot keeps the earlier edit (the user edited there and left it)')

    # a page reopened over earlier unsaved edits: they belong to the output playing now
    eb = list(AUTOEQ_BANDS); eb[1] = (1, 0, 2000, 4.0, 1.41)
    m = epage([(HD, AUTOEQ)], state=pack_state(1, pack_preset(eb, preamp=-6.2), HD.encode()), flag=1)
    out_sync(m)
    m.fs[SLOT[2]] = pop; out_set(m, 2, 0); out_sync(m)
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(went_back(m) and m.fs[STATE] == pop and slot_preset(m, 0)['bands'][:4] == orig['bands'][:4], f"reopened edits, then USB: Don't Save restores the Headphones slot and leaves USB's Pop ({toasts(m)})")

    # a Don't Save whose record write fails keeps the session's output: after a switch the next Don't Save still targets Headphones
    m = epage([(HD, AUTOEQ)], state=None, flag=1)
    out_sync(m); open_band(m, 2); drag_to(m, 1, 0.9)
    ask(m); m.fail.add(('rename', STATE)); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(toasts(m) == ['Not saved'] and not went_back(m), "setup: the first Don't Save fails")
    m.fail.discard(('rename', STATE))
    m.fs[SLOT[2]] = pop; out_set(m, 2, 0); out_sync(m)
    ask(m); m.hist.clear(); fire(m, m.bw['pq_item2'], 'EVT_CLICK')
    expect(went_back(m) and m.fs[STATE] == pop and slot_preset(m, 0)['bands'][:4] == orig['bands'][:4], f"after the failure and a switch to USB: Don't Save restores Headphones, USB keeps Pop ({toasts(m)})")

    # Save As whose slot write fails: "Not saved", no new file, the page stays on the old one with the edit unsaved
    m, edited = session()
    ask(m); fire(m, m.bw['pq_item1'], 'EVT_CLICK'); m.fail.add(('rename', SLOT[0])); m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('Copy'), count=1 << 40)
    fire(m, m.band_win, 'EVT_WINDOW_TO_FG')
    expect(toasts(m) == ['Not saved'] and f'{EQ_DIR}/Copy.txt' not in m.fs and not went_back(m) and m.fs[HD_PATH] == AUTOEQ, f'a failed Save As: the message, no file, the page stays ({toasts(m)})')
    expect(not any(c[0] == 'widget_set_text_utf8' and u8(c[2]).startswith('Copy') for c in m.hist), 'and the page never showed the new name')
    ask(m)
    expect(dialog_up(m), 'and the edit is still unsaved: Back asks again')
    expect(NAME_OF(m.fs[SLOT[0]]) == HD.encode() and slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3], "and Headphones, the session's owner, keep the edit in their slot")
    m.fail.discard(('rename', SLOT[0])); fire(m, m.bw['pq_item1'], 'EVT_CLICK'); m.hist.clear(); m.call(PSYMS['peqpage_named'], m.cstr('Copy'), count=1 << 40)
    fire(m, m.band_win, 'EVT_WINDOW_TO_FG')
    expect(not toasts(m) and f'{EQ_DIR}/Copy.txt' in m.fs and m.fs[HD_PATH] == AUTOEQ and NAME_OF(m.fs[SLOT[0]]) == b'Copy.txt' and slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3] and m.fs[STATE] == pop, f'a second Save As, the fault cleared: the new file, the slot names it, USB keeps Pop ({toasts(m)})')
    m.hist.clear(); ask(m)
    expect(went_back(m) and not dialog_up(m), 'the new file is saved: Back leaves without asking')
    # Save whose slot write fails: the page does not close, the file is written, the edit counts as unsaved
    m, edited = session()
    ask(m); m.fail.add(('rename', SLOT[0])); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(toasts(m) == ['Not saved'] and not went_back(m) and m.fs[HD_PATH] != AUTOEQ, f'a failed Save record write: the message, the page stays ({toasts(m)})')
    m.hist.clear(); ask(m)
    expect(dialog_up(m), 'and the slot was not written: Back asks again')
    m.fail.discard(('rename', SLOT[0])); m.hist.clear(); fire(m, m.bw['pq_item0'], 'EVT_CLICK')
    expect(went_back(m) and not toasts(m) and slot_preset(m, 0)['bands'][1][3] == edited['bands'][1][3] and NAME_OF(m.fs[SLOT[0]]) == HD.encode() and m.fs[STATE] == pop, f'a second Save, the fault cleared: the slot has the saved preset, USB keeps Pop ({toasts(m)})')

    # Delete Preset reaches every output's slot: the slots that name the file point at the 10-Band EQ with that output's switch off, others stay
    m = ppage([(HD, AUTOEQ), ('keep.txt', AUTOEQ)], HD)
    mine = pack_state(1, pack_preset(AUTOEQ_BANDS), HD.encode()); keep = pack_state(1, pack_preset(AUTOEQ_BANDS), b'keep.txt')
    m.fs[STATE] = keep; m.fs[SLOT[0]] = mine; m.fs[SLOT[1]] = keep; m.fs[SLOT[2]] = mine
    m.fs[OUT_FILE] = b'M1PEQO1\0' + struct.pack('<4i', 1, 1, 1, 1)
    m.confirm_yes = True; tap_row(m, 31)
    expect(HD_PATH not in m.fs and NAME_OF(m.fs[SLOT[0]]) == b'' and NAME_OF(m.fs[SLOT[2]]) == b'' and m.fs[SLOT[1]] == keep and out_rec(m)[0] == (1, 0, 1, 0) and not [c for c in m.calls if c[0] == 'toast'],
           f'Delete Preset: the Headphones and USB slots drop the file and their switches go off, Line Out is left alone ({out_rec(m)[0]})')
    m = ppage([(HD, AUTOEQ)], HD)
    m.fs[SLOT[1]] = mine; m.fail.add(('rename', SLOT[1])); m.confirm_yes = True; tap_row(m, 31)
    expect([c[1] for c in m.calls if c[0] == 'toast'] == ['Not saved'], 'Delete Preset with a slot that cannot be rewritten: "Not saved"')


SECTIONS = [player_tests, carry_tests, parser_tests, page_tests, cross_tests, asset_tests, preset_page_tests, presets_page_tests, layout_peqp_tests, edit_band_tests, edit_select_tests, edit_dialog_tests, edit_revert_tests, edit_saveas_tests, edit_rename_tests, edit_channels_tests, layout_peqlib_tests, tenband_drag_tests, tenband_edit_tests, tenband_switch_tests, tenband_replace_tests, tenband_rows_tests, tenband_reopen_tests, tenband_memory_tests, tenband_reset_tests, tenband_curve_tests, tenband_preamp_tests, save_preset_tests, layout_tenband_tests, widths_tests, output_tests, output_edit_tests, retire_tests]


def run(ctx):
    for s in SECTIONS: s(ctx)
