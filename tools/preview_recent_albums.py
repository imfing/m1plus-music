#!/usr/bin/env python3
"""Mock-up of the Recently Added page with a navbar view toggle (docs/modules/recent-albums.md): a PIL approximation built on preview_songs.py's
helpers (the Songs rows, pills, glass pieces) and the shared Albums grid's cell geometry (offsets.inc GRID_*, the Recently Played shelf's look).
Not the payload's paint (the songs preview path draws no real page); the numbers are the page's (offsets.inc). make preview also writes both PNGs beside the sheet. The page keeps the Songs view; the toggle (Albums page slot 214) switches to the newest-first Albums grid.

  preview_recent_albums.py WORKDIR OUTDIR

WORKDIR is a built tree (work/mod-release). Writes recent-songs-view.png and recent-album-view.png (320 x 450) to OUTDIR. The navbars are the real
glass pieces in one capsule: songs view Search 122 | Select 168 | grid toggle 214 | Now Playing 260; album view Search 168 | list toggle 214 | Now Playing 260.
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview_icons as PI
import preview_songs as PS

O, W, WIN, NAV = PS.O, PS.W, PS.WIN, PS.NAV
ALBUMS = [('Kind of Blue', 'Miles Davis', 0), ('Music Has the Right to Children', 'Boards of Canada', 5), ('Homogenic', 'Bjork', 2),
          ('Dummy', 'Portishead', 9), ('Kid A', 'Radiohead', 6), ('Mezzanine', 'Massive Attack', 3), ('Rumours', 'Fleetwood Mac', 4),
          ('Blue', 'Joni Mitchell', 7)]


def title(s, im):
    s.text(im, O['SG_TITLE_X'], O['SG_TITLE_H'] / 2, PS.fit(s, PS.tr(s, 'Recently Added'), 32, O['SG_TITLE_W']), 32)


def navbar(s, im, pieces):
    """Back disc, then the capsule's pieces (name, x) from the left cap to the middles, Now Playing as the right cap at 260."""
    d = ImageDraw.Draw(im); d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    PS.glass(s, im, 'ah_nav_back', 7, 44)
    for name, x in pieces: PS.glass(s, im, name, x)
    PS.glass(s, im, 'ah_nav_play', 260, 60)


def album_view(s):
    tall = Image.new('RGBA', (W, WIN - NAV), (0, 0, 0, 255)); title(s, tall)
    grey = (0xAA,) * 3; top = O['SG_PILL_Y']                    # where the pills would begin: no pills above an album grid
    for i, (album, artist, ci) in enumerate(ALBUMS):
        x = O['GRID_MARGIN'] + i % 2 * (O['GRID_COVER'] + O['GRID_GAP'])
        y = top + i // 2 * (O['GRID_COVER'] + 46 + O['GRID_ROW_GAP'])
        if y >= WIN - NAV: continue
        tall.alpha_composite(PI.rounded(PI.sample_cover(PI.ALBUMS[ci][2], O['GRID_COVER']), O['GRID_R']), (x, y))
        ty = y + O['GRID_COVER'] + O['GRID_TITLE_GAP']
        s.text(tall, x, ty + O['GRID_TITLE_H'] / 2, s.clip(album, 18, O['GRID_COVER']), 18)
        s.text(tall, x, ty + O['GRID_TITLE_H'] + O['GRID_SUB_H'] / 2, s.clip(artist, 15, O['GRID_COVER']), 15, grey)
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255)); im.alpha_composite(tall, (0, NAV))
    navbar(s, im, [('pod_nav_search', 168), ('pod_nav_list', 214)])
    return im


def songs_view(s):
    tall, _ = PS.content(s, title='Recently Added')           # the current page, unchanged: title, pills, rows (no sections)
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255)); im.alpha_composite(tall.crop((0, 0, W, WIN - NAV)), (0, NAV))
    navbar(s, im, [('pod_nav_search', 122), ('pod_nav_select', 168), ('pod_nav_grid', 214)])
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, 'en_US')
    os.makedirs(a.outdir, exist_ok=True)
    for name, im in (('songs', songs_view(s)), ('album', album_view(s))):
        out = os.path.join(a.outdir, f'recent-{name}-view.png'); PI.save_compact(im.convert('RGB'), out); print('wrote', out, im.size)
    px = PI.title_px(s.tree)
    print('small title room before x 122:', 122 - O['NAV_TITLE_X'], 'px; "Recently Added" at', px, 'px =', s.font.width('Recently Added', px))


if __name__ == '__main__': main()
