#!/usr/bin/env python3
"""Host build of Cover Flow's depth renderer and the cover cache's pixel helpers, with checks and PNG captures.

The same patch/coverflow.c and patch/covercache.c that go into the payload are compiled for the host with
-DCF_HOST (which drops everything that talks to demo) and driven through ctypes, so the geometry, the
compositing, the texture sampling, the grid's box-filter tile reduction and the cache key are tested without
a device. Modelled on q2-pod's test/coverflow.py.

  uv run python -I test/coverflow.py [--captures DIR] [--preview PNG]

--captures writes the raw CF_VIEW_W x CF_VIEW_H frames at rest and part-way through a turn;
--preview composes the 320x480 page around one of them (approximate: PIL, not AWTK).
"""
import argparse, collections, ctypes, os, struct, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import cdefs  # noqa: E402
import pod_ui  # noqa: E402  (the page layout: COVER_Y, ALBUM_Y, ARTIST_Y)
SRC = [os.path.join(ROOT, 'patch', f) for f in ('coverflow.c', 'covercache.c')]
INC = os.path.join(ROOT, 'patch', 'offsets.inc')

C = cdefs.defines(INC)   # the CF_* geometry the payload is built with
W, H, ART, CX = C['CF_VIEW_W'], C['CF_VIEW_H'], C['ART_SIZE'], C['CF_CX']
TOP, REFLECT = C['CF_TOP'], C['CF_REFLECT']
ONE, REACH, RING = 65536, 3, 7
TEXELS = ART * ART


AR_EMIT = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte))   # ar_emit_t


def build(tmp):
    so = os.path.join(tmp, 'coverflow.so')
    subprocess.run(['cc', '-O2', '-std=c99', '-Wall', '-DCF_HOST',
                    '-shared', '-fPIC', '-I', os.path.join(ROOT, 'patch'), *SRC, '-o', so], check=True)
    lib = ctypes.CDLL(so)
    lib.coverflow_render.restype = None
    lib.coverflow_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.c_int, ctypes.c_int,
                                     ctypes.POINTER(ctypes.c_void_p)]
    lib.portrait = ctypes.addressof(ctypes.c_int.in_dll(lib, 'cf_portrait'))   # the shelves' geometry (cfg_t)
    lib.land = ctypes.addressof(ctypes.c_int.in_dll(lib, 'cf_land'))
    lib.cc_fnv.restype = ctypes.c_uint
    lib.cc_fnv.argtypes = [ctypes.c_uint, ctypes.c_char_p]
    lib.ar_init.restype = ctypes.c_int
    lib.ar_init.argtypes = [ctypes.c_void_p] + [ctypes.c_uint] * 4
    lib.ar_push.restype = None
    lib.ar_push.argtypes = [ctypes.c_void_p, ctypes.c_char_p] + [ctypes.c_uint] * 5 + [AR_EMIT, ctypes.c_void_p]
    lib.cc_stock_fit.restype = ctypes.c_int
    lib.cc_stock_fit.argtypes = [ctypes.c_uint] * 3 + [ctypes.POINTER(ctypes.c_uint)] * 2
    lib.cc_stock_dims.restype = None
    lib.cc_stock_dims.argtypes = [ctypes.c_uint] * 3 + [ctypes.POINTER(ctypes.c_uint)] * 2
    lib.cc_fit.restype = ctypes.c_int   # the timed cover page's whole-picture fit (patch/bigcover.c)
    lib.cc_fit.argtypes = [ctypes.c_char_p] + [ctypes.c_uint] * 3 + [ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
    for f in (lib.cc_sample, lib.cc_box):
        f.restype = None
        f.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                      ctypes.c_char_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
    return lib


def texture(colour, mark=0):
    """A flat cover with a brighter band, so turns and mirroring are visible."""
    buf = (ctypes.c_uint * TEXELS)()
    r, g, b = colour
    for y in range(ART):
        for x in range(ART):
            v = (r, g, b)
            if y < 10 or y >= ART - 10 or x < 10 or x >= ART - 10: v = (240, 240, 240)
            if mark and (x // 16 + y // 16) % 2 == 0: v = (v[0] // 2, v[1] // 2, v[2] // 2)
            buf[y * ART + x] = 0xff000000 | v[0] | v[1] << 8 | v[2] << 16
    return buf


def render(lib, frac, texs, cfg=None, pw=W, ph=H):
    """The portrait frame (W x H), or with cfg (lib.land, or a CFG copy) the pw x ph one of that shelf."""
    frame = (ctypes.c_uint * (pw * ph))()
    ring = (ctypes.c_void_p * RING)()
    for i, t in enumerate(texs):
        ring[i] = ctypes.cast(t, ctypes.c_void_p) if t is not None else None
    lib.coverflow_render(ctypes.addressof(cfg) if isinstance(cfg, CFG) else cfg or lib.portrait, frame, pw, frac, ring)
    return frame


class CFG(ctypes.Structure):
    """patch/coverflow.c cfg_t."""
    _fields_ = [(n, ctypes.c_int) for n in ('w', 'h', 'cx', 'top', 'art', 'eye', 'x1', 'xs', 'z1', 'zs', 'reflect', 'rot', 'turn', 'tail', 'bg')]


def land_cfg(lib, rot=1):
    """A copy of the landscape shelf's geometry, turned (the device) or not (to compare the two)."""
    cfg = CFG.from_address(lib.land)
    out = CFG(*[getattr(cfg, n) for n, _ in CFG._fields_])
    out.rot = rot
    return out


def px(frame, x, y):
    v = frame[y * W + x]
    return v & 255, v >> 8 & 255, v >> 16 & 255, v >> 24 & 255


def save(frame, path):
    from PIL import Image
    img = Image.new('RGB', (W, H))
    img.putdata([(frame[i] & 255, frame[i] >> 8 & 255, frame[i] >> 16 & 255) for i in range(W * H)])
    img.save(path)


def landscape(lib, frac, texs):
    """The landscape shelf as the user sees it (CFL_W x CFL_H, the content
    turned 90 degrees clockwise): the turned physical frame, turned back."""
    from PIL import Image
    pw, ph = C['CFL_H'], C['CFL_W']
    frame = render(lib, frac, texs, land_cfg(lib), pw, ph)
    img = Image.new('RGB', (pw, ph))
    img.putdata([(v & 255, v >> 8 & 255, v >> 16 & 255) for v in frame])
    return img.transpose(Image.ROTATE_90)


def layout():
    """(frame y, album y, album h, artist y, artist h) of the page this shelf is on."""
    return pod_ui.cover_layout()


def preview(frame, path, album='Kind of Blue', artist='Miles Davis', title='Cover Flow'):
    """The whole 320x480 page around a rendered frame: status bar gap, navbar, captions, laid out
    as tools/pod_ui.py builds ui/m1plus_cover.bin (the window starts under the 30 px status bar,
    drawn here as black). Approximate."""
    from PIL import Image, ImageDraw, ImageFont
    page = Image.new('RGB', (320, 480), (0, 0, 0))
    covers = Image.new('RGB', (W, H))
    covers.putdata([(frame[i] & 255, frame[i] >> 8 & 255, frame[i] >> 16 & 255) for i in range(W * H)])
    top = 480 - pod_ui.CLIENT_H      # the window under the status bar
    fy, ay, _, ry, _ = layout()
    page.paste(covers, (0, top + fy))
    d = ImageDraw.Draw(page)

    def font(size):
        for p in ('/System/Library/Fonts/Helvetica.ttc', '/Library/Fonts/Arial.ttf'):
            if os.path.exists(p):
                try: return ImageFont.truetype(p, size)
                except OSError: pass
        return ImageFont.load_default()

    def centred(text, y, size, colour):
        f = font(size)
        w = d.textbbox((0, 0), text, font=f)[2]
        d.text(((320 - w) // 2, y), text, font=f, fill=colour)

    d.rectangle([0, top, 319, top + 49], fill=(0, 0, 0))
    d.line([(0, top + 49), (319, top + 49)], fill=(30, 30, 30))
    d.polygon([(28, top + 25), (40, top + 17), (40, top + 33)], fill=(220, 220, 220))   # Back chevron
    d.ellipse([272, top + 13, 296, top + 37], outline=(220, 220, 220))                  # Now Playing
    centred(title, top + 14, 20, (255, 255, 255))
    centred(album, top + ay + 5, 22, (255, 255, 255))
    centred(artist, top + ry + 4, 18, (170, 170, 170))
    page.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--captures'); ap.add_argument('--preview')
    a = ap.parse_args()
    ok = fail = 0

    def expect(cond, msg):
        nonlocal ok, fail
        if cond: ok += 1
        else: fail += 1; print('  FAIL:', msg)

    with tempfile.TemporaryDirectory() as tmp:
        lib = build(tmp)
        colours = [(200, 60, 60), (60, 160, 200), (230, 190, 70), (120, 200, 120),
                   (200, 120, 200), (90, 90, 220), (210, 140, 60)]
        texs = [texture(c, mark=i == REACH) for i, c in enumerate(colours)]

        # 1. At rest the centre cover is its texture, pixel for pixel, at the expected place.
        rest = render(lib, 0, texs)
        x0, y0 = CX - ART // 2, TOP
        same = all(rest[(y0 + y) * W + x0 + x] == texs[REACH][y * ART + x] for y in range(ART)
                   for x in range(0, ART, 7))
        expect(same, 'the centre cover is drawn 1:1 from its texture')

        # 2. Nothing is drawn above the frame, and every pixel is opaque black or cover.
        expect(all(px(rest, x, 0)[3] == 255 for x in range(0, W, 3)), 'the frame is opaque')
        expect(all(rest[0 * W + x] & 0xffffff == 0 for x in range(0, W, 3)), 'top row is black')
        expect(all(rest[(H - 1) * W + x] & 0xffffff == 0 for x in range(0, W, 3)),
               'bottom row is black (reflections fade out above it)')

        # 3. At rest, with one mirror-symmetric texture in every slot, the shelf is symmetric
        #    about the centre line (the renderer mirrors left covers onto right ones).
        flat = texture((200, 60, 60))
        sym = render(lib, 0, [flat] * RING)
        mirrored = all(sym[y * W + x] == sym[y * W + (2 * CX - 1 - x)]
                       for y in range(0, H, 5) for x in range(0, CX, 5))
        expect(mirrored, 'the shelf is mirror-symmetric at rest')

        # 4. Brightness falls with distance: the same cover alone in each ring slot, so nothing
        #    overlaps it, is dimmer one out than at the centre and dimmer still two out.
        def alone_at(j):
            ring = [None] * RING
            ring[j] = flat
            f = render(lib, 0, ring)
            return max(max(px(f, x, y)[:3]) for y in range(0, H, 3) for x in range(0, W, 2))
        b0, b1, b2, b3 = (alone_at(REACH + k) for k in range(4))
        expect(b0 == 240, f'the centre cover keeps its own pixels ({b0})')
        expect(b1 == 240 * C['CF_BRIGHT1'] // 256, f'one cover out is CF_BRIGHT1 ({b1})')
        expect(b2 == 240 * C['CF_BRIGHT2'] // 256, f'two covers out are CF_BRIGHT2 ({b2})')
        expect(b3 == 0, 'three covers out have faded away')

        # 5. A cover has a reflection under it: the rows just below its bottom edge are not black.
        refl = [sum(px(rest, CX, TOP + ART + k)[:3]) for k in range(1, REFLECT)]
        expect(any(v > 0 for v in refl), 'the centre cover reflects')
        expect(refl[0] >= refl[-1], 'the reflection fades downwards')

        # 6. A small step changes the frame only a little; half a step is still symmetric about
        #    the pair of covers that share the centre.
        small = render(lib, ONE // 64, texs)
        n = len(range(0, W * H, 11))
        drift = sum(max(abs(a - b) for a, b in zip(px(small, i % W, i // W), px(rest, i % W, i // W)))
                    for i in range(0, W * H, 11)) / n
        expect(drift < 12, f'a 1/64 step moves the frame only a little (mean |delta| {drift:.1f})')
        half = render(lib, ONE // 2, texs)
        expect(any(half[i] != rest[i] for i in range(0, W * H, 7)), 'half a step differs from rest')

        # 7. A missing texture (no art decoded) leaves its slot empty without disturbing the rest.
        gap = list(texs); gap[REACH + 1] = None
        hole = render(lib, 0, gap)
        expect(all(hole[(y0 + y) * W + x0 + x] == rest[(y0 + y) * W + x0 + x]
                   for y in range(0, ART, 9) for x in range(0, ART, 9)),
               'a missing neighbour does not change the centre cover')

        # 8. Only the centre cover: no neighbours, no crash, still symmetric.
        alone = render(lib, 0, [None] * REACH + [texs[REACH]] + [None] * REACH)
        expect(alone[(y0 + 5) * W + x0 + 5] == texs[REACH][5 * ART + 5], 'a one-album library draws')

        # 8b. Every shelf: the side covers still show either side of the centre cover, and nothing
        #     is drawn below the reflections, where the captions lie (the page's layout).
        side = [x for x in range(0, CX - ART // 2) if any(rest[y * W + x] & 0xffffff for y in range(0, H, 2))]
        expect(len(side) >= 40, f'the left side covers show beside the centre cover ({len(side)} columns)')
        fy, ay, _, ry, rh = layout()
        below = range(TOP + ART + REFLECT, H)
        expect(all(rest[y * W + x] & 0xffffff == 0 for y in below for x in range(0, W, 3)),
               'nothing is drawn under the reflections')
        expect(fy + TOP + ART + REFLECT <= ay and ry + rh <= pod_ui.CLIENT_H,
               f'the captions sit under the reflections, inside the 450 px window ({ay}, {ry + rh})')

        # 8c. Landscape: the same renderer into a window-sized bitmap turned a quarter (the logical x
        #     along the 450 px side, logical (x, y) at physical (CFL_H - 1 - y, x)).
        LW, LH, LA, LCX, LTOP, LREFL = C['CFL_W'], C['CFL_H'], ART, C['CFL_CX'], C['CFL_TOP'], REFLECT
        turned = land_cfg(lib, 1)
        land = render(lib, 0, texs, turned, LH, LW)            # physical LH wide, LW high

        def lp(frame, x, y): return frame[x * LH + LH - 1 - y]   # the logical pixel of a turned frame

        straight = render(lib, 0, texs, land_cfg(lib, 0), LW, LH)  # the same shelf not turned
        expect(all(lp(land, x, y) == straight[y * LW + x] for y in range(0, LH, 3) for x in range(0, LW, 2)),
               'the turned frame is the straight one, pixel for pixel, through the quarter-turn map')
        half_l = render(lib, ONE // 3, texs, turned, LH, LW)
        half_s = render(lib, ONE // 3, texs, land_cfg(lib, 0), LW, LH)
        expect(all(lp(half_l, x, y) == half_s[y * LW + x] for y in range(0, LH, 3) for x in range(0, LW, 2)),
               'and part-way through a turn')
        expect(all(land[i] >> 24 == 255 for i in range(0, LW * LH, 7)), 'the landscape frame is opaque')
        inside = lp(land, LCX, LTOP + LA // 2)                 # the middle of the centre cover: the texture's flat colour
        border = lp(land, LCX - LA // 2 + 3, LTOP + LA // 2)  # 3 px in from its edge: the 240 grey frame
        expect((inside & 255, inside >> 8 & 255, inside >> 16 & 255) in (colours[REACH], tuple(v // 2 for v in colours[REACH])),
               f'the centre cover is on the horizon at the middle of the landscape frame ({inside:06x})')
        expect((border & 255, border >> 8 & 255, border >> 16 & 255) == (240, 240, 240),
               'and its edge lies LA / 2 px from the centre line')
        expect(lp(land, LCX, LTOP - 2) & 0xffffff == 0 and lp(land, LCX, LTOP + LA + LREFL + 4) & 0xffffff == 0,
               'nothing above the cover, nor below its reflection')
        expect(all(lp(land, x, y) & 0xffffff == 0 for y in range(LTOP + LA + LREFL, LH) for x in range(0, LW, 5)),
               'the rows under the reflections are black, for the captions')
        flat_l = render(lib, 0, [flat] * RING, turned, LH, LW)
        expect(all(lp(flat_l, x, y) == lp(flat_l, LW - 1 - x, y) for y in range(0, LH, 7) for x in range(0, LCX, 5)),
               'the landscape shelf is mirror-symmetric about the centre line')
        lit = [x for x in range(0, LCX - LA // 2) if any(lp(land, x, y) & 0xffffff for y in range(0, LH, 3))]
        expect(len(lit) >= 100 and len(lit) >= len(side) + 20,
               f'more of the side covers show than in portrait ({len(lit)} columns against {len(side)})')

        # 8d. Occlusion mid-turn, both shelves: every cover is drawn alone (a flat colour of its own, so its body is the
        #     commonest pixel value) and in the shelf; wherever the nearest cover's body is, the shelf shows exactly that,
        #     so no farther cover ever lands on a nearer one (nearest is by distance from the visual position).
        flats = [texture(c, mark=0) for c in colours]
        for v in flats:                                             # no border: the body is one flat value per cover
            for i in range(TEXELS): v[i] = v[ART * (ART // 2) + ART // 2]
        shelves = ((lib.portrait, W, H, lambda f, x, y: f[y * W + x]),
                   (land_cfg(lib), LH, LW, lambda f, x, y: f[x * LH + LH - 1 - y]))
        for cfg, pw, ph, at in shelves:
            gw, gh = (W, H) if cfg is lib.portrait else (LW, LH)
            for frac in (0, ONE // 4, -ONE // 4, ONE // 2 - 100, -ONE // 2 + 100, ONE // 3):
                bodies = []                                         # (distance, {(x, y): value}) per cover
                for j in range(RING):
                    one = [None] * RING; one[j] = flats[j]
                    f = render(lib, frac, one, cfg, pw, ph)
                    vals = {}
                    for y in range(gh):
                        for x in range(gw): vals[(x, y)] = at(f, x, y) & 0xffffff
                    mode = next((v for v, _ in collections.Counter(vals.values()).most_common() if v), 0)
                    bodies.append((abs((j - REACH) * ONE - frac), mode, {p for p, v in vals.items() if v == mode},
                                   {p for p, v in vals.items() if v}))
                shelf = render(lib, frac, flats, cfg, pw, ph)
                wrong = 0
                for dist, mode, body, _ in bodies:
                    for (x, y) in body:   # unless something nearer is drawn there (body, edge or reflection)
                        if not any(d < dist and (x, y) in lit for d, _, _, lit in bodies) and at(shelf, x, y) & 0xffffff != mode:
                            wrong += 1
                expect(wrong == 0, f'{"portrait" if cfg is lib.portrait else "landscape"} frac {frac}: '
                       f'{wrong} body pixels show a farther cover or a mixture where a nearer cover is not')

        # 8d. cfg.bg: the frame over a colour. 0 is over black (the same bytes as the shelf itself); white turns the fade into a blend
        #     towards white (the covers stay opaque) and ends on white where no cover is, never grey covers or black gaps.
        def with_bg(base, bg):
            c = CFG.from_address(base)
            out = CFG(*[getattr(c, n) for n, _ in CFG._fields_])
            out.bg = bg
            return out
        expect(CFG.from_address(lib.portrait).bg == 0 and CFG.from_address(lib.land).bg == 0, 'the stock shelves are over black (bg 0)')
        black = render(lib, ONE // 5, texs)
        expect(list(render(lib, ONE // 5, texs, with_bg(lib.portrait, 0))) == list(black), 'bg 0 renders the shelf as it was')
        white = render(lib, ONE // 5, texs, with_bg(lib.portrait, 0xffffff))
        expect(all(v >> 24 == 255 for v in white), 'over white the frame is opaque')
        expect(all(white[x] == 0xffffffff for x in range(W)) and white[(H - 1) * W] == 0xffffffff and white[(H - 1) * W + W - 1] == 0xffffffff, 'no cover: the pixel is white (top row, bottom corners)')
        rest_w, rest_b = render(lib, 0, texs, with_bg(lib.portrait, 0xffffff)), render(lib, 0, texs)
        expect(all(rest_w[(TOP + ART // 2) * W + x] == rest_b[(TOP + ART // 2) * W + x] for x in range(CX - ART // 4, CX + ART // 4)), 'the centre cover at rest is unfaded over either')
        chan = lambda v: (v & 255, v >> 8 & 255, v >> 16 & 255)
        mid = (TOP + ART // 2) * W
        lighter = bad = 0
        for x in range(W):
            b, w = chan(black[mid + x]), chan(white[mid + x])
            if any(wc < bc for wc, bc in zip(w, b)): bad += 1
            if any(wc > bc + 20 for wc, bc in zip(w, b)): lighter += 1
        expect(bad == 0 and lighter > 100, f'the dimmed side covers blend towards white, not black: never darker than over black ({bad} darker), clearly lighter on {lighter} of {W} columns')
        side = [None] * RING; side[REACH + 2] = texture((200, 60, 60))
        ws = render(lib, 0, side, with_bg(lib.portrait, 0xffffff)); bs = render(lib, 0, side)
        hit = [i for i in range(mid, mid + W) if bs[i] & 0xffffff]
        wp, bp = chan(ws[hit[len(hit) // 2]]), chan(bs[hit[len(hit) // 2]])
        expect(hit and wp[0] > 150 and wp[1] > bp[1] + 100 and wp[1] > 100 and wp[1] < 255, f'a cover two out over white is its colour thinned towards white ({wp}), over black dimmed ({bp})')
        near = [None] * RING; near[REACH + 1] = texture((200, 60, 60))
        both = list(near); both[REACH + 2] = texture((60, 60, 200))
        wn, wb = render(lib, 0, near, with_bg(lib.portrait, 0xffffff)), render(lib, 0, both, with_bg(lib.portrait, 0xffffff))
        under = [i for i in range(mid, mid + W) if wn[i] != 0xffffffff]
        expect(under and all(wb[i] == wn[i] for i in under), 'over white a faded side cover is still opaque: the cover behind it does not show through')
        lite = with_bg(lib.portrait, 0); lite.tail = 208
        for k, lo in ((2, 170), (3, 158)):
            one = [None] * RING; one[REACH + k] = texture((200, 60, 60))
            reds = [chan(v)[0] for v in render(lib, 0, one, lite) if v & 255]
            expect(reds and max(reds) >= lo, f'tail: a cover {k} out barely dims, as on the iPod (red {max(reds) if reds else 0} of 200, want >= {lo})')
        flatw = texture((255, 255, 255))
        for i in range(TEXELS): flatw[i] = 0xffffffff
        wf = render(lib, ONE // 3, [flatw] * RING, with_bg(lib.portrait, 0xffffff))
        expect(all(min(chan(v)) >= 244 for v in wf), f'white covers over white: all within the 1-per-layer rounding of white, no channel overflows into a dark pixel or leaves a seam (darkest {min(min(chan(v)) for v in wf)})')
        gap = render(lib, ONE // 7, texs, with_bg(lib.portrait, 0x336699))
        expect(chan(gap[0]) == (0x99, 0x66, 0x33) and gap[0] >> 24 == 255, 'any colour: the corner is the bg (r | g << 8 | b << 16), opaque')

        # 9. The cache key: FNV-1a of artist then album, each with a separator, never 0.
        def fnv(h, s):
            for c in s.encode(): h = (h ^ c) * 16777619 & 0xffffffff
            return h * 16777619 & 0xffffffff
        for artist, album in (('Miles Davis', 'Kind of Blue'), ('', ''), ('a', 'bc'), ('ab', 'c')):
            want = fnv(fnv(C['FNV_SEED'], artist), album)
            got = lib.cc_fnv(lib.cc_fnv(C['FNV_SEED'], artist.encode()), album.encode())
            expect(got == want, f'cc_fnv({artist!r}, {album!r})')
        expect(lib.cc_fnv(C['FNV_SEED'], b'a') != lib.cc_fnv(C['FNV_SEED'], b'b'), 'keys differ')
        expect(fnv(fnv(C['FNV_SEED'], 'ab'), 'c') != fnv(fnv(C['FNV_SEED'], 'a'), 'bc'),
               'the separator keeps "ab"+"c" and "a"+"bc" apart')

        # 10. cc_sample: the centred square of a wide image, nearest sampled, alpha over black.
        src_w, src_h = 2 * ART, ART
        src = bytearray(src_w * src_h * 4)
        for y in range(src_h):
            for x in range(src_w):
                inside = ART // 2 <= x < ART // 2 + ART
                src[(y * src_w + x) * 4:(y * src_w + x) * 4 + 4] = bytes(
                    (255, 0, 0, 255) if inside else (0, 255, 0, 255))
        out = (ctypes.c_uint * TEXELS)()
        lib.cc_sample(bytes(src), src_w, src_h, src_w * 4, bytes((0, 1, 2, 3)), ART, out)
        expect(all(out[i] == 0xff0000ff for i in range(0, TEXELS, 97)),
               'cc_sample takes the centred square')
        half_alpha = bytes((10, 20, 30, 128)) * (src_w * src_h)
        lib.cc_sample(half_alpha, src_w, src_h, src_w * 4, bytes((0, 1, 2, 3)), ART, out)
        expect(out[0] == 0xff000000 | 5 | 10 << 8 | 15 << 16, 'cc_sample composes alpha over black')

        # 11. cc_box, the grid's tile reduction (168 -> GRID_COVER): the same centred square, but an area average.
        tile = C['GRID_COVER']
        rgba = bytes((0, 1, 2, 3))
        box = (ctypes.c_uint * (tile * tile))()
        lib.cc_box(bytes(src), src_w, src_h, src_w * 4, rgba, tile, box)
        expect(all(box[i] == 0xff0000ff for i in range(0, tile * tile, 31)), 'cc_box takes the centred square')
        flat_img = bytes((10, 200, 90, 255)) * (ART * ART)
        lib.cc_box(flat_img, ART, ART, ART * 4, rgba, tile, box)
        expect(all(box[i] == 0xff000000 | 10 | 200 << 8 | 90 << 16 for i in range(tile * tile)),
               'cc_box keeps a flat colour exactly, edge to edge')
        # a 1 px chequer of black and white averages to mid grey where every box holds both; nearest sampling
        # shows one of the two
        chequer = bytearray()
        for y in range(ART):
            for x in range(ART):
                chequer += bytes((255, 255, 255, 255) if (x + y) % 2 else (0, 0, 0, 255))
        half_box = (ctypes.c_uint * (ART // 2) ** 2)()
        lib.cc_box(bytes(chequer), ART, ART, ART * 4, rgba, ART // 2, half_box)
        expect(all(v & 0xffffff == 0x808080 for v in half_box), 'cc_box at 2:1 averages a chequer to mid grey (127.5 rounds up)')
        lib.cc_box(bytes(chequer), ART, ART, ART * 4, rgba, tile, box)
        greys = [box[i] & 255 for i in range(tile * tile)]
        expect(min(greys) < 100 and max(greys) > 155, f'cc_box at 7:6 leaves the chequer contrast a box that size has ({min(greys)}..{max(greys)}), not blurred over two pixels')
        nearest = (ctypes.c_uint * (tile * tile))()
        lib.cc_sample(bytes(chequer), ART, ART, ART * 4, rgba, tile, nearest)
        expect({v & 255 for v in nearest} <= {0, 255}, 'cc_sample keeps the chequer hard')
        # exactly 2:1, each output pixel is the mean of its 2 x 2 block
        two = bytearray()
        for y in range(8):
            for x in range(8):
                two += bytes((x * 30, y * 30, (x + y) * 10, 255))
        out4 = (ctypes.c_uint * 16)()
        lib.cc_box(bytes(two), 8, 8, 32, rgba, 4, out4)
        want = lambda bx, by: (sum((bx * 2 + i) * 30 for i in range(2)) // 2, sum((by * 2 + j) * 30 for j in range(2)) // 2)
        expect(all(out4[by * 4 + bx] & 255 == want(bx, by)[0] and out4[by * 4 + bx] >> 8 & 255 == want(bx, by)[1]
                   for by in range(4) for bx in range(4)), 'cc_box at 2:1 is the 2 x 2 block mean')
        same_size = (ctypes.c_uint * 64)()
        lib.cc_box(bytes(two), 8, 8, 32, rgba, 8, same_size)
        expect(all(same_size[i] & 0xffffff == (two[i * 4] | two[i * 4 + 1] << 8 | two[i * 4 + 2] << 16) for i in range(64)),
               'cc_box at 1:1 is the image')
        lib.cc_box(half_alpha, src_w, src_h, src_w * 4, rgba, tile, box)
        expect(box[0] == 0xff000000 | 5 | 10 << 8 | 15 << 16, 'cc_box composes alpha over black')
        # a row of the wide image's stride is respected (padding bytes after each line are never read)
        padded = bytearray()
        for y in range(4):
            padded += bytes((50, 60, 70, 255)) * 4 + bytes((255, 255, 255, 255)) * 2
        out2 = (ctypes.c_uint * 4)()
        lib.cc_box(bytes(padded), 4, 4, 24, rgba, 2, out2)
        expect(all(v == 0xff000000 | 50 | 60 << 8 | 70 << 16 for v in out2), 'cc_box honours the stride')

        # 11b. cc_fit, the timed cover page's fit: the whole picture inside size x size over a background, never cropped.
        def fit(w, h, img, size, bg=0xff141414, stride=None, order=rgba):
            o = (ctypes.c_uint * (size * size))()
            ok = lib.cc_fit(bytes(img), w, h, stride or w * 4, order, size, bg, o)
            return ok, list(o)
        edge = bytearray()
        for y in range(40):
            for x in range(60):
                edge += bytes((x * 4, y * 6, (x + y) & 255, 255))
        ok, o = fit(60, 40, edge, 60)
        expect(ok and all(o[(10 + y) * 60 + x] == 0xff000000 | x * 4 | y * 6 << 8 | ((x + y) & 255) << 16 for y in range(40) for x in range(60))
               and all(o[y * 60 + x] == 0xff141414 for y in list(range(10)) + list(range(50, 60)) for x in range(60)),
               'cc_fit with a longer side of exactly size is a pixel copy, centred, the bars the background')
        ok, o = fit(40, 60, bytes(edge[:40 * 60 * 4]), 60)
        expect(ok and all(o[y * 60 + x] == 0xff141414 for y in range(60) for x in list(range(10)) + list(range(50, 60))), 'cc_fit centres a tall picture, the side bars the background')
        sq = bytes((9, 8, 7, 255)) * 100
        ok, o = fit(10, 10, sq, 15)
        expect(ok and set(o) == {0xff000000 | 9 | 8 << 8 | 7 << 16}, 'cc_fit enlarges a square filtered and keeps a flat colour')
        ok, o = fit(10, 10, sq, 4, bg=0xff00ff00)
        expect(ok and set(o) == {0xff000000 | 9 | 8 << 8 | 7 << 16}, 'cc_fit reduces a square, the result has no background pixel')
        wide = bytes((100, 100, 100, 255)) * (30 * 10)
        ok, o = fit(30, 10, wide, 12, bg=0xff0000ff)
        expect(ok and all(o[y * 12 + x] == (0xff646464 if 4 <= y < 8 else 0xff0000ff) for y in range(12) for x in range(12)), 'cc_fit 30 x 10 into 12: 12 x 4 at y 4 (the other side follows the ratio)')
        thin = bytes((1, 2, 3, 255)) * 100
        ok, o = fit(100, 1, thin, 10)
        expect(ok and sum(1 for v in o if v == 0xff030201) == 10, 'cc_fit keeps a one pixel high result for a very wide picture')
        half = bytes((200, 100, 50, 128)) * 4
        ok, o = fit(2, 2, half, 2)
        expect(ok and o[0] == 0xff000000 | 100 | 50 << 8 | 25 << 16, 'cc_fit composes alpha over black like the other filters')
        ok, o = fit(4, 4, bytes(bytearray((50, 60, 70, 255)) * 4 + bytearray((255, 255, 255, 255)) * 2) * 4, 4, stride=24)
        expect(ok and all(v == 0xff000000 | 50 | 60 << 8 | 70 << 16 for v in o), 'cc_fit honours the stride')
        sentinel = (ctypes.c_uint * 4)(7, 7, 7, 7)
        expect(lib.cc_fit(b'\0' * 16, 0, 2, 8, rgba, 2, 0, sentinel) == 0 and lib.cc_fit(b'\0' * 16, 2, 2, 8, rgba, 0, 0, sentinel) == 0 and list(sentinel) == [7] * 4
               and lib.cc_fit(b'\0' * 16, 2, 2, 8, rgba, 2, 0, sentinel) == 1, 'cc_fit refuses an empty picture or size and leaves the output alone')
        big = (ctypes.c_uint * 4)(7, 7, 7, 7)
        expect(lib.cc_fit(b'\0' * 16, 2, 2, 8, rgba, 600, 0, big) == 0 and list(big) == [7] * 4, 'cc_fit refuses a size over the filter\'s row limit (AR_MAX)')

        # 12. Both filters against an independent model (the division per pixel, spelled out), pixel for pixel, for 1:1,
        #     integral and fractional ratios, enlargements, wide and tall sources, a padded stride, every byte order.
        import random
        rnd = random.Random(7)

        def model(kind, px, w, h, stride, at, size):
            side = min(w, h); ox, oy = (w - side) // 2, (h - side) // 2
            def over(x, y):
                o = y * stride + x * 4
                a_ = px[o + at[3]]
                return tuple(px[o + at[k]] * a_ // 255 if a_ != 255 else px[o + at[k]] for k in range(3))
            out_ = []
            for y in range(size):
                for x in range(size):
                    if kind == 'sample':
                        r, g, b = over(ox + x * side // size, oy + y * side // size)
                    else:   # the exact area average: a pixel counts for the part of it inside the target cell, one rounding at the end
                        def cover(k):
                            a_, e_ = k * side, (k + 1) * side
                            return [(i, min(e_, (i + 1) * size) - max(a_, i * size)) for i in range(a_ // size, -(-e_ // size))]
                        acc = [0, 0, 0]
                        for j, wy in cover(y):
                            for i, wx in cover(x):
                                p_ = over(ox + i, oy + j)
                                for k in range(3): acc[k] += wx * wy * p_[k]
                        tot = side * side
                        r, g, b = ((v + tot // 2) // tot for v in acc)
                    out_.append(0xff000000 | r | g << 8 | b << 16)
            return out_

        exact = True
        for (w_, h_, size_, pad) in ((20, 20, 20, 0), (24, 24, 8, 0), (24, 24, 10, 8), (31, 24, 13, 0), (17, 29, 17, 4),
                                     (30, 30, 50, 0), (37, 37, 23, 0), (168, 168, 92, 0), (168, 168, 52, 0), (168, 168, 168, 0)):
            order = rnd.choice(((0, 1, 2, 3), (2, 1, 0, 3), (1, 2, 3, 0)))
            stride_ = w_ * 4 + pad
            src_px = bytes(rnd.choice((255, 255, 255, rnd.randrange(256))) if k % 4 == order[3] else rnd.randrange(256)
                       for k in range(stride_ * h_))
            for kind, fn in (('sample', lib.cc_sample), ('box', lib.cc_box)):
                got = (ctypes.c_uint * (size_ * size_))()
                fn(src_px, w_, h_, stride_, bytes(order), size_, got)
                if list(got) != model(kind, src_px, w_, h_, stride_, order, size_):
                    exact = False
                    print(f'  mismatch: {kind} {w_}x{h_} -> {size_} (stride {stride_}, order {order})')
        expect(exact, 'cc_sample and cc_box match the models (cc_sample the per-pixel division, cc_box the exact area average with edge pixels weighted by their covered fraction) for 1:1, integral, fractional and enlarging ratios')

        # 13. The exact area average row by row (ar_init / ar_push: the core of cc_box and of the cover extraction): every ratio, up and down, a pixel
        #     weighted by the part of it inside the target cell, against an exact rational model; the totals' limits; and the alpha composing.
        def area_model(img, ow, oh, tw, th):
            def cover(k, n, m):   # the source pixels target cell k of n-wide cells touches, with their share, pixels m wide
                return [(i, min((k + 1) * n, (i + 1) * m) - max(k * n, i * m)) for i in range(k * n // m, -(-(k + 1) * n // m))]
            out_ = []
            for y in range(th):
                row_ = []
                for x in range(tw):
                    acc = [0, 0, 0]
                    for j, wy in cover(y, oh, th):
                        for i, wx in cover(x, ow, tw):
                            for k in range(3): acc[k] += wx * wy * img[j][i][k]
                    tot = ow * oh
                    row_.append(tuple((v + tot // 2) // tot for v in acc))
                out_.append(row_)
            return out_

        def area_run(img, ow, oh, tw, th, step=3, order=(0, 1, 2, 3)):
            buf = ctypes.create_string_buffer(20000)
            if not lib.ar_init(buf, ow, oh, tw, th): return None
            rows_ = []
            def emit(_, p): rows_.append([tuple(p[3 * x + k] for k in range(3)) for x in range(tw)])
            cb = AR_EMIT(emit)
            for j in range(oh):
                if step == 3: px_ = bytes(v for p in img[j] for v in p)
                else: px_ = b''.join(bytes(p[order.index(q)] for q in range(4)) for p in img[j])   # byte q holds the component whose position (order[c]) is q
                lib.ar_push(buf, px_, step, *(order[:3] if step == 4 else (0, 1, 2)), order[3] if step == 4 else 3, cb, None)
            return rows_

        area_ok = True
        for (ow_, oh_, tw_, th_) in ((24, 24, 24, 24), (24, 20, 8, 6), (37, 29, 23, 11), (10, 10, 30, 25), (168, 168, 144, 144), (101, 50, 50, 50),
                                     (5, 5, 1, 1), (64, 48, 168, 3), (200, 3, 7, 3), (168, 168, 168, 168), (9, 9, 4, 8)):
            img_ = [[tuple(rnd.randrange(256) for _ in range(3)) for _ in range(ow_)] for _ in range(oh_)]
            if area_run(img_, ow_, oh_, tw_, th_) != area_model(img_, ow_, oh_, tw_, th_):
                area_ok = False; print(f'  mismatch: ar {ow_}x{oh_} -> {tw_}x{th_}')
        expect(area_ok, 'ar_push is the exact area average (edge pixels by their covered fraction, one rounding) for 1:1, integral, fractional, anisotropic and enlarging ratios')
        flat3 = [[(7, 130, 251)] * 33 for _ in range(33)]
        expect(all(p == (7, 130, 251) for r in area_run(flat3, 33, 33, 20, 17) for p in r), 'a flat picture stays exactly flat, whatever the ratio')
        top = [[(255, 255, 255)] * 24 for _ in range(12)] + [[(0, 0, 0)] * 24 for _ in range(12)]
        got = area_run(top, 24, 24, 24, 16)   # 24 -> 16 rows: target row 8 covers source rows 12 .. 13.5: all black, row 7 covers 10.5 .. 12: all white; no row leaks across the edge
        expect(got[7][0] == (255, 255, 255) and got[8][0] == (0, 0, 0), 'a hard edge on a pixel boundary does not bleed into the next target row (weights are exact)')
        buf_ = ctypes.create_string_buffer(20000)
        expect(not lib.ar_init(buf_, 0, 5, 5, 5) and not lib.ar_init(buf_, 5, 5, 0, 5) and not lib.ar_init(buf_, 5, 5, 513, 5) and not lib.ar_init(buf_, 4097, 4097, 5, 5) and
               lib.ar_init(buf_, 4096, 4096, 512, 5), 'sizes of zero, a target over 512 wide and a source over 2^24 pixels are refused (the sums fit 32 bits)')
        for order_ in ((0, 1, 2, 3), (2, 1, 0, 3), (1, 2, 3, 0)):   # RGBA rows with alpha over black, any byte order
            img_ = [[(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), rnd.choice((255, 255, 128, 0, rnd.randrange(256)))) for _ in range(6)] for _ in range(6)]
            composed = [[tuple(p[k] * p[3] // 255 for k in range(3)) for p in r] for r in img_]
            expect(area_run(img_, 6, 6, 4, 3, 4, order_) == area_model(composed, 6, 6, 4, 3), f'the area average composes alpha over black first, byte order {order_}')

        # 14. Stock's resize geometry (cc_stock_fit: the FPU sequences of 0x5e00bc) and the picture it is given (cc_stock_dims): the cases read from the disassembly, then single precision.
        f32 = lambda v: struct.unpack('<f', struct.pack('<f', v))[0]

        def fit(w_, h_, t_):
            tw_, th_ = ctypes.c_uint(), ctypes.c_uint()
            r_ = lib.cc_stock_fit(w_, h_, t_, ctypes.byref(tw_), ctypes.byref(th_))
            return (tw_.value, th_.value) if r_ else None

        def fit_model(w_, h_, t_):
            if w_ >= h_:
                if t_ < w_: return t_, max(1, int(f32(h_ / f32(f32(w_) / f32(t_)))))
                return (t_, t_) if w_ == t_ else None
            if t_ < h_: return max(1, int(f32(w_ / f32(f32(h_) / f32(t_))))), t_
            return (t_, t_) if h_ == t_ else None

        expect([fit(*c) for c in ((600, 400, 168), (400, 600, 168), (1000, 1000, 168), (750, 500, 168), (168, 168, 168), (100, 100, 168), (167, 150, 168), (168, 100, 168), (100, 168, 168),
                                  (3000, 3, 168), (1200, 1000, 264))] ==
               [(168, 112), (112, 168), (168, 168), (168, 112), (168, 168), None, None, (168, 168), (168, 168), (168, 1), (264, 220)],
               'stock fit: the long side to the request, the other by single precision division; smaller kept; exactly the request stretches to a square (stock\'s quirk)')
        bad = [(w_, h_, t_) for w_ in list(range(1, 60)) + list(range(160, 175)) + [255, 264, 600, 1023, 1024, 1025, 2000] for h_ in list(range(1, 60, 7)) + list(range(160, 175)) + [333, 700, 1024]
               for t_ in (168, 264) if fit(w_, h_, t_) != fit_model(w_, h_, t_)]
        expect(not bad, f'stock fit equals the single precision model ({bad[:3]})')
        # a 3 : 2 picture whose exact quotient is an integer would truncate one short if the division went through the double reciprocal; 600 x 400 -> 112 and 1800 x 1200 are the cases
        expect(fit(1800, 1200, 168) == (168, 112) and fit(168, 168, 168) == (168, 168), 'integral quotients keep their value')

        def dims(w0_, h0_, n_):
            w_, h_ = ctypes.c_uint(), ctypes.c_uint()
            lib.cc_stock_dims(w0_, h0_, n_, ctypes.byref(w_), ctypes.byref(h_))
            return w_.value, h_.value

        expect([dims(*c) for c in ((1024, 1024, 3), (1024, 1024, 1), (1500, 1500, 3), (1025, 100, 3), (2048, 2048, 3), (3000, 2000, 3), (4096, 100, 3), (4097, 4097, 3), (8000, 6001, 3), (500, 500, 1),
                                   (1023, 1023, 1), (300, 200, 3))] ==
               [(1024, 1024), (512, 512), (750, 750), (513, 50), (1024, 1024), (750, 500), (1024, 25), (513, 513), (1000, 751), (500, 500), (1023, 1023), (300, 200)],
               'stock decodes up to 1024 x 1024 in colour whole, else at 1/2 (to 2048), 1/4 (to 4096), 1/8, sides rounded up; a gray JPEG always takes the scaled path')

        if a.captures:
            os.makedirs(a.captures, exist_ok=True)
            for name, frac in (('rest', 0), ('quarter', ONE // 4), ('half', ONE // 2),
                               ('three-quarter', -ONE // 4)):
                save(render(lib, frac, texs), os.path.join(a.captures, f'coverflow-{name}.png'))
            landscape(lib, ONE // 5, texs).save(os.path.join(a.captures, 'coverflow-landscape.png'))
            print(f'captures in {a.captures}')
        if a.preview:
            preview(render(lib, ONE // 6, texs), a.preview)
            print(f'preview {a.preview}')

    print(f'{ok} passed, {fail} failed')
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
