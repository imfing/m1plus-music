#!/usr/bin/env python3
"""Generated playlist covers (docs/modules/plcover.md): five styles drawn in colours taken from the playlist's albums, integers only. The device code is
patch/plcover.c (plc_art mirrors this file line by line; patch/offsets.inc carries the PLC_* numbers, test/pod/plcover.py asserts it and runs the compiled code
against this file pixel for pixel), tools/preview/preview_plcover.py draws the styles.

The art is a pure function of (style, tones, seed, side): a side x side RGB image at RGB565 precision, the Daily Mix's dither (tools/pod_dailymix.py).
Style 0 (Albums) is the 2x2 mosaic the grid composes; the generator never draws it. The corners are the caller's.
"""
import argparse, math
import pod_dailymix as D

ALBUMS, SOLID, MESH, SUNBURST, STRIPES, BAND = range(6)
NAMES = ('Albums', 'Solid', 'Mesh', 'Sunburst', 'Stripes', 'Band')
GREY = 0x787878                  # the tone of a playlist without a cover tone (0xAABBGGRR; a grey)
PLC_MAX = 320                    # the largest side
PLC_K = 41                       # K, the dark end of the ramp: A * 41 / 256 (16 %)
PLC_L = 179                      # L, the light end: A mixed 179 / 256 (70 %) toward white
PLC_SOLID_TOP, PLC_SOLID_BOT = 287, 210      # Solid: A * 1.12 at the top to A * 0.82 at the bottom (/ 256)
PLC_STRIPE_LO, PLC_STRIPE_SPAN = 31, 199     # Stripes: the ramp position 0.12 + 0.78 * smoothstep (/ 256)
STRIPE_LEVELS = (128, 92, 154, 113, 77)      # each of the 5 columns' step height (0.50 0.36 0.60 0.44 0.30 of the height, / 256)
PLC_BAND_Y, PLC_BAND_R2 = 154, 4424          # Band: the light band's centre (0.6 of the height) and its (1 - d^2 / R^2)^2 reach: R^2 = 3 * (0.15 * 256)^2
PLC_BAND_MIX = 243                           # ... its weight toward L (0.95)
PLC_BAND_T0, PLC_BAND_TS = 38, 90            # ... the ramp behind it: position 0.15 + 0.35 v
PLC_SUN_X, PLC_SUN_Y = 14, 22                # Sunburst: the apex at (0.7, 1.1) of the side, in tenths of the doubled side (half pixels)
PLC_SUN_RAYS = 7                             # ... rays per turn
PLC_SUN_T0, PLC_SUN_RAY, PLC_SUN_FADE, PLC_SUN_GLOW = 31, 179, 115, 46   # ... ramp position 0.12 + 0.70 rays (1 - 0.45 far) + 0.18 glow (/ 256)
PLC_SUN_FAR, PLC_SUN_NEAR = 20, 8           # ... the far fade's and the glow's reach, in tenths of the side (radius R: R^2 in half pixels)


def sm(t):
    """Smoothstep of t in 0..256 -> 0..256."""
    return t * t * (768 - 2 * t) >> 16


def mix(a, b, t):
    """a to b by t / 256, per channel."""
    return tuple(x + ((y - x) * t >> 8) for x, y in zip(a, b))


class Pal:
    """A: the first tone as a Daily Mix tone (tone_prep); K: A at 16 % (a tinted near-black); L: A 70 % toward white; ramp[0..256] runs K, A, L with smoothsteps."""
    def __init__(self, tones):
        self.A = D.tone_prep(tones[0] if tones else (GREY & 255, GREY >> 8 & 255, GREY >> 16 & 255))
        self.K = tuple(c * PLC_K >> 8 for c in self.A)
        self.L = mix(self.A, (255, 255, 255), PLC_L)
        self.ramp = [mix(self.K, self.A, sm(2 * i)) if i < 128 else mix(self.A, self.L, sm(2 * i - 256)) for i in range(257)]


def centres(side):
    """(2 x + 1) * 256 / (2 side) for every x: the position of a pixel centre in 1/256 of the side."""
    return [(2 * x + 1) * 256 // (2 * side) for x in range(side)]


def solid(p, side):
    return [[mix(tuple(min(255, c * PLC_SOLID_TOP >> 8) for c in p.A), tuple(c * PLC_SOLID_BOT >> 8 for c in p.A), v)] * side for v in centres(side)]


def band(p, side):
    rows = []
    for v in centres(side):
        d2 = (v - PLC_BAND_Y) ** 2
        g = 0
        if d2 < PLC_BAND_R2:
            q = 256 - 256 * d2 // PLC_BAND_R2
            g = (q * q >> 8) * PLC_BAND_MIX >> 8
        rows.append([mix(p.ramp[PLC_BAND_T0 + (PLC_BAND_TS * v >> 8)], p.L, g)] * side)
    return rows


def stripes(p, side):
    edge = [(i * side + 4) // 5 for i in range(6)]     # column i holds x * 5 // side == i
    rows = []
    for v in centres(side):
        row = []
        for i in range(5):
            t = min(256, max(0, v - STRIPE_LEVELS[i] + 128))
            row += [p.ramp[PLC_STRIPE_LO + (PLC_STRIPE_SPAN * sm(t) >> 8)]] * (edge[i + 1] - edge[i])
        rows.append(row)
    return rows


# the angle in 65536ths of a turn: atan of 0..1 in 64 steps (interpolated; one more entry pads the last), and the sunburst's rays 0.5 + 0.5 cos (a full turn of rays in 256 steps, / 256)
ATAN = [round(math.atan(i / 64) / (2 * math.pi) * 65536) for i in range(66)]
RAYS = [round(256 * (0.5 + 0.5 * math.cos(2 * math.pi * i / 256))) for i in range(256)]


def atan2(y, x, rec):
    """The angle of (x, y) in 65536ths of a turn from the +x axis, counter-clockwise with y down being positive (an octant and a 64 step table, no division:
    rec[m] = 2^22 // m)."""
    ax, ay = abs(x), abs(y)
    if ax == 0 and ay == 0: return 0
    hi, lo = max(ax, ay), min(ax, ay)
    q = lo * rec[hi] >> 10                       # lo / hi in 1/4096
    a = ATAN[q >> 6] + ((ATAN[(q >> 6) + 1] - ATAN[q >> 6]) * (q & 63) >> 6)
    if ay > ax: a = 16384 - a                    # the angle from the x axis in the first quadrant
    if x >= 0: return a if y >= 0 else 65536 - a
    return 32768 - a if y >= 0 else 32768 + a


def sunburst(p, side):
    cx, cy = PLC_SUN_X * side // 10, PLC_SUN_Y * side // 10     # the apex in half pixels
    r1, r2 = (PLC_SUN_FAR * side // 10) ** 2, (PLC_SUN_NEAR * side // 10) ** 2
    i1, i2 = (256 << 20) // r1, (256 << 20) // r2
    top = max(abs(cx), abs(cx - 2 * side), abs(cy), abs(cy - 2 * side)) + 1
    rec = [0] + [(1 << 22) // m for m in range(1, top + 1)]
    rows = []
    for y in range(side):
        Y = 2 * y + 1 - cy; row = []
        for x in range(side):
            X = 2 * x + 1 - cx
            d2 = X * X + Y * Y
            far = min(256, d2 * i1 >> 20); near = min(256, d2 * i2 >> 20)
            ray = RAYS[(PLC_SUN_RAYS * atan2(Y, X, rec) & 0xFFFF) >> 8]
            t = PLC_SUN_T0 + ((PLC_SUN_RAY * ray >> 8) * (256 - (PLC_SUN_FADE * sm(far) >> 8)) >> 8) + (PLC_SUN_GLOW * (256 - sm(near)) >> 8)
            row.append(p.ramp[min(256, t)])
        rows.append(row)
    return rows


def mesh(p, tones, seed, side):
    """The Daily Mix's blob field of the tones (no scrim); one tone is completed with L, packed back through tone_prep as the field does."""
    t = list(tones[:4]) if len(tones) > 1 else [p.A, p.L]
    return D.field(t, seed, side, side)


def art(style, tones, seed, side):
    """Rows of (r, g, b) at RGB565 precision for a style 1..5; tones are (r, g, b), the playlist's album tones in order (none: a grey)."""
    assert SOLID <= style <= BAND and 1 <= side <= PLC_MAX
    p = Pal(tones)
    rows = mesh(p, tones, seed, side) if style == MESH else (None, solid, None, sunburst, stripes, band)[style](p, side)
    return [[D.quantise(px, x, y) for x, px in enumerate(row)] for y, row in enumerate(rows)]


def to_image(rows): return D.to_image(rows)


def c_tables():
    """patch/plcover.c's two tables as C source."""
    def fmt(name, ty, v):
        body = ''.join(('\n    ' if i % 16 == 0 else ' ') + f'{x},' for i, x in enumerate(v))
        return f'static const {ty} {name}[{len(v)}] = {{{body}}};'
    return fmt('plc_atan', 'unsigned short', ATAN) + '\n\n' + fmt('plc_rays', 'unsigned short', RAYS)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# The stored choice (patch/plcover.c, "The file"): /mnt/mmc/.m1plus/playlist-covers
#   M1PC1\n, then per playlist  <id>\t<style 1..5>\t<flags hex>\t<seed hex8>\t<0..3 tones rrggbb, space separated>\t<name>\n
# An entry is (id, style, flags, seed, tones, name): tones are (r, g, b), the name a str.
MAGIC = b'M1PC1\n'
FILE_MAX = 12288
NAME_MAX = 64          # bytes of a name kept, the NUL included
MAX_ENTRIES = 100      # PL_MAX
FNV_SEED, FNV_PRIME = 2166136261, 16777619


def norm(name):
    """The name as the file keeps it: control bytes as spaces, cut to 63 bytes before a split UTF-8 sequence."""
    b = bytearray(name.encode('utf-8'))
    n = len(b)
    if n >= NAME_MAX:
        n = NAME_MAX - 1
        while n and (b[n] & 0xc0) == 0x80: n -= 1
    return bytes(0x20 if c < 0x20 or c == 0x7f else c for c in b[:n]).decode('utf-8')


def make_seed(pid, name):
    """The seed made at the first set: FNV-1a of the name, xor the id, one more FNV step, never 0."""
    h = FNV_SEED
    for c in name.encode('utf-8'): h = ((h ^ c) * FNV_PRIME) & 0xffffffff
    h = ((h ^ pid) * FNV_PRIME) & 0xffffffff
    return h or 1


def sig(style, flags, seed, tones):
    """patch/plcover.c plc_sig, with tones as (r, g, b)."""
    h = FNV_SEED
    for v in (style, flags, seed) + tuple(0xff000000 | t[0] | t[1] << 8 | t[2] << 16 for t in tones) + (len(tones),):
        h = ((h ^ v) * FNV_PRIME) & 0xffffffff
    return h or 1


def line(e):
    pid, style, flags, seed, tones, name = e
    return f'{pid}\t{style}\t{flags:x}\t{seed:08x}\t' + ' '.join('%02x%02x%02x' % t for t in tones) + f'\t{name}\n'


def dump(entries): return MAGIC + ''.join(line(e) for e in entries).encode('utf-8')


def parse_line(raw):
    """One line (without its newline) as an entry, None when it does not read."""
    import re
    m = re.fullmatch(rb'(0|[1-9][0-9]{0,9})\t([1-5])\t(0|[1-9a-f][0-9a-f]?)\t([0-9a-f]{8})\t((?:[0-9a-f]{6}(?: [0-9a-f]{6}){0,2})?)\t([^\x00-\x1f\x7f]{1,63})', raw)
    if not m or int(m.group(1)) > 0x7fffffff: return None
    try: name = m.group(6).decode('utf-8')
    except UnicodeDecodeError: return None
    tones = tuple((int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)) for t in m.group(5).decode().split())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3), 16), int(m.group(4), 16), tones, name)


def parse(data):
    """The entries the reader keeps: a bad header or a file over FILE_MAX is none; a line that does not read is dropped; the first of an id stays; at most MAX_ENTRIES."""
    if len(data) > FILE_MAX or len(data) <= len(MAGIC) or not data.startswith(MAGIC): return []
    out = []
    pos = len(MAGIC)
    while pos < len(data) and len(out) < MAX_ENTRIES:
        nl = data.find(b'\n', pos)
        if nl < 0: break
        e = parse_line(data[pos:nl])
        pos = nl + 1
        if e and all(o[0] != e[0] for o in out): out.append(e)
    return out


def find(entries, pid, name):
    return next((e for e in entries if e[0] == pid and e[5] == norm(name)), None)


def set_(entries, pid, name, style, flags=0, tones=()):
    """plc_set: the new entry list (the same list when there is nothing to do). A stale entry of the id under another name goes; the seed of an existing entry stays."""
    name = norm(name)
    old = find(entries, pid, name)
    if style == ALBUMS: return [e for e in entries if e is not old] if old else entries
    seed = old[3] if old else make_seed(pid, name)
    out = [e for e in entries if e is not old and e[0] != pid] + [(pid, style, flags & 255, seed, tuple(tones[:3]), name)]
    return out


def rename(entries, pid, old, name):
    e = find(entries, pid, old)
    return entries if not e else [x for x in entries if x is not e] + [e[:5] + (norm(name),)]


def forget(entries, pid, name):
    e = find(entries, pid, name)
    return entries if not e else [x for x in entries if x is not e]


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--c-tables', action='store_true', help='print the tables patch/plcover.c carries')
    if ap.parse_args().c_tables: print(c_tables())
