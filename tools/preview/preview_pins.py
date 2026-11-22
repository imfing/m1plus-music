#!/usr/bin/env python3
"""Previews of the Home pins (docs/modules/pins.md): Home with four, six (the cap), two, one and no pinned items above the rows (a song's tile is an album's: its cover and its title), a tile mid-drag (held, drawn larger, the others closed up around its slot), a tile's long press sheet (an album's, and a song's two rows), round artist tiles among the square ones, the Artists page's hold sheet, the artist's Albums page "..." card with Pin Artist, the Albums page's long press sheet, the album page's capsule "..." and its sheet, a Recently Played tile's sheet on Home and the track rows' sheet with Pin Song. Approximate, not AWTK; sample data.

  uv run python -I tools/preview/preview_pins.py WORKDIR [OUTDIR]       (WORKDIR: the built release tree, work/mod-release; default OUTDIR out/pins)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from PIL import Image, ImageDraw
import preview, preview_icons as PI, preview_dailymix as PD, preview_songs as PSG, preview_rowmenu as PRM, preview_minibar, pod_ui as U, pod_pages as P

C, COLS, MARGIN, GAP, R, TGAP, TH = (U.OFFSETS[k] for k in ('PIN_COVER', 'PIN_COLS', 'PIN_MARGIN', 'PIN_GAP', 'PIN_R', 'PIN_TGAP', 'PIN_TH'))   # patch/offsets.inc
BAR = ('Blue in Green (Remastered, Mono Version)', 'Miles Davis', (70, 110, 190))
PINNED = [('Kind of Blue', (70, 110, 190)), ('Late Night Jazz', (40, 40, 48)), ('The Boys of Dungeon Lane', (225, 220, 205)), ('Road Trip', (200, 120, 50)),
          ('Homogenic', (190, 90, 120)), ('Mezzanine', (110, 90, 130))]


ARTIST_PINS = [('Miles Davis', (70, 110, 190), 1), ('Kind of Blue', (70, 110, 190)), ('Nina Simone', (110, 90, 130), 1), ('Homogenic', (190, 90, 120)), ('The Beatles', (200, 155, 60), 1), ('Road Trip', (200, 120, 50))]


def pinned(s, items, lift=None):
    """The section as the payload paints it: PIN_COLS columns of PIN_COVER px covers with PIN_R corners, the name centred under each, nothing above the first row but PIN_TOP.
    lift = (tile, slot, finger x, finger y) in section coordinates: that tile is held and dragged, drawn PIN_LIFT px larger on the finger, the others closed up around its slot."""
    rows = (len(items) + COLS - 1) // COLS
    im = Image.new('RGBA', (320, U.PIN_H(rows)), (0, 0, 0, 255)); k = 4
    n = len(items)

    def cover(rgb, size, round_=False):
        art = PI.sample_cover(rgb, C).resize((size, size), Image.LANCZOS)
        mask = Image.new('L', (size * k, size * k), 0)
        if round_: ImageDraw.Draw(mask).ellipse((0, 0, size * k - 1, size * k - 1), fill=255)   # an artist: the photo cut to the circle (patch/pins.c pn_circle), black outside
        else: ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * k - 1, size * k - 1), radius=R * k, fill=255)
        art.putalpha(mask.resize((size, size), Image.LANCZOS))
        return art

    def draw(i, name, rgb, x, y, grow=0, round_=False):
        im.alpha_composite(cover(rgb, C + 2 * grow, round_), (x - grow, y - grow))
        s.text(im, x + C / 2, y + C + TGAP + TH / 2, s.clip(name, U.PIN_TEXT_PX, C), U.PIN_TEXT_PX, anchor='m')

    rest = [i for i in range(n) if not lift or i != lift[0]]
    slots = [i for i in range(n) if not lift or i != lift[1]]   # the slot the held tile would land in stays empty
    for slot, i in zip(slots, rest):
        draw(i, *items[i][:2], U.pin_x(slot, n), U.PIN_TOP + slot // COLS * U.PIN_PITCH, 0, len(items[i]) > 2)
    if lift:
        draw(lift[0], *items[lift[0]][:2], lift[2] - C // 2, lift[3] - C // 2, U.OFFSETS['PIN_LIFT'], len(items[lift[0]]) > 2)
    return im


def home(s, items, daily, scroll=0, lift=None):
    """The Home instance scrolled `scroll` px: the pins first, then the rows (Extras last), the Daily Mix card, the Recently Played shelf, the mini bar."""
    nrows = len(P.DEFAULT_MENU) + 1
    base = preview.menu_page(s, None, home=True).convert('RGBA')
    parts = ([pinned(s, items, lift)] if items else []) + [base.crop((0, 10, 320, 10 + nrows * U.ROW_H)), daily, preview.shelf_image(s, preview.SHELF_ALBUMS)]
    content = Image.new('RGBA', (320, sum(p.height for p in parts) + U.MB_PAD + 430), (0, 0, 0, 255)); y = 0
    for p in parts: content.paste(p, (0, y)); y += p.height
    im = Image.new('RGBA', base.size, (0, 0, 0, 255))
    im.paste(base.crop((0, 0, 320, 10)), (0, 0))
    im.paste(content.crop((0, scroll, 320, scroll + 430)), (0, 10))
    preview_minibar.draw(im, U.MB_X, U.MB_Y, s.img, lambda im_, x, cy, t, px, col=None: s.text(im_, x, cy, t, px, col) if col else s.text(im_, x, cy, t, px), s.clip, BAR[0], BAR[1],
                         PI.sample_cover(BAR[2], U.MB_ART), True, True)
    return im


def PS_AZ(s):
    return PSG.tr(s, 'A–Z')


def main():
    work = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(preview.build.ROOT, 'out', 'pins')
    os.makedirs(out, exist_ok=True)
    s = PD.side(work)
    daily = PD.section_image(s, PD.PALETTES[0][1])
    sheet_rows = [('Play', 'rm_ic_pplay'), ('Shuffle', 'rm_ic_pshuffle'), ('Unpin Album', 'rm_ic_unpin'), ('Add to Playlist', 'rm_ic_add'), ('Play Next', 'rm_ic_next'), ('Play After', 'rm_ic_after')]   # the album sheet (patch/rowmenu.c rowmenu_open_album)
    lp = home(s, PINNED[:4], daily)
    PSG.row_menu(s, lp, keys=tuple(k for k, _ in sheet_rows), glyphs=tuple(g for _, g in sheet_rows))
    two = home(s, [('Blue in Green', (70, 110, 190))] + PINNED[:3], daily)   # a song's tile: its album's cover, the title
    PSG.row_menu(s, two, keys=('Play', 'Unpin Song'), glyphs=('rm_ic_pplay', 'rm_ic_unpin'))
    al = PI.albums_grid(s).convert('RGBA')   # the Albums page: a long press on an album
    PRM.sheet(s, al, [('Pin Album', 'rm_ic_pin') if k == 'Unpin Album' else (k, g) for k, g in sheet_rows])
    ap = PRM.album(s).convert('RGBA')   # the album page: Select | "..." | Now Playing, and the "..." sheet
    aps = PRM.album(s, pins=True).convert('RGBA')
    rp = home(s, PINNED[:2], daily, scroll=640)   # Home scrolled to the Recently Played shelf: a tile held
    PRM.sheet(s, rp, [('Pin Album', 'rm_ic_pin') if k == 'Unpin Album' else (k, g) for k, g in sheet_rows])
    tr_ = PSG.page(s).convert('RGBA')   # a track row's sheet: the sixth row, Pin Song
    PSG.row_menu(s, tr_)   # (its default rows: Pin Song, Add to Playlist, Favorite, Get Info | Play Next, Play After)
    mixed = home(s, ARTIST_PINS, daily)   # artists (round photos) among albums and playlists (an item with a third field is an artist)
    ar_sheet = home(s, ARTIST_PINS[:4], daily)
    PSG.row_menu(s, ar_sheet, keys=('Play', 'Shuffle', 'Unpin Artist'), glyphs=('rm_ic_pplay', 'rm_ic_pshuffle', 'rm_ic_unpin'))
    import preview_artists_photo as PA
    arp = PA.artists_page(s)   # the Artists page: a row held
    PSG.row_menu(s, arp, keys=('Play', 'Shuffle', 'Pin Artist'), glyphs=('rm_ic_pplay', 'rm_ic_pshuffle', 'rm_ic_pin'))
    asp = PA.artist_page(s, 'Miles Davis', ((0x30, 0x58, 0x90), (0x08, 0x10, 0x20))).convert('RGBA')   # the artist's Albums page: the "..." card, Find Artist Photo and Pin Artist, Grid, List, three sorts
    asp.alpha_composite(Image.new('RGBA', asp.size, (0, 0, 0, 0x82)))
    PI.view_card(s, asp, [('Find Artist Photo', 'pod_ic_vsphoto', False, None), ('Pin Artist', 'pod_ic_vspin', False, None), ('Grid', 'pod_ic_vsgrid', False, None), ('List', 'pod_ic_vslist', True, None),
                          ('Title', None, True, PS_AZ(s)), ('Recently Added', None, False, None), ('Year', None, False, None)], 'vs_glass7', (2, 4))
    dr = home(s, PINNED[:4], daily, lift=(0, 3, U.pin_x(3, 4) + C // 2 + 14, U.PIN_TOP + U.PIN_PITCH + C // 2 + 10))   # the first tile held and dragged over the fourth slot
    panels = [('Pinned: 4 items, above the rows', home(s, PINNED[:4], daily)), ('Pinned: 6 items (the cap)', home(s, PINNED, daily)), ('Pinned: 2 items, centred', home(s, PINNED[:2], daily)), ('Pinned: 1 item, centred', home(s, PINNED[:1], daily)),
              ('Nothing pinned: Home as today', home(s, [], daily)), ('Long press a pinned tile', lp), ('Hold and drag a tile to reorder', dr), ('Long press a song tile', two), ('Albums: long press an album', al), ('Album page: the "..."', ap), ('Album page: its sheet', aps), ('Home: long press a Recently Played tile', rp), ('Track row sheet: Pin Song', tr_),
              ('Pinned artists: round photos among albums', mixed), ('Long press a pinned artist', ar_sheet), ('Artists: long press an artist', arp), ('Artist page: the "..." card', asp)]
    pad, lab = 12, 20
    H = max(im.height for _, im in panels)
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, H + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(panels):
        x = pad + i * (320 + pad); d.text((x, pad), t, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    name = os.path.join(out, 'pins-home.png')
    sheet.save(name); print('wrote', name, sheet.size)


if __name__ == '__main__':
    main()
