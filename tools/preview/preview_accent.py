#!/usr/bin/env python3
"""The Accent feature's sheets (docs/modules/accent.md), drawn through the real model: every colour goes through palette.map_colour and every image through palette.render_image (tools/palette.py,
which test/pod/palette.py compares with the C of patch/palette.c) (row glyphs tinted by render_image like the decode hook). The screens are the built tree's own assets and the other previews' helpers
(preview_settings.draw_page, preview_nowplaying.Painter). Approximate (PIL, not AWTK); sample data.

  out/preview/accent-black.png    rows = the accents, columns = the screens: Settings (Library pressed), the M1+ Music menu (glyphs in the accent, Albums pressed), a song list (a row pressed, the playing wave),
                                  a card with switches, a picker row and a slider, Now Playing's progress bar
  out/preview/accent-picker.png   the Appearance page and the Accent picker (Settings > Appearance > Accent) with each accent chosen, and the pressed row of the picker
  out/preview/accent-tinted.png   Background Tinted x each accent: the M1+ Music menu, Settings, the Appearance page (Background row), a song list, the pull-down, Now Playing (its cover background untouched)
  out/preview/accent-tints.png    the images the accent tints, one row per accent (the mixed track / fill pixels of other_progress and datetime_back zoomed)
  out/preview/uic2/accent-*.png   the elements the second consistency pass made follow the accent (Neutral | Teal | Orange panels): tenband, band (the EQ pages' thumb, fill and curve), songs-select (selected mark),
                                  songs-rail (the index rail's disc), sheet (a bottom sheet's pressed row), cachepill (Home cache pill's fill), podring (the Podcasts and download rings' arcs)

Roles (Neutral = today's colours for all of them): a pressed row is mix(surface, accent, 22 %) with white text and its glyph in the accent; a switch on has an accent track and a white knob; the
slider and progress fill, the picker check and the playing wave are the accent. Never accent: chevrons, secondary text, navbar buttons, body text, card backgrounds. The main menu's glyphs are the accent at rest. Backgrounds: Black, and Tinted (dark neutrals take 12 % of the accent).

Usage: uv run python -I tools/preview/preview_accent.py WORKDIR [OUT_DIR]     (default out/preview/)
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
import build, palette as PM, preview_icons as PI, preview_settings as PS, preview_nowplaying as NP

W, NAV, H = 320, 50, 480
ACC = PM.ACCENTS   # neutral, red, ...


def rgb(css):
    css = css.lstrip('#')
    return tuple(int(css[i:i + 2], 16) for i in (0, 2, 4))


def lum(c):
    f = lambda v: (v / 255 / 12.92) if v / 255 <= 0.03928 else ((v / 255 + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class Palette:
    """One background and one accent, as the hooks of patch/palette.c give them: the object preview_settings.draw_page takes. Everything goes through tools/palette.py (the model the C is tested against)."""
    def __init__(self, bg, ac, cover=False):
        self.bg, self.ac, self.cover = bg, ac, cover   # cover: a cover-tinted page is in front (the Tinted wash leaves its colours alone)

    def ink(self, c):
        """A colour (r, g, b) or (r, g, b, a) as the style hooks give it."""
        c = tuple(c)
        return PM.map_colour(c + (255,) * (len(c) == 3), self.bg, self.ac, self.cover)[:len(c)]

    def image(self, side, name):
        return PM.render_image(name, side.img(name), self.bg, self.ac)

    @property
    def base(self):
        return self.ink((0, 0, 0))

    @property
    def row_down(self):
        return self.ink((0x33, 0x33, 0x34))

    def css(self, v):
        """A colour string of a style ('#RRGGBB' or '#RRGGBBAA') as the hooks give it."""
        if not isinstance(v, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?', v): return v
        c = tuple(int(v[i:i + 2], 16) for i in range(1, len(v), 2))
        c = self.ink(c)
        return '#' + ''.join('%02X' % x for x in c)


def settings_screen(s, pal):
    im = Image.new('RGBA', (W, H), pal.base + (255,))   # the page is 450 px high: the window under the status bar
    im.alpha_composite(PS.draw_page(s, 'm1plus_settings', pal=pal, pressed='Library'))
    return im


def menu_screen(s, pal, pressed='Albums'):
    """The M1+ Music menu (ui/m1plus_menu.bin): 52 px rows, the glyph, the title, the chevron and an inset hairline; the glyphs are the accent at rest (render_image: the decode-time tint), the pressed
    row is the whole row in the pressed colour."""
    import awtk_ui
    root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', 'm1plus_menu.bin'), 'rb').read())
    im = Image.new('RGBA', (W, H), pal.base + (255,)); d = ImageDraw.Draw(im)
    rows = [w for w in root.walk() if w.type == 'list_item' and w.name.startswith('pod_row')][:8]
    for i, r in enumerate(rows):
        y = NAV + i * 52
        lab = next(c for c in r.children if c.type == 'hscroll_label')
        down = s.shown(lab) == pressed
        if down: d.rectangle((0, y, W - 1, y + 51), fill=pal.row_down)
        for c in r.children:
            if c.type == 'image':
                g = pal.image(s, c.get('image'))
                im.alpha_composite(g, (c.x + (c.w - g.width) // 2 if g.width < c.w else c.x, y + c.y + (c.h - g.height) // 2 if g.height < c.h else y + c.y))   # draw type icon: centred in its box
            elif c.name == 'pod_hair':
                d.rectangle((c.x, y + 51, W - 1, y + 51), fill=pal.ink((0x22, 0x22, 0x22)))
        s.text(im, lab.x, y + 26, s.clip(s.shown(lab), 21, lab.w), 21, pal.ink((255, 255, 255)))
    d.rectangle((0, 0, W - 1, NAV - 1), fill=pal.base)
    s.text(im, 58, 25, 'M1+ Music', PI.title_px(s.tree))
    return im


SONGS = [('All Blues', 'Miles Davis'), ('Blue in Green', 'Miles Davis'), ('Freddie Freeloader', 'Miles Davis'), ('So What', 'Miles Davis'),
         ('Flamenco Sketches', 'Miles Davis'), ('Take Five', 'The Dave Brubeck Quartet'), ('Naima', 'John Coltrane'), ('My Favorite Things', 'John Coltrane')]


def songs_screen(s, pal):
    """A song list as docs/modules/rows.md draws it: 64 px rows, the title 21 px white from x 12, the artist 18 px grey, a hairline from x 12 (#222222); the playing row's title ends at 250 and the
    np_row_playing wave (x 278..298) is a tinted image; the pressed row is the whole row in the pressed colour (the payload's LIST_PRESS through the hook)."""
    im = Image.new('RGBA', (W, H), pal.base + (255,)); d = ImageDraw.Draw(im)
    wave = pal.image(s, 'np_row_playing')
    for i, (title, artist) in enumerate(SONGS):
        y = NAV + i * 64
        if i == 3: d.rectangle((0, y, W - 1, y + 62), fill=pal.row_down)   # the 60 px body and its separator row
        s.text(im, 12, y + 7 + 12, s.clip(title, 21, 238 if i == 1 else 286), 21, pal.ink((255, 255, 255)))
        s.text(im, 12, y + 33 + 10, s.clip(artist, 18, 286), 18, pal.ink((0xAA, 0xAA, 0xAA)))
        if i == 1: im.alpha_composite(wave, (258, y + 22))
        d.rectangle((12, y + 63, W - 1, y + 63), fill=pal.ink((0x22, 0x22, 0x22)))
    d.rectangle((0, 0, W - 1, NAV - 1), fill=pal.base)
    s.text(im, 58, 25, 'Songs', PI.title_px(s.tree))
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = pal.image(s, name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return im


def controls_screen(s, pal):
    """Keyboards' card (a switch on, one off), the Cassette Theme picker's rows (the check) and a slider row (the pull-down's drop_bg / drop_fg / pod_sl_thumb art)."""
    kb = PS.draw_page(s, 'm1plus_keyboards', pal=pal)
    ao = PS.draw_page(s, 'm1plus_tapetheme', pal=pal, state={'shown': {'pod_check0'}})
    im = Image.new('RGBA', (W, H), pal.base + (255,))
    im.alpha_composite(kb.crop((0, 0, W, 176)), (0, 0))
    im.alpha_composite(ao.crop((0, 56, W, 168)), (0, 184))   # the picker's card (Normal checked, Chrome)
    y = 300; piece = pal.image(s, 'pod_cd_single')
    s.text(im, PS.ST.HDR_X, y + 20, 'Brightness', PS.ST.HDR_PX, pal.ink(rgb(PS.ST.GREY)))
    y += 40
    im.alpha_composite(piece, (0, y))
    ty = y + 26 - 3
    im.alpha_composite(pal.image(s, 'drop_lighticon0'), (20, y + 16)); im.alpha_composite(pal.image(s, 'drop_lighticon1'), (270, y + 16))
    bg = pal.image(s, 'drop_bg').crop((0, 0, 200, 6)); fg = pal.image(s, 'drop_fg').crop((0, 0, 120, 6))
    im.alpha_composite(bg, (60, ty)); im.alpha_composite(fg, (60, ty)); im.alpha_composite(pal.image(s, 'pod_sl_thumb'), (60 + 120 - 19, y + 26 - 17))
    return im


def nowplaying_screen(raw, pal, tint=None):
    class P(NP.Painter):
        def prop(self, wd, prop, state='normal'):
            return pal.css(super().prop(wd, prop, state))   # every colour of the page's styles as the style hook gives it (the progress fill is the accent)

        def image(self, name):
            im = super().image(name)
            return PM.render_image(name, im, pal.bg, pal.ac) if im is not None else None
    p = P(raw); p.playing = True; p.tint = tint
    root = NP.awtk_ui.parse(open(os.path.join(raw, 'ui', 'playing_page.bin'), 'rb').read())
    return p.render(root, 0)


def label_of(ac):
    a = PM.ACCENT_RGB.get(ac)
    return ac.capitalize() + (f'  #{a[0]:02X}{a[1]:02X}{a[2]:02X}' if a else '  (today)')


def sheet(s, raw, bg, path):
    pad, lab, top = 14, 22, 44
    cols = ['Settings: Library pressed', 'M1+ Music menu: Albums pressed', 'Song list: row pressed, playing wave', 'Switches, check, slider', 'Now Playing: progress bar']
    rows = []
    for ac in ACC:
        pal = Palette(bg, ac)
        rows.append((ac, [settings_screen(s, pal), menu_screen(s, pal), songs_screen(s, pal), controls_screen(s, pal), nowplaying_screen(raw, pal)]))
    out = Image.new('RGB', (len(cols) * (W + pad) + pad, top + len(rows) * (H + pad + lab)), (0x2A,) * 3); d = ImageDraw.Draw(out)
    d.text((pad, 10), f'Background: {bg} (through palette.map_colour / render_image)', fill=(0xEE,) * 3, font=PI.ANN_B)
    for j, c in enumerate(cols): d.text((pad + j * (W + pad), 28), c, fill=(0xAA,) * 3, font=PI.ANN)
    for i, (ac, shots) in enumerate(rows):
        y = top + i * (H + pad + lab)
        d.text((pad, y), label_of(ac), fill=(0xEE,) * 3, font=PI.ANN_B)
        for j, im in enumerate(shots): out.paste(im.convert('RGB').crop((0, 0, W, H)), (pad + j * (W + pad), y + lab))
    out.save(path, optimize=True)  # true colour: a 256 colour sheet merged the accents (Red went pink)
    print('wrote', path, out.size)


COVER_TINT = (0x1E, 0x3A, 0x5C)   # the sample cover's tone on Now Playing: the page keeps it on every background


class PalSide:
    """A preview Side whose images come through the palette (the pull-down preview draws with s.img)."""
    def __init__(self, s, pal): self._s, self._p = s, pal
    def __getattr__(self, k): return getattr(self._s, k)
    def img(self, name): return self._p.image(self._s, name)


def pulldown_screen(s, work, pal):
    import preview
    im = preview.controls(PalSide(s, pal), work, bg=pal.ink((0, 0, 0)) + (255,), ink=pal.ink)
    return im.crop((0, 0, W, H)) if im.height >= H else im


def tinted_sheet(s, raw, work, path):
    """accent-tinted.png: Background Tinted x each accent (Neutral = Black). Screens: the M1+ Music menu (glyphs in the accent), Settings, Appearance (Background and Accent rows, the Background picker's value),
    a song list, the pull-down, Now Playing (a cover tone: the page's background is the cover, the same as on Black)."""
    pad, lab, top = 14, 22, 44
    cols = ['M1+ Music menu (Albums pressed)', 'Settings (Library pressed)', 'Appearance (Background pressed)', 'Song list', 'Pull-down', 'Now Playing (cover background)']
    rows = []
    for ac in ACC:
        pal = Palette('tinted', ac)
        ap = PS.draw_page(s, 'm1plus_appearance', pal=pal, state={'values': {'pod_value0': 'Tinted', 'pod_value1': ac.capitalize()}}, pressed='Background')
        apim = Image.new('RGBA', (W, H), pal.base + (255,)); apim.alpha_composite(ap)
        rows.append((ac, [menu_screen(s, pal), settings_screen(s, pal), apim, songs_screen(s, pal), pulldown_screen(s, work, pal), nowplaying_screen(raw, pal, tint=COVER_TINT)]))
    out = Image.new('RGB', (len(cols) * (W + pad) + pad, top + len(rows) * (H + pad + lab)), (0x2A,) * 3); d = ImageDraw.Draw(out)
    d.text((pad, 10), 'Background: Tinted (dark neutrals take 12 % of the accent; Neutral + Tinted is Black), drawn through palette.map_colour / render_image', fill=(0xEE,) * 3, font=PI.ANN_B)
    for j, c in enumerate(cols): d.text((pad + j * (W + pad), 28), c, fill=(0xAA,) * 3, font=PI.ANN)
    for i, (ac, shots) in enumerate(rows):
        y = top + i * (H + pad + lab)
        pal = Palette('tinted', ac); b, c = pal.ink((0, 0, 0)), pal.ink((0x1C, 0x1C, 0x1E))
        d.text((pad, y), label_of(ac) + f'   page #{b[0]:02X}{b[1]:02X}{b[2]:02X}  card #{c[0]:02X}{c[1]:02X}{c[2]:02X}', fill=(0xEE,) * 3, font=PI.ANN_B)
        for j, im in enumerate(shots): out.paste(im.convert('RGB').crop((0, 0, W, H)), (pad + j * (W + pad), y + lab))
    out.save(path, optimize=True)
    print('wrote', path, out.size)


def tinted_contrast():
    hx = lambda c: f'#{c[0]:02X}{c[1]:02X}{c[2]:02X}'
    sec, white = (0x8C,) * 3, (255,) * 3
    lines = ['Tinted background (12 %): page / card, secondary text #8C8C8C on page / card, card against page, white on the pressed row, the accent glyph on the page',
             f'{"accent":<10} {"page":>8} {"card":>8} {"8C/page":>8} {"8C/card":>8} {"card/pg":>8} {"wht/prs":>8} {"acc/pg":>8}']
    for ac in ACC[1:]:
        a = PM.ACCENT_RGB[ac]; p = Palette('tinted', ac)
        base, card, prs = p.ink((0, 0, 0)), p.ink((0x1C, 0x1C, 0x1E)), p.row_down
        lines.append(f'{ac:<10} {hx(base):>8} {hx(card):>8} {contrast(sec, base):>8.2f} {contrast(sec, card):>8.2f} {contrast(card, base):>8.2f} {contrast(white, prs):>8.2f} {contrast(a, base):>8.2f}   press {hx(prs)}')
    return '\n'.join(lines)


def picker_sheet(s, bg, path):
    """The Accent picker with each accent chosen (the check, the swatches), and the Appearance page with its Accent row; one pressed row (Teal) shows the pressed card piece in the accent."""
    pad, top = 14, 44
    cols = [('Settings > Appearance', PS.draw_page(s, 'm1plus_appearance', pal=Palette(bg, 'teal'), state={'values': {'pod_value0': 'Teal'}}, pressed='Accent'))]
    for i, ac in enumerate(ACC):
        pal = Palette(bg, ac)
        cols.append((label_of(ac), PS.draw_page(s, 'm1plus_accent', pal=pal, state={'shown': {f'pod_check{i}'}}, pressed='Teal')))
    out = Image.new('RGB', (len(cols) * (W + pad) + pad, top + 450 + pad), (0x2A,) * 3); d = ImageDraw.Draw(out)
    d.text((pad, 10), 'Settings > Appearance > Accent: the Appearance page (Accent pressed, Teal), then the picker with each accent chosen (Teal pressed)', fill=(0xEE,) * 3, font=PI.ANN_B)
    for j, (t, im) in enumerate(cols):
        d.text((pad + j * (W + pad), 28), t, fill=(0xAA,) * 3, font=PI.ANN)
        out.paste(im.convert('RGB'), (pad + j * (W + pad), top))
    out.save(path, optimize=True)
    print('wrote', path, out.size)


TINTS = ('other_progress', 'datetime_back', 'vol_progress', 'cdprogress_bar', 'drop_fg', 'volume_fg', 'pod_check', 'np_row_playing', 'sset_on', 'pod_cd_mid_down', 'drop_wifiopen', 'drop_usbdac', 'drop_lo')


def tints_sheet(s, bg, path):
    """Every image the accent tints (tools/palette.py ACCENT_ALL's chief ones) per accent on the dark page, native size, and the left end of other_progress at 4x: its edge pixels mix the track
    and the fill, so they move by the share of the fill (palette.accent_pixel)."""
    pad, lab = 12, 22
    tiles = []
    for ac in ACC:
        pal = Palette(bg, ac)
        row = []
        for n in TINTS:
            g = pal.image(s, n)
            bgim = Image.new('RGBA', g.size, (0, 0, 0, 255)); bgim.alpha_composite(g); row.append(bgim)
        z = pal.image(s, 'other_progress').crop((0, 0, 48, 36)).resize((192, 144), Image.NEAREST)
        zb = Image.new('RGBA', z.size, (0, 0, 0, 255)); zb.alpha_composite(z); row.append(zb)
        tiles.append(row)
    widths = [max(t[j].width for t in tiles) for j in range(len(TINTS) + 1)]
    hmax = max(im.height for t in tiles for im in t)
    out = Image.new('RGB', (sum(widths) + pad * (len(widths) + 1), 44 + len(tiles) * (hmax + pad + lab)), (0x2A,) * 3); d = ImageDraw.Draw(out)
    d.text((pad, 10), 'Images the accent tints, per accent (palette.render_image)', fill=(0xEE,) * 3, font=PI.ANN_B)
    x = pad
    for j, n in enumerate(TINTS + ('other_progress 4x',)):
        d.text((x, 28), n, fill=(0xAA,) * 3, font=PI.ANN); x += widths[j] + pad
    for i, row in enumerate(tiles):
        y = 44 + i * (hmax + pad + lab)
        d.text((pad, y), label_of(ACC[i]), fill=(0xEE,) * 3, font=PI.ANN_B)
        x = pad
        for j, im in enumerate(row):
            out.paste(im.convert('RGB'), (x, y + lab)); x += widths[j] + pad
    out.save(path, optimize=True)
    print('wrote', path, out.size)


def contrast_table():
    lines = ['accent contrast, from the model (glyph = the pressed glyph, the accent, on the pressed card tint; base = accent on the black page; row = accent on the pressed row tint; tile = the #141414 glyph of a pull-down ON tile on the accent disc)',
             f'{"background":<9} {"accent":<10} {"glyph/card":>10} {"accent/base":>11} {"accent/row":>10} {"tile glyph":>10}']
    for bg in PM.BACKGROUNDS[:1]:
        for ac in ACC[1:]:
            a = PM.ACCENT_RGB[ac]; p = Palette(bg, ac)
            card = PM.card_press(ac)
            lines.append(f'{bg:<9} {ac:<10} {contrast(a, card):>10.2f} {contrast(a, p.base):>11.2f} {contrast(a, p.row_down):>10.2f} {contrast((PM.KNOB_R,) * 3, a):>10.2f}')
    return '\n'.join(lines)


def uic2_sheet(path, panels):
    """panels: [(title, image)] side by side on a dark ground."""
    pad, lab = 12, 20
    wid = sum(im.width for _, im in panels) + pad * (len(panels) + 1)
    out = Image.new('RGB', (wid, max(im.height for _, im in panels) + lab + 2 * pad), (0x2A,) * 3); d = ImageDraw.Draw(out)
    x = pad
    for title, im in panels:
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); out.paste(im.convert('RGB'), (x, pad + lab)); x += im.width + pad
    out.save(path, optimize=True); print('wrote', path, out.size)


def cache_pill(s, ac):
    """Home's cache pill (patch/homecover.c, tools/pod_ui.py cache_pill): the capsule, the 15 px text, the track and the fill at 40 % (ROLE_FILL through the hook), the stop x."""
    O = PI.offsets()
    im = Image.new('RGBA', (320, 70), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    pal = Palette('black', ac)
    d.rounded_rectangle((12, 10, 12 + 296 - 1, 10 + O['HC_PH'] - 1), radius=O['HC_PH'] // 2, fill=(0x1C, 0x1C, 0x1E))
    s.text(im, 12 + O['HC_TX'], 10 + O['HC_TY'] + 10, 'Preparing covers 336/840', 15, (0xAA,) * 3)
    bx, by = 12 + O['HC_TX'], 10 + O['HC_BY']
    ov = Image.new('RGBA', im.size, (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    od.rounded_rectangle((bx, by, bx + O['HC_BW'] - 1, by + O['HC_BH'] - 1), radius=O['HC_BH'] // 2, fill=(255, 255, 255, 0x33))
    od.rounded_rectangle((bx, by, bx + O['HC_BW'] * 4 // 10 - 1, by + O['HC_BH'] - 1), radius=O['HC_BH'] // 2, fill=pal.ink((0xEB, 0xEB, 0xEC)) + (255,))
    im.alpha_composite(ov)
    od = ImageDraw.Draw(im); od.ellipse((12 + O['HC_XX'] + 6, 10 + 6, 12 + O['HC_XX'] + 33, 10 + 33), fill=(0x3A, 0x3A, 0x3C))
    s.text(im, 12 + O['HC_XX'] + 20, 10 + 20, 'x', 18, (255, 255, 255), 'm')
    return im


def ring_panel(s, ac):
    """The Podcasts progress ring (a state pill at 42 %, the ring cell 5 of pc_atlas) and the source rows' download ring steps, at 1:1 and 4x, with the arcs as the payload tints them."""
    import mod_icons
    atlas = Image.open(os.path.join(mod_icons.PNG, 'pc_atlas.png')).convert('RGBA')
    def cell(x0, y0, n, k, cols, tint):
        c = atlas.crop((x0 + k % cols * n, y0 + k // cols * n, x0 + k % cols * n + n, y0 + k // cols * n + n))
        c.putdata([tint(p, ac) for p in c.getdata()])
        return c
    im = Image.new('RGBA', (320, 200), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((16, 12, 16 + 100, 12 + 29), radius=15, outline=(255, 255, 255, 110), width=2)
    im.alpha_composite(cell(0, 0, PM_RING_PX, 5, 6, PM.ring_pixel), (26, 19))
    s.text(im, 48, 27, '42%', 15, (255, 255, 255))
    for k in range(0, 12, 2):   # the ring's steps zoomed 4x
        im.alpha_composite(cell(0, 0, PM_RING_PX, k, 6, PM.ring_pixel).resize((PM_RING_PX * 2, PM_RING_PX * 2), Image.NEAREST), (16 + k // 2 * 40, 60))
    for k in range(12):   # the download ring's steps
        c = cell(76, 112, 14, k, 6, PM.dl_ring_pixel)
        im.alpha_composite(c.resize((28, 28), Image.NEAREST), (16 + k % 6 * 40, 120 + k // 6 * 36))
    return im


PM_RING_PX = 16


def uic2(s, work, out):
    """The elements of the second consistency pass: Neutral | Teal | Orange panels each."""
    import preview_tenband as PT, preview_peqband as PB, preview_peqpage as PP, preview_songs as PSG
    os.makedirs(out, exist_ok=True)
    accents = ('neutral', 'teal', 'orange')
    def panels(path, titled, fn):
        shots = []
        for ac in accents:
            rgb_ = PM.ACCENT_RGB.get(ac)
            PT.ACC = PB.ACC = PSG.ACC = rgb_
            shots.append((f'{titled}: {label_of(ac)}', fn(PalSide(s, Palette('black', ac)), ac)))
        PT.ACC = PB.ACC = PSG.ACC = None
        uic2_sheet(os.path.join(out, path), shots)
    custom = PT.ROCK[:6] + [5] + PT.ROCK[7:]
    panels('accent-tenband.png', '10-Band editor, dragging 2k', lambda sd, ac: PT.screen(sd, '10-Band EQ', PT.editor(sd, custom, 'Custom', 'Auto · −5.6 dB', drag=6)))
    edited = [tuple(b) for b in PP.HD600]; edited[3] = (1, 0, 2600, -4.1, 3.2)
    panels('accent-band.png', 'Band page', lambda sd, ac: PB.band_page(sd, edited, 3).crop((0, 0, W, PS.SCREEN)))
    _, heads, _ = PSG.build_items()
    panels('accent-songs-select.png', 'Songs, select mode', lambda sd, ac: PSG.page(sd, scroll=heads['C'] - 8, select={'Creep', '春よ、来い'}))
    panels('accent-songs-rail.png', 'Songs, finger on the rail', lambda sd, ac: PSG.page(sd, scroll=heads['M'], touched='M', letters=PSG.ALL_LETTERS))
    def sheet_panel(sd, ac):
        PSG.PRESSED_ROW = 2
        try: return PSG.page(sd, scroll=heads['A'] - 8, row_menu_at=True)
        finally: PSG.PRESSED_ROW = None
    panels('accent-sheet.png', 'Track menu, a row pressed', sheet_panel)
    panels('accent-cachepill.png', 'Home cache pill', lambda sd, ac: cache_pill(s, ac))
    panels('accent-podring.png', 'Rings', lambda sd, ac: ring_panel(s, ac))


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    work = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(build.ROOT, 'out', 'preview')
    s = PI.Side(work, True, 'en_US'); s.mark = lambda *a: None
    raw = os.path.join(work, PI.RAW)
    os.makedirs(out, exist_ok=True)
    sheet(s, raw, 'black', os.path.join(out, 'accent-black.png'))
    picker_sheet(s, 'black', os.path.join(out, 'accent-picker.png'))
    tinted_sheet(s, raw, work, os.path.join(out, 'accent-tinted.png'))
    tints_sheet(s, 'black', os.path.join(out, 'accent-tints.png'))
    uic2(s, work, os.path.join(out, 'uic2'))
    print(contrast_table())
    print(tinted_contrast())


if __name__ == '__main__':
    main()
