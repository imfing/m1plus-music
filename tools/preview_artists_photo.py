#!/usr/bin/env python3
"""Approximate PIL mock-up of the artist photos (patch/artists.c, patch/albums.c, patch/artistphoto.c; docs/modules/artists.md "Artist photos", docs/modules/albums.md) drawn from
the built tree and the payload's own constants (patch/artists.c AR_*, patch/artistphoto.h AP_*, patch/offsets.inc PH_*, AL_*, LIST_*):
  1  the Artists page, layout A: a 40 px circle at x 16 centred in the 52 px row, the name and the hairline from x 68; stand-in photos for some rows, the shared placeholder for the rest;
  2  an artist's Albums page (list mode) at rest: the album page's header with a circle (88 px at (116, 8)), the name under it, the Play / Shuffle pills, the albums;
  3  the same page scrolled past the name: the navbar's small title, the circle cut by the window's top;
  4  an artist without a photo: the same header without the circle (no placeholder), the name and the pills PH_SHIFT higher, the rows with them (patch/albums.c al_gone); panels 2 and 4 side by side show
     the two layouts; 5 is the no-photo page scrolled past the name.
The Artists rows' placeholder is the payload's: a #333333 circle with the mic-vocal glyph (images/xx/pod_ic_ar_art.png, #8C8C8C) at 0.52 of the diameter, edge antialiased. Not pixel-exact AWTK: the text is
the project's text model, the photos and covers are stand-in gradients, the circles are drawn at 4x and reduced.

  preview_artists_photo.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release).
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdefs
import preview_icons as PI
import mod_icons as M
import preview_songs as PS

W, WIN, NAV = 320, 450, 50
ROOT = M.ROOT
O = PI.offsets()
AP = cdefs.defines(os.path.join(ROOT, 'patch', 'artistphoto.h'), ['AP_ROW_D', 'AP_HEAD_D'])
COMMON = cdefs.defines(os.path.join(ROOT, 'patch', 'common.h'), ['POD_CHEV_W', 'POD_CHEV_H'])
AR = cdefs.defines(os.path.join(ROOT, 'patch', 'artists.c'),
                   ['AR_ROW', 'AR_PHOTO', 'AR_PHOTO_X', 'AR_NAME_X', 'AR_TEXT_Y', 'AR_TEXT_H', 'AR_TEXT_END', 'AR_CHEV_X', 'AR_TOP'], known={**O, **AP, **COMMON})
CHEV_RGB, HAIR, TILE, GLYPH_COVER = (0x8A,) * 3, (0x22, 0x22, 0x22), (0x33,) * 3, M.COVER_FRAC
assert AR['AR_PHOTO'] == AP['AP_ROW_D'] and AP['AP_HEAD_D'] == O['AL_PHOTO_D']

# the Artists page: (name, stand-in photo gradient or None: no photo). Sections by the Initial.
ARTISTS = [('Arctic Monkeys', ((0x3A, 0x6E, 0x9E), (0x12, 0x1E, 0x33))), ('Aretha Franklin', None), ('The Beatles', ((0xC8, 0x9B, 0x3C), (0x5A, 0x3A, 0x18))), ('Bill Evans', None),
           ('Björk', ((0xB0, 0x5A, 0x7A), (0x40, 0x18, 0x2C))), ('Mahavishnu Orchestra with John McLaughlin', None), ('Massive Attack', ((0x7A, 0x7A, 0x50), (0x20, 0x20, 0x14))),
           ('Miles Davis', ((0x30, 0x58, 0x90), (0x08, 0x10, 0x20))), ('周杰倫', None)]
LETTERS = {'Arctic Monkeys': 'A', 'Aretha Franklin': 'A', 'The Beatles': 'B', 'Bill Evans': 'B', 'Björk': 'B', 'Mahavishnu Orchestra with John McLaughlin': 'M', 'Massive Attack': 'M',
           'Miles Davis': 'M', '周杰倫': 'Z'}
# the artist's page: album, year, cover colour
ALBUMS = [('Kind of Blue', '1959', 0), ('Bitches Brew', '1970', 1), ('Jazz Hits', '', 2), ('Sketches of Spain', '1960', 3), ('All Songs', '', None)]


def circle(d, fill_fn):
    """A d x d RGBA disc, antialiased by drawing at 4x and reducing; fill_fn(size) gives the RGB image at 4x."""
    k = 4; S = d * k
    mask = Image.new('L', (S, S), 0); ImageDraw.Draw(mask).ellipse((0, 0, S - 1, S - 1), fill=255)
    out = Image.new('RGBA', (d, d), (0, 0, 0, 0))
    out.paste(fill_fn(S).resize((d, d), Image.LANCZOS).convert('RGBA'), (0, 0), mask.resize((d, d), Image.LANCZOS))
    return out


def gradient(c1, c2):
    def fn(S):
        im = Image.new('RGB', (S, S)); px = im.load()
        for y in range(S):
            for x in range(S):
                t = (x + y) / (2 * S - 2)
                px[x, y] = tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        return im
    return fn


def placeholder(s, d):
    """patch/artistphoto.c ap_placeholder: the tile colour circle, the asset's glyph reduced to 0.52 of the diameter, composed with its coverage."""
    c = circle(d, lambda S: Image.new('RGB', (S, S), TILE))
    gs = d * 52 // 100
    g = s.img('pod_ic_ar_art').resize((gs, gs), Image.BOX)
    c.alpha_composite(g, ((d - gs) // 2, (d - gs) // 2))
    mask = circle(d, lambda S: Image.new('RGB', (S, S), (255,) * 3)).getchannel('A')
    c.putalpha(mask)
    return c


def photo(c, d):
    return circle(d, gradient(*c))


def chevron():
    k = 4; im = Image.new('L', (COMMON['POD_CHEV_W'] * k, COMMON['POD_CHEV_H'] * k), 0)
    ImageDraw.Draw(im).line([(1.5 * k, 2.5 * k), (8.0 * k, 8.0 * k), (1.5 * k, 13.5 * k)], fill=255, width=int(2.2 * k), joint='curve')
    return Image.new('RGBA', (COMMON['POD_CHEV_W'], COMMON['POD_CHEV_H']), CHEV_RGB + (255,)), im.resize((COMMON['POD_CHEV_W'], COMMON['POD_CHEV_H']), Image.LANCZOS)


def artists_page(s, scroll=300):
    """The Artists page (AR_* of patch/artists.c)."""
    row, top, hdr = AR['AR_ROW'], AR['AR_TOP'], O['SG_HDR_H']
    tall = Image.new('RGBA', (W, top + len(ARTISTS) * row + 4 * hdr + 40), (0, 0, 0, 255)); d = ImageDraw.Draw(tall)
    s.text(tall, O['SG_TITLE_X'], O['SG_TITLE_H'] / 2, PS.tr(s, 'Artists'), 32)
    y, last, letters = top, None, []
    for name, ph in ARTISTS:
        if LETTERS[name] != last:
            PS.header(s, tall, LETTERS[name], y); letters.append(LETTERS[name]); y += hdr; last = LETTERS[name]
        disc = photo(ph, AR['AR_PHOTO']) if ph else placeholder(s, AR['AR_PHOTO'])
        tall.alpha_composite(disc, (AR['AR_PHOTO_X'], y + (row - AR['AR_PHOTO']) // 2))
        d.rectangle((AR['AR_NAME_X'], y + row - 1, O['LIST_HAIR_END'] - O['SG_RAIL_INSET'] - 1, y + row - 1), fill=HAIR)
        s.text(tall, AR['AR_NAME_X'], y + row / 2, s.clip(name, 21, AR['AR_TEXT_END'] - AR['AR_NAME_X']), 21)
        bar, mask = chevron()
        tall.paste(bar, (AR['AR_CHEV_X'], y + (row - COMMON['POD_CHEV_H']) // 2), mask)
        y += row
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    im.alpha_composite(tall.crop((0, scroll, W, scroll + WIN - NAV)), (0, NAV))
    PS.navbar(s, im, scroll, None, 'Artists', False, True)
    PS.rail(s, im, letters, None, WIN - NAV)
    return im


def artist_page(s, name, ph, scroll=0):
    """An artist's Albums page in list mode with the header (patch/albums.c: AL_PHOTO_*, PH_NAME_*, AL_HEAD_*); ph None: no photo, the circle's room (PH_SHIFT) is gone and nothing else differs."""
    gone = 0 if ph else O['PH_SHIFT']
    end, rows_y = O['AL_HEAD_END'] - gone, O['AL_HEAD_END'] - gone + O['GRID_ROW_GAP']
    tall = Image.new('RGBA', (W, rows_y + len(ALBUMS) * O['LIST_ROW_H'] + 60), (0, 0, 0, 255)); d = ImageDraw.Draw(tall)
    c = O['AL_PHOTO_D']
    if ph: tall.alpha_composite(photo(ph, c), (O['AL_PHOTO_X'], O['AL_PHOTO_Y']))
    s.text(tall, O['PH_NAME_X'] + O['PH_NAME_W'] / 2, O['AL_NAME_Y'] - gone + O['PH_NAME_H'] / 2, s.clip(name, 22, O['PH_NAME_W']), 22, anchor='m')
    PS.pill(s, tall, O['AL_PLAY_X'], O['AL_HEAD_PILL_Y'] - gone, PS.tr(s, 'Play'), s.img('sg_play'), w=O['AL_PLAY_W'])
    PS.pill(s, tall, O['AL_SHUFFLE_X'], O['AL_HEAD_PILL_Y'] - gone, PS.tr(s, 'Shuffle'), s.img('sg_shuffle'), w=O['AL_SHUFFLE_W'])
    assert O['AL_HEAD_PILL_Y'] - gone + O['SG_PILL_H'] == end and (ph or (O['PH_SHIFT'] == O['AL_PHOTO_Y'] + c and end == O['AL_PILLS_END']))
    for i, (album, year, ci) in enumerate(ALBUMS):
        y = rows_y + i * O['LIST_ROW_H']
        tall.alpha_composite(PI.rounded(PI.sample_cover(PI.ALBUMS[ci][2] if ci is not None else None, O['LIST_ART']), O['LIST_R']), (O['LIST_ART_X'], y + O['LIST_ART_Y']))
        room = O['LIST_TEXT_X'] + O['LIST_TEXT_W_CHEV']
        s.text(tall, O['LIST_TEXT_X'], y + O['LIST_TITLE_Y'] + O['LIST_TITLE_H'] / 2, s.clip(PS.tr(s, 'All Songs') if ci is None else album, 21, room - O['LIST_TEXT_X']), 21)
        if year: s.text(tall, O['LIST_TEXT_X'], y + O['LIST_SUB_Y'] + O['LIST_SUB_H'] / 2, year, 18, (0xAA,) * 3)
        d.rectangle((O['LIST_TEXT_X'], y + O['LIST_ROW_H'] - 1, O['LIST_HAIR_END'] - 1, y + O['LIST_ROW_H'] - 1), fill=HAIR)
        bar, mask = chevron()
        tall.paste(bar, (O['LIST_CHEV_X'], y + (O['LIST_ROW_H'] - COMMON['POD_CHEV_H']) // 2), mask)
    im = Image.new('RGBA', (W, WIN), (0, 0, 0, 255))
    im.alpha_composite(tall.crop((0, scroll, W, scroll + WIN - NAV)), (0, NAV))
    # the navbar: Back, Cover Flow | ... | Now Playing, the small title once the name's box has scrolled away (AL_HEAD_COLLAPSE)
    PS.navbar(s, im, scroll - (O['AL_HEAD_COLLAPSE'] - gone - O['SG_COLLAPSE']), None, name, True, True)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    me = ((0x30, 0x58, 0x90), (0x08, 0x10, 0x20))
    panels = [('Artists: 40 px circles, names from x 68', artists_page(s)),
              ('An artist\'s page: the photo header', artist_page(s, 'Miles Davis', me)),
              ('Scrolled past the name', artist_page(s, 'Miles Davis', me, scroll=O['AL_HEAD_COLLAPSE'] + 40)),
              ('No photo: the same header without the circle', artist_page(s, 'Aretha Franklin', None)),
              ('No photo, scrolled past the name', artist_page(s, 'Aretha Franklin', None, scroll=O['AL_HEAD_COLLAPSE'] - O['PH_SHIFT'] + 40))]
    pad, lab = 16, 22
    sheet = Image.new('RGB', (len(panels) * (W + pad) + pad, WIN + lab + 2 * pad), (0x2A, 0x2A, 0x2A))
    dr = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (W + pad)
        sheet.paste(im.convert('RGB'), (x, pad))
        dr.text((x, pad + WIN + 6), title, fill=(0xAA,) * 3, font=PI.ANN)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
