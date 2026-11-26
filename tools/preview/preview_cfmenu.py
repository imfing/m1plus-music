#!/usr/bin/env python3
"""Cover Flow's "..." menu and scrubber (docs/modules/coverflow.md "Menu", "Scrubber"): the main page with the
"... | Now Playing" capsule, the scrubber's ticks at rest and while dragged (taller and brighter, the needle, the playing
album's dot, the bubble over the centre cover with the section of the current order, the counter under the ticks), and
the "..." card (Search Albums, Playing Album, the Albums sort rows). The page and shelf are tools/preview/preview_cover.py's (the tree's asset,
the real depth renderer); the card is the shared view card painter. Approximate, not AWTK; sample data.

Landscape (the page turned, the ticks along the screen's left edge; the bubble and the counter in the frame): the same page, the scrubber's band, ticks, needle, dot, bubble and counter
as patch/coverflow.c lays them in the frame's logical axes (CFL_*), shown as the player is held.

Usage: uv run python -I tools/preview/preview_cfmenu.py WORKDIR OUT.png
       uv run python -I tools/preview/preview_cfmenu.py WORKDIR --landscape OUT.png
"""
import argparse, math, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preview_cover as PC
import preview_icons as PI
import preview_songs as PS
import pod_ui
hostcf = PC.hostcf
TOP = 480 - pod_ui.CLIENT_H          # the status bar above the page's client area
O = PI.offsets()
BELL = [255] + [round(256 * math.exp(-k / 8)) for k in range(1, 49)]   # patch/coverflow.c bell_tab


def aa_round(im, box, r, rgba):
    """An anti-aliased rounded rectangle composited on im (4x supersampled)."""
    x0, y0, x1, y1 = box; w, h = x1 - x0, y1 - y0; k = 4
    m = Image.new('L', (w * k, h * k), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, w * k - 1, h * k - 1), radius=r * k, fill=255)
    layer = Image.new('RGBA', (w, h), rgba[:3] + (0,)); a = Image.new('L', (w, h), rgba[3])
    layer.putalpha(Image.composite(a, Image.new('L', (w, h), 0), m.resize((w, h), Image.LANCZOS)))
    im.alpha_composite(layer, (x0, y0))


def capsule(s, im):
    """The navbar's right end as "... | Now Playing": "..." the capsule's left cap on the 214 slot, Now Playing its right cap."""
    d = ImageDraw.Draw(im); d.rectangle((O['NAV_VIEW_X'], TOP, 319, TOP + 49), fill=(0, 0, 0))
    for name, x, bw in (('pod_nav_more', O['NAV_VIEW_X'], 46), ('ah_nav_play', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (x + (bw - g.width) // 2, TOP + (50 - g.height) // 2))


def bell(d, sigma):
    k = d * d * 8 // (sigma * sigma)
    return BELL[k] if k < len(BELL) else 0


def grey(a): return (a, a, a, 255)   # patch/coverflow.c blend over the black page: a of 255 of the way to white


def scrubber(im, frac, drag=False, playing=None):
    """patch/coverflow.c on_scrub_paint, the same integer rectangles: CF_TICKS ticks swelling around the position; dragged, taller and brighter, the needle and the playing album's dot."""
    d = ImageDraw.Draw(im); y = TOP + O['CF_SCRUB_Y'] + O['CF_TICK_Y']; span = O['CF_TICK_X1'] - O['CF_TICK_X0']
    x0 = O['CF_TICK_X0'] + round(frac * span)
    pre = 'CF_DRAG_' if drag else 'CF_REST_'
    for i in range(O['CF_TICKS']):
        x = O['CF_TICK_X0'] + i * span // (O['CF_TICKS'] - 1); g = bell(abs(x - x0), O[pre + 'SIGMA'])
        h = O[pre + 'H'] + (O[pre + 'BUMP'] * g + 128) // 256; a = O[pre + 'A'] + (O[pre + 'DA'] * g + 128) // 256
        d.rectangle((x - 1, y - h // 2, x - 1 + O['CF_TICK_W'] - 1, y - h // 2 + h - 1), fill=grey(a))
    if drag:
        d.rectangle((x0 - 1, y - O['CF_NEEDLE_H'] // 2, x0 - 2 + O['CF_NEEDLE_W'], y - O['CF_NEEDLE_H'] // 2 + O['CF_NEEDLE_H'] - 1), fill=grey(255))
        if playing is not None:
            px, py, n = O['CF_TICK_X0'] + round(playing * span), y - O['CF_DOT_DY'], O['CF_DOT']
            d.rectangle((px - n // 2, py + 1, px + n // 2 - 1, py + n - 2), fill=grey(O['CF_DOT_A']))
            d.rectangle((px - n // 2 + 1, py, px + n // 2 - 2, py + n - 1), fill=grey(O['CF_DOT_A']))


def bubble(s, im, text):
    """cf_bubble: the A-Z rail's bubble (SG_BUBBLE px, #3A3A3A rim, #262626 fill), centred on the centre cover; a letter SG_BUBBLE_PX, a year SG_BUBBLE_PX_YEAR."""
    px = O['SG_BUBBLE_PX'] if len(text) <= 2 else O['SG_BUBBLE_PX_YEAR']
    bw = bh = O['SG_BUBBLE']
    fy = pod_ui.cover_layout()[0]
    x, y = (320 - bw) // 2, TOP + fy + O['CF_TOP'] + (O['ART_SIZE'] - bh) // 2
    aa_round(im, (x, y, x + bw, y + bh), 14, (0x3A, 0x3A, 0x3A, 0xF0)); aa_round(im, (x + 1, y + 1, x + bw - 1, y + bh - 1), 13, (0x26, 0x26, 0x26, 0xF0))
    s.text(im, x + bw / 2, y + bh / 2, text, px, anchor='m')


def counter(s, im, text):
    s.text(im, 160, TOP + O['CF_COUNT_Y'] + O['CF_COUNT_H'] / 2, text, O['CF_COUNT_PX'], (0x8E, 0x8E, 0x93), anchor='m')


def menu(s, im, current=0, rev=False):
    """The "..." card: Search Albums, Playing Album, then the Albums sort rows (the shared order) with the tick and direction."""
    im.alpha_composite(Image.new('RGBA', im.size, (0, 0, 0, 0x82)))
    sub = PS.tr(s, ('Z–A' if rev else 'A–Z') if current < 2 else ('Oldest First' if rev else 'Newest First'))
    sorts = [(k, None, i == current, sub if i == current else None) for i, k in enumerate(('Title', 'Artist', 'Recently Added', 'Year'))]
    rows = [('Search Albums', 'pod_ic_vssearch', False, None), ('Playing Album', 'pod_ic_vslocate', False, None)] + sorts
    sub_im = im.crop((0, TOP, 320, 480)); PI.view_card(s, sub_im, rows, 'vs_glass6', (2,)); im.paste(sub_im, (0, TOP))


SHELF = [((200, 60, 60), 0), ((60, 160, 200), 0), ((230, 190, 70), 0), ((90, 90, 220), 1),
         ((120, 200, 120), 0), ((200, 120, 200), 0), ((210, 140, 60), 0)]
GREY_SHELF = [((0x3A, 0x3A, 0x3A), 0)] * 7   # covers not decoded yet while the finger moves (the device shows the stock disc placeholder)


def shot(s, work, album, artist, ring, title='Cover Flow'):
    im = PC.page(work, album, artist, title, ring).convert('RGBA'); capsule(s, im); return im


def band_fill(im, x, y, w, h, rgb):
    """patch/coverflow.c band_fill: a rectangle of the scrubber band's axes (x along the ticks, y across), here on the logical frame where the band is the rows CFL_SCRUB_Y and down."""
    ImageDraw.Draw(im).rectangle((x, O['CFL_SCRUB_Y'] + y, x + w - 1, O['CFL_SCRUB_Y'] + y + h - 1), fill=rgb + (255,))


def land_scrubber(im, frac, drag=False, playing=None):
    """patch/coverflow.c on_scrub_paint in landscape, the same integer rectangles in the band: the ticks along CFL_TICK_X0 .. CFL_TICK_X1 on the line CFL_TICK_Y; dragged,
    taller and brighter, the needle and the playing album's dot (CFL_DOT_DY above the line)."""
    x0s, span, ty = O['CFL_TICK_X0'], O['CFL_TICK_X1'] - O['CFL_TICK_X0'], O['CFL_TICK_Y']
    x0 = x0s + round(frac * span)
    pre = 'CF_DRAG_' if drag else 'CF_REST_'
    for i in range(O['CF_TICKS']):
        x = x0s + i * span // (O['CF_TICKS'] - 1); g = bell(abs(x - x0), O[pre + 'SIGMA'])
        h = O[pre + 'H'] + (O[pre + 'BUMP'] * g + 128) // 256; a = O[pre + 'A'] + (O[pre + 'DA'] * g + 128) // 256
        band_fill(im, x - 1, ty - h // 2, O['CF_TICK_W'], h, grey(a)[:3])
    if drag:
        band_fill(im, x0 - 1, ty - O['CF_NEEDLE_H'] // 2, O['CF_NEEDLE_W'], O['CF_NEEDLE_H'], (255, 255, 255))
        if playing is not None:
            px, py, n = x0s + round(playing * span), ty - O['CFL_DOT_DY'], O['CF_DOT']
            band_fill(im, px - n // 2, py + 1, n, n - 2, grey(O['CF_DOT_A'])[:3]); band_fill(im, px - n // 2 + 1, py, n - 2, n, grey(O['CF_DOT_A'])[:3])


def round_cover(x, y, n, r):
    """patch/coverflow.c round_cover: how much of pixel (x, y) of an n px square with corner radius r is inside it, 0..255, from the distance of its centre to the corner's circle in quarter pixels."""
    if not (0 <= x < n and 0 <= y < n): return 0
    dx = 4 * (r - x) - 2 if x < r else 4 * (x - (n - r)) + 2 if x >= n - r else 0
    dy = 4 * (r - y) - 2 if y < r else 4 * (y - (n - r)) + 2 if y >= n - r else 0
    return max(0, min(255, 128 + 64 * (4 * r - math.isqrt(dx * dx + dy * dy))))


def land_bubble(im, font, text):
    """patch/coverflow.c scrub_land's bubble: SG_BUBBLE square (rim #3A3A3A, fill #262626, corner CFL_BUBBLE_R) centred on the centre cover, the text centred in it by line box (top (n - px) / 2)."""
    n, r = O['SG_BUBBLE'], O['CFL_BUBBLE_R']; x0, y0 = O['CFL_CX'] - n // 2, O['CFL_TOP'] + O['ART_SIZE'] // 2 - n // 2
    px = O['SG_BUBBLE_PX'] if len(text) <= 1 else O['SG_BUBBLE_PX_YEAR']
    pix = im.load()
    for y in range(n):
        for x in range(n):
            for cover, rgb in ((round_cover(x, y, n, r), (0x3A,) * 3), (round_cover(x - 1, y - 1, n - 2, r - 1), (0x26,) * 3)):
                if cover:
                    b = pix[x0 + x, y0 + y]; w = cover + (cover >> 7)
                    pix[x0 + x, y0 + y] = tuple((b[k] * (256 - w) + rgb[k] * w) >> 8 for k in range(3)) + (255,)
    font.draw(im, O['CFL_CX'] - font.width(text, px) // 2, y0 + (n - px) // 2, text, px, (255, 255, 255, 255))


def land_counter(im, font, text):
    """scrub_land's counter: the line CFL_COUNT_Y in cf_count's size, grey #AAAAAA, centred in the frame."""
    font.draw(im, (O['CFL_W'] - font.width(text, O['CF_COUNT_PX'])) // 2, O['CFL_COUNT_Y'], text, O['CF_COUNT_PX'], (0xAA, 0xAA, 0xAA, 255))


def landscape_sheet(work, out):
    """The landscape page as the player is held, at rest and while dragged (a letter in the Title order, a year in the Year order)."""
    grey_shelf = [(0x3A, 0x3A, 0x3A)] * 7   # covers not decoded yet while the finger moves (the device shows the stock disc placeholder)
    panels = []
    panels.append(('At rest', PC.landscape(work, 'Kind of Blue', 'Miles Davis', overlay=lambda im, f: land_scrubber(im, 0.46))))
    def drag(album, artist, frac, text, count):
        def paint(im, f):
            land_scrubber(im, frac, True, 0.46)
            if text: land_bubble(im, f, text)
            land_counter(im, f, count)
        return PC.landscape(work, album, artist, shelf=grey_shelf, overlay=paint)
    panels.append(('Dragging, Title order: bubble "M"', drag('Moving Pictures', 'Rush', 0.55, 'M', '663 of 1204')))
    panels.append(('Dragging, Year order: bubble "1997"', drag('OK Computer', 'Radiohead', 0.31, '1997', '373 of 1204')))
    pad, lab = 12, 20
    w, h = panels[0][1].size
    sheet = Image.new('RGB', (w + 2 * pad, len(panels) * (h + lab + pad) + pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (cap, p) in enumerate(panels):
        y = pad + i * (h + lab + pad); d.text((pad, y), cap, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(p, (pad, y + lab))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    PI.save_compact(sheet, out); print('wrote', out, sheet.size)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('work'); ap.add_argument('out', nargs='?', help='the portrait sheet')
    ap.add_argument('--landscape', metavar='PNG', help='write only the landscape sheet (the player held turned) here')
    a = ap.parse_args()
    if a.landscape:
        landscape_sheet(a.work, a.landscape); return
    if not a.out: ap.error('OUT.png or --landscape PNG')
    s = PI.Side(a.work, True)
    panels = []
    im = shot(s, a.work, 'Kind of Blue', 'Miles Davis', SHELF); scrubber(im, 0.46); panels.append(('At rest: "... | Now Playing", the dial', im))
    im = shot(s, a.work, 'Moving Pictures', 'Rush', GREY_SHELF); scrubber(im, 0.55, True, 0.46); bubble(s, im, 'M'); counter(s, im, '663 of 1204')
    panels.append(('Dragging, Title order: bubble "M", covers load on rest', im))
    im = shot(s, a.work, 'OK Computer', 'Radiohead', SHELF); scrubber(im, 0.31, True, 0.46); bubble(s, im, '1997'); counter(s, im, '373 of 1204')
    panels.append(('Dragging, Year order: bubble "1997"', im))
    im = shot(s, a.work, 'Blonde', 'Frank Ocean', SHELF); scrubber(im, 0.08, True, 0.46); counter(s, im, '97 of 1204')
    panels.append(('Dragging, Recently Added: no bubble', im))
    im = shot(s, a.work, 'Kind of Blue', 'Miles Davis', SHELF); scrubber(im, 0.46); menu(s, im)
    panels.append(('"..." card: Search, Go to Playing, sort', im))
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 480 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (cap, p) in enumerate(panels):
        x = pad + i * (320 + pad); d.text((x, pad), cap, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(p.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out); print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
