#!/usr/bin/env python3
"""Design preview (no payload yet): the Lyrics idle display, an own full-screen page over Now Playing. A header (cover, title, artist, no controls)
over the synchronized lyrics, on the Now Playing cover tint with the lyrics scrim.

  preview_idlelyrics.py OUTDIR [--tree RAW_TREE_ROOT]

writes idlelyrics-*.png (fullscreen 320 x 480 windows, no status bar, 2x the pixels in the sheets): baseline (88 px header, 56 px cover), large header (104 / 72), the first design beside the baseline (header), CJK with a
long title, the three lyric sizes 22 / 26 / 30, no lyrics. The cover is the mini bar's (preview_minibar.rounded_cover: corners rounded in the alpha, drawn 4x and
reduced; the radius scaled with the cover, 5 / 36), the title and artist its sizes and colours (pod_ui MB_*); the lyric lines are preview_lyrics.render
(patch/offsets.inc LY_*, the page's own wrap, opacities and edge fade) in a view of another height. The background is the page's tint (mod_nowplaying tone,
tint_alpha) with np_scrim_lyrics's alpha over the whole window.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
import paths, pod_ui as U, mod_nowplaying as mn
import preview_lyrics as L
from awtk_text import Ttf
from stb_raster import StbFont

W, H = 320, U.OFFSETS['IL_H']      # fullscreen: 320 x 480, no status bar (patch/offsets.inc IL_*)
TOP = U.OFFSETS['IL_ART_Y']        # the cover top: 20 (the side margin is 28)
MARGIN = 28                       # the lyric view's left margin (LY_W 264): the cover's left edge is the same
GAP_TEXT = 12                     # cover to text
BOTTOM = 12                       # the view ends this far above the window's bottom
HINT_RGB = (0xAA, 0xAA, 0xAA)     # pod_roles HINT_RGB; empty-state hint 20 px
ARTIST_RGB = tuple(int(U.MB_ARTIST_RGB[i:i + 2], 16) for i in (1, 3, 5))

# header: (cover px, title px, artist px); the header is TOP above the cover and 12 px under it (88 px at 56)
BASE = (U.OFFSETS['IL_ART'], U.OFFSETS['IL_TITLE_PX'], U.OFFSETS['IL_ARTIST_PX'])
FIRST = (48, U.MB_TITLE_PX, U.MB_ARTIST_PX)   # the first design (the mini bar's sizes, cover top 28); the lyrics view was at the same y 96
LARGE = (72, 20, 17)

def lyric_params(font):
    """The page's look at a Lyrics Text Size: the size branch's pitch and gap (preview_lyrics.sized: 22 / 25 / 9, 26 / 29 / 10, 30 / 34 / 12)."""
    return L.sized({30: '', 26: '_m', 22: '_s'}[font])

def background(rgb, height=H):
    im = Image.new('RGBA', (W, height)); d = ImageDraw.Draw(im); t = mn.tone(*rgb) if rgb else mn.NP_NEUTRAL
    for y in range(height):
        base = tuple(v * (255 - mn.tint_alpha(y, height)) // 255 for v in t)
        d.line([(0, y), (W - 1, y)], fill=base + (255,))
    scrim = Image.new('RGBA', (W, height))
    sd = ImageDraw.Draw(scrim)
    for y in range(height):   # np_scrim_lyrics's alpha, its ramps at both ends of the window
        d_ = min(y, height - 1 - y); e = mn.LSCRIM_EDGE
        a = mn.LSCRIM_ALPHA if d_ >= e else mn.LSCRIM_ALPHA * (3 * d_ * d_ * e - 2 * d_ ** 3) // e ** 3
        sd.line([(0, y), (W - 1, y)], fill=(0, 0, 0, a))
    im.alpha_composite(scrim); return im

def cover(rgb, size):
    """preview_icons.sample_cover's stand-in, rounded like the mini bar's (radius 5 at 36 px, scaled)."""
    import preview_icons as PI
    art = PI.sample_cover(rgb, size); r = max(5, round(U.MB_ART_R * size / U.MB_ART)); k = 4
    mask = Image.new('L', (size * k, size * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * k - 1, size * k - 1), radius=r * k, fill=255)
    art.putalpha(mask.resize((size, size), Image.LANCZOS)); return art

def clip(f, text, px, room):
    while f.width(text, px) > room and len(text) > 1: text = text[:-2] + '…' if text.endswith('…') else text[:-1] + '…'
    return text

def page(fonts, title, artist, rgb, lines, cur, head=BASE, lyric_px=30, hint=None, tint_rgb=None, art_y=TOP):
    """One 320 x 480 window. lines=None draws the hint (centred, grey) in the lyric area."""
    cs, tpx, apx = head; hh = art_y + cs + 12
    im = background(tint_rgb or rgb); df = fonts['default'][0]
    cy = art_y
    im.alpha_composite(cover(rgb, cs), (MARGIN, cy))
    x = MARGIN + cs + GAP_TEXT; room = W - MARGIN - x; mid = cy + cs / 2
    off = (tpx + apx) / 2 * 0.64   # half the line pitch: 10.5 at the mini bar's 17 / 16 (title centre 18, artist 39 in a 56 px pill)
    df.draw(im, x, int(mid - off - tpx / 2), clip(df, title, tpx, room), tpx, (255, 255, 255, 255))
    df.draw(im, x, int(mid + off - apx / 2), clip(df, artist, apx, room), apx, ARTIST_RGB + (255,))
    top = hh + 8; vh = H - top - BOTTOM
    if lines is None:
        px = 20; w = df.width(hint, px)
        df.draw(im, (W - w) // 2, top + (vh - px) // 2, hint, px, HINT_RGB + (255,))
    else:
        p = lyric_params(lyric_px)
        layer = L.render(None, lines, cur, p, fonts, vh=vh, anc=round(0.35 * vh))
        im.alpha_composite(layer, (MARGIN, top))
    return im

def label(im, text):
    d = ImageDraw.Draw(im); d.text((4, H - 12), text, fill=(255, 220, 120, 255)); return im

def sheet(ims, out, scale=1):
    s = Image.new('RGB', (len(ims) * (W + 4) - 4, H), (40, 40, 40))
    for i, im in enumerate(ims): s.paste(im.convert('RGB'), (i * (W + 4), 0))
    if scale != 1: s = s.resize((s.width * scale, s.height * scale), Image.LANCZOS)
    s.save(out); print(os.path.abspath(out))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('outdir'); ap.add_argument('--tree', help='the raw tree with fonts/default.ttf and lyrics.ttf (default: the release tree in work/)')
    a = ap.parse_args()
    tree = a.tree or next(p for p in (os.path.join(paths.WORK, 'mod-release', 'rootfs/release/assets/default/raw'),
                                      os.path.join(paths.WORK, 'check/release/work/mod-release/rootfs/release/assets/default/raw')) if os.path.isdir(p))
    dpath, bpath = os.path.join(tree, 'fonts', 'default.ttf'), os.path.join(tree, 'fonts', 'lyrics.ttf')
    fonts = {'default': (StbFont(dpath), Ttf(dpath)), 'bold': (StbFont(bpath), Ttf(bpath))}
    os.makedirs(a.outdir, exist_ok=True); o = lambda n: os.path.join(a.outdir, n)
    warm, cool = (200, 120, 60), (70, 110, 190)
    T, A, LN = 'Walking Down the Street', 'The Midnight Drivers', L.LATIN_A
    sheet([label(page(fonts, T, A, warm, LN, 2), 'baseline: 88 px header, 56 px cover'),
           label(page(fonts, T, A, cool, L.LATIN_B, 1), 'baseline: cool cover, long lines')], o('idlelyrics-baseline.png'))
    sheet([label(page(fonts, T, A, warm, LN, 2, head=LARGE), 'large: 104 px header, 72 px cover'),
           label(page(fonts, T, A, warm, LN, 2), 'baseline (for comparison)')], o('idlelyrics-large.png'))
    sheet([label(page(fonts, T, A, warm, LN, 2, head=FIRST, art_y=28), 'first design: cover 48 at y 28, title 17, artist 16'),
           label(page(fonts, T, A, warm, LN, 2), 'baseline: cover 56 at y 20, title 19, artist 17')], o('idlelyrics-header.png'))
    sheet([label(page(fonts, '夜晚的风轻轻吹过我的窗前，我想要的只是和你在一起', '周杰伦 / 林俊杰', cool, L.CJK, 1), 'CJK, long title cut'),
           label(page(fonts, '夜に駆ける', 'YOASOBI', warm, L.CJK, 6), 'kana / Latin lines')], o('idlelyrics-cjk.png'))
    sheet([label(page(fonts, T, A, warm, LN, 2, lyric_px=px), f'lyrics {px} px') for px in (22, 26, 30)], o('idlelyrics-sizes.png'))
    sheet([label(page(fonts, T, A, warm, None, 0, hint='No lyrics'), 'no lyrics'),
           label(page(fonts, 'Untitled Recording', 'Unknown Artist', None, None, 0, hint='No lyrics'), 'no lyrics, no cover (placeholder)')], o('idlelyrics-nolyrics.png'))

if __name__ == '__main__': main()
