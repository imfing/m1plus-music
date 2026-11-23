#!/usr/bin/env python3
"""Control Center page 2 mock (out/preview/cc2.png, gitignored): page 1 as the tree draws it (preview.controls) beside three
page-2 options laid on the same grid (tile rows y 51 / 151, captions 5 px under the disc, the bottom card y 265 .. 317,
grabber y 328). Approximate, not AWTK; sample data.

  A  Now Playing: media card (cover, title, artist, prev / play / next), four playback toggles, volume card
  B  More tiles: a second grid of eight, volume card
  C  Status: battery and storage cards, Wi-Fi and Bluetooth rows, volume card

Usage: uv run python -I tools/preview/preview_cc2.py WORKDIR [OUT.png]
"""
import os, sys
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import preview, preview_icons as PI, preview_settings as PS, mod_icons as MI, awtk_ui, mod_pulldown as MP
from awtk_text import Ttf
from awtk_ui import RAW

H = 340                       # the dialog
CARD, CAP, DIM = (0x1C, 0x1C, 0x1E), (0xB0, 0xB0, 0xB0), (0x8A, 0x8A, 0x8E)
COLS, ROWS = (21, 95, 169, 243), (51, 151)


def glyph(name, px=24, rgb=(255, 255, 255)):
    return MI.ink_crop(MI.glyph(name, px, 'tile', rgb))


def tile(im, s, ttf, x, y, g, label, on=False):
    t = MI.disc_tile(g, 'on' if on else 'off') if not isinstance(g, Image.Image) else g
    im.alpha_composite(t, (x, y))
    for i, line in enumerate(MP.wrap(ttf, label, 16, 71)):
        s.text(im, x + 28, y + 56 + 5 + MP.CAP_MT + i * (16 + MP.CAP_SPACER) + 8, line, 16, CAP, anchor='m')


def card(im, box, r=26):
    ImageDraw.Draw(im).rounded_rectangle(box, r, fill=CARD)


def volume_card(im, s, root, pct=45):
    """The brightness card's build with speakers in place of the suns."""
    bl = root.find('view_backlight')
    card(im, (bl.x, bl.y, bl.x + bl.w - 1, bl.y + bl.h - 1), int(bl.get('style:normal:round_radius')))
    PS.draw_brightness(im, bl, bl.y, s.img, pct, card=False)
    d = ImageDraw.Draw(im)
    for cx, g in ((bl.x + 24, 'volume'), (bl.x + bl.w - 24, 'volume-2')):
        d.rectangle((cx - 14, bl.y + 8, cx + 14, bl.y + bl.h - 9), fill=CARD)
        gi = glyph(g, 20); im.alpha_composite(gi, (cx - gi.width // 2, bl.y + (bl.h - gi.height) // 2))


def dots(im, page):
    """Page dots, side by side over the grabber (pages swipe left and right; up and down closes)."""
    d = ImageDraw.Draw(im)
    for i in range(2):
        x = 160 - 9 + i * 12
        d.ellipse((x, 319, x + 5, 324), fill=(255, 255, 255) if i == page else (0x55, 0x55, 0x55))


def base(s, root):
    im = Image.new('RGBA', (320, H), (0, 0, 0, 255))
    PI.asset_bar(s, root.find('view_sysbar'), im)
    g = root.find('pod_grabber'); im.alpha_composite(s.img(g.get('image')), (g.x, g.y))
    return im


def cover(size, top=(70, 110, 190), bot=(20, 30, 70)):
    c = Image.new('RGBA', (size, size))
    for y in range(size):
        k = y / (size - 1); c.paste(tuple(int(a + (b - a) * k) for a, b in zip(top, bot)) + (255,), (0, y, size, y + 1))
    m = Image.new('L', (size * 4, size * 4), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, size * 4 - 1, size * 4 - 1), 32, fill=255)
    c.putalpha(m.resize((size, size), Image.LANCZOS)); return c


def page_a(s, root, ttf):
    im = base(s, root)
    card(im, (10, 44, 309, 139), 22)
    im.alpha_composite(cover(72), (22, 56))
    s.text(im, 108, 68, s.clip('Blue in Green', 18, 190), 18)
    s.text(im, 108, 89, s.clip('Miles Davis — Kind of Blue', 15, 190), 15, DIM)
    for cx, n in ((134, 'np_prev'), (196, 'np_pause'), (258, 'np_next')):
        g = s.img(n).resize((36, 36), Image.LANCZOS); im.alpha_composite(g, (cx - 18, 103))
    for x, (g, lab, on) in zip(COLS, (('shuffle', 'Shuffle', True), ('repeat', 'Repeat', False),
                                      ('audio-lines', 'Crossfade', False), ('headphones', 'Mono', False))):
        tile(im, s, ttf, x, ROWS[1], g, lab, on)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_b(s, root, ttf):
    im = base(s, root)
    own = (('drop_sleepopen', 'Sleep Timer'), ('drop_settings', 'Settings'), ('drop_equalizer', 'Equalizer'), ('drop_power', 'Power Off'),
           ('drop_airplay', 'AirPlay'), ('drop_dlna', 'DLNA'), ('drop_transfer', 'Wi-Fi Transfer'), ('drop_shot', 'Screenshot'))
    for i, (img, lab) in enumerate(own):
        tile(im, s, ttf, COLS[i % 4], ROWS[i // 4], s.img(img), lab)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_c(s, root, ttf):
    im = base(s, root); d = ImageDraw.Draw(im)
    card(im, (10, 44, 155, 139), 22); card(im, (165, 44, 309, 139), 22)
    gi = glyph('battery-charging', 22); im.alpha_composite(gi, (24, 58))
    s.text(im, 24, 100, '82%', 30)
    s.text(im, 24, 125, 'Limit 86% · 1h 10m', 13, DIM)
    gi = glyph('hard-drive', 22); im.alpha_composite(gi, (179, 58))
    s.text(im, 179, 100, '41 GB', 30)
    d.rounded_rectangle((179, 120, 295, 125), 3, fill=(0x3A, 0x3A, 0x3C)); d.rounded_rectangle((179, 120, 263, 125), 3, fill=(0xEE, 0xEE, 0xEC))
    s.text(im, 179, 133, 'free of 256 GB', 11, DIM)
    for y, g, name, sub in ((151, 'wifi', 'HomeNet-5G', 'Connected'), (205, 'bluetooth', 'AirPods Pro', 'AAC · 80%')):
        card(im, (10, y, 309, y + 46), 23)
        disc = MI.disc(34, (255, 255, 255)); gi = glyph(g, 18, (0x14, 0x14, 0x14)); disc.alpha_composite(gi, ((34 - gi.width) // 2, (34 - gi.height) // 2))
        im.alpha_composite(disc, (18, y + 6))
        s.text(im, 62, y + 15, name, 17); s.text(im, 62, y + 34, sub, 13, DIM)
        ch = MI.pod_chevron((0x8A, 0x8A, 0x8A)); im.alpha_composite(ch, (290 - ch.width, y + (47 - ch.height) // 2))
    volume_card(im, s, root); dots(im, 1)
    return im


def minibar(im, s, playing=True):
    """The Home mini bar (preview_minibar.draw, the payload's numbers) in the brightness card's slot, 2 px wider and taller each way."""
    import preview_minibar as MB, pod_ui as U
    art = cover(U.MB_ART).copy(); art.putalpha(255)
    txt = lambda im_, x, cy, t, px, rgb: s.text(im_, x, cy, t, px, rgb or (255, 255, 255))
    MB.draw(im, 8, 263, s.img, txt, lambda t, px, w: s.clip(t, px, w), 'Blue in Green', 'Miles Davis', art, playing=playing, blur=False)


def page1_bar(s, root, ttf, playing=True):
    im = preview.controls(s, s.tree).crop((0, 0, 320, H))
    ImageDraw.Draw(im).rectangle((0, 260, 319, 322), fill=(0, 0, 0))
    minibar(im, s, playing); dots(im, 0)
    return im


def brightness_card(im, s, root, y):
    bl = root.find('view_backlight')
    card(im, (bl.x, y, bl.x + bl.w - 1, y + bl.h - 1), int(bl.get('style:normal:round_radius')))
    PS.draw_brightness(im, bl, y, s.img, 60, card=False)


def page2_tiles(s, root, ttf):
    im = base(s, root)
    for i, (g, lab, on) in enumerate((('shuffle', 'Shuffle', True), ('repeat', 'Repeat', False), ('audio-lines', 'Crossfade', False), ('headphones', 'Mono', False))):
        tile(im, s, ttf, COLS[i], ROWS[0], g, lab, on)
    for i, (img, lab) in enumerate((('drop_sleepopen', 'Sleep Timer'), ('drop_equalizer', 'Equalizer'), ('drop_airplay', 'AirPlay'), ('drop_shot', 'Screenshot'))):
        tile(im, s, ttf, COLS[i], ROWS[1], s.img(img), lab)
    brightness_card(im, s, root, 265); dots(im, 1)
    return im


def page2_sliders(s, root, ttf):
    im = base(s, root)
    for i, (g, lab, on) in enumerate((('shuffle', 'Shuffle', True), ('repeat', 'Repeat', False), ('audio-lines', 'Crossfade', False), ('headphones', 'Mono', False))):
        tile(im, s, ttf, COLS[i], ROWS[0], g, lab, on)
    brightness_card(im, s, root, 181)
    volume_card(im, s, root); dots(im, 1)
    return im


def img_tile(s, name, on=False, px=24):
    """A tile from a stock-style image glyph (white ink) on the flat disc."""
    g = MI.ink_crop(s.img(name)); k = px / max(g.size); g = g.resize((max(1, round(g.width * k)), max(1, round(g.height * k))), Image.LANCZOS)
    if on: g = MI.tint(g, (0x14, 0x14, 0x14))
    t = MI.disc(56, (255, 255, 255) if on else (0x2C, 0x2C, 0x2E)); t.alpha_composite(g, ((56 - g.width) // 2, (56 - g.height) // 2)); return t


def page_music(s, root, ttf):
    """iOS page 2 manner: the Now Playing module on top, four playback tiles, volume where page 1 has brightness."""
    im = base(s, root); d = ImageDraw.Draw(im)
    card(im, (10, 44, 309, 139), 22)
    im.alpha_composite(cover(72), (22, 56))
    s.text(im, 108, 64, s.clip('Blue in Green', 18, 186), 18)
    s.text(im, 108, 84, s.clip('Miles Davis', 15, 186), 15, DIM)
    d.rounded_rectangle((108, 98, 294, 100), 1, fill=(0x3A, 0x3A, 0x3C)); d.rounded_rectangle((108, 98, 170, 100), 1, fill=(0xEE, 0xEE, 0xEC))
    for cx, n in ((140, 'np_prev'), (201, 'np_pause'), (262, 'np_next')):
        g = s.img(n).resize((34, 34), Image.LANCZOS); im.alpha_composite(g, (cx - 17, 106))
    tiles = ((MI.disc_tile('shuffle', 'on'), 'Shuffle'), (MI.disc_tile('repeat', 'off'), 'Repeat'),
             (img_tile(s, 'np_fav', True), 'Favorite'), (s.img('drop_sleepopen'), 'Sleep Timer'))
    for x, (t, lab) in zip(COLS, tiles): tile(im, s, ttf, x, ROWS[1], t, lab)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_sound(s, root, ttf):
    """A sound page: eight audio tiles over volume."""
    im = base(s, root)
    tiles = ((s.img('drop_eqopen'), 'Equalizer'), (s.img('drop_highgain'), 'High Gain'), (s.img('drop_po'), 'Output'), (MI.disc_tile('gauge', 'off'), 'ReplayGain'),
             (MI.disc_tile('audio-lines', 'on'), 'Crossfade'), (MI.disc_tile('headphones', 'off'), 'Mono'), (MI.disc_tile('waves', 'off'), 'Crossfeed'), (MI.disc_tile('disc-3', 'off'), 'Vinyl Mode'))
    for i, (t, lab) in enumerate(tiles): tile(im, s, ttf, COLS[i % 4], ROWS[i // 4], t, lab)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_player(s, root, ttf):
    """iOS page 2: one large Now Playing module (Shuffle, Repeat and Favorite inside it) over volume; no tiles."""
    im = base(s, root); d = ImageDraw.Draw(im)
    card(im, (10, 44, 309, 252), 26)
    im.alpha_composite(cover(96), (24, 58))
    s.text(im, 134, 72, s.clip('Blue in Green', 18, 140), 18)
    s.text(im, 134, 94, s.clip('Miles Davis', 15, 140), 15, DIM)
    s.text(im, 134, 114, s.clip('Kind of Blue', 15, 140), 15, DIM)
    fav = MI.ink_crop(s.img('np_fav')); fav = fav.resize((22, round(22 * fav.height / fav.width)), Image.LANCZOS); im.alpha_composite(fav, (284 - 11, 61))
    d.rounded_rectangle((24, 172, 295, 175), 2, fill=(0x3A, 0x3A, 0x3C)); d.rounded_rectangle((24, 172, 120, 175), 2, fill=(0xEE, 0xEE, 0xEC))
    s.text(im, 24, 188, '1:52', 12, DIM); s.text(im, 295, 188, '-3:45', 12, DIM, anchor='r')
    for cx, n in ((104, 'np_prev'), (160, 'np_pause'), (216, 'np_next')):
        g = s.img(n); im.alpha_composite(g, (cx - 22, 224 - 22))
    on = MI.disc(32, (0x3A, 0x3A, 0x3C)); gi = glyph('shuffle', 18); on.alpha_composite(gi, ((32 - gi.width) // 2, (32 - gi.height) // 2)); im.alpha_composite(on, (40 - 16, 224 - 16))
    gi = glyph('repeat', 18, DIM); im.alpha_composite(gi, (280 - gi.width // 2, 224 - gi.height // 2))
    volume_card(im, s, root); dots(im, 1)
    return im


def transport(im, s, y, xs=(104, 160, 216), size=44, side=(40, 280), shuffle_on=True):
    for cx, n in zip(xs, ('np_prev', 'np_pause', 'np_next')):
        g = s.img(n)
        if size != 44: g = g.resize((size, size), Image.LANCZOS)
        im.alpha_composite(g, (cx - size // 2, y - size // 2))
    if side:
        sh = glyph('shuffle', 18)
        if shuffle_on:
            dd = MI.disc(32, (0x3A, 0x3A, 0x3C)); dd.alpha_composite(sh, ((32 - sh.width) // 2, (32 - sh.height) // 2)); im.alpha_composite(dd, (side[0] - 16, y - 16))
        else: im.alpha_composite(sh, (side[0] - sh.width // 2, y - sh.height // 2))
        gi = glyph('repeat', 18, DIM); im.alpha_composite(gi, (side[1] - gi.width // 2, y - gi.height // 2))


def fav_mark(im, s, cx, y, w=22):
    f = MI.ink_crop(s.img('np_fav')); f = f.resize((w, round(w * f.height / f.width)), Image.LANCZOS); im.alpha_composite(f, (cx - w // 2, y))


def progress(im, s, x0, x1, y, k=0.35, times=True):
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x0, y, x1, y + 3), 2, fill=(0x3A, 0x3A, 0x3C)); d.rounded_rectangle((x0, y, x0 + int((x1 - x0) * k), y + 3), 2, fill=(0xEE, 0xEE, 0xEC))
    if times: s.text(im, x0, y + 16, '1:52', 12, DIM); s.text(im, x1, y + 16, '-3:45', 12, DIM, anchor='r')


def tinted_card(im, box, r, top=(46, 66, 112), bot=(22, 28, 44)):
    x0, y0, x1, y1 = box
    g = Image.new('RGBA', (x1 - x0 + 1, y1 - y0 + 1))
    for y in range(g.height):
        k = y / (g.height - 1); g.paste(tuple(int(a + (b - a) * k) for a, b in zip(top, bot)) + (255,), (0, y, g.width, y + 1))
    m = Image.new('L', (g.width * 4, g.height * 4), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, g.width * 4 - 1, g.height * 4 - 1), r * 4, fill=255)
    g.putalpha(m.resize(g.size, Image.LANCZOS)); im.alpha_composite(g, (x0, y0))


def page_tint(s, root, ttf):
    """H with the card tinted from the cover (Now Playing's album colour), Apple Music's lock-screen manner."""
    im = base(s, root)
    tinted_card(im, (10, 44, 309, 252), 26)
    im.alpha_composite(cover(96), (24, 58))
    s.text(im, 134, 72, s.clip('Blue in Green', 18, 140), 18)
    s.text(im, 134, 94, s.clip('Miles Davis', 15, 140), 15, (0xC8, 0xCC, 0xD8))
    s.text(im, 134, 114, s.clip('Kind of Blue', 15, 140), 15, (0xC8, 0xCC, 0xD8))
    fav_mark(im, s, 284, 61)
    progress(im, s, 24, 295, 172); transport(im, s, 224)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_centre(s, root, ttf):
    """The cover centred over centred text, like Now Playing itself."""
    im = base(s, root)
    card(im, (10, 44, 309, 252), 26)
    im.alpha_composite(cover(84), (160 - 42, 54))
    s.text(im, 160, 152, s.clip('Blue in Green', 17, 250), 17, anchor='m')
    s.text(im, 160, 171, s.clip('Miles Davis — Kind of Blue', 14, 250), 14, DIM, anchor='m')
    progress(im, s, 24, 295, 186, times=False)
    fav_mark(im, s, 284, 58, 20)
    transport(im, s, 222, size=40)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_vslider(s, root, ttf):
    """iOS module grid: the player card and a tall volume slider beside it, the whole page height; no bottom card."""
    im = base(s, root)
    card(im, (10, 44, 239, 317), 26)
    im.alpha_composite(cover(112), (125 - 56, 56))
    s.text(im, 24, 186, s.clip('Blue in Green', 17, 180), 17)
    s.text(im, 24, 206, s.clip('Miles Davis', 14, 180), 14, DIM)
    fav_mark(im, s, 214, 177, 20)
    progress(im, s, 24, 225, 222, times=False)
    transport(im, s, 260, xs=(72, 125, 178), size=40, side=None)
    sh = glyph('shuffle', 18); im.alpha_composite(sh, (40 - sh.width // 2, 296 - sh.height // 2))
    gi = glyph('repeat', 18, DIM); im.alpha_composite(gi, (210 - gi.width // 2, 296 - gi.height // 2))
    tinted_card(im, (249, 44, 309, 317), 26, CARD, CARD)
    fill = Image.new('RGBA', (61, 274), (0, 0, 0, 0)); ImageDraw.Draw(fill).rectangle((0, 274 - 123, 60, 273), fill=(0xEE, 0xEE, 0xEC))
    m = Image.new('L', (61 * 4, 274 * 4), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, 61 * 4 - 1, 274 * 4 - 1), 104, fill=255)
    a = fill.getchannel('A'); a.paste(0, (0, 0, 61, 274 - 123)); fill.putalpha(Image.composite(a, Image.new('L', a.size, 0), m.resize(a.size, Image.LANCZOS)))
    im.alpha_composite(fill, (249, 44))
    gi = glyph('volume-2', 22, (0x14, 0x14, 0x14)); im.alpha_composite(gi, (279 - gi.width // 2, 290 - gi.height // 2))
    dots(im, 1)
    return im


def page_upnext(s, root, ttf):
    """The compact player over the next two queue rows (tap: play it), then volume."""
    im = base(s, root); d = ImageDraw.Draw(im)
    card(im, (10, 44, 309, 139), 22)
    im.alpha_composite(cover(72), (22, 56))
    s.text(im, 108, 64, s.clip('Blue in Green', 18, 160), 18)
    s.text(im, 108, 84, s.clip('Miles Davis', 15, 160), 15, DIM)
    fav_mark(im, s, 286, 56, 18)
    progress(im, s, 108, 294, 98, times=False)
    transport(im, s, 123, xs=(140, 201, 262), size=34, side=None)
    s.text(im, 14, 156, 'Up Next', 14, DIM)
    sh = glyph('shuffle', 16); im.alpha_composite(sh, (262 - sh.width // 2, 156 - sh.height // 2))
    gi = glyph('repeat', 16, DIM); im.alpha_composite(gi, (296 - gi.width // 2, 156 - gi.height // 2))
    for i, (t, a, c) in enumerate((('Alice in Wonderland', 'Bill Evans Trio', ((150, 60, 40), (60, 20, 10))), ('Naima', 'John Coltrane', ((200, 170, 90), (90, 60, 20))))):
        y = 170 + i * 46
        im.alpha_composite(cover(36, *c), (14, y + 4))
        s.text(im, 60, y + 14, s.clip(t, 16, 240), 16); s.text(im, 60, y + 33, s.clip(a, 13, 240), 13, DIM)
        if i == 0: d.rectangle((60, y + 45, 309, y + 45), fill=(0x2C, 0x2C, 0x2E))
    volume_card(im, s, root); dots(im, 1)
    return im


def page_more(s, root, ttf, n=8):
    """Page 2 = the tiles past the eighth, the same grid; the brightness card stays, so a swipe only changes the grid."""
    im = base(s, root)
    own = (('drop_sleepopen', 'Sleep Timer'), ('drop_settings', 'Settings'), ('drop_equalizer', 'Equalizer'), ('drop_power', 'Power Off'),
           ('drop_airplay', 'AirPlay'), ('drop_dlna', 'DLNA'), ('drop_transfer', 'Wi-Fi Transfer'), ('drop_shot', 'Screenshot'))[:n]
    for i, (img, lab) in enumerate(own):
        tile(im, s, ttf, COLS[i % 4], ROWS[i // 4], s.img(img), lab)
    brightness_card(im, s, root, 265); dots(im, 1)
    return im


def music_card(im, s, shuffle_on=True, repeat_on=False):
    """F's card with Shuffle and Repeat moved in beside the transport (small marks, lit white / dim), so the row below is free for actions."""
    d = ImageDraw.Draw(im)
    card(im, (10, 44, 309, 139), 22)
    im.alpha_composite(cover(72), (22, 56))
    s.text(im, 108, 64, s.clip('Blue in Green', 18, 186), 18)
    s.text(im, 108, 84, s.clip('Miles Davis', 15, 186), 15, DIM)
    d.rounded_rectangle((108, 98, 294, 100), 1, fill=(0x3A, 0x3A, 0x3C)); d.rounded_rectangle((108, 98, 170, 100), 1, fill=(0xEE, 0xEE, 0xEC))
    for cx, n in ((162, 'np_prev'), (201, 'np_pause'), (240, 'np_next')):
        g = s.img(n).resize((30, 30), Image.LANCZOS); im.alpha_composite(g, (cx - 15, 108))
    for cx, n, on in ((118, 'shuffle', shuffle_on), (284, 'repeat', repeat_on)):
        g = glyph(n, 18, (255, 255, 255) if on else DIM); im.alpha_composite(g, (cx - g.width // 2, 123 - g.height // 2))


def act_glyph(s, name, px=24):
    """A white action glyph: a Lucide name, or an asset image (img:<name>) cropped and scaled to px."""
    if name.startswith('img:'):
        g = MI.ink_crop(s.img(name[4:])); k = px / max(g.size)
        return MI.tint(g.resize((max(1, round(g.width * k)), max(1, round(g.height * k))), Image.LANCZOS), (255, 255, 255))
    return glyph(name, px)


def page_act_discs(s, root, ttf, acts):
    """M/N: the card, then four action discs (never lit: a tap opens a page and closes the Control Center), volume."""
    im = base(s, root); music_card(im, s)
    for x, (g, lab) in zip(COLS, acts):
        t = MI.disc(56, (0x2C, 0x2C, 0x2E)); gi = act_glyph(s, g); t.alpha_composite(gi, ((56 - gi.width) // 2, (56 - gi.height) // 2))
        tile(im, s, ttf, x, ROWS[1], t, lab)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_act_pills(s, root, ttf, acts):
    """O: the card, then a 2 x 2 of wide buttons (glyph + label), volume. Squarer than the round toggles, so they read as buttons."""
    im = base(s, root); music_card(im, s); d = ImageDraw.Draw(im)
    for i, (g, lab) in enumerate(acts):
        x0 = 10 + (i % 2) * 152; y0 = 149 + (i // 2) * 56
        d.rounded_rectangle((x0, y0, x0 + 147, y0 + 49), 16, fill=CARD)
        gi = act_glyph(s, g, 22); im.alpha_composite(gi, (x0 + 26 - gi.width // 2, y0 + 25 - gi.height // 2))
        s.text(im, x0 + 46, y0 + 25, s.clip(lab, 16, 96), 16)
    volume_card(im, s, root); dots(im, 1)
    return im


def page_act_grid(s, root, ttf, acts):
    """P: the card, then eight small square buttons in two rows (glyph over a 13 px label), volume."""
    im = base(s, root); music_card(im, s); d = ImageDraw.Draw(im)
    for i, (g, lab) in enumerate(acts):
        x0 = 10 + (i % 4) * 76; y0 = 147 + (i // 4) * 58
        d.rounded_rectangle((x0, y0, x0 + 71, y0 + 53), 14, fill=CARD)
        gi = act_glyph(s, g, 20); im.alpha_composite(gi, (x0 + 36 - gi.width // 2, y0 + 19 - gi.height // 2))
        s.text(im, x0 + 36, y0 + 41, s.clip(lab, 13, 68), 13, CAP, anchor='m')
    volume_card(im, s, root); dots(im, 1)
    return im


def music_card_fav(im, s):
    """O's card without Shuffle / Repeat (they move to the square below); the Favorite star in the top-right corner."""
    d = ImageDraw.Draw(im)
    card(im, (10, 44, 309, 139), 22)
    im.alpha_composite(cover(72), (22, 56))
    s.text(im, 108, 64, s.clip('Blue in Green', 18, 160), 18)
    s.text(im, 108, 84, s.clip('Miles Davis', 15, 160), 15, DIM)
    fav_mark(im, s, 290, 55, 18)
    d.rounded_rectangle((108, 98, 294, 100), 1, fill=(0x3A, 0x3A, 0x3C)); d.rounded_rectangle((108, 98, 170, 100), 1, fill=(0xEE, 0xEE, 0xEC))
    for cx, n in ((150, 'np_prev'), (201, 'np_pause'), (252, 'np_next')):
        g = s.img(n).resize((30, 30), Image.LANCZOS); im.alpha_composite(g, (cx - 15, 108))


def wide_card(im, s, box, g, title, sub=None, lit=True):
    """A wide card: a 44 px disc (lit white with a dark glyph, or off) and a title with an optional grey line under it."""
    x0, y0, x1, y1 = box; card(im, box, 22); cy = (y0 + y1) // 2
    t = MI.disc(44, (255, 255, 255) if lit else (0x2C, 0x2C, 0x2E)); gi = act_glyph(s, g, 22)
    if lit: gi = MI.tint(gi, (0x14, 0x14, 0x14))
    t.alpha_composite(gi, ((44 - gi.width) // 2, (44 - gi.height) // 2)); im.alpha_composite(t, (x0 + 12, cy - 22))
    if sub:
        s.text(im, x0 + 66, cy - 10, s.clip(title, 17, x1 - x0 - 74), 17); s.text(im, x0 + 66, cy + 12, s.clip(sub, 14, x1 - x0 - 74), 14, DIM)
    else: s.text(im, x0 + 66, cy, s.clip(title, 17, x1 - x0 - 74), 17)


def page_square(s, root, ttf, quad, right):
    """Q/R: the card, then a square of four discs (left) beside two wide cards (right) down to the grabber; no volume card."""
    im = base(s, root); music_card_fav(im, s)
    card(im, (10, 149, 153, 317), 26)
    for i, (g, on) in enumerate(quad):
        cx, cy = 46 + (i % 2) * 71, 191 + (i // 2) * 84
        t = MI.disc(56, (255, 255, 255) if on else (0x2C, 0x2C, 0x2E)); gi = act_glyph(s, g, 24)
        if on: gi = MI.tint(gi, (0x14, 0x14, 0x14))
        t.alpha_composite(gi, ((56 - gi.width) // 2, (56 - gi.height) // 2)); im.alpha_composite(t, (cx - 28, cy - 28))
    for j, (g, title, sub, lit) in enumerate(right):
        y0 = 149 + j * 89; wide_card(im, s, (162, y0, 309, y0 + 79), g, title, sub, lit)
    dots(im, 1)
    return im


def tall_card(im, s, title, sub, transport_imgs, fav=True, live=False, art=None):
    """The top card (y 44 .. 163) in Apple's Now Playing pill order: a 96 px cover filling the height, title and artist, a round button top right (Favorite),
    the transport, then a thick progress bar with elapsed / remaining under it (radio: a LIVE mark instead)."""
    d = ImageDraw.Draw(im)
    card(im, (10, 44, 309, 163), 26)
    a = art or cover(96)
    if a.width != 96: a = a.resize((96, 96), Image.LANCZOS)
    im.alpha_composite(a, (22, 56))
    s.text(im, 130, 66, s.clip(title, 18, 134 if fav else 166), 18)
    s.text(im, 130, 87, s.clip(sub, 15, 134 if fav else 166), 15, DIM)
    if fav:
        b = MI.disc(32, (0x3A, 0x3A, 0x3C)); g = glyph('star', 16); b.alpha_composite(g, ((32 - g.width) // 2, (32 - g.height) // 2)); im.alpha_composite(b, (282 - 16, 70 - 16))
    xs = {1: (214,), 3: (154, 214, 274)}[len(transport_imgs)]
    for cx, n in zip(xs, transport_imgs):
        g = s.img(n).resize((24, 24), Image.LANCZOS); im.alpha_composite(g, (cx - 12, 101))
    if live:
        # Radio Now Playing's LIVE divider (tools/pod_ui.py rn_live): fading capsules either side of a small white LIVE, where the progress bar would be
        import mod_nowplaying as NPM
        w = 297 - 130 + 1; bw = (w - NPM.LIVE_W - 2 * NPM.LIVE_GAP) // 2
        im.alpha_composite(NPM.live_bar_image(bw, False), (130, 136 - NPM.LIVE_BAR_H // 2))
        im.alpha_composite(NPM.live_bar_image(bw, True), (298 - bw, 136 - NPM.LIVE_BAR_H // 2))
        s.text(im, 214, 136, 'LIVE', 13, (255, 255, 255), anchor='m')
    else:
        d.rounded_rectangle((130, 134, 297, 138), 2, fill=(0x48, 0x48, 0x4A)); d.rounded_rectangle((130, 134, 205, 138), 2, fill=(0xF2, 0xF2, 0xF2))
        s.text(im, 130, 151, '1:47', 12, DIM); s.text(im, 297, 151, '-1:26', 12, DIM, anchor='r')


def quad_disc(im, s, cx, cy, g, on):
    t = MI.disc(54, (255, 255, 255) if on else (0x2C, 0x2C, 0x2E))
    ink = (0x14, 0x14, 0x14) if on else (255, 255, 255)
    if g.startswith('txt:'):
        im.alpha_composite(t, (cx - 27, cy - 27)); s.text(im, cx, cy, g[4:], 17, ink, anchor='m'); return
    gi = act_glyph(s, g, 24)
    if on: gi = MI.tint(gi, ink)
    t.alpha_composite(gi, ((54 - gi.width) // 2, (54 - gi.height) // 2)); im.alpha_composite(t, (cx - 27, cy - 27))


def page_kind(s, root, ttf, top, quad, right):
    """S..V: the taller card, a square of four discs (left), two wide cards (right); one builder per player kind."""
    im = base(s, root); tall_card(im, s, **top)
    card(im, (10, 173, 153, 317), 26)
    for i, (g, on) in enumerate(quad):
        if g: quad_disc(im, s, 46 + (i % 2) * 71, 209 + (i // 2) * 72, g, on)
    for j, (g, title, sub, lit) in enumerate(right):
        y0 = 173 + j * 77; wide_card(im, s, (162, y0, 309, y0 + 67), g, title, sub, lit)
    dots(im, 1)
    return im


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]; work = args[0]; out = args[1] if len(args) > 1 else 'out/preview/cc2.png'
    tree = os.path.join(work, 'tree') if os.path.isdir(os.path.join(work, 'tree')) else work
    s = PI.Side(tree, True)
    raw = os.path.join(tree, RAW)
    root = awtk_ui.parse(open(os.path.join(raw, 'ui/dialog/dropdown_dialog.bin'), 'rb').read())
    ttf = Ttf(os.path.join(tree, MP.FONT))
    p1 = preview.controls(s, tree).crop((0, 0, 320, H)); dots(p1, 0)
    if '--kinds' in sys.argv:
        eq, sl = ('sliders-vertical', 'Equalizer', 'AutoEq', True), ('moon', 'Sleep', '25m left', True)
        music = page_kind(s, root, ttf, dict(title='Blue in Green', sub='Miles Davis', transport_imgs=('np_prev', 'np_pause', 'np_next')),
                          (('shuffle', True), ('list-music', False), ('img:pod_ic_artists', False), ('disc-3', False)), (eq, sl))
        sp = ('circle-gauge', 'Speed', '1.5x', True)
        radio = page_kind(s, root, ttf, dict(title='Take Five', sub='Jazz FM 91', transport_imgs=('np_stop',), fav=False, live=True, art=cover(96, (150, 70, 60), (50, 20, 30))),
                          (('img:pod_ic_radio', False), ('history', False), ('info', False), ('search', False)),
                          (('list-plus', 'Station', 'Saved', True), ('moon', 'Sleep', 'Off', False)))
        pod = page_kind(s, root, ttf, dict(title='The Long Game, Part 2', sub='Hardcore History', transport_imgs=('np_back15', 'np_pause', 'np_fwd30'), fav=False,
                                           art=cover(96, (200, 140, 50), (90, 50, 20))),
                        (('img:pod_ic_podcasts', False), ('list', False), ('info', False), ('skip-forward', False)), (sp, ('moon', 'Sleep', '25m left', True)))
        book = page_kind(s, root, ttf, dict(title='Moby-Dick', sub='Part 3 of 135  -  42% read', transport_imgs=('np_back15', 'np_pause', 'np_fwd30'), fav=False,
                                            art=cover(96, (60, 120, 100), (20, 50, 45))),
                         (('img:pod_ic_audiobooks', False), ('list', False), ('info', False), ('skip-forward', False)), (('circle-gauge', 'Speed', '1.0x', False), ('moon', 'Sleep', '25m left', True)))
        panels = [('S  Music', music), ('T  Radio', radio), ('U  Podcast', pod), ('V  Audiobook', book)]
    elif '--sq' in sys.argv:
        quad = (('shuffle', True), ('repeat', False), ('list-music', False), ('mic-vocal', False))
        q = (('disc-3', 'Album', 'Kind of Blue', False), ('list-plus', 'Playlist', 'Add song', False))
        r = (('sliders-vertical', 'Equalizer', 'AutoEq', True), ('moon', 'Sleep', '25m left', True))
        r2 = (('sliders-vertical', 'Equalizer', 'Off', False), ('moon', 'Sleep', 'Off', False))
        panels = [('O', page_act_pills(s, root, ttf, (('list-music', 'Up Next'), ('mic-vocal', 'Lyrics'), ('disc-3', 'Go to Album'), ('list-plus', 'Add to Playlist')))),
                  ('Q  square + actions', page_square(s, root, ttf, quad, q)), ('R  square + EQ / Sleep', page_square(s, root, ttf, quad, r)),
                  ('R  both off', page_square(s, root, ttf, quad, r2))]
    elif '--act' in sys.argv:
        m = (('list-music', 'Up Next'), ('mic-vocal', 'Lyrics'), ('disc-3', 'Go to Album'), ('list-plus', 'Add to Playlist'))
        n = (('list-music', 'Up Next'), ('img:pod_ic_artists', 'Go to Artist'), ('info', 'Song Info'), ('radio', 'Radio'))
        o = (('list-music', 'Up Next'), ('mic-vocal', 'Lyrics'), ('disc-3', 'Go to Album'), ('list-plus', 'Add to Playlist'))
        p8 = (('list-music', 'Up Next'), ('mic-vocal', 'Lyrics'), ('disc-3', 'Album'), ('img:pod_ic_artists', 'Artist'),
              ('list-plus', 'Add to List'), ('info', 'Song Info'), ('search', 'Search'), ('radio', 'Radio'))
        panels = [('Page 1', p1), ('M  4 discs', page_act_discs(s, root, ttf, m)), ('N  other 4', page_act_discs(s, root, ttf, n)),
                  ('O  wide buttons', page_act_pills(s, root, ttf, o)), ('P  8 small', page_act_grid(s, root, ttf, p8))]
    elif '--more' in sys.argv:
        panels = [('Page 1', p1), ('Page 2: 8 more', page_more(s, root, ttf)), ('Page 2: 3 more', page_more(s, root, ttf, 3))]
    elif '--ios' in sys.argv:
        panels = [('H  player', page_player(s, root, ttf)), ('I  album tint', page_tint(s, root, ttf)), ('J  centred', page_centre(s, root, ttf)),
                  ('K  tall volume', page_vslider(s, root, ttf)), ('L  Up Next', page_upnext(s, root, ttf))]
    elif '--bar' in sys.argv:
        panels = [('Page 1: playing', page1_bar(s, root, ttf)), ('Page 1: paused', page1_bar(s, root, ttf, False)),
                  ('Page 2 D: 8 tiles + brightness', page2_tiles(s, root, ttf)), ('Page 2 E: 4 tiles + 2 sliders', page2_sliders(s, root, ttf))]
    else:
        panels = [('Page 1 (today)', p1), ('A  Now Playing', page_a(s, root, ttf)), ('B  More tiles', page_b(s, root, ttf)), ('C  Status', page_c(s, root, ttf))]
    gap, top = 24, 30
    sheet = Image.new('RGBA', (len(panels) * (320 + gap) + gap, H + top + gap), (0x30, 0x30, 0x34, 255))
    for i, (lab, p) in enumerate(panels):
        x = gap + i * (320 + gap); sheet.alpha_composite(p, (x, top)); s.text(sheet, x, top / 2, lab, 18)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.convert('RGB').save(out); print(out)


if __name__ == '__main__':
    main()
