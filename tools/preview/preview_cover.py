#!/usr/bin/env python3
"""PIL mock-up of Cover Flow (docs/ui.md) from a finished tree: a long title, a title that fits, and
the artist-scoped shelf. The covers are the real depth renderer (test/coverflow.py's host build of
patch/coverflow.c); the page is the tree's own ui/m1plus_cover.bin, its text rasterized from the
tree's default.ttf the stb_truetype way (tools/preview/preview_font.py). Approximate, not AWTK; sample data.

A caption wider than its box is drawn as an hscroll_label shows it when it starts to scroll: from
its left margin, clipped to its box (it then scrolls back and forth, pausing 3 s at each end). Its
AWTK width (tools/awtk_text.StbText: truncated advances + 1 px per glyph) is printed.

Usage: uv run python -I tools/preview/preview_cover.py WORKDIR OUT.png [LANDSCAPE.png]
"""
import argparse, os, sys, tempfile
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import awtk_ui
import preview_font   # noqa: F401  (redirects the painters' text to stb_raster, the tree's font)
import preview_layout, pod_ui
from awtk_text import Ttf, StbText
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'test'))
import coverflow as hostcf  # noqa: E402

LONG = 'The Rise and Fall of Ziggy Stardust and the Spiders from Mars'
LONG_ARTIST = 'David Bowie with the Spiders from Mars'
HSCROLL_MARGIN = 2


def page(work, album, artist, title, ring, frac=0):
    """The tree's ui/m1plus_cover.bin with its captions filled and the rendered frame in view_covers."""
    raw = os.path.join(work, preview_layout.RAW)
    root = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_cover.bin'), 'rb').read())
    ttf = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    for w in root.walk():   # renamed: the Now Playing painter has sample text for label_album
        text = {'label_title': title, 'label_album': album, 'label_artist': artist}.get(w.name)
        if text is not None:
            if w.type == 'label' and w.name != 'label_title':
                # a plain label draws a text wider than its box centred all the same (canvas_draw_text_
                # in_rect), so it runs off both sides: give the painter that box
                tw = StbText(ttf, int(w.get('style:normal:font_size', '18'))).layout(text)[1]
                if tw > w.w: w.x, w.w = w.x + (w.w - tw) // 2, tw
            w.set('text', text); w.set('name', w.name + '_preview')
            if w.type == 'hscroll_label': w.remove('ellipses')   # as it shows while it scrolls
    im = preview_layout.MenuPainter(raw).render(root, 0)
    with tempfile.TemporaryDirectory() as tmp:
        lib = hostcf.build(tmp)
        tex = [None if t is None else hostcf.texture(*t) for t in ring]
        frame = hostcf.render(lib, frac, tex)
    covers = Image.new('RGB', (hostcf.W, hostcf.H))
    covers.putdata([(v & 255, v >> 8 & 255, v >> 16 & 255) for v in frame])
    fy, ay = pod_ui.cover_layout()[:2]
    top = 480 - pod_ui.CLIENT_H
    im.paste(covers.crop((0, 0, hostcf.W, ay - fy)).convert('RGBA'), (0, top + fy))
    return im


LAND_SHELF = [(200, 60, 60), (60, 160, 200), (230, 190, 70), (90, 90, 220), (120, 200, 120), (200, 120, 200), (210, 140, 60)]


def landscape(work, album='Kind of Blue', artist='Miles Davis', frac=None, shelf=None, overlay=None):
    """The landscape Cover Flow as the user sees it, the player held turned counter-clockwise (480 x 320): the tree's own
    page (status bar and navbar, which stay portrait, now along the left side) with the real renderer's turned frame in
    the 320 x 400 body under the navbar, the captions in the tree's font as patch/coverflow.c lays them (centred, the line
    top at CFL_ALBUM_Y / CFL_ARTIST_Y, 22 px white over 18 px grey). shelf: the textures' colours (None: placeholders);
    overlay(im, font): more drawn into the logical frame (an RGBA image, CFL_W x CFL_H) after the captions. Approximate, like the rest."""
    from stb_raster import StbFont
    raw = os.path.join(work, preview_layout.RAW)
    font = StbFont(os.path.join(raw, 'fonts', 'default.ttf'))
    root = awtk_ui.parse(open(os.path.join(raw, 'ui', 'm1plus_cover.bin'), 'rb').read())
    for w in root.walk():   # the caption labels are hidden in landscape (renamed: the painter has sample text for them)
        if w.name in ('label_album', 'label_artist'): w.set('text', ''); w.set('name', w.name + '_preview')
    page_im = preview_layout.MenuPainter(raw).render(root, 0).convert('RGBA')
    with tempfile.TemporaryDirectory() as tmp:
        lib = hostcf.build(tmp)
        tex = [hostcf.texture(c, mark=i == 3) for i, c in enumerate(shelf or LAND_SHELF)]
        im = hostcf.landscape(lib, hostcf.ONE // 10 if frac is None else frac, tex).convert('RGBA')
    c = hostcf.C
    for text, px, y, grey in ((album, 22, c['CFL_ALBUM_Y'], 255), (artist, 18, c['CFL_ARTIST_Y'], 0xAA)):
        font.draw(im, (c['CFL_W'] - font.width(text, px)) // 2, y, text, px, (grey, grey, grey, 255))
    if overlay: overlay(im, font)
    page_im.paste(im.transpose(Image.ROTATE_270), (0, 480 - pod_ui.CLIENT_H + c['CFL_Y']))   # the physical frame
    return page_im.transpose(Image.ROTATE_90).convert('RGB')


def widths(work):
    """AWTK widths of the sample captions in the tree's font against the caption boxes."""
    ttf = Ttf(os.path.join(work, preview_layout.RAW, 'fonts', 'default.ttf'))
    box = pod_ui.SCREEN_W - 2 * pod_ui.CAPTION_X - 2 * HSCROLL_MARGIN
    out = []
    for text, px in ((LONG, 22), (LONG_ARTIST, 18), ('Kind of Blue', 22), ('Miles Davis', 18)):
        w = StbText(ttf, px).layout(text)[1]
        out.append(f'"{text}" {px} px: {w} px in {box} -> {"scrolls" if w > box else "centred"}')
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('work'); ap.add_argument('out'); ap.add_argument('landscape', nargs='?', help='also write the landscape panel here')
    a = ap.parse_args()
    if a.landscape:
        landscape(a.work).save(a.landscape); print('wrote', a.landscape)
    shelf = [((200, 60, 60), 0), ((60, 160, 200), 0), ((230, 190, 70), 0), ((90, 90, 220), 1),
             ((120, 200, 120), 0), ((200, 120, 200), 0), ((210, 140, 60), 0)]
    scoped = [None] * 3 + shelf[3:]
    shots = [('a long title', page(a.work, LONG, LONG_ARTIST, 'Cover Flow', shelf, hostcf.ONE // 10)),
             ('a title that fits', page(a.work, 'Kind of Blue', 'Miles Davis', 'Cover Flow', shelf)),
             ('on one artist', page(a.work, 'Kind of Blue', 'Miles Davis', 'Miles Davis', scoped)),
             ('stretched past the first album', page(a.work, 'Kind of Blue', 'Miles Davis', 'Cover Flow', scoped, -(hostcf.ONE * 2 // 5)))]   # the rubber band's largest stretch: 2/5 of a cover
    notes = widths(a.work)
    for n in notes: print(n)
    W, H, pad, top = 320, 480, 12, 20
    out = Image.new('RGB', (len(shots) * (W + pad) + pad, H + top + 2 * pad + 16 * (len(notes) + 1)), (40, 40, 40))
    d = ImageDraw.Draw(out)
    for i, (cap, im) in enumerate(shots):
        x = pad + i * (W + pad)
        assert im.size == (W, H), (cap, im.size)
        out.paste(im.convert('RGB'), (x, pad + top)); d.text((x, pad + 4), cap, fill=(230, 230, 230))
    y = pad + top + H + 6
    d.text((pad, y), 'approximate PIL mock-ups (not AWTK), text from the tree\'s default.ttf; the covers are the real '
           'renderer; a long caption is shown as it starts to scroll (it then scrolls back and forth)', fill=(160, 160, 160))
    for n in notes:
        y += 16; d.text((pad, y), 'AWTK width ' + n, fill=(160, 160, 160))
    out.quantize(colors=192).save(a.out, optimize=True); print('wrote', a.out)


if __name__ == '__main__': main()
