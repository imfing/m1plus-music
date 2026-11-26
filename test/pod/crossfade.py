"""Crossfade (patch/xfade.c, patch/xfadeset.c, docs/modules/crossfade.md): dual-decoder real-time track overlap
inside hciplayer (equal-power cos/sin curve, swr cross-rate conversion with its continuous handoff, the sticky output format, ReplayGain matching, float & native
PCM paths, VBR early/late EOF, backward-seek and closegapless aborts, DSD/MQA/kill-switch bypass) and demo's
persistent settings, smart cross-album logic, Gapless-off bridge, early preload and Playback Settings UI."""
import math, os, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3, UC_MIPS_REG_F0, UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_V0
import awtk_ui
import mod_player

PEQ = sibling('peq')
ST = sibling('stereo')

XFADE_FILE, XFADE_TMP = '/tmp/m1plus-xfade', '/tmp/m1plus-xfade.tmp'
XFOUT_FILE = '/tmp/m1plus-xfout'
SET_FILE, SET_TMP = '/mnt/data/m1plus/playback-crossfade', '/mnt/data/m1plus/playback-crossfade.tmp'
AUTO_FILE, AUTO_TMP = '/mnt/data/m1plus/playback-crossfade-auto', '/mnt/data/m1plus/playback-crossfade-auto.tmp'
KILL = '/mnt/mmc/m1plus-off'

# Pinned hciplayer addresses matching patch/xfade.c and tools/mod_player.py
MPCTX_PTR = 0xaf9e30
NEXT_MPCTX = 0xaf9b90
NEXT_STATE = 0xb10dd0
NEXT_FLAG = 0xb10de0
NEXT_CODEC_INITED = 0xb10d70
MQA_MODE = 0xb10c54
RG_MODE = 0xb10e30
RG_NEXT = 0xb0c790
INIT_BEST_ACODEC = 0x47eb50
UNINIT_NEXT = 0x42a9cc
DEMUX_LEN = 0x486914
# libswresample as hciplayer links it (patch/xfsrc.c): stubbed here by a Python model, the real code is not run under Unicorn.
SWR_ALLOC_SET_OPTS, SWR_INIT, SWR_CONVERT, SWR_FREE, AV_OPT_SET_INT = 0x7235bc, 0x41e32c, 0x724b40, 0x41e2d0, 0x6f9770
UNINIT_PLAYER, STOCK_AO_INIT, STOCK_AO_PLAY = 0x42def4, 0x438648, 0x43aae4
REINIT_CHAIN, STOCK_AO_PAUSE, STOCK_AO_RESUME, STOCK_AO_SPACE, USEC_SLEEP, AO_BUFFERSIZE = 0x42e680, 0x438224, 0x4384ac, 0x437e1c, 0x4a4730, 0xafa1b4
PLAYER_FLAGS, GAPLESS_SW, AO_RATE, AO_CH, AO_FMT = 0xb10e70, 0xb10e40, 0xafa1a0, 0xafa1a4, 0xafa1a8
RATE_SET = 0x40000100

FLOAT, S16, S24, S32, U8 = 0x1d, 0x09, 0x11, 0x19, 0x03


def xfrec(seconds=5, seq=1, magic=b'M1XFD01\0', keep=None):
    return magic + struct.pack('<iii', seconds, seq, (seconds > 0) if keep is None else keep)


def encode_pcm(samples, fmt):
    """Encode float samples in [-1, 1] into MPlayer format bytes (FLOAT / S16 / S24 / S32 / U8)."""
    if fmt == FLOAT: return struct.pack(f'<{len(samples)}f', *samples)
    if fmt == S16: return struct.pack(f'<{len(samples)}h', *(max(-32768, min(32767, int(round(v * 32768.0)))) for v in samples))
    if fmt == S32: return struct.pack(f'<{len(samples)}i', *(max(-2147483648, min(2147483647, int(round(v * 2147483648.0)))) for v in samples))
    if fmt == U8: return bytes(max(0, min(255, int(round(v * 128.0 + 128.0)))) for v in samples)
    if fmt == S24:
        out = bytearray()
        for v in samples:
            s = max(-8388608, min(8388607, int(round(v * 8388608.0))))
            out += bytes((s & 0xff, (s >> 8) & 0xff, (s >> 16) & 0xff))
        return bytes(out)
    raise ValueError(fmt)


def decode_pcm(raw, fmt):
    """Decode MPlayer format bytes to float samples."""
    if fmt == FLOAT: return list(struct.unpack(f'<{len(raw) // 4}f', raw))
    if fmt == S16: return [v / 32768.0 for v in struct.unpack(f'<{len(raw) // 2}h', raw)]
    if fmt == S32: return [v / 2147483648.0 for v in struct.unpack(f'<{len(raw) // 4}i', raw)]
    if fmt == U8: return [(b - 128) / 128.0 for b in raw]
    if fmt == S24:
        out = []
        for i in range(0, len(raw), 3):
            s = raw[i] | (raw[i + 1] << 8) | ((raw[i + 2] - 256 if raw[i + 2] >= 128 else raw[i + 2]) << 16)
            out.append(s / 8388608.0)
        return out
    raise ValueError(fmt)


def fmt_bps(fmt):
    return {FLOAT: 4, S16: 2, S24: 3, S32: 4, U8: 1}[fmt]


def soft_clip(x):
    if x > 0.95:
        d = x - 0.95
        return 0.95 + 0.05 * (d / (d + 0.05))
    if x < -0.95:
        d = -0.95 - x
        return -0.95 - 0.05 * (d / (d + 0.05))
    return x


class XP(ST.SP):
    """Patched hciplayer under Unicorn with Track A MPContext and Track B next_mpctx/ad_driver mocked."""

    def __init__(self, files=None):
        super().__init__(files)
        self.track_a_len = 60.0
        self.track_b_len = 60.0
        self.init_b_ok = 1
        self.init_b_calls = 0
        self.uninit_next_calls = 0
        self.b_stream = b''
        self.b_stream_pos = 0
        self.b_chunk_max = 4096
        self.b_decode_calls = 0
        self.b_dec_fn = self.TRAP + 0x400
        self.traps[self.b_dec_fn] = 'decode_b'
        self.swr, self.swr_log, self.uninit_masks, self.ao_plays = {}, [], [], []
        self.ao_events, self.ao_space = [], []   # the driver and player calls in order; get_space's answers, last one repeated
        self.ao_short = []   # play's next answers (bytes taken); then everything asked
        self.xfout_h, self.xfout_opens = 0, []
        for addr, cb in ((INIT_BEST_ACODEC, self._init_b), (UNINIT_NEXT, self._uninit_next),
                         (DEMUX_LEN, self._demux_len), (SWR_ALLOC_SET_OPTS, self._swr_alloc), (SWR_INIT, self._swr_init),
                         (SWR_CONVERT, self._swr_convert), (SWR_FREE, self._swr_free), (AV_OPT_SET_INT, self._swr_opt),
                         (UNINIT_PLAYER, self._uninit_player), (STOCK_AO_INIT, self._ao_init),
                         (STOCK_AO_PLAY, self._ao_play),
                         (REINIT_CHAIN, lambda *a: self._ao_event('reinit')), (STOCK_AO_PAUSE, lambda *a: self._ao_event('pause')),
                         (STOCK_AO_RESUME, lambda *a: self._ao_event('resume')), (USEC_SLEEP, lambda *a: self._ao_event('sleep')),
                         (STOCK_AO_SPACE, self._ao_get_space)):
            self.u.hook_add(UC_HOOK_CODE, cb, begin=addr, end=addr)
        # Clear hciplayer crossfade globals
        for a in (NEXT_STATE, NEXT_FLAG, NEXT_CODEC_INITED, MQA_MODE, RG_MODE):
            self.setword(a, 0)
        self.setword(NEXT_MPCTX + 0x28, 0)
        self.setword(NEXT_MPCTX + 0x2c, 0)
        self.u.mem_write(RG_NEXT, struct.pack('<iIiI', -0x80000000, 100000, -0x80000000, 100000))
        self.mp_a = self.malloc(0x80)
        self.demux_a = self.malloc(0x40)
        self.demux_b = 0
        self.ds_a = self.malloc(0x40)
        self.sh_a = self.malloc(0x100)
        self.setword(MPCTX_PTR, self.mp_a)
        self.setword(self.mp_a + 0x28, self.demux_a)
        self.setword(self.mp_a + 0x2c, self.sh_a)
        self.setword(self.mp_a + 0x34, self.ds_a)
        self.setword(self.mp_a + 0x14, 0)
        self.setword(self.ds_a + 0x1c, 0)
        self.u.mem_write(self.sh_a + 0x20, struct.pack('<d', 0.0))
        self.setword(self.sh_a + 0x4c, 48000 * 4)
        self.setword(self.sh_a + 0x6c, 0)
        self.setword(self.sh_a + 0xd0, 0)
        self.sh_b = 0

    def _trap(self, u, address, size, user):
        name = self.traps.get(address)
        if name == 'decode_b':
            return self._decode_b(u, address, size, user)
        # the output-rate record (XFOUT_FILE): "r+b" opens an existing one, "wb" makes it; the write is at its start
        a = [u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3)]
        if name == 'fopen' and self.read_cstr(a[0]).decode() == XFOUT_FILE:
            mode = self.read_cstr(a[1]).decode(); self.xfout_opens.append(mode)
            if 'w' in mode: self.files[XFOUT_FILE] = b''
            self.xfout_h = self.malloc(4) if XFOUT_FILE in self.files else 0
            return self._ret(self.xfout_h)
        if name == 'fwrite' and a[3] == self.xfout_h and self.xfout_h:
            data = bytes(u.mem_read(a[0], a[1] * a[2])); self.files[XFOUT_FILE] = data + self.files[XFOUT_FILE][len(data):]
            return self._ret(a[2])
        if name == 'fclose' and a[0] == self.xfout_h and self.xfout_h:
            self.xfout_h = 0
            return self._ret(0)
        return super()._trap(u, address, size, user)

    def set_track_a(self, pos=0.0, total=60.0, obps=192000, pts_bytes=0, abuf_len=0, drv='ffmpeg', name='ffflac'):
        self.track_a_len = total
        self.u.mem_write(self.sh_a + 0x20, struct.pack('<d', pos))
        self.setword(self.sh_a + 0x4c, obps)
        self.setword(self.sh_a + 0x6c, abuf_len)
        self.setword(self.sh_a + 0xd0, pts_bytes)
        self.setword(self.mp_a + 0x14, 0)
        self.setword(self.ds_a + 0x1c, 0)
        codec = self.malloc(0x400)
        self.setword(codec + 0x3d0, self.cstr(name))
        self.setword(codec + 0x3e0, self.cstr(drv))
        self.setword(self.sh_a + 4, codec)

    def setup_track_b(self, pcm_bytes, rate=48000, nch=2, fmt=S16, drv='ffmpeg', name='ffflac', buf_size=16384, pre_inited=0, total=60.0):
        bps = fmt_bps(fmt)
        self.demux_b = self.malloc(0x40)
        self.track_b_len = total
        self.sh_b = self.malloc(0x100)
        codec = self.malloc(0x400)
        self.setword(codec + 0x3d0, self.cstr(name))
        self.setword(codec + 0x3e0, self.cstr(drv))
        ad_drv = self.malloc(0x40)
        self.setword(ad_drv + 0x14, self.b_dec_fn)
        abuf = self.malloc(buf_size)
        self.setword(self.sh_b + 4, codec)
        self.setword(self.sh_b + 0x38, fmt)
        self.setword(self.sh_b + 0x3c, rate)
        self.setword(self.sh_b + 0x40, bps)
        self.setword(self.sh_b + 0x44, nch)
        self.setword(self.sh_b + 0x4c, rate * nch * bps)
        self.setword(self.sh_b + 0x68, abuf)
        self.setword(self.sh_b + 0x6c, 0)
        self.setword(self.sh_b + 0x70, buf_size)
        self.setword(self.sh_b + 0x88, ad_drv)
        self.u.mem_write(self.sh_b + 0x20, struct.pack('<d', 0.0))
        self.setword(self.sh_b + 0xd0, 0)
        self.setword(NEXT_MPCTX + 0x28, self.demux_b)
        self.setword(NEXT_MPCTX + 0x2c, self.sh_b)
        self.setword(NEXT_STATE, 2)
        self.setword(NEXT_CODEC_INITED, pre_inited)
        self.b_stream = pcm_bytes
        self.b_stream_pos = 0
        self.b_decode_calls = 0
        return abuf

    def set_rg(self, mode, track_g=-0x80000000, track_p=100000, album_g=-0x80000000, album_p=100000):
        self.setword(RG_MODE, mode)
        self.u.mem_write(RG_NEXT, struct.pack('<iIiI', track_g, track_p, album_g, album_p))

    # ---- libswresample's model: float interleaved, linear interpolation, the input and the phase kept in the context
    def _ret(self, v=0):
        self.u.reg_write(UC_MIPS_REG_V0, v & 0xffffffff)
        self.u.reg_write(UC_MIPS_REG_PC, self.u.reg_read(UC_MIPS_REG_RA))

    def _arg(self, n):
        return self.word(self.u.reg_read(UC_MIPS_REG_SP) + 0x10 + 4 * n)

    def _swr_alloc(self, u, address, size, _):
        ol = u.reg_read(UC_MIPS_REG_A2) | u.reg_read(UC_MIPS_REG_A3) << 32
        il = self._arg(2) | self._arg(3) << 32
        h = self.malloc(16)
        self.swr[h] = dict(out_fmt=self._arg(0), out=self._arg(1), in_fmt=self._arg(4), inr=self._arg(5), nch=1 if ol == 4 else 2,
                           same=ol == il, buf=[], pos=0.0, base=0, opts={})
        self.swr_log.append(('new', h, self.swr[h]['inr'], self.swr[h]['out']))
        self._ret(h)

    def _swr_opt(self, u, address, size, _):
        a0, a1 = u.reg_read(UC_MIPS_REG_A0), u.reg_read(UC_MIPS_REG_A1)
        self.swr[a0]['opts'][self.read_cstr(a1).decode()] = u.reg_read(UC_MIPS_REG_A2)
        self._ret(0)

    def _swr_init(self, u, address, size, _):
        self.swr_log.append(('init', u.reg_read(UC_MIPS_REG_A0)))
        self._ret(0)

    def _swr_free(self, u, address, size, _):
        pp = u.reg_read(UC_MIPS_REG_A0); h = self.word(pp)
        self.swr_log.append(('free', h)); self.swr.pop(h); self.setword(pp, 0)
        self._ret(0)

    def _swr_convert(self, u, address, size, _):
        h, outp, cap, inp, n_in = (u.reg_read(UC_MIPS_REG_A0), self.word(u.reg_read(UC_MIPS_REG_A1)), u.reg_read(UC_MIPS_REG_A2),
                                   self.word(u.reg_read(UC_MIPS_REG_A3)), self._arg(0))
        m = self.swr[h]; nch = m['nch']
        self.swr_log.append(('convert', h, n_in, cap))
        raw = struct.unpack(f'<{n_in * nch}f', bytes(u.mem_read(inp, 4 * n_in * nch))) if n_in else ()
        m['buf'] += [raw[i * nch:(i + 1) * nch] for i in range(n_in)]
        step, out = m['inr'] / m['out'], []
        while len(out) < cap * nch and int(m['pos']) - m['base'] + 1 < len(m['buf']):
            i = int(m['pos']) - m['base']; t = m['pos'] - int(m['pos'])
            out += [m['buf'][i][c] * (1 - t) + m['buf'][i + 1][c] * t for c in range(nch)]
            m['pos'] += step
        drop = min(max(int(m['pos']) - m['base'], 0), len(m['buf'])); del m['buf'][:drop]; m['base'] += drop
        if out: u.mem_write(outp, struct.pack(f'<{len(out)}f', *out))
        self._ret(len(out) // nch)

    def _uninit_player(self, u, address, size, _):
        self.uninit_masks.append(u.reg_read(UC_MIPS_REG_A0)); self.ao_events.append(('uninit', self.uninit_masks[-1])); self._ret(0)

    def _ao_event(self, name):
        self.ao_events.append(name); self._ret(0)

    def _ao_get_space(self, u, address, size, _):
        v = self.ao_space.pop(0) if len(self.ao_space) > 1 else self.ao_space[0]
        self.ao_events.append(('space', v)); self._ret(v)

    def _ao_init(self, u, address, size, _):
        self._ret(0)

    def _ao_play(self, u, address, size, _):
        a = [u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2)]
        self.ao_plays.append((*a, len(self.uninit_masks))); self.ao_events.append(('play', a[1], a[2])); self._ret(self.ao_short.pop(0) if self.ao_short else a[1])

    def sym(self, name): return self.manifest['symbols'][name]

    def ctl(self, af, cmd, arg): return self.call(self.word(af + 4), af, cmd, arg)

    def play_out(self, af, samples, rate, nch=2):
        """play() when the instance converts: the output is the instance's own buffer (the returned af_data)."""
        body = struct.pack(f'<{len(samples)}f', *samples)
        buf = self.malloc(len(body)); self.u.mem_write(buf, body)
        d = self.malloc(24); self.u.mem_write(d, struct.pack('<Iiiiii', buf, len(body), rate, nch, FLOAT, 4))
        back = self.call(self.word(af + 12), af, d) & 0xffffffff
        audio, ln, orate, onch = struct.unpack('<Iiii', bytes(self.u.mem_read(back, 16)))
        return back != d, orate, list(struct.unpack(f'<{ln // 4}f', bytes(self.u.mem_read(audio, ln)))) if ln else []

    def _init_b(self, u, address, size, _):
        self.init_b_calls += 1
        u.reg_write(UC_MIPS_REG_V0, self.init_b_ok)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def _uninit_next(self, u, address, size, _):
        self.uninit_next_calls += 1
        self.setword(NEXT_MPCTX + 0x28, 0)
        self.setword(NEXT_MPCTX + 0x2c, 0)
        u.reg_write(UC_MIPS_REG_V0, 0)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def _demux_len(self, u, address, size, _):
        a0 = u.reg_read(UC_MIPS_REG_A0)
        val = self.track_b_len if a0 == self.demux_b else self.track_a_len
        u.reg_write(UC_MIPS_REG_F0, struct.unpack('<Q', struct.pack('<d', val))[0])
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def _decode_b(self, u, address, size, _):
        self.b_decode_calls += 1
        sh, dst, minlen, maxlen = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3))
        rem = len(self.b_stream) - self.b_stream_pos
        take = min(rem, maxlen, max(minlen, self.b_chunk_max))
        if take > 0:
            u.mem_write(dst, self.b_stream[self.b_stream_pos:self.b_stream_pos + take])
            self.b_stream_pos += take
            self.setword(sh + 0xd0, self.word(sh + 0xd0) + take)
        u.reg_write(UC_MIPS_REG_V0, take if take > 0 else 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def play_raw(self, af, raw, rate, nch=2, fmt=S16):
        """Run play() with raw PCM bytes in any format; returns (same_bytes, out_bytes)."""
        _, out = self.play(af, None, rate, nch=nch, fmt=fmt, bps=fmt_bps(fmt), raw=raw)
        return out == raw, out

    def uninit(self, af):
        self.leave(af)


def py_resample(b_stereo, b_rate, a_rate, n_out):
    """The swr model's output (linear interpolation, phase kept): the output frames reachable from b_stereo."""
    if b_rate == a_rate:
        return [b_stereo[i] if i < len(b_stereo) else (0.0, 0.0) for i in range(n_out)]
    step, out = b_rate / a_rate, []
    for k in range(n_out):
        i = int(k * step)
        if i + 1 >= len(b_stereo): break
        t = k * step - i
        out.append(tuple(b_stereo[i][c] * (1 - t) + b_stereo[i + 1][c] * t for c in (0, 1)))
    return out + [(0.0, 0.0)] * (n_out - len(out))


def py_xfade_mix(a_stereo, b_stereo, a_rate, b_rate, dur_s, b_rg=1.0):
    """Exact Python reference of equal-power crossfade over len(a_stereo) frames."""
    tot = int(dur_s * a_rate + 0.5)
    b_scaled = [(l * b_rg, r * b_rg) for l, r in b_stereo]
    b_res = py_resample(b_scaled, b_rate, a_rate, len(a_stereo))
    out = []
    for k, ((al, ar), (bl, br)) in enumerate(zip(a_stereo, b_res)):
        if k >= tot:
            out.append((bl, br))
        else:
            ang = math.pi * 0.5 * (k / tot)
            ga, gb = math.cos(ang), math.sin(ang)
            out.append((ga * al + gb * bl, ga * ar + gb * br))
    return out


# ---- 1. Pins & binary invariants
def pin_tests(ctx):
    expect = ctx.expect
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', mod_player.REL), 'rb').read()
    # Every Crossfade pin in mod_player.PINS is checked by check_stock; verify mutating each fails
    xf_pins = [p for p in mod_player.PINS if any(k in p[2] for k in ('PreInitNextSong', 'init_best_audio_codec', 'uninit_next_song', 'demuxer_get_time_length', 'NEXT_', 'RG_', 'MQA', 'ACODEC', 'AFM', 'next_mpctx', 'gapless', 'sh_audio', 'ad_driver', 'codec', 'pts', 'a_buffer', 'eof', 'Crossfade'))]
    expect(len(xf_pins) >= 20, f'mod_player.PINS carries the Crossfade hciplayer pins ({len(xf_pins)})')
    mut = bytearray(stock)
    a0 = xf_pins[0][0]
    off0 = pod.fileoff(mut, a0)
    mut[off0] ^= 1
    keep = mod_player.PLAYER_SHA
    mod_player.PLAYER_SHA = pod.sha(bytes(mut))
    try:
        mod_player.check_stock(bytes(mut)); ok = False
    except ValueError as e: ok = hex(a0)[2:] in str(e)
    finally: mod_player.PLAYER_SHA = keep
    expect(ok, f'mutating pinned hciplayer word {a0:#x} is caught by check_stock')
    # Demo XFADE_PINS
    expect(len(pod.XFADE_PINS) == 15 and {a for a, _, _ in pod.XFADE_PINS} >= {0x5d35a8, 0x5d35e0, 0x5d35f4, 0x5d6454, 0x5d0ea4},
           'XFADE_PINS pins mclGetPlayTime (mutex/playinfo), mclAutoChange post-handoff preload and mcl_gapless_preload')
    expect(len(xfrec()) == 20 and xfrec()[:8] == b'M1XFD01\0', 'xfade_record is 20 bytes with NUL-terminated M1XFD01 magic')


# ---- 2. Record parsing & bit-exact bypass when off or before window
def rec_tests(ctx):
    expect = ctx.expect
    R = 48000
    x = ST.music(512, R)
    cases = [
        ('missing', None), ('seconds 0', xfrec(0, 1)), ('bad magic', xfrec(5, 1, b'M1XFD00\0')),
        ('short', xfrec(5, 1)[:-1]), ('long', xfrec(5, 1) + b'\0'), ('negative', xfrec(-1, 1)),
        ('over max 13', xfrec(13, 1)), ('empty', b''),
    ]
    for what, data in cases:
        p = XP({} if data is None else {XFADE_FILE: data})
        p.set_track_a(pos=57.0, total=60.0)
        p.setup_track_b(encode_pcm(ST.music(1024, R), S16), rate=R, nch=2, fmt=S16)
        af = p.start(R)
        same, y = p.play(af, x, R)
        expect(same and y == x and p.init_b_calls == 0, f'{what}: inactive, bit-exact, Track B codec untouched')
    # Before NEXT_STATE == 2: zero fopen(/tmp/m1plus-xfade) calls!
    p = XP({XFADE_FILE: xfrec(5, 1)})
    p.set_track_a(pos=10.0, total=60.0)
    af = p.start(R)
    p.calls = []
    same, y = p.play(af, x, R)
    expect(same and y == x and ('fopen', XFADE_FILE) not in p.calls, 'NEXT_STATE != 2: zero fopen of /tmp/m1plus-xfade, bit-exact')
    # NEXT_STATE == 2 but still before window (pos=50, total=60, dur=5 -> rem=10 > 5): bit-exact
    p = XP({XFADE_FILE: xfrec(5, 1)})
    p.set_track_a(pos=50.0, total=60.0)
    p.setup_track_b(encode_pcm(ST.music(1024, R), S16), rate=R, nch=2, fmt=S16)
    af = p.start(R)
    same, y = p.play(af, x, R)
    expect(same and y == x and p.init_b_calls == 0, 'before fade window: bit-exact and Track B codec not yet initialized')
    # A decoder without timestamps (sh_audio->pts is MP_NOPTS_VALUE): stock's calc_a_pts fallback, not pts_bytes on top
    NOPTS = -9223372036854775808.0

    def nopts(ds_pts, pts_bytes=0, ibps=0, ds=(0, 0, 0), in_len=0):
        p = XP({XFADE_FILE: xfrec(5, 1)})
        p.set_track_a(pos=NOPTS, total=60.0, pts_bytes=pts_bytes)
        p.u.mem_write(p.ds_a + 0x10, struct.pack('<d', ds_pts))
        p.setword(p.sh_a + 0x50, ibps); p.setword(p.sh_a + 0x5c, in_len)
        for off, v in zip((0, 4, 0x18), ds): p.setword(p.ds_a + off, v)
        p.setup_track_b(encode_pcm(ST.music(1024, R), S16), rate=R, nch=2, fmt=S16)
        p.play(p.start(R), x, R)
        return p.init_b_calls
    expect(nopts(57.0, pts_bytes=57 * 192000) == 1, 'no decoder timestamps, demuxer at 57 s of 60: the fade starts (the decoded bytes are not added again)')
    expect(nopts(40.0, pts_bytes=17 * 192000) == 0, 'no decoder timestamps, demuxer at 40 s: not in the window, whatever was decoded since the seek')
    expect(nopts(50.0, ibps=16000, ds=(1000, 5000, 118000), in_len=2000) == 1,
           'constant bitrate: the packet data read but not decoded (7 s at i_bps) is added to the demuxer\'s 50 s')
    expect(nopts(50.0, ibps=16000, ds=(1000, 5000, 6000), in_len=2000) == 0, 'constant bitrate, nothing read ahead: 50 s, not in the window')
    expect(nopts(0.0, pts_bytes=57 * 192000) == 1, 'nothing from the demuxer either (pts 0, no i_bps): the decoded bytes are the position')
    expect(nopts(0.0, pts_bytes=57 * 192000, ibps=16000) == 0, 'demuxer pts 0 with an i_bps: stock\'s constant-bitrate method, the decoded bytes are not used')
    # A length the demuxer did not know when the track started is asked for again
    p = XP({XFADE_FILE: xfrec(5, 1)})
    p.set_track_a(pos=57.0, total=0.0)
    p.setup_track_b(encode_pcm(ST.music(1024, R), S16), rate=R, nch=2, fmt=S16)
    af = p.start(R)
    p.play(af, x, R)
    none = p.init_b_calls
    p.track_a_len = 60.0
    p.play(af, x, R)
    soon = p.init_b_calls
    p.u.mem_write(p.sh_a + 0x20, struct.pack('<d', 57.6))
    p.play(af, x, R)
    expect((none, soon, p.init_b_calls) == (0, 0, 1), f'a length unknown at the start (0) and known later: asked again 0.5 s on, and the fade starts ({none}, {soon}, {p.init_b_calls})')


# ---- 3. Equal-power mixing, leftover buffer preservation, mono/stereo, ReplayGain
def mix_tests(ctx):
    expect = ctx.expect
    R = 48000
    N = 1024
    # Track A: 440 Hz / 660 Hz; Track B: 1000 Hz / 1500 Hz
    a_flat = PEQ.f32([0.3 * math.sin(2 * math.pi * (440 if c == 0 else 660) * i / R) for i in range(N) for c in (0, 1)])
    b_flat = PEQ.f32([0.3 * math.sin(2 * math.pi * (1000 if c == 0 else 1500) * i / R) for i in range(N + 256) for c in (0, 1)])
    a_st = [(a_flat[2 * i], a_flat[2 * i + 1]) for i in range(N)]
    b_st = [(b_flat[2 * i], b_flat[2 * i + 1]) for i in range(N + 256)]

    # Equal-power mix on float32 (Track A float, Track B S16) with 16 KiB decode chunks:
    # verify exact leftover bytes (overlapping compact_buf: 4096 consumed, 12288 kept) AND real-time instruction budget.
    b_big = PEQ.f32([0.3 * math.sin(2 * math.pi * (1000 if c == 0 else 1500) * i / R) for i in range(5000) for c in (0, 1)])
    b_pcm = encode_pcm(b_big, S16)
    p = XP({XFADE_FILE: xfrec(2, 1)})
    p.b_chunk_max = 16384
    p.set_track_a(pos=58.0, total=60.0)
    abuf = p.setup_track_b(b_pcm, rate=R, nch=2, fmt=S16, buf_size=16384)
    af = p.start(R)
    icount = [0]
    def _cnt(u, a, sz, _): icount[0] += 1
    hk = p.u.hook_add(UC_HOOK_CODE, _cnt, begin=mod_player.PLAYER_BASE, end=mod_player.PLAYER_BASE + 0x10000)
    _, y = p.play(af, a_flat, R)
    p.u.hook_del(hk)
    b_q = decode_pcm(b_pcm, S16)
    b_q_st = [(b_q[2 * i], b_q[2 * i + 1]) for i in range(N)]
    want = [v for pair in py_xfade_mix(a_st, b_q_st, R, R, 2.0) for v in pair]
    err = max(abs(u - v) for u, v in zip(y, want))
    expect(err < 2e-5 and p.init_b_calls == 1 and p.word(NEXT_CODEC_INITED) == 1,
           f'equal-power float mix matches Python model (max err {err:.2e}), NEXT_CODEC_INITED=1')
    # Verify exact frame consumption, byte-exact leftover buffer compaction, and low instruction count (< 1M vs 75.8M)
    rem_len = p.word(p.sh_b + 0x6c)
    consumed = p.b_stream_pos - rem_len
    rem_bytes = bytes(p.u.mem_read(abuf, rem_len))
    expect(consumed == N * 4 and rem_len == 16384 - N * 4 and rem_bytes == b_pcm[N * 4:16384],
           f'sample-accurate handoff: consumed {consumed} == {N * 4}, {rem_len} leftover bytes compacted verbatim')
    expect(icount[0] < 600_000, f'batch buffer consumption keeps 1024-frame 16 KiB block fast ({icount[0]:,} insns < 600,000)')
    # Follow-up block of 2048 frames (8192 B > 4096 B remaining -> exercises non-overlapping memcpy path too)
    a2 = PEQ.f32([0.2 * math.sin(2 * math.pi * (440 + 220 * c) * (N + i) / R) for i in range(2048) for c in (0, 1)])
    p.play(af, a2, R)
    rem_len2 = p.word(p.sh_b + 0x6c)
    consumed2 = p.b_stream_pos - rem_len2
    expect(consumed2 == (N + 2048) * 4 and bytes(p.u.mem_read(abuf, rem_len2)) == b_pcm[consumed2:p.b_stream_pos],
           f'second block (non-overlapping compact): consumed {consumed2} == {(N + 2048) * 4}, leftover exact')

    # Mono Track B -> Stereo Track A
    b_mono = PEQ.f32([0.4 * math.sin(2 * math.pi * 800 * i / R) for i in range(N + 64)])
    p = XP({XFADE_FILE: xfrec(2, 1)})
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(encode_pcm(b_mono, FLOAT), rate=R, nch=1, fmt=FLOAT)
    af = p.start(R)
    _, y = p.play(af, a_flat, R)
    want = [v for pair in py_xfade_mix(a_st, [(v, v) for v in b_mono[:N]], R, R, 2.0) for v in pair]
    expect(max(abs(u - v) for u, v in zip(y, want)) < 2e-5, 'mono Track B upmixed cleanly into stereo Track A')

    # ReplayGain matching: mode 1 (track gain -6 dB), mode 2 (album gain +6 dB with peak 0.8 -> clipped to 1/0.8), mode 1 fallback to album
    for what, mode, tg, tp, ag, ap, want_rg in (
        ('RG off', 0, -600000, 100000, 0, 100000, 1.0),
        ('RG track -6 dB', 1, -600000, 100000, 0, 100000, 10 ** (-6.0 / 20.0)),
        ('RG album +6 dB peak-limited at 0.8', 2, 0, 100000, 600000, 80000, 1.0 / 0.8),
        ('RG track unset falls back to album -3 dB', 1, -0x80000000, 100000, -300000, 100000, 10 ** (-3.0 / 20.0)),
        ('RG gain 100000 (1 dB sentinel? stock skips 100000)', 1, 100000, 100000, 0, 100000, 1.0),
    ):
        p = XP({XFADE_FILE: xfrec(2, 1)})
        p.set_track_a(pos=58.0, total=60.0)
        p.setup_track_b(encode_pcm(b_flat, FLOAT), rate=R, nch=2, fmt=FLOAT)
        p.set_rg(mode, tg, tp, ag, ap)
        af = p.start(R)
        _, y = p.play(af, a_flat, R)
        want = [v for pair in py_xfade_mix(a_st, b_st[:N], R, R, 2.0, b_rg=want_rg) for v in pair]
        expect(max(abs(u - v) for u, v in zip(y, want)) < 2e-5, f'{what}: Track B ReplayGain {want_rg:.4f}')


# ---- 4. Real-time swr cross-rate conversion (the Python model stands in for libswresample)
def resample_tests(ctx):
    expect = ctx.expect
    N = 512
    for a_rate, b_rate in ((44100, 48000), (48000, 44100), (44100, 96000), (96000, 44100)):
        a_flat = PEQ.f32([0.25 * math.sin(2 * math.pi * (440 + 200 * c) * i / a_rate) for i in range(N) for c in (0, 1)])
        b_len = int(N * b_rate / a_rate) + 64
        b_flat = PEQ.f32([0.25 * math.sin(2 * math.pi * (1000 + 300 * c) * i / b_rate) for i in range(b_len) for c in (0, 1)])
        a_st = [(a_flat[2 * i], a_flat[2 * i + 1]) for i in range(N)]
        b_st = [(b_flat[2 * i], b_flat[2 * i + 1]) for i in range(b_len)]
        p = XP({XFADE_FILE: xfrec(2, 1)})
        p.set_track_a(pos=58.0, total=60.0, obps=a_rate * 4)
        p.setup_track_b(encode_pcm(b_flat, FLOAT), rate=b_rate, nch=2, fmt=FLOAT)
        af = p.start(a_rate)
        _, y = p.play(af, a_flat, a_rate)
        want = [v for pair in py_xfade_mix(a_st, b_st, a_rate, b_rate, 2.0) for v in pair]
        err = max(abs(u - v) for u, v in zip(y, want))
        expect(err < 2e-5, f'cross-rate {a_rate} Hz <- {b_rate} Hz matches the Python swr model (max err {err:.2e})')


# ---- 5. Native PCM formats (EQ/Mono/Crossfeed all off -> pass_native) & soft-clipping
def native_tests(ctx):
    expect = ctx.expect
    R = 48000
    N = 256
    a_flat = PEQ.f32([0.3 * math.sin(2 * math.pi * (440 + 100 * c) * i / R) for i in range(N) for c in (0, 1)])
    b_flat = PEQ.f32([0.3 * math.sin(2 * math.pi * (900 + 150 * c) * i / R) for i in range(N + 32) for c in (0, 1)])
    for name, fmt, tol in (('S16', S16, 2e-4), ('S24', S24, 2e-5), ('S32', S32, 2e-5), ('U8', U8, 2e-2)):
        raw_a = encode_pcm(a_flat, fmt)
        raw_b = encode_pcm(b_flat, fmt)
        # Before window: EQ off -> pass_native, accepted natively and bit-exact
        p = XP({XFADE_FILE: xfrec(2, 1)})
        p.flag('0')
        p.set_track_a(pos=10.0, total=60.0)
        p.setup_track_b(raw_b, rate=R, nch=2, fmt=fmt)
        af = p.open()
        r, _, data = p.reinit(af, R, nch=2, fmt=fmt, bps=fmt_bps(fmt))
        same, out = p.play_raw(af, raw_a, R, nch=2, fmt=fmt)
        expect(r == 1 and data[4] == fmt and same, f'native {name} before window: accepted natively and bit-exact')
        # Inside fade window (rem = 0.1 s -> u reaches ~5.3% over 256 frames, well above even U8's LSB): mixes natively
        p.set_track_a(pos=59.9, total=60.0)
        same, out = p.play_raw(af, raw_a, R, nch=2, fmt=fmt)
        dec_a = decode_pcm(raw_a, fmt)
        dec_b = decode_pcm(raw_b, fmt)
        want = [v for pair in py_xfade_mix([(dec_a[2 * i], dec_a[2 * i + 1]) for i in range(N)],
                                           [(dec_b[2 * i], dec_b[2 * i + 1]) for i in range(N)], R, R, 0.1) for v in pair]
        got = decode_pcm(out, fmt)
        err = max(abs(u - v) for u, v in zip(got, want))
        expect(not same and err < tol, f'native {name} crossfade matches reference (max err {err:.2e})')

    # Soft-clipping on S16 when two hot (+0.95) tracks overlap near 50% (sum ~ 1.34 > 1.0)
    hot_a = [0.95] * (2 * 512)
    p = XP({XFADE_FILE: xfrec(1, 1)})
    p.flag('0')
    p.set_track_a(pos=59.0, total=60.0)
    p.setup_track_b(encode_pcm([0.95] * (2 * 30000), S16), rate=R, nch=2, fmt=S16)
    af = p.open()
    p.reinit(af, R, nch=2, fmt=S16, bps=2)
    raw_a = encode_pcm(hot_a, S16)
    peak = 0.0
    wrapped = False
    for k in range(50):
        p.set_track_a(pos=59.0 + k * 512 / R, total=60.0)
        _, out = p.play_raw(af, raw_a, R, nch=2, fmt=S16)
        vals = decode_pcm(out, S16)
        if any(v < 0.0 for v in vals): wrapped = True
        peak = max(peak, max(vals))
    expect(not wrapped and 0.95 < peak <= 1.0, f'hot native S16 overlap soft-clips cleanly without wrap (peak {peak:.4f})')


def flac_seek_tests(ctx):
    expect = ctx.expect
    trim_addr = 0xb15290
    trim_bits = struct.unpack('<I', struct.pack('<f', 240.125))[0]

    class FP(XP):
        def __init__(self):
            super().__init__({XFADE_FILE: xfrec(2, 1)})
            self.init_trims, self.decode_trims = [], []

        def _init_b(self, u, address, size, user):
            self.init_trims.append(self.word(trim_addr))
            return super()._init_b(u, address, size, user)

        def _decode_b(self, u, address, size, user):
            self.decode_trims.append(self.word(trim_addr))
            if self.word(trim_addr):
                u.reg_write(UC_MIPS_REG_V0, 0xffffffff)
                u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
                return
            return super()._decode_b(u, address, size, user)

    for rate, fmt in ((44100, S32), (96000, S32), (44100, FLOAT)):
        p = FP()
        if fmt != FLOAT: p.flag('0')
        p.set_track_a(pos=58.0, total=60.0, obps=rate * 8)
        p.setup_track_b(encode_pcm([0.6] * 8192, S32), rate=rate, fmt=S32)
        p.setword(trim_addr, trim_bits)
        af = p.start(rate, fmt=fmt)
        p.play_raw(af, encode_pcm([0.25] * 2048, fmt), rate, fmt=fmt)
        expect(p.init_trims == [0] and p.decode_trims and not any(p.decode_trims) and p.b_stream_pos > 0
               and p.word(NEXT_CODEC_INITED) == 1 and p.word(trim_addr) == trim_bits,
               f'FLAC {rate} Hz format {fmt}: B init/refills see zero seek trim and preserve A\'s exact 240.125 s threshold')

    p = FP()
    p.init_b_ok = 0
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(encode_pcm([0.6] * 8192, FLOAT), fmt=FLOAT)
    p.setword(trim_addr, trim_bits)
    af = p.start(48000)
    p.play(af, [0.25] * 1024, 48000)
    expect(p.init_trims == [0] and not p.decode_trims and p.word(trim_addr) == trim_bits,
           'failed B codec initialization restores A\'s seek threshold before returning')

    p = FP()
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(b'', fmt=FLOAT, pre_inited=1)
    p.setword(trim_addr, trim_bits)
    af = p.start(48000)
    p.play(af, [0.25] * 1024, 48000)
    expect(not p.init_trims and p.decode_trims == [0] and p.word(trim_addr) == trim_bits,
           'already-initialized B still isolates its decode and restores A\'s threshold on EOF/error')


# ---- 6. VBR early/late EOF, backward seek abort, closegapless abort, exclusions
def edge_tests(ctx):
    expect = ctx.expect
    R = 48000

    # VBR early EOF carry across rate change (44100 -> 48000): Track A ends at ~25% of a 2 s fade
    p = XP({XFADE_FILE: xfrec(2, 1)})
    p.set_track_a(pos=58.0, total=60.0, obps=44100 * 4)
    p.setup_track_b(encode_pcm([0.5] * (2 * 40000), FLOAT), rate=48000, nch=2, fmt=FLOAT)
    af1 = p.start(44100)
    blk = [0.5] * (2 * 22050)   # 0.5 s of 2.0 s -> u = 0.25
    p.play(af1, blk, 44100)
    p.ended(1)      # Track A hit early EOF
    p.uninit(af1)   # saves xfade_carry (u ~ 0.25, dur = 2.0)
    # Track B opens at its native 48000 Hz!
    p.setword(NEXT_STATE, 0)
    p.set_track_a(pos=0.5, total=120.0, obps=48000 * 4)
    af2 = p.start(48000)
    x_b = [0.5] * (2 * 1024)
    _, y_b = p.play(af2, x_b, 48000)
    # First frame gain should be sin(pi/2 * 0.25) ~ 0.3827 -> 0.5 * 0.3827 = 0.1913
    expect(abs(y_b[0] - 0.5 * math.sin(math.pi * 0.5 * 0.25)) < 1e-3 and y_b[-1] > y_b[0],
           f'VBR early EOF carry across 44.1k->48k starts Track B at sin(pi/2*0.25) ({y_b[0]:.4f}) and ramps up')
    # After remaining 1.5 s (72000 frames) finishes, Track B is bit-exact untouched
    for _ in range(72): p.play(af2, x_b, 48000)
    same, y_done = p.play(af2, x_b, 48000)
    expect(same and y_done == x_b, 'after XF_TAIL_IN finishes, Track B is bit-exact untouched')

    # VBR late EOF (force_eof): when pos_frames reaches tot_frames, d_audio->eof=1 & mpctx->eof=1, XF_DONE plays Track B
    p = XP({XFADE_FILE: xfrec(1, 1)})
    p.set_track_a(pos=59.9, total=60.0)   # eff clamped to rem = 0.1 s = 4800 frames
    b_sig = PEQ.f32([0.6] * (2 * 8000))
    p.setup_track_b(encode_pcm(b_sig, FLOAT), rate=R, nch=2, fmt=FLOAT)
    af = p.start(R)
    a_sig = PEQ.f32([0.2] * (2 * 6000))
    _, y = p.play(af, a_sig, R)
    expect(p.word(p.ds_a + 0x1c) == 1 and p.word(p.mp_a + 0x14) == 1 and abs(y[-1] - 0.6) < 1e-5,
           'VBR late EOF sets d_audio->eof=1 and mpctx->eof=1, remaining frames output pure Track B')

    # Backward seek mid-fade -> 20 ms smooth abort, UNINIT_NEXT called, NEXT_FLAG=1
    p = XP({XFADE_FILE: xfrec(2, 1)})
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(encode_pcm([0.8] * (2 * 10000), FLOAT), rate=R, nch=2, fmt=FLOAT)
    af = p.start(R)
    p.play(af, [0.2] * (2 * 2400), R)   # enter XF_ACTIVE
    p.set_track_a(pos=30.0, total=60.0)  # seek backward 28 s!
    _, y_ab = p.play(af, [0.2] * (2 * 1200), R)  # 960 frames = 20 ms ramp, then XF_IDLE
    expect(p.uninit_next_calls == 1 and p.word(NEXT_CODEC_INITED) == 0 and p.word(NEXT_STATE) == 0 and p.word(NEXT_FLAG) == 1,
           'backward seek mid-fade aborts cleanly, frees next_mpctx and sets NEXT_FLAG=1 to re-preload')
    expect(abs(y_ab[-1] - 0.2) < 1e-5, 'after 20 ms abort ramp, output is back to pure Track A')
    same, y_after = p.play(af, [0.2] * (2 * 256), R)
    expect(same, 'subsequent blocks after abort are bit-exact Track A')

    # mcl-closegapless mid-fade (NEXT_STATE drops 2 -> 0) -> 20 ms abort WITHOUT calling UNINIT_NEXT or NEXT_FLAG
    p = XP({XFADE_FILE: xfrec(2, 1)})
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(encode_pcm([0.8] * (2 * 10000), FLOAT), rate=R, nch=2, fmt=FLOAT)
    af = p.start(R)
    p.play(af, [0.2] * (2 * 2400), R)
    p.setword(NEXT_STATE, 0)
    _, y_ab = p.play(af, [0.2] * (2 * 1200), R)
    expect(p.uninit_next_calls == 0 and p.word(NEXT_FLAG) == 0 and abs(y_ab[-1] - 0.2) < 1e-5,
           'mcl-closegapless mid-fade ramps back to Track A in 20 ms without double-freeing next_mpctx')

    # Bypasses: DSD Track B, MQA_MODE==2, kill switch, failed init_best_audio_codec, short Track A, short Track B, live Off change
    x = ST.music(256, R)
    for what, tweak in (
        ('DSD dsdiff Track B', lambda p: p.setup_track_b(encode_pcm(x, S16), rate=R, drv='dsdiff', name='dsd')),
        ('FFmpeg ffdsd Track B', lambda p: p.setup_track_b(encode_pcm(x, S16), rate=R, drv='ffmpeg', name='ffdsd_msbf')),
        ('MQA_MODE 2', lambda p: (p.setup_track_b(encode_pcm(x, S16), rate=R), p.setword(MQA_MODE, 2))),
        ('kill switch', lambda p: (p.setup_track_b(encode_pcm(x, S16), rate=R), p.files.update({KILL: b''}))),
        ('init_best_audio_codec fails', lambda p: (p.setup_track_b(encode_pcm(x, S16), rate=R), setattr(p, 'init_b_ok', 0))),
        ('short Track A (9 s)', lambda p: (p.setup_track_b(encode_pcm(x, S16), rate=R), p.set_track_a(pos=7.0, total=9.0))),
        ('short Track B (9 s)', lambda p: p.setup_track_b(encode_pcm(x, S16), rate=R, total=9.0)),
    ):
        p = XP({XFADE_FILE: xfrec(2, 1)})
        p.set_track_a(pos=58.0, total=60.0)
        tweak(p)
        af = p.start(R)
        same, y = p.play(af, x, R)
        expect(same and y == x, f'{what}: skipped cleanly, bit-exact')

    # Short Track B duration clamp: 12 s Track B with 5 s setting -> max_eff = (12 - 4)/2 = 4.0 s
    p = XP({XFADE_FILE: xfrec(5, 1)})
    p.set_track_a(pos=55.5, total=60.0)   # rem = 4.5 > 4.0 -> must wait
    p.setup_track_b(encode_pcm(ST.music(1024, R), S16), rate=R, total=12.0)
    af = p.start(R)
    _, y_wait = p.play(af, x, R)
    expect(y_wait == x and p.init_b_calls == 0, '12 s Track B clamps 5 s fade to 4 s: inactive at rem=4.5 s')
    p.set_track_a(pos=56.0, total=60.0)   # rem = 4.0 <= 4.0 -> starts now
    _, y_go = p.play(af, x, R)
    expect(y_go != x and p.init_b_calls == 1, '12 s Track B enters clamped 4 s fade at rem=4.0 s')

    # Track B early EOF mid-fade (e.g. overestimated duration or truncated file):
    # must NOT fade Track A to silence or force_eof; ramps Track A back to 1.0, re-preloads Track B, never re-enters same seq
    p = XP({XFADE_FILE: xfrec(2, 7)})
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(encode_pcm([0.6] * (2 * 1500), FLOAT), rate=R, nch=2, fmt=FLOAT, total=60.0)
    af = p.start(R)
    a_blk = PEQ.f32([0.4] * (2 * 1024))
    p.play(af, a_blk, R)   # 1024 frames in XF_ACTIVE (476 B frames left)
    _, y_eof = p.play(af, PEQ.f32([0.4] * (2 * 2000)), R)   # B hits EOF at frame 476 -> 960-frame abort ramp -> pure Track A (0.4)
    expect(p.word(p.ds_a + 0x1c) == 0 and p.word(p.mp_a + 0x14) == 0
           and p.uninit_next_calls == 1 and p.word(NEXT_FLAG) == 1 and p.word(NEXT_STATE) == 0,
           'Track B early EOF mid-fade does not force_eof A; frees next_mpctx and sets NEXT_FLAG=1')
    expect(abs(y_eof[-1] - 0.4) < 1e-5 and min(y_eof) > 0.35,
           f'Track B early EOF ramps Track A smoothly back to 0.4 without dropping to silence (min {min(y_eof):.3f}, end {y_eof[-1]:.3f})')
    # Even after PreInitNextSong re-preloads Track B (NEXT_STATE=2, same seq=7), Track A stays untouched (no loop)
    p.setup_track_b(encode_pcm([0.6] * (2 * 1500), FLOAT), rate=R, nch=2, fmt=FLOAT, total=60.0)
    p.set_track_a(pos=58.2, total=60.0)
    same, y_after = p.play(af, a_blk, R)
    expect(same and y_after == a_blk, 'after Track B early EOF re-preload with same seq, Track A stays bit-exact (no re-entry loop)')

    # Track B immediate EOF on frame 0 (empty B stream): entire block stays bit-exact untouched Track A
    p = XP({XFADE_FILE: xfrec(2, 9)})
    p.set_track_a(pos=58.0, total=60.0)
    p.setup_track_b(b'', rate=R, nch=2, fmt=FLOAT, total=0.0)
    af = p.start(R)
    same, y_zero = p.play(af, x, R)
    expect(same and y_zero == x and p.uninit_next_calls == 1 and p.word(NEXT_FLAG) == 1 and p.word(p.mp_a + 0x14) == 0,
           'Track B immediate EOF on frame 0 leaves Track A bit-exact and re-preloads without force_eof')

    # Cross-rate Track B early EOF (44.1k <- 48k): also aborts cleanly back to full Track A
    p = XP({XFADE_FILE: xfrec(2, 11)})
    p.set_track_a(pos=58.0, total=60.0, obps=44100 * 4)
    p.setup_track_b(encode_pcm([0.5] * (2 * 800), FLOAT), rate=48000, nch=2, fmt=FLOAT, total=60.0)
    af = p.start(44100)
    _, y_cr = p.play(af, [0.3] * (2 * 2500), 44100)
    expect(p.word(p.mp_a + 0x14) == 0 and p.uninit_next_calls == 1 and abs(y_cr[-1] - 0.3) < 1e-5,
           'cross-rate Track B early EOF recovers cleanly to pure Track A without force_eof')

    # Live setting update: record changed from 5 s to 0 s while NEXT_STATE==2 before window
    p = XP({XFADE_FILE: xfrec(5, 1)})
    p.set_track_a(pos=50.0, total=60.0)
    p.setup_track_b(encode_pcm(x, S16), rate=R)
    af = p.start(R)
    p.play(af, x, R)   # caches next_sec = 5 at pos=50
    p.files[XFADE_FILE] = xfrec(0, 2)   # user turns Crossfade Off at pos=55.5
    p.set_track_a(pos=55.5, total=60.0)
    same, y = p.play(af, x, R)
    expect(same and y == x and p.init_b_calls == 0, 'turning Crossfade Off while preloaded before window cancels fade')


# ---- 7. demo side (patch/xfadeset.c): settings, smart cross-album, exclusions, Gapless-off bridge
class XM(Machine):
    """Machine with mclAutoChange and mclGetPlayType mocked (records MCL_GAPLESS observed during mclAutoChange)."""

    def __init__(self):
        super().__init__()
        self.handlers[pod.FUNCTIONS['mclAutoChange'][2]] = 'mclAutoChange'
        self.auto_seen = []
        self.play_type = 0

    def _hook(self, u, address, size, d):
        name = self.handlers.get(address)
        if name == 'mclAutoChange':
            gl = self.u.mem_read(pod.DATA['MCL_GAPLESS'][0], 1)[0]
            self.calls.append(('mclAutoChange', gl))
            self.auto_seen.append(gl)
            u.reg_write(UC_MIPS_REG_V0, 42)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'mclGetPlayType':
            u.reg_write(UC_MIPS_REG_V0, self.play_type & 0xffffffff)
            u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        return super()._hook(u, address, size, d)


def call_c(m, name, *args):
    kw = dict(zip(('a0', 'a1', 'a2', 'a3'), args))
    return m.call(PSYMS[name], count=4000000, **kw)


def read_rt(m):
    raw = m.fs.get(XFADE_FILE)
    if not raw or len(raw) != 20: return None
    magic = raw[:8]
    sec, seq, keep = struct.unpack_from('<iii', raw, 8)
    return magic, sec, seq, keep


def demo_tests(ctx):
    expect = ctx.expect
    # Settings persistence, validation, failure handling
    m = XM()
    expect(call_c(m, 'xfade_on') == 0 and call_c(m, 'xfade_sec') == 5 and call_c(m, 'xfade_seconds') == 0 and call_c(m, 'xfade_auto') == 1,
           'defaults: Crossfade off (0 s), duration 5 s, Keep Albums Gapless ON (1)')
    expect(call_c(m, 'xfade_on_toggle') == 1 and m.fs[SET_FILE] == b'e\n' and ('rename', SET_TMP, SET_FILE) in m.calls and call_c(m, 'xfade_seconds') == 5,
           'xfade_on_toggle -> on, 5 s, saved atomically as "e"')
    expect(call_c(m, 'xfade_sec_set', 8) == 8 and m.fs[SET_FILE] == b'h\n' and call_c(m, 'xfade_seconds') == 8 and call_c(m, 'xfade_sec_set', 12) == 12 and m.fs[SET_FILE] == b'l\n',
           'xfade_sec_set(8) -> "h", 12 s -> "l"')
    expect(call_c(m, 'xfade_sec_set', 0) == 0xffffffff and call_c(m, 'xfade_sec_set', 13) == 0xffffffff and call_c(m, 'xfade_sec') == 12, 'out-of-range durations rejected')
    expect(call_c(m, 'xfade_on_toggle') == 0 and m.fs[SET_FILE] == b'L\n' and call_c(m, 'xfade_seconds') == 0 and call_c(m, 'xfade_sec') == 12,
           'off keeps the duration ("L"); xfade_seconds is 0')
    m.fail.add(('write', SET_TMP))
    expect(call_c(m, 'xfade_sec_set', 4) == 0xffffffff and call_c(m, 'xfade_sec') == 12 and call_c(m, 'xfade_on_toggle') == 0xffffffff and call_c(m, 'xfade_on') == 0, 'failed write leaves the settings unchanged')
    m.fail.clear()
    m = XM(); m.fs[SET_FILE] = b'C\n'
    expect(call_c(m, 'xfade_on') == 0 and call_c(m, 'xfade_sec') == 3, 'a file "C": off, 3 s kept')
    m = XM(); m.fs[SET_FILE] = b'2\n'
    expect(call_c(m, 'xfade_on') == 0 and call_c(m, 'xfade_sec') == 5, 'any other file (the old "0".."5"): off, 5 s')
    m = XM()
    expect(call_c(m, 'xfade_auto_toggle') == 0 and m.fs[AUTO_FILE] == b'0\n' and call_c(m, 'xfade_auto') == 0,
           'xfade_auto_toggle -> 0 (Always), saved atomically')
    expect(call_c(m, 'xfade_auto_toggle') == 1 and m.fs[AUTO_FILE] == b'1\n', 'toggle back -> 1')
    # Boot cleanup
    m.fs[XFADE_FILE] = xfrec(5, 1); m.fs[XFADE_TMP] = b'tmp'; m.fs[XFOUT_FILE] = b'\0' * 8
    call_c(m, 'xfade_boot')
    expect(XFADE_FILE not in m.fs and XFADE_TMP not in m.fs and XFOUT_FILE not in m.fs, 'xfade_boot unlinks stale tmpfs record, .tmp and the output-rate record')

    # Helper to set up a 2-track queue and run xfade_auto_change
    def run_auto(cur_kw, nxt_kw, sec=5, smart=1, gapless=1, play_time=(190, 200), mode=0, pos=0, running=1, preload=0, pt=0, kill=False):
        m = XM()
        m.fs[SET_FILE] = f'{chr(ord("a") + sec - 1) if sec else "E"}\n'.encode()
        m.fs[AUTO_FILE] = f'{smart}\n'.encode()
        if kill: m.present.add(KILL)
        cue_end0 = cur_kw.pop('cue_end', 0)
        r0 = m.record(**cur_kw)
        if cue_end0: m.setword(r0 + O['REC_CUE_END'], cue_end0)
        r1 = m.record(**nxt_kw)
        q = m.new_deque([r0, r1])
        m.setword(pod.DATA['PLAY_QUEUE'][0], q)
        m.u.mem_write(pod.DATA['HCI_RUNNING'][0], bytes([running]))
        m.u.mem_write(pod.DATA['MCL_GAPLESS'][0], bytes([gapless]))
        m.setword(pod.DATA['MCL_PRELOAD'][0], preload)
        m.play_pos = pos
        m.play_status = 2
        m.mode = mode
        m.play_time = play_time
        m.calls = []
        r = call_c(m, 'xfade_auto_change')
        return m, r

    # Off: zero extra calls, direct mclAutoChange
    m, r = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=0)
    expect(r == 42 and m.auto_seen == [1] and not any(c[0] in ('mclGetPlayTime', 'mcl_gapless_preload') for c in m.calls),
           'Crossfade Off: direct mclAutoChange without reading play time or preloading')
    # Off, the passes after the first (the idle pass runs about 125 times a second): the setting is the cached one, so no file is looked at
    files = lambda m: [c for c in m.calls if c[0] in ('access', 'open', 'fopen', 'stat')]
    expect(not [c for c in m.calls if c[0] == 'access'], f'Crossfade Off, the first pass: the kill switch is not looked for ({files(m)})')
    m.calls = []; m.auto_seen = []
    rs = [call_c(m, 'xfade_auto_change') for _ in range(3)]
    expect(rs == [42] * 3 and m.auto_seen == [1] * 3 and not files(m), f'Crossfade Off, later passes: stock\'s mclAutoChange each time, no file call at all ({files(m)})')
    m, r = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=0, kill=True)
    m.calls = []
    expect(r == 42 and call_c(m, 'xfade_auto_change') == 42 and not files(m), 'Crossfade Off with the kill switch: the same, stock and no file call')

    # Kill switch: direct mclAutoChange
    m, r = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, kill=True)
    expect(r == 42 and XFADE_FILE not in m.fs and not any(c[0] == 'mcl_gapless_preload' for c in m.calls),
           'kill switch: direct mclAutoChange, no record written')
    expect(('access', KILL) in m.calls and m.auto_seen == [1] and not any(c[0] == 'mclGetPlayTime' for c in m.calls),
           'Crossfade On with the kill switch: the switch is looked for, stock runs with Gapless as it was, the play time not read')
    m.calls = []; m.auto_seen = []
    expect(call_c(m, 'xfade_auto_change') == 42 and ('access', KILL) in m.calls and m.auto_seen == [1] and XFADE_FILE not in m.fs,
           'and on the next pass again (the switch is looked for on every pass while Crossfade is on)')

    # Cross-album with smart ON (5 s, total 200, cur 190 -> rem 10 <= 5+5): writes 5 s and triggers early preload!
    m, r = run_auto({'album': 'Album A', 'path': '/mnt/mmc/1.flac'}, {'album': 'Album B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, play_time=(190, 200))
    expect(r == 42 and read_rt(m)[:2] == (b'M1XFD01\0', 5) and read_rt(m)[3] == 1 and ('mcl_gapless_preload', 1) in m.calls,
           'cross-album at T-10s (5 s fade): writes 5 s (and keep) to /tmp/m1plus-xfade and triggers early preload')

    # Same-album with smart ON: writes 0 s near end, does NOT crossfade or trigger early preload
    m, r = run_auto({'album': 'Same', 'path': '/mnt/mmc/1.flac'}, {'album': 'Same', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, play_time=(195, 200))
    expect(read_rt(m)[:2] == (b'M1XFD01\0', 0) and read_rt(m)[3] == 1 and not any(c[0] == 'mcl_gapless_preload' for c in m.calls),
           'same-album with Keep Albums Gapless ON: writes seconds=0 (stays gapless) with keep=1 (two music tracks)')
    m.calls = []
    call_c(m, 'xfade_auto_change')
    expect(read_rt(m)[2] == 1, 'an unchanged record is not written again (its sequence number stays)')

    # The queue records are looked at 500 ms apart far from the end (the idle pass runs far more often); the play time is read on every pass, and
    # inside the longest window (sec + 5 s), on another track or after a seek there, the records are looked at at once
    reads = lambda m: sum(m.deque_reads.values())
    m, r = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, play_time=(100, 200))
    n = reads(m)
    expect(n and read_rt(m)[1:] == (0, 1, 1), f'the first pass looks: not in the window yet, keep 1 ({read_rt(m)})')
    m.play_time = (150, 200); m.clock += 100; m.calls = []; m.auto_seen = []
    call_c(m, 'xfade_auto_change')
    expect(reads(m) == n and any(c[0] == 'mclGetPlayTime' for c in m.calls) and not any(c[0] == 'mcl_gapless_preload' for c in m.calls) and read_rt(m)[1:] == (0, 1, 1)
           and m.auto_seen == [1], 'a pass 100 ms later, 50 s from the end: the play time read, no record looked at, the record stands, stock\'s mclAutoChange runs')
    m.play_time = (196, 200); m.clock += 100; m.calls = []
    call_c(m, 'xfade_auto_change')
    expect(reads(m) > n and ('mcl_gapless_preload', 1) in m.calls and read_rt(m)[1] == 5 and m.word(pod.DATA['MCL_PRELOAD'][0]) == 1,
           'a seek to 4 s before the end 100 ms after the last look: looked at at once, 5 s written and the preload open before stock\'s own')
    m, r = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, play_time=(100, 200))
    n = reads(m); m.play_time = (150, 200); m.clock += 500
    call_c(m, 'xfade_auto_change')
    expect(reads(m) > n, '500 ms after the last look: looked at again')
    m, r = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, play_time=(100, 200), mode=3)
    n = reads(m); m.play_pos = 1
    call_c(m, 'xfade_auto_change')
    expect(reads(m) > n, 'another track: looked at in the same millisecond')

    # Same-album with smart OFF (Always): crossfades!
    m, r = run_auto({'album': 'Same', 'path': '/mnt/mmc/1.flac'}, {'album': 'Same', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=0, play_time=(190, 200))
    expect(read_rt(m)[:2] == (b'M1XFD01\0', 5) and ('mcl_gapless_preload', 1) in m.calls,
           'same-album with Keep Albums Gapless OFF: crossfades (writes 5 s and preloads)')

    # Exclusions: DSD (.dsf/.dff/.iso), CUE, Podcasts, Audiobooks, HTTP, short track (< 10 s)
    # keep (the last field): 0 for everything crossfade stays out of, so a kept output never goes on into it either
    excl = [
        ('DSD .dsf', {'album': 'A', 'path': '/mnt/mmc/1.dsf'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (195, 200), 0),
        ('DSD .dff next', {'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.DFF'}, (195, 200), 0),
        ('DSD .iso', {'album': 'A', 'path': '/mnt/mmc/1.iso'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (195, 200), 0),
        ('CUE track', {'album': 'A', 'path': '/mnt/mmc/1.flac', 'cue_end': 200}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (195, 200), 0),
        ('Podcast', {'album': 'A', 'path': '/mnt/mmc/Podcasts/show/ep1.mp3'}, {'album': 'B', 'path': '/mnt/mmc/Podcasts/show/ep2.mp3'}, (195, 200), 0),
        ('Podcast, the folder in lower case', {'album': 'A', 'path': '/mnt/mmc/podcasts/show/ep1.mp3'}, {'album': 'B', 'path': '/mnt/mmc/podcasts/show/ep2.mp3'}, (195, 200), 0),
        ('music into a podcast episode', {'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/PODCASTS/show/ep2.mp3'}, (195, 200), 0),
        ('a file loose in the Podcasts folder', {'album': 'A', 'path': '/mnt/mmc/Podcasts/ep1.mp3'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (195, 200), 0),
        ('Audiobook', {'album': 'A', 'path': '/mnt/mmc/Audiobooks/bk/ch1.m4b'}, {'album': 'B', 'path': '/mnt/mmc/Audiobooks/bk/ch2.m4b'}, (195, 200), 0),
        ('Audiobook, the folder in upper case', {'album': 'A', 'path': '/mnt/mmc/AUDIOBOOKS/bk/ch1.m4b'}, {'album': 'B', 'path': '/mnt/mmc/AUDIOBOOKS/bk/ch2.m4b'}, (195, 200), 0),
        ('an audiobook chapter into music', {'album': 'A', 'path': '/mnt/mmc/audiobooks/ch1.mp3'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (195, 200), 0),
        ('HTTP stream', {'album': 'A', 'path': 'http://example/1.mp3'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (195, 200), 0),
        ('HTTPS stream (radio, a server, a feed)', {'album': 'A', 'path': 'HTTPS://example/1.mp3'}, {'album': 'B', 'path': 'https://example/2.mp3'}, (195, 200), 0),
        ('short track 9 s', {'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, (5, 9), 1),
    ]
    for what, c0, c1, tm, keep in excl:
        m, _ = run_auto(c0, c1, sec=5, smart=0, play_time=tm)
        rt = read_rt(m)
        expect(not any(c[0] == 'mcl_gapless_preload' for c in m.calls) and rt is not None and rt[1] == 0 and rt[3] == keep,
               f'exclusion {what}: no crossfade preload, record seconds 0 and keep {keep} ({rt})')
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/Podcasts Extra/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/Music/Audiobooks/2.flac'}, sec=5, smart=0, play_time=(190, 200))
    expect(read_rt(m)[1] == 5 and read_rt(m)[3] == 1, 'folders that only look like Podcasts / Audiobooks are music: crossfaded')

    # Duration clamp: 14 s track with 10 s setting -> max_eff = (14 - 4) / 2 = 5 s
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=10, smart=1, play_time=(6, 14))
    expect(read_rt(m)[:2] == (b'M1XFD01\0', 5) and ('mcl_gapless_preload', 1) in m.calls,
           '14 s track with 10 s setting clamps eff to (14-4)/2 = 5 s')

    # Gapless-OFF bridge: preload raises MCL_GAPLESS to 1 and restores 0; handoff (running=0, preload=1) raises to 1 around mclAutoChange and restores 0!
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, gapless=0, play_time=(190, 200))
    expect(('mcl_gapless_preload', 1) in m.calls and m.u.mem_read(pod.DATA['MCL_GAPLESS'][0], 1)[0] == 0 and m.word(pod.DATA['MCL_PRELOAD'][0]) == 1,
           'Gapless OFF: preload temporarily raises MCL_GAPLESS=1 and immediately restores 0')
    # Now Track A ends (HCI_RUNNING=0, MCL_PRELOAD=1): clears shared play time before mclAutoChange so stock's 0x5d6454
    # fallthrough cannot prematurely preload Track C, runs mclAutoChange with MCL_GAPLESS=1, then restores 0!
    m.setword(pod.DATA['MCL_PLAYINFO'][0] + 8, 200)
    m.setword(pod.DATA['MCL_PLAYINFO'][0] + 12, 198)
    m.u.mem_write(pod.DATA['HCI_RUNNING'][0], b'\0')
    m.auto_seen = []; m.calls = []
    call_c(m, 'xfade_auto_change')
    expect(m.auto_seen == [1] and m.u.mem_read(pod.DATA['MCL_GAPLESS'][0], 1)[0] == 0
           and m.word(pod.DATA['MCL_PLAYINFO'][0] + 8) == 0 and m.word(pod.DATA['MCL_PLAYINFO'][0] + 12) == 0,
           'Gapless OFF handoff: clears shared play time, runs mclAutoChange with MCL_GAPLESS=1, restores user byte to 0')

    # Turning Crossfade Off while forced_gapless preload is open closes preload via mclSetGaplessMode(0)
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, gapless=0, play_time=(190, 200))
    m.calls = []
    call_c(m, 'xfade_on_toggle')
    expect(('mclSetGaplessMode', 0) in m.calls and read_rt(m)[1] == 0,
           'turning Crossfade Off while forced_gapless preload is active sends mclSetGaplessMode(0) and writes 0')

    # Repeat All wrap-around at last track -> preloads track 0; List Play at last track -> no preload
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, mode=3, pos=1, play_time=(190, 200))
    expect(read_rt(m)[:2] == (b'M1XFD01\0', 5) and ('mcl_gapless_preload', 1) in m.calls, 'Repeat All wraps from last track to track 0')
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, mode=0, pos=1, play_time=(190, 200))
    expect(not any(c[0] == 'mcl_gapless_preload' for c in m.calls), 'List Play at last track does not preload')
    m, _ = run_auto({'album': 'A', 'path': '/mnt/mmc/1.flac'}, {'album': 'B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, mode=1, pos=0, play_time=(190, 200))
    expect(not any(c[0] == 'mcl_gapless_preload' for c in m.calls), 'Repeat Track does not crossfade')

    # Stale runtime record from previous track must be cleared on subsequent short / excluded / same-album / Repeat Track songs
    m, _ = run_auto({'album': 'Album A', 'path': '/mnt/mmc/1.flac'}, {'album': 'Album B', 'path': '/mnt/mmc/2.flac'}, sec=5, smart=1, play_time=(190, 200))
    expect(read_rt(m)[1] == 5, 'track 0 wrote seconds=5')
    # Advance to a 9-second track (preload resets to 0): runtime record MUST be cleared to 0 immediately
    m.setword(pod.DATA['MCL_PRELOAD'][0], 0)
    m.play_pos = 1
    m.play_time = (2, 9)
    m.calls = []
    call_c(m, 'xfade_auto_change')
    expect(read_rt(m)[1] == 0 and not any(c[0] == 'mcl_gapless_preload' for c in m.calls),
           'subsequent 9 s short track clears stale seconds=5 runtime record to 0')
    # Pre-seeded stale record on Repeat Track and on same-album track early in playback also clears to 0
    for what, extra in (
        ('short 9 s with pre-seeded file', {'play_time': (5, 9)}),
        ('Repeat Track with pre-seeded file', {'mode': 1, 'play_time': (100, 200)}),
        ('same-album early in track', {'play_time': (10, 200)}),
    ):
        m = XM()
        m.fs[SET_FILE] = b'e\n'; m.fs[AUTO_FILE] = b'1\n'; m.fs[XFADE_FILE] = xfrec(5, 1)
        r0 = m.record(album='Same', path='/mnt/mmc/1.flac')
        r1 = m.record(album='Same', path='/mnt/mmc/2.flac')
        m.setword(pod.DATA['PLAY_QUEUE'][0], m.new_deque([r0, r1]))
        m.u.mem_write(pod.DATA['HCI_RUNNING'][0], b'\x01')
        m.u.mem_write(pod.DATA['MCL_GAPLESS'][0], b'\x01')
        m.setword(pod.DATA['MCL_PRELOAD'][0], 0)
        m.play_pos = 0; m.play_status = 2
        m.mode = extra.get('mode', 0); m.play_time = extra['play_time']
        call_c(m, 'xfade_auto_change')
        expect(read_rt(m)[1] == 0, f'{what}: stale /tmp/m1plus-xfade cleared to 0')

    # xfade_on_preload_cancel writes seconds=0
    call_c(m, 'xfade_on_preload_cancel')
    expect(read_rt(m)[1] == 0, 'xfade_on_preload_cancel clears runtime crossfade record to 0')


# ---- 8. Settings UI & Settings Files integration
def ui_tests(ctx):
    expect, P = ctx.expect, pod_pages
    PS, XF = P.PLAYSET_PAGE, P.PSXFADE_PAGE
    labels = [r.label for r in PS.rows]
    gi = labels.index('Gapless')
    expect(labels[gi + 1] == 'Crossfade' and PS.rows[gi + 1].action == P.ACT_XFADE == 215
           and PS.rows[gi + 1].arg == P.PSXFADE_PAGE_INDEX and P.PAGES[P.PSXFADE_PAGE_INDEX] is XF
           and P.row_kind(PS.rows[gi + 1]) == 'value' and P.VALUE_INIT[P.ACT_XFADE] == 'Off',
           'Playback Settings: Crossfade value row directly below Gapless opening m1plus_psxfade')
    expect([(r.label, r.action, r.arg) for r in XF.rows] == [('Crossfade', P.ACT_XFADESET, 0), ('Keep Albums Gapless', P.ACT_XFADEAUTO, 0)] and P.ACT_XFADESET == 216
           and P.ACT_XFADESET in P.SWITCH_ACTIONS and P.ACT_XFADESET not in P.CHECK_ACTIONS and {P.ACT_XFADESET, P.ACT_XFADEAUTO} <= set(P.NOGLYPH_ACTIONS),
           'm1plus_psxfade: the Crossfade switch and the Keep Albums Gapless switch (no glyphs)')
    kinds = [type(x).__name__ for x in XF.layout]
    expect(kinds == ['Row', 'Hdr', 'XfadeCard', 'Row', 'Note', 'Note'] and XF.layout[-1].lines == 4 and not getattr(XF.layout[0], 'start_hidden', 0) and all(x.start_hidden for x in XF.layout[1:]) and XF.layout[1].text == 'Crossfade Duration',
           'm1plus_psxfade: the switch card, then the header, the duration card, Keep Albums Gapless and the two notes (the second four lines), hidden until the switch is on')
    # Asset structure
    raw = os.path.join(WORK, 'rootfs/release/assets/default/raw/ui/m1plus_psxfade.bin')
    t = awtk_ui.parse(open(raw, 'rb').read())
    hid = lambda n: t.find(n).get('visible') == 'false' and t.find(n).get('sensitive') == 'false'
    sl = t.find('pod_xf_slider')
    expect(t.find('label_title').get('tr_text') == 'Crossfade' and t.find('pod_switch0') is not None and t.find('pod_switch1') is not None and t.find('pod_row0').find('pod_icon') is None
           and all(hid(n) for n in ('pod_sec0', 'pod_xfcard', 'pod_row1', 'pod_note0', 'pod_note1')) and not t.find('pod_row0').get('visible'),
           'm1plus_psxfade.bin: two switches with no icons; the header, card, Keep Albums Gapless and note start hidden and insensitive')
    expect(sl.get('min') == '1' and sl.get('max') == '12' and sl.get('step') == '1' and sl.get('bar_size') == '6' and sl.get('slide_with_bar') == 'true'
           and {v for k, v in sl.props if k.endswith(':icon')} == {'pod_sl_thumb'} and sl.get('style:normal:bg_image') == 'drop_bg' and sl.get('style:normal:fg_image') == 'drop_fg'
           and t.find('pod_xfcard').h == 96 + 20 and t.find('pod_xf_dots').get('image') == 'pod_xf_dots' and t.find('pod_xf_lo').get('tr_text') == '1 s' and t.find('pod_xf_hi').get('tr_text') == '12 s',
           'the duration card: the Display slider look, 1 .. 12 step 1, the end labels and the dots')
    # Settings Files entries
    expect('playback-crossfade' in P.SETTING_FILES and 'playback-crossfade-auto' in P.SETTING_FILES,
           'Settings Files lists playback-crossfade and playback-crossfade-auto')

    # Interactive UI test: open m1plus_psxfade, the card hidden while off, the switch shows it, the slider saves, the switch hides it again
    m = XM()
    nrows = 2
    m.widgets = {n: 0x30000000 + 0x100 * i for i, n in enumerate(
        ['btn_return', 'btn_backtoplayer', 'pod_sec0', 'pod_xfcard', 'pod_note0', 'pod_note1', 'pod_xf_slider', 'pod_xf_val']
        + [f'{k}{i}' for k in ('pod_row', 'pod_label', 'pod_switch') for i in range(nrows)])}
    row = m.alloc(12)
    m.setword(row, m.cstr('pod_row0')); m.setword(row + 4, P.ACT_PAGE); m.setword(row + 8, P.PSXFADE_PAGE_INDEX)
    m.call(PSYMS['on_row'], a0=row, count=6000000)
    names = ('pod_sec0', 'pod_xfcard', 'pod_row1', 'pod_note0', 'pod_note1')

    def shown(m_):
        return [([c[2] for c in m_.calls if c[0] == 'widget_set_visible' and c[1] == m_.widgets[n]][-1:], [c[2] for c in m_.calls if c[0] == 'widget_set_sensitive' and c[1] == m_.widgets[n]][-1:]) for n in names]
    def sw_img(m_, r_):
        return [c[2] for c in m_.calls if c[0] == 'image_base_set_image' and c[1] == m_.widgets[f'pod_switch{r_}']][-1]
    def text(m_):
        return [m_.read_cstr(c[2]) if isinstance(c[2], int) else c[2] for c in m_.calls if c[0] == 'widget_set_text_utf8' and c[1] == m_.widgets['pod_xf_val']][-1:]

    expect(shown(m) == [([0], [0])] * 5 and sw_img(m, 0) == 'sset_off' and sw_img(m, 1) == 'sset_on' and m.props.get((m.widgets['pod_xf_slider'], 'value')) == 5 and text(m) == ['5 seconds'],
           'm1plus_psxfade when off: the header, card, Keep Albums Gapless and note hidden and insensitive; the slider at 5, "5 seconds"')
    m.calls = []; m.click('pod_row0')
    expect(shown(m) == [([1], [1])] * 5 and sw_img(m, 0) == 'sset_on' and m.fs[SET_FILE] == b'e\n',
           'tap Crossfade: on, saved, the five items shown and sensitive')
    w = m.widgets['pod_xf_slider']
    fn, ctx = m.bound[(w, O['EVT_VALUE_CHANGING'])]
    m.calls = []; m.props[(w, 'value')] = 1; m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(m.fs[SET_FILE] == b'a\n' and text(m) == ['1 second'], 'the slider at 1: saved as "a", "1 second"')
    m.calls = []; m.props[(w, 'value')] = 12; m.call(fn, a0=ctx, a1=0, count=2000000)
    expect(m.fs[SET_FILE] == b'l\n' and text(m) == ['12 seconds'], 'the slider at 12: saved as "l", "12 seconds"')
    m.calls = []; m.click('pod_row1')   # toggle Keep Albums Gapless off
    expect(sw_img(m, 1) == 'sset_off' and m.fs[AUTO_FILE] == b'0\n', 'tap Keep Albums Gapless: switch flips to sset_off and saves 0')
    m.calls = []; m.click('pod_row0')   # back to off
    expect(shown(m) == [([0], [0])] * 5 and m.fs[SET_FILE] == b'L\n', 'tap Crossfade again: off, the duration kept ("L"), the five items hidden again')


# ---- 8. The sticky output format: the end-of-track cleanup's wrapper, the chain's rate request, the continuous conversion
def kept(p, eof=1, record=xfrec(5, 1), ao=(48000, 2, S16), b=(44100, 2, FLOAT), state=2, gapless=1, faded=0, flags=0xff7b, tail=0):
    """Run xf_uninit_player(0xff7a) the way hciplayer's end-of-track cleanup does; returns (mask passed on, sticky)."""
    p.files.pop(XFADE_FILE, None)
    if record is not None: p.files[XFADE_FILE] = record
    p.mpctx(); p.setword(p.mp_a + 0x14, eof); p.setword(p.mp_a + 8, 0x5000)
    p.setword(PLAYER_FLAGS, flags); p.setword(GAPLESS_SW, gapless); p.setword(NEXT_STATE, state)
    p.setword(AO_RATE, ao[0]); p.setword(AO_CH, ao[1]); p.setword(AO_FMT, ao[2])
    if state == 2 and p.sh_b:
        p.setword(p.sh_b + 0x3c, b[0]); p.setword(p.sh_b + 0x44, b[1]); p.setword(p.sh_b + 0x38, b[2])
    p.setword(NEXT_MPCTX + 8, 0)
    p.call(p.sym('xf_note_fade'), faded)
    if tail:   # Track A's filtered audio stock has not written yet (sh_audio->a_out_buffer), and a driver table to play it
        p.setword(p.mp_a + 8, ao_table(p))
    p.setword(p.sh_a + 0x78, 0x6000); p.setword(p.sh_a + 0x7c, tail)
    p.uninit_masks, p.ao_plays = [], []
    p.call(p.sym('xf_uninit_player'), 0xff7a)
    return p.uninit_masks[-1], p.call(p.sym('xf_sticky'))


def ao_table(p):
    ao = p.malloc(0x28)
    for off, fn in ((0x14, STOCK_AO_SPACE), (0x18, STOCK_AO_PLAY), (0x20, STOCK_AO_PAUSE), (0x24, STOCK_AO_RESUME)): p.setword(ao + off, fn)
    return ao


def sticky_tests(ctx):
    expect = ctx.expect
    R = 48000
    built = open(os.path.join(WORK, 'rootfs', mod_player.REL), 'rb').read()
    p = XP()
    p.setup_track_b(encode_pcm([0.0] * 64, S16), rate=R, nch=2, fmt=S16)
    j = mod_player.word(built, 0x4217d8)
    expect(j == 0x0c000000 | p.sym('xf_uninit_player') >> 2, 'the end-of-track cleanup call (0x4217d8) is now xf_uninit_player')
    m, st = kept(p, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff78 and st == 0 and p.word(NEXT_MPCTX + 8) == 0x5000,
           f'automatic change, Crossfade on, same format: the output bit dropped ({m:#x}), not sticky, next_mpctx carries audio_out')
    m, st = kept(p, record=xfrec(0, 1), ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a and st == 0 and p.word(NEXT_MPCTX + 8) == 0, f'Crossfade off: the mask is stock\'s ({m:#x})')
    m, st = kept(p, record=None, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a, 'no record: stock')
    m, st = kept(p, b=(44100, 2, S16))
    expect(m == 0xff7a and st == 0, 'a different rate, no fade and no sticky session: stock reopens at the native format')
    m, st = kept(p, b=(R, 1, S16))
    expect(m == 0xff7a, 'a different channel count, no fade: stock')
    m, st = kept(p, eof=4, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a, 'a skip (eof 4): stock, whatever the format')
    m, st = kept(p, eof=3, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a, 'a previous-entry change (eof 3): stock')
    m, st = kept(p, state=0, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a, 'no preloaded Track B (NEXT_STATE 0): stock')
    m, st = kept(p, gapless=0, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a, 'the gapless switch off (no swap follows): stock')
    m, st = kept(p, flags=0xff79, ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a, 'the output not initialized: the mask is passed on unchanged')
    xfout = lambda: struct.unpack('<ii', p.files[XFOUT_FILE]) if XFOUT_FILE in p.files else None
    expect(xfout() is None and 'wb' not in p.xfout_opens, 'no sticky session yet: the player has made no output-rate record (demo\'s info page)')
    m, st = kept(p, faded=1, b=(44100, 2, FLOAT))
    expect(m == 0xff78 and st == 1 and p.word(NEXT_MPCTX + 8) == 0x5000,
           'this transition crossfaded into another rate: the output stays open and the session is sticky')
    expect(xfout() == (0x314f4658, R), f'sticky: the record says the rate the output is kept at ({xfout()})')
    m, st = kept(p, faded=1, b=(44100, 2, FLOAT), tail=6200)
    expect(m == 0xff78 and p.ao_plays == [(0x6000, 6200, 1, 0)] and p.word(p.sh_a + 0x7c) == 0,
           f'the output kept: Track A\'s unwritten tail is played whole (final chunk) before uninit_player frees it ({p.ao_plays})')
    p.ao_short = [4096]
    m, st = kept(p, faded=1, b=(44100, 2, FLOAT), tail=6200)
    expect(p.ao_plays == [(0x6000, 6200, 1, 0), (0x6000 + 4096, 2104, 1, 0)] and p.word(p.sh_a + 0x7c) == 0,
           f'the driver took only part of the tail: the rest is played after it ({p.ao_plays})')
    p.ao_short = [0]
    m, st = kept(p, faded=1, b=(44100, 2, FLOAT), tail=6200)
    expect(m == 0xff78 and len(p.ao_plays) == 1 and p.word(p.sh_a + 0x7c) == 0, 'a driver that takes nothing: one try, no loop')
    p.ao_short = [1] * 20
    m, st = kept(p, faded=1, b=(44100, 2, FLOAT), tail=6200)
    expect(len(p.ao_plays) == 8, f'a driver that takes a byte at a time: the tries are bounded ({len(p.ao_plays)})')
    p.ao_short = []
    m, st = kept(p, record=xfrec(0, 1), b=(96000, 2, S16), tail=6200)
    expect(m == 0xff7a and p.ao_plays == [] and p.word(p.sh_a + 0x7c) == 6200, 'the output closing (stock): the tail is left to stock')
    # a join crossfade leaves gapless (same album) in a sticky session: the output and the conversion go on
    expect(kept(p, faded=1, b=(44100, 2, FLOAT)) == (0xff78, 1), 'sticky again')
    m, st = kept(p, record=xfrec(0, 1, keep=1), b=(44100, 2, FLOAT))
    expect(m == 0xff78 and st == 1 and p.word(NEXT_MPCTX + 8) == 0x5000,
           'sticky, a same-album join (no fade, the record says music): the output stays open, still sticky')
    m, st = kept(p, record=xfrec(0, 1, keep=0), b=(44100, 2, FLOAT))
    expect(m == 0xff7a, 'sticky, a join crossfade stays out of (a podcast, a stream, Crossfade off): stock reopens')
    p.call(p.sym('xf_ao_init'), 44100, 2, S16, 0)
    m, st = kept(p, record=xfrec(0, 1, keep=1), ao=(R, 2, S16), b=(R, 2, S16))
    expect(m == 0xff7a and st == 0, 'not sticky, a same-album join: stock\'s own gapless change, as without Crossfade')
    expect(kept(p, faded=1, b=(44100, 2, FLOAT)) == (0xff78, 1), 'sticky again')
    m, st = kept(p, record=xfrec(0, 1), faded=1, b=(96000, 2, S16))
    expect(m == 0xff78 and st == 1, 'a crossfade that overlapped keeps the output even when the record has gone to 0')
    m, st = kept(p, b=(96000, 2, S32))
    expect(m == 0xff78 and st == 1, 'a sticky session continues over a later change of rate and format without a fade')
    m, st = kept(p, record=xfrec(0, 1), b=(96000, 2, S32))
    expect(m == 0xff7a and st == 1, 'Crossfade turned off in a sticky session: the next change is stock (it reopens)')
    p.call(p.sym('xf_ao_init'), 44100, 2, S16, 0)
    expect(p.call(p.sym('xf_sticky')) == 0, 'any real reopen (ao init) is native again: not sticky')
    expect(xfout() == (0x314f4658, 0), 'and the output-rate record says 0')
    m, st = kept(p, ao=(R, 2, FLOAT), b=(R, 2, FLOAT))
    expect(m == 0xff78 and st == 0, 'sticky ends at the reopen: the same format keeps the output again, not sticky')
    # only what Track B's filter converts is kept in another format; DSD never keeps the output
    def b_codec(name): p.setword(p.word(p.sh_b + 4) + 0x3d0, p.cstr(name))
    expect(kept(p, faded=1, b=(44100, 2, FLOAT)) == (0xff78, 1), 'sticky again')
    expect(kept(p, b=(44100, 6, S16))[0] == 0xff7a, 'sticky, Track B has six channels (the filter does not convert it): stock')
    expect(kept(p, b=(705600, 2, S16))[0] == 0xff7a, 'sticky, a rate above 384 kHz: stock')
    expect(kept(p, b=(44100, 2, 0x100))[0] == 0xff7a, 'sticky, a special sample format: stock')
    b_codec('ffdsdlsbf')
    expect(kept(p, b=(44100, 2, S16))[0] == 0xff7a, 'sticky, Track B is DSD: stock')
    p.call(p.sym('xf_ao_init'), R, 2, S16, 0)
    expect(kept(p, ao=(R, 2, S16), b=(R, 2, S16))[0] == 0xff7a, 'the same format but DSD: stock (its output mode is not PCM\'s)')
    b_codec('ffflac')
    p.set_track_a(name='ffdsdmsbf')
    expect(kept(p, ao=(R, 2, S16), b=(R, 2, S16))[0] == 0xff7a, 'Track A is DSD: stock')
    p.set_track_a()
    expect(kept(p, ao=(R, 6, S16), b=(R, 6, S16)) == (0xff78, 0), 'six channels in the same format need no conversion: kept')
    # pause in a sticky session: what is queued plays out, and the resume reopens in the track's own format
    built_w = lambda a_: mod_player.word(built, a_)
    expect(built_w(0x88f188) == p.sym('xf_ao_pause') and built_w(0x88f18c) == p.sym('xf_ao_resume'), "ao_alsa's pause and resume slots are xf_ao_pause and xf_ao_resume")
    def paused(tail=0, space=(1000,)):
        p.setword(p.mp_a + 8, ao_table(p)); p.setword(p.sh_a + 0x78, 0x6000); p.setword(p.sh_a + 0x7c, tail)
        p.setword(PLAYER_FLAGS, 0xff7b); p.setword(AO_BUFFERSIZE, 1000)
        p.ao_events, p.ao_space = [], list(space)
        p.call(p.sym('xf_ao_pause')); ev = p.ao_events; p.ao_events = []
        p.call(p.sym('xf_ao_resume'))
        return ev, p.ao_events, p.call(p.sym('xf_sticky'))
    expect(paused(tail=800) == (['pause'], ['resume'], 0), 'not sticky: pause and resume are the driver\'s own')
    expect(kept(p, faded=1, b=(44100, 2, FLOAT)) == (0xff78, 1), 'sticky again')
    p.call(p.sym('xf_note_fade'), 1)
    expect(paused(tail=800) == (['pause'], ['resume'], 1), 'sticky, a crossfade running: pause and resume are the driver\'s own, still sticky')
    p.call(p.sym('xf_note_fade'), 0)
    ev, ev2, st = paused(tail=800, space=(200, 600, 1000))
    expect(ev == [('play', 800, 1), ('space', 200), 'sleep', ('space', 600), 'sleep', ('space', 1000), 'pause'],
           f'sticky: pause writes the tail, waits until the output has played everything, then pauses ({ev})')
    expect(ev2 == [('uninit', 2), 'reinit', 'resume'] and st == 0, f'the resume closes the output, rebuilds the chain and resumes: not sticky ({ev2}, {st})')
    expect(kept(p, faded=1, b=(44100, 2, FLOAT)) == (0xff78, 1), 'sticky again')
    ev, ev2, st = paused(space=(0,))
    expect(ev.count('sleep') == 100 and ev[-1] == 'pause' and ev2 == [('uninit', 2), 'reinit', 'resume'], f'an output that never empties: the wait is bounded ({ev.count("sleep")} sleeps)')
    expect(kept(p, faded=1, b=(44100, 2, FLOAT)) == (0xff78, 1), 'sticky again')
    p.ao_events, p.ao_space = [], [1000]; p.setword(p.mp_a + 8, ao_table(p)); p.setword(PLAYER_FLAGS, 0xff7b)
    p.call(p.sym('xf_ao_pause')); p.call(p.sym('xf_ao_init'), 44100, 2, S16, 0); p.ao_events = []
    p.call(p.sym('xf_ao_resume'))
    expect(p.ao_events == ['resume'], 'the output reopened while paused (a skip): the resume is the driver\'s own')


def rate_tests(ctx):
    expect = ctx.expect
    R = 48000

    def sticky(p):
        p.setup_track_b(encode_pcm([0.0] * 64, FLOAT), rate=44100, nch=2, fmt=FLOAT)
        return kept(p, faded=1, ao=(R, 2, S16), b=(44100, 2, FLOAT))

    def rate_ptr(p, v):
        a = p.malloc(4); p.setword(a, v); return a

    p = XP()
    af = p.start(44100)
    expect(p.ctl(af, RATE_SET, rate_ptr(p, R)) == -1, 'not sticky: the rate request is declined (stock inserts its resampler)')
    expect(sticky(p) == (0xff78, 1), 'the session is sticky')
    expect(p.ctl(af, RATE_SET, rate_ptr(p, 44100)) == -1, 'the request for the rate that arrives is declined')
    expect(p.ctl(af, RATE_SET, 0) == -1, 'no argument: declined')
    r = p.ctl(af, RATE_SET, rate_ptr(p, R))
    expect(r == 1, 'sticky and a different rate: AF_OK takes the request')
    r, _, data = p.reinit(af, 44100)
    mul = struct.unpack('<d', bytes(p.u.mem_read(af + 40, 8)))[0]
    expect(r == 1 and data[2:] == (R, 2, FLOAT, 4) and abs(mul - R / 44100) < 1e-12,
           f'after the request the instance reports the output rate ({data[2]}) and mul {mul:.6f}')
    # the filter chain then sends the output rate to the stages: a 1 kHz tone through the converter arrives at 48 kHz pitch
    tone = PEQ.f32([0.3 * math.sin(2 * math.pi * 1000 * i / 44100) for i in range(2048) for _ in (0, 1)])
    other, orate, y = p.play_out(af, tone, 44100)
    n = len(y) // 2
    expect(other and orate == R and abs(n - 2048 * R / 44100) <= 40, f'play returns its own buffer at {orate} Hz with {n} frames (about {2048 * R // 44100})')
    err = max(abs(y[2 * k] - 0.3 * math.sin(2 * math.pi * 1000 * k / R)) for k in range(20, n - 20))
    expect(err < 0.01, f'the converted tone is the 1 kHz tone at 48 kHz (max err {err:.4f}; the model interpolates linearly)')
    # af_format after this filter rewrites the af_data it is handed (this instance's own) to its S32 output: the next
    # block must say float again, or the floats would pass on as integers (device: static after the swap)
    out = p.word(af + 20)
    p.u.mem_write(out + 8, struct.pack('<iiii', 44100, 1, S16, 2))
    p.play_out(af, tone, 44100)
    fields = struct.unpack('<iiii', bytes(p.u.mem_read(out + 8, 16)))
    expect(fields == (R, 2, FLOAT, 4), f'every block restates the output format after a later filter rewrote it ({fields})')
    # a mono input and more than two channels
    p = XP(); sticky(p)
    af = p.start(44100, nch=3)
    expect(p.ctl(af, RATE_SET, rate_ptr(p, R)) == -1, 'three channels: declined (stock converts)')
    af = p.start(44100, nch=1)
    expect(p.ctl(af, RATE_SET, rate_ptr(p, R)) == 1, 'mono: accepted')
    # the kill switch, a rate out of range and DSD pass through, whatever the chain asks
    p = XP({KILL: b''}); sticky(p)
    af = p.start(44100)
    expect(p.ctl(af, RATE_SET, rate_ptr(p, R)) == -1, 'the kill switch: declined')
    # Equalizer off, no stereo option: the filter passes the native format through, but a conversion needs float
    p = XP(); sticky(p)
    p.flag('0')
    af = p.open()
    r, asked, data = p.reinit(af, 44100, fmt=S16, bps=2)
    # the chain is built at the track's own rate (xf_reinit_chain), so the kept output's rate comes from ao_data, unasked
    expect(r == 0 and asked[2:] == (44100, 2, FLOAT, 4) and data[2] == R,
           f'EQ off but the kept output is {R} Hz: float is asked at the rate that arrives ({asked[2]} Hz), the output is {data[2]} Hz')
    expect(p.ctl(af, RATE_SET, rate_ptr(p, R)) == 1, 'EQ off but sticky: the request is accepted too')
    p.setword(0xafa1a0, 44100)
    r, _, data = p.reinit(af, 44100, fmt=S16, bps=2)
    expect(data[2] == R, f'an accepted request still sets the output rate ({data[2]} Hz)')
    # the session ends (pause reopens the output at the track's own format): the request goes with it
    p.call(p.sym('xf_ao_init'), 44100, 2, S16, 0)
    r, _, data = p.reinit(af, 44100, fmt=S16, bps=2)
    expect(data[2] == 44100, f'sticky over: the same instance reports the track\'s own rate again ({data[2]} Hz), no conversion left behind')
    p.setword(0xafa1a0, R)


def handoff_tests(ctx):
    expect = ctx.expect
    R, RB, N = 48000, 44100, 1000
    sine = lambda n, rate, f=997.0: [0.5 * math.sin(2 * math.pi * f * i / rate) for i in range(n)]
    ref = lambda b, n: py_resample([(v, v) for v in b], RB, R, n)

    # (1) A crossfade into another rate: the converter that mixed Track B goes whole into Track B's instance
    b_sig = sine(int(RB * 1.6), RB)
    b_flat = [v for x in b_sig for v in (x, x)]
    p = XP({XFADE_FILE: xfrec(1, 1)})
    p.set_track_a(pos=59.0, total=60.0, obps=R * 4)
    abuf = p.setup_track_b(encode_pcm(b_flat, FLOAT), rate=RB, nch=2, fmt=FLOAT, buf_size=65536)
    af1 = p.start(R)
    out = []
    for _ in range(50):
        _, y = p.play(af1, [0.0] * (2 * N), R)
        out += y[0::2]
    expect(p.word(p.ds_a + 0x1c) == 1, 'the fade ran its length: Track A is ended (force_eof)')
    handles = {e[1] for e in p.swr_log if e[0] == 'new'}
    expect(len(handles) == 1 and ('free', next(iter(handles))) not in p.swr_log, 'one converter made for the overlap')
    h = next(iter(handles))
    expect(kept(p, faded=1, ao=(R, 2, S16), b=(RB, 2, FLOAT)) == (0xff78, 1), 'the cleanup keeps the output, sticky')
    p.uninit(af1)
    expect(('free', h) not in p.swr_log, 'Track A\'s instance ends: the converter was handed on, not freed')
    # what stock plays next: the bytes left in next_sh->a_buffer, then the rest of Track B's decode
    left = bytes(p.u.mem_read(abuf, p.word(p.sh_b + 0x6c))) + p.b_stream[p.b_stream_pos:]
    rest = decode_pcm(left, FLOAT)
    p.setword(NEXT_STATE, 0); p.set_track_a(pos=0.5, total=120.0, obps=RB * 4)
    af2 = p.open(); p.reinit(af2, RB)
    expect(p.ctl(af2, RATE_SET, p.malloc(4)) == -1, 'a request for rate 0 is declined')
    q = p.malloc(4); p.setword(q, R)
    expect(p.ctl(af2, RATE_SET, q) == 1, 'Track B\'s chain asks for the output rate and the instance takes it')
    p.reinit(af2, RB)
    seam = len(out)
    for i in range(0, 20000, 2 * 1024):
        _, orate, y = p.play_out(af2, rest[i:i + 2048], RB)
        out += y[0::2]
    expect(orate == R and len({e[1] for e in p.swr_log if e[0] == 'convert'}) == 1, 'Track B\'s instance converts with the same context')
    want = [v[0] for v in ref(b_sig, len(out))]
    gb = [math.sin(0.5 * math.pi * min(k, 48000) / 48000) for k in range(len(out))]
    err = max(abs(out[k] - gb[k] * want[k]) for k in range(len(out) - 8))
    expect(err < 2e-5, f'the stream is one continuous conversion of Track B through the overlap and the swap (max err {err:.2e})')
    jump = max(abs(out[k + 1] - out[k]) for k in range(seam - 4, seam + 4))
    top = max(abs(out[k + 1] - out[k]) for k in range(seam + 100, seam + 2000))
    expect(jump < 1.05 * top, f'no discontinuity at the swap (largest step {jump:.4f}, a sine\'s own {top:.4f})')
    p.uninit(af2)
    expect(('free', h) in p.swr_log, 'the converter is freed when Track B\'s instance ends (not carried: the track was not ended)')

    # (2) A gapless change between two tracks of one input format, no fade: the same converter, no flush or padding
    c_sig = sine(RB, RB, 441.0)
    p = XP()
    sticky_ptr = p.malloc(4); p.setword(sticky_ptr, R)
    p.setup_track_b(encode_pcm([0.0] * 64, FLOAT), rate=RB, nch=2, fmt=FLOAT)
    kept(p, faded=1, ao=(R, 2, S16), b=(RB, 2, FLOAT))
    af1 = p.open(); p.reinit(af1, RB); p.ctl(af1, RATE_SET, sticky_ptr); p.reinit(af1, RB)
    flat = [v for x in c_sig for v in (x, x)]
    out = []
    half = 20000
    for i in range(0, half, 1000):
        _, _, y = p.play_out(af1, flat[2 * i:2 * i + 2000], RB)
        out += y[0::2]
    p.ended(1); p.uninit(af1)
    handles = {e[1] for e in p.swr_log if e[0] == 'new'}
    af2 = p.open(); p.reinit(af2, RB); p.ctl(af2, RATE_SET, sticky_ptr); p.reinit(af2, RB)
    seam = len(out)
    for i in range(half, 40000, 1000):
        _, _, y = p.play_out(af2, flat[2 * i:2 * i + 2000], RB)
        out += y[0::2]
    expect(len(handles) == 1 and len({e[1] for e in p.swr_log if e[0] == 'convert'}) == 1,
           'the next track with the same input format goes on in the same converter')
    want = [v[0] for v in py_resample([(v, v) for v in c_sig], RB, R, len(out))]
    err = max(abs(a - b) for a, b in zip(out[:-8], want))
    expect(err < 2e-5 and len(out) > 40000 * R // RB - 40, f'no gap, no padding across the gapless change (max err {err:.2e}, {len(out)} frames)')
    # a different input rate: a new converter
    af3 = None
    p.ended(1); p.uninit(af2)
    p.setword(sticky_ptr, R)
    af3 = p.open(); p.reinit(af3, 96000); p.ctl(af3, RATE_SET, sticky_ptr); p.reinit(af3, 96000)
    p.play_out(af3, [0.1] * 4000, 96000)
    new = [e for e in p.swr_log if e[0] == 'new']
    expect(len(new) == 2 and new[-1][2] == 96000 and ('free', new[0][1]) in p.swr_log,
           'another input rate makes a new converter; the old one is freed')
    p.ended(0); p.uninit(af3)
    expect(len([e for e in p.swr_log if e[0] == 'free']) == 2 and not p.swr, 'every converter made is freed')


# ---- 8. the handoff through stock's own code: mclAutoChange, mclNextSong(1) and the getters run for real
MCL_STATUS, MCL_POS, MCL_MODE = 0xa0abe4, 0xa0abdc, 0xa0abe0   # the words mclGetPlayStatus (0x5d3640), mclGetPlayPos (0x5d4290) and mclGetPlayMode (0x5d3628) return
MCL_ASK_STATUS = 0x5d0918   # mclAutoChange's {player-status\request} round trip (@0x5d6430): nonzero while hciplayer answers "playing"
STOCK_STUBS = {0x741fb0: 'pthread_mutex_lock', 0x743460: 'pthread_mutex_unlock', 0x743590: 'deque_size', 0x742c70: 'deque_at'}   # libc and libcstl as demo's GOT has them


class StockAuto(Machine):
    """Stock's end-of-track step run for real. Only its leaves are answered here: the status request ("playing"), the preload (the harness's mock, plus the index stock stores),
    mclStartPlayer (recorded: the path that mutes the DAC) and the lyric load."""

    def __init__(self, gapless, tracks=3):
        super().__init__()
        for n in ('mclAutoChange', 'mclGetPlayTime', 'mclGetPlayPos', 'mclGetPlayStatus', 'mclGetPlayType', 'mclGetPlayMode'): self.handlers.pop(pod.FUNCTIONS[n][2])
        self.handlers.update(STOCK_STUBS)
        self.handlers[MCL_ASK_STATUS] = 'ask_status'
        self.handlers[pod.START_PLAYER] = 'mclStartPlayer'
        self.fs[SET_FILE], self.fs[AUTO_FILE] = b'h\n', b'0\n'   # on, 8 s, Always
        self.setword(pod.DATA['PLAY_QUEUE'][0], self.new_deque([self.record(album=f'Album {i}', path=f'/mnt/mmc/{i}.flac') for i in range(tracks)]))
        self.setword(MCL_MODE, 0)
        self.set(pos=0, status=2, running=1, gapless=gapless, preload=0, time=(0, 200))

    def set(self, pos=None, status=None, running=None, gapless=None, preload=None, time=None):
        if pos is not None: self.setword(MCL_POS, pos)
        if status is not None: self.setword(MCL_STATUS, status)
        if running is not None: self.u.mem_write(pod.DATA['HCI_RUNNING'][0], bytes([running]))
        if gapless is not None: self.u.mem_write(pod.DATA['MCL_GAPLESS'][0], bytes([gapless]))
        if preload is not None: self.setword(pod.DATA['MCL_PRELOAD'][0], preload)
        if time is not None: self.setword(pod.DATA['MCL_PLAYINFO'][0] + 12, time[0]); self.setword(pod.DATA['MCL_PLAYINFO'][0] + 8, time[1])

    def got(self):
        """(position, running, preload state, Gapless byte, (cur, total)) as stock's words have them."""
        info = pod.DATA['MCL_PLAYINFO'][0]
        return (self.s32(MCL_POS), self.u.mem_read(pod.DATA['HCI_RUNNING'][0], 1)[0], self.s32(pod.DATA['MCL_PRELOAD'][0]), self.u.mem_read(pod.DATA['MCL_GAPLESS'][0], 1)[0],
                (self.s32(info + 12), self.s32(info + 8)))

    def _hook(self, u, address, size, d):
        name = self.handlers.get(address)
        if name in ('ask_status', 'mclStartPlayer', 'mclLoadExLyric'):
            self.calls.append((name,))
            u.reg_write(UC_MIPS_REG_V0, 1); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))
            return
        if name == 'mcl_gapless_preload': self.setword(pod.DATA['MCL_PRELOAD_NEXT'][0], self.s32(MCL_POS) + 1)   # the index stock's decision stores in List play (mclNextSong(1) moves the position there)
        return super()._hook(u, address, size, d)


def stock_tests(ctx):
    expect = ctx.expect
    AUTO = pod.FUNCTIONS['mclAutoChange'][2]
    # The stock behaviour the handoff has to work around: mclAutoChange tests the ended track's time (its stack copy) after mclNextSong(1) has moved on
    m = StockAuto(1); m.set(running=0, preload=1, time=(198, 200)); m.setword(pod.DATA['MCL_PRELOAD_NEXT'][0], 1)
    m.call(AUTO, count=4000000)
    expect(m.got() == (1, 1, 1, 1, (0, 0)) and ('mcl_gapless_preload', 1) in m.calls and 'mclStartPlayer' not in m.names(),
           'stock alone, a track ended 2 s short of its total: the handoff, then at once a preload of the track after (its time test reads the ended track\'s)')
    m = StockAuto(1); m.set(running=0, preload=1, time=(200, 200)); m.setword(pod.DATA['MCL_PRELOAD_NEXT'][0], 1)
    m.call(AUTO, count=4000000)
    expect(m.got() == (1, 1, 0, 1, (0, 0)) and 'mcl_gapless_preload' not in m.names(), 'stock alone, ended at its total: the handoff and no preload')
    # Through xfade_auto_change, three tracks, the Gapless setting off and on: each join is preloaded once, with its own record, and handed off; mclStartPlayer never runs
    for g in (0, 1):
        m = StockAuto(g); seqs = []
        for pos in (0, 1):
            m.set(time=(20, 200)); m.clock += 1000
            call_c(m, 'xfade_auto_change')
            expect(m.got()[:4] == (pos, 1, 0, g) and 'mcl_gapless_preload' not in m.names(), f'Gapless {g}, track {pos} far from its end: no preload')
            m.set(time=(188, 200)); m.clock += 1000
            call_c(m, 'xfade_auto_change')
            seqs.append(read_rt(m)[2])
            expect(m.got()[:4] == (pos, 1, 1, g) and ('mcl_gapless_preload', 1) in m.calls and read_rt(m)[1] == 8 and read_rt(m)[3] == 1,
                   f'Gapless {g}, track {pos} 12 s from its end: the record (8 s) is written and the next track preloaded; the Gapless byte is the user\'s again')
            m.set(running=0, time=(198, 200))   # the faded end: the last time hciplayer reported is short of the total
            call_c(m, 'xfade_auto_change')
            expect(m.got() == (pos + 1, 1, 0, g, (0, 0)) and not {'mcl_gapless_preload', 'mclStartPlayer'} & set(m.names()),
                   f'Gapless {g}, track {pos} ended: stock hands off to track {pos + 1}, with no preload of the one after and no mclStartPlayer')
        expect(seqs[1] > seqs[0], f'Gapless {g}: the second join has a record of its own')
    # A preload open at the end with the Gapless setting off and nothing remembered here (a fresh state): still the handoff
    m = StockAuto(0); m.set(running=0, preload=1, time=(198, 200)); m.setword(pod.DATA['MCL_PRELOAD_NEXT'][0], 1)
    call_c(m, 'xfade_auto_change')
    expect(m.got() == (1, 1, 0, 0, (0, 0)) and not {'mcl_gapless_preload', 'mclStartPlayer'} & set(m.names()),
           'an open preload at a track\'s end is handed off whether or not this file opened it: never mclStartPlayer under a playing hciplayer')
    # Stopped: stock returns at once, and the time is left alone
    m = StockAuto(0); m.set(running=0, preload=1, status=1, time=(198, 200))
    call_c(m, 'xfade_auto_change')
    expect(m.got() == (0, 0, 1, 0, (198, 200)), 'stopped with a preload open: nothing moves, the play time stands')


SECTIONS = [pin_tests, rec_tests, mix_tests, resample_tests, native_tests, flac_seek_tests, edge_tests, sticky_tests, rate_tests, handoff_tests, demo_tests, stock_tests, ui_tests]
