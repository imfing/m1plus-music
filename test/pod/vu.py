"""VU Meter Mode's level tap (docs/modules/vu.md): patch/vu.c called from patch/peq_player.c, run inside the patched hciplayer under Unicorn.
What is proved: the record's layout against patch/vu.h; no measuring, no write and no delay call unless the page's mark (VU_FILE with its magic) is there;
the levels (peak, sum of squares) of known float and native integer blocks, after the stages in the float path; a block is never written, with everything
off bit for bit; one-channel and many-channel streams; DSD, special formats and the kill switch give no levels; the audible time (now plus the output's
delay); short blocks merged, the ring wrapping, the sequence counter.

The page (patch/vupage.c, tools/pod_ui.py build_vu_page, from page_tests on), on the real compiled payload under Unicorn with the level file and CLOCK_MONOTONIC answered by
a machine (VUM): the asset and the open / close, the mark created and unlinked, the stale mark at boot (page_tests); the record read and what parks the needles (level_tests); the
needle's step response, 99 % at about 300 ms with about 1 % overshoot (step_tests); the PEAK lamp and its hold (lamp_tests); the frame against tools/vu_art.py's reference renderer
(compose, from the generator's own pictures) within 2 per channel, incremental drawing against drawing from scratch, the dirty rectangles (pixel_tests); the per-tick instruction
budgets (motion_tests); touch, text, life and idle power as the Vinyl page's (touch_tests, text_tests, life_tests); the emulated frames out/preview/vu-emu-*.png (preview_tests)."""
import math, os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import vu_art as A
from PIL import Image, ImageChops, ImageDraw
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_V0, UC_MIPS_REG_PC, UC_MIPS_REG_RA

PEQ, STE = sibling('peq'), sibling('stereo')
VU, KILL, MAGIC = '/tmp/m1plus-vu', '/mnt/mmc/m1plus-off', b'M1VU001\0'
RING = 64
HEAD, ENTRY, TAIL = 40, 32, 8
S16, S24, S32, U8, BE16, FLOAT = 0x09, 0x11, 0x19, 0x03, 0x08, 0x1d   # MPlayer's af formats: bit 0 LE, bit 1 unsigned, bit 2 float, bits 3..5 the width
MPCTX = 0xaf9e30


class VP(STE.SP):
    """SP with the level file's stdio (r+b, fread, fseek, fwrite, fclose) answered on a mutable file, the delay function and the writes counted."""
    def __init__(self, files=None, delay=0.0):
        super().__init__(files)
        self.vh, self.writes = {}, 0
        self.set_delay(delay)

    def set_delay(self, seconds, wild=None):
        """mpctx + 8 -> the ao table, whose +0x1c get_delay is MIPS code returning a float read from memory."""
        if wild is not None: seconds = wild
        at = self.malloc(8); self.u.mem_write(at, struct.pack('<f', seconds))
        hi = (at + 0x8000) >> 16; lo = at - (hi << 16)
        code = self.malloc(32)
        self.u.mem_write(code, struct.pack('<4I', 0x3c020000 | hi, 0xc4400000 | (lo & 0xffff), 0x03e00008, 0))
        ao = self.malloc(0x40); self.setword(ao + 0x1c, code)
        self.setword(self.mpctx() + 8, ao)
        self.delay_at = at

    def no_output(self): self.setword(self.mpctx() + 8, 0)

    def _trap(self, u, address, size, user):
        name = self.traps[address]
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'fopen' and self.read_cstr(a0).decode() == VU:
            self.calls.append(('fopen', VU, self.read_cstr(a1).decode()))
            if VU in self.files:
                ret = self.malloc(4); self.vh[ret] = 0
            else: ret = 0
        elif name in ('fread', 'fseek', 'fwrite', 'fclose') and (a3 if name in ('fread', 'fwrite') else a0) in self.vh:
            h = a3 if name in ('fread', 'fwrite') else a0
            data = self.files[VU]
            if name == 'fread':
                chunk = bytes(data[self.vh[h]:self.vh[h] + a1 * a2]); u.mem_write(a0, chunk); self.vh[h] += len(chunk); ret = len(chunk) // a1
            elif name == 'fseek':
                assert a2 == 0; self.vh[h] = a1; ret = 0
            elif name == 'fwrite':
                chunk = bytes(u.mem_read(a0, a1 * a2)); pos = self.vh[h]
                self.files[VU] = data = bytearray(data).ljust(pos, b'\0'); data[pos:pos + len(chunk)] = chunk
                self.vh[h] = pos + len(chunk); self.writes += 1; self.calls.append(('fwrite', VU, pos, len(chunk))); ret = len(chunk) // a1
            else:
                self.vh.pop(h); self.calls.append(('fclose', VU)); ret = 0
        if ret is None: return super()._trap(u, address, size, user)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def watch(self): self.files[VU] = bytearray(MAGIC)
    def vu_opens(self): return len([c for c in self.calls if c[:2] == ('fopen', VU)])
    def start_vu(self, rate=48000, nch=2, **k):
        self.watch(); return self.start(rate, nch=nch, **k)


def rd(p):
    """The record, read whole as the page would: a header dict, entries oldest first, the tail check."""
    raw = bytes(p.files[VU])
    assert len(raw) == HEAD + ENTRY * RING + TAIL, len(raw)
    magic, seq, rate, ch, count, head, _, now = struct.unpack_from('<8siiiiiiq', raw, 0)
    es = [dict(zip(('due', 'dur', 'frames', 'pk', 'sq'), (a, b, c, (d, e), (f, g)))) for a, b, c, d, e, f, g in
          (struct.unpack_from('<qiiffff', raw, HEAD + ENTRY * i) for i in range(RING))]
    order = [es[(head - count + 1 + i) % RING] for i in range(count)]
    seq_end, _ = struct.unpack_from('<ii', raw, HEAD + ENTRY * RING)
    return dict(magic=magic, seq=seq, rate=rate, ch=ch, count=count, head=head, now=now, seq_end=seq_end, es=order)


def stats(x, nch, ch):
    v = x[ch::nch]
    return max(abs(s) for s in v), sum(s * s for s in v)


def close(a, b, tol=1e-5): return abs(a - b) <= tol * max(1.0, abs(b))


def layout_tests(ctx):
    expect = ctx.expect
    h = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'patch', 'vu.h')).read()
    d = {k: v for k, v in re.findall(r'#define (VU_\w+) (\S+)', h)}
    expect(d['VU_FILE'] == '"/tmp/m1plus-vu"' and d['VU_MAGIC'] == '"M1VU001"' and int(d['VU_RING']) == RING, 'vu.h: the file, the magic and the ring size')
    expect(VU.startswith('/tmp/'), 'the record lives on tmpfs')
    expect('sizeof(vu_entry) == 32' in h and 'sizeof(vu_record) == 40 + 32 * VU_RING + 8' in h and 'offsetof(vu_record, ring) == 40' in h, 'vu.h pins the sizes and the ring offset the tests decode')
    p = VP(); af = p.start_vu(); p.play(af, PEQ.tone(512, 2, 48000), 48000)
    expect(len(p.files[VU]) == HEAD + ENTRY * RING + TAIL, 'the record is 2096 bytes')
    r = rd(p)
    expect(r['magic'] == MAGIC and r['seq'] == r['seq_end'] and r['rate'] == 48000 and r['ch'] == 2 and r['count'] == 1 and r['head'] == 0, f'header: magic, seq == seq_end, rate, channels, one entry ({r["seq"]})')


def wanted_tests(ctx):
    expect = ctx.expect
    x = PEQ.tone(1024, 2, 48000)
    # no mark: one failed open a block, no write, no level, nothing created, the output's delay not asked
    p = VP(); af = p.start(48000)
    p.calls = []
    for _ in range(3): same, y = p.play(af, x, 48000)
    expect(p.vu_opens() == 3 and p.writes == 0 and VU not in p.files and y == x and not [c for c in p.calls if c[0] in ('fwrite', 'fclose')], 'no mark: one open a block (3 blocks, 3 opens), nothing written or created, samples untouched')
    # the mark's magic must be there
    for what, data in (('empty file', b''), ('wrong magic', b'M1VU000\0'), ('no NUL', b'M1VU001X'), ('short', MAGIC[:7])):
        p = VP({VU: bytearray(data)}); af = p.start(48000); p.play(af, x, 48000)
        expect(p.writes == 0 and bytes(p.files[VU]) == data, f'{what}: not the mark, nothing written')
    # the mark: the page's file with just the magic; the player extends it to the whole record
    p = VP(); af = p.start_vu(); w = p.writes; p.calls = []
    p.play(af, x, 48000)
    expect(w == 1 and p.writes == 2 and len(p.files[VU]) == 2096 and ('fclose', VU) in p.calls, 'the mark: the stream note and each block write the whole record once, the file closed')
    # the page closing (the file unlinked): measuring stops at the next block, nothing is made again
    del p.files[VU]; p.calls = []
    p.play(af, x, 48000)
    expect(VU not in p.files and p.writes == 2, 'the mark removed: nothing measured, nothing created')
    # the delay is asked only when wanted
    p = VP(delay=0.0); af = p.start(48000)
    p.u.mem_write(p.delay_at, struct.pack('<f', float('nan')))
    p.play(af, x, 48000)
    expect(p.writes == 0, 'not wanted: no write (the delay code is never run: a NaN there would show)')


def float_tests(ctx):
    expect = ctx.expect
    # known blocks: a constant, a sine, silence; the record keeps peak and sum of squares per channel, normalised to full scale
    n = 4800
    blk = [0.5, -0.25] * n
    p = VP(delay=0.0); p.clock = 123456; af = p.start_vu(); p.play(af, blk, 48000)
    r = rd(p); e = r['es'][0]
    expect(r['count'] == 1 and e['frames'] == n and e['dur'] == 100000 and e['pk'] == (0.5, 0.25) and close(e['sq'][0], n * 0.25) and close(e['sq'][1], n * 0.0625), f'constant block: peaks 0.5 / 0.25, sum of squares n/4 and n/16 ({e})')
    expect(e['due'] == 123456 * 1000 and r['now'] == 123456 * 1000, 'due = the time it was filtered (no output delay), now = the write time')
    x = PEQ.tone(n, 2, 48000, freqs=(997.0,), amp=0.8)
    p = VP(); af = p.start_vu(); _, y = p.play(af, x, 48000)
    e = rd(p)['es'][0]
    want = [stats(x, 2, c) for c in (0, 1)]
    expect(y == x and all(close(e['pk'][c], want[c][0]) and close(e['sq'][c], want[c][1]) for c in (0, 1)), f'a sine at 0.8: its peak and sum of squares (rms {math.sqrt(e["sq"][0] / n):.4f}), samples untouched')
    p = VP(); af = p.start_vu(); p.play(af, [0.0] * 2000, 48000)
    e = rd(p)['es'][0]
    expect(e['pk'] == (0.0, 0.0) and e['sq'] == (0.0, 0.0) and e['frames'] == 1000, 'silence: zeros (a level, not a missing record)')
    p = VP(); af = p.start_vu(); p.play(af, [float('nan'), 1.5, float('inf'), -2.0, -0.5, 0.25], 48000)
    e = rd(p)['es'][0]
    expect(e['pk'] == (0.5, 2.0) and close(e['sq'][0], 0.25) and close(e['sq'][1], 6.3125) and e['frames'] == 3, 'full scale is 1.0 (over shows as above 1.0); a NaN or infinity counts as 0')
    # after the stages: Mono Audio, Crossfeed and the EQ are in what is measured, nothing else is written
    x = PEQ.tone(4096, 2, 48000, freqs=(997.0, 61.0), amp=0.25)
    for what, files in (('Mono Audio', {STE.STEREO: STE.rec(1, 0)}), ('Crossfeed', {STE.STEREO: STE.rec(0, 3)}),
                        ('an EQ band', {STE.STATE: PEQ.pack_state(1, PEQ.pack_preset([(2, 0, 1000, 9.0, 1.0)], preamp=-2.0, automatic=2), b'x.txt')}),
                        ('all three', {STE.STEREO: STE.rec(1, 2), STE.STATE: PEQ.tenband([6.0] * 10, 0)})):
        p = VP(files); af = p.start_vu(); _, y = p.play(af, x, 48000)
        e = rd(p)['es'][0]
        ok = all(close(e['pk'][c], stats(y, 2, c)[0], 1e-6) and close(e['sq'][c], stats(y, 2, c)[1], 1e-4) for c in (0, 1))
        expect(ok and y != x, f'{what}: the levels are those of the block sent on (peaks {e["pk"][0]:.4f} / {e["pk"][1]:.4f})')
    # one channel: both meters get it; more than two: the first two
    x = PEQ.tone(2048, 1, 44100, freqs=(500.0,), amp=0.3)
    p = VP(); af = p.start_vu(44100, nch=1); _, y = p.play(af, x, 44100, nch=1)
    r = rd(p); e = r['es'][0]
    expect(r['ch'] == 1 and e['pk'][0] == e['pk'][1] and e['sq'][0] == e['sq'][1] and close(e['pk'][0], stats(x, 1, 0)[0]) and e['frames'] == 2048 and y == x, 'one channel: channels 1, both meters the same, the samples untouched')
    x = PEQ.tone(1200, 6, 48000, freqs=(300.0, 1100.0), amp=0.1)
    x = PEQ.f32([v * (i % 6 + 1) for i, v in enumerate(x)])
    p = VP(); af = p.start_vu(48000, nch=6); _, y = p.play(af, x, 48000, nch=6)
    r = rd(p); e = r['es'][0]
    expect(r['ch'] == 2 and all(close(e['pk'][c], stats(x, 6, c)[0]) for c in (0, 1)) and e['frames'] == 1200 and y == x, 'six channels: the first two are measured, nothing is written')


def exact_tests(ctx):
    expect = ctx.expect
    # everything off, bit for bit, wanted or not (float and the native pass-through)
    for mark in (False, True):
        for what, files in (('no record', {}), ('records with both off', {STE.STEREO: STE.rec(0, 0)})):
            xs = PEQ.tone(512, 2, 44100)
            p = VP(files); af = p.start_vu(44100) if mark else p.start(44100)
            expect(p.play(af, xs, 44100)[1] == xs, f'float, {what}, level tap {"on" if mark else "off"}: untouched')
            pcm = bytes((i * 37) & 255 for i in range(2048))
            p = VP(files); p.flag('0')
            if mark: p.watch()
            af = p.open(); r, _, data = p.reinit(af, 44100, fmt=S16, bps=2)
            same, out = p.play(af, None, 44100, fmt=S16, bps=2, raw=pcm)
            expect(r == 1 and same and out == pcm, f'native S16, {what}, level tap {"on" if mark else "off"}: the block is the very same bytes')


def native_tests(ctx):
    expect = ctx.expect
    n = 3000
    vals = [int(30000 * math.sin(i * 0.05)) for i in range(2 * n)]
    vals[1::2] = [v // 4 for v in vals[1::2]]
    cases = [('S16', S16, 2, struct.pack(f'<{2 * n}h', *vals), 32768.0, vals),
             ('S24', S24, 3, b''.join(struct.pack('<i', v * 256)[:3] for v in vals), 32768.0, vals),
             ('S32', S32, 4, struct.pack(f'<{2 * n}i', *[v * 65536 for v in vals]), 32768.0, vals),
             ('U8', U8, 1, bytes((v >> 8) + 128 for v in vals), 128.0, [v >> 8 for v in vals]),
             ('float', FLOAT, 4, struct.pack(f'<{2 * n}f', *[v / 32768 for v in vals]), 32768.0, vals)]
    for what, fmt, bps, raw, scale, ref in cases:
        p = VP(); p.flag('0'); p.watch()
        af = p.open(); r, _, data = p.reinit(af, 48000, fmt=fmt, bps=bps)
        same, out = p.play(af, None, 48000, fmt=fmt, bps=bps, raw=raw)
        rec = rd(p); e = rec['es'][0]
        want = [stats([v / scale for v in ref], 2, c) for c in (0, 1)]
        ok = all(close(e['pk'][c], want[c][0], 1e-5) and close(e['sq'][c], want[c][1], 1e-4) for c in (0, 1))
        expect(r == 1 and data[4] == fmt and out == raw and ok and e['frames'] == n and rec['rate'] == 48000 and rec['ch'] == 2,
               f'native {what}: accepted as it is, bytes untouched, peak {e["pk"][0]:.4f} / {e["pk"][1]:.4f} as the model ({want[0][0]:.4f} / {want[1][0]:.4f})')
    # full scale: -32768 is 1.0; a one-channel native stream
    raw = struct.pack('<4h', -32768, 32767, 0, -16384)
    p = VP(); p.flag('0'); p.watch(); af = p.open(); p.reinit(af, 48000, nch=1, fmt=S16, bps=2); p.play(af, None, 48000, nch=1, fmt=S16, bps=2, raw=raw)
    e = rd(p)['es'][0]
    expect(e['pk'] == (1.0, 1.0) and e['frames'] == 4 and e['sq'][0] == e['sq'][1] and close(e['sq'][0], 1 + (32767 / 32768) ** 2 + 0.25), 'one native channel: -32768 is 1.0, both meters the same')
    # Equalizer on with a flat curve and nothing else: the float path measures too (what the engine ran)
    p = VP(); p.watch(); af = p.start(48000); p.play(af, [0.5] * 400, 48000)
    expect(rd(p)['es'][0]['pk'] == (0.5, 0.5), 'Equalizer on, flat: float blocks are measured')
    # formats that cannot be measured pass untouched and publish nothing: big endian, a width that disagrees with bps, unsigned 16 bit, 8 bit signed, a special format
    for what, fmt, bps in (('S16 big endian', BE16, 2), ('S16 with bps 4', S16, 4), ('U16', 0x0b, 2), ('S8', 0x01, 1), ('IMA ADPCM-style special', 0x140, 2)):
        raw = bytes((i * 11) & 255 for i in range(1024))
        p = VP(); p.flag('0'); p.watch(); af = p.open(); p.reinit(af, 48000, fmt=fmt, bps=bps)
        same, out = p.play(af, None, 48000, fmt=fmt, bps=bps, raw=raw)
        expect(out == raw and bytes(p.files[VU])[:8] == MAGIC and not (len(p.files[VU]) > 8 and rd(p)['count']), f'{what}: untouched, no entry')
    # a block that does not match what REINIT agreed (rate, channels, format) or is cut off mid-frame is not measured
    raw = struct.pack('<8h', *range(1, 9))
    p = VP(); p.flag('0'); p.watch(); af = p.open(); p.reinit(af, 48000, fmt=S16, bps=2)
    p.play(af, None, 44100, fmt=S16, bps=2, raw=raw); p.play(af, None, 48000, nch=1, fmt=S16, bps=2, raw=raw); p.play(af, None, 48000, fmt=S16, bps=2, raw=raw[:-2])
    expect(p.writes == 1 and bytes(p.files[VU]) == bytes(p.files[VU])[:2096] and rd(p)['count'] == 0, 'a block of another rate, channel count or a cut frame: not measured (the one write is the REINIT note)')


def none_tests(ctx):
    expect = ctx.expect
    raw = bytes(range(256)) * 8
    # DSD: the bytes pass, no levels, the header says "none" (rate 0)
    for what, setup in (('dsdiff driver', lambda p: p.codec(drv='dsdiff')), ('FFmpeg ffdsd codec', lambda p: p.codec(name='ffdsd_msbf'))):
        for eq in (False, True):
            p = VP({STE.STEREO: STE.rec(1, 2)}); setup(p); p.flag('1' if eq else '0'); p.watch()
            af = p.open(); r, _, data = p.reinit(af, 352800, fmt=0x0a, bps=4)
            same, out = p.play(af, None, 352800, fmt=0x0a, raw=raw)
            rec = rd(p)
            expect(out == raw and rec['rate'] == 0 and rec['ch'] == 0 and rec['count'] == 0 and rec['seq'] == 1, f'{what}, Equalizer {"on" if eq else "off"}: untouched, rate 0 / channels 0, no entry')
    # a DSD file after a PCM one: the ring keeps the PCM end (still audible) while the header says none
    p = VP(); p.watch(); af = p.start(48000); p.play(af, PEQ.tone(2400, 2, 48000), 48000); old = rd(p)['es'][0]
    p.codec(drv='dsdiff'); af2 = p.open(); p.reinit(af2, 352800, fmt=0x0a, bps=4); p.play(af2, None, 352800, fmt=0x0a, raw=raw)
    rec = rd(p)
    expect(rec['rate'] == 0 and rec['es'] == [old], 'DSD after PCM: the earlier entries stay (they expire by their own times), the header drops to rate 0')
    # a rate out of the filter's range
    p = VP(); p.watch(); af = p.start(768000); xs = PEQ.tone(128, 2, 768000)
    expect(p.play(af, xs, 768000)[1] == xs and rd(p)['rate'] == 0 and rd(p)['count'] == 0, 'a rate past 384 kHz: untouched, no levels')
    # the kill switch: hands off, not even the check
    p = VP({KILL: b''}); p.watch(); af = p.start(48000); xs = PEQ.tone(512, 2, 48000); p.calls = []
    expect(p.play(af, xs, 48000)[1] == xs and p.vu_opens() == 0 and bytes(p.files[VU]) == MAGIC, 'kill switch: the file is never opened')


def timing_tests(ctx):
    expect = ctx.expect
    x = PEQ.tone(2400, 2, 48000)
    for delay, want in ((0.25, 250000), (0.0, 0), (0.0625, 62500)):
        p = VP(delay=delay); p.clock = 5000; af = p.start_vu(); p.play(af, x, 48000)
        e = rd(p)['es'][0]
        expect(e['due'] == 5000 * 1000 + want, f'output delay {delay} s: audible {want} us after the block was filtered')
    for what, mk in (('negative', lambda p: p.set_delay(-0.5)), ('NaN', lambda p: p.set_delay(float('nan'))), ('a wild 99 s', lambda p: p.set_delay(99.0)), ('no output', lambda p: p.no_output())):
        p = VP(); p.clock = 7000; mk(p); af = p.start_vu(); p.play(af, x, 48000)
        expect(rd(p)['es'][0]['due'] == 7000 * 1000, f'{what}: no delay is assumed')
    p = VP(); p.clock = 100; p.setword(p.mpctx() + 8, 0); af = p.start_vu(); p.play(af, x, 48000)
    expect(rd(p)['count'] == 1, 'mpctx without an output: still measured')
    # a delay that changes: each entry has its own time; the entries are in order
    p = VP(delay=0.1); p.clock = 1000; af = p.start_vu()
    for i in range(4):
        p.clock = 1000 + 100 * i; p.play(af, x, 48000)
    es = rd(p)['es']
    expect([e['due'] // 1000 for e in es] == [1100, 1200, 1300, 1400] and all(e['dur'] == 50000 for e in es), 'one entry a block, each stamped with its own time')
    # no new blocks: the sequence and the write time stand still; a block moves them
    p = VP(); af = p.start_vu(); p.clock = 2000; p.play(af, x, 48000); a = rd(p)
    p.clock = 9000
    b = rd(p)
    expect(a['seq'] == b['seq'] == a['seq_end'] and b['now'] == a['now'] == 2000000, 'pause or stop: nothing is written, seq and now_us stay (the page sees the stall)')
    p.play(af, x, 48000); c = rd(p)
    expect(c['seq'] == a['seq'] + 1 and c['now'] == 9000000, 'a new block: seq + 1 and now_us moves')
    # a new stream (REINIT) is a new sequence number with the new rate and channels
    af2 = p.open(); p.reinit(af2, 44100, nch=1)
    d = rd(p)
    expect(d['seq'] > c['seq'] and d['rate'] == 44100 and d['ch'] == 1 and d['es'] == c['es'], 'a stream starts: seq moves, the header has its rate and channels, the earlier entries stay')


def merge_tests(ctx):
    expect = ctx.expect
    # short blocks (128 frames, 2.67 ms) join into entries of at least 10 ms: four blocks make one
    x = PEQ.tone(128 * 40, 2, 48000, freqs=(440.0,), amp=0.5)
    p = VP(); p.clock = 1000; af = p.start_vu()
    for i in range(40):
        p.clock = 1000 + i * 2.6667; p.clock = int(p.clock); p.play(af, x[256 * i:256 * (i + 1)], 48000)
    r = rd(p); es = r['es']
    expect(len(es) == 10 and all(e['frames'] == 512 and e['dur'] == 10664 for e in es), f'40 blocks of 128 frames: 10 entries of 512 frames ({len(es)} entries, {es[0]["frames"]} frames)')
    ok = all(close(e['pk'][c], stats(x[1024 * k:1024 * (k + 1)], 2, c)[0]) and close(e['sq'][c], stats(x[1024 * k:1024 * (k + 1)], 2, c)[1], 1e-4) for k, e in enumerate(es) for c in (0, 1))
    expect(ok, 'a merged entry: the peak is the largest and the sums of squares add')
    # a gap (a pause, a seek) starts a new entry instead of stretching one
    p = VP(); p.clock = 1000; af = p.start_vu(); y = x[:256]
    p.play(af, y, 48000); p.clock = 1500; p.play(af, y, 48000)
    expect(rd(p)['count'] == 2, 'blocks 500 ms apart are two entries')
    # a new stream does not merge into the last entry of the old one
    p = VP(); p.clock = 1000; af = p.start_vu(); p.play(af, y, 48000); af2 = p.start(48000); p.play(af2, y, 48000)
    expect(rd(p)['count'] == 2, 'a new stream opens its own entry')
    # the ring wraps: 64 entries kept, the newest last
    p = VP(); af = p.start_vu(); big = PEQ.tone(960, 2, 48000, amp=0.1)
    for i in range(70):
        p.clock = 1000 + 25 * i; p.play(af, [v * (1 + i / 100) for v in big], 48000)
    r = rd(p)
    expect(r['count'] == RING and r['head'] == 69 % RING and [e['due'] // 1000 for e in r['es']] == [1000 + 25 * i for i in range(6, 70)], 'a ring of 64 entries: the oldest six dropped, entries in order, head at the newest')
    expect(r['seq'] == r['seq_end'] and r['seq'] == 70 + 1, f'seq counts every write (the stream note and 70 blocks: {r["seq"]})')


def art_tests(ctx):
    """tools/vu_art.py without the page: the layout's sanity, the VU -> angle law, the needle's dirty rectangles, and the installed pictures (their sizes, and that the
    built ones hold the generator's pixels)."""
    expect = ctx.expect
    wins, ok = A.WINDOWS, True
    for m in (0, 1):
        w = wins[m]; b = A.BOXES[m]
        ok = ok and (w[2] - w[0], w[3] - w[1]) == (A.DIAL_W, A.DIAL_H) and b[0] < w[0] and b[1] < w[1] and w[2] < b[2] and w[3] < b[3]
        ok = ok and A.PIVOTS[m] == (w[0] + 143, w[1] + 180) and A.PIVOTS[m][1] > w[3]
        hx, hy = A.HOOD_AT[m]; lx, ly = A.LAMP_AT[m]
        ok = ok and w[0] <= hx and hx + 84 <= w[2] and w[1] <= hy and hy + 18 <= w[3] and w[0] <= lx and lx + 33 <= w[2] and w[1] <= ly and ly + 31 <= w[3]
    expect(ok and wins[1][1] - wins[0][1] == A.METER_DY == 162, 'two 286 x 144 windows inside their frames, the pivots 36 px below them, the hood and lamp rectangles inside the windows')
    expect(A.PIVOTS == ((160, 211), (160, 373)) and A.R0 == 20 and A.R1 == 151 and A.SCALE_R == 139, 'pivots (160, 211) and (160, 373), the needle drawn over radius 20 .. 151')
    deg = math.degrees
    expect(abs(A.frac(3) - 1) < 1e-12 and abs(A.frac(0) - 10 ** -0.15) < 1e-12 and abs(A.frac(-20) - 0.0708) < 1e-4, 'the law 10^(VU/20) / 10^(3/20): +3 VU is full sweep, 0 VU 70.8 %, -20 VU 7.1 %')
    expect(abs(deg(A.angle(3)) - 46) < 1e-9 and abs(deg(A.angle(0)) - (-46 + 2 * 46 * 0.7079)) < 0.01 and abs(deg(A.angle(99)) - (-46 + 1.03 * 92)) < 1e-9 and abs(deg(A.angle(None)) + 48.5) < 1e-9,
           'the sweep is +-46 degrees, +3 VU at the end, 3 % past it at most, the rest 2.5 degrees before the start')
    # the dirty rectangles
    res = True
    for m in (0, 1):
        w = wins[m]
        for a in (A.REST, A.angle(-20), A.angle(0), A.angle(3), A.angle(99)):
            r = A.needle_rect(m, a)
            res = res and w[0] <= r[0] < r[2] <= w[2] and w[1] <= r[1] < r[3] <= w[3]
        r0, r1, u = A.needle_rect(m, A.angle(-5)), A.needle_rect(m, A.angle(1)), A.move_rect(m, A.angle(-5), A.angle(1))
        res = res and u[0] <= min(r0[0], r1[0]) and u[1] <= min(r0[1], r1[1]) and u[2] >= max(r0[2], r1[2]) and u[3] >= max(r0[3], r1[3])
    expect(res, 'needle_rect stays in the window at the rest and the sweep ends; move_rect holds both ends')
    # the reference needle: it writes only inside its rectangle, and it is dark on the axis and on the shadow side
    base = Image.new('RGBA', (A.W, A.H), (0xE0, 0xD0, 0xB0, 255)); im = base.copy(); a = A.angle(-2.4)
    A.draw_needle(im, 0, a); r = A.needle_rect(0, a)
    diff = ImageChops.difference(im, base).getbbox(alpha_only=False)
    expect(diff is not None and r[0] <= diff[0] and r[1] <= diff[1] and diff[2] <= r[2] and diff[3] <= r[3], 'the needle changes pixels only inside its dirty rectangle')
    px, py = A.PIVOTS[0]; mid = (px + 100 * math.sin(a), py - 100 * math.cos(a)); c = im.getpixel((int(mid[0]), int(mid[1])))
    expect(c[0] < 0x80, f'the needle is dark on its axis (r 100: {c})')
    # the pictures
    imgs = A.images()
    expect({n: im.size for n, im in imgs.items()} == {'vu_base': (320, 480), 'vu_hood': (84, 18), 'vu_lamp': (33, 31), 'vu_keys': (286, 58)} and tuple(imgs) == A.NAMES, 'the four pictures and their sizes')
    expect(imgs['vu_base'].getchannel('A').getextrema() == (255, 255) and imgs['vu_keys'].getchannel('A').getextrema() == (255, 255), 'the base and the key sheet are opaque')
    hood, lamp = imgs['vu_hood'].getchannel('A'), imgs['vu_lamp'].getchannel('A')
    expect(hood.getextrema()[1] == 255 and hood.getpixel((0, 0)) == 0 and lamp.getextrema()[1] == 255 and lamp.getpixel((0, 0)) == 0, 'the hood and the lamp are shaped: transparent at the corners, opaque inside')
    same = all(ImageChops.difference(asset_image(n), im).getbbox(alpha_only=False) is None for n, im in imgs.items())
    expect(same, 'the built pictures hold the generator\'s pixels')


# =============================================================================================================================================================
# The page (patch/vupage.c, tools/pod_ui.py build_vu_page, docs/modules/vu.md)
UI = os.path.join('rootfs', 'release/assets/default/raw/ui/m1plus_vu.bin')
EVT_DOWN, EVT_MOVE, EVT_UP, EVT_ABORT = O['EVT_POINTER_DOWN'], O['EVT_POINTER_MOVE'], O['EVT_POINTER_UP'], O['EVT_POINTER_ABORT']
EVT_BG, EVT_FG, EVT_DESTROY, EVT_PAINT = O['EVT_WINDOW_TO_BG'], O['EVT_WINDOW_TO_FG'], O['EVT_DESTROY'], O['EVT_AFTER_PAINT']
WIN = 0x24200000
SYSBAR = pod.DATA['SYSTEM_BAR'][0]
OUT = os.path.join(ROOT, 'out', 'preview')
LABELS = ('vu_title', 'vu_artist', 'vu_times', 'vu_status')
K_NONE, K_CLOSE, K_PREV, K_PLAY, K_NEXT, K_BODY = range(6)
OFF_M, SIZE_M = 144, 72   # patch/vupage.c: the offset of vu.m[] in the page's state, and sizeof(vp_meter): x, v, tgt, ad (doubles), drawn, r[4], lit, lvl, lvl_drawn, until
FULL = 10 ** (-11 / 20)   # the rms at +3 VU with the reference pinned at -14 dBFS rms (the default of every test but the auto level's: VUM.pin)
FS = 10 ** (-0.1 / 20)    # the PEAK lamp always lights from here, -0.1 dBFS (digital full scale)
REF0, REF_MIN, REF_MAX = -12.0, -24.0, -6.0   # the reference (dBFS rms at 0 VU): the start value on page open and the clamps
LT = lambda ref: 10 ** ((ref - 3) / 10)       # the long-term power that gives the reference ref (ref = lt + 3 dB)


def lamp_at(ref): return 10 ** ((ref + 8) / 20)   # the PEAK lamp's relative threshold: 8 dB above 0 VU
TICK_MAX = 1500000        # instructions of the heaviest tick: the Vinyl page's playing-tick budget (2.3 M per 50 ms, test/pod/vinyl.py motion_tests) at VU_TICK_MS, 2.3 M x 33 / 50
TOL_MAX, TOL_MANY = 2, 0  # the C frame against the reference renderer: no channel off by more than TOL_MAX, at most TOL_MANY channels off by more than 2


def deg(a): return math.degrees(a)


def ang(rms):
    """The needle's angle for an rms: tools/vu_art.py's law (linear in the voltage), written out."""
    return -A.SWEEP + min(1.03, rms / FULL) * 2 * A.SWEEP



def entry(due, dur, rms=(0.1, 0.1), peak=None, rate=48000):
    frames = int(dur * rate / 1e6)
    peak = peak or (min(1.0, rms[0] * 1.5), min(1.0, rms[1] * 1.5))
    return dict(due=due, dur=dur, frames=frames, pk=peak, sq=(rms[0] ** 2 * frames, rms[1] ** 2 * frames))


def record(es, now, rate=48000, ch=2, seq=5, seq_end=None, magic=MAGIC):
    ring = bytearray(ENTRY * RING)
    for i, e in enumerate(es): struct.pack_into('<qiiffff', ring, ENTRY * i, e['due'], e['dur'], e['frames'], e['pk'][0], e['pk'][1], e['sq'][0], e['sq'][1])
    return magic + struct.pack('<iiiiiiq', seq, rate, ch, len(es), len(es) - 1, 0, now) + bytes(ring) + struct.pack('<ii', seq if seq_end is None else seq_end, 0)


class VUM(Machine):
    """The machine plus what the page calls that the shared mocks do not know (as test/pod/vinyl.py's VM): the player, the playing time, the quick clicks, the status bar, the invalidate; and the
    level file (fopen / fread / fwrite / fclose / unlink of VU_FILE answered on `vufile`) and the monotonic clock (`mono_us`, in step with time_now_ms)."""
    def __init__(self):
        super().__init__()
        self.status, self.pt, self.cmds, self.rects = 2, None, [], []
        self.window = WIN
        self.load_image = 0
        self.canvas = self.alloc(0x80)
        for w in ('vu_view', 'label_volume') + LABELS: Machine.widget(self, w)
        self.setword(SYSBAR, self.alloc(0x80))
        self.volume = '42'
        self.wall = 1800000000 + 13 * 3600 + 7 * 60
        self.tz = 8 * 3600
        self.mock_ms = 1000
        self.mono_us = 5000000000
        self.vufile, self.vh, self.feed, self.log = None, {}, None, []
        self.mark_fail = False   # True: VU_FILE cannot be created (fopen "wb" answers NULL)
        self.pin = -14.0   # the reference every call of the page's look is made at (dBFS rms at 0 VU; None: the page's automatic level runs)
        self.view = self.widgets['vu_view']
        win = self.alloc(0x80)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, 0)): self.setword(win + off, v)
        for off, v in ((0, 0), (4, 0), (8, 320), (0xc, 480), (0x44, win)): self.setword(self.view + off, v)
        self.images = {n: (im.width, im.height, im.tobytes()) for n, im in ((n, asset_image(n)) for n in A.NAMES)}
        for n in ('mclGetPlayStatus', 'playpause_quick_click', 'next_quick_click', 'prev_quick_click', 'get_playtimeandlength', 'widget_get_text', 'time_now_ms'):
            self.handlers[pod.FUNCTIONS[n][2]] = n
        for n in ('sba_rec_track', 'sba_rec_cover'): self.handlers[PSYMS[n]] = n

    def set_ref(self, ref):
        """The page's reference level (vp_lv: lt, peg, fast) set to the reference ref dBFS, the quick-rise state cleared."""
        self.u.mem_write(PSYMS['vp_lv.0'], struct.pack('<dii', LT(ref), 0, 0))

    def ref(self):
        lt, peg, fast = struct.unpack('<dii', bytes(self.u.mem_read(PSYMS['vp_lv.0'], 16)))
        return 10 * math.log10(lt) + 3

    def lv(self):
        return struct.unpack('<dii', bytes(self.u.mem_read(PSYMS['vp_lv.0'], 16)))

    def call(self, addr, *a, **k):
        if self.pin is not None and addr in (PSYMS['vp_tick'], PSYMS['vp_first'], PSYMS['vp_on_touch']): self.set_ref(self.pin)
        return super().call(addr, *a, **k)

    def reading(self, i, key='tgt'):
        """The VU a needle's target (or its angle: key 'x') stands for at the page's present reference: the angle is linear in the voltage, +3 VU at the end of the sweep."""
        f = (self.needle(i)[key] + A.SWEEP) / (2 * A.SWEEP)
        return 3 + 20 * math.log10(f) if f > 1e-9 else -99.0

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address, '')
        a0, a1, a2, a3 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        ret = None
        if name == 'mclGetPlayStatus': ret = self.status
        elif name == 'sba_rec_track': ret = self.cstr('')
        elif name == 'sba_rec_cover': ret = 0xffffffff
        elif name == 'time_now_ms': ret = self.mock_ms
        elif name == 'clock_gettime':
            self.log.append(('clock_gettime', a0))
            if a0 != 1: ret = 0xffffffff
            else: self.setword(a1, self.mono_us // 1000000); self.setword(a1 + 4, self.mono_us % 1000000 * 1000); ret = 0
        elif name == 'fopen' and self.read_cstr(a0) == VU:
            mode = self.read_cstr(a1); self.calls.append(('fopen', VU, mode)); self.log.append(('fopen', mode))
            made = 'w' not in mode or not self.mark_fail
            if 'w' in mode and made: self.vufile = bytearray()
            ret = 0
            if made and self.vufile is not None: ret = self.alloc(4); self.vh[ret] = 0
        elif name in ('fread', 'fwrite', 'fclose', 'fseek') and (a0 if name in ('fclose', 'fseek') else a3) in self.vh:
            h = a0 if name in ('fclose', 'fseek') else a3
            if name == 'fread':
                chunk = bytes(self.vufile[self.vh[h]:self.vh[h] + a1 * a2]); self.u.mem_write(a0, chunk) if chunk else None; self.vh[h] += len(chunk); ret = len(chunk) // a1
            elif name == 'fwrite':
                chunk = bytes(self.u.mem_read(a0, a1 * a2)); self.vufile[self.vh[h]:self.vh[h] + len(chunk)] = chunk; self.vh[h] += len(chunk); self.log.append(('fwrite', chunk)); ret = len(chunk) // a1
            elif name == 'fclose': self.vh.pop(h); ret = 0
            else: ret = 0
        elif name == 'unlink' and self.read_cstr(a0) == VU:
            self.calls.append(('unlink', VU)); self.log.append(('unlink',)); self.vufile = None; ret = 0
        elif name == 'playpause_quick_click':
            self.calls.append(('playpause_quick_click',)); self.cmds.append(('playpause',)); self.status = 2 if self.status != 2 else 3; ret = 1
        elif name in ('next_quick_click', 'prev_quick_click'):
            self.calls.append((name, a1)); self.cmds.append((name[:4], self.word(a0 + 8), a1)); ret = 1
        elif name == 'get_playtimeandlength':
            if self.pt: self.setword(a0, self.pt[0]); self.setword(a1, self.pt[1])
            ret = 1 if self.pt else 0
        elif name == 'widget_get_text':
            ret = self.alloc(4 * len(self.volume) + 4); self.u.mem_write(ret, struct.pack(f'<{len(self.volume) + 1}I', *map(ord, self.volume), 0))
        elif name == 'widget_invalidate_force':
            self.rects.append(tuple(struct.unpack('<4i', self.u.mem_read(a1, 16))) if a1 else None)
        if ret is None: return super()._hook(u, address, size, _)
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def playing(self, title='Midnight City', artist='M83', album='Hurry Up', pos=200, length=243, path='/mnt/mmc/m/midnight.flac'):
        self.play([self.record(album=album, artist=artist, path=path, title=title, name=os.path.basename(path))], 0)
        self.pt = (pos, length)

    def open(self):
        self.calls = []
        return self.call(PSYMS['vupage_open'], count=60000000) & 0xffffffff

    def open_idle(self):
        self.calls = []
        return self.call(PSYMS['vupage_open_idle'], count=60000000) & 0xffffffff

    def first(self):
        self.calls = []; self.rects = []
        self.call(PSYMS['vp_first'], a0=0, count=400000000)

    def signal(self, left, right=None, pl=None, pr=None):
        """The player writes a block every tick from now on: rms left / right (None: no signal), peaks (default 1.5 x rms)."""
        right = left if right is None else right
        self.feed = None if left is None else (left, right, None if pl is None else (pl, pl if pr is None else pr))

    def write_feed(self):
        l, r, pk = self.feed
        self.vufile = bytearray(record([entry(self.mono_us - 50000, 100000, (l, r), pk)], self.mono_us))

    def tick(self, ms=50):
        self.mock_ms += ms; self.mono_us += ms * 1000
        if self.feed and self.vufile is not None: self.write_feed()
        self.calls = []; self.rects = []
        self.call(PSYMS['vp_tick'], a0=0, count=400000000)

    def paint(self):
        ev = self.paint_event()
        self.blits = []
        self.call(PSYMS['vp_on_paint'], a0=0, a1=ev, count=2000000)
        return list(self.blits)

    def frame(self):
        data, w, h = [v for v in self.bitmaps.values() if v[1:] == (320, 480)][-1]
        return Image.frombytes('RGBA', (w, h), bytes(self.u.mem_read(data, w * h * 4)))

    def needle(self, i):
        at = PSYMS['vu'] + OFF_M + SIZE_M * i
        x, v, tgt, ad = struct.unpack('<4d', bytes(self.u.mem_read(at, 32)))
        drawn, *r = struct.unpack('<5i', bytes(self.u.mem_read(at + 32, 20)))
        lit, lvl, lvl_drawn = struct.unpack('<3i', bytes(self.u.mem_read(at + 52, 12)))
        return dict(x=x, v=v, tgt=tgt, ad=ad, drawn=drawn, r=tuple(r), lit=lit, lvl=lvl, lvl_drawn=lvl_drawn)

    def unkick(self):
        """The needles' opening kick taken away (speed 0), so a test can start from a still needle."""
        for i in (0, 1): self.u.mem_write(PSYMS['vu'] + OFF_M + SIZE_M * i + 8, struct.pack('<d', 0.0))

    def text_of(self, name):
        t = [c[2] for c in self.calls_all if c[0] == 'widget_set_text_utf8' and c[1] == self.widgets[name]]
        return t[-1] if t else None

    def ptr(self, kind, x, y, t=0):
        e = self.alloc(0x30); self.u.mem_write(e, bytes(0x30))
        self.setword(e, {'down': EVT_DOWN, 'move': EVT_MOVE, 'up': EVT_UP, 'abort': EVT_ABORT}[kind]); self.setword(e + 8, t); self.setword(e + 0x18, x); self.setword(e + 0x1c, y)
        self.calls = []; self.rects = []
        return self.call(PSYMS['vp_on_touch'], a0=0, a1=e, count=200000000)

    def gesture(self, a, b, t=1000):
        calls = []
        self.ptr('down', *a, t); calls += self.calls
        for i in range(1, 4):
            self.ptr('move', a[0] + (b[0] - a[0]) * i // 4, a[1] + (b[1] - a[1]) * i // 4, t + 20 * i); calls += self.calls
        self.ptr('up', *b, t + 100); self.calls = calls + self.calls
        return list(self.calls)


def machine(playing=True, status=2, pin=-14.0, **kw):
    m = VUM(); m.status = status; m.pin = pin
    if playing: m.playing(**kw)
    return m


def opened(settle=False, kick=False, **kw):
    """The page open and drawn once (the opening kick taken off the needles unless kick: tests that start from a still needle)."""
    m = machine(**kw)
    assert m.open() == 0
    m.timers = []
    m.calls_all = []
    m.first(); m.calls_all += m.calls
    if not kick: m.unkick()
    return m


_REF = {}
def reference(vu, peak=(False, False), playing=True):
    """tools/vu_art.py compose (the generator's own pictures, the reference needle) for needles at the levels vu (dB; None: parked) and lamps lit as peak says."""
    key = (tuple(vu), tuple(peak), playing)
    if key not in _REF:
        if 'imgs' not in _REF: _REF['imgs'] = A.images()
        _REF[key] = A.compose(dict(playing=playing, vu=list(vu), peak=list(peak)), _REF['imgs'])
    return _REF[key]


def vu_of(rms, ref=-14.0): return 20 * math.log10(rms) - ref


def compare(a, b, box=None):
    """(the largest channel difference, the number of channels that differ by more than 2) of two RGBA frames, over `box` (default all)."""
    d = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
    if box: d = d.crop(box)
    h = d.histogram()
    big = sum(sum(h[256 * c + 3:256 * (c + 1)]) for c in range(3))
    top = max((i for c in range(3) for i in range(256) if h[256 * c + i]), default=0)
    return top, big


def side():
    import preview_icons as PI
    return PI.Side(WORK, True)


def dump(m, name, f):
    """out/preview/vu-emu-<name>.png: the emulated frame with the labels' text drawn as the AWTK labels draw it."""
    os.makedirs(OUT, exist_ok=True)
    im = m.frame().convert('RGBA')
    A.text(side(), im, f)
    im.convert('RGB').save(os.path.join(OUT, f'vu-emu-{name}.png'))


def settle(m, n=60, ms=10):
    for _ in range(n): m.tick(ms)


def page_tests(ctx):
    """The asset, the open and close, the mark."""
    expect = ctx.expect
    tree = awtk_ui.parse(open(os.path.join(WORK, UI), 'rb').read())
    expect(tree.name == 'm1plus_vu_page' and tree.get('fullscreen') == 'true', 'the window is fullscreen (480 px, the status bar not drawn)')
    by = {w.name: w for w in tree.walk() if w.name}
    v = by['vu_view']
    expect((v.x, v.y, v.w, v.h) == (0, 0, 320, 480) and v.get('sensitive') != 'false' and v.get('visible') != 'false' and tree.children[0] is v, 'vu_view is the whole window, first, and takes the touches')
    for name, field, dx in (('vu_title', 'title', 0), ('vu_artist', 'artist', 0), ('vu_times', 'times', 0), ('vu_status', 'status', 0)):
        w = by[name]; x, y, bw, bh = A.label_box(field); t = A.TEXT[field]
        expect(w.type == 'hscroll_label' and (w.x, w.y, w.w, w.h) == (x + dx, y, bw, bh) and w.get('sensitive') == 'false' and w.get('ellipses') == 'true' and w.get('only_parent_focus') == 'true'
               and w.get('style:normal:font_size') == str(t['px']) and w.get('style:normal:text_color') == '#%02X%02X%02X' % t['rgb'], f'{name}: an insensitive, non-scrolling label with an ellipsis at {(x + dx, y, bw, bh)}, {t["px"]} px')
    expect('vu_title2' not in by and by['vu_title'].get('style:normal:font_name') is None, 'no twin label; the title\'s font is the payload\'s to set (ly_title_face)')
    expect(by['label_title'].get('visible') == 'false' and by['label_title'].get('sensitive') == 'false' and by['label_title'].get('tr_text') == 'VU Meter Mode', 'label_title (hidden) carries the page\'s name')
    root = asset_tree(os.path.join(WORK, UI)); root.h = 480
    for x, y in ((160, 240), (5, 5), (246, 449), (30, 367), (315, 475)):
        expect(stock_target(Machine(), root, x, y)[-1] == 'vu_view', f'a touch at ({x}, {y}) reaches vu_view (the labels are insensitive)')
    order = pod_pages.PAGE_ORDER
    expect(order.index('m1plus_vu') == order.index('m1plus_general') - 1 and pod_pages.PAGES[pod_pages.page_index('m1plus_vu')] is pod_pages.VU_PAGE, 'the page sits just before General in PAGE_ORDER (the pages pinned from the end keep their places)')
    # opens, the mark
    m = machine(); m.vufile = None
    expect(m.open() == 0 and ('window_open', 'm1plus_vu') in m.calls, 'the page opens')
    expect(m.vufile == bytearray(MAGIC) and ('fopen', VU, 'wb') in m.calls and ('fwrite', MAGIC) in m.log, f'open creates the mark: VU_FILE holding just VU_MAGIC ({bytes(m.vufile)})')
    on = {(a, e) for _, a, e, f, x in (c for c in m.calls if c[0] == 'widget_on')}
    expect(on == {(m.view, EVT_DOWN), (m.view, EVT_UP), (m.view, EVT_ABORT), (m.view, EVT_PAINT), (WIN, EVT_DESTROY), (WIN, EVT_BG), (WIN, EVT_FG)}, 'the view takes down, up, abort and its paint; the window its three events')
    expect(len(m.bitmaps) == 5 and m.names().count('timer_add') == 1 and ('timer_add', PSYMS['vp_first'], O['VN_FIRST_MS']) in m.calls, 'five bitmaps (frame, base, keys, hood, lamp); one 50 ms one-shot')
    m.vufile = bytearray(record([entry(1, 1)], 2))
    expect(m.open() == 0 and 'window_open' not in m.names() and bytes(m.vufile) == record([entry(1, 1)], 2), 'opening again while it is up does nothing (the record is not touched)')
    # the mark's reader: the player's own check (patch/vu.c vu_open) accepts what the page wrote
    m = machine(); m.open(); w = m.vufile
    expect(len(w) == 8 and bytes(w) == MAGIC and VU == '/tmp/m1plus-vu', 'the mark is exactly what the player\'s check reads: 8 bytes, "M1VU001" and its NUL, on tmpfs')
    # close: destroy unlinks it; another window's destroy does not
    m.timers = []; m.first()
    fn, cx = m.bound[(WIN, EVT_DESTROY)]
    m.calls = []; m.call(fn, a0=WIN + 8, a1=0)
    expect(m.vufile is not None and 'bitmap_destroy' not in m.names(), 'another window\'s destroy leaves the page and its mark alone')
    m.calls = []; m.call(fn, a0=cx, a1=0)
    expect(m.vufile is None and ('unlink', VU) in m.calls and m.names().count('bitmap_destroy') == 5 and len(m.bitmaps) == 0, 'destroy: the mark is unlinked, the five bitmaps freed')
    m.timers = []; m.calls = []
    expect(m.open() == 0 and m.vufile == bytearray(MAGIC) and ('window_open', 'm1plus_vu') in m.calls, 'the state is clean: it opens again and makes the mark again')
    # a failed open leaves no mark
    for what, mk in (('a window that will not open', lambda m: m.windows.update({'m1plus_vu': 0})), ('no vu_view', lambda m: m.widgets.pop('vu_view')), ('a picture that will not load', lambda m: setattr(m, 'load_image', 1)),
                     ('no memory', lambda m: setattr(m, 'bitmap_ok', False))):
        m = machine(); mk(m)
        expect(m.open() == 0xffffffff and m.vufile is None and len(m.bitmaps) == 0 and 'timer_add' not in m.names(), f'{what}: -1, no mark, nothing allocated')
    for n in A.NAMES:
        m = machine(); m.images[n] = (10, 10, bytes(400))
        expect(m.open() == 0xffffffff and m.vufile is None and len(m.bitmaps) == 0 and 'navigator_back' in m.names(), f'{n} of another size is refused, every bitmap freed, no mark')
    # a stale mark and the boot
    m = machine(); m.vufile = bytearray(record([entry(1, 1)], 2)); m.call(PSYMS['vupage_boot'], count=100000)
    expect(m.vufile is None and ('unlink', VU) in m.calls, 'demo start: a mark (and record) left by an earlier run is unlinked')
    HM = sibling('home')
    m = Machine(); m.fs = {}; HM.boot(m)
    expect(('unlink', VU) in m.calls, 'home_boot, the existing boot hook, calls it')
    # the idle-opened variant
    m = machine(status=3); expect(m.open_idle() == 0 and m.vufile == bytearray(MAGIC), 'the idle open makes the mark too')


def level_tests(ctx):
    """The record the page reads: which entry is audible, what parks the needles, and the needle's target."""
    expect = ctx.expect
    # a signal: the needles go to the law's angles
    for left, right in ((0.1995, 0.0200), (0.2818, 0.5), (0.0, 0.05), (0.6, 0.1)):
        m = opened(); m.signal(left, right); settle(m, 150, 10)
        n0, n1 = m.needle(0), m.needle(1)
        expect(abs(n0['x'] - ang(left)) < 1e-6 and abs(n1['x'] - ang(right)) < 1e-6 and abs(n0['ad'] - n0['x']) < math.radians(0.05) + 1e-9,
               f'rms {left} / {right}: the needles settle at {deg(ang(left)):.2f} / {deg(ang(right)):.2f} degrees ({deg(n0["x"]):.2f} / {deg(n1["x"]):.2f}); 0 VU (rms {10 ** (-14 / 20):.4f}) is at {deg(A.angle(0)):.2f}')
    expect(abs(ang(10 ** (-14 / 20)) - A.angle(0)) < 1e-9 and abs(ang(FULL) - A.angle(3)) < 1e-9 and abs(ang(10 ** (-34 / 20)) - A.angle(-20)) < 1e-9 and abs(ang(1.0) - A.angle(99)) < 1e-9, 'the page\'s law is vu_art.angle: 0 VU = -14 dBFS rms, +3 VU the end, -20 VU, over +3 stops 3 % past the end')
    # the rms is sqrt(sumsq / frames) of the entries audible since the last tick
    m = opened(); t = m.mono_us + 50000
    m.mock_ms += 50; m.mono_us = t
    m.vufile = bytearray(record([entry(t - 90000, 40000, (0.9, 0.9)), entry(t - 50000, 50000, (0.05, 0.2))], t))   # the loud one ended before the window; the current ones
    m.calls = []; m.call(PSYMS['vp_tick'], a0=0, count=400000000)
    expect(abs(m.needle(0)['tgt'] - ang(0.05)) < 1e-5 and abs(m.needle(1)['tgt'] - ang(0.2)) < 1e-5, 'an entry that ended before the window is not looked at: the audible one gives the target')
    m.mock_ms += 50; m.mono_us += 50000; t = m.mono_us
    m.vufile = bytearray(record([entry(t - 40000, 20000, (0.3, 0.3)), entry(t - 20000, 20000, (0.1, 0.1)), entry(t + 30000, 20000, (0.9, 0.9))], t))
    m.call(PSYMS['vp_tick'], a0=0, count=400000000)
    want = math.sqrt((0.3 ** 2 * 960 + 0.1 ** 2 * 960) / 1920)
    expect(abs(m.needle(0)['tgt'] - ang(want)) < 1e-4, f'two entries audible in the tick\'s window: their sums of squares and frames added ({want:.4f}); an entry not yet audible is ignored')
    # parked: no signal
    def parked(what, mk, after=None):
        m = opened(); m.signal(0.1995); settle(m, 150, 10)
        up = abs(m.needle(0)['x'] - A.angle(0)) < 1e-3
        mk(m)
        settle(m, 150, 10)
        if after: after(m)
        n = m.needle(0)
        expect(up and abs(n['x'] - A.REST) < 1e-6 and abs(m.needle(1)['x'] - A.REST) < 1e-6 and n['tgt'] == A.REST, f'{what}: the needles fall back to the rest ({deg(A.REST):.1f} degrees, {deg(n["x"]):.2f})')
        return m
    parked('the player writes nothing more (paused, stopped, no new block)', lambda m: m.signal(None))
    parked('rate 0 (DSD, a special format)', lambda m: (m.signal(None), setattr(m, 'vufile', bytearray(record([entry(m.mono_us - 50000, 100000, (0.3, 0.3))], m.mono_us, rate=0, ch=0))), setattr(m, 'mono_us', m.mono_us)))
    parked('the kill switch (only the mark in the file)', lambda m: (m.signal(None), setattr(m, 'vufile', bytearray(MAGIC))))
    parked('no file at all', lambda m: (m.signal(None), setattr(m, 'vufile', None)))
    parked('a wrong magic', lambda m: (m.signal(None), setattr(m, 'vufile', bytearray(b'M1VU000\0' + bytes(2088)))))
    parked('a stalled record: now_us older than VU_STALL_MS although its entry still covers now', lambda m: (m.signal(None), setattr(m, 'vufile', bytearray(record([entry(m.mono_us - 50000, 3000000, (0.3, 0.3))], m.mono_us - 600000)))))
    m = opened(); m.signal(0.3); settle(m, 30, 10); m.status = 3
    m.tick(10)
    expect(m.needle(0)['tgt'] == A.REST, 'a known paused player: parked at once, with a fresh record')
    settle(m, 150, 10)
    expect(abs(m.needle(0)['x'] - A.REST) < 1e-6, 'and the needles fall there')
    m.status = 2; m.tick(10); m.tick(10)
    expect(abs(m.needle(0)['tgt'] - ang(0.3)) < 1e-5, 'resumed: the needle follows the record again')
    # a torn read keeps what the page knew: seq != seq_end on every read
    m = opened(); m.signal(0.2); settle(m, 30, 10); a = m.needle(0)['tgt']
    m.signal(None); m.mono_us += 10000; m.mock_ms += 10
    m.vufile = bytearray(record([entry(m.mono_us - 50000, 100000, (0.05, 0.05))], m.mono_us, seq=7, seq_end=8))
    m.calls = []; m.call(PSYMS['vp_tick'], a0=0, count=400000000)
    expect(m.needle(0)['tgt'] == a and len([c for c in m.calls if c[:2] == ('fopen', VU)]) == 3, 'a record that never reads consistent (seq 7, seq_end 8): three tries, then the last target is kept')
    # the clock is the monotonic one: clock_gettime(CLOCK_MONOTONIC) once a tick
    expect(m.log.count(('clock_gettime', 1)) >= 1 and all(c[1] == 1 for c in m.log if c[0] == 'clock_gettime'), 'CLOCK_MONOTONIC (1) is the clock asked')
    # nothing playing: the record is not even opened
    m = opened(playing=False, status=3); m.signal(0.3); m.tick(50)
    expect(m.needle(0)['tgt'] == A.REST, 'nothing playing: parked')


def step_tests(ctx):
    """The needle's step response."""
    expect = ctx.expect
    m = opened(); m.signal(0.2818); m.tick(1)
    x0, tg = A.REST, ang(0.2818)
    fr = []
    for i in range(1, 100): m.tick(10); fr.append((m.needle(0)['x'] - x0) / (tg - x0))
    t99 = next(i for i, f in enumerate(fr) if f >= 0.99) + 1
    over = max(fr) - 1
    expect(280 <= t99 * 10 + 1 <= 320, f'a step to +3 VU: 99 % reached at {t99 * 10 + 1} ms (the aim is 300)')
    expect(0.004 <= over <= 0.016, f'overshoot {over * 100:.2f} % (the aim is about 1 %)')
    expect(abs(fr[-1] - 1) < 1e-3 and all(f < 1.02 for f in fr), 'and it settles on the target')
    # the real elapsed time: the same 500 ms in 10 ms ticks or 100 ms ticks (the cap) arrives at the same place
    a, b = opened(), opened()
    for q in (a, b): q.signal(0.1995)
    for _ in range(5): a.tick(100)
    for _ in range(50): b.tick(10)
    expect(abs(a.needle(0)['x'] - b.needle(0)['x']) < 1e-9, 'the model is stepped by the elapsed time: 5 ticks of 100 ms = 50 ticks of 10 ms')
    c = opened(); c.signal(0.1995); c.tick(1000)
    d = opened(); d.signal(0.1995); d.tick(O['VN_DT_MAX'])
    expect(abs(c.needle(0)['x'] - d.needle(0)['x']) < 1e-9, f'a tick after a stall moves things as VN_DT_MAX ({O["VN_DT_MAX"]} ms) would')
    # no signal: the same model back to the rest
    m = opened(); m.signal(0.2818); settle(m, 150, 10)
    m.signal(None); m.vufile = bytearray(MAGIC); m.tick(1)   # (the record stops at once: the entries of the last block would still cover 50 ms)
    x1 = m.needle(0)['x']; fr = []
    for i in range(1, 100): m.tick(10); fr.append((m.needle(0)['x'] - x1) / (A.REST - x1))
    t99 = next(i for i, f in enumerate(fr) if f >= 0.99) + 1
    expect(280 <= t99 * 10 + 1 <= 330 and max(fr) < 1.02, f'falling to the rest takes the same {t99 * 10 + 1} ms to 99 %')
    # a long silence: no denormals (the tail lands), the state stands still
    settle(m, 20, 100)
    n = m.needle(0)
    expect(n['x'] == A.REST and n['v'] == 0.0, 'parked: the needle is at the rest exactly, speed 0 (never a denormal tail)')


def kick_tests(ctx):
    """The needles' swing when the page opens: a kick of VP_KICK through the ballistics."""
    expect = ctx.expect
    K = 13.62
    wd = 14.05 * math.sqrt(1 - 0.826 ** 2); tp = math.atan2(wd, 0.826 * 14.05) / wd
    want = math.radians(-46 + 10 ** (-13 / 20) * 92) - A.REST   # the -10 VU mark above the rest
    expect(abs(K * math.exp(-0.826 * 14.05 * tp) * math.sin(wd * tp) / wd - want) < 0.001 and abs(tp - 0.0756) < 0.0005, f'VP_KICK {K}: the peak of the damped swing is the -10 VU mark ({math.degrees(want):.1f} degrees above the rest) at {tp * 1000:.0f} ms')
    for path in ('open', 'open_idle'):
        m = machine(status=3); m.signal(None)
        expect(getattr(m, path)() == 0, f'{path} opens')
        m.timers = []; m.first()
        n = [m.needle(0), m.needle(1)]
        expect(all(q['x'] == A.REST and abs(q['v'] - K) < 1e-9 for q in n), f'{path}: both needles at the rest with the kick speed {K} rad/s')
        xs, drawn = [], []
        for _ in range(100):
            m.tick(10); xs.append(m.needle(0)['x']); drawn.append(m.needle(1)['ad'])
        peak = max(xs); at = (xs.index(peak) + 1) * 10
        expect(abs(peak - A.REST - want) < 0.01 and 70 <= at <= 80, f'{path}: no signal: the needle peaks {math.degrees(peak - A.REST):.1f} degrees above the rest (the -10 VU mark: {math.degrees(want):.1f}) at {at} ms')
        back = next(i for i, x in enumerate(xs) if i > 10 and x == A.REST) * 10 + 10
        expect(back <= 700 and min(xs) >= A.REST and min(drawn) >= A.REST and all(x == A.REST for x in xs[back // 10:]), f'{path}: back at the rest at {back} ms (within 700), never under it, still afterwards')
        q = m.needle(0)
        expect(q['v'] == 0.0 and q['ad'] == A.REST and q['r'] == tuple(A.needle_rect(0, A.REST)), f'{path}: drawn at the rest, speed 0 (no denormal tail)')
        expect(m.needle(1)['x'] == A.REST, f'{path}: both meters swing')
    # the kick is in the ballistics, not an animation: the speed halves the rise to a signal
    a, b = opened(kick=True), opened()
    for q in (a, b): q.signal(0.2818); q.tick(30)
    expect(a.needle(0)['x'] > b.needle(0)['x'] + 0.05, 'with a signal the kick joins the level: it rises faster than from standing')
    for _ in range(200): a.tick(10); b.tick(10)
    expect(abs(a.needle(0)['x'] - b.needle(0)['x']) < 0.001 and abs(a.needle(0)['x'] - ang(0.2818)) < 0.005, 'and ends on the same level')
    # the rest as the clamp: a needle falling past it stops on it
    m = opened(); m.signal(0.2818); settle(m, 100, 10); m.signal(None); m.vufile = bytearray(MAGIC)
    xs = []
    for _ in range(100): m.tick(10); xs.append(m.needle(0)['x'])
    expect(min(xs) >= A.REST and xs[-1] == A.REST, 'a fall to the rest never goes under it')


def lamp_tests(ctx):
    expect = ctx.expect
    # the reference pinned at -20 dBFS: the lamp is 8 dB above 0 VU, -12 dBFS (0.251)
    thr = lamp_at(-20.0)
    expect(abs(thr - 10 ** (-12 / 20)) < 1e-12 and abs(FS - 0.98855) < 1e-5, f'the lamp rule at ref -20: ref + 8 dB = -12 dBFS ({thr:.4f}); always from -0.1 dBFS ({FS:.5f})')
    m = opened(pin=-20.0); m.signal(0.1, 0.1, 0.2, 0.2); settle(m, 5, 10)
    expect(not m.needle(0)['lit'] and not m.needle(1)['lit'], 'peak -14 dBFS (ref + 6 dB): the PEAK lamps stay off')
    m.signal(0.1, 0.1, thr - 0.002, thr - 0.002); m.tick(10)
    expect(not m.needle(0)['lit'], 'just under ref + 8 dB: off')
    m.signal(0.1, 0.1, thr + 0.002, 0.2); m.tick(10)
    expect(m.needle(0)['lit'] and not m.needle(1)['lit'], 'at or over ref + 8 dB in the left channel: the left lamp lights, the right stays off')
    t_lit = m.mock_ms
    lamp0 = A.LAMP_AT[0]
    px = m.frame().getpixel((lamp0[0] + 16, lamp0[1] + 16))
    expect(px[0] > 0xC0 and px[1] < 0x80, f'the lit lamp is drawn (the centre {px[:3]} is red)')
    m.signal(0.1, 0.1, 0.2, 0.2)
    for _ in range(3): m.tick(100)
    expect(m.needle(0)['lit'] and m.needle(0)['lvl'] == 255 and m.mock_ms - t_lit == 300, 'held: still fully lit 300 ms after the peak')
    m.tick(100)
    expect(m.mock_ms - t_lit == 400 and not m.needle(0)['lit'], 'the hold ends after 400 ms (VU_HOLD_MS)')
    m.tick(60)
    mid = m.frame().getpixel((lamp0[0] + 16, lamp0[1] + 16))
    base = asset_image('vu_base').getpixel((lamp0[0] + 16, lamp0[1] + 16))
    lit_px = reference([vu_of(0.1, -20.0)] * 2, (True, False)).getpixel((lamp0[0] + 16, lamp0[1] + 16))
    expect(0 < m.needle(0)['lvl'] < 255 and mid != base and mid != lit_px, f'the hold is over: the lamp fades, not out and not lit (level {m.needle(0)["lvl"]}, centre {mid[:3]} between {base[:3]} and {lit_px[:3]})')
    m.tick(O['VU_GLOW_MS'])
    off = m.frame().getpixel((lamp0[0] + 16, lamp0[1] + 16))
    expect(m.needle(0)['lvl'] == 0 and off == base, 'and the lamp\'s rectangle is restored from vu_base when the fade is over')
    # a new peak while lit holds it longer
    m.signal(0.1, 0.1, 0.95); m.tick(10)
    m.signal(0.1, 0.1, 0.2)
    for _ in range(3): m.tick(100)
    m.signal(0.1, 0.1, 0.95); m.tick(100)
    m.signal(0.1, 0.1, 0.2)
    for _ in range(3): m.tick(100)
    expect(m.needle(0)['lit'], 'a peak while lit starts the hold again (the lamp is still on 300 ms after the second peak)')
    m.tick(100); m.tick(100)
    expect(not m.needle(0)['lit'], 'and ends after it')
    # the afterglow: linear in alpha over VU_GLOW_MS, drawn only when the level changes, a new peak relights at once
    GL = O['VU_GLOW_MS']
    expect(O['VU_HOLD_MS'] == 400 and GL == 180 and O['VU_TICK_MS'] == 33, 'VU_HOLD_MS 400, VU_GLOW_MS 180, VU_TICK_MS 33')
    m = opened(pin=-20.0); m.signal(0.1, 0.1, 0.95, 0.2); m.tick(10)
    m.signal(0.1, 0.1, 0.2, 0.2); m.tick(390)
    expect(m.needle(0)['lvl'] == 255 and m.needle(0)['lit'], 'lit until the hold ends')
    m.tick(20)
    n = m.needle(0)
    expect(not n['lit'] and n['lvl'] == 255 * (GL - 10) // GL and n['lvl_drawn'] == n['lvl'], f'10 ms into the fade (the tick after the hold): level {n["lvl"]}, drawn')
    m.tick(80)
    n = m.needle(0)
    expect(n['lvl'] == 255 * (GL - 90) // GL, f'90 ms into the fade: half the alpha ({n["lvl"]})')
    lamp_r = (lamp0[0], lamp0[1], 33, 31)
    m.tick(0)
    expect(m.rects == [], 'a look in which the level does not change draws nothing')
    m.signal(0.1, 0.1, 0.95, 0.2); m.tick(5)
    n = m.needle(0)
    expect(n['lit'] and n['lvl'] == 255 and n['lvl_drawn'] == 255 and any(q[0] <= lamp_r[0] and q[1] <= lamp_r[1] and q[0] + q[2] >= lamp_r[0] + 33 and q[1] + q[3] >= lamp_r[1] + 31 for q in m.rects), 'a peak during the fade relights fully at once')
    m.signal(0.1, 0.1, 0.2, 0.2); m.tick(O['VU_HOLD_MS'])
    levels = []
    for _ in range(8): m.tick(30); levels.append(m.needle(0)['lvl'])
    expect(levels == sorted(levels, reverse=True) and levels[-1] == 0 and len(set(levels)) > 4, f'the fade steps down to 0 ({levels})')
    n = m.needle(0)
    expect(ImageChops.difference(m.frame().convert('RGB'), opened(pin=-20.0).frame().convert('RGB')).crop((lamp0[0], lamp0[1], lamp0[0] + 33, lamp0[1] + 31)).getbbox() is None,
           'at the end of the fade the lamp rectangle is vu_base exactly')

    # the frame with the lamp on is the reference's, and off again the base's
    m = opened(pin=-20.0); m.signal(0.1, 0.1, 0.95, 0.2); settle(m, 150, 10)
    got = m.frame(); ref = reference([vu_of(0.1, -20.0)] * 2, (True, False))
    top, big = compare(got, ref, A.LAMP_RECT)
    expect(top <= TOL_MAX and big <= TOL_MANY, f'the lit left lamp: the reference\'s pixels (largest difference {top}, {big} channels over 2)')
    r1 = A.LAMP_AT[1]
    top, big = compare(got, ref, (r1[0], r1[1], r1[0] + 33, r1[1] + 31))
    expect(top <= TOL_MAX, f'the right lamp, off, is the reference\'s ({top})')
    # the rule follows the reference: -24 (the floor of ref) lights from -16 dBFS, -14 from -6 dBFS, -6 (the ceiling) only at digital full scale
    for ref_db, pk, want in ((-24.0, 10 ** (-16 / 20) + 0.002, True), (-24.0, 10 ** (-16 / 20) - 0.002, False), (-6.0, 0.95, False), (-6.0, 0.9, False), (-6.0, FS - 0.001, False), (-6.0, FS, True),
                             (-14.0, 0.45, False), (-14.0, 0.55, True), (-16.0, lamp_at(-16.0) + 0.002, True), (-16.0, lamp_at(-16.0) - 0.002, False)):
        m = opened(pin=ref_db); m.signal(0.05, 0.05, min(pk, 1.0)); m.tick(10); m.tick(10)
        expect(bool(m.needle(0)['lit']) == want, f'ref {ref_db:g}: a peak of {20 * math.log10(pk):.2f} dBFS {"lights" if want else "leaves off"} the lamp (ref + 8 dB = {ref_db + 8:g} dBFS, always from -0.1 dBFS)')
    expect(lamp_at(-6.0) > 1.0, 'with ref at its -6 ceiling the relative rule is +2 dBFS, unreachable: only the full-scale rule lights the lamp')


def pixel_tests(ctx):
    """The C needle, shadow, lamp and hood against the reference renderer (tools/vu_art.py compose), pixel for pixel within a tolerance; and the dirty rectangles."""
    expect = ctx.expect
    results = []
    for left, right, pk in ((0.1995, 0.0200, (0.5, 0.5)), (0.2818, 0.5, (0.99, 0.99)), (0.0, 0.0707, (0.2, 0.2)), (0.04, 0.2, (0.3, 0.3))):
        m = opened(); m.signal(left, right, *pk); settle(m, 150, 10)
        n = [m.needle(0), m.needle(1)]
        # (the needle is drawn at the angle the model has reached, which is the target once settled)
        vu = [vu_of(v) if v > 0 else -200 for v in (left, right)]
        peak = tuple(p >= FS or p >= lamp_at(-14.0) for p in pk)   # (ref pinned at -14: lit from -6 dBFS, 0.501, or at full scale)
        ref = reference(vu, peak)
        top, big = compare(m.frame(), ref)
        results.append((top, big))
        expect(n[0]['lit'] == int(peak[0]) and top <= TOL_MAX and big <= TOL_MANY, f'rms {left} / {right}: the page against vu_art.compose: largest channel difference {top}, {big} channels over 2 (tolerance {TOL_MAX} / {TOL_MANY})')
    print('  vu frame against the reference renderer (largest channel difference, channels over 2):', results)
    # the rest and the first look
    m = opened(status=3)
    top, big = compare(m.frame(), reference([None, None], (False, False), playing=False))
    expect(top <= TOL_MAX and big <= TOL_MANY, f'paused, parked: the reference\'s frame ({top}, {big})')
    # incremental drawing equals drawing from scratch: after a long walk of the needles and the lamps the frame is exactly the fresh one
    a = opened(); b = opened()
    seq = [(0.05, 0.2), (0.28, 0.01), (0.15, 0.15), (0.4, 0.3), (0.02, 0.08), (0.1995, 0.1995)]
    for left, right in seq:
        a.signal(left, right, 0.99 if left > 0.25 else 0.2, 0.99 if right > 0.25 else 0.2)
        for _ in range(12): a.tick(20)
    a.signal(0.1995, 0.1995, 0.2, 0.2)
    for _ in range(120): a.tick(20)
    b.signal(0.1995, 0.1995, 0.2, 0.2)
    for _ in range(60): b.tick(20)
    same = ImageChops.difference(a.frame().convert('RGB'), b.frame().convert('RGB')).getbbox()
    expect(same is None and a.needle(0)['drawn'] and not a.needle(0)['lit'], f'after a long walk (needles, lamps on and off) the frame is exactly the frame drawn from scratch ({same})')
    # confinement: a tick changes pixels only inside what it invalidates, and the rectangles are the old and new needle's (vu_art.move_rect)
    m = opened(); m.signal(0.05, 0.05); settle(m, 150, 10)
    ok, rects_ok, n_rect = True, True, 0
    for level in (0.12, 0.2, 0.08, 0.25):
        m.signal(level, level * 0.7)
        for _ in range(14):
            before = m.frame(); old = [m.needle(0), m.needle(1)]
            m.tick(20)
            after = m.frame(); new = [m.needle(0), m.needle(1)]
            dimg = ImageChops.difference(before.convert('RGB'), after.convert('RGB'))
            rs = m.rects
            for r in rs: ImageDraw.Draw(dimg).rectangle((r[0], r[1], r[0] + r[2] - 1, r[1] + r[3] - 1), fill=(0, 0, 0))
            diff = dimg.getbbox()   # what changed outside every invalidated rectangle
            n_rect += len(rs)
            want = []
            for i in (0, 1):
                if old[i]['drawn'] and new[i]['ad'] != old[i]['ad']:
                    r = A.move_rect(i, old[i]['ad'], new[i]['ad']); want.append((r[0], r[1], r[2] - r[0], r[3] - r[1]))
            rects_ok = rects_ok and sorted(rs) == sorted(want)
            ok = ok and diff is None
    expect(ok and n_rect > 20, f'a moving tick changes pixels only inside the invalidated rectangles ({n_rect} rectangles)')
    expect(rects_ok, 'and each rectangle is vu_art.move_rect of the needle\'s old and new angle (one per meter that moved, never the union of both)')
    wins = A.WINDOWS
    inside = all(any(w[0] <= r[0] and w[1] <= r[1] and r[0] + r[2] <= w[2] and r[1] + r[3] <= w[3] for w in wins) for r in m.rects)
    expect(inside, 'the rectangles lie inside a dial\'s window')
    n = m.needle(0)
    expect(n['r'] == tuple(A.needle_rect(0, n['ad'])), f'the rectangle the page keeps for a needle is vu_art.needle_rect ({n["r"]})')
    m3 = opened()
    expect(m3.needle(0)['r'] == tuple(A.needle_rect(0, A.REST)) and m3.needle(1)['r'] == tuple(A.needle_rect(1, A.REST)), 'the first look: the needles at the rest, their rectangles vu_art.needle_rect')
    # a change below what shows is not drawn
    m = opened(); m.signal(0.1995); settle(m, 150, 10)
    m.signal(0.1995 + 0.00004); m.tick(10); m.tick(10)
    expect(m.rects == [] and 0 < abs(m.needle(0)['x'] - m.needle(0)['ad']) < 0.0008, 'an angle that changes by less than 0.05 degrees is not redrawn while it moves')
    n = 0
    for _ in range(100): m.tick(10); n += len(m.rects)
    expect(n == 2 and m.needle(0)['x'] == m.needle(0)['ad'], f'each meter\'s needle is drawn once, where it comes to rest ({n} rectangles for two meters)')
    m.signal(0.1995 + 0.01); m.tick(50)
    expect(len(m.rects) >= 1, 'a visible one is')
    # steady state: nothing is drawn or invalidated
    m = opened(); m.signal(0.1995, 0.1995, 0.2, 0.2); settle(m, 150, 10); m.tick(50); m.tick(50)
    expect(m.rects == [], 'a steady signal: nothing invalidated')


def motion_tests(ctx):
    """Per-tick instruction costs against the Vinyl page's yardstick (its playing tick 2.3 M, a swing 4.5 M; the tick is 50 ms)."""
    expect = ctx.expect
    m = opened(); m.count()
    m.signal(0.02, 0.02, 0.1, 0.1); settle(m, 40, 10)
    worst, costs = 0, []
    # both needles sweeping, a lamp changing in the same tick
    for i, (lv, pk) in enumerate(((0.28, 0.99), (0.01, 0.1), (0.28, 0.99), (0.005, 0.1), (0.2, 0.1), (0.03, 0.1))):
        m.signal(lv, lv, pk, pk)
        for _ in range(8):
            m.tick(O['VU_TICK_MS']); costs.append((m.icount, len(m.rects), (m.needle(0)['lit'], m.needle(1)['lit'])))
    worst = max(c[0] for c in costs)
    both = [c for c in costs if c[1] == 2]
    lampchg = [costs[i][0] for i in range(1, len(costs)) if costs[i][2] != costs[i - 1][2] and costs[i][1] == 2]
    print(f'  vu tick cost (instructions): worst {worst}, both needles moving {max(c[0] for c in both)} (typical {sorted(c[0] for c in both)[len(both) // 2]}), with a lamp change {max(lampchg) if lampchg else None}')
    expect(both and worst < TICK_MAX, f'a tick with both needles moving (and a lamp changing: {len(lampchg)} such ticks) costs under the Vinyl playing-tick budget, {TICK_MAX}: worst {worst}')
    # a steady tick (the record read, the model, no drawing)
    m.signal(0.1995); settle(m, 150, 10); m.tick(50); steady = m.icount
    expect(steady < 20000 and m.rects == [], f'a tick with nothing to draw: {steady} instructions (under 20 k)')
    # the tick the page asks for: 33 ms while a needle or lamp moves or the player plays, VN_IDLE_MS at rest
    m = opened(status=3, kick=True); mods = []
    expect(('timer_add', PSYMS['vp_tick'], O['VU_TICK_MS']) in m.calls_all and O['VU_TICK_MS'] == 33, 'a kicked needle asks for the 33 ms tick')
    for _ in range(80): m.tick(10); mods += [c for c in m.calls if c[0] == 'timer_modify']
    expect(mods == [('timer_modify', 0x777, O['VN_IDLE_MS'])] and O['VN_IDLE_MS'] == 500, f'at rest again it slows to VN_IDLE_MS ({mods})')
    m = opened(); m.signal(0.1); m.tick(33); m.tick(33)
    m.signal(None); m.vufile = bytearray(MAGIC); m.status = 3; mods = []
    for _ in range(40): m.tick(33); mods += [c[2] for c in m.calls if c[0] == 'timer_modify']
    expect(mods == [O['VN_IDLE_MS']], f'a needle that returns to the rest and a lamp that is out: one change, to the idle interval ({mods})')
    # the full sweep: rest to +3 VU in one 100 ms tick, the biggest rectangle
    m = opened(); m.count(); m.signal(0.2818); m.tick(100); sweep = m.icount
    expect(sweep < TICK_MAX, f'the first tick of a step to +3 VU: {sweep}')
    # the first look, the widest draw (hoods, lamps and needles composed)
    m = machine(); m.count(); assert m.open() == 0; m.timers = []; m.first()
    print(f'  vu: a tick with nothing to draw {steady}, the first tick of a step to +3 VU {sweep}, the first full draw {m.icount}')
    expect(m.icount < 2000000, f'the first full draw (hoods, lamps and both needles composed): {m.icount} instructions')


def touch_tests(ctx):
    expect = ctx.expect
    m = opened(status=3)
    names = lambda c: [x[0] for x in c]
    calls = m.gesture((16, 12), (18, 14))
    expect('navigator_back' in names(calls) and not m.cmds, 'a tap on the chevron closes the page')
    m.cmds = []; calls = m.gesture((16, 12), (160, 300))
    expect('navigator_back' not in names(calls) and not m.cmds, 'began on the chevron, lifted elsewhere: nothing')
    m.ptr('down', 246, 449, 3000)
    ref = asset_image('vu_keys')
    held = m.frame().crop((223, 420, 269, 478)).convert('RGB')
    cell = ref.crop((A.KEY_CELLS[('play', 2)], 0, A.KEY_CELLS[('play', 2)] + 46, 58)).convert('RGB')
    expect(held.tobytes() == cell.tobytes() and m.rects == [(223, 420, 46, 58)], f'the play key held: drawn pressed from vu_keys, only its cell invalidated ({m.rects})')
    m.cmds = []; m.ptr('up', 248, 452, 3080)
    expect(m.cmds == [('playpause',)] and m.status == 2, 'released on it: play / pause (stock playpause_quick_click)')
    expect(m.frame().crop((223, 420, 269, 478)).convert('RGB').tobytes() == ref.crop((A.KEY_CELLS[('play', 1)], 0, A.KEY_CELLS[('play', 1)] + 46, 58)).convert('RGB').tobytes(), 'and the play key shows the pause glyph while it plays')
    for k, pt, cmd in ((K_PREV, (200, 449), 'prev'), (K_NEXT, (292, 449), 'next')):
        m.cmds = []
        m.ptr('down', *pt, 5000); held = m.frame().tobytes()
        m.ptr('up', pt[0] + 2, pt[1], 5060)
        expect(m.cmds == [(cmd, 5000 + 60, 0)], f'{cmd}: released on the key, {cmd}_quick_click(e, 0) with the click\'s own event')
        expect(held != m.frame().tobytes(), f'{cmd}: drawn pressed while held and back on release')
    m.cmds = []; calls = m.gesture((200, 449), (292, 449))
    expect(not m.cmds, 'a drag from one key to another does nothing')
    m.cmds = []; m.gesture((160, 240), (162, 238))
    expect(m.cmds == [('playpause',)], 'a tap on the dials plays / pauses')
    m.cmds = []; m.gesture((160, 366), (160, 368))
    expect(m.cmds == [('playpause',)], 'a tap on the text plays / pauses too (the labels are insensitive)')
    m.cmds = []; m.gesture((96, 196), (200, 196))
    expect(not m.cmds, 'a drag across the page does nothing')
    m.cmds = []; m.gesture((10, 460), (11, 460))
    expect(not m.cmds, 'a tap in the band beside the keys does nothing')
    m.cmds = []; m.ptr('down', 246, 449, 9000); m.ptr('abort', 246, 449, 9010); m.ptr('up', 246, 449, 9020)
    expect(not m.cmds, 'an abort lets the key go; the up after it does nothing')
    expect((m.view, EVT_MOVE) not in m.bound and 'widget_grab' not in names(m.calls), 'no move handler, no grab')
    rets = [m.ptr(k, 150, y, 10000 + y) for k, y in (('down', 40), ('move', 80), ('move', 160), ('up', 160), ('abort', 160))]
    expect(set(rets) == {0}, f'a drag from the top edge (the pull-down) is passed on: every call returns RET_OK ({rets})')
    m2 = machine(); e = m2.alloc(0x30); m2.u.mem_write(e, bytes(0x30)); m2.setword(e, EVT_DOWN)
    m2.call(PSYMS['vp_on_touch'], a0=0, a1=e, count=100000)
    expect(not m2.cmds and 'navigator_back' not in m2.names(), 'no page: a touch handler left behind does nothing')
    # the idle-opened page: a tap on the page closes it
    def auto():
        q = machine(status=3); assert q.open_idle() == 0
        q.timers = []; q.first()
        return q
    q = auto(); q.cmds = []; calls = q.gesture((160, 240), (162, 240))
    expect(q.cmds == [] and names(calls).count('navigator_back') == 1, 'idle-opened: a tap on the page closes it, plays / pauses nothing')
    q = auto(); calls = q.gesture((16, 12), (18, 14))
    expect('navigator_back' in names(calls) and not q.cmds, 'idle-opened: the chevron still closes')
    q.ptr('down', 246, 449, 3000); q.cmds = []; q.ptr('up', 248, 452, 3080)
    expect(q.cmds == [('playpause',)] and 'navigator_back' not in names(q.calls), 'idle-opened: the play key still plays / pauses')
    q.cmds = []; calls = q.gesture((160, 240), (260, 240))
    expect(not q.cmds and 'navigator_back' not in names(calls), 'idle-opened: a drag does nothing')
    q = machine(status=3); q.open(); q.timers = []; q.first()
    expect(q.open_idle() == 0, 'the timer on a page that is already up: 0, left alone')
    q.cmds = []; calls = q.gesture((160, 240), (162, 240))
    expect(q.cmds == [('playpause',)] and 'navigator_back' not in names(calls), 'and its tap still plays / pauses')
    q = auto(); fn, cx = q.bound[(WIN, EVT_DESTROY)]; q.call(fn, a0=cx, a1=0, count=3000000)
    q.windows = {}; q.bound = {}
    assert q.open() == 0; q.timers = []; q.first()
    q.cmds = []; calls = q.gesture((160, 240), (162, 240))
    expect(q.cmds == [('playpause',)] and 'navigator_back' not in names(calls), 'after the idle-opened page was destroyed a normal one plays / pauses on the tap')


def text_tests(ctx):
    expect = ctx.expect
    m = opened(title='So What', artist='Miles Davis', pos=14, length=562)
    expect(m.text_of('vu_title') == 'So What' and m.text_of('vu_artist') == 'Miles Davis' and m.text_of('vu_times') == '0:14  -9:08', 'the title, the artist, the times (no twin label)')
    import time as _t
    tm = _t.gmtime(m.wall + m.tz); clock = f'{tm.tm_hour:02d}:{tm.tm_min:02d}'
    expect(m.text_of('vu_status') == f'VOL 42 | FLAC | {clock}', f'the status line ({m.text_of("vu_status")})')
    m.pt = (15, 562); m.volume = '55'
    m.tick(500); m.calls_all = m.calls
    expect(m.text_of('vu_times') == '0:15  -9:07' and m.text_of('vu_status') == f'VOL 55 | FLAC | {clock}' and m.text_of('vu_title') is None, 'a second on: the times and the status line, the title not set again')
    m.tick(500); m.calls_all = m.calls
    expect(all(m.text_of(n) is None for n in LABELS), 'nothing changed: no label is set')
    m.play([m.record(title='', name='track 07.mp3', path='/mnt/mmc/x/track 07.mp3', artist='')], 0); m.tick(500); m.calls_all = m.calls
    expect(m.text_of('vu_title') == 'track 07.mp3' and m.text_of('vu_artist') == '', 'a track without a title: its file name (track change handled)')
    m = opened(playing=False, status=3)
    expect(m.text_of('vu_title') == 'Not Playing', 'nothing playing: "Not Playing"')
    # the title's face (patch/lyrics.c ly_title_face): drawn once, in the lyrics face when every code point is in lyrics.ttf, else in the default font; the face is loaded with its gamma
    FM, STB, TG = 0x24000000, O['STB_GET_GLYPH'], PSYMS['tg_get_glyph']

    def face(m): return tuple(m.props.get((m.widgets['vu_title'], f'style:{s}:font_name')) for s in ('normal', 'disable', 'focused'))

    def asked(m): return ('font_manager_get_font', FM, 'lyrics', 0) in m.calls

    def play(m, title):
        m.play([m.record(title=title, artist='X')], 0); m.tick(500); m.calls_all = m.calls
    m = opened(title='So What', artist='Miles Davis')
    expect(face(m) == ('lyrics',) * 3, 'a Latin title: the lyrics face in all three states')
    f = m.malloc(0xd4); m.u.mem_write(f, bytes(0xd4)); m.setword(f + O['FONT_MATCH'], O['STB_MATCH']); m.setword(f + O['FONT_GET_GLYPH'], STB); m.u.mem_write(f + O['FONT_MONO'], bytes([0])); m.fm, m.font = FM, f
    play(m, 'Kind of Blue')
    expect(face(m) == ('lyrics',) * 3 and asked(m) and m.word(f + O['FONT_GET_GLYPH']) == TG, 'a Latin title asks for the lyrics font and installs the coverage gamma on it, without Now Playing\'s lyrics code having run')
    play(m, 'Привет мир Ελληνικά')
    expect(face(m) == ('lyrics',) * 3, 'Cyrillic and Greek are in the face too')
    play(m, '夜に駆ける')
    expect(face(m) == ('default',) * 3 and m.text_of('vu_title') == '夜に駆ける'.encode().decode('latin-1') and not asked(m), 'a CJK title: the default font, drawn once, the lyrics face not asked for')
    play(m, 'Hello 世界')
    expect(face(m) == ('default',) * 3, 'a mixed title: the default font (AWTK takes a glyph from one font only)')
    play(m, 'Back In Black')
    expect(face(m) == ('lyrics',) * 3, 'a track change back to a Latin title switches the style back')
    play(m, 'Back In Black')
    expect(face(m) == ('lyrics',) * 3 and m.text_of('vu_title') is None, 'the same track again: nothing is set')
    m = opened(playing=False, status=3)
    expect(face(m) == ('lyrics',) * 3, 'nothing playing: "Not Playing" in the lyrics face')
    m = opened(title='So What'); m.fm, m.font = FM, 0
    play(m, 'Kind of Blue')
    expect(face(m) == ('lyrics',) * 3 and m.text_of('vu_title') == 'Kind of Blue', 'a lyrics font that cannot be loaded (none returned): the label still names it and the page works (the stock fallback draws the default font)')
    # the idle-opened page: the same face and the gamma on its first look, with no Now Playing lyrics code run before
    m = machine(status=3, title='Midnight City'); m.fm = FM; m.font = f2 = m.malloc(0xd4)
    m.u.mem_write(f2, bytes(0xd4)); m.setword(f2 + O['FONT_MATCH'], O['STB_MATCH']); m.setword(f2 + O['FONT_GET_GLYPH'], STB); m.u.mem_write(f2 + O['FONT_MONO'], bytes([0]))
    expect(m.open_idle() == 0, 'opened by the idle timer')
    m.timers = []; m.first()
    expect(face(m) == ('lyrics',) * 3 and m.word(f2 + O['FONT_GET_GLYPH']) == TG, 'the idle-opened page: its first look sets the face and installs the gamma on the lyrics font')
    from stb_raster import StbFont
    font = StbFont(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/default.ttf'))
    wide = 'VOL 100 | WAVE | 23:59'
    expect(font.width(wide, A.TEXT['status']['px']) <= A.TEXT['status']['w'], f'"{wide}" fits the {A.TEXT["status"]["w"]} px status label')
    bold = StbFont(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/fonts/lyrics.ttf'))
    sample = 'The quick brown fox jumps over the lazy dog, ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789'
    wb, wr = bold.width(sample, A.TEXT['title']['px']), font.width(sample, A.TEXT['title']['px'])
    expect(wb <= wr, f'the bold face is no wider than the default font (measured 0.94 - 0.98 of its width): {wb} px against {wr} px for an 80-character line at 22 px ({wb / wr:.3f}); the label clips by its own ellipsis at {A.TEXT["title"]["w"]} px, so the width rule holds')


def life_tests(ctx):
    expect = ctx.expect
    m = opened(); m.signal(0.1995)
    m.calls = []; m.call(PSYMS['vp_first'], a0=0, count=400000000)
    expect(('timer_add', PSYMS['vp_tick'], O['VU_TICK_MS']) in m.calls, 'playing: the tick at VU_TICK_MS (33 ms)')
    m.status = 3; m.signal(None)
    for _ in range(80): m.tick(50)
    m.tick(50)
    expect('timer_add' not in m.names(), 'no second timer')
    m.tick(500)
    expect(m.names().count('timer_modify') == 0 and not m.rects, 'paused and parked: 500 ms, nothing drawn')
    m2 = opened(status=3)
    m2.tick(500); seen = [c for c in m2.calls if c[0] == 'timer_modify']
    m2.status = 2; m2.signal(0.1); m2.tick(500); seen += [c for c in m2.calls if c[0] == 'timer_modify']
    expect(('timer_modify', 0x777, O['VU_TICK_MS']) in seen, f'playing again: back to 33 ms in place ({seen})')
    m2.screen(False); m2.tick(50)
    expect(('timer_modify', 0x777, 1000) in m2.calls and not m2.rects and not any(c[0] in ('get_playtimeandlength', 'mclGetPlayStatus', 'widget_set_text_utf8') for c in m2.calls), 'screen off: 1 s, nothing read, drawn or set')
    reads = len([c for c in m2.log if c[0] == 'fopen'])
    m2.tick(1000)
    expect('timer_modify' not in m2.names() and not m2.rects and len([c for c in m2.log if c[0] == 'fopen']) == reads, 'dark: the interval is not set again, the record is not read')
    m2.screen(True); m2.tick(1000)
    expect(('timer_modify', 0x777, O['VU_TICK_MS']) in m2.calls, 'lit again: the interval returns')
    m2.calls = []; m2.fire(EVT_BG, WIN)
    expect(('timer_remove', 0x777) in m2.calls, 'to the background: the timer goes')
    m2.calls = []; m2.call(PSYMS['vp_tick'], a0=0, count=100000)
    expect(not any(c[0] in ('widget_invalidate_force', 'timer_modify') for c in m2.calls), 'a stray tick in the background draws nothing')
    m2.screen(False); m2.calls = []; m2.fire(EVT_FG, WIN); m2.first()
    expect(('timer_add', PSYMS['vp_first'], 1000) in m2.calls and not m2.rects, 'the first look with the screen off waits for the light')
    m2.screen(True)
    fn, cx = m2.bound[(WIN, EVT_DESTROY)]
    m2.calls = []; m2.call(fn, a0=cx, a1=0)
    expect(m2.vufile is None and len(m2.bitmaps) == 0, 'destroy: the mark unlinked, every bitmap freed')
    m2.timers = []
    expect(m2.open() == 0 and m2.vufile == bytearray(MAGIC), 'it opens again with a clean state')
    expect(not any('click' in n.lower() and n not in ('playpause_quick_click', 'next_quick_click', 'prev_quick_click') for n in m2.names()), 'no click sound')
    m3 = opened(); m3.fs['/mnt/data/m1plus/scrobbling'] = b'1\n'
    m3.screen(False); m3.calls = []; m3.tick(1000)
    expect(('open', '/mnt/data/m1plus/scrobbling', 0) in m3.calls and not m3.rects, 'screen off: the tick still polls scrobbling and draws nothing')
    # the mark exists only while the page is open and the screen is lit
    m = opened()
    expect(m.vufile is not None, 'open and lit: the mark exists')
    m.screen(False); m.tick(1000)
    expect(m.vufile is None, 'a dark tick: the mark is gone (the player stops measuring)')
    m.tick(1000)
    expect(m.vufile is None, 'dark again: still none')
    m.screen(True); m.tick(1000)
    expect(m.vufile is not None and bytes(m.vufile[:8]) == bytes(MAGIC), 'the first lit tick: the mark is back')
    m.screen(False); m.tick(1000); m.mark_fail = True; m.screen(True); m.calls = []; m.tick(1000)
    expect(m.vufile is None and ('fopen', VU, 'wb') in m.calls, 'a mark that cannot be made: none')
    m.mark_fail = False; m.tick(1000)
    expect(m.vufile is not None and bytes(m.vufile[:8]) == bytes(MAGIC), 'the next lit tick tries again: the mark is there')
    fn, cx = m.bound[(WIN, EVT_BG)]
    m.call(fn, a0=cx, a1=0)
    expect(m.vufile is None, 'covered by another window (the lock screen as the screen goes dark): the mark is gone')
    m.screen(False)
    fn, cx = m.bound[(WIN, EVT_FG)]
    m.call(fn, a0=cx, a1=0)
    expect(m.vufile is None, 'back in front in the dark: still none')
    m.call(m.bound[(WIN, EVT_BG)][0], a0=cx, a1=0); m.screen(True); m.call(fn, a0=cx, a1=0)
    expect(m.vufile is not None and bytes(m.vufile[:8]) == bytes(MAGIC), 'back in front and lit: the mark is back')
    fn, cx = m.bound[(WIN, EVT_DESTROY)]
    m.call(fn, a0=cx, a1=0)
    expect(m.vufile is None, 'destroy: the mark is gone')
    m = machine(); m.screen(False)
    expect(m.open() == 0 and m.vufile is None, 'opened with the screen off: no mark')
    m.first()
    expect(m.vufile is None, 'the first look in the dark: still none')
    m.screen(True); m.first()
    expect(m.vufile is not None, 'the first look once lit: the mark')
    # the paint blits the frame 1:1
    m = opened()
    expect(m.paint() != [], 'the paint blits the frame')


def auto_tests(ctx):
    """The automatic reference level (patch/vupage.c vp_level, docs/modules/vu.md "Automatic level"): ref = the long-term level of the louder channel + 3 dB, common to both channels, kept over
    tracks, reset on page open; every other test pins the reference (VUM.pin) instead."""
    expect = ctx.expect
    dbfs = lambda db: 10 ** (db / 20)

    def fresh(**k): return opened(pin=None, **k)

    def run(m, secs, ms=100, probe=None):
        """Ticks of ms for secs seconds (100 ms is the page's own cap); the probe's results (called after each tick), with the time."""
        out = []
        for i in range(int(round(secs * 1000 / ms))):
            m.tick(ms)
            if probe: out.append(((i + 1) * ms / 1000, probe(m)))
        return out

    def first(series, ok):
        """The time of the first sample where ok holds, or None."""
        return next((t for t, v in series if ok(v)), None)
    # the start value, and the constants the doc names
    m = fresh()
    expect(abs(m.ref() - REF0) < 1e-9 and m.lv()[1:] == (0, 0), f'page open: ref {m.ref():.3f} dBFS (the start value {REF0:g}), no peg time, no quick rise')
    expect(PSYMS['vp_lv.1'] == PSYMS['vp_lv.0'] + 8 and PSYMS['vp_lv.2'] == PSYMS['vp_lv.0'] + 12, 'the state (lt, peg, fast) is contiguous (the test reads it as one struct)')
    # a loud master, -8 dBFS rms: pegged at first (reading +4 VU), then it settles; the ceiling of ref (-6) leaves it at -2 VU
    m = fresh(); m.signal(dbfs(-8)); m.tick(100)
    expect(m.reading(0) > 3.2 and m.reading(1) > 3.2, f'-8 dBFS rms against ref {REF0:g}: both needles are pegged at first (target {m.reading(0):.2f} VU: past +3, stopped 3 % past the end)')
    res = run(m, 40, probe=lambda m: (m.reading(0), m.ref(), m.lv()[2]))
    t_unpeg = first(res, lambda v: v[0] < 3.0)
    final = res[-1][1]
    expect(t_unpeg is not None and t_unpeg <= 2.0, f'-8 dBFS rms: the needle stops pegging after {t_unpeg:.1f} s (a couple of seconds at most)')
    expect(abs(final[1] - REF_MAX) < 1e-6 and -2.3 < final[0] < -1.7, f'-8 dBFS rms for 40 s: ref reaches its ceiling {final[1]:.3f} dBFS, the needle reads {final[0]:.2f} VU (-3 VU would need ref -5)')
    print(f'  vu auto level: -8 dBFS rms stops pegging at {t_unpeg:.1f} s; ref {first(res, lambda v: v[1] > REF_MAX - 1.0)} s to within 1 dB of -6')
    # louder still, -4 dBFS rms: pegged for 1 s, then the quick rise (2 s constant) ends it before the slow one would
    m = fresh(); m.signal(dbfs(-4))
    res = run(m, 6, probe=lambda m: (m.reading(0), m.ref(), m.lv()[2]))
    t4 = first(res, lambda v: v[0] < 3.0)
    print(f'  vu auto level: -4 dBFS rms stops pegging at {t4} s (quick rise)')
    expect(res[0][1][0] > 3.2 and t4 is not None and 1.0 <= t4 <= 2.0 and any(v[2] for _, v in res), f'-4 dBFS rms: pegged ({res[0][1][0]:.1f} VU) for {t4:.1f} s, the quick rise on (it takes the needle off the stop at once after the 1 s)')
    expect(res[-1][1][1] > REF_MAX - 0.5, f'and ref goes to the ceiling ({res[-1][1][1]:.2f})')
    # a master of -10 dBFS: ref goes to -7, the needle settles at -3 VU
    m = fresh(); m.signal(dbfs(-10))
    res = run(m, 60, probe=lambda m: (m.reading(0), m.ref()))
    t_in = first(res, lambda v: abs(v[0] + 3) < 1.0)
    expect(abs(res[-1][1][0] + 3) < 0.15 and abs(res[-1][1][1] + 7) < 0.15, f'-10 dBFS rms for 60 s: ref {res[-1][1][1]:.2f} dBFS (the programme + 3 dB), the needle at {res[-1][1][0]:.2f} VU (-3)')
    print(f'  vu auto level: -10 dBFS rms is within 1 dB of -3 VU at {t_in:.1f} s')
    # a quiet one, -20 dBFS rms: -8 VU at first, rises (ref falls to -17) over the long time constant
    m = fresh(); m.signal(dbfs(-20)); m.tick(100)
    start = m.reading(0)
    expect(abs(start + 8) < 0.3, f'-20 dBFS rms against ref {REF0:g}: it starts at {start:.2f} VU')
    res = run(m, 60, probe=lambda m: (m.reading(0), m.ref()))
    rising = all(res[i + 1][1][0] >= res[i][1][0] - 1e-6 for i in range(len(res) - 1))
    t_q = first(res, lambda v: v[0] > -4.0)
    expect(rising and abs(res[-1][1][0] + 3) < 0.25 and abs(res[-1][1][1] + 17) < 0.25, f'-20 dBFS rms: the needle rises steadily to {res[-1][1][0]:.2f} VU in 60 s (ref {res[-1][1][1]:.2f}, -17)')
    expect(t_q is not None and 15 < t_q < 40, f'and passes -4 VU at {t_q:.1f} s (the 12 s constant: 12 ln 5 = 19 s to 1 dB)')
    print(f'  vu auto level: -20 dBFS rms passes -4 VU at {t_q:.1f} s')
    # within a settled track a burst of +6 dB swings the needle by about 6 dB and it comes back; ref hardly moves
    m = fresh(); m.set_ref(-11.0); m.signal(dbfs(-14))
    run(m, 3)
    base, ref_a = m.reading(0, 'x'), m.ref()
    m.signal(dbfs(-8)); seen = []
    for _ in range(5): m.tick(100); seen.append(m.reading(0, 'x'))
    top = max(seen)
    m.signal(dbfs(-14)); run(m, 1.5)
    back, ref_b = m.reading(0, 'x'), m.ref()
    expect(abs(base + 3) < 0.4 and abs((top - base) - 6) < 1.0 and abs(back - base) < 0.6 and abs(ref_b - ref_a) < 0.8,
           f'a settled track (ref {ref_a:.2f}, {base:.2f} VU): a +6 dB burst of 0.5 s takes the needle to {top:.2f} VU (+{top - base:.2f}), back to {back:.2f} after it; ref {ref_b:.2f}')
    # silence and pauses do not move ref
    m = fresh(); m.set_ref(-15.0); lt0 = m.lv()
    m.signal(dbfs(-70)); run(m, 5)
    expect(m.lv() == lt0, 'a block below the floor (-70 dBFS rms): nothing moves')
    m.signal(None); run(m, 5)
    expect(m.lv() == lt0, 'no signal at all (the player writes nothing): nothing moves')
    m.signal(dbfs(-10)); m.status = 3; run(m, 5); m.status = 2
    expect(m.lv() == lt0, 'a paused player: nothing moves')
    m.signal(dbfs(-45)); run(m, 5)
    expect(m.lv()[0] < lt0[0], 'a quiet passage just above the floor (-45 dBFS rms) does count: lt falls')
    m = fresh(); m.signal(dbfs(-14)); run(m, 5); a = m.lv()[0]
    m.signal(None); run(m, 8); m.signal(dbfs(-14)); run(m, 0.1)
    expect(abs(m.ref() - 10 * math.log10(a) - 3) < 0.05, 'a pause of 8 s between two passages leaves ref where the first one put it (no drag towards zero)')
    # one reference for both channels: the L/R relation is kept, and lt follows the louder one
    m = fresh(); m.signal(0.1, 0.05); run(m, 10)
    f = [(m.needle(i)['tgt'] + A.SWEEP) / (2 * A.SWEEP) for i in (0, 1)]
    expect(abs(f[0] / f[1] - 2) < 1e-6, f'L at twice R (rms 0.1 / 0.05): the needles are in the ratio {f[0] / f[1]:.6f} (6.02 dB, one reference)')
    b = fresh(); b.signal(0.1, 0.1); run(b, 10)
    c = fresh(); c.signal(0.05, 0.1); run(c, 10)
    expect(m.lv() == b.lv() == c.lv(), 'lt follows the louder channel: the same ref for (0.1, 0.05), (0.1, 0.1) and (0.05, 0.1)')
    fc = [(c.needle(i)['tgt'] + A.SWEEP) / (2 * A.SWEEP) for i in (0, 1)]
    expect(abs(fc[1] / fc[0] - 2) < 1e-6, 'and right louder than left reads the other way round')
    # the clamps
    m = fresh(); m.set_ref(REF_MIN + 0.1); m.signal(dbfs(-40)); run(m, 20)
    expect(abs(m.ref() - REF_MIN) < 1e-6, f'quiet: ref stops at its floor {REF_MIN:g} dBFS ({m.ref():.4f})')
    m.signal(dbfs(-20)); r = run(m, 5, probe=lambda m: m.ref())
    expect(r[-1][1] > REF_MIN + 0.2, 'and it comes back up at once (the long-term level is clamped too: no wind-up)')
    m = fresh(); m.set_ref(REF_MAX - 0.1); m.signal(dbfs(-3)); run(m, 20)
    expect(abs(m.ref() - REF_MAX) < 1e-6, f'loud: ref stops at its ceiling {REF_MAX:g} dBFS ({m.ref():.4f})')
    m.signal(dbfs(-20)); r = run(m, 20, probe=lambda m: m.ref())
    expect(r[-1][1] < REF_MAX - 1.0, 'and a quiet passage after it brings ref down at the slow rate (no wind-up above the ceiling)')
    # kept over a track change, reset on page open
    m = fresh(); m.signal(dbfs(-10)); run(m, 10)
    r1 = m.ref()
    m.play([m.record(title='Next', artist='X')], 0); m.tick(100)
    expect(abs(m.ref() - r1) < 0.3 and abs(m.ref() - REF0) > 0.5, f'a track change keeps ref ({r1:.2f} before, {m.ref():.2f} after: the next track adapts from there)')
    fn, cx = m.bound[(WIN, EVT_DESTROY)]
    m.call(fn, a0=cx, a1=0); m.timers = []
    expect(m.open() == 0 and abs(m.ref() - REF0) < 1e-9 and m.lv()[1:] == (0, 0), f'closed and opened again: ref is the start value {REF0:g} again ({m.ref():.3f})')
    # the lamps follow the automatic level: a loud master with peaks at -0.9 dBFS (the old fixed rule lit them at once and for good) lights them only until ref has risen past -8.9 (ref + 8 dB above the peaks)
    m = fresh(); m.signal(dbfs(-8), dbfs(-8), 0.9)
    lit = run(m, 6, probe=lambda m: (m.needle(0)['lit'], m.needle(1)['lit']))
    on = [t for t, (a, b) in lit if a or b]
    expect(on and on[0] < 0.2 and on[-1] < 5.0, f'a loud master (-8 dBFS rms, peaks at -0.9 dBFS): the lamps light at the start and are out for good by {on[-1] if on else -1:.1f} s (ref + 8 dB has passed the peaks)')
    m = fresh(); m.signal(dbfs(-8), dbfs(-8), 0.995); m.tick(100)
    expect(m.needle(0)['lit'] and m.needle(1)['lit'], 'and a peak at -0.04 dBFS (digital full scale) lights them at any reference')


def preview_tests(ctx):
    """The emulated frames: out/preview/vu-emu-playing.png and vu-emu-paused.png, with the labels' text as the AWTK labels draw it."""
    expect = ctx.expect
    import time as _t
    m = opened(title='Midnight City', artist='M83', pos=79, length=243); m.signal(0.17, 0.12, 0.99, 0.4); settle(m, 150, 10)
    tm = _t.gmtime(m.wall + m.tz); clock = f'{tm.tm_hour:02d}:{tm.tm_min:02d}'
    f = dict(title='Midnight City', artist='M83', pos=79, len=243, fmt='FLAC', vol=42, clock=clock, playing=True, vu=[vu_of(0.17), vu_of(0.12)], peak=[True, False])
    dump(m, 'playing', f)
    p = opened(status=3, title='Midnight City', artist='M83', pos=79, length=243)
    dump(p, 'paused', dict(f, playing=False, vu=[None, None], peak=[False, False]))
    ok = os.path.getsize(os.path.join(OUT, 'vu-emu-playing.png')) > 20000 and os.path.getsize(os.path.join(OUT, 'vu-emu-paused.png')) > 20000
    expect(ok, 'out/preview/vu-emu-playing.png and vu-emu-paused.png written')


SECTIONS = [layout_tests, wanted_tests, float_tests, exact_tests, native_tests, none_tests, timing_tests, merge_tests, art_tests,
            page_tests, level_tests, step_tests, kick_tests, lamp_tests, pixel_tests, motion_tests, touch_tests, text_tests, life_tests, auto_tests, preview_tests]


