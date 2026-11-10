#!/usr/bin/env python3
"""Approximate PIL mock-up of the track rows' "..." and its menu (patch/rowmenu.c, docs/modules/rowmenu.md), drawn from the built assets and the payload's constants:

  - the Songs page with the A-Z rail: the grey "..." left of the rail, the titles 36 px narrower than before;
  - the same page with the menu open: Now Playing's More sheet at the window's foot;
  - a list (no rail) with the menu open, and again for a track that is a favourite (Undo Favorite, the filled star);
  - the album page scrolled to its tracks, the "..." on every track, and the menu open.

Not pixel-exact AWTK (the text is the project's own text model, the covers are stand-in gradients).

  preview_rowmenu.py WORKDIR OUT.png [--lang CODE]
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview_icons as PI
import preview_songs as PS

O = PI.offsets()
ROW, NAV = O['LIST_ROW_H'], PS.NAV
TRACKS = ['So What', 'Freddie Freeloader', 'Blue in Green', 'All Blues', 'Flamenco Sketches', 'Flamenco Sketches (Alt)', 'So What (Alt)', 'Blue in Green (Alt)']
TONE = (0x3A, 0x1E, 0x24)   # a cover's tone behind the album page (pod_tone of a red cover, approximately)


ND_STATES = {   # a Navidrome row's sheet (patch/rowmenu.c rm_third): the third row and the star by the row's state
    'new': (('Play Next', 'Play After', 'Download', 'Favorite', 'Get Info'), ('rm_ic_next', 'rm_ic_after', 'rm_ic_dl', 'rm_ic_fav', 'rm_ic_info')),
    'done': (('Play Next', 'Play After', 'Remove Download', 'Undo Favorite', 'Get Info'), ('rm_ic_next', 'rm_ic_after', 'rm_ic_rmdl', 'rm_ic_unfav', 'rm_ic_info')),
    'busy': (('Play Next', 'Play After', 'Cancel Download', 'Favorite', 'Get Info'), ('rm_ic_next', 'rm_ic_after', 'rm_ic_cxdl', 'rm_ic_fav', 'rm_ic_info'))}


def album(s, scroll=300, menu=False, playing=2, nd=None):
    """The album page (patch/albumpage.c) scrolled to its tracks: the tinted window, the glass Back and Select | Now Playing capsule, each track's number, title and "..." (the title ends
    RM_TEXT_GAP before the zone), the hairline; the menu when asked. 450 px of window."""
    win, hdr = O['AH_WIN_H'], O['AH_HDR_H']
    im = Image.new('RGBA', (320, win), TONE + (255,))
    d = ImageDraw.Draw(im)
    more, right = PS.dots(s), O['RM_MORE_RIGHT']
    tx = O['AB_NUM_X'] + O['ROW_NUM_W'] + O['AB_NUM_GAP']
    room = right - O['RM_MORE_W'] - O['RM_TEXT_GAP'] - tx
    for i in range(len(TRACKS)):
        y = hdr + i * ROW - scroll
        if y + ROW < 0 or y > win: continue
        d.rectangle((0, y + ROW - 1, 309, y + ROW - 1), fill=(0x55, 0x3A, 0x40))
        if i == playing: im.alpha_composite(s.img('ah_wave'), (O['AB_NUM_X'] + O['ROW_NUM_W'] - O['AB_WAVE'], y + O['AB_TEXT_Y'] + (O['AB_TEXT_H'] - O['AB_WAVE']) // 2))
        else: s.text(im, O['AB_NUM_X'] + O['ROW_NUM_W'], y + O['AB_TEXT_Y'] + O['AB_TEXT_H'] / 2, str(i + 1), 19, (0xAA, 0xAA, 0xAA), 'r')
        s.text(im, tx, y + O['AB_TEXT_Y'] + O['AB_TEXT_H'] / 2, s.clip(TRACKS[i], 19, room), 19)
        im.alpha_composite(more, (right - O['RM_MORE_W'] + (O['RM_MORE_W'] - O['RM_DOTS_PX']) // 2, y + (ROW - 1 - O['RM_DOTS_PX']) // 2))
    for name, x, w in (('ah_nav_back', 7, 44), ('pod_nav_selectl', O['NAV_VIEW_X'], O['NAV_VIEW_W']), ('ah_nav_play', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (x + (w - g.width) // 2, (NAV - g.height) // 2))
    if menu: PS.row_menu(s, im, *([ND_STATES[nd][0]] if nd else []), **({'glyphs': ND_STATES[nd][1]} if nd else {}))
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    items, heads, _ = PS.build_items()
    scroll = heads['A'] - 8
    fav = PS.tr(s, 'Favorites')
    panels = [('Songs: the "..." left of the A-Z rail', PS.page(s, scroll=scroll)),
              ('Songs: the menu (a bottom sheet)', PS.page(s, scroll=scroll, row_menu_at=True)),
              ('A list: no rail, the menu', PS.page(s, title=fav, row_menu_at=True, direct=True)),
              ('A favourite: Undo Favorite', PS.page(s, title=fav, row_menu_at='fav', direct=True)),
              ('Album page: the "..." on every track', album(s)),
              ('Album page: the menu', album(s, menu=True)),
              ('Navidrome: the sheet', album(s, menu=True, nd='new')),
              ('Navidrome: downloaded, a favourite', album(s, menu=True, nd='done')),
              ('Navidrome: downloading', album(s, menu=True, nd='busy'))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 450 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (320 + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
