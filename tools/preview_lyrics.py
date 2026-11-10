#!/usr/bin/env python3
"""Preview of the Now Playing lyrics page: the earlier look (28 px Medium, greys, hard clip) beside the current one (bold face, white
at falling opacity, edge fade), over the background of a device screenshot. docs/modules/lyrics.md.

  preview_lyrics.py OUT.png --shot SHOT.bmp [--mode look|scrim|intro] [--tree RAW_TREE_ROOT] [--bold FILE.ttf]

The --mode scrim option puts the info scrim (np_scrim, 50 % black) beside the lyrics scrim (np_scrim_lyrics, 27 %, eased edges) over the screenshot's window and
over two cover tones; --mode intro shows the interlude dots at four moments of a 12 s intro, the first line waiting under them.

The layout is the page's own: the line geometry of patch/offsets.inc (LY_*), a line's rows from a greedy word wrap with the text model of the
build (awtk_text.StbText on the real font files: default.ttf of the tree, the lyric face from tools/mod_font.lyric_face), the anchor,
the opacities and the edge factor of patch/lyrics.c; glyphs rasterised the stb_truetype way (stb_raster). The wrap is a model: AWTK's own
(label line_wrap) is checked on the device. The screenshot's lyric rectangle is repainted from the margin column so no old text shows.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import paths, mod_font
from awtk_text import Ttf, StbText
from stb_raster import StbFont
from pod_ui import OFFSETS as O

W, ROW_W, VIEW_X, VIEW_Y = O['LY_W'], O['LY_ROW_W'], 28, 44
VIEW_H, ANCHOR = O['LY_VIEW_H'], O['LY_ANCHOR']
NEW_OPACITY = (255, 115, 82, 61, 46)            # patch/lyrics.c ly_opacity: distance 0, 1, 2, 3, 4+
OLD_OPACITY = (255, 179, 128, 89)               # stage 2
OLD = dict(font=28, line_h=34, gap=14, op=OLD_OPACITY, fade=0, cur=(0xee, 0xee, 0xec), dim=(0xa0, 0xa0, 0xa0), bold=False)
NEW = dict(font=O['LY_FONT'], line_h=O['LY_LINE_H'], gap=O['LY_GAP'], op=NEW_OPACITY, fade=O['LY_FADE'], cur=(255, 255, 255), dim=(255, 255, 255), bold=True)

LATIN_A = ['Walking down the street tonight', 'Be what you want to be', 'When you get a head', 'A head full of dreams and a heart wide open',
           "Into life, I've just been", 'With a head full of stars', 'Nothing left to say but goodbye', 'And we run, run, run']
LATIN_B = ['Counting every star above the city lights', "Every night I lie awake wondering what you're thinking of me",
           'Hold me close', 'Never let me go', 'Take me back to where we started', 'Say it one more time']
CJK = ['夜晚的风轻轻吹过我的窗前', '我想要的只是和你在一起', '不管明天会怎样', '每一个梦都在等待天亮的时候', '就这样慢慢走下去',
       'Hello, 你好吗', 'もう一度だけ会いたい', '조용히 눈을 감으면']

def latin_only(text): return all(mod_font.in_ranges(ord(c), mod_font.INTER_RANGES) for c in text)

def wrap_text(text, st, width=ROW_W):
    """The rows of a greedy word wrap: break after a space, between CJK characters, inside a word longer than a row."""
    adv = lambda c: (st.advance(c) or 4) + 1
    toks, word = [], ''
    for c in text:
        if c == ' ' or ord(c) >= 0x2E80:
            if word: toks.append(word); word = ''
            toks.append(c)
        else: word += c
    if word: toks.append(word)
    rows, cur, x = [], '', 0
    for t in toks:
        w = sum(adv(c) for c in t)
        if w > width:
            for c in t:
                if x + adv(c) > width and cur: rows.append(cur); cur, x = '', 0
                cur += c; x += adv(c)
        else:
            if x + w > width and cur and t != ' ': rows.append(cur.rstrip()); cur, x = '', 0
            cur += t; x += w
    rows.append(cur.rstrip())
    return rows

def wrap_rows(text, st, width=ROW_W, cap=3): return min(len(wrap_text(text, st, width)), cap)

def edge(y, rows, p):
    top, bot = y + rows * p['line_h'] - p['line_h'] // 2, VIEW_H - (y + p['line_h'] // 2)
    e = min(top, bot)
    if not p['fade']: return 255
    return 0 if e <= 0 else 255 if e >= p['fade'] else e * 255 // p['fade']

def render(bg, lines, cur, p, fonts, pad=0, ref=None):
    """The lyric rectangle for lines with line `cur` anchored `pad` px below the anchor, the opacities counted from line `ref` (default `cur`; -1 in an intro): an RGBA layer (W x VIEW_H) of the settled page."""
    layer = Image.new('RGBA', (W, VIEW_H), (0, 0, 0, 0))
    ref = cur if ref is None else ref
    def face(t):
        bold = p['bold'] and latin_only(t)
        return fonts['bold' if bold else 'default']
    def rows(t):
        f = face(t)[1]
        return wrap_rows(t, StbText(f, p['font']))
    ys, y = {}, ANCHOR + pad
    for i in range(cur, len(lines)):
        ys[i] = y; y += rows(lines[i]) * p['line_h'] + p['gap']
    y = ANCHOR + pad
    for i in range(cur - 1, -1, -1):
        y -= rows(lines[i]) * p['line_h'] + p['gap']; ys[i] = y
    for i, y in sorted(ys.items()):
        n = rows(lines[i]); h = n * p['line_h']
        if y + h <= 0 or y >= VIEW_H: continue
        op = p['op'][min(abs(i - ref), len(p['op']) - 1)] * edge(y, n, p) // 255
        if not op: continue
        sf, tt = face(lines[i]); st = StbText(tt, p['font'])
        col = p['cur'] if i == ref else p['dim']
        for k, t in enumerate(wrap_text(lines[i], st)[:n]):
            sf.draw(layer, 0, y + k * p['line_h'] + (p['line_h'] - p['font']) // 2, t, p['font'], (*col, op))
    return layer

def dot_op(k, el, ln):
    """patch/lyrics.c ly_dot_op: dim to full by thirds of the gap (less its last fade), times the breath, times the fade out."""
    dim, fade, br, brmin = O['LY_DOT_DIM'], O['LY_DOT_FADE_MS'], O['LY_DOT_BREATH_MS'], O['LY_DOT_BREATH_MIN']
    fl = max(ln - fade, 1); f = min(max(el * 3 - k * fl, 0), fl)
    op = dim + (255 - dim) * f // fl
    tri = el % br
    if tri > br // 2: tri = br - tri
    op = op * (255 - (255 - brmin) * tri // (br // 2)) // 255
    left = ln - el
    return 0 if left <= 0 else op * left // fade if left < fade else op

def draw_dots(layer, el, ln):
    """The three interlude dots (np_dot.png) at the anchor row."""
    import mod_nowplaying as mn
    dot = mn.dot_image(); y = ANCHOR + (O['LY_LINE_H'] - O['LY_DOT']) // 2
    for k in range(3):
        op = dot_op(k, el, ln) * edge(ANCHOR, 1, NEW) // 255
        d = dot.copy(); d.putalpha(d.getchannel('A').point(lambda v: v * op // 255))
        layer.alpha_composite(d, (O['LY_DOT_X'] + k * O['LY_DOT_PITCH'], y))

def panel(bg, layer, label):
    im = bg.copy(); im.alpha_composite(layer, (VIEW_X, VIEW_Y))
    d = ImageDraw.Draw(im); d.text((6, 286), label, fill=(255, 220, 120, 255))
    return im.crop((0, 0, 320, 300))

def background(shot):
    im = Image.open(shot).convert('RGBA')
    px = im.load()
    for y in range(VIEW_Y, VIEW_Y + VIEW_H):
        c = px[12, y]
        for x in range(VIEW_X, VIEW_X + W): px[x, y] = c
    return im

def scrimed(rows, which):
    """A 320 x 300 background from per-row colours (the window with its tint, no scrim), the scrim of `which` ('old': np_scrim, 'new': np_scrim_lyrics) laid over."""
    import mod_nowplaying as mn
    im = Image.new('RGBA', (320, 300)); d = ImageDraw.Draw(im)
    for y in range(300):
        a = (mn.scrim_alpha(y - mn.SCRIM[1]) if 0 <= y - mn.SCRIM[1] < mn.SCRIM[3] else 0) if which == 'old' else (mn.lscrim_alpha(y - mn.LSCRIM[1]) if 0 <= y - mn.LSCRIM[1] < mn.LSCRIM[3] else 0)
        d.line([(0, y), (319, y)], fill=tuple(v * (255 - a) // 255 for v in rows[y]) + (255,))
    return im

def shot_rows(shot):
    """The device screenshot's colour per row (margin column), with the old scrim taken off again: the window as it was before any scrim."""
    import mod_nowplaying as mn
    px = Image.open(shot).convert('RGB').load(); out = []
    for y in range(300):
        a = mn.scrim_alpha(y - mn.SCRIM[1]) if 0 <= y - mn.SCRIM[1] < mn.SCRIM[3] else 0
        out.append(tuple(min(255, v * 255 // (255 - a)) for v in px[12, y]))
    return out

def tone_rows(rgb):
    """A cover tone's window (patch/nowplaying.c tone, then the tint gradient), per row."""
    import mod_nowplaying as mn
    return [tuple(v * (255 - mn.tint_alpha(y)) // 255 for v in mn.tone(*rgb)) for y in range(300)]

def sheets(a, fonts):
    """--scrim: the old scrim beside the new one over the screenshot and over a bright cover; --intro: four frames of the interlude dots."""
    shot = shot_rows(a.shot)
    if a.mode == 'scrim':
        sheet = Image.new('RGBA', (3 * 324, 2 * 304), (40, 40, 40, 255))
        for r, which in enumerate(('old', 'new')):
            for c, (name, rows) in enumerate((('shot-0022', shot), ('bright cover', tone_rows((255, 255, 255))), ('warm cover', tone_rows((230, 150, 60))))):
                bg = scrimed(rows, which)
                sheet.paste(panel(bg, render(bg, LATIN_A, 2, NEW, fonts), f'{which} scrim ({128 if which == "old" else 68}): {name}'), (c * 324, r * 304))
    else:
        lines = ['Walking down the street tonight', 'Be what you want to be', 'A head full of dreams and a heart wide open', 'And we run, run, run']
        ln = 12000
        sheet = Image.new('RGBA', (4 * 324, 2 * 304), (40, 40, 40, 255))
        for r, (name, rows) in enumerate((('shot-0022', shot), ('bright cover', tone_rows((255, 255, 255))))):
            bg = scrimed(rows, 'new')
            for c, el in enumerate((500, 4000, 8200, 11700)):
                layer = render(bg, lines, 0, NEW, fonts, pad=O['LY_DOT_PAD'], ref=-1); draw_dots(layer, el, ln)
                sheet.paste(panel(bg, layer, f'intro {el / 1000:.1f} s of {ln // 1000} s: {name}'), (c * 324, r * 304))
    sheet.convert('RGB').save(a.out); print(os.path.abspath(a.out))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out'); ap.add_argument('--shot', required=True, help='device screenshot used as the preview background')
    ap.add_argument('--mode', choices=('look', 'scrim', 'intro'), default='look', help='look: earlier and current typography; scrim: info and lyrics scrims; intro: interlude dots')
    ap.add_argument('--tree', help='the raw tree with fonts/default.ttf (default: the release tree in work/)')
    ap.add_argument('--bold', help='the lyric face file (default: mod_font.lyric_face of the committed subset)')
    a = ap.parse_args()
    tree = a.tree or next(p for p in (os.path.join(paths.WORK, 'mod-release', 'rootfs/release/assets/default/raw'),
                                      os.path.join(paths.WORK, 'check/release/work/mod-release/rootfs/release/assets/default/raw')) if os.path.isdir(p))
    dpath = os.path.join(tree, 'fonts', 'default.ttf')
    bpath = a.bold or os.path.join(tree, 'fonts', 'lyrics.ttf')
    fonts = {'default': (StbFont(dpath), Ttf(dpath)), 'bold': (StbFont(bpath), Ttf(bpath))}
    if a.mode != 'look': return sheets(a, fonts)
    bg = background(a.shot)
    sets = [('latin', LATIN_A, 2), ('long', LATIN_B, 0), ('cjk', CJK, 1)]
    rows = []
    for name, p in (('old', OLD), ('new', NEW)):
        rows.append([panel(bg, render(bg, ls, cur, p, fonts), f'{name}: {n}') for n, ls, cur in sets])
    sheet = Image.new('RGBA', (3 * 324, 2 * 304), (40, 40, 40, 255))
    for r, ims in enumerate(rows):
        for c, im in enumerate(ims): sheet.paste(im, (c * 324, r * 304))
    sheet.convert('RGB').save(a.out); print(os.path.abspath(a.out))

if __name__ == '__main__': main()
