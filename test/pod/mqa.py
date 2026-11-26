"""Non-MQA probe skip in hciplayer (tools/mod_player.py, docs/modules/mqa.md): pins, refusals, manifest,
and Unicorn MIPS execution of stock vs patched mqa_probe (0x42e428) across MQA, non-MQA, unaligned,
error and non-qualifying inputs."""
import json
import os
import struct
from unicorn import UC_ARCH_MIPS, UC_HOOK_CODE, UC_MODE_LITTLE_ENDIAN, UC_MODE_MIPS32, Uc
from unicorn.mips_const import (
    UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
    UC_MIPS_REG_PC, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_T9, UC_MIPS_REG_V0,
)
from harness import *   # noqa: F401,F403
import mod_player
import paths
import pod

MQA_PROBE = 0x42e428
DET_ALLOC = 0x72f300
DET_FREE = 0x72f360
DET_CHECK = 0x72f380
DECODE_AUDIO = 0x47f0ac
DET_HANDLE = 0x40010000
SH_AUDIO = 0x40020000
OUT_BUF = 0x40030000


class ProbeRunner:
    """LOAD segments of stock or patched hciplayer with mqa_probe's four callees trapped."""
    RET, STACK, HEAP = 0x00ff0000, 0x7ffe0000, 0x40000000

    def __init__(self, image):
        self.u = u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        for _, (t, o, v, _, f, m, _, _) in pod.segments(image):
            if t != 1: continue
            start = v & ~0xfff
            u.mem_map(start, ((v + m + 0xfff) & ~0xfff) - start)
            u.mem_write(v, image[o:o + f])
        u.mem_map(self.STACK & ~0xfffff, 0x200000)
        u.mem_map(self.HEAP, 0x100000)
        self.calls = []
        self.alloc_ret = DET_HANDLE
        self.decode_ret = 1
        self.decoded_len = 0xc00
        self.detect_ret = 0
        for addr in (DET_ALLOC, DET_FREE, DET_CHECK, DECODE_AUDIO):
            u.hook_add(UC_HOOK_CODE, self._hook, begin=addr, end=addr)

    def _hook(self, u, address, size, _):
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        ret = 0
        if address == DET_ALLOC:
            self.calls.append(('alloc', a0, a1))
            ret = self.alloc_ret
        elif address == DECODE_AUDIO:
            self.calls.append(('decode', a0, a1))
            ret = self.decode_ret
            if ret > 0:
                u.mem_write(SH_AUDIO + 0x68, struct.pack('<II', OUT_BUF, self.decoded_len))
        elif address == DET_CHECK:
            self.calls.append(('detect', a0, a1, a2))
            ret = self.detect_ret
        elif address == DET_FREE:
            self.calls.append(('free', a0))
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff)
        u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))

    def probe(self, *, ch=2, rate=44100, bits=16, codec=11, probe_bytes=0xc00,
              alloc_ret=DET_HANDLE, decode_ret=1, decoded_len=0xc00, detect_ret=0):
        u = self.u
        self.calls = []
        self.alloc_ret, self.decode_ret, self.decoded_len, self.detect_ret = alloc_ret, decode_ret, decoded_len, detect_ret
        u.mem_write(SH_AUDIO, bytes(0x80))
        sp = self.STACK - 0x40
        u.mem_write(sp + 0x10, struct.pack('<III', bits, codec, probe_bytes))
        u.reg_write(UC_MIPS_REG_SP, sp)
        u.reg_write(UC_MIPS_REG_RA, self.RET)
        u.reg_write(UC_MIPS_REG_T9, MQA_PROBE)
        u.reg_write(UC_MIPS_REG_A0, SH_AUDIO)
        u.reg_write(UC_MIPS_REG_A1, ch)
        u.reg_write(UC_MIPS_REG_A2, rate)
        u.reg_write(UC_MIPS_REG_A3, bits)
        u.emu_start(MQA_PROBE, self.RET, count=10000)
        v0 = u.reg_read(UC_MIPS_REG_V0)
        return v0 - 0x100000000 if v0 >= 0x80000000 else v0


def run(ctx):
    expect = ctx.expect
    stock = open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', mod_player.REL), 'rb').read()
    built = open(os.path.join(WORK, 'rootfs', mod_player.REL), 'rb').read()
    w = mod_player.word

    # ---- pins, bytes and manifest ----
    expect(mod_player.MQA_PROBE_RET == ((0x42e548, 0x24020001, 0x24020000), (0x42e564, 0x24020001, 0x24020000)),
           'MQA_PROBE_RET targets the two non-MQA return immediates (addiu $v0, $zero, 1 -> 0)')
    expect(all(w(stock, a) == old and w(built, a) == new for a, old, new in mod_player.MQA_PROBE_RET),
           'both non-MQA return words are patched in built hciplayer')
    manifest = json.load(open(os.path.join(WORK, 'playerbuild', 'manifest.json')))
    expect(manifest['mqa_probe_ret'] == [[a, old, new] for a, old, new in mod_player.MQA_PROBE_RET],
           'manifest records both MQA probe edits')

    # ---- refusals on mutated stock words ----
    for at, what in ((0x42e548, 'unaligned return'), (0x42e564, 'non-MQA return'),
                     (0x42e570, 'real MQA movz'), (0x42e940, 'reinit blez gate'), (0x42efbc, 'mqa_mode store')):
        bad = bytearray(stock)
        off = pod.fileoff(stock, at)
        struct.pack_into('<I', bad, off, w(stock, at) ^ 1)
        keep = mod_player.PLAYER_SHA
        mod_player.PLAYER_SHA = pod.sha(bytes(bad))
        try:
            mod_player.check_stock(bytes(bad)); refused = False
        except ValueError:
            refused = True
        finally:
            mod_player.PLAYER_SHA = keep
        expect(refused, f'check_stock refuses a mutated {what} ({at:#x})')

    # ---- Unicorn execution: stock vs patched mqa_probe ----
    s_run, p_run = ProbeRunner(stock), ProbeRunner(built)

    # Ordinary FLAC/PCM (non-MQA): stock returns 1 (shadow MQA decoder); patched returns 0 (skip decoder).
    for codec in (11, 13):
        for bits in (16, 24):
            for rate in (44100, 48000, 88200, 96000, 176400, 192000):
                sr = s_run.probe(codec=codec, bits=bits, rate=rate, detect_ret=0)
                pr = p_run.probe(codec=codec, bits=bits, rate=rate, detect_ret=0)
                expect(sr == 1 and pr == 0,
                       f'non-MQA codec {codec} {bits}b/{rate}Hz: stock={sr} (want 1), patched={pr} (want 0)')
    expect([c[0] for c in p_run.calls] == ['alloc', 'decode', 'detect', 'free'] and p_run.calls[-1] == ('free', DET_HANDLE),
           'non-MQA probe still frees the detector handle cleanly')

    # Real MQA detected at track start: both stock and patched return 2.
    for codec in (11, 13):
        for bits in (16, 24):
            for rate in (44100, 48000, 88200, 96000, 176400, 192000):
                sr = s_run.probe(codec=codec, bits=bits, rate=rate, detect_ret=1)
                pr = p_run.probe(codec=codec, bits=bits, rate=rate, detect_ret=1)
                expect(sr == 2 and pr == 2,
                       f'real MQA codec {codec} {bits}b/{rate}Hz: stock={sr}, patched={pr} (both want 2)')
    expect([c[0] for c in p_run.calls] == ['alloc', 'decode', 'detect', 'free'],
           'real MQA probe allocates, decodes, detects and frees')

    # Short or frame-unaligned initial read (0x42e548 path): stock returns 1, patched returns 0.
    for bits, bad_len in ((16, 0), (16, 3), (24, 4)):
        sr = s_run.probe(bits=bits, decoded_len=bad_len)
        pr = p_run.probe(bits=bits, decoded_len=bad_len)
        expect(sr == 1 and pr == 0 and [c[0] for c in p_run.calls] == ['alloc', 'decode', 'free'],
               f'unaligned/short read ({bits}b, {bad_len}B): stock={sr}, patched={pr}, detector freed without detect')

    # Decode failure (0x42e578) and alloc failure (0x42e4e0): unchanged from stock.
    expect(s_run.probe(decode_ret=0) == -1 and p_run.probe(decode_ret=0) == -1, 'decode failure still returns -1')
    expect(s_run.probe(alloc_ret=0) == 0 and p_run.probe(alloc_ret=0) == 0, 'detector alloc failure still returns 0')

    # Non-qualifying streams (other codec, mono, 8/32-bit, unsupported rate): both return 0 without allocating.
    for kw in ({'codec': 5}, {'ch': 1}, {'bits': 8}, {'bits': 32}, {'rate': 32000}, {'rate': 384000}):
        sr, pr = s_run.probe(**kw), p_run.probe(**kw)
        expect(sr == 0 and pr == 0 and not p_run.calls, f'non-qualifying {kw}: both return 0 without probing')
