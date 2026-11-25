"""The generated playlist covers (patch/plcover.c, patch/dmart.h, tools/pod_plcover.py, docs/modules/plcover.md).

The compiled plc_art runs under Unicorn on a bare machine (no widget, no stock call: it is a pure function of the tones) against the integer model, pixel for
pixel. The checks:
  tables   patch/offsets.inc PLC_* and the two tables of patch/plcover.c against the Python model
  art      the five styles in C against pod_plcover.art over palettes (warm, blue, green, grey, one tone, no tone), sides (52, 144, 160 and odd ones) and seeds
  look     every pixel opaque and RGB565 expanded, the styles and the seeds differ, a style or side out of range draws nothing, nothing is written past the bitmap
  cost     (PERF=1) the instructions a pixel takes in each style
  file     the stored choice (patch/plcover.c plc_get, tools/pod_plcover.py parse / dump): the model's round trip, every kind of bad line, the reader of the C against the model, the cap, no card
  api      plc_set / plc_get / plc_rename / plc_forget against the model: the file after each call, the seed made once, a stale id, a failing write, a full file
  draw     the Playlists page (grid and list), the playlist's Songs header and a Home pin draw plc_art and the rounded corners for a playlist with a cover and the mosaic for one without; a change shows when the
           page returns; a source's page ignores the file; a rename keeps the cover"""
import os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import pod_plcover as P
import pod_settings as ST

REGION, SIZE = 0x30000000, 0x100000
OUT = REGION + 0x100000
PALETTES = [('warm', [(190, 140, 60), (170, 90, 80), (70, 110, 190)]), ('blue', [(70, 110, 190), (50, 90, 170), (110, 130, 150), (60, 40, 110)]),
            ('green', [(90, 160, 110), (190, 140, 60)]), ('grey', [(120, 120, 120), (60, 60, 60)]), ('one', [(170, 90, 80)]), ('none', []),
            ('dark', [(10, 10, 12), (20, 20, 30)]), ('pale', [(250, 245, 235), (255, 255, 255), (240, 240, 250)])]


def word(rgb): return 0xff000000 | rgb[0] | rgb[1] << 8 | rgb[2] << 16


class Plc:
    """plc_art on a bare machine: the tones at the end of one mapped region and the bitmap at the end of another (an unmapped page follows each: a read or write past either faults)."""
    def __init__(self, count=False):
        self.m = Machine()
        if count: self.m.count()
        for base in (REGION, OUT): self.m.u.mem_map(base, SIZE)

    def draw(self, style, tones, seed, side, nt=None, fill=0xdeadbeef):
        m = self.m
        nt = len(tones) if nt is None else nt
        ta = REGION + SIZE - 4 * max(nt, 1)
        m.u.mem_write(ta, b''.join(struct.pack('<I', word(t)) for t in tones[:nt]) or bytes(4))
        oa = OUT + SIZE - 4 * side * side
        m.u.mem_write(oa, struct.pack('<I', fill) * (side * side))
        m.setword(STACK + 16, nt); m.setword(STACK + 20, seed)
        m.call(PSYMS['plc_art'], a0=oa, a1=side, a2=style, a3=ta, count=1 << 40)
        return list(struct.unpack(f'<{side * side}I', bytes(m.u.mem_read(oa, 4 * side * side))))


def words_of(rows): return [word(px) for row in rows for px in row]


def tables_tests(ctx):
    """The numbers the C and the model share."""
    expect = ctx.expect
    names = [n for n in dir(P) if n.startswith('PLC_')]
    bad = [n for n in names if O[n] != getattr(P, n)]
    expect(len(names) >= 20 and not bad, f'patch/offsets.inc PLC_* equal the model\'s ({len(names)} numbers; differing: {bad})')
    expect({n for n in O if n.startswith('PLC_')} == set(names), 'and every PLC_ define of the header is in the model, and the other way round')
    src = open(os.path.join(ROOT, 'patch', 'plcover.c')).read()
    for tab, want in (('plc_atan', P.ATAN), ('plc_rays', P.RAYS)):
        mm = re.search(r'static const unsigned short ' + tab + r'\[(\d+)\] = \{(.*?)\};', src, re.S)
        have = [int(v) for v in re.findall(r'\d+', mm.group(2))] if mm else []
        expect(mm and int(mm.group(1)) == len(want) and have == want, f'the table {tab} of patch/plcover.c is the model\'s (pod_plcover.py --c-tables prints it)')
    expect(P.STRIPE_LEVELS == tuple(int(v) for v in re.search(r'plc_levels\[5\] = \{(.*?)\}', src).group(1).split(',')), 'the Stripes step heights of the C equal the model\'s')
    expect(P.GREY == int(re.search(r'PLC_GREY (0xff[0-9a-f]{6})u', open(os.path.join(ROOT, 'patch', 'plcover.h')).read()).group(1), 16) & 0xffffff, 'the no-tone grey of the header is the model\'s')


def art_tests(ctx):
    """plc_art against pod_plcover.art, pixel for pixel."""
    expect = ctx.expect
    t = Plc()
    bad, n = [], 0
    cases = [(side, pal) for side in (52, 53, 7) for pal in PALETTES] + [(side, pal) for side in (144, 160, 97) for pal in PALETTES[:6:2] + PALETTES[5:]]
    for k, (side, (name, tones)) in enumerate(cases):
        for style in range(P.SOLID, P.BAND + 1):
            seed = (0x0badf00d * (k + 1) + style) & 0xffffffff if k % 4 else 0
            got = t.draw(style, tones, seed, side)
            n += 1
            if got != words_of(P.art(style, tones, seed, side)): bad.append((P.NAMES[style], side, name, seed))
    expect(not bad, f'plc_art equals the model on {n} renders (5 styles, {len(PALETTES)} palettes, sides 7, 52, 53, 97, 144, 160, seeds): {bad[:6]}')
    got = t.draw(P.MESH, PALETTES[0][1] * 2, 5, 52, nt=6)
    expect(got == words_of(P.art(P.MESH, PALETTES[0][1] * 2, 5, 52)), 'Mesh takes the first four of more tones (as the Daily Mix does)')
    got = t.draw(P.SUNBURST, PALETTES[0][1], 1, P.PLC_MAX)
    expect(got == words_of(P.art(P.SUNBURST, PALETTES[0][1], 1, P.PLC_MAX)), f'the largest side ({P.PLC_MAX}) too')


def look_tests(ctx):
    """What any caller can rely on."""
    expect = ctx.expect
    t = Plc()
    side = 52
    tones = PALETTES[0][1]
    imgs = {s: t.draw(s, tones, 7, side) for s in range(P.SOLID, P.BAND + 1)}
    ok565 = lambda v: v >> 24 == 255 and all((c & 7) == (c >> 5) if i != 1 else (c & 3) == (c >> 6) for i, c in enumerate((v & 255, v >> 8 & 255, v >> 16 & 255)))
    expect(all(ok565(v) for im in imgs.values() for v in im), 'every pixel is opaque and an RGB565 value expanded to 8 bits')
    expect(len({tuple(im) for im in imgs.values()}) == 5, 'the five styles differ')
    expect(t.draw(P.MESH, tones, 8, side) != imgs[P.MESH] and t.draw(P.SUNBURST, tones, 8, side) == imgs[P.SUNBURST], 'the seed shapes Mesh and only Mesh')
    expect(t.draw(P.BAND, [], 0, side) == t.draw(P.BAND, [(0x78, 0x78, 0x78)], 0, side), 'no tone is the grey 0x787878')
    expect(t.draw(P.SOLID, tones[:1], 0, side) == t.draw(P.SOLID, tones, 0, side), 'every style but Mesh draws from the first tone only')
    expect(t.draw(P.BAND, [(0x40, 0x80, 0xc0)], 0, side)[:3] != t.draw(P.BAND, [(0xc0, 0x80, 0x40)], 0, side)[:3], 'another tone, another colour')
    fill = 0xdeadbeef
    for style, sd in ((P.ALBUMS, side), (6, side), (-1, side), (P.SOLID, 0), (P.SOLID, P.PLC_MAX + 1), (P.SOLID, -3)):
        n = side * side
        oa = OUT + SIZE - 4 * n
        t.m.u.mem_write(oa, struct.pack('<I', fill) * n)
        t.m.setword(STACK + 16, 3); t.m.setword(STACK + 20, 1)
        t.m.u.mem_write(REGION + SIZE - 12, b'\0' * 12)
        t.m.call(PSYMS['plc_art'], a0=oa, a1=sd, a2=style, a3=REGION + SIZE - 12, count=1 << 40)
        expect(bytes(t.m.u.mem_read(oa, 4 * n)) == struct.pack('<I', fill) * n, f'style {style}, side {sd}: nothing is drawn')
    for style in range(P.SOLID, P.BAND + 1):
        want = P.art(style, tones, 1, 5)
        expect(t.draw(style, tones, 1, 5) == words_of(want), f'{P.NAMES[style]}: a 5 px side draws and stays inside its bitmap')


def cost_tests(ctx):
    """Instructions a pixel takes (PERF=1)."""
    expect = ctx.expect
    if not PERF: return
    t = Plc(count=True)
    side = 160
    line = []
    for style in range(P.SOLID, P.BAND + 1):
        t.draw(style, PALETTES[0][1], 3, side)
        per = t.m.icount // (side * side)
        line.append(f'{P.NAMES[style]} {per}')
        expect(per < 700, f'{P.NAMES[style]} stays under 700 instructions a pixel ({per})')
    print('  (plcover, instructions a pixel at 160 px: ' + ', '.join(line) + ')')




# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# The stored choice
PLC = '/mnt/mmc/.m1plus/playlist-covers'
TONES = [(190, 140, 60), (70, 110, 190), (90, 160, 110)]
HEX = lambda t: '%02x%02x%02x' % t


def E(pid, style=P.SUNBURST, tones=TONES[:2], name='Road Trip', flags=0, seed=0x1234abcd): return (pid, style, flags, seed, tuple(tones), name)


class FM(Machine):
    COUNT = True


def fm(data=None):
    m = FM()
    if data is not None: m.fs[PLC] = data
    return m


def get(m, pid, name):
    """plc_get: None, or (style, flags, seed, tones, sig) from the plc_t it fills."""
    out = m.alloc(40)
    m.u.mem_write(out, b'\xee' * 40)
    r = m.call(PSYMS['plc_get'], a0=pid, a1=m.cstr(name), a2=out, count=40000000)
    if not r: return None
    st, fl, sd, nt, t0, t1, t2, sig = struct.unpack('<8I', bytes(m.u.mem_read(out, 32)))
    tw = [t0, t1, t2][:nt]
    return st, fl, sd, [(w & 255, w >> 8 & 255, w >> 16 & 255) for w in tw], sig, [w >> 24 for w in tw]


def tones_arg(m, tones):
    a = m.alloc(16)
    m.u.mem_write(a, struct.pack('<4I', *([word(t) for t in tones] + [0] * 4)[:4]))
    return a


def setc(m, pid, name, style, flags=0, tones=()):
    """plc_set; its answer as a signed number (the tones and their count are the 5th and 6th argument, on the stack)."""
    m.setword(STACK + 16, tones_arg(m, tones)); m.setword(STACK + 20, len(tones))
    r = m.call(PSYMS['plc_set'], a0=pid, a1=m.cstr(name), a2=style, a3=flags, count=40000000)
    return r - (1 << 32) if r >> 31 else r


def read_back(m, pid, name):
    """What plc_get says about a playlist, as the model's entry (None for none)."""
    g = get(m, pid, name)
    return None if g is None else (pid, g[0], g[1], g[2], tuple(g[3]), name)


def file_tests(ctx):
    """The file model, and the reader of the C against it."""
    expect = ctx.expect
    good = [E(3, P.SOLID, TONES[:1], 'Late Night'), E(7), E(12, P.MESH, TONES, 'Mix \u00e9\u4e2d', flags=1, seed=1), E(40, P.BAND, (), 'No tones', flags=0x81, seed=0), E(2147483647, P.STRIPES, TONES[:3], 'Big id')]
    data = P.dump(good)
    expect(P.parse(data) == good and P.parse(P.MAGIC) == [] and P.parse(b'') == [] and data.startswith(b'M1PC1\n') and data.count(b'\n') == 6, 'the model round-trips a list (tones 0..3, flags, UTF-8 names); the bare header is an empty list')
    expect(data.split(b'\n')[2] == b'7\t3\t0\t1234abcd\tbe8c3c 466ebe\tRoad Trip' and data.split(b'\n')[3].startswith(b'12\t2\t1\t00000001\tbe8c3c 466ebe 5aa06e\t'),
           'a line is id, style, flags in hex, the seed in 8 hex digits, the tones as rrggbb, the name, tab separated')
    base = [E(7), E(8, P.BAND, (), 'Second')]
    L = lambda e: P.line(e).encode()
    bad = {'id sign': b'-1\t3\t0\t00000001\t\tx\n', 'id zero pad': b'07\t3\t0\t00000001\t\tx\n', 'id too big': b'2147483648\t3\t0\t00000001\t\tx\n', 'id 11 digits': b'10000000000\t3\t0\t00000001\t\tx\n',
           'style 0': b'5\t0\t0\t00000001\t\tx\n', 'style 6': b'5\t6\t0\t00000001\t\tx\n', 'style 2 digits': b'5\t10\t0\t00000001\t\tx\n', 'flags empty': b'5\t3\t\t00000001\t\tx\n',
           'flags upper': b'5\t3\tA\t00000001\t\tx\n', 'flags zero pad': b'5\t3\t01\t00000001\t\tx\n', 'flags three': b'5\t3\t100\t00000001\t\tx\n', 'seed short': b'5\t3\t0\t0001\t\tx\n',
           'seed upper': b'5\t3\t0\t0000000A\t\tx\n', 'seed long': b'5\t3\t0\t000000001\t\tx\n', 'four tones': b'5\t3\t0\t00000001\taaaaaa bbbbbb cccccc dddddd\tx\n', 'tone upper': b'5\t3\t0\t00000001\tAAAAAA\tx\n',
           'tone short': b'5\t3\t0\t00000001\taaaaa\tx\n', 'tone comma': b'5\t3\t0\t00000001\taaaaaa,bbbbbb\tx\n', 'trailing space': b'5\t3\t0\t00000001\taaaaaa \tx\n', 'double space': b'5\t3\t0\t00000001\taaaaaa  bbbbbb\tx\n',
           'empty name': b'5\t3\t0\t00000001\t\t\n', 'control in name': b'5\t3\t0\t00000001\t\ta\x01b\n', 'long name': b'5\t3\t0\t00000001\t\t' + b'n' * 64 + b'\n', 'missing field': b'5\t3\t0\t00000001\tx\n',
           'extra field': b'5\t3\t0\t00000001\t\tx\tz\n', 'cr': b'5\t3\t0\t00000001\t\tx\r\n', 'blank line': b'\n', 'duplicate id': L(base[0]) + b'7\t4\t0\t00000002\t\tOther\n'}
    m = fm()
    for k, line in bad.items():
        m.fs[PLC] = P.MAGIC + L(base[0]) + line + L(base[1])
        want = [e for e in P.parse(m.fs[PLC])]
        got = [read_back(m, e[0], e[5]) for e in base]
        expect(want == base and got == base and (k == 'duplicate id' or read_back(m, 5, 'x') is None), f'a bad line ({k}) is dropped and the lines around it are read (model {len(want)}, C {[g is not None for g in got]})')
    m.fs[PLC] = P.MAGIC + L(base[0]) + L(base[1])[:-1]
    expect(P.parse(m.fs[PLC]) == base[:1] and read_back(m, 7, 'Road Trip') == base[0] and read_back(m, 8, 'Second') is None, 'a last line with no newline is dropped')
    ok = {'name 63 bytes': b'5\t3\t0\t00000001\t\t' + b'n' * 63 + b'\n', 'ff flags': b'5\t3\tff\t00000001\t\tx\n', 'id 0': b'0\t3\t0\t00000001\t\tx\n'}
    for k, line in ok.items():
        e = P.parse(P.MAGIC + line)
        nm = ('n' * 63) if 'name' in k else 'x'
        m.fs[PLC] = P.MAGIC + line
        expect(len(e) == 1 and read_back(m, e[0][0], nm) == e[0], f'{k}: read')
    for k, d in {'magic': b'M1PC2\n' + data[6:], 'no magic': data[6:], 'header only': P.MAGIC, 'empty': b'', 'cut header': data[:4], 'too big': P.MAGIC + L(E(1)) * 200 + b'\n' * 12288}.items():
        m.fs[PLC] = d
        expect(P.parse(d) == [] and all(read_back(m, e[0], e[5]) is None for e in good + [E(1)]), f'{k}: no covers')
    for e in good:
        m.fs[PLC] = data
        g = get(m, e[0], e[5])
        expect(g and (g[0], g[1], g[2], g[3]) == (e[1], e[2], e[3], list(e[4])) and all(a == 255 for a in g[5]) and g[4] not in (0,) , f'plc_get of {e[5]!r}: the style, flags, seed, tones (opaque words 0xffBBGGRR) as the file says')
    m.fs[PLC] = data
    sigs = [get(m, e[0], e[5])[4] for e in good]
    expect(len(set(sigs)) == len(good) and all(sigs) and [get(m, e[0], e[5])[4] for e in good] == sigs and sigs == [P.sig(e[1], e[2], e[3], e[4]) for e in good], 'the sig is the model\'s hash of style, flags, seed and tones (never 0); every cover has its own')
    expect(read_back(m, 7, 'Road Trip ') is None and read_back(m, 7, 'road trip') is None and read_back(m, 8, 'Road Trip') is None and read_back(m, 7, '') is None and read_back(m, -1, 'Road Trip') is None,
           'a playlist is its id and its exact name: another name (a replacement playlist reusing the id), another id, an empty name or a negative id has no cover')
    expect(get(m, 7, 'Road Trip') and m.call(PSYMS['plc_get'], a0=7, a1=m.cstr('Road Trip'), a2=0, count=40000000) == 1, 'plc_get without an out pointer only answers')
    lines = [E(i, P.SOLID, TONES[:1], f'P{i}') for i in range(1, 103)]
    m.fs[PLC] = P.dump(lines)
    got = [read_back(m, e[0], e[5]) is not None for e in lines]
    expect(got == [True] * 100 + [False] * 2 and len(P.parse(m.fs[PLC])) == 100, 'at most PL_MAX (100) covers are read: the first 100 lines')
    m.card_mounted = False
    m.fs[PLC] = data
    expect(read_back(m, 7, 'Road Trip') is None, 'no card: no covers')
    m.card_mounted = True
    expect(read_back(m, 7, 'Road Trip') == E(7)[:5] + ('Road Trip',) or read_back(m, 7, 'Road Trip') is not None, 'and with the card back they are there again')
    m.fs[PLC] = data
    expect(read_back(m, 7, 'Road Trip') is not None and (m.fs.__setitem__(PLC, P.dump([E(7, P.BAND, (), 'Road Trip')])) or True) and read_back(m, 7, 'Road Trip')[1] == P.BAND,
           'the file is read again after it changed (its state follows its text: harness stat_fs)')


def api_tests(ctx):
    """plc_set / plc_get / plc_rename / plc_forget against the model."""
    expect = ctx.expect
    TMP = PLC + '.tmp'
    m = fm()
    expect(read_back(m, 7, 'Road Trip') is None and PLC not in m.fs, 'no file: no cover, nothing written by a read')
    r = setc(m, 7, 'Road Trip', P.SUNBURST, 0, TONES[:2])
    want = [(7, P.SUNBURST, 0, P.make_seed(7, 'Road Trip'), tuple(TONES[:2]), 'Road Trip')]
    expect(r == 0 and m.fs[PLC] == P.dump(want) and TMP not in m.fs and read_back(m, 7, 'Road Trip') == want[0], f'the first set writes the file (atomically): the seed made from the id and the name ({r}, {m.fs.get(PLC)})')
    seed = want[0][3]
    expect(seed and P.make_seed(8, 'Road Trip') != seed and P.make_seed(7, 'Road Trips') != seed, 'the seed depends on the id and the name, never 0')
    expect(setc(m, 7, 'Road Trip', P.MESH, 1, TONES) == 0 and P.parse(m.fs[PLC]) == [(7, P.MESH, 1, seed, tuple(TONES), 'Road Trip')], 'set again: the style, flags and tones change; the seed is kept')
    expect(setc(m, 3, 'Late Night', P.SOLID, 0, ()) == 0 and [e[0] for e in P.parse(m.fs[PLC])] == [7, 3] and P.parse(m.fs[PLC])[1][4] == (), 'a second playlist goes to the end; no tones is a line with an empty tone field')
    expect(setc(m, 3, 'Late Night', P.BAND, 0xff, TONES * 2) == 0 and P.parse(m.fs[PLC])[1][4] == tuple(TONES) and P.parse(m.fs[PLC])[1][2] == 0xff, 'more than three tones: the first three; flags are one byte')
    expect(setc(m, 3, 'Late Night', P.BAND, 0x1ff, TONES[:1]) == 0 and P.parse(m.fs[PLC])[1][2] == 0xff, 'flags beyond a byte are cut to it')
    before = m.fs[PLC]
    expect(setc(m, 3, 'Late Night', 6, 0, ()) == -1 and setc(m, 3, 'Late Night', -1, 0, ()) == -1 and setc(m, 3, '', P.SOLID, 0, ()) == -1 and setc(m, -1, 'x', P.SOLID, 0, ()) == -1 and m.fs[PLC] == before,
           'a style out of range, an empty name or a negative id: -1, nothing written')
    expect(setc(m, 7, 'Other Name', P.SOLID, 0, TONES[:1]) == 0 and [(e[0], e[5]) for e in P.parse(m.fs[PLC])] == [(3, 'Late Night'), (7, 'Other Name')] and read_back(m, 7, 'Road Trip') is None,
           'a stale entry of the same id under another name (the id was reused) is replaced')
    expect(setc(m, 7, 'Other Name', P.ALBUMS, 0, ()) == 0 and [e[0] for e in P.parse(m.fs[PLC])] == [3] and read_back(m, 7, 'Other Name') is None, 'style 0 (Albums) removes the entry')
    before = m.fs[PLC]
    expect(setc(m, 7, 'Other Name', P.ALBUMS, 0, ()) == 0 and setc(m, 3, 'Late', P.ALBUMS, 0, ()) == 0 and m.fs[PLC] == before and m.fs.get(TMP) is None, 'removing what is not there (or under another name) writes nothing')
    # a long or odd name
    nm = 'x' * 70
    setc(m, 20, nm, P.SOLID, 0, ()); setc(m, 21, 'a\tb\x01c', P.SOLID, 0, ())
    got = {e[0]: e[5] for e in P.parse(m.fs[PLC])}
    expect(got.get(20) == 'x' * 63 and got.get(21) == 'a b c' and read_back(m, 20, nm) is not None and read_back(m, 21, 'a\tb\x01c') is not None, f'a name is kept as the pins keep it: cut at 63 bytes, control bytes as spaces ({got})')
    u = '\u4e2d' * 30
    setc(m, 22, u, P.SOLID, 0, ())
    cut = {e[0]: e[5] for e in P.parse(m.fs[PLC])}.get(22)
    expect(cut == '\u4e2d' * 21 and read_back(m, 22, u) is not None, 'a cut never splits a UTF-8 character')
    # rename and forget
    m = fm(P.dump([E(3, P.SOLID, TONES[:1], 'Late Night'), E(7, P.MESH, TONES, 'Road Trip', seed=0x55)]))
    rn = lambda pid, old, new: m.call(PSYMS['plc_rename'], a0=pid, a1=m.cstr(old), a2=m.cstr(new), count=40000000)
    fg = lambda pid, name: m.call(PSYMS['plc_forget'], a0=pid, a1=m.cstr(name), count=40000000)
    expect(rn(7, 'Road Trip', 'Drive') == 1 and P.parse(m.fs[PLC]) == [E(3, P.SOLID, TONES[:1], 'Late Night'), E(7, P.MESH, TONES, 'Drive', seed=0x55)] and read_back(m, 7, 'Drive')[1:4] == (P.MESH, 0, 0x55), 'rename: the entry follows with its style, tones and seed')
    sig0 = get(m, 7, 'Drive')[4]
    rn(7, 'Drive', 'Drive 2')
    expect(get(m, 7, 'Drive 2')[4] == sig0, 'a rename keeps the cover\'s sig (the pictures of the tiles stay)')
    before = m.fs[PLC]
    expect(rn(7, 'Nope', 'X') == 0 and rn(9, 'Drive 2', 'X') == 0 and rn(7, 'Drive 2', '') == 0 and rn(-1, 'a', 'b') == 0 and m.fs[PLC] == before, 'renaming what has no cover (another name, another id) or to an empty name does nothing')
    expect(fg(7, 'Drive') == 0 and fg(9, 'Drive 2') == 0 and m.fs[PLC] == before, 'forgetting another name or id does nothing')
    expect(fg(7, 'Drive 2') == 1 and P.parse(m.fs[PLC]) == [E(3, P.SOLID, TONES[:1], 'Late Night')] and fg(3, 'Late Night') == 1 and m.fs[PLC] == P.MAGIC and P.parse(m.fs[PLC]) == [], 'forget removes the entry; the last one leaves the header alone')
    expect(setc(m, 4, 'Again', P.STRIPES, 0, TONES[:1]) == 0 and len(P.parse(m.fs[PLC])) == 1, 'and a header-only file takes a cover again')
    # no card, a failing write, the caps
    m = fm(P.dump([E(7)])); m.card_mounted = False
    expect(setc(m, 3, 'Late', P.SOLID, 0, ()) == -1 and m.fs[PLC] == P.dump([E(7)]) and fg(7, 'Road Trip') == 0 and rn(7, 'Road Trip', 'X') == 0, 'no card: set answers -1, forget and rename 0, nothing is written')
    m = fm(P.dump([E(7)])); m.fail.add(('rename', PLC))
    expect(setc(m, 3, 'Late', P.SOLID, 0, ()) == -1 and m.fs[PLC] == P.dump([E(7)]) and read_back(m, 3, 'Late') is None and read_back(m, 7, 'Road Trip') is not None, 'a write that fails: -1, the file and what is read from it are as they were')
    expect(rn(7, 'Road Trip', 'X') == 0 and fg(7, 'Road Trip') == 0 and read_back(m, 7, 'Road Trip') is not None and read_back(m, 7, 'X') is None, 'a failing rename and forget answer 0 and change nothing')
    m.fail.clear()
    expect(setc(m, 3, 'Late', P.SOLID, 0, ()) == 0 and len(P.parse(m.fs[PLC])) == 2, 'and the same call works once the card writes again')
    m = fm(P.dump([E(i, P.SOLID, (), f'P{i}') for i in range(1, 101)]))
    expect(setc(m, 500, 'Hundred and one', P.SOLID, 0, ()) == -1 and len(P.parse(m.fs[PLC])) == 100, 'a 101st cover is refused')
    expect(setc(m, 50, 'P50', P.BAND, 0, ()) == 0 and len(P.parse(m.fs[PLC])) == 100 and P.find(P.parse(m.fs[PLC]), 50, 'P50')[1] == P.BAND, 'but a cover that is there can change at 100')
    m = fm(P.dump([E(i, P.SOLID, TONES, 'n' * 63) for i in range(1, 100)]))
    expect(len(m.fs[PLC]) < 12288 and setc(m, 100, 'n' * 63, P.SOLID, 0, TONES) == 0 and len(m.fs[PLC]) <= 12288, 'a file of 100 of the longest lines fits its size cap')


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# The covers where they are drawn
PL, SG, PN = sibling('playlists'), sibling('songs'), sibling('pins')


def bmp_words(m, b):
    data, w, h = m.bitmaps[b]
    return w, list(struct.unpack(f'<{w * h}I', bytes(m.u.mem_read(data, 4 * w * h))))


def is_art(m, b, side, e, r):
    """The bitmap is plc_art of the entry at side x side with the corners (r x r each) left to the rounding: every other pixel equal to the model's, the corner pixel itself not."""
    w, px = bmp_words(m, b)
    if w != side: return False
    want = words_of(P.art(e[1], list(e[4]), e[3], side))
    bad = [i for i in range(side * side) if not ((i % side < r or i % side >= side - r) and (i // side < r or i // side >= side - r)) and px[i] != want[i]]
    return not bad and px[0] != want[0]


def draw_tests(ctx):
    """The three places that draw the playlist's mosaic draw a chosen cover instead."""
    expect = ctx.expect
    COVER, LART = O['GRID_COVER'], O['LIST_ART']
    cov = E(7, P.SUNBURST, TONES[:2], 'Road')
    cov2 = E(7, P.BAND, TONES[:1], 'Road', seed=9)
    lists = [(3, 'Night', [0, 1, 2]), (7, 'Road', [0, 1])]
    # ---- the Playlists page: grid
    for mode, side, rad in (('grid', COVER, O['GRID_R']), ('list', LART, O['LIST_R'])):
        m = PL.PM(lists)
        if mode == 'list': m.fs[PL.PL_FILE] = b'0\n'
        m.fs[PLC] = P.dump([cov])
        PL.open_page(m)
        log = []
        blits, texts, styles = PL.settle(m, log=log)
        if mode == 'grid': mine, plain = PL.cell_blit(blits, 1), PL.cell_blit(blits, 0)
        else:
            lb = sorted((b for b in blits if b[2][2] == LART), key=lambda b: b[2][1])
            mine, plain = lb[1][0], lb[0][0]
        expect(mine is not None and is_art(m, mine, side, cov, rad), f'the Playlists page ({mode}): a playlist with a cover shows plc_art at {side} px with the rounded corners')
        q = PL.quadrants(m, plain, side)
        expect(plain is not None and all(PL.near(a, b) for a, b in zip(q, PL.want_mosaic([0, 1, 2]))), f'({mode}) a playlist without one keeps its mosaic ({[hex(x) for x in q]})')
        expect(m.most_per_tick <= 1, f'({mode}) a tick decodes at most one cover')
        # the file changes while the page is behind: the next to-foreground shows it
        m.fs[PLC] = P.dump([cov2])
        fn, c = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]
        m.call(fn, a0=c, a1=0, count=60000000)
        blits = PL.settle(m)[0]
        mine = PL.cell_blit(blits, 1) if mode == 'grid' else sorted((b for b in blits if b[2][2] == LART), key=lambda b: b[2][1])[1][0]
        expect(is_art(m, mine, side, cov2, rad), f'({mode}) another style chosen meanwhile shows when the page returns, the database untouched')
        m.fs[PLC] = P.MAGIC
        m.call(fn, a0=c, a1=0, count=60000000)
        blits = PL.settle(m)[0]
        mine = PL.cell_blit(blits, 1) if mode == 'grid' else sorted((b for b in blits if b[2][2] == LART), key=lambda b: b[2][1])[1][0]
        q = PL.quadrants(m, mine, side)
        expect(all(PL.near(a, b) for a, b in zip(q, PL.want_mosaic([0, 1]))), f'({mode}) the cover removed: the mosaic is back at the next return')
        m.fs[PLC] = P.dump([E(7, P.SOLID, TONES[:1], 'Another')])
        m.call(fn, a0=c, a1=0, count=60000000)
        blits = PL.settle(m)[0]
        mine = PL.cell_blit(blits, 1) if mode == 'grid' else sorted((b for b in blits if b[2][2] == LART), key=lambda b: b[2][1])[1][0]
        expect(all(PL.near(a, b) for a, b in zip(PL.quadrants(m, mine, side), PL.want_mosaic([0, 1]))), f'({mode}) a cover for another name (the id reused) is not this playlist\'s')
    # a source's page never looks the file up
    m = PL.PM(lists); src = m.fake_src()
    m.fs[PLC] = P.dump([E(3, P.SOLID, TONES[:1], 'Night'), cov])
    m.call(PSYMS['playlists_open_src'], a0=src, count=60000000)
    blits = PL.settle(m)[0]
    ok = all(PL.near(a, b) for a, b in zip(PL.quadrants(m, PL.cell_blit(blits, 1)), PL.want_mosaic([0, 1]))) and all(PL.near(a, b) for a, b in zip(PL.quadrants(m, PL.cell_blit(blits, 0)), PL.want_mosaic([0, 1, 2])))
    expect(ok and not [c for c in m.calls if c[0] == 'open' and c[1] == PLC], 'a source\'s Playlists page shows its mosaics whatever the file holds')

    # ---- the playlist's Songs header
    titles = ['Zed', 'Alpha', 'Mike', 'Bravo', 'Echo', 'Yankee', 'Delta', 'Kilo']
    PHC, PHR = O['PH_COVER'], O['PH_COVER_R']
    hb = lambda blits: [b for b in blits if b[2][2] == PHC]

    def songs_page(entries, pid=7, name='Road Trip'):
        m = SG.list_machine(titles); m.playlist_songs = {pid: list(m.songs[:5])}
        if entries is not None: m.fs[PLC] = P.dump(entries)
        m.call(PSYMS['songs_open_playlist'], a0=pid, a1=m.cstr(name), count=900000000)
        return m
    hc = E(7, P.STRIPES, TONES, 'Road Trip', seed=77)
    m = songs_page([hc])
    blits = SG.settle(m)[0]
    h = hb(blits)
    expect(len(h) == 1 and is_art(m, h[0][0], PHC, hc, PHR) and pixel(m, h[0][0], 0, 0) & 0xffffff == 0, 'the playlist\'s header shows plc_art at 160 px, the corner rounded into black')
    keep = h[0][0]
    m.setword(SG.SHOWLIST, m.new_deque([])); m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    expect(hb(SG.settle(m)[0])[0][0] == keep, 'a list read again keeps the tile (no flicker)')
    m.fs[PLC] = P.dump([E(7, P.BAND, TONES[:1], 'Road Trip', seed=5)])
    m.setword(SG.SHOWLIST, m.new_deque([])); m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    h = hb(SG.settle(m)[0])
    expect(is_art(m, h[0][0], PHC, E(7, P.BAND, TONES[:1], 'Road Trip', seed=5), PHR), 'another style chosen meanwhile shows when the page comes back')
    m.fs[PLC] = P.MAGIC
    m.setword(SG.SHOWLIST, m.new_deque([])); m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    h = hb(SG.settle(m)[0])
    expect(all(PL.near(a, b) for a, b in zip([pixel(m, h[0][0], x, y) for x, y in ((PHC // 4, PHC // 4), (3 * PHC // 4, PHC // 4), (PHC // 4, 3 * PHC // 4), (3 * PHC // 4, 3 * PHC // 4))], [SG.colour(k) for k in range(4)])),
           'the cover removed: the mosaic is made again')
    m = songs_page([E(7, P.SOLID, TONES[:1], 'Another')])
    h = hb(SG.settle(m)[0])
    expect(all(PL.near(a, b) for a, b in zip([pixel(m, h[0][0], x, y) for x, y in ((PHC // 4, PHC // 4), (3 * PHC // 4, PHC // 4))], [SG.colour(0), SG.colour(1)])), 'a cover for another name is not this playlist\'s')
    # a source's playlist header never looks
    m = SG.list_machine(['Stock']); m.top_main = m.window
    row = SG.make_song(m, 'Night', 'Night', 'Night', rid=-9, path='nd://pl9'); m.present.discard('nd://pl9')
    recs = SG.src_records(m, SG.src_titles(6))
    src = SG.fake_source(m, {3: recs})
    m.fs[PLC] = P.dump([E(0, P.SUNBURST, TONES[:2], 'Night')])
    m.call(PSYMS['songs_open_src_in'], a0=src, a1=3, a2=row, a3=m.cstr('Night'), count=900000000)
    h = hb(SG.settle(m)[0])
    expect(h and not is_art(m, h[0][0], PHC, E(0, P.SUNBURST, TONES[:2], 'Night'), PHR), 'a source\'s playlist header never draws the stored cover, even for the same id and name')

    # ---- a Home pin
    pc = PN.playlist(3, 'Late Night', (11, 22, 33))
    side = O['PIN_COVER']

    def home(pins, cover):
        m = PN.PH(entries=pins)
        if cover is not None: m.fs[PLC] = P.dump(cover)
        m.begin()
        return m

    def decode(m):
        m.call(PSYMS['pn_first'], count=400000000)
        n = 0
        while m.call(PSYMS['pn_tick'], a0=0, count=400000000) == O['RET_REPEAT'] and n < 12: n += 1

    def tiles(m):
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        m.blits.clear()
        m.call(PSYMS['pn_on_paint'], a0=0, a1=e, count=400000000)
        return [b for b in m.blits if b[2][2:] == (side, side)]

    def px_of(m, b): return bmp_words(m, b[0])[1]
    pe = E(3, P.MESH, TONES, 'Late Night', seed=0x2468)
    m = home([pc, PN.playlist(9, 'Road Trip', (44,))], [pe])
    decode(m)
    t = tiles(m)
    want = words_of(P.art(pe[1], list(pe[4]), pe[3], side))
    px = px_of(m, t[0])
    r = O['PIN_R']
    inner = [i for i in range(side * side) if not ((i % side < r or i % side >= side - r) and (i // side < r or i // side >= side - r))]
    expect(len(t) == 2 and all(px[i] & 0xffffff == want[i] & 0xffffff for i in inner) and px[0] >> 24 == 0, 'a pinned playlist with a cover shows plc_art at the pin size, the corners cut in the alpha')
    expect(px_of(m, t[1])[side * side // 2 + side // 2] != want[side * side // 2 + side // 2] and t[1][0] != t[0][0], 'a pin of a playlist without one keeps its own tile')
    pe2 = E(3, P.BAND, TONES[:1], 'Late Night', seed=0x13)
    m.fs[PLC] = P.dump([pe2])
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    decode(m)
    t = tiles(m); px = px_of(m, t[0]); want = words_of(P.art(pe2[1], list(pe2[4]), pe2[3], side))
    expect(all(px[i] & 0xffffff == want[i] & 0xffffff for i in inner), 'another style chosen meanwhile shows at the next to-foreground')
    keep = t[0][0]
    m.fs[PLC] = P.dump([pe2, E(8, P.SOLID, (), 'Elsewhere')])
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    decode(m)
    expect(tiles(m)[0][0] == keep, 'a file that changed elsewhere leaves this tile (the bitmap is kept)')
    m.fs[PLC] = P.MAGIC
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    decode(m)
    t = tiles(m)
    expect(not all(px_of(m, t[0])[i] & 0xffffff == want[i] & 0xffffff for i in inner), 'the cover removed: the mosaic (here the placeholder: its albums have no files) is back')
    # a renamed playlist keeps its pin's cover (pins_rename_playlist then plc_rename, as songs.c does)
    m = home([pc], [pe])
    decode(m)
    before = tiles(m)[0][0]
    m.call(PSYMS['pins_rename_playlist'], a0=3, a1=m.cstr('Late Night'), a2=m.cstr('Evening'), count=40000000)
    m.call(PSYMS['plc_rename'], a0=3, a1=m.cstr('Late Night'), a2=m.cstr('Evening'), count=40000000)
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    decode(m)
    t = tiles(m)
    expect(len(t) == 1 and t[0][0] == before and P.parse(m.fs[PLC]) == [E(3, P.MESH, TONES, 'Evening', seed=0x2468)], 'a renamed playlist: the pin keeps its cover tile and the file follows the name')




# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# The Cover page (patch/plcpage.c), reached from the Songs page's Edit mode
def page_tests(ctx):
    """The cover badge and the cover tap in Edit; the page's thumbnails (one a tick, what a tap would store), the taps (the file, Albums removing it, the switch's flag, a card that fails) and the header on return."""
    expect = ctx.expect
    import mod_icons
    RM = sibling('rowmenu')
    titles = ['Zed', 'Alpha', 'Mike', 'Bravo', 'Echo', 'Yankee', 'Delta', 'Kilo']
    PHC, PHR = O['PH_COVER'], O['PH_COVER_R']
    T, PX, PY, TY, X = O['PLP_T'], O['PLP_PX'], O['PLP_PY'], O['PLP_TY'], O['PLP_X']
    expect((T, O['PLP_R'], X, TY, PX, PY, O['PLP_GROW'], O['PLP_RING']) == (mod_icons.COVER_T, mod_icons.COVER_R, ST.CM, 4, ST.COVER_PITCH_X, ST.COVER_PITCH_Y, mod_icons.COVER_RING_GROW, mod_icons.COVER_RING)
           and ST.COVER_LAB_Y >= TY + T + O['PLP_GROW'] and mod_icons.SG_CBADGE[1] == 28 and X + 2 * PX + T + O['PLP_GROW'] <= ST.LIST_W,
           'offsets.inc PLP_* are the layout model\'s and the icons\' numbers; the ring fits inside the item')

    def edit_page(entries=None, pid=7, name='Road Trip'):
        m = SG.list_machine(titles)
        RM.with_menu(m, 0)
        m.images['sg_handle'] = (O['SG_HANDLE_PX'],) * 2 + (b''.join(struct.pack('<4B', c, c, c, 255) for c in mod_icons.handle_image().getchannel('A').tobytes()),)
        badge = mod_icons.songs_images()['sg_cbadge']
        m.images['sg_cbadge'] = (28, 28, badge.tobytes())
        for n in ('pod_cover', 'pod_row0', 'pod_covname', *(f'pod_covl{k}' for k in range(6))): m.widget(n)
        m.images['pod_covring'] = (O['PLP_RING'],) * 2 + (mod_icons.cover_ring().tobytes(),)
        m.playlist_songs = {pid: list(m.songs[:5])}
        h = m.record(path='', title=name, name=name, rid=pid); m.setword(h + O['REC_DISC'], pid); m.setword(h + O['REC_TYPE'], 4)
        m.playlists.append(h)
        m.card_mounted = True
        if entries is not None: m.fs[PLC] = P.dump(entries)
        m.call(PSYMS['songs_open_playlist'], a0=pid, a1=m.cstr(name), count=900000000)
        SG.settle(m)
        m.calls = []
        return m

    def go_edit(m):
        m.click('btn_more', count=900000000)
        m.click('vs_item7', count=900000000)
        return SG.settle(m)

    badge = lambda blits: [b for b in blits if b[2][2:] == (28, 28)]
    m = edit_page()
    expect(not badge(SG.paint(m)[0]), 'outside Edit the header cover has no badge')
    blits = go_edit(m)[0]
    bb = badge(blits)
    expect(len(bb) == 1 and bb[0][2][:2] == (O['PH_COVER_X'] + PHC - 28 - 6, O['PH_COVER_Y'] + PHC - 28 - 6) and m.images['sg_cbadge'] is not None, f'in Edit a 28 px badge sits on the cover\'s lower right corner ({bb})')
    # a tap on the cover opens the page; one elsewhere in the header does not
    m.calls = []
    SG.tap(m, 40, O['PH_COVER_Y'] + 80)
    expect(('window_open', 'm1plus_plcover') not in m.calls, 'a tap beside the cover opens nothing')
    calls = SG.tap(m, O['PH_COVER_X'] + 80, O['PH_COVER_Y'] + 80)
    expect(('window_open', 'm1plus_plcover') in calls, 'a tap on the cover in Edit opens the Cover page')
    m = edit_page()
    calls = SG.tap(m, O['PH_COVER_X'] + 80, O['PH_COVER_Y'] + 80)
    expect(('window_open', 'm1plus_plcover') not in calls, 'outside Edit a tap on the cover opens nothing')
    go_edit(m)
    m.click('btn_return', count=900000000)   # (Done)
    expect(not badge(SG.settle(m)[0]), 'Done takes the badge away')
    # ---- the page: its thumbnails, one a tick
    m = edit_page()
    go_edit(m)
    SG.tap(m, O['PH_COVER_X'] + 80, O['PH_COVER_Y'] + 80)
    view = m.widgets['pod_cover']
    expect((view, O['EVT_BEFORE_PAINT']) in m.bound and (view, O['EVT_POINTER_DOWN']) in m.bound and (view, O['EVT_POINTER_UP']) in m.bound, 'the page binds the card\'s paint and touch')
    tick = lambda: m.call(PSYMS['pc_tick'], a0=0, count=400000000)
    made = []
    for _ in range(40):
        n0 = len(m.bitmaps)
        m.calls = []
        tick()
        made.append(len(m.bitmaps) - n0)
        if not any(c[0] == 'timer_add' for c in m.calls): break
    expect(max(made) <= 1 and sum(made) >= 6 and not any(c[0] == 'timer_add' for c in m.calls), f'six thumbnails, at most one bitmap a tick, then the timer stops ({made})')

    def page_paint():
        ev = m.paint_event(); m.blits.clear(); m.texts.clear()
        fn, ctx_ = m.bound[(view, O['EVT_BEFORE_PAINT'])]
        m.call(fn, a0=ctx_, a1=ev, count=400000000)
        return list(m.blits)
    blits = page_paint()
    thumbs = [b for b in blits if b[2][2:] == (T, T)]
    ring = [b for b in blits if b[2][2:] == (O['PLP_RING'],) * 2]
    expect(len(thumbs) == 6 and sorted((b[2][0], b[2][1]) for b in thumbs) == sorted((X + k % 3 * PX, k // 3 * PY + TY) for k in range(6)), 'the six thumbnails are painted in a 3 x 2 grid')
    expect(len(ring) == 1 and ring[0][2][:2] == (X - O['PLP_GROW'], TY - O['PLP_GROW']), 'the ring is round the chosen one (Albums, nothing stored)')

    def touch(x, y):
        for kind, evt, t in (('down', 'EVT_POINTER_DOWN', 1000), ('up', 'EVT_POINTER_UP', 1080)):
            e = m.alloc(0x30); m.u.mem_write(e, bytes(0x30)); m.setword(e + 8, t); m.setword(e + 0x18, x); m.setword(e + 0x1c, y)
            fn, c = m.bound[(view, O[evt])]
            m.call(fn, a0=c, a1=e, count=400000000)

    def cell(k): return X + k % 3 * PX + T // 2, k // 3 * PY + TY + T // 2
    entries = lambda: P.parse(m.fs.get(PLC, P.MAGIC))
    m.calls = []
    touch(*cell(3))   # Sunburst
    ents = entries()
    expect(len(ents) == 1 and ents[0][0] == 7 and ents[0][1] == P.SUNBURST and ents[0][2] == 0 and ents[0][5] == 'Road Trip', f'a tap on Sunburst stores it for the playlist at once ({ents})')
    tones = list(ents[0][4])
    ring = [b for b in page_paint() if b[2][2:] == (O['PLP_RING'],) * 2]
    expect(ring and ring[0][2][:2] == (X + 0 * PX - O['PLP_GROW'], PY + TY - O['PLP_GROW']), 'the ring moved to Sunburst')
    sun = [b for b in page_paint() if b[2][2:] == (T, T)]
    st = [b for b in sun if b[2][:2] == (X, PY + TY)]
    expect(st and is_art(m, st[0][0], T, (7, P.SUNBURST, 0, ents[0][3], tuple(tones), 'x'), O['PLP_R']), 'the thumbnail is plc_art at the thumbnail size from the stored tones and seed')
    touch(*cell(3))
    expect(entries() == ents, 'a tap on the chosen one stores it again (the same colours here)')
    # the switch (the stored tones made when the playlist had other albums: the flag alone changes, the colours stay)
    alt = TONES[:1] if len(tones) != 1 else TONES[:2]
    m.fs[PLC] = P.dump([E(7, P.SUNBURST, alt, 'Road Trip', seed=ents[0][3])])
    kept = P.parse(m.fs[PLC])[0][4]
    fn = PSYMS['plcpage_name_toggle']
    expect(m.call(fn, count=40000000) == 1 and entries()[0][2] == 1 and entries()[0][1] == P.SUNBURST and m.call(PSYMS['plcpage_name_on'], count=400000) == 1, 'Name on Cover stores flag bit 0 with the same style')
    expect(entries()[0][4] == kept != tuple(tones), f'the switch keeps the stored tones ({entries()[0][4]} vs now {tones})')
    page_paint()
    onthumb = sorted(r[:2] for tx, r in m.texts if tx == 'Road Trip')
    expect(onthumb == sorted((X + k % 3 * PX + T * 8 // 100, k // 3 * PY + TY + T * 8 // 100) for k in range(1, 6)), f'the switch on: the name is on thumbnails 1..5 and never on Albums ({onthumb})')
    touch(*cell(2))   # Mesh keeps the flag
    expect(entries()[0][1] == P.MESH and entries()[0][2] == 1, 'another style keeps the flag')
    m.calls = []
    expect(m.call(fn, count=40000000) == 0 and entries()[0][2] == 0, 'the switch off clears it')
    expect(('widget_invalidate_force', m.widgets['pod_cover']) in m.calls, 'the switch repaints the card (the names go without another tap)')
    page_paint()
    expect(not [1 for tx, r in m.texts if tx == 'Road Trip'], 'the switch off: no names on the thumbnails')
    # Albums removes the line, and the switch goes off and inert
    touch(*cell(0))
    expect(entries() == [] and m.call(PSYMS['plcpage_name_on'], count=400000) == 0 and m.call(PSYMS['plcpage_style'], count=400000) == 0, 'Albums removes the entry; Name on Cover reads off')
    expect(m.call(fn, count=40000000) == 0xffffffff and entries() == [], 'the switch does nothing for Albums')
    # no card: nothing moves, a toast
    m.card_mounted = False
    m.calls = []
    touch(*cell(4))
    expect(any(c[0] == 'toast' and "Can't change cover" in str(c) for c in m.calls), 'a card that cannot be written: the "Can\'t change cover" toast')
    expect(m.call(PSYMS['plcpage_style'], count=400000) == 0 and entries() == [], 'and nothing moved')
    m.card_mounted = True
    # ---- back on the Songs page: the header shows the choice
    touch(*cell(4))
    ents = entries()
    expect(len(ents) == 1 and ents[0][1] == P.STRIPES, 'Stripes stored')
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    h = [b for b in SG.settle(m)[0] if b[2][2] == PHC]
    expect(len(h) == 1 and is_art(m, h[0][0], PHC, (7, P.STRIPES, 0, ents[0][3], tuple(ents[0][4]), 'x'), PHR), 'back in Edit the header cover is the chosen style')
    SG.tap(m, O['PH_COVER_X'] + 80, O['PH_COVER_Y'] + 80)   # (the page opened again)
    touch(*cell(0))
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    h = [b for b in SG.settle(m)[0] if b[2][2] == PHC]
    expect(len(h) == 1 and not is_art(m, h[0][0], PHC, (7, P.STRIPES, 0, ents[0][3], tuple(ents[0][4]), 'x'), PHR), 'Albums again: the header is the mosaic when the page is back')
    # a renamed playlist keeps its old seed; Albums removes it, so the styles are drawn again with the seed a tap would store now
    m = edit_page([E(7, P.MESH, TONES[:2], 'Road Trip', seed=0x1234abcd)])
    go_edit(m)
    SG.tap(m, O['PH_COVER_X'] + 80, O['PH_COVER_Y'] + 80)
    view = m.widgets['pod_cover']
    for _ in range(40): tick()
    touch(*cell(0))
    for _ in range(40): tick()
    touch(*cell(2))
    ents = entries()
    mesh = [b for b in page_paint() if b[2][:4] == (X + 2 * PX, TY, T, T)]
    expect(len(ents) == 1 and ents[0][3] != 0x1234abcd and mesh and is_art(m, mesh[0][0], T, ents[0], O['PLP_R']), f'Albums then Mesh: the thumbnail is the Mesh stored (seed {ents[0][3]:#x})')
    expect(all(k in pod_i18n.TEXT and set(pod_i18n.TEXT[k]) == set(pod_i18n.LOCALES) for k in ("Can't change cover", 'Solid', 'Mesh', 'Sunburst', 'Stripes', 'Band', 'Name on Cover', 'Colours come from the albums in this playlist.')), 'the new texts exist in the 13 languages')


def name_tests(ctx):
    """Name on Cover: the flag draws the playlist's name (white, top left, inset, at most two lines) wherever a stored cover is shown and the cover is at least GRID_NAME_MIN px; nothing without the flag,
    nothing on the list rows, and a rename shows the new name."""
    expect = ctx.expect
    COVER, LART, PHC, PIN = O['GRID_COVER'], O['LIST_ART'], O['PH_COVER'], O['PIN_COVER']
    expect(LART < 64 <= min(O['PLP_T'], PIN, COVER, PHC), 'the threshold keeps the 52 px list rows out and every cover tile in')
    ins = lambda side: side * 8 // 100
    cov = lambda flags, name='Road': E(7, P.SOLID, TONES[:1], name, flags=flags)
    # ---- the Playlists page
    for mode, side in (('grid', COVER), ('list', LART)):
        for flags in (0, 1):
            m = PL.PM([(3, 'Night', [0, 1, 2]), (7, 'Road', [0, 1])])
            if mode == 'list': m.fs[PL.PL_FILE] = b'0\n'
            m.fs[PLC] = P.dump([cov(flags)])
            PL.open_page(m)
            texts = PL.settle(m)[1]
            got = [(tx, r) for tx, r in texts if tx == 'Road' and r[2] != COVER and r[2] != 204 and r[3] == 22]
            want = mode == 'grid' and flags == 1
            expect(bool(got) == want and (not got or got[0][1][0] == O['GRID_MARGIN'] + COVER + O['GRID_GAP'] + ins(COVER)),
                   f'the Playlists page ({mode}, flag {flags}): the name is drawn on the cover only in the grid with the flag ({got})')
    # the tiles are a ring keyed by the playlist, not its index: scrolled down a long page (the ring reused), the name is on its own playlist's cover and no other
    k = 25
    m = PL.PM([(100 + i, f'P{i:02d}', [i % 8, (i + 1) % 8]) for i in range(30)])   # (the page sorts by title: the names keep the order)
    m.fs[PLC] = P.dump([E(100 + k, P.SOLID, TONES[:1], f'P{k}', flags=1)])
    PL.open_page(m)
    PL.settle(m)
    off = (k // PL.COLS - 1) * PL.PITCH
    PL.scroll_to(m, off)
    blits, texts = PL.settle(m)[:2]
    got = [(tx, r) for tx, r in texts if r[3] == 22 and r[2] != COVER and r[2] != 204]
    cx, cy = PL.MARGIN + (k % PL.COLS) * PL.CPITCH, PL.R0 + (k // PL.COLS) * PL.PITCH - off
    expect(len(got) == 1 and got[0][0] == f'P{k}' and got[0][1][0] == cx + ins(COVER) and cy <= got[0][1][1] < cy + COVER and PL.cell_blit(blits, k, off) is not None,
           f'a long page scrolled down: the name is drawn on its playlist\'s cover only ({got})')
    # ---- the Songs header
    titles = ['Zed', 'Alpha', 'Mike', 'Bravo', 'Echo', 'Yankee', 'Delta', 'Kilo']

    def songs_page(entries, name='Road Trip'):
        m = SG.list_machine(titles); m.playlist_songs = {7: list(m.songs[:5])}
        m.widget('label_grid_title')
        m.fs[PLC] = P.dump(entries)
        m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr(name), count=900000000)
        return m
    for flags in (0, 1):
        m = songs_page([cov(flags, 'Road Trip')])
        texts = SG.settle(m)[1]
        got = [(tx, r) for tx, r in texts if tx == 'Road Trip' and r[2] == 72]
        expect(bool(got) == bool(flags) and (not got or got[0][1][0] == O['PH_COVER_X'] + ins(PHC)), f'the Songs header (flag {flags}): the name is drawn on the cover only with the flag ({got})')
    import mod_icons
    m = SG.list_machine(titles); m.playlist_songs = {7: []}   # an empty playlist (the Add Songs row): the name stays on its cover
    m.widget('label_grid_title')
    si = mod_icons.songs_images()
    for k in mod_icons.SG_ADD: m.images[k] = (LART,) * 2 + (b''.join(struct.pack('<4B', c, c, c, 255) for c in si[k].getchannel('A').tobytes()),)
    h = m.record(path='', title='Road Trip', name='Road Trip', rid=7); m.setword(h + O['REC_DISC'], 7); m.setword(h + O['REC_TYPE'], 4); m.playlists.append(h)
    m.fs[PLC] = P.dump([cov(1, 'Road Trip')])
    m.call(PSYMS['songs_open_playlist'], a0=7, a1=m.cstr('Road Trip'), count=900000000)
    texts = SG.settle(m)[1]
    expect(any(tx == 'Add Songs' for tx, r in texts) and [tx for tx, r in texts if r[0] == O['PH_COVER_X'] + ins(PHC)] == ['Road Trip'], f'an empty playlist: the name is on its cover ({texts})')
    m = songs_page([cov(1, 'Road Trip')])
    SG.settle(m)
    m.setword(PSYMS['sg_rn_id'], 7); m.setword(PSYMS['sg_rn_on'], 1)
    h = m.record(path='', title='Road Trip', name='Road Trip', rid=7); m.setword(h + O['REC_DISC'], 7); m.playlists.append(h)
    m.call(PSYMS['sg_renamed'], a0=m.cstr('Evening'), count=900000000)
    texts = SG.settle(m)[1]
    expect([tx for tx, r in texts if r[2] == 56 and r[0] == O['PH_COVER_X'] + ins(PHC)] == ['Evening']  and P.parse(m.fs[PLC])[0][2] == 1, 'a rename: the header cover shows the new name and the flag stays')
    # a long name: two lines, the last one cut with an ellipsis; CJK breaks per character
    m = songs_page([cov(1, 'Alpha Beta Gamma Delta Epsilon Zeta Eta Theta')], 'Alpha Beta Gamma Delta Epsilon Zeta Eta Theta')
    texts = [(tx, r) for tx, r in SG.settle(m)[1] if r[0] == O['PH_COVER_X'] + ins(PHC)]
    expect(len(texts) == 2 and texts[0][0] == 'Alpha Beta Gamma' and texts[1][0].endswith('\u2026') and texts[1][1][1] - texts[0][1][1] in (18, 22) and all(r[2] <= PHC - 2 * ins(PHC) for _, r in texts), f'a long name: two lines, the last cut with an ellipsis ({texts})')
    name = '\u6f20' * 20
    m = songs_page([cov(1, name)], name)
    texts = [(tx, r) for tx, r in SG.settle(m)[1] if r[0] == O['PH_COVER_X'] + ins(PHC)]
    expect(len(texts) == 2 and texts[0][0] == name[:17] and texts[1][0] == name[17:], f'CJK breaks per character ({texts})')
    # ---- a Home pin
    pc = PN.playlist(3, 'Late', (11, 22, 33))
    for flags in (0, 1):
        m = PN.PH(entries=[pc]); m.fs[PLC] = P.dump([E(3, P.MESH, TONES, 'Late', flags=flags, seed=5)]); m.begin()
        m.call(PSYMS['pn_first'], count=400000000)
        n = 0
        while m.call(PSYMS['pn_tick'], a0=0, count=400000000) == O['RET_REPEAT'] and n < 12: n += 1
        e = m.alloc(0x40); m.u.mem_write(e, bytes(0x40)); m.setword(e + O['EVENT_PAINT_CANVAS'], 0x22220000)
        m.texts.clear(); m.call(PSYMS['pn_on_paint'], a0=0, a1=e, count=400000000)
        got = [(tx, r) for tx, r in m.texts if tx == 'Late' and r[3] == 18]
        x0 = [r[0] for tx, r in m.texts if tx == 'Late' and r[3] == 20][0]
        expect(bool(got) == bool(flags) and (not got or got[0][1][0] == x0 + ins(PIN)), f'a Home pin (flag {flags}): the name is drawn on the cover only with the flag ({got})')
    m.call(PSYMS['pins_rename_playlist'], a0=3, a1=m.cstr('Late'), a2=m.cstr('Evening'), count=40000000)
    m.call(PSYMS['plc_rename'], a0=3, a1=m.cstr('Late'), a2=m.cstr('Evening'), count=40000000)
    m.call(PSYMS['pn_on_foreground'], a0=m.root, a1=0, count=8000000)
    n = 0
    while m.call(PSYMS['pn_tick'], a0=0, count=400000000) == O['RET_REPEAT'] and n < 12: n += 1
    m.texts.clear(); m.call(PSYMS['pn_on_paint'], a0=0, a1=e, count=400000000)
    expect([tx for tx, r in m.texts if tx == 'Evening' and r[3] == 18 and r[0] == x0 + ins(PIN)] == ['Evening'], 'a renamed pin\'s cover shows the new name')


SECTIONS = [tables_tests, art_tests, look_tests, cost_tests, file_tests, api_tests, draw_tests, name_tests, page_tests]
