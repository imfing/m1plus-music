"""Mono Audio and Crossfeed (docs/modules/stereo.md): the player's stereo stage (patch/stereo.c, called from patch/peq_player.c) run inside the
patched hciplayer under Unicorn, compared with a Python model of libbs2b's formulas; the record it reads; the mcl-seteq flag takeover
(peq_seteq_flag) that keeps the filter in the chain with Equalizer off; and the pins of that edit."""
import math, os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_V0, UC_MIPS_REG_A0, UC_MIPS_REG_A2
import mod_player

PEQ = sibling('peq')
STEREO, KILL, STATE = '/mnt/data/m1plus/playback-stereo', '/mnt/mmc/m1plus-off', '/mnt/data/m1plus/playback-eq'
FLOAT, S16, REMOVE = 0x1d, 0x10, 0x42929c
LEVELS = {1: (650, 95), 2: (700, 60), 3: (700, 45)}   # libbs2b's jmeier, cmoy and default: Fc_lo Hz, feed in tenths of a dB
RATES = (44100, 48000, 96000, 192000)


def rec(mono=0, cf=0, magic=b'M1STR01\0'): return magic + struct.pack('<ii', mono, cf)


class SP(PEQ.Player):
    """The player with strtol (peq_seteq_flag's import) answered and stock's removal 0x42929c counted."""
    def __init__(self, files=None):
        super().__init__(files)
        self.removed = 0
        self.u.hook_add(UC_HOOK_CODE, self._remove, begin=REMOVE, end=REMOVE)

    def _remove(self, u, address, size, _):
        self.removed += 1
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def _trap(self, u, address, size, user):
        if self.traps[address] != 'strtol': return super()._trap(u, address, size, user)
        try: ret = int(self.read_cstr(u.reg_read(UC_MIPS_REG_A0)).split()[0], u.reg_read(UC_MIPS_REG_A2))
        except (ValueError, IndexError): ret = 0
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def flag(self, text): return self.call(self.manifest['symbols']['peq_seteq_flag'], self.cstr(text), 0, 10)

    def start(self, rate, nch=2, **k):
        af = self.open(); self.reinit(af, rate, nch=nch, **k)
        return af

    def set(self, af, record):
        """demo's write, then the gain command stock sends after mcl-seteq (channel 0 rereads the records)."""
        self.files[STEREO] = record
        self.gains(af, [0.0] * 10)


def f32(xs): return PEQ.f32(xs)


def music(n, rate, nch=2): return PEQ.tone(n, nch, rate, freqs=(997.0, 61.0, 3500.0), amp=0.2)


def near(a, b, tol=1e-6): return PEQ.near(a, b, tol)


# ---- the Python model: libbs2b's init() and cross_feed_d(), in double
def coefs(level, rate):
    fc, feed = LEVELS[level]
    lvl = feed / 10.0
    gb_lo, gb_hi = lvl * -5.0 / 6.0 - 3.0, lvl / 6.0 - 3.0
    g_lo, g_hi = 10 ** (gb_lo / 20.0), 1.0 - 10 ** (gb_hi / 20.0)
    fc_hi = fc * 2.0 ** ((gb_lo - 20.0 * math.log10(g_hi)) / 12.0)
    x = math.exp(-2.0 * math.pi * fc / rate)
    xh = math.exp(-2.0 * math.pi * fc_hi / rate)
    return dict(b1lo=x, a0lo=g_lo * (1.0 - x), b1hi=xh, a0hi=1.0 - g_hi * (1.0 - xh), a1hi=-xh, gain=1.0 / (1.0 - g_hi + g_lo), g_lo=g_lo, fc_hi=fc_hi)


class Cross:
    def __init__(self, level, rate, mem=None):
        self.c = coefs(level, rate)
        self.m = mem or dict(lo=[0.0, 0.0], hi=[0.0, 0.0], asis=[0.0, 0.0])

    def copy(self, level, rate): return Cross(level, rate, {k: list(v) for k, v in self.m.items()})

    def step(self, l, r):
        c, m = self.c, self.m
        m['lo'] = [c['a0lo'] * l + c['b1lo'] * m['lo'][0], c['a0lo'] * r + c['b1lo'] * m['lo'][1]]
        m['hi'] = [c['a0hi'] * l + c['a1hi'] * m['asis'][0] + c['b1hi'] * m['hi'][0], c['a0hi'] * r + c['a1hi'] * m['asis'][1] + c['b1hi'] * m['hi'][1]]
        m['asis'] = [l, r]
        return (m['hi'][0] + m['lo'][1]) * c['gain'], (m['hi'][1] + m['lo'][0]) * c['gain']


def cross(x, level, rate, cf=None):
    cf = cf or Cross(level, rate)
    out = []
    for i in range(0, len(x), 2): out += cf.step(x[i], x[i + 1])
    return f32(out)


def mono_of(x): return f32([(x[i] + x[i + 1]) * 0.5 for i in range(0, len(x), 2) for _ in (0, 1)])


def rec_tests(ctx):
    expect = ctx.expect
    x = music(512, 48000)
    good = rec(1, 0)
    cases = [('no record', None), ('mono 1', rec(1, 0)), ('crossfeed 2', rec(0, 2)),
             ('bad magic', rec(1, 2, b'M1STR00\0')), ('old-style magic with no NUL', b'M1STR01' + b'\x01' + good[8:]), ('short', good[:-1]), ('long', good + b'\0'),
             ('mono 2', rec(2, 0)), ('mono -1', rec(-1, 0)), ('crossfeed 4', rec(0, 4)), ('crossfeed -1', rec(0, -1)),
             ('valid mono with a bad crossfeed', rec(1, 9)), ('bad mono with a valid crossfeed', rec(7, 2)), ('empty', b''), ('all off', rec(0, 0))]
    for what, data in cases:
        p = SP({} if data is None else {STEREO: data}); af = p.start(48000)
        same, y = p.play(af, x, 48000)
        expect(('fopen', STEREO) in p.calls, f'{what}: the reinit reads the record')
        if what in ('mono 1',):
            expect(y[0::2] == y[1::2] and y != x, f'{what}: Mono Audio on')
        elif what == 'crossfeed 2':
            expect(near(y, cross(x, 2, 48000)), f'{what}: Crossfeed on, Medium')
        else:
            expect(y == x, f'{what}: both off, every sample untouched')


def mono_tests(ctx):
    expect = ctx.expect
    for rate in RATES:
        x = music(2048, rate)
        p = SP({STEREO: rec(1, 0)}); af = p.start(rate)
        same, y = p.play(af, x, rate)
        want = mono_of(x)
        expect(same and y == want and y[0::2] == y[1::2], f'{rate} Hz: L = R = (L + R) / 2, exact')
    # the order: the downmix comes first, a left-only EQ band after it (and the crossfeed after both)
    bands = [(2, 0, 1000, 6.0, 1.0), (1, 1, 100, 4.0, 0.7)]
    eq = PEQ.pack_state(1, PEQ.pack_preset(bands, preamp=-1.0, automatic=2), b'x.txt')
    x = music(2048, 48000)
    p = SP({STATE: eq, STEREO: rec(1, 0)}); af = p.start(48000)
    _, y = p.play(af, x, 48000)
    want = PEQ.model(bands, 48000, 2, mono_of(x), 10 ** (-1 / 20))
    expect(near(y, want, 5e-6) and y[0::2] != y[1::2], 'Mono Audio before the EQ: the left-only band still applies to the downmix')
    for level in (1, 2, 3):
        p = SP({STATE: eq, STEREO: rec(1, level)}); af = p.start(48000)
        _, y = p.play(af, x, 48000)
        expect(near(y, cross(f32(want), level, 48000), 5e-6), f'Mono Audio, the EQ, then the crossfeed (level {level})')
    # a non-finite sample is a silent one, not a poisoned pair
    p = SP({STEREO: rec(1, 0)}); af = p.start(48000)
    _, y = p.play(af, [float('nan'), 0.5, float('inf'), 0.25, 0.1, 0.3], 48000)
    expect(y[:4] == [0.25, 0.25, 0.125, 0.125] and all(v == v for v in y), 'a NaN or infinity counts as 0 in the downmix')
    # one channel or more than two: nothing
    for nch in (1, 3, 6):
        x = music(600, 48000, nch)
        p = SP({STEREO: rec(1, 2)}); af = p.start(48000, nch=nch)
        _, y = p.play(af, x, 48000, nch=nch)
        expect(y == x, f'{nch} channel{"s" if nch > 1 else ""}: Mono Audio and Crossfeed do nothing')


def crossfeed_tests(ctx):
    expect = ctx.expect
    N = 3000
    for level, (fc, feed) in LEVELS.items():
        for rate in RATES:
            imp = [0.0] * (2 * N); imp[0] = 0.5
            p = SP({STEREO: rec(0, level)}); af = p.start(rate)
            _, y = p.play(af, imp, rate)
            expect(near(y, cross(imp, level, rate), 1e-7), f'level {level} ({fc} Hz / {feed / 10} dB) at {rate} Hz: the impulse response is bs2b\'s (max err {max(abs(a - b) for a, b in zip(y, cross(imp, level, rate))):.1e})')
            c = coefs(level, rate)

            def dft(ch, f):
                w = 2 * math.pi * f / rate
                return sum(y[2 * n + ch] * complex(math.cos(w * n), -math.sin(w * n)) for n in range(N)) / 0.5

            def lp(f):
                z = complex(math.cos(2 * math.pi * f / rate), -math.sin(2 * math.pi * f / rate))
                return c['gain'] * c['a0lo'] / (1 - c['b1lo'] * z), c['gain'] * (c['a0hi'] + c['a1hi'] * z) / (1 - c['b1hi'] * z)
            freqs = [f for f in (20, 150, 650, 700, 2000, 6000, 15000) if f < rate / 2 * 0.9]
            ok = all(abs(dft(1, f) - lp(f)[0]) <= 1e-3 * abs(lp(f)[0]) and abs(dft(0, f) - lp(f)[1]) <= 1e-3 * abs(lp(f)[1]) for f in freqs)
            expect(ok, f'level {level} at {rate} Hz: the crossed copy is the one-pole low-pass (G_lo {20 * math.log10(c["g_lo"]):.2f} dB), the direct path the high boost (corner {c["fc_hi"]:.0f} Hz), both scaled by the output gain')
            dc = abs(dft(1, 1.0))
            lo_f, hi_f = 50.0, 4000.0
            for _ in range(14):
                mid = (lo_f + hi_f) / 2
                if abs(dft(1, mid)) < dc / math.sqrt(2): hi_f = mid
                else: lo_f = mid
            f3 = round(hi_f)
            expect(abs(f3 - fc) / fc < 0.06, f'level {level} at {rate} Hz: the crossed copy\'s -3 dB corner is {f3} Hz (bs2b: {fc})')
    # the level is the crossed copy's attenuation against the direct path at DC: stronger levels feed more
    dcs = []
    for level in (3, 2, 1):
        c = coefs(level, 48000)
        dcs.append(20 * math.log10(c['gain'] * c['g_lo']) - 20 * math.log10(c['gain'] * (c['a0hi'] + c['a1hi']) / (1 - c['b1hi'])))
    expect(all(abs(d - want) < 0.01 for d, want in zip(dcs, (-4.5, -6.0, -9.5))), f'the feed level is the crossed copy against the direct path at DC: High -4.5, Medium -6.0, Low -9.5 dB ({dcs[0]:.2f}, {dcs[1]:.2f}, {dcs[2]:.2f})')
    # music, both channels, a block at a time
    x = music(4096, 48000)
    p = SP({STEREO: rec(0, 3)}); af = p.start(48000)
    ys = []
    for i in range(0, 4096, 700): ys += p.play(af, x[2 * i:2 * min(i + 700, 4096)], 48000)[1]
    expect(near(ys, cross(x, 3, 48000)), 'a signal in blocks of any size: the filter memory runs across them')
    # R only is the mirror of L only
    imp_r = [0.0] * (2 * 200); imp_r[1] = 0.5
    imp_l = [0.0] * (2 * 200); imp_l[0] = 0.5
    p = SP({STEREO: rec(0, 1)}); af = p.start(48000); _, yr = p.play(af, imp_r, 48000)
    p = SP({STEREO: rec(0, 1)}); af = p.start(48000); _, yl = p.play(af, imp_l, 48000)
    expect(yr[0::2] == yl[1::2] and yr[1::2] == yl[0::2], 'the right channel feeds the left as the left feeds the right')
    # the tail dies away: a long silence after the impulse ends below 1e-30 (the 1e-18 flush leaves a ~1e-34 floor, not denormals)
    imp = [0.0] * (2 * 40000); imp[0] = 0.5
    p = SP({STEREO: rec(0, 2)}); af = p.start(48000); _, y = p.play(af, imp, 48000)
    expect(max(abs(v) for v in y[-100:]) < 1e-30, 'the impulse response dies away (no denormal tail)')


def ramp_tests(ctx):
    expect = ctx.expect
    R = 48000
    N = R // 50   # 20 ms
    pre, blk = music(1000, R), music(3 * N, R)

    def played(first, second_rec, x_first=pre, x=blk, record_first=None):
        p = SP({STEREO: first} if first is not None else {}); af = p.start(R)
        _, y0 = p.play(af, x_first, R)
        p.set(af, second_rec)
        _, y = p.play(af, x, R)
        return p, af, y0, y

    # Mono on while playing: L + (M - L) * w, w = k / 960 a frame, then exactly mono
    p, af, y0, y = played(None, rec(1, 0))
    w = lambda k: min(1.0, (k + 1) / N)
    want = f32([v for k in range(3 * N) for v in (blk[2 * k] + ((blk[2 * k] + blk[2 * k + 1]) * 0.5 - blk[2 * k]) * w(k), blk[2 * k + 1] + ((blk[2 * k] + blk[2 * k + 1]) * 0.5 - blk[2 * k + 1]) * w(k))])
    expect(y0 == pre and near(y, want, 2e-7), 'Mono Audio switched on while playing: a 20 ms ramp from the stereo signal')
    expect(abs(y[0] - blk[0]) < 1e-3 and y[2 * N:][0::2] == y[2 * N:][1::2], 'it starts at the stereo sample (no jump) and is exactly mono after 20 ms')
    # Mono off again: back to bit-exact
    p.set(af, rec(0, 0))
    _, y2 = p.play(af, blk, R)
    wo = lambda k: max(0.0, 1 - (k + 1) / N)
    want = f32([blk[2 * k + c] + ((blk[2 * k] + blk[2 * k + 1]) * 0.5 - blk[2 * k + c]) * wo(k) for k in range(3 * N) for c in (0, 1)])
    expect(near(y2, want, 2e-7) and y2[2 * N:] == blk[2 * N:], 'Mono Audio switched off: ramps out in 20 ms, then every sample untouched')

    # Crossfeed on while playing: dry * (1 - w) + w * wet, the filter starting from zero
    for level in (1, 2, 3):
        p, af, y0, y = played(None, rec(0, level))
        cf = Cross(level, R)
        wet = cross(blk, level, R, cf)
        want = f32([blk[i] * (1 - w(i // 2)) + w(i // 2) * wet[i] for i in range(len(blk))])
        expect(y0 == pre and near(y, want, 2e-7), f'Crossfeed level {level} switched on while playing: 20 ms from the dry signal to the crossfeed')
        expect(max(abs(a - b) for a, b in zip(y[:20], blk[:20])) < 1e-2, f'level {level}: the change starts at the dry signal (no jump)')
        # and off again: the filter runs on while it fades out
        p.set(af, rec(0, 0))
        _, y2 = p.play(af, blk, R)
        wet = cross(blk, level, R, cf)
        want = f32([blk[i] * (1 - wo(i // 2)) + wo(i // 2) * wet[i] for i in range(len(blk))])
        expect(near(y2, want, 2e-7) and y2[2 * N:] == blk[2 * N:], f'level {level} switched off: faded out in 20 ms, then every sample untouched')

    # a level change crosses over between two filters, the new one starting from the old one's memory
    x2 = music(1000, R)
    p, af, y0, y = played(rec(0, 1), rec(0, 3), x_first=x2)
    a = Cross(1, R)
    for i in range(0, len(x2), 2): a.step(x2[i], x2[i + 1])
    b = a.copy(3, R)
    out = []
    for k in range(3 * N):
        l, r = blk[2 * k], blk[2 * k + 1]
        wb = w(k); wa = max(0.0, 1 - (k + 1) / N)
        oa, ob = a.step(l, r), b.step(l, r)
        out += [oa[0] * wa + ob[0] * wb + l * max(0.0, 1 - wa - wb), oa[1] * wa + ob[1] * wb + r * max(0.0, 1 - wa - wb)]
    expect(near(y, f32(out), 5e-7), 'Crossfeed level 1 to 3 while playing: the two filters cross over in 20 ms')
    step = lambda v, n: max(abs(v[i + 2] - v[i]) for i in range(0, 2 * (n - 1), 2))
    natural = 1.5 * max(step(v, 3 * N) for v in (blk, cross(blk, 1, R), cross(blk, 3, R)))
    expect(step(y, 3 * N) < natural, f'and the output has no jump on the way (largest step {step(y, 3 * N):.3f}, the signals\' own {natural / 1.5:.3f})')

    # changes asked faster than a ramp: no free filter until one has faded, the last request wins, no click
    p = SP({STEREO: rec(0, 1)}); af = p.start(R)
    x = music(8000, R)
    ys = list(p.play(af, x[:2 * 500], R)[1])
    for k, level in enumerate((2, 3, 1, 3)):
        p.set(af, rec(0, level))
        ys += p.play(af, x[2 * (500 + 100 * k):2 * (600 + 100 * k)], R)[1]
    ys += p.play(af, x[2 * 900:], R)[1]
    cold = cross(x[2 * 3500:], 3, R)   # from zero memory: the difference is gone after a few hundred frames
    expect(near(ys[2 * 4000:], cold[2 * 500:], 1e-5), 'four changes in 400 frames: the last (High) plays, the others have faded out')
    natural = 1.5 * max(step(v, 1400) for v in (x, cross(x, 1, R), cross(x, 2, R), cross(x, 3, R)))
    expect(step(ys[:2 * 1400], 1400) < natural, 'and nothing jumped on the way')

    # Mono and Crossfeed together on a stereo track, one after the other
    p = SP({STEREO: rec(1, 0)}); af = p.start(R)
    p.play(af, pre, R)
    p.set(af, rec(1, 2))
    _, y = p.play(af, blk, R)
    mono = mono_of(blk)
    wet = cross(mono, 2, R)
    expect(near(y, f32([mono[i] * (1 - w(i // 2)) + w(i // 2) * wet[i] for i in range(len(blk))]), 2e-7), 'Mono Audio on, Crossfeed switched on: the crossfeed ramps over the downmix')
    # a record changed while the stereo option does not apply (one channel): nothing happens
    p = SP({STEREO: rec(0, 0)}); af = p.start(R, nch=1)
    p.set(af, rec(1, 2))
    m = music(300, R, 1)
    expect(p.play(af, m, R, nch=1)[1] == m, 'a change on a one channel track does nothing')


def passthrough_tests(ctx):
    expect = ctx.expect
    on = rec(1, 2)
    x = music(512, 48000)
    # DSD, the kill switch, a rate past the filter's range and a special format: the bytes arrive unchanged
    raw = bytes(range(256)) * 8
    for what, setup in (('dsdiff driver', lambda p: p.codec(drv='dsdiff')), ('FFmpeg ffdsd codec', lambda p: p.codec(name='ffdsd_msbf')),
                        ('kill switch', lambda p: p.files.update({KILL: b''}))):
        for eq in (False, True):
            p = SP({STEREO: on, **({STATE: PEQ.tenband([3.0] * 10, 0)} if eq else {})}); setup(p)
            p.flag('1' if eq else '0')
            af = p.open(); r, din, data = p.reinit(af, 352800, fmt=0x0a, bps=4)
            same, out = p.play(af, None, 352800, fmt=0x0a, raw=raw)
            expect(r == 1 and data[4] == 0x0a and out == raw, f'{what}, Equalizer {"on" if eq else "off"}: the format is accepted as it is and the bytes pass untouched')
            p.set(af, on)
            same, out = p.play(af, None, 352800, fmt=0x0a, raw=raw)
            expect(out == raw, f'{what}, Equalizer {"on" if eq else "off"}: a gain command changes nothing')
    p = SP({STEREO: on}); af = p.start(768000)
    xs = music(128, 768000)
    expect(p.play(af, xs, 768000)[1] == xs, 'a rate past 384 kHz passes untouched')
    # not DSD: another codec is processed
    p = SP({STEREO: rec(1, 0)}); p.codec(drv='ad_flac', name='ffflac'); af = p.start(48000)
    expect(p.play(af, x, 48000)[1] != x, 'another codec (ffflac) gets Mono Audio')
    # everything off, bit for bit
    for what, files in (('no record', {}), ('a record with both off', {STEREO: rec(0, 0)})):
        p = SP(files); af = p.start(44100); xs = music(512, 44100)
        expect(p.play(af, xs, 44100)[1] == xs, f'Equalizer on, flat curve, {what}: float stereo untouched')
        flat = PEQ.tenband([0.0] * 10, -1)
        p = SP({**files, STATE: flat}); af = p.start(44100)
        expect(p.play(af, xs, 44100)[1] == xs, f'Equalizer on, Flat 10-Band, {what}: untouched')
        pcm = bytes((i * 37) & 255 for i in range(2048))
        p = SP(files); p.flag('0')
        af = p.open(); r, ind, data = p.reinit(af, 44100, fmt=S16, bps=2)
        same, out = p.play(af, None, 44100, fmt=S16, bps=2, raw=pcm)
        expect(r == 1 and data[2:] == (44100, 2, S16, 2) and out == pcm, f'Equalizer off, {what}: the native format is accepted and the block is untouched (stock\'s bits)')
        af = p.open(); r, _, data = p.reinit(af, 192000, fmt=S16, bps=2)
        expect(r == 1 and data[4] == S16, f'Equalizer off, {what}: any rate passes through')
        af = p.open(); p.reinit(af, 44100)
        expect(p.play(af, xs, 44100)[1] == xs, f'Equalizer off, {what}, float input: untouched too')
    # Equalizer off with an option on: float, no curve, only the stereo stage
    p = SP({STEREO: rec(1, 0), STATE: PEQ.tenband([6.0] * 10, 0)}); p.flag('0')
    af = p.open(); r, _, data = p.reinit(af, 44100, fmt=S16, bps=2)
    expect(r == 0 and data[4] == FLOAT, 'Equalizer off, Mono Audio on: the filter asks for float')
    af = p.start(44100); xs = music(512, 44100)
    expect(p.play(af, xs, 44100)[1] == mono_of(xs), 'Equalizer off, Mono Audio on: no curve (the record\'s 6 dB is not applied), only the downmix')
    p = SP({STEREO: rec(0, 2), STATE: PEQ.tenband([6.0] * 10, 0)}); p.flag('0'); af = p.start(44100)
    expect(near(p.play(af, xs, 44100)[1], cross(xs, 2, 44100)), 'Equalizer off, Crossfeed on: no curve, only the crossfeed')
    # Equalizer off, an option on, but the track has one channel or more than two: native pass-through
    for nch in (1, 3):
        p = SP({STEREO: rec(1, 3)}); p.flag('0')
        af = p.open(); r, _, data = p.reinit(af, 44100, nch=nch, fmt=S16, bps=2)
        expect(r == 1 and data[4] == S16, f'Equalizer off, {nch} channel{"s" if nch > 1 else ""}: native pass-through (the options are stereo only)')
    # switch toggled mid-track: the curve ramps out, the stereo stage stays
    p = SP({STEREO: rec(1, 0)}); p.flag('1'); af = p.start(44100)
    p.gains(af, [0.0] * 10)
    p.files[STATE] = PEQ.tenband([6.0] * 10, 0)
    p.gains(af, [0.0] * 10)
    for _ in range(4): y = p.play(af, xs, 44100)[1]
    expect(y[0::2] == y[1::2] and y != mono_of(xs), 'Equalizer on: the curve plays after the downmix')
    p.flag('0'); p.gains(af, [0.0] * 10)
    for _ in range(6): y = p.play(af, xs, 44100)[1]
    expect(y == mono_of(xs), 'Equalizer switched off mid-track: the curve ramps out, Mono Audio stays')


def carry_tests(ctx):
    expect = ctx.expect
    R, K, N = 48000, 4000, 9000
    x = music(N, R)
    cut = 2 * K
    flat = PEQ.tenband([0.0] * 10, -1)
    bands = [(1, 1, 100, 9.0, 0.7), (1, 0, 1000, -4.0, 1.0)]
    eqrec = PEQ.pack_state(1, PEQ.pack_preset(bands, preamp=-6.0, automatic=2), b'a.txt')

    def first(files, eq_off=False):
        p = SP(files)
        if eq_off: p.flag('0')
        af = p.open(); p.reinit(af, R)
        _, y = p.play(af, x[:cut], R)
        return p, af, y

    def second(p, af, gap=20, files=None):
        p.leave(af); p.clock += gap
        if files: p.files.update(files)
        af2 = p.open(); p.reinit(af2, R)
        return af2, p.play(af2, x[cut:], R)[1]

    for what, files, eq_off in (('Crossfeed, Equalizer flat', {STEREO: rec(0, 2), STATE: flat}, False), ('Crossfeed with the EQ off', {STEREO: rec(0, 2)}, True),
                                ('Mono and Crossfeed, with a curve', {STEREO: rec(1, 3), STATE: eqrec}, False)):
        p = SP(files)
        if eq_off: p.flag('0')
        af = p.open(); p.reinit(af, R)
        c1 = p.play(af, x[:cut], R)[1]; c2 = p.play(af, x[cut:], R)[1]
        p, af, y1 = first(files, eq_off); p.ended()
        _, y2 = second(p, af)
        expect(y1 == c1 and y2 == c2, f'{what}: a gapless join continues the crossfeed memory, the second file equals one continuous run bit for bit')
        p, af, _ = first(files, eq_off); p.ended(0)
        _, y2 = second(p, af)
        expect(y2 != c2, f'{what}: not played to its end (a skip): the next starts from zero memory')
        p, af, _ = first(files, eq_off); p.ended()
        _, y2 = second(p, af, gap=3000)
        expect(y2 != c2, f'{what}: a join 3 s later starts from zero memory')
    # the join does not need a settled stage: the weights and the filters go on, toward what the record asks now
    M = R // 50   # 20 ms
    up = lambda k, k0=0: min(1.0, (k0 + k + 1) / M)
    down = lambda k, k0=0: max(0.0, 1 - (k0 + k + 1) / M)
    rest = x[cut:]; F = len(rest) // 2
    step = lambda v, n: max(abs(v[i + 2] - v[i]) for i in range(0, 2 * (n - 1), 2))

    def warm(level, upto=cut):
        cf = Cross(level, R)
        for i in range(0, upto, 2): cf.step(x[i], x[i + 1])
        return cf
    # another level in the record: the two cross over, the new one from the old one's memory (as a change while playing)
    p, af, _ = first({STEREO: rec(0, 2), STATE: flat}); p.ended()
    _, y2 = second(p, af, files={STEREO: rec(0, 3)})
    ca = warm(2); cb = ca.copy(3, R); out = []
    for k in range(F):
        l, r = rest[2 * k], rest[2 * k + 1]
        oa, ob = ca.step(l, r), cb.step(l, r)
        out += [oa[0] * down(k) + ob[0] * up(k), oa[1] * down(k) + ob[1] * up(k)]
    expect(near(y2, f32(out), 5e-7), 'a join into another level: the two filters cross over in 20 ms from the carried memory')
    # the crossfeed turned off at the join: it fades out
    p, af, _ = first({STEREO: rec(0, 2), STATE: flat}); p.ended()
    _, y2 = second(p, af, files={STEREO: rec(0, 0)})
    wet = cross(rest, 2, R, warm(2))
    expect(near(y2, f32([rest[i] * (1 - down(i // 2)) + down(i // 2) * wet[i] for i in range(len(rest))]), 2e-7) and y2[2 * M:] == rest[2 * M:],
           'a join into Crossfeed off: faded out in 20 ms, then untouched')
    # a track that ends within a crossfeed ramp: the next one finishes it
    p = SP({STEREO: rec(0, 0), STATE: flat}); af = p.start(R)
    p.play(af, x[:cut], R)
    p.set(af, rec(0, 2))
    ya = p.play(af, x[cut:cut + 200], R)[1]; p.ended()
    p.leave(af); p.clock += 20
    af2 = p.start(R); tail = x[cut + 200:]; y2 = p.play(af2, tail, R)[1]
    cf = Cross(2, R); wet = cross(x[cut:], 2, R, cf)
    want = f32([x[cut + i] * (1 - up(i // 2)) + up(i // 2) * wet[i] for i in range(len(x) - cut)])
    expect(near(ya + y2, want, 2e-7), 'a track that ends 100 frames into a Crossfeed ramp: the next continues the ramp where it was')
    expect(abs(y2[0] - ya[-2]) < 1.5 * step(x, N), 'and nothing jumps at the join')
    # the same for Mono Audio, on and off, with the Equalizer off too
    for eq_off in (False, True):
        p = SP({STEREO: rec(0, 2), STATE: flat})
        if eq_off: p.flag('0')
        af = p.start(R); p.play(af, x[:cut], R)
        p.set(af, rec(1, 2))
        ya = p.play(af, x[cut:cut + 200], R)[1]; p.ended()
        p.leave(af); p.clock += 20
        af2 = p.start(R); y2 = p.play(af2, tail, R)[1]
        seg = x[cut:]
        pre_ = f32([seg[2 * k + c] + ((seg[2 * k] + seg[2 * k + 1]) * 0.5 - seg[2 * k + c]) * up(k) for k in range(len(seg) // 2) for c in (0, 1)])
        want = cross(pre_, 2, R, warm(2))
        expect(near(ya + y2, want, 5e-7), f'Equalizer {"off" if eq_off else "flat"}: a track that ends 100 frames into a Mono Audio ramp: the next continues it (not full weight at once)')
    p = SP({STEREO: rec(1, 0), STATE: flat}); af = p.start(R); p.play(af, x[:cut], R)
    p.set(af, rec(0, 0))
    ya = p.play(af, x[cut:cut + 200], R)[1]; p.ended()
    p.leave(af); p.clock += 20
    af2 = p.start(R); y2 = p.play(af2, tail, R)[1]
    seg = x[cut:]
    want = f32([seg[2 * k + c] + ((seg[2 * k] + seg[2 * k + 1]) * 0.5 - seg[2 * k + c]) * down(k) for k in range(len(seg) // 2) for c in (0, 1)])
    expect(near(ya + y2, want, 2e-7) and y2[2 * M:] == tail[2 * M:], 'Mono Audio switched off 100 frames before the end: the next track finishes the ramp out, then untouched')
    # the same with the Equalizer off, where the next instance would otherwise pass the native format through and drop the fade
    p = SP({STEREO: rec(1, 0)}); p.flag('0'); af = p.start(R); p.play(af, x[:cut], R)
    p.set(af, rec(0, 0))
    ya = p.play(af, x[cut:cut + 200], R)[1]; p.ended()
    p.leave(af); p.clock += 20
    af2 = p.open(); r, _, data = p.reinit(af2, R, fmt=S16, bps=2)
    expect(r == 0 and data[4] == FLOAT, 'Equalizer off, Mono Audio switched off 100 frames before the end: the next instance still filters (float)')
    p.reinit(af2, R); y2 = p.play(af2, tail, R)[1]
    expect(near(ya + y2, want, 2e-7) and y2[2 * M:] == tail[2 * M:], 'and finishes the ramp out, then leaves every sample untouched')
    p = SP({STEREO: rec(1, 0)}); p.flag('0'); af = p.start(R); p.play(af, [0.8, 0.0] * 2000, R)
    p.set(af, rec(0, 0))
    ya = p.play(af, [0.8, 0.0] * 100, R)[1]; p.ended(); p.leave(af); p.clock += 20
    af2 = p.start(R); y2 = p.play(af2, [0.8, 0.0] * 4, R)[1]
    expect(near(ya[-2:], [0.8 - 0.4 * 860 / M, 0.4 * 860 / M], 1e-6) and near(y2[:2], [0.8 - 0.4 * 859 / M, 0.4 * 859 / M], 1e-6), f'[0.8, 0]: [0.44167, 0.35833] is followed by [0.44208, 0.35792], not [0.8, 0] ({y2[0]:.5f}, {y2[1]:.5f})')
    p = SP({STEREO: rec(0, 2)}); p.flag('0'); af = p.start(R); p.play(af, x[:cut], R)
    p.set(af, rec(0, 0))
    ya = p.play(af, x[cut:cut + 200], R)[1]; p.ended(); p.leave(af); p.clock += 20
    af2 = p.start(R); y2 = p.play(af2, tail, R)[1]
    wet = cross(seg, 2, R, warm(2))
    expect(near(ya + y2, f32([seg[i] * (1 - down(i // 2)) + down(i // 2) * wet[i] for i in range(len(seg))]), 2e-7) and y2[2 * M:] == tail[2 * M:],
           'Equalizer off, Crossfeed switched off 100 frames before the end: the next track finishes the fade, then untouched')
    # nothing left to fade (settled off, a skip, or 3 s later): native pass-through as before
    for what, setup in (('settled off', lambda p, af: p.play(af, x[:4000], R)), ('a skip', lambda p, af: p.ended(0)), ('3 s later', None)):
        p = SP({STEREO: rec(1, 0)}); p.flag('0'); af = p.start(R); p.play(af, x[:cut], R)
        p.set(af, rec(0, 0)); p.play(af, x[cut:cut + 200], R); p.ended()
        if setup: setup(p, af)
        p.leave(af); p.clock += 20 if setup else 3000
        af2 = p.open(); r, _, data = p.reinit(af2, R, fmt=S16, bps=2)
        expect(r == 1 and data[4] == S16, f'Equalizer off, both off, {what}: the next instance passes the native format through')
    # Mono Audio changed between the tracks (no gain command): it ramps at the join
    p, af, _ = first({STEREO: rec(0, 0), STATE: flat}); p.ended()
    _, y2 = second(p, af, files={STEREO: rec(1, 0)})
    want = f32([rest[2 * k + c] + ((rest[2 * k] + rest[2 * k + 1]) * 0.5 - rest[2 * k + c]) * up(k) for k in range(F) for c in (0, 1)])
    expect(near(y2, want, 2e-7), 'Mono Audio switched on between two gapless tracks: a 20 ms ramp at the join')
    # the stereo stage carries on its own: another curve at the join (the cascade starts from zero) keeps the crossfeed's memory
    p, af, _ = first({STEREO: rec(0, 2), STATE: flat}); p.ended()
    _, y2 = second(p, af, files={STATE: eqrec})
    want = cross(f32(PEQ.model(bands, R, 2, rest, 10 ** (-6 / 20))), 2, R, warm(2))
    expect(near(y2, want, 5e-6), 'another curve at the join: the cascade starts from zero, the crossfeed goes on from its memory')
    # another rate: nothing of it
    p, af, _ = first({STEREO: rec(0, 2), STATE: flat}); p.ended()
    p.leave(af); p.clock += 20
    af2 = p.start(44100); xs = music(2000, 44100)
    expect(near(p.play(af2, xs, 44100)[1], cross(xs, 2, 44100)), 'a join into another rate starts from zero memory, at full weight')


def activate_tests(ctx):
    """Mono Audio or Crossfeed switched on while the Equalizer is off and the filter passes the native format through: peq_seteq_flag
    removes that instance and the loop adds another in the middle of the music, which must ramp in like any change while playing."""
    expect = ctx.expect
    R = 48000
    M = R // 50
    blk = music(3 * M, R)
    up = lambda k: min(1.0, (k + 1) / M)

    def replaced(record, twice=False):
        p = SP({}); p.mpctx(); p.flag('0')
        af = p.open(); p.reinit(af, R, fmt=S16, bps=2)
        p.files[STEREO] = record; p.flag('0')
        assert p.removed == 1
        p.leave(af)                                  # stock's removal uninits it
        af2 = p.open(); r = p.reinit(af2, R, fmt=S16, bps=2)[0]
        assert r == 0                                # asks for float; the chain calls REINIT again
        p.reinit(af2, R)
        if twice: p.reinit(af2, R)
        return p, af2

    p, af = replaced(rec(1, 0))
    _, y = p.play(af, [0.8, 0.0] * 4, R)
    expect(near(y[:2], [0.8 - 0.4 / M, 0.4 / M], 1e-7), f'Mono Audio switched on with the Equalizer off: the first pair of [0.8, 0] is [0.79958, 0.00042], not [0.4, 0.4] ({y[0]:.5f}, {y[1]:.5f})')
    for twice in (False, True):
        p, af = replaced(rec(1, 0), twice)
        _, y = p.play(af, blk, R)
        want = f32([blk[2 * k + c] + ((blk[2 * k] + blk[2 * k + 1]) * 0.5 - blk[2 * k + c]) * up(k) for k in range(3 * M) for c in (0, 1)])
        expect(near(y, want, 2e-7) and y[2 * M:][0::2] == y[2 * M:][1::2], f'Mono Audio, the replacing instance{" (REINIT once more before the first block)" if twice else ""}: a 20 ms ramp from the stereo signal, then exactly mono')
    for level in (1, 2, 3):
        p, af = replaced(rec(0, level))
        _, y = p.play(af, blk, R)
        wet = cross(blk, level, R)
        expect(near(y, f32([blk[i] * (1 - up(i // 2)) + up(i // 2) * wet[i] for i in range(len(blk))]), 2e-7), f'Crossfeed level {level} switched on with the Equalizer off: 20 ms from the dry signal')
    p, af = replaced(rec(1, 3))
    _, y = p.play(af, blk, R)
    pre_ = f32([blk[2 * k + c] + ((blk[2 * k] + blk[2 * k + 1]) * 0.5 - blk[2 * k + c]) * up(k) for k in range(3 * M) for c in (0, 1)])
    wet = cross(pre_, 3, R)
    expect(near(y, f32([pre_[i] * (1 - up(i // 2)) + up(i // 2) * wet[i] for i in range(len(blk))]), 5e-7), 'both switched on at once: both ramp')
    # a REINIT later in the same instance (it has played) and the next track's instance start at full weight, as before
    p.reinit(af, R)
    expect(near(p.play(af, blk, R)[1], cross(mono_of(blk), 3, R)), 'a REINIT after the instance has played: no second ramp')
    p.leave(af); af3 = p.start(R)
    expect(near(p.play(af3, blk, R)[1], cross(mono_of(blk), 3, R)), 'the next track\'s instance plays what the record asks from its first frame')
    # the Equalizer switched on over a pass-through instance: the replacement is marked too, with nothing to ramp
    p = SP({}); p.mpctx(); p.flag('0'); af = p.open(); p.reinit(af, R, fmt=S16, bps=2)
    p.flag('1'); p.leave(af); af2 = p.start(R)
    expect(p.removed == 1 and p.play(af2, blk, R)[1] == blk, 'Equalizer on over a pass-through instance, both options off: untouched')


def flag_tests(ctx):
    expect = ctx.expect
    on = rec(1, 0)
    p = SP({STEREO: on})
    expect(p.flag('0') == 2 and p.flag('1') == 1 and p.flag('2') == 2 and p.flag('7') == 2 and p.flag('0') == 2,
           'mcl-seteq flag: 1 and 2 as they are, anything else (off) is answered 2, so stock keeps the filter in the chain')
    pk = SP({STEREO: on, KILL: b''})
    expect(pk.flag('0') == 0 and pk.flag('1') == 1, 'kill switch: stock gets its own answer (off removes the filter)')
    # the removal: only an instance that passes the native format through is removed, and only when it has to filter
    p = SP({}); p.mpctx(); p.flag('0')
    af = p.open(); p.reinit(af, 44100, fmt=S16, bps=2)
    p.removed = 0; p.flag('0')
    expect(p.removed == 0, 'EQ off again, both options off: the pass-through instance stays')
    p.files[STEREO] = rec(1, 0); p.flag('0')
    expect(p.removed == 1, 'Mono Audio on (record, then mcl-seteq off): the pass-through instance is removed, the loop adds a float one')
    p.removed = 0; p.files[STEREO] = rec(0, 2); p.flag('0')
    expect(p.removed == 1, 'Crossfeed on with a pass-through instance: removed')
    p.removed = 0; p.files[STEREO] = rec(0, 0); p.flag('1')
    expect(p.removed == 1, 'Equalizer on while an instance passes the native format through: removed')
    p.removed = 0; p.flag('1'); p.flag('2'); p.flag('0')
    expect(p.removed == 0, 'and not again while the instance is the same')
    p.leave(af)
    # the float instance (an option is on) is never removed
    p = SP({STEREO: rec(1, 0)}); p.mpctx(); p.flag('0')
    af = p.open(); r, _, data = p.reinit(af, 44100, fmt=S16, bps=2)
    expect(r == 0 and data[4] == FLOAT, 'Equalizer off, Mono Audio on: the filter takes float')
    p.removed = 0; p.flag('0'); p.flag('1'); p.flag('0')
    expect(p.removed == 0, 'a float instance is not removed by any flag')
    # the kill switch removes nothing
    p = SP({}); p.mpctx(); p.flag('0'); af = p.open(); p.reinit(af, 44100, fmt=S16, bps=2)
    p.files[KILL] = b''; p.files[STEREO] = rec(1, 0); p.removed = 0; p.flag('0')
    expect(p.removed == 0, 'kill switch: peq_seteq_flag removes nothing')
    # Equalizer on, then the records: the gain command applies a new record, the flag does not need to
    p = SP({}); p.flag('1'); af = p.start(44100); xs = music(256, 44100)
    expect(p.play(af, xs, 44100)[1] == xs, 'Equalizer on, no record: untouched')
    p.set(af, rec(1, 0))
    for _ in range(5): y = p.play(af, xs, 44100)[1]
    expect(y == mono_of(xs), 'a record written while playing is read by the next gain command')
    # GAIN SET on another channel changes nothing
    p.files[STEREO] = rec(0, 0); p.gains(af, [0.0] * 10, channel=3)
    expect(p.play(af, xs, 44100)[1] == mono_of(xs), 'a gain command for channel 1..7 rereads nothing')


def pin_tests(ctx):
    expect = ctx.expect
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', mod_player.REL), 'rb').read()
    built = open(os.path.join(WORK, 'rootfs', mod_player.REL), 'rb').read()
    w = mod_player.word
    flag_fn = json.load(open(os.path.join(WORK, 'playerbuild', 'manifest.json')))['symbols']['peq_seteq_flag']
    expect(w(stock, mod_player.SETEQ_CALL) == mod_player.SETEQ_STOCK == 0x0c2b6b84 and w(built, mod_player.SETEQ_CALL) == 0x0c000000 | flag_fn >> 2,
           'mcl-seteq: the strtol call (jal 0xadae10) becomes a jal to peq_seteq_flag')
    pinned = {a for a, _, _ in mod_player.PINS}
    expect({0x42cd54, 0x42cd64, 0x42ce18, 0x42ce44, 0x4224ec, 0x42929c, 0xadae14} <= pinned, 'the removal, the insert state writes and the strtol stub are pinned')
    expect(all(w(stock, a) == old for a, old, _ in mod_player.PINS), 'every pin is a word of the stock binary')
    expect(mod_player.LIBC['strtol'][2] == 'strtol' and set(mod_player.LIBC) == {'memset', 'memcpy', 'memcmp', 'strcmp', 'strlen', 'calloc', 'free', 'fopen', 'fread', 'fclose',
                                                                                'clock_gettime', 'strtol', 'pow', 'cos', 'sin', 'fseek', 'fwrite'},
           'one libc import is new, strtol (the call the edit replaces); everything else the stereo stage uses was imported (fseek and fwrite are the level tap\'s, hciplayer\'s own slots)')
    # a pin that does not match fails the build: with the hash check out of the way, one changed word in each group is refused
    for at, what in ((mod_player.SETEQ_CALL, 'the strtol call'), (0x42cd54, 'a flag-0 path word'), (0x42ce18, 'the flag-2 store'), (0x4224ec, 'the file-start state'),
                     (0x42929c, 'the removal'), (0xadae14, 'the strtol stub')):
        bad = bytearray(stock); bad[pod.fileoff(bad, at)] ^= 1
        keep = mod_player.PLAYER_SHA
        mod_player.PLAYER_SHA = pod.sha(bytes(bad))
        try:
            mod_player.check_stock(bytes(bad)); refused = False
        except ValueError as e: refused = hex(at)[2:] in str(e)
        finally: mod_player.PLAYER_SHA = keep
        expect(refused, f'{what} ({at:#x}) changed: check_stock refuses it')
    try: mod_player.check_stock(stock); ok = True
    except ValueError: ok = False
    expect(ok, 'the stock binary passes every pin')
    manifest = json.load(open(os.path.join(WORK, 'playerbuild', 'manifest.json')))
    expect(manifest['seteq_call']['target'] == flag_fn and manifest['libc_slots']['strtol'] == 0xaf98e8, 'the manifest records the edit and the strtol slot')
    expect(manifest['payload_len'] < 0xc000, f'the payload is {manifest["payload_len"]} bytes')


# ---- demo's side: the settings, the effective record and when the player is told (patch/stereoset.c, called by peqout_sync)
PODCASTS = sibling('podcasts')   # (a machine with a file system the payload reads and writes)
MONO_FILE, XFEED_FILE = '/mnt/data/m1plus/playback-mono', '/mnt/data/m1plus/playback-crossfeed'
LINEOUT = pod.DATA['LINEOUT_FLAG'][0]
EQ_FLAG, EQ_MODE = pod.DATA['EQ_FLAG'][0], pod.DATA['EQ_MODE'][0]


def out_machine(mono=None, xfeed=None, record=None, way=0, lo=0, flag=0):
    m = PODCASTS.PM()
    m.u.mem_write(EQ_FLAG, bytes([flag])); m.setword(EQ_MODE, 4)
    m.out_way = way; m.u.mem_write(LINEOUT, bytes([lo]))
    if mono is not None: m.fs[MONO_FILE] = mono
    if xfeed is not None: m.fs[XFEED_FILE] = xfeed
    if record is not None: m.fs[STEREO] = record
    return m


def out_set(m, way=0, lo=0): m.out_way = way; m.u.mem_write(LINEOUT, bytes([lo]))
def sync(m, notify=1): m.calls = []; return m.call(PSYMS['peqout_sync'], notify, count=1 << 30)
def sword(r): return r - (1 << 32) if r >= 1 << 31 else r
def got(m): return struct.unpack_from('<ii', m.fs[STEREO], 8) if STEREO in m.fs and len(m.fs[STEREO]) == 16 and m.fs[STEREO][:8] == b'M1STR01\0' else None


def events(m):
    """The record's replacements and the player's rereads, in order."""
    return [('record', c[2]) if c[0] == 'rename' and c[2] == STEREO else ('seteq', c[1]) for c in m.calls if (c[0] == 'rename' and c[2] == STEREO) or c[0] == 'set_equalizer_value']


def set_mono(m): m.calls = []; return sword(m.call(PSYMS['stereo_mono_toggle'], count=1 << 30))
def set_level(m, v): m.calls = []; return sword(m.call(PSYMS['stereo_crossfeed_set'], v, count=1 << 30))
def level(m): return m.call(PSYMS['stereo_crossfeed'], count=1 << 30)
def mono(m): return m.call(PSYMS['stereo_mono'], count=1 << 30)


def settings_tests(ctx):
    expect = ctx.expect
    # a fresh device with both options off: nothing is written, the player is not told, on any output, however often it is asked
    m = out_machine()
    for way, lo in ((0, 0), (0, 1), (2, 0), (1, 0), (0, 0)):
        out_set(m, way, lo); sync(m)
        expect(STEREO not in m.fs and not events(m) and not [c for c in m.calls if c[0] in ('open', 'write', 'rename', 'unlink', 'mkdir') and 'playback-stereo' in str(c[1:])] and (mono(m), level(m)) == (0, 0), f'fresh device, way {way} Line Out {lo}: no record, nothing sent')
    expect(MONO_FILE not in m.fs and XFEED_FILE not in m.fs, 'and no setting file was made')
    # a level on the headphones: the setting file, the record (effective level), then the player rereads, in that order
    r = set_level(m, 3)
    expect(r == 3 and m.fs[XFEED_FILE] == b'3\n' and got(m) == (0, 3) and events(m) == [('record', STEREO), ('seteq', 4)] and level(m) == 3, f'Crossfeed High: file "3", record (mono 0, level 3) written before the seteq ({events(m)})')
    expect(MONO_FILE not in m.fs and STEREO + '.tmp' not in m.fs, 'no mono file, no temporary file left')
    for _ in range(3): sync(m, 1); sync(m, 0)
    expect(not events(m) and got(m) == (0, 3), 'asked again with nothing changed: not rewritten, not sent')
    # Line Out, USB DAC: the record's level is 0, the setting stays; back on the jacks it comes back; Bluetooth (way 1) is headphones
    out_set(m, 0, 1); sync(m)
    expect(got(m) == (0, 0) and events(m) == [('record', STEREO), ('seteq', 4)] and level(m) == 3 and m.fs[XFEED_FILE] == b'3\n', f'to Line Out: the record says 0, the user\'s level is kept ({events(m)})')
    out_set(m, 0, 0); sync(m)
    expect(got(m) == (0, 3) and events(m) == [('record', STEREO), ('seteq', 4)], 'back to the jacks: the level returns')
    out_set(m, 2, 0); sync(m)
    expect(got(m) == (0, 0), 'USB DAC: 0')
    out_set(m, 2, 1); sync(m); out_set(m, 1, 0); sync(m)
    expect(got(m) == (0, 3) and events(m) == [('record', STEREO), ('seteq', 4)], 'Bluetooth (output way 1) plays with the headphone rule: the level')
    out_set(m, 1, 1); sync(m)
    expect(got(m) == (0, 3) and not events(m), 'Bluetooth with the Line Out byte set is still the headphone rule (way 1: peqout_current is Headphones)')
    # the player thread's call (no notify) writes the record and sends nothing
    out_set(m, 0, 1); out_set(m, 0, 1); sync(m, 0)
    expect(got(m) == (0, 0) and events(m) == [('record', STEREO)], f'a track starting on Line Out (notify 0): the record only ({events(m)})')
    out_set(m, 0, 0); sync(m, 0); sync(m, 1)
    expect(got(m) == (0, 3) and events(m) == [], 'headphones again on the player thread; the UI thread\'s next tick finds it done')
    # Mono Audio: every output, saved, on at once
    m = out_machine()
    r = set_mono(m)
    expect(r == 1 and m.fs[MONO_FILE] == b'1\n' and got(m) == (1, 0) and events(m) == [('record', STEREO), ('seteq', 4)] and mono(m) == 1, f'Mono Audio on: file "1", record (1, 0), then the seteq ({events(m)})')
    for way, lo in ((0, 1), (2, 0), (1, 0)):
        out_set(m, way, lo); sync(m)
        expect(got(m) == (1, 0) and not events(m), f'mono stays on way {way} Line Out {lo}')
    r = set_mono(m)
    expect(r == 0 and m.fs[MONO_FILE] == b'0\n' and got(m) == (0, 0) and events(m) == [('record', STEREO), ('seteq', 4)], 'off again: the record is rewritten as both off (not removed)')
    # both: mono 1, crossfeed Low, on Line Out
    m = out_machine(b'1\n', b'1\n', way=0, lo=1); sync(m)
    expect(got(m) == (1, 0), 'first look on Line Out with both settings: (1, 0)')
    out_set(m, 0, 0); sync(m)
    expect(got(m) == (1, 1), 'headphones: (1, 1)')
    # a level changed while on Line Out: the setting is saved, the record does not change, the player is not told
    out_set(m, 0, 1); sync(m)
    r = set_level(m, 2)
    expect(r == 2 and m.fs[XFEED_FILE] == b'2\n' and got(m) == (1, 0) and not events(m), 'Line Out: Medium is saved, the record and the player stay as they were')
    out_set(m, 0, 0); sync(m)
    expect(got(m) == (1, 2), 'and it applies on the jacks')
    expect(set_level(m, 2) == 2 and not [c for c in m.calls if c[0] in ('rename', 'open')], 'choosing the level that is set writes nothing')
    expect(set_level(m, 4) == -1 and set_level(m, -1) == -1 and level(m) == 2, 'a level that is not offered is refused')
    # an existing equal record on disk is not rewritten at the first look
    m = out_machine(b'1\n', b'3\n', rec(1, 3)); sync(m)
    expect(not events(m) and m.fs[STEREO] == rec(1, 3), 'the record on disk already says it: nothing written, nothing sent')
    # a stale record is replaced; a damaged one counts as off
    m = out_machine(None, None, rec(1, 2)); sync(m)
    expect(got(m) == (0, 0) and events(m) == [('record', STEREO), ('seteq', 4)], 'a stale record and both off: rewritten as off, the player told')
    for junk in (b'junk', b'', rec(0, 9), rec(2, 0), rec(0, 1)[:-1], rec(0, 1) + b'x', rec(0, 1, magic=b'M1STR02\0')):
        m = out_machine(None, None, junk); sync(m)
        expect(m.fs[STEREO] == junk and not events(m), f'a damaged record ({junk[:12]!r}) with both off is as good as off: left alone')
    m = out_machine(b'1\n', None, b'junk'); sync(m)
    expect(got(m) == (1, 0), 'a damaged record and Mono on: replaced')
    # damaged setting files are off
    for junk in (b'junk', b'', b'9\n', b'4\n', b'-1\n', b'01\n', b'3'):
        m = out_machine(b'x', junk); sync(m)
        want = 3 if junk == b'3' else 0
        expect(level(m) == want and mono(m) == 0 and (STEREO in m.fs) == bool(want), f'crossfeed file {junk!r}: level {want}')
    m = out_machine(b'11\n'); sync(m)
    expect(mono(m) == 0 and STEREO not in m.fs, 'mono file "11": off')
    # the kill switch: the settings are still saved, nothing else is done
    m = out_machine(); m.present.add(KILL)
    expect(set_level(m, 3) == 3 and m.fs[XFEED_FILE] == b'3\n' and STEREO not in m.fs and not events(m), 'kill switch: the level is saved, no record, no seteq')
    sync(m); out_set(m, 0, 1); sync(m)
    expect(STEREO not in m.fs and not events(m), 'and the output change does not make one')
    m.present.discard(KILL); sync(m)
    expect(STEREO not in m.fs and not events(m), 'switch removed on Line Out: the record would say off, and there is none: nothing is written')
    out_set(m, 0, 0); sync(m)
    expect(got(m) == (0, 3) and events(m) == [('record', STEREO), ('seteq', 4)], 'back on the jacks: the level is followed')
    # a record that cannot be written: asked again by the next call, the player is not told in between
    m = out_machine(None, b'2\n'); m.fail.add(('rename', STEREO)); sync(m)
    expect(STEREO not in m.fs and not [e for e in events(m) if e[0] == 'seteq'], 'the rename fails: no record, no seteq')
    m.fail.discard(('rename', STEREO)); sync(m)
    expect(got(m) == (0, 2) and events(m) == [('record', STEREO), ('seteq', 4)], 'the next call writes it and tells the player')
    m = out_machine(); m.fail.add(('rename', STEREO))
    expect(set_mono(m) == 1 and mono(m) == 1 and m.fs[MONO_FILE] == b'1\n' and STEREO not in m.fs, 'a setting whose record failed: the choice is saved, the next call retries')
    m.fail.discard(('rename', STEREO)); sync(m)
    expect(got(m) == (1, 0), 'retried')
    # a setting that cannot be saved changes nothing
    m = out_machine(); m.fail.add(('rename', XFEED_FILE))
    expect(set_level(m, 3) == -1 and level(m) == 0 and STEREO not in m.fs and not events(m) and XFEED_FILE + '.tmp' not in m.fs, 'the level cannot be saved: refused, nothing changes')
    m = out_machine(); m.fail.add(('rename', MONO_FILE))
    expect(set_mono(m) == -1 and mono(m) == 0 and STEREO not in m.fs and not events(m), 'mono cannot be saved: refused, nothing changes')
    # the hooks that run it: the status bar's timer, stock's save_start_player and mclStartPlayer all reach peqout_sync
    m = out_machine(None, b'3\n', rec(0, 0), lo=1); sync(m); out_set(m, 0, 0); m.calls = []
    m.call(PSYMS['rd_save_start'], 0, count=1 << 30)
    expect(got(m) == (0, 3) and not [e for e in events(m) if e[0] == 'seteq'], 'save_start_player (an output changed under the track): the record is in place before stock restarts it')


SECTIONS = [rec_tests, mono_tests, crossfeed_tests, ramp_tests, passthrough_tests, carry_tests, activate_tests, flag_tests, pin_tests, settings_tests]
