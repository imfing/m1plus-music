#!/usr/bin/env python3
"""The palette's model (docs/modules/accent.md): the one colour mapping (background, then accent), Light Mode's flip of a neutral colour and the classification of a theme image, as
patch/palette.c does them at run time.

patch/palette.c is the C twin of this file and test/pod/palette.py runs the compiled C against it; the previews (tools/preview_settings.py) draw with this one. The constants are read from
patch/offsets.inc (LIGHT_*), the name lists are below and pod.py writes them into stock.h for the payload, so there is one source for each.

  map_colour(c, bg, ac) the one entry point: a colour as the painter gets it for a background ('black', 'tinted' or 'light') and an accent (ACCENTS; the role colours, below)
  render_image(n, im, bg, ac) the image as the device shows it: tinted by the accent (ACCENT_* names), else Light's flip
  flip(c)               a colour (r, g, b) or (r, g, b, a): neutral colours (channels within LIGHT_SPREAD) flip per channel, black to LIGHT_PAPER and white to LIGHT_INK, alpha kept
  image_flips(name, im) whether the image of that file name is flipped, and how: None (kept), 'glyph' (every pixel, no colour in it and mostly glyph) or 'whole' (a plate or card of ours)
  flip_image(name, im)  the image as the device shows it in Light Mode

An image is the theme's only when its name is a plain asset name (no '/' and no ':'): covers by path or URL never are. Album art, covers, wallpapers, photos and videos are never changed.
"""
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _consts():
    out = {}
    for line in open(os.path.join(ROOT, 'patch', 'offsets.inc')):
        m = re.match(r'#define ((?:LIGHT|ACC|ROLE)_\w+) (0x[0-9a-fA-F]+|\d+)\b', line)
        if m: out[m.group(1)] = int(m.group(2), 0)
    return out


C = _consts()
PAPER, INK, SPREAD, CHROMA, GLYPH, SURFACE = (C[k] for k in ('LIGHT_PAPER', 'LIGHT_INK', 'LIGHT_SPREAD', 'LIGHT_CHROMA', 'LIGHT_GLYPH', 'LIGHT_SURFACE'))
DAY_FROM, DAY_UNTIL = C["LIGHT_FROM"], C["LIGHT_UNTIL"]
TINT, TRACK_R, FILL_R, KNOB_R, TILE_R = (C[k] for k in ('ACC_TINT', 'ACC_TRACK_R', 'ACC_FILL_R', 'ACC_KNOB_R', 'ACC_TILE_R'))
WASH, DARK = C['ACC_WASH'], C['ACC_DARK']   # the Tinted background: percent of the accent in a dark neutral colour, and the brightest channel that still counts as dark
CARD = tuple(C['ACC_CARD'].to_bytes(3, 'big'))   # the settings card colour
ROLE_PRESS_ROW, ROLE_PROGRESS, ROLE_PRESS_PILL, ROLE_PRESS_QPILL = (C[k] for k in ('ROLE_PRESS_ROW', 'ROLE_PROGRESS', 'ROLE_PRESS_PILL', 'ROLE_PRESS_QPILL'))
PILL, QPILL, SHUF = (tuple(C[k].to_bytes(3, 'big')) for k in ('ACC_PILL', 'ACC_QPILL', 'ACC_SHUF'))   # rest colours of the surfaces a pressed role tints: the flat pill, the Queue's off buttons, the Shuffle disc
SHUF_DOWN_R = C['ACC_SHUF_DOWN_R']
# The pressed-surface roles (colour -> the rest surface it is tinted from); patch/palette.c pal_role. Row: the page black.
PRESS_SURFACES = {ROLE_PRESS_ROW: (0, 0, 0), ROLE_PRESS_PILL: PILL, ROLE_PRESS_QPILL: QPILL}

# Images that are never flipped, by name prefix: objects with materials of their own (the cassette, the Pod's wheel and marks), the soft shadow under the Now Playing cover, and the glass
# the lock screen's card and the Daily Mix's Add disc put over a photo or art (their text stays white there). Every other image follows the rule below.
KEEP = ('tape_', 'ipod_', 'np_shadow', 'lk_card', 'dm_disc', 'pod_sw')
# Images of ours that are plates, cards and gradients rather than glyphs, flipped whole (every neutral pixel): the Settings cards, the bottom sheets, the mini player's glass pane, and the
# black fades over a page (the navbar's, the tint under Now Playing / the album page, the lyrics scrim), which become paper fades.
WHOLE = ('pod_cd_', 'pc_sheet', 'pm_sheet', 'mb_glass', 'nb_fade', 'np_tint', 'np_scrim', 'ah_tint')
# The fades over a cover-tinted page (Now Playing, the album page): they stay black on the Tinted background, as the pages' cover tones do. The other WHOLE images are surfaces the Tinted background tints.
COVER_FADES = ('np_tint', 'np_scrim', 'ah_tint')
TINT_SURFACE = tuple(n for n in WHOLE if n not in COVER_FADES)
# Windows that stay as they are in Light Mode (the style hooks pass through while one is the top main window): the lock screen's wallpaper and glass card, the full-screen cover, the
# power-off splash, and the two pages with a look of their own, the Pod and Cassette Mode.
EXEMPT = ('screensaver_page', 'bigcover_page', 'poweroff_page', 'm1plus_ipod_page', 'm1plus_tape_page')
# The cover-tinted pages (patch/palette.c pal_cover_page; the order is its PAL_COVER_* codes): Now Playing, the album page, the Podcasts Show page and the Daily Mix page. While one is the top main
# window and shows a cover's tone (the album page once tinted, the Show page but not the shows list or an episode) the Tinted wash leaves every colour alone; the accent's roles still apply.
COVER_PAGES = ('playing_page', 'm1plus_album_page', 'm1plus_podcasts_page', 'm1plus_dailymix_page', 'm1plus_radionp_page')


def flip_v(v):
    """One channel: black to LIGHT_PAPER, white to LIGHT_INK (the C: LIGHT_PAPER - v * (LIGHT_PAPER - LIGHT_INK) / 255)."""
    return PAPER - v * (PAPER - INK) // 255


def neutral(c):
    """Channels within LIGHT_SPREAD of each other (r, g and b of c; alpha is not looked at)."""
    return max(c[:3]) - min(c[:3]) <= SPREAD


def flip(c):
    """A colour (3 or 4 channels) flipped when it is neutral; any other hue, and the alpha, as they are."""
    return tuple(flip_v(v) for v in c[:3]) + tuple(c[3:]) if neutral(c) else tuple(c)


def ink(c):
    """The payload's own colours (ui_ink): a clear colour (alpha 0) stays as it is, since stock tests for it."""
    return tuple(c) if len(c) == 4 and c[3] == 0 else flip(c)


BACKGROUNDS = ('black', 'tinted', 'light')   # Tinted needs an accent (with Neutral it is Black); Light is not offered in the picker
ACCENTS = ('neutral', 'red', 'orange', 'green', 'teal', 'purple', 'champagne')   # the saved index is the position here (patch/palette.c pal_accent)
ACCENT_RGB = {a: tuple(C['ACC_' + a.upper()].to_bytes(3, 'big')) for a in ACCENTS[1:]}
NEUTRAL_FILL = (0xEE, 0xEE, 0xEC)   # what the swatch of Neutral shows: today's #EEEEEC fill

# Images the accent tints, by exact name (patch/palette.c pal_accent_image; pod.py writes the lists into stock.h as ACCENT_FILL / ACCENT_SWITCH / ACCENT_PRESS / ACCENT_DISC). FILL: slider and progress fills
# (the pull-down's volume and brightness, the volume page, the other progress bars, the CD ring, the date selector's edge), the picker check and the playing wave: single-colour art whose
# pixels run from the dark track (ACC_TRACK_R) to the fill (ACC_FILL_R) and go to the accent by how light they are. SWITCH: the on switch (track #EEEEEC to the accent, knob #141414 to white).
# PRESS: the settings card's pressed pieces, mix(card, accent, ACC_TINT %). Pressed rows' glyphs have no twin image of their own: nothing to tint.
ACCENT_FILL = ('vol_progress', 'volume_fg', 'drop_fg', 'eq_plan', 'other_progress', 'cdprogress_bar', 'datetime_back', 'pod_check', 'np_row_playing')
ACCENT_SWITCH = ('sset_on',)
ACCENT_PRESS = tuple(f'pod_cd_{p}_down' for p in ('single', 'top', 'mid', 'bot'))
# DISC: the pull-down's ON tiles, a filled white disc with a #141414 glyph (or a glyph cut out of the disc): white to the accent, the dark glyph stays dark (ACC_KNOB_R), a pixel between moves by its lightness.
ACCENT_DISC = ('drop_wifiopen', 'drop_btopen', 'drop_keylockopen', 'drop_eqopen', 'drop_usbaudio', 'drop_usbdac', 'drop_usbstorage', 'drop_playsetdown', 'drop_syssetdown', 'drop_highgain', 'drop_lo')
# GLYPH, by name prefix: every row glyph is white art, tinted at decode: every colour becomes the accent, alpha kept. The M1+ Music rows' (the main menu, Shuffle, Extras and Main Menu pages), the Folders list's own
# (fo_ic_sd, fo_ic_usb, fo_ic_file) and the Settings cards' (pod_ci_*, tools/mod_icons.py CARD_GLYPHS; the accent swatches pod_sw* are not). The two tiles (a rounded square with its own colour behind the glyph,
# patch/podcasts.c) are not glyphs. GLYPH_STOCK, by exact name (plain white art, alpha kept): the More sheet's stock row glyphs (Look up album, Look up artist, Add to playlist, Speed, A-B repeat; patch/playmore.c),
# the Podcasts sheets' (pc_ic_*: all but pc_ic_unsub, already red; pc_ic_trash is Radio's Clear row's too), the Playlists "..." menu's (pl_ic_new, pl_ic_import, pl_ic_export, pl_ic_delete),
# the track rows' "..." sheet's (rm_ic_next, rm_ic_after, rm_ic_add; patch/rowmenu.c), the multi-select Add dialog's (batchadd_fav, batchadd_playlist) and the selection checks: the Songs sort card's tick (sg_tick) and the stock Select All navbar button's checked state (mulselected). So every
# row of those sheets is the accent, the destructive rows' glyphs too (their labels do not change: Delete Song's stays red). Not p_onlinesearch (never shown) and not selected (also the Delete dialog's "also delete the file" checkbox).
ACCENT_GLYPH = ('pod_ic_', 'fo_ic_', 'pod_ci_', 'pod_sb_download')
ACCENT_GLYPH_STOCK = ('player_albuminfo', 'player_songerinfo', 'p_add', 'p_multiple', 'p_abrepeat', 'p_delete',
                      'pc_ic_import', 'pc_ic_speed', 'pc_ic_refresh', 'pc_ic_select', 'pc_ic_check', 'pc_ic_down', 'pc_ic_undo', 'pc_ic_trash',
                      'pl_ic_new', 'pl_ic_import', 'pl_ic_export', 'pl_ic_delete', 'rm_ic_next', 'rm_ic_after', 'rm_ic_add', 'batchadd_fav', 'batchadd_playlist', 'sg_tick', 'mulselected',
                      'ah_pill_down', 'dp_pill_down')
# TILE: the Podcasts Library rows' tiles (patch/podcasts.c; a #1E1E1E rounded square, ACC_TILE_R, with a white glyph on it): white goes to the accent, the square stays exactly #1E1E1E, the antialiased glyph edge
# between blends by lightness (the disc rule with the tile's grey as the fixed end). Their pod_ic_ prefix is why they are in GLYPH_NOT (the glyph rule would paint the whole square).
ACCENT_TILE = ('pod_ic_dltile', 'pod_ic_subtile', 'pod_ic_savetile')
# SHUFDOWN: the album page's (and the Daily Mix page's) pressed Shuffle disc ah_shuffle_down (a #444444 disc, a white glyph): the disc becomes the pressed tint of the rest disc #2A2A2A,
# mix(#2A2A2A, accent, ACC_TINT %), the glyph stays white. The white Play pills' pressed images (ah_pill_down, dp_pill_down: one solid colour each, the dark glyph and the label are drawn apart) are
# GLYPH_STOCK names below: the solid accent. Dark flat pills (Songs / Folders Play and Shuffle) and the Queue's off buttons press through the roles ROLE_PRESS_PILL / ROLE_PRESS_QPILL (colours, not images).
ACCENT_SHUFDOWN = ('ah_shuffle_down',)
# pod_ic_rd_art (a muted grey #8E8E93 radio set: secondary art, the logo-less station tile, Radio Now Playing's art box and the mini bar) also keeps the prefix out of the glyph rule: placeholders stay neutral.
ACCENT_GLYPH_NOT = ACCENT_TILE + ('pod_ic_rd_art',)
ACCENT_ALL = ACCENT_FILL + ACCENT_SWITCH + ACCENT_PRESS + ACCENT_DISC + ACCENT_TILE + ACCENT_SHUFDOWN


def mix_tint(base, acc):
    """A surface with TINT percent of the accent: (base * (100 - TINT) + acc * TINT + 50) // 100 per channel (patch/palette.c pal_mix)."""
    return tuple((b * (100 - TINT) + a * TINT + 50) // 100 for b, a in zip(base, acc))


def mix_pct(base, acc, pct):
    """base with pct percent of acc, per channel, rounded (patch/palette.c pal_mix)."""
    return tuple((b * (100 - pct) + a * pct + 50) // 100 for b, a in zip(base, acc))


def is_dark(c):
    """A dark neutral colour (channels within LIGHT_SPREAD, none above ACC_DARK): what the Tinted background tints."""
    return neutral(c) and max(c[:3]) <= DARK


def wash(c, ac):
    """The Tinted background (a colour, 3 or 4 channels): a dark neutral one takes WASH percent of the accent, alpha kept; any other colour and Neutral stay."""
    if ac == 'neutral' or not is_dark(c): return tuple(c)
    return mix_pct(c[:3], ACCENT_RGB[ac], WASH) + tuple(c[3:])


def row_press(ac, bg='black'):
    """The pressed row under an accent: the page black (on Tinted, the tinted page black) tinted."""
    return mix_tint(wash((0, 0, 0), ac) if bg == 'tinted' else (0, 0, 0), ACCENT_RGB[ac])


def press_of(surface, ac, bg='black'):
    """A pressed surface under an accent: its rest colour (on Tinted, the tinted rest colour) with ACC_TINT percent of the accent."""
    return mix_tint(wash(surface, ac) if bg == 'tinted' else surface, ACCENT_RGB[ac])


def card_press(ac, bg='black'):
    """The pressed settings card under an accent: the card colour (on Tinted, the tinted card) tinted."""
    return mix_tint(wash(CARD, ac) if bg == 'tinted' else CARD, ACCENT_RGB[ac])


def role(c, ac, bg='black'):
    """The accent step of patch/palette.c pal_map: a colour that is one of the unique role colours (compared without alpha, alpha kept) becomes the accent's; None when it is not."""
    if ac == 'neutral': return None
    rgb = (c[0] << 16) | (c[1] << 8) | c[2]
    if rgb in PRESS_SURFACES: new = press_of(PRESS_SURFACES[rgb], ac, bg)
    elif rgb == ROLE_PROGRESS: new = ACCENT_RGB[ac]
    else: return None
    return new + tuple(c[3:])


def not_role(c):
    """patch/palette.c pal_not_role: a colour derived from a cover (3 or 4 channels) that equals a role colour moves one LSB of blue off it (#333334 to #333333, #FFFFFE to #FFFFFF)."""
    rgb = (c[0] << 16) | (c[1] << 8) | c[2]
    if rgb == ROLE_PRESS_ROW: return (c[0], c[1], c[2] - 1) + tuple(c[3:])
    if rgb in (ROLE_PROGRESS, ROLE_PRESS_PILL, ROLE_PRESS_QPILL): return (c[0], c[1], c[2] + 1) + tuple(c[3:])
    return tuple(c)


def map_colour(c, bg='black', ac='neutral', cover=False):
    """patch/palette.c pal_map: an accent's role colour first (a pressed row, the Now Playing progress fill: they are chromatic or accent-coloured, so the background never touches
    them), else the background (black: as it is; tinted: a dark neutral colour takes WASH % of the accent, except while a cover-tinted page shows its tone (cover=True); light: the neutral flip). Pure: its callers (ui_ink, the hooks) skip a clear colour (alpha 0) first, since stock tests for it (see ink).
    Black + neutral is the identity: the hooks are pass-throughs."""
    assert bg in BACKGROUNDS and ac in ACCENTS, (bg, ac)
    c = tuple(c)
    r = role(c, ac, bg)
    if r is not None: return r
    return flip(c) if bg == 'light' else wash(c, ac) if bg == 'tinted' and not cover else c


def plain(name):
    """A theme asset's name: no '/' and no ':' (a path or URL is a cover)."""
    return bool(name) and '/' not in name and ':' not in name


def image_flips(name, im):
    """None (the image stays), 'whole' (a plate of ours: every neutral pixel flips) or 'glyph' (a theme image without colour that is mostly glyph: every pixel flips).
    The glyph rule is q2-pod's: no pixel (alpha 128 and up) more than LIGHT_CHROMA saturated, and under 1/LIGHT_SURFACE of the area opaque and darker than LIGHT_GLYPH."""
    if not plain(name) or name.startswith(KEEP): return None
    if name.startswith(WHOLE): return 'whole'
    w, h = im.size
    px = im.convert('RGBA').getdata()
    solid = 0
    for r, g, b, a in px:
        if a < 128: continue
        if max(r, g, b) - min(r, g, b) > CHROMA: return None
        solid += (r * 299 + g * 587 + b * 114) // 1000 < GLYPH
    return 'glyph' if solid * SURFACE < w * h else None


def flip_image(name, im):
    """The image the device shows in Light Mode: straight alpha, every flipped pixel mapped per channel."""
    from PIL import Image
    how = image_flips(name, im)
    im = im.convert('RGBA')
    if how is None: return im
    out = Image.new('RGBA', im.size)
    every = lambda p: tuple(flip_v(v) for v in p[:3]) + tuple(p[3:])   # a glyph image: every channel (nothing in it has colour but pixels too faint to count)
    out.putdata([(every(p) if how == 'glyph' else flip(p)) if p[3] else p for p in im.getdata()])   # (a clear pixel's colour is not seen: the device leaves it)
    return out


def _trunc(a, b):
    """a / b toward zero (C's integer division)."""
    return a // b if a >= 0 else -(-a // b)


def _clamp255(v):
    return max(0, min(255, v))


def accent_pixel(kind, p, ac, bg='black'):
    """One straight pixel (r, g, b, a) of an accent-tinted image (kind 'fill', 'switch', 'press' or 'disc'); a clear pixel and the alpha stay. patch/palette.c pal_accent_image is the C twin."""
    if not p[3]: return p
    acc = ACCENT_RGB[ac]
    if kind == 'press': return card_press(ac, bg) + (p[3],)
    if kind == 'glyph': return acc + (p[3],)
    if kind == 'shufdown':   # the pressed Shuffle disc: the disc (#44) becomes the tinted rest disc, the white glyph stays, between by lightness
        base = press_of(SHUF, ac, bg)
        u = _clamp255((p[0] - SHUF_DOWN_R) * 255 // (255 - SHUF_DOWN_R))
        return tuple(b + (255 - b) * u // 255 for b in base) + (p[3],)
    if kind == 'tile':   # the square (#1E1E1E) stays, white goes to the accent, the glyph's antialiased edge blends by lightness
        u = _clamp255((p[0] - TILE_R) * 255 // (255 - TILE_R))
        return tuple(TILE_R + _trunc((a - TILE_R) * u, 255) for a in acc) + (p[3],)
    if kind == 'fill':   # the fill (or lighter: white) becomes the accent, the track (or darker) stays, a pixel between them (an antialiased edge over a track) moves by its share t of the way fill -> accent
        if p[0] >= FILL_R: return acc + (p[3],)
        if p[0] <= TRACK_R: return p
        t = (p[0] - TRACK_R) * 255 // (FILL_R - TRACK_R)
        return tuple(_clamp255(v + _trunc((a - f) * t, 255)) for v, a, f in zip(p[:3], acc, NEUTRAL_FILL)) + (p[3],)
    if kind == 'disc':   # an ON tile: u is how light the pixel is (white 255 .. #141414 0); white goes to the accent, #141414 stays, the antialiased edge between blends the same way
        u = _clamp255((p[0] - KNOB_R) * 255 // (255 - KNOB_R))
        return tuple(KNOB_R + _trunc((a - KNOB_R) * u, 255) for a in acc) + (p[3],)
    u = _clamp255((FILL_R - p[0]) * 255 // (FILL_R - KNOB_R))   # a switch: the track to the accent, the knob to white
    return tuple(a + (255 - a) * u // 255 for a in acc) + (p[3],)


def accent_kind(name):
    """'fill', 'switch', 'press', 'disc', 'tile' or 'glyph' for a theme image the accent tints, else None (a path or URL is a cover)."""
    if not plain(name): return None
    if name in ACCENT_TILE: return 'tile'
    if name in ACCENT_SHUFDOWN: return 'shufdown'
    if (name.startswith(ACCENT_GLYPH) and name not in ACCENT_GLYPH_NOT) or name in ACCENT_GLYPH_STOCK: return 'glyph'
    return 'fill' if name in ACCENT_FILL else 'switch' if name in ACCENT_SWITCH else 'press' if name in ACCENT_PRESS else 'disc' if name in ACCENT_DISC else None


def tint_surface(name):
    """A theme image the Tinted background tints: a plain name with one of the TINT_SURFACE prefixes."""
    return plain(name) and name.startswith(TINT_SURFACE)


def render_image(name, im, bg='black', ac='neutral'):
    """The image the device shows (RGBA, straight alpha) for a background and an accent: an accent-tinted image is tinted instead of flipped (the accent wins over Light; its press piece follows the Tinted
    background), else Light's rule, else on Tinted a surface's dark neutral pixels take WASH % of the accent."""
    kind = accent_kind(name) if ac != 'neutral' else None
    if kind is None:
        if bg == 'light': return flip_image(name, im)
        if bg != 'tinted' or ac == 'neutral' or not tint_surface(name): return im.convert('RGBA')
        from PIL import Image
        im = im.convert('RGBA')
        out = Image.new('RGBA', im.size)
        out.putdata([wash(p, ac) if p[3] else p for p in im.getdata()])
        return out
    from PIL import Image
    im = im.convert('RGBA')
    out = Image.new('RGBA', im.size)
    out.putdata([accent_pixel(kind, p, ac, bg) for p in im.getdata()])
    return out


def glyph_image_px(p, ac, premul=False):
    """One pixel of a row glyph tinted at decode (kind GLYPH; r, g, b, a): the accent with the alpha kept; premultiplied pixels (as stored) get the accent scaled by the alpha."""
    a = p[3]
    return tuple(c * a // 255 for c in ACCENT_RGB[ac]) + (a,) if premul else ACCENT_RGB[ac] + (a,)


if __name__ == '__main__':
    sys.exit(__doc__)
