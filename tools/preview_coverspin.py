#!/usr/bin/env python3
"""Mock-up of the cover-loading spinner on the Subsonic source pages (docs/modules/subsonic.md): while a cover is still downloading, the Wi-Fi page's 14 px wf_spin frame (the
one ls_spin and the Search page's se_spin turn) is centred on the cover's placeholder disc. A PIL approximation on the shared Albums / Playlists previews; the album page header is
laid out from the AH_* numbers (patch/offsets.inc). Sample data.

  preview_coverspin.py WORKDIR OUTDIR

WORKDIR is a built tree (work/mod-release). Writes coverspin-albums.png, coverspin-playlists.png, coverspin-albumpage.png (the 28 px wf_spinL frame on the 168 px header cover, and the cover arrived) and coverspin-sheet.png (all three) to OUTDIR.
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview_icons as PI, preview_songs as PS

LOADING_ALBUMS = {1, 3, 4, 5, 8, 9}          # indexes into PI.ALBUMS * 2 (the grid order)
LOADING_PLAYLISTS = {'Late Night', 'Favourites'}


def spinner(s, frame=2, large=False):
    return s.img('wf_spinL%d' % frame if large else 'wf_spin%d' % frame)


def centre(im, g, x, y, size):
    im.alpha_composite(g, (x + (size - g.width) // 2, y + (size - g.height) // 2))


def tiles(o, n, scroll=0, block=None):
    cover, gap, m = o['GRID_COVER'], o['GRID_GAP'], o['GRID_MARGIN']
    pitch = cover + o['GRID_TITLE_GAP'] + o['GRID_TITLE_H'] + o['GRID_SUB_H'] + o['GRID_ROW_GAP']
    for a in range(n):
        yield a, m + (a % o['GRID_COLS']) * (cover + gap), 50 + block + o['GRID_ROW_GAP'] + (a // o['GRID_COLS']) * pitch - scroll


def albums(s):
    o = PI.offsets(); orig = PI.ALBUMS
    PI.ALBUMS = [(t, a, None if i in LOADING_ALBUMS else c) for i, (t, a, c) in enumerate(orig * 2)][:len(orig)]
    try:
        # the grid draws ALBUMS * 2: index i and i + 12 share a cover; mark both copies loading
        PI.ALBUMS = [(t, a, None if (i in LOADING_ALBUMS or i + len(orig) in LOADING_ALBUMS) else c) for i, (t, a, c) in enumerate(orig)]
        im = PI.albums_grid(s, 60)
    finally: PI.ALBUMS = orig
    for a, x, top in tiles(o, len(orig) * 2, 60, o['SG_TITLE_H']):
        if a in LOADING_ALBUMS and top + o['GRID_COVER'] // 2 >= 50 and top + o['GRID_COVER'] // 2 <= im.height: centre(im, spinner(s), x, top, o['GRID_COVER'])
    return im


def playlists(s):
    o = PI.offsets(); orig = PI.PLAYLISTS
    PI.PLAYLISTS = [(n, t, () if n in LOADING_PLAYLISTS else a) for n, t, a in orig]
    try: im = PI.playlists_grid(s)
    finally: PI.PLAYLISTS = orig
    pls = sorted(PI.PLAYLISTS, key=lambda p: p[0].casefold())
    for a, x, top in tiles(o, len(pls), 0, o['SG_TITLE_H']):
        if pls[a][0] in LOADING_PLAYLISTS and top + o['GRID_COVER'] // 2 <= im.height: centre(im, spinner(s), x, top, o['GRID_COVER'])
    return im


def albumpage(s, loaded=False):
    """The album page's header (patch/albumpage.c): the tinted window, the AH_ART cover (placeholder + spinner while polled), the lines, Shuffle + Play, the first rows."""
    O = PI.offsets()
    rgb = (70, 110, 190) if loaded else None
    im = Image.new('RGBA', (320, 450), (0x24, 0x24, 0x28, 255)); d = ImageDraw.Draw(im)
    if loaded:
        for y in range(450): d.line((0, y, 319, y), fill=(int(40 * .55), int(60 * .55), int(105 * .55), 255))
    c = PI.rounded(PI.sample_cover(rgb, O['AH_ART']), O['AH_CORNER'])
    im.alpha_composite(c, (O['AH_ART_X'], O['AH_ART_Y']))
    if not loaded: centre(im, spinner(s, 2, True), O['AH_ART_X'], O['AH_ART_Y'], O['AH_ART'])
    s.text(im, 160, O['AH_TITLE_Y'] + O['AH_TITLE_H'] / 2, 'Kind of Blue', 20, anchor='m')
    s.text(im, 160, O['AH_ARTIST_Y'] + O['AH_ARTIST_H'] / 2, 'Miles Davis', 17, (0xAA,) * 3, anchor='m')
    s.text(im, 160, O['AH_META_Y'] + O['AH_META_H'] / 2, '1959 · 8 tracks', 14, (0x9C,) * 3, anchor='m')
    PS.play_header(s, im, O['AH_BTN_Y'] + 2)
    row = O['LIST_ROW_H']
    for i, t in enumerate(['So What', 'Freddie Freeloader']):
        y = O['AH_HDR_H'] + i * row
        d.rectangle((0, y + row - 1, 309, y + row - 1), fill=(0x3A, 0x3A, 0x3E))
        s.text(im, O['AB_NUM_X'] + 22, y + O['AB_TEXT_Y'] + O['AB_TEXT_H'] / 2, str(i + 1), 19, (0xAA,) * 3, 'r')
        s.text(im, O['AB_NUM_X'] + 22 + O['AB_NUM_GAP'], y + O['AB_TEXT_Y'] + O['AB_TEXT_H'] / 2, t, 19)
    PS.glass(s, im, 'ah_nav_back', 7, 44); PS.glass(s, im, 'ah_nav_play', 260, 60); PS.glass(s, im, 'pod_nav_more', 214)
    return im


def label(im, text, s):
    out = Image.new('RGBA', (im.width, im.height + 24), (0x2A, 0x2A, 0x2A, 255)); out.alpha_composite(im, (0, 24))
    ImageDraw.Draw(out).text((6, 6), text, fill=(255, 255, 255))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True); os.makedirs(a.outdir, exist_ok=True)
    al, pl, a1, a3 = albums(s), playlists(s), albumpage(s), albumpage(s, loaded=True)
    ap_ = Image.new('RGBA', (2 * 320 + 10, 450), (0x2A, 0x2A, 0x2A, 255))
    for i, g in enumerate((a1, a3)): ap_.alpha_composite(g, (i * 330, 0))
    ap_ = label(ap_, 'Album page header: 28 px spinner | cover arrived', s)
    for n, im in (('albums', al), ('playlists', pl), ('albumpage', ap_)): im.convert('RGB').save(os.path.join(a.outdir, 'coverspin-%s.png' % n))
    sheet = Image.new('RGBA', (3 * 330 + 10, 450 + 24 + 10 + 474), (0x2A, 0x2A, 0x2A, 255))
    sheet.alpha_composite(label(al, 'Albums grid (source)', s), (5, 5)); sheet.alpha_composite(label(pl, 'Playlists grid (source)', s), (335, 5))
    sheet.alpha_composite(label(a1, 'Album page, 28 px spinner', s), (665, 5))
    sheet.alpha_composite(label(a3, 'Album page, cover arrived', s), (5, 489))
    sheet.convert('RGB').save(os.path.join(a.outdir, 'coverspin-sheet.png'))
    print('wrote 4 PNGs to', a.outdir)


if __name__ == '__main__':
    main()
