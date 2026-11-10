#!/usr/bin/env python3
"""Approximate PIL mock-up of Now Playing's More menu over the Now Playing page: the bottom sheet's two pages, the page above
dimmed (patch/playmore.c, docs/modules/playmore.md); not pixel-exact AWTK.

  preview_playmore.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release). The page behind is tools/preview_nowplaying.py's; the sheet is the built
ui/dialog/playmore_dialog.bin with the rows in the order and at the heights the payload gives them (PM_ROW_H each, the sheet
as tall as its rows, top at y 130), drawn by the same painter (inline styles, then the window theme, then default.bin;
text laid out as demo's AWTK does). The row texts are the stock en_US strings (or --lang's table).
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui, awtk_strings
import preview_nowplaying as NP

ROW_H, SCREEN_H, SHEET_W, SV_W = 50, 480, 320, 310
PAGE1 = ['listitem4', 'listitem5', 'listitem2', 'pod_tape', 'pod_vinyl', 'pod_more']   # Look up album, Look up artist, Add to playlist, Cassette Mode, Vinyl Mode, More
PAGE2 = ['pod_back', 'listitem1', 'pod_sleep', 'listitem0', 'pod_art', 'listitem6']   # the back header, Playback speed, Sleep Timer, A-B repeat, Find Cover & Lyrics, Delete
ART_DIM = 100                                                                     # the Find Cover & Lyrics row's opacity (of 255) with the Wi-Fi off (patch/playmore.c PM_ART_DIM)
DIM_ALPHA = 130                                                                   # the asset's highlight="default(alpha=130)"
KEYS = {'scrlabel0': 'player_abrepeat', 'scrlabel1': 'Speed', 'scrlabel2': 'batch_addplaylist', 'scrlabel3': 'player_onlinesearch',
        'scrlabel4': 'player_albuminfo', 'scrlabel5': 'player_songerinfo', 'scrlabel6': 'player_delete', 'label1_msg': 'Files below 48 kHz only',
        'pod_more_label': 'More', 'pod_back_label': 'More', 'pod_tape_label': 'Cassette Mode', 'pod_vinyl_label': 'Vinyl Mode', 'pod_art_label': 'Cover & Lyrics', 'pod_sleep_label': 'powerm_sleep'}
SPEED_SEL = {'img_1x': 'p_1_sel'}                                                  # 1.0X is the selected speed in the mock-up


def tint(argb):
    """'#RRGGBBAA' (AWTK order) -> an RGBA tuple."""
    return tuple(int(argb[i:i + 2], 16) for i in (1, 3, 5, 7))

def sheet(p, im, tree, order, pressed=None, offline=False):
    """Draw the sheet for `order` (row names, top to bottom) on im (the 320 x 480 screen): the whole page dimmed (the highlighter dims the
    full screen, the sheet's own area included, then the glass lies on that), the glass image (the dialog's bg_image) on the bottom, the rows
    transparent over it (the painter draws no row fill), the hairlines and the pressed band (`pressed`: a row name) as the rows' inline styles."""
    h = len(order) * ROW_H; sy = SCREEN_H - h
    im.alpha_composite(Image.new('RGBA', (SHEET_W, SCREEN_H), (0, 0, 0, DIM_ALPHA)), (0, 0))
    glass = p.image('pm_sheet6'); assert glass and glass.size == (SHEET_W, h), 'the page\'s own glass picture (pod_glass: pm_sheet6 for the six rows of both pages), not a crop'
    im.alpha_composite(glass, (0, sy))
    hair = tint(tree.find('listitem1').get('style:normal:border_color'))
    for pos, name in enumerate(order):
        row = tree.find(name)
        row = awtk_ui.Widget(row.type, 0, pos * ROW_H, SV_W, ROW_H, list(row.props), [awtk_ui.Widget(c.type, c.x, c.y, c.w, c.h, list(c.props), list(c.children)) for c in row.children])
        if name == 'listitem1':   # the speed badges: top left of their rectangle plus the style's y_offset 8 (no centring)
            for c in row.children:
                if c.name.startswith('img_'):
                    c.y, c.h = 8, 20
                    if c.name in SPEED_SEL: c.set('image', SPEED_SEL[c.name])
        if name in ('pod_more', 'pod_back', 'pod_tape', 'pod_vinyl', 'pod_art', 'pod_sleep'):
            row.remove('visible'); row.remove('sensitive')       # the asset starts it hidden; the payload shows it
        if name == pressed:
            im.alpha_composite(Image.new('RGBA', (SV_W, ROW_H), tint(tree.find(name).get('style:pressed:bg_color'))), (0, sy + pos * ROW_H))
        if row.get('style:normal:border') == 'top' and pos:
            im.alpha_composite(Image.new('RGBA', (SV_W, 1), hair), (0, sy + pos * ROW_H))     # AWTK blends a 1 px line's alpha like a fill
        box = (0, sy + pos * ROW_H, SV_W, sy + (pos + 1) * ROW_H)
        before = im.crop(box)
        p.walk(im, row, 0, sy, (0, sy, SV_W, sy + h), 0, tree)
        if name == 'pod_art' and offline:
            im.paste(Image.blend(before, im.crop(box), ART_DIM / 255), box)   # the row's opacity (the painter has none): the row over what was under it


def panel(work, lang, order, pressed=None, offline=False):
    raw = os.path.join(work, 'rootfs/release/assets', 'default', 'raw')
    strings = dict(awtk_strings.load(os.path.join(raw, 'strings', lang + '.bin')))
    page = awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read())
    p = NP.Painter(raw); p.playing = True
    im = p.render(page, 0)
    tree = awtk_ui.parse(open(os.path.join(raw, 'ui/dialog/playmore_dialog.bin'), 'rb').read())
    p.sample = {name: strings.get(key, key) for name, key in KEYS.items()}
    sheet(p, im, tree, order, pressed, offline)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('work'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    shots = [('page 1 (when it opens)', panel(a.work, a.lang, PAGE1)), ('page 2 (More tapped)', panel(a.work, a.lang, PAGE2)),
             ('page 2, Wi-Fi off (row dimmed)', panel(a.work, a.lang, PAGE2, None, True)), ('page 2, Delete pressed', panel(a.work, a.lang, PAGE2, 'listitem6'))]
    pad, top = 10, 18
    out = Image.new('RGB', (len(shots) * (NP.W + pad) + pad, NP.BAR + NP.H + top + 18), (40, 40, 40)); d = ImageDraw.Draw(out)
    for i, (label, im) in enumerate(shots):
        x = pad + i * (NP.W + pad); out.paste(im.convert('RGB'), (x, top)); d.text((x, 3), label, fill=(220, 220, 220))
    d.text((pad, NP.BAR + NP.H + top + 3), 'approximate PIL mock-up, not AWTK; the sheet\'s rows as patch/playmore.c arranges them, sample track on Now Playing', fill=(160, 160, 160))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    out.save(a.out, optimize=True); print('wrote', a.out)


if __name__ == '__main__': main()
