#!/usr/bin/env python3
"""The Settings pages (iOS style grouped cards, docs/modules/settings.md "Cards"), drawn from the built tree's own ui assets: the cards, rows, glyphs, hairlines, headers and notes are the
widgets tools/pod_ui.py build_cards_page made from the numbers of tools/pod_settings.py (shared with the tests), with the font, images and navbar of the tree. A value takes the room its text
needs and the row's label gets the rest, as patch/m1plus.c value_fit does. Approximate (PIL, not AWTK); the sample state (values, switches, checks) is what a typical device shows.

  out/preview/settings-mock-3.png   Settings (first screen and whole list), Home Screen, Library, Now Playing, Theme, Developer, Keyboards, About

Usage: uv run python -I tools/preview/preview_settings.py WORKDIR [OUT.png]     (en_US; WORKDIR e.g. work/mod-release after a build)
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw
import awtk_ui, build, palette, preview_icons as PI, pod_settings as ST
from stb_raster import StbFont

W, NAV, SCREEN = 320, 50, 450
WRAP_UNIT = re.compile(r'[^\s⺀-鿿＀-￯฀-๿]+\s*|[⺀-鿿＀-￯฀-๿]\s*|\s+')
RAW = PI.RAW

# What a typical device shows: widget name -> text (values), name -> on (switches), name -> shown (checks, the hidden card), per page key.
WT_STATE = {'values': {'pod_big0_t': '192.168.100.100:8888'}}
WT_QR_STATE = dict(WT_STATE, hidden={'pod_hero'}, items={'pod_qr'}, pill='Hide QR Code')   # the pill tapped: the code in the hero's place (patch/netservice.c wt_qr_set)   # Wi-Fi Transfer: the big card's text, four three-digit groups (the digits are tabular: 255.255.255.255 is as wide)
XFADE_SHOWN = {'pod_sec0', 'pod_xfcard', 'pod_row1', 'pod_note0', 'pod_note1'}   # the items of the Crossfade page the payload shows while its switch is on (patch/xfadeset.c xfade_show)
XFADE_ON = {'switches': {'pod_switch0': True, 'pod_switch1': True}, 'items': XFADE_SHOWN, 'vol': 5, 'xf_text': '5 seconds'}
XFADE_OFF = {'switches': {'pod_switch0': False, 'pod_switch1': True}}
STATE = {
    'm1plus_settings': {'values': {'pod_value0': 'Off', 'pod_value1': 'Off', 'pod_value6': 'Rock'}},   # Wi-Fi, Bluetooth and EQ (the 10-Band EQ's curve name, or Off)
    'm1plus_appearance': {'values': {'pod_value0': 'Black', 'pod_value1': 'Neutral'}, 'switches': {'pod_switch3': True}},
    'm1plus_general': {'values': {'pod_value3': 'English'}},   # Language
    'm1plus_background': {'shown': {'pod_check1'}},
    'm1plus_accent': {'shown': {'pod_check0'}},
    'm1plus_battery': {'values': {'pod_value1': '80%'}, 'switches': {'pod_switch0': True}},
    'm1plus_chargelimit': {'shown': {'pod_check0'}},
    'm1plus_display': {'values': {'pod_value0': '30s', 'pod_value3': 'Green'}, 'switches': {'pod_switch2': True}},   # Screen Timeout, LED Light; Screen Rotation on
    'm1plus_sleeptimer': {'shown': {'pod_check0'}, 'hidden': {'pod_row7'}},   # a timer off: no Time Left card
    'm1plus_language': {'shown': {'pod_check0'}},
    'm1plus_datetime': {'values': {'pod_value1': 'Auckland', 'pod_value2': '2026-11-15', 'pod_value3': '14:05'}, 'switches': {'pod_switch0': False, 'pod_switch4': True}},
    'm1plus_lighttime': {'shown': {'pod_check2'}},
    'm1plus_keyspower': {'values': {'pod_value0': 'Both', 'pod_value3': '5min'}, 'switches': {'pod_switch1': True, 'pod_switch2': False, 'pod_switch4': True}},
    'm1plus_playset': {'values': {'pod_value0': 'Repeat All', 'pod_value1': 'Off', 'pod_value3': 'Location', 'pod_value5': '5 s'}, 'switches': {'pod_switch2': True, 'pod_switch4': False}},
    'm1plus_psxfade': XFADE_ON,
    'm1plus_psvolume': {'values': {'pod_value0': 'Low', 'pod_value1': '80', 'pod_value2': 'Memory', 'pod_value3': 'Off', 'pod_value4': 'L3', 'pod_value6': 'Medium'}, 'switches': {'pod_switch5': True}},
    'm1plus_psoutput': {'values': {'pod_value1': 'D2P', 'pod_value3': 'Variable'}, 'switches': {'pod_switch4': False}},
    'm1plus_psxfeed': {'shown': {'pod_check2'}},
    'm1plus_psmaxvol': {'vol_text': '80', 'vol': 80},
    'm1plus_plcover': {'cover': 3, 'switches': {'pod_switch0': False}},
    'm1plus_volume': {'volnum': '42', 'volinfo': 'Headphones \u00b7 Max 80', 'vol': 42},
    'm1plus_psbootvol': {'vol_text': '30', 'vol': 30, 'switches': {'pod_switch0': False}},
    'm1plus_psbal': {'vol_text': 'L3', 'vol': 7},
    'm1plus_psmode': {'shown': {'pod_check3'}},
    'm1plus_psfilter': {'shown': {'pod_check3'}},
    'm1plus_psgain': {'shown': {'pod_check0'}},
    'm1plus_keylock': {'shown': {'pod_check3'}},
    'm1plus_shutdown': {'shown': {'pod_check3'}},
    'm1plus_ledlight': {'shown': {'pod_check1'}},
    'm1plus_nextalbum': {'shown': {'pod_check0'}},
    'm1plus_lockscreen': {'switches': {'pod_switch0': True, 'pod_switch2': True}, 'values': {'pod_value3': 'Large Cover'}},
    'm1plus_lockstyle': {'shown': {'pod_check0'}},
    'm1plus_homeset': {'switches': {'pod_switch0': True, 'pod_switch1': True}},
    'm1plus_library': {'switches': {'pod_switch3': True, 'pod_switch4': True, 'pod_switch5': True, 'pod_switch6': False}},
    'm1plus_npset': {'values': {'pod_value0': 'Chrome'}},
    'm1plus_tapetheme': {'shown': {'pod_check1'}},
    'm1plus_developer': {'switches': {'pod_switch0': True}},
    'm1plus_about': {'values': {'pod_value0': 'V2.1pM', 'pod_value1': 'V2.1', 'pod_value2': 'Shanling M1 Plus', 'pod_value3': 'M1P2305A01234', 'pod_value4': '98:b3:ec:4a:7c:1e',
                                'pod_value5': '192.168.1.42', 'pod_value6': '119.25 GB', 'pod_value7': '87.41 GB'}},
    'm1plus_keyboards': {'switches': {'pod_switch0': True, 'pod_switch1': False}},
    'm1plus_libupdate': {'values': {'pod_value0': '4,812', 'pod_value1': 'Today 09:41'}, 'switches': {'pod_switch4': True}},   # Update Library: the songs, the last scan, Auto Update on
    'm1plus_cardrun': {'values': {'pod_value0': 'Ready'}},   # Card Script: a script, no run (no row is dimmed)
    'm1plus_cache': {'values': {'pod_value0': '840', 'pod_value1': '812', 'pod_value2': '9', 'pod_value3': '19', 'pod_value4': '3', 'pod_value5': '14.2 MB', 'pod_value6': 'Idle'}},
}


# Settings > Wi-Fi's sample networks: (name, stock level 0..4, secured, saved, connected), the connected one first
WIFI_NETS = [('Home', 4, True, True, True), ('Studio', 4, True, True, False), ('Sam’s iPhone', 3, True, False, False), ('Cafe Open', 3, False, False, False), ('eduroam', 3, True, False, False),
             ('Neighbour 5G', 2, True, False, False)]


def rgb(css):
    css = css.lstrip('#')
    return tuple(int(css[i:i + 2], 16) for i in (0, 2, 4))


def style(w, prop, default=None):
    return w.get(f'style:normal:{prop}') or default


def draw_page(s, key, full=False, state=None, lit=False, pal=None, pressed=None, root=None):
    """A cards page of the tree as the payload leaves it: the widgets of ui/<key>.bin, the sample state applied. lit: in Light Mode (docs/modules/accent.md): every colour of the styles and every
    image as the hooks of patch/palette.c give it (tools/palette.py is their model); the page's layout is the same.
    pal: an optional palette object (tools/preview/preview_accent.py: .ink(rgb), .image(side, name), .base): every colour and image goes through the model of tools/palette.py as the hooks
    of patch/palette.c give it (an accent's tints, the pressed card piece, the row glyphs in the accent); None draws today's colours.
    pressed: the label text of the one row drawn in its pressed state (needs pal).
    root: the same tree, already changed as the payload changes it (the Equalizer page)."""
    ink = (lambda c: palette.flip(c)) if lit else (lambda c: c)
    img = lambda n: palette.flip_image(n, s.img(n)) if lit else s.img(n)
    if pal: ink, img = pal.ink, (lambda n: pal.image(s, n))
    if root is None: root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', key + '.bin'), 'rb').read())
    st = STATE.get(key, {}) if state is None else state
    values, switches, shown = st.get('values', {}), st.get('switches', {}), st.get('shown', set())
    sv = next(w for w in root.walk() if w.name == 'pod_scrollview')
    hidden = st.get('hidden', set())
    kids = [c for c in sv.children if c.name not in hidden and (c.get('visible') != 'false' or c.name in st.get('items', ()))]   # the list_view layouter stacks the visible children (it ignores their y)
    end = sum(c.h for c in kids)
    base = ink((0, 0, 0))
    im = Image.new('RGBA', (W, max(SCREEN, NAV + end) if full else SCREEN), base + (255,)); d = ImageDraw.Draw(im)
    y = NAV
    for c in kids:
        if c.type == 'list_item':
            lab = next(t for t in c.children if t.name.startswith('pod_label'))
            draw_row(s, im, d, c, y, values, switches, shown, ink, img, pal, pal is not None and pressed is not None and s.shown(lab) == pressed)
        if c.name == 'pod_bright': draw_brightness(im, c, y, img, st.get('brightness', 60))
        elif c.name in ('pod_vsval', 'pod_vsctl'): draw_volcard(s, im, c, y, img, ink, st.get('vol_text', ''), st.get('vol', 0), st.get('vol_dim', False))
        elif c.name == 'pod_xfcard': draw_xfcard(s, im, c, y, img, ink, st.get('vol', 5), st.get('xf_text', ''))
        elif c.name == 'pod_volume': draw_volume(s, im, c, y, ink, img, st)
        elif c.name == 'pod_cover': draw_cover(s, im, c, y, ink, img, st.get('cover', 0), st.get('switches', {}).get('pod_switch0', False))
        elif c.name == 'pod_hero': draw_hero(s, im, c, y, ink, img)
        elif c.name.startswith('pod_big'): draw_bigcard(s, im, c, y, ink, img, values)
        elif c.name == 'pod_qr': draw_qr(im, c, y, ink, values)
        elif c.name == 'pod_qrpill': draw_qrpill(s, im, c, y, ink, img, st.get('pill'))
        else: draw_text_item(s, im, c, y, ink, st.get('texts'))
        y += c.h
    d.rectangle((0, 0, W - 1, NAV - 1), fill=base)   # the list is under the navbar: it clips at its top
    lt = next(w for w in root.walk() if w.name == 'label_title'); tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, s.clip(s.shown(lt), tpx, lt.w), tpx, ink((255, 255, 255)))
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):   # the glass navbar: Back (7, 0, 44, 50), Now Playing's round glass (260, 0, 60, 50)
        g = img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    if full and im.height > SCREEN:
        for x in range(0, W, 8): d.line((x, SCREEN, x + 3, SCREEN), fill=(0xFF, 0x50, 0x50))
    return im


def draw_brightness(im, c, y, img, value, card=True):
    """The Display page's brightness card (tools/pod_ui.py cards_brightness): the card piece, the two suns and the slider at `value` (0 .. 100): its bar images stretched to the slider's width,
    the fill up to the thumb, the thumb's image centred on the value (approximate: AWTK's slider draws the bar bar_size high in the middle)."""
    if card: im.alpha_composite(img(c.get('style:normal:bg_image')), (0, y))   # (card=False: the pull-down's, which draws its own flat card and has the children at its own x)
    dx = 0 if card else c.x
    for t in c.children:
        if t.type == 'image' and t.get('visible') != 'false':
            g = img(t.get('image')); im.alpha_composite(g, (dx + t.x + (t.w - g.width) // 2, y + t.y + (t.h - g.height) // 2))
        elif t.type == 'slider': draw_slider(im, t, y, img, value, dx)


def draw_slider(im, t, y, img, value, dx=0):
    """A slider of the pages (the Display page's, the loudness pages'): its bar images stretched to its width, the fill up to the thumb, the thumb's image centred on `value` (0 .. its max)."""
    bar, dot = int(t.get('bar_size')), img(t.get('style:normal:icon'))
    by, travel = y + t.y + (t.h - bar) // 2, t.w - dot.width
    lo = int(t.get('min', '0'))
    tx = dx + t.x; x = tx + dot.width // 2 + travel * (value - lo) // (int(t.get('max', '100')) - lo)
    im.alpha_composite(img(t.get('style:normal:bg_image')).resize((t.w, bar)), (tx, by))
    if x > tx: im.alpha_composite(img(t.get('style:normal:fg_image')).resize((x - tx, bar)), (tx, by))
    im.alpha_composite(dot, (x - dot.width // 2, y + t.y + (t.h - dot.height) // 2))


def draw_xfcard(s, im, c, y, img, ink, value, text):
    """The Crossfade page's duration card (tools/pod_ui.py cards_xfade): the two card pieces, the duration text, "1 s", the slider at `value` (1 .. 12), "12 s" and the dots image."""
    for k in c.children:
        if k.type == 'view': im.alpha_composite(img(k.get('style:normal:bg_image')), (0, y + k.y))
    for t in c.children:
        px = int(style(t, 'font_size')) if t.type == 'label' else 0
        if t.type == 'label':
            al = style(t, 'text_align_h'); lab = text if t.name == 'pod_xf_val' else s.shown(t)
            if al == 'left': s.text(im, t.x, y + t.y + t.h / 2, lab, px, ink(rgb(style(t, 'text_color'))))
            else: s.text(im, t.x + t.w, y + t.y + t.h / 2, lab, px, ink(rgb(style(t, 'text_color'))), anchor='r')
        elif t.type == 'slider': draw_slider(im, t, y, img, value)
        elif t.type == 'image': im.alpha_composite(img(t.get('image')), (t.x, y + t.y))


def draw_volcard(s, im, c, y, img, ink, text, value, dim=False):
    """A loudness page's card (tools/pod_ui.py cards_volcard): the card piece; the value card's label (the text stock's refresh writes) centred; the control card's two buttons (their texts) and the slider at `value`. dim: 60 % opacity, as
    the payload dims Default Volume's cards while Volume Memory is on."""
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.alpha_composite(img(c.get('style:normal:bg_image')), (0, y))
    for t in c.children:
        px = int(style(t, 'font_size')) if t.type in ('label', 'button') else 0
        if t.type == 'label': s.text(layer, t.x + t.w / 2, y + t.y + t.h / 2, text, px, ink(rgb(style(t, 'text_color'))), anchor='m')
        elif t.type == 'button': s.text(layer, t.x + t.w / 2, y + t.y + t.h / 2, t.get('text'), px, ink(rgb(style(t, 'text_color'))), anchor='m')
        elif t.type == 'slider': draw_slider(layer, t, y, img, value)
        elif t.type == 'view':   # a button's disc: its fill, round (drawn at 4x and reduced for the edge)
            disc = Image.new('RGBA', (t.w * 4, t.h * 4), (0, 0, 0, 0)); fill = style(t, 'bg_color').lstrip('#')
            ImageDraw.Draw(disc).ellipse((0, 0, t.w * 4 - 1, t.h * 4 - 1), fill=ink(rgb(fill)) + (int(fill[6:8], 16),))
            layer.alpha_composite(disc.resize((t.w, t.h), Image.LANCZOS), (t.x, y + t.y))
    if dim: layer.putalpha(layer.getchannel('A').point(lambda a: a * 153 // 255))
    im.alpha_composite(layer)


def draw_volume(s, im, c, y, ink, img, st):
    """The Volume page's card (tools/pod_ui.py cards_volume): the three card pieces, the number (the bold face) and the grey line at the state's 'volnum' / 'volinfo', the - and + discs and buttons, and the slider at the state's 'vol'."""
    if not hasattr(s, 'bold'): s.bold = StbFont(os.path.join(s.tree, RAW, 'fonts/lyrics.ttf'))
    for t in c.children:
        if t.type == 'view' and t.name.startswith('pod_volcard'): im.alpha_composite(img(t.get('style:normal:bg_image')), (0, y + t.y))
        elif t.type == 'view' and t.name != 'pod_volbar':   # a button's disc
            disc = Image.new('RGBA', (t.w * 4, t.h * 4), (0, 0, 0, 0)); fill = style(t, 'bg_color').lstrip('#')
            ImageDraw.Draw(disc).ellipse((0, 0, t.w * 4 - 1, t.h * 4 - 1), fill=ink(rgb(fill)) + (int(fill[6:8], 16),))
            im.alpha_composite(disc.resize((t.w, t.h), Image.LANCZOS), (t.x, y + t.y))
        elif t.name == 'pod_volnum':
            px = int(style(t, 'font_size')); s.bold.draw(im, t.x, int(y + t.y + (t.h - px) / 2), st.get('volnum', '42'), px, ink(rgb(style(t, 'text_color'))) + (255,))
        elif t.name == 'pod_volinfo':
            px = int(style(t, 'font_size')); s.text(im, t.x, y + t.y + t.h / 2, st.get('volinfo', ''), px, ink(rgb(style(t, 'text_color'))))
        elif t.type == 'button':
            px = int(style(t, 'font_size')); s.text(im, t.x + t.w / 2, y + t.y + t.h / 2, t.get('text'), px, ink(rgb(style(t, 'text_color'))), anchor='m')
        elif t.name == 'pod_volbar': draw_volbar(im, t, y, img, ink, st.get('vol', 42), st.get('vmax'))   # (vol_slider is invisible: the bar is the view over it)


def draw_cover(s, im, c, y, ink, img, chosen, name_on=False):
    """The Cover page's card (tools/pod_ui.py cards_cover, patch/plcpage.c pc_paint): the six thumbnails (Albums: a 2 x 2 of sample album colours; the styles from the integer model, tools/pod_plcover.py, over three sample tones, the playlist's seed),
    each with the grid's rounded corners, the ring (pod_covring) round the `chosen` one, and the names under them (white when chosen, grey otherwise)."""
    import pod_plcover as PC, preview_plcover as PP; PI2 = PI
    T, A = 88, PI2.ALBUMS
    tones = [A[0][2], A[7][2], A[6][2]]
    for k in range(6):
        x, ty = 10 + k % 3 * 101, y + k // 3 * 124 + 4
        if k == 0:
            t = Image.new('RGBA', (T, T)); h = T // 2
            for q, a in enumerate((0, 7, 6, 1)): t.paste(A[a][2] + (255,), (q % 2 * h, q // 2 * h, q % 2 * h + h, q // 2 * h + h))
        else: t = PC.to_image(PC.art(k, tones, 20261123, T)).convert('RGBA')
        im.alpha_composite(PI2.rounded(t, 10), (x, ty))
        if k and name_on: PP.put_name(s, im, x, ty, T, 'Road Trip', 14)
        if k == chosen: im.alpha_composite(img('pod_covring'), (x - 4, ty - 4))
    for t in c.children:
        if t.name.startswith('pod_covl'):
            k = int(t.name[8:]); px = int(style(t, 'font_size'))
            s.text(im, t.x + t.w / 2, y + t.y + t.h / 2, s.shown(t), px, ink((255, 255, 255) if k == chosen else rgb(style(t, 'text_color'))), anchor='m')


def VOLUME_STATES(tr):
    """The Volume page's three samples: 42 with Max 80; 6 with Max 80 (the glyph split at the fill's edge, the tick); Bluetooth at 64 (no Max, no tick). Max Volume 80, Equalizer Off."""
    rows = {'pod_value0': '80', 'pod_value1': tr('Off')}
    return [{'volnum': '42', 'volinfo': tr('Headphones') + ' \u00b7 ' + tr('Max') + ' 80', 'vol': 42, 'vmax': 80, 'values': rows},
            {'volnum': '6', 'volinfo': tr('Headphones') + ' \u00b7 ' + tr('Max') + ' 80', 'vol': 6, 'vmax': 80, 'values': rows},
            {'volnum': '64', 'volinfo': tr('Bluetooth'), 'vol': 64, 'vmax': None, 'values': rows}]


def draw_volbar(im, t, y, img, ink, value, vmax):
    """The Volume page's bar (patch/volume.c vp_paint, the same arithmetic): the capsule track, the fill cut straight at the value, the Max tick (vmax: None on Bluetooth or at 100) and the speaker glyph split at the edge."""
    fw = value * t.w // 100
    im.alpha_composite(img('pod_vol_track'), (t.x, y + t.y))
    if fw > 0: im.alpha_composite(img('pod_vol_fill').crop((0, 0, fw, t.h)), (t.x, y + t.y))
    if vmax is not None:
        tx = min(max(vmax * t.w // 100 - 1, 0), t.w - 2)
        ImageDraw.Draw(im).rectangle((t.x + tx, y + t.y + 12, t.x + tx + 1, y + t.y + t.h - 13), fill=ink((0x6A, 0x6A, 0x6E)) + (255,))
    ix, iy = 26 - 12, (t.h - 24) // 2
    cut = min(max(fw - ix, 0), 24)
    ink_g, glyph = img('pod_vol_ink'), img('pod_ci_volume')
    if cut > 0: im.alpha_composite(ink_g.crop((0, 0, cut, 24)), (t.x + ix, y + t.y + iy))
    if cut < 24: im.alpha_composite(glyph.crop((cut, 0, 24, 24)), (t.x + ix + cut, y + t.y + iy))


def draw_centred(s, im, t, y, ink, text=None, font=None):
    """A centred label (a Hero's title and description, a centred note, a big card's text): wrapped by words to the label's width less its 2 px margins, each row centred on the label,
    the first row 2 px under its top, rows font size + 2 px apart (the label paint's pitch: the font size and the style's spacer, docs/modules/addresses.md); font: the face (default: the tree's)."""
    font = font or s.font
    px, rows, line = int(style(t, 'font_size')), [], ''
    for u in WRAP_UNIT.findall(text if text is not None else s.shown(t)):   # a word, or one CJK / Thai character, with the space after it (test/pod/i18n.py's rule)
        if line and font.width((line + u).rstrip(), px) > t.w - 4: rows.append(line.rstrip()); line = u
        else: line += u
    rows.append(line.rstrip())
    top = y + t.y + (2 if style(t, 'text_align_v') == 'top' else (t.h - len(rows) * (px + 2)) / 2)
    for k, r in enumerate(rows):
        font.draw(im, int(t.x + t.w / 2 - font.width(r, px) // 2), int(top + k * (px + 2)), r, px, ink(rgb(style(t, 'text_color'))) + (255,))
    return len(rows)


def draw_hero(s, im, c, y, ink, img):
    """A Hero (tools/pod_ui.py cards_hero): the rounded tile (drawn at 4x and reduced for the edge) with its glyph, the title and the wrapped description, all centred."""
    for t in c.children:
        if t.name == 'pod_hero_tile':
            fill = ink(rgb(style(t, 'bg_color'))); r = int(style(t, 'round_radius'))
            tile = Image.new('RGBA', (t.w * 4, t.h * 4), (0, 0, 0, 0))
            ImageDraw.Draw(tile).rounded_rectangle((0, 0, t.w * 4 - 1, t.h * 4 - 1), r * 4, fill=fill + (255,))
            im.alpha_composite(tile.resize((t.w, t.h), Image.LANCZOS), (t.x, y + t.y))
            for g in t.children: im.alpha_composite(img(g.get('image')), (t.x + g.x, y + t.y + g.y))
        elif t.type == 'label': draw_centred(s, im, t, y, ink)


def draw_bigcard(s, im, c, y, ink, img, values):
    """A BigCard (tools/pod_ui.py cards_bigcard): the tall card piece and its text in the bold face, centred in the card (the payload's text: the state's value of the label)."""
    card = c.children[0]
    im.alpha_composite(img(card.get('style:normal:bg_image')), (0, y))
    for t in card.children:
        if not hasattr(s, 'bold'): s.bold = StbFont(os.path.join(s.tree, RAW, 'fonts/lyrics.ttf'))
        px = int(style(t, 'font_size')); text = values.get(t.name) or s.shown(t)
        s.bold.draw(im, int(t.x + t.w / 2 - s.bold.width(text, px) // 2), int(y + card.y + t.y + (t.h - px) / 2), text, px, ink(rgb(style(t, 'text_color'))) + (255,))


def draw_qr(im, c, y, ink, values):
    """A QrCard as patch/netservice.c wt_qr_paint draws it: the near-white paper, the modules of tools/qr.py's symbol of the big card's address (raw colours, as the payload's), the corners rounded
    in the page's colour (ink: Light Mode flips them with the page)."""
    import qr
    code = c.children[0]; mod, quiet = ST.QR_MOD, ST.QR_QUIET; side = code.w
    ip = (values.get('pod_big0_t') or '').split(':')[0]
    sym = Image.new('RGBA', (side, side), rgb(ST.QR_RGB) + (255,)); d = ImageDraw.Draw(sym)
    for r, row in enumerate(qr.encode(qr.address_text(ip)) or ()):
        for k, v in enumerate(row):
            if v: d.rectangle(((quiet + k) * mod, (quiet + r) * mod, (quiet + k + 1) * mod - 1, (quiet + r + 1) * mod - 1), fill=rgb(ST.QR_DARK_RGB))
    mask = Image.new('L', (side * 4, side * 4), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, side * 4 - 1, side * 4 - 1), ST.QR_R * 4, fill=255)
    sym.putalpha(mask.resize((side, side), Image.LANCZOS))
    under = Image.new('RGBA', (side, side), ink((0, 0, 0)) + (255,)); under.alpha_composite(sym)
    im.alpha_composite(under, (c.x + code.x, y + code.y))


def draw_qrpill(s, im, c, y, ink, img, text=None):
    """A QrPill as patch/netservice.c wt_pill_fit leaves it: as wide as its label needs, centred, the glyph and the grey label centred as a pair on the flat rest-surface pill."""
    b = c.children[0]; text = s.strings.get(text, text) if text else s.shown(b)
    px = ST.PILL_PX; tw = s.font.width(text, px); w = 2 * ST.PILL_PAD + ST.PILL_GLYPH + ST.PILL_GAP + tw; h = ST.PILL_H
    x0, top = ST.CM + ST.CARD_W // 2 - w // 2, y + ST.PILL_Y
    big = Image.new('RGBA', (w * 4, h * 4), (0, 0, 0, 0)); ImageDraw.Draw(big).rounded_rectangle((0, 0, w * 4 - 1, h * 4 - 1), ST.PILL_R * 4, fill=ink(rgb(style(b, 'bg_color'))) + (255,))
    im.alpha_composite(big.resize((w, h), Image.LANCZOS), (x0, top))
    g = img('wt_qr'); im.alpha_composite(g, (x0 + ST.PILL_PAD, top + ST.PILL_DROP + (h - g.height) // 2))   # the margins move the icon square down PILL_DROP, the PNG's clear rows lift the glyph back
    s.text(im, x0 + ST.PILL_PAD + ST.PILL_GLYPH + ST.PILL_GAP, top + h / 2 + ST.PILL_DROP, text, px, ink(rgb(style(b, 'text_color'))))


def draw_text_item(s, im, c, y, ink=lambda c: c, texts=None):
    """A header or a note (a view holding a grey label) at y."""
    shown = lambda t: s.strings.get(texts[t.name], texts[t.name]) if texts and t.name in texts else s.shown(t)   # texts: the notes the payload sets at run time, by widget name
    for t in c.children:   # a header or a note: its grey label
        if c.type == 'view' and t.type == 'hscroll_label':
            px = int(style(t, 'font_size'))
            s.text(im, t.x, y + t.y + t.h / 2, s.clip(shown(t), px, t.w), px, ink(rgb(style(t, 'text_color'))))
        elif c.type == 'view' and t.type == 'label' and style(t, 'text_align_h') == 'center': draw_centred(s, im, t, y, ink)   # a centred note
        elif c.type == 'view' and t.type == 'label':   # a wrapping note: by words, from the top, ST.WRAP_LINE apart
            px, line, k = int(style(t, 'font_size')), '', 0
            for word in shown(t).split():
                if line and s.font.width(line + ' ' + word, px) > t.w: s.text(im, t.x, y + t.y + ST.NOTE_LABEL_H / 2 + k * ST.WRAP_LINE, line, px, ink(rgb(style(t, 'text_color')))); line, k = word, k + 1
                else: line = (line + ' ' + word).strip()
            s.text(im, t.x, y + t.y + ST.NOTE_LABEL_H / 2 + k * ST.WRAP_LINE, line, px, ink(rgb(style(t, 'text_color'))))


def draw_row(s, im, d, row, y, values, switches, shown, ink=lambda c: c, img=None, pal=None, pressed=False):
    img = img or s.img
    piece = img(row.get('style:normal:bg_image') + ('_down' if pressed else ''))   # the row's piece of its card (the pressed twin when pressed)
    im.alpha_composite(piece, (0, y))
    label = next(c for c in row.children if c.name.startswith('pod_label'))
    val = next((c for c in row.children if c.name.startswith('pod_value')), None)
    lab_w = label.w
    if val:   # the payload's value_fit: the text sets its room, the label gets the rest
        text = values.get(val.name) or s.shown(val)
        info = row.get('sensitive') == 'false'   # an About row: 16 px, no chevron, the value ends at the right ink edge
        px, mx = (int(style(val, 'font_size', ST.INFO_PX)), ST.INFO_MAX) if info else (ST.VALUE_PX, ST.VALUE_MAX)   # (an info row's own size: About's 16, the Cover Cache page's 18)
        vw = min(s.font.width(text, px) + 6, mx) if text else 8
        right = val.x + (ST.INFO_W if info else val.w)
        s.text(im, right - 2, y + row.h / 2, text, px, ink(rgb(ST.GREY)), 'r')
        lab_w = right - vw - ST.VALUE_LABEL_GAP - label.x
    for c in row.children:
        if c.type == 'image':
            if c.name.startswith('pod_check') and c.name not in shown: continue
            name = c.get('image')
            if c.name.startswith('pod_switch'): name = 'sset_on' if switches.get(c.name) else 'sset_off'
            g = img(name)
            im.alpha_composite(g, (c.x, y + c.y))
        elif c.name == 'pod_hair':
            d.rectangle((c.x, y + c.y, c.x + c.w - 1, y + c.y), fill=ink(rgb(style(c, 'bg_color'))))
    sub = next((c for c in row.children if c.name.startswith('pod_sub')), None)   # a two line row (the Presets page's files): the name on the first line, the grey line under it
    own = values.get(label.name + '.color') or style(label, 'text_color')   # a label with a colour of its own (the red Sign Out; a page's state may grey it as the payload does)
    s.text(im, label.x, y + (label.y + label.h / 2 if sub else row.h / 2), s.clip(values.get(label.name + '.text') or s.shown(label), int(style(label, 'font_size', 21)), lab_w), int(style(label, 'font_size', 21)), ink(rgb(own) if own else (255, 255, 255)))
    if sub: s.text(im, sub.x, y + sub.y + sub.h / 2, s.clip(s.shown(sub), int(style(sub, 'font_size', 18)), sub.w), int(style(sub, 'font_size', 18)), ink(rgb(style(sub, 'text_color', '#AAAAAA'))))


def draw_covlist(s, title, albums):
    """The plain list of patch/covlist.c (the Albums list mode's rows without the cover: title 21 px white and artist 18 px grey from x 16, a hairline under each, rows 64 px) under the plain navbar."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_covlist.bin'), 'rb').read())
    im = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    if albums:
        for i, (al, ar) in enumerate(albums):
            y = NAV + i * 64
            s.text(im, 16, y + 7 + 12, s.clip(al, 21, 288), 21)
            s.text(im, 16, y + 33 + 10, s.clip(ar, 18, 288), 18, rgb('#AAAAAA'))
            d.rectangle((0, y + 63, W - 1, y + 63), fill=(0x22, 0x22, 0x22))
    else:
        s.text(im, W // 2, 225, s.shown(type('L', (), {'get': lambda self, k: {'tr_text': 'No albums'}.get(k)})()), 20, (255, 255, 255), 'm')
    d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    lt = next(w for w in root.walk() if w.name == 'label_title'); tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, title, tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return im


def draw_lockwall(s, entries=4, chosen=2):
    """Settings > Lock Screen > Wallpaper (patch/lockscreen.c lkwp_*): the widgets of ui/m1plus_lockwall.bin as the payload leaves them. The first cell is the Default wallpaper (the tree's own screensaver_default, scaled as
    AWTK's scale_auto does), the others sample pictures (flat gradients standing for the user's 320 x 480 files); entries: cells shown (the rest stay hidden), chosen: the marked one (its 2 px #FE7E40 border)."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_lockwall.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    covers = by['view_covers']
    for i in range(6):
        c = by[f'imgcover{i}']
        if i >= entries: continue
        x, y = c.x + covers.x, c.y + covers.y
        if i == 0: pic = s.img('screensaver_default').resize((c.w, c.h), Image.LANCZOS)
        else:
            top, bot = [(0x3A, 0x5A, 0x8C), (0x8C, 0x4A, 0x3A), (0x3A, 0x8C, 0x6A), (0x7A, 0x3A, 0x8C)][(i - 1) % 4], (0x10, 0x10, 0x18)
            pic = Image.new('RGBA', (c.w, c.h))
            for r in range(c.h): ImageDraw.Draw(pic).line((0, r, c.w, r), fill=tuple(int(a + (b - a) * r / (c.h - 1)) for a, b in zip(top, bot)) + (255,))
        im.alpha_composite(pic.convert('RGBA'), (x, y))
        if i == chosen: d.rectangle((x, y, x + c.w - 1, y + c.h - 1), outline=rgb('#EEEEEC'), width=2)
        mk = by[f'img_choice{i}']
        im.alpha_composite(s.img('screensaver_selected' if i == chosen else 'screensaver_unselect'), (x + mk.x, y + mk.y))
        if i == 0: ic = by['img_defaulticon']; im.alpha_composite(s.img('screensaver_defaulticon'), (x + ic.x, y + ic.y))
    d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    lt = by['label_title']; tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, s.shown(lt), tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return im


def draw_lockinfo(s):
    """Settings > Lock Screen > Custom Wallpaper: the Release Notes page (ui/m1plus_lockinfo.bin, painter patch/relnotes.c): the 22 px white heading at y 12, then the three paragraphs, 20 px #E6E6E6 on a 27 px
    pitch in x 16, width 288, wrapped by words, a 12 px gap between them (English here)."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_lockinfo.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    px, pitch, y = int(style(by['label_line'], 'font_size')), 27, NAV + 12
    s.text(im, 16, y + 15, 'Add Your Own Pictures', int(style(by['label_head'], 'font_size')))
    y += 30 + 12
    for para in ('Copy pictures to a folder named lockscreenimage at the top level of the card.', 'JPG or PNG, exactly 320 x 480 pixels, under 1 MB each.', 'Up to 5 pictures. Choose one in Wallpaper.'):
        line = ''
        for word in para.split():
            if line and s.font.width(line + ' ' + word, px) > 288: s.text(im, 16, y + pitch / 2, line, px, (230, 230, 230)); line, y = word, y + pitch
            else: line = (line + ' ' + word).strip()
        s.text(im, 16, y + pitch / 2, line, px, (230, 230, 230)); y += pitch + 12
    d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    lt = by['label_title']; tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, s.shown(lt), tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return im


CARDSRC_SAMPLE = ['#!/bin/sh', 'LOG=/mnt/mmc/m1plus-battery.csv', 'while true; do', '  cat /sys/class/power_supply/battery/capacity >> $LOG', '  sleep 60', 'done']
CARDLOG_SAMPLE = ['[probe] battery 87% 4012 mV discharging', 'wlan0 up, backlight 120, PCM idle', 'row 41 written to /mnt/mmc/m1plus-battery.csv'] * 6 + ['done']


def draw_cardlog(s, lines, page='m1plus_cardlog'):
    """Settings > Developer > Tools > Card Script > View Log (ui/m1plus_cardlog.bin, painter patch/relnotes.c): no heading, the text 15 px #E6E6E6 on a 20 px pitch in x 16, width 288 (wrapped by
    words), the end of the log at the bottom of the view, the stock navbar."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', page + '.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    px, pitch = int(style(by['label_line'], 'font_size')), 20
    rows = []
    for para in lines:
        line = ''
        for word in para.split():
            if line and s.font.width(line + ' ' + word, px) > 288: rows.append(line); line = word
            else: line = (line + ' ' + word).strip()
        rows.append(line)
    y = NAV + 12 - max(0, NAV + 12 + len(rows) * pitch + 20 - SCREEN)   # scrolled to the end when it is longer than the view
    for r in rows:
        if y >= NAV: s.text(im, 16, y + pitch / 2, r, px, (230, 230, 230))
        y += pitch
    d.rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    lt = by['label_title']; tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, s.shown(lt), tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return im


def draw_wifi(s, on=True, nets=(), scanning=True, joining=False, scroll=0):
    """Settings > Wi-Fi (patch/wifipage.c, docs/modules/wifi.md): the widgets of ui/m1plus_wifi.bin as the payload lays them out. nets: (name, level 0..4, secured, saved, connected) in the page's order (the
    connected one first). The first group is the switch row (and the connected network under it), My Networks the saved ones, Networks the others and Other...; a row's picture piece, hairline and glyphs are
    the payload's (wp_layout). joining: the connected row shows a spinner frame instead of the check. scroll: pixels the list is scrolled."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_wifi.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, 900), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    grey = rgb(ST.GREY)
    cur = [n for n in nets if on and n[4]][:1]
    mine = [n for n in nets if on and n[3] and not n[4]]
    others = [n for n in nets if on and not n[3] and not n[4]]
    def piece(i, n): return 'single' if n == 1 else 'top' if i == 0 else 'bot' if i == n - 1 else 'mid'
    def row(y, p, hair):
        im.alpha_composite(s.img(f'pod_cd_{p}'), (0, y))
        if hair: d.rectangle((24, y + 51, 309, y + 51), fill=rgb(ST.CARD_HAIR_RGB))
    def label(name, y, text=None, px=21):
        w = by[name]; s.text(im, w.x + 2, y + ST.ROW_H / 2, s.clip(text or s.shown(w), px, w.w - 4), px)
    def net(k, y, n, p, hair):
        name, level, secured, saved, conn = n
        row(y, p, hair)
        w = by['wf_name0']; s.text(im, w.x + 2, y + ST.ROW_H / 2, s.clip(name, 21, w.w - 4), 21)
        if conn: im.alpha_composite(s.img('wf_spin1' if joining else 'pod_check'), (by['wf_chk0'].x + (3 if joining else 0), y + by['wf_chk0'].y + (3 if joining else 0)))
        if secured: im.alpha_composite(s.img('wf_lock'), (by['wf_lock0'].x, y + by['wf_lock0'].y))
        im.alpha_composite(s.img(f'wf_sig{[0, 1, 1, 2, 3][level]}'), (by['wf_sig0'].x, y + by['wf_sig0'].y))
        im.alpha_composite(s.img('wf_info'), (by['wf_info0'].x, y + by['wf_info0'].y))
    def header(name, y, spinner=False):
        t = by[name + '_t']; px = int(style(t, 'font_size'))
        s.text(im, t.x + 2, y + t.y + t.h / 2, s.shown(t), px, grey)
        if spinner: im.alpha_composite(s.img('wf_spin2'), (t.x + 2 + s.font.width(s.shown(t), px) + 8, y + by['wf_hdr_net_spin'].y))
    y = ST.CM
    row(y, 'top' if cur else 'single', bool(cur))
    label('wf_sw_label', y); im.alpha_composite(s.img('sset_on' if on else 'sset_off'), (by['wf_sw_img'].x, y + by['wf_sw_img'].y)); y += ST.ROW_H
    if cur: net(0, y, cur[0], 'bot', False); y += ST.ROW_H
    if on:
        if mine:
            header('wf_hdr_my', y); y += ST.HDR_H
            for i, n in enumerate(mine): net(1 + i, y, n, piece(i, len(mine)), i < len(mine) - 1); y += ST.ROW_H
        header('wf_hdr_net', y, scanning); y += ST.HDR_H
        for i, n in enumerate(others): net(17 + i, y, n, piece(i, len(others) + 1), True); y += ST.ROW_H
        row(y, piece(len(others), len(others) + 1), False); label('wf_other_label', y, None); y += ST.ROW_H
    y += ST.END_H
    out = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); out.alpha_composite(im.crop((0, scroll, W, scroll + SCREEN - NAV)), (0, NAV))
    d = ImageDraw.Draw(out)
    lt = by['label_title']; tpx = PI.title_px(s.tree)
    s.text(out, lt.x, NAV / 2, s.shown(lt), tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); out.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return out


def draw_wifiinfo(s, title, fields, saved=True, auto=True):
    """One network's info page (patch/wifipage.c wi_layout, docs/modules/wifi.md): the widgets of ui/m1plus_wifiinfo.bin as the payload lays them out. fields: (label, value) of the info card; saved: Forget This
    Network on top and Auto-Join (on / off by auto) under the card, else Join under it. Pieces, hairlines and gaps are the payload's."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_wifiinfo.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, 900), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    grey = rgb(ST.GREY)
    def piece(i, n): return 'single' if n == 1 else 'top' if i == 0 else 'bot' if i == n - 1 else 'mid'
    def row(y, p, hair):
        im.alpha_composite(s.img(f'pod_cd_{p}'), (0, y))
        if hair: d.rectangle((24, y + 51, 309, y + 51), fill=rgb(ST.CARD_HAIR_RGB))
    def centred(name, y):
        w = by[name]; s.text(im, w.x + w.w // 2, y + ST.ROW_H / 2, s.shown(w), 21, (255, 255, 255), 'm')
    y = ST.CM
    lt = by['label_title']; tpx = PI.title_px(s.tree); cut = s.clip(title, tpx, lt.w)
    if cut != title:   # wi_name: the whole name in one grey line, or two (broken at a space in the first line's second half, else at the last character that fits)
        nl = by['wi_name0']; npx = int(nl.get('style:normal:font_size')); lines = [title]
        if s.font.width(title, npx) > nl.w:
            lo = max(k for k in range(1, len(title)) if k == 1 or s.font.width(title[:k], npx) <= nl.w)
            sp = title.rfind(' ', lo // 2 + 1, lo + 1)
            lines = [title[:sp], s.clip(title[sp + 1:], npx, nl.w)] if sp > 0 else [title[:lo], s.clip(title[lo:], npx, nl.w)]
        for t in lines:
            s.text(im, nl.x + nl.w // 2, y + nl.h / 2, t, npx, grey, 'm'); y += nl.h
        y += 8   # patch/wifipage.c WI_NAME_GAP
    if saved:
        row(y, 'single', False); centred('wi_forget_t', y); y += ST.ROW_H + ST.GAP_H
    for i, (lab, val) in enumerate(fields):
        row(y, piece(i, len(fields)), i < len(fields) - 1)
        s.text(im, by['wi_fl0'].x + 2, y + ST.ROW_H / 2, lab, 21)
        s.text(im, by['wi_fv0'].x + by['wi_fv0'].w - 2, y + ST.ROW_H / 2, val, 18, grey, 'r')
        y += ST.ROW_H
    y += ST.GAP_H
    row(y, 'single', False)
    if saved:
        s.text(im, by['wi_auto_t'].x + 2, y + ST.ROW_H / 2, s.shown(by['wi_auto_t']), 21)
        im.alpha_composite(s.img('sset_on' if auto else 'sset_off'), (by['wi_auto_img'].x, y + by['wi_auto_img'].y))
    else:
        centred('wi_join_t', y)
    out = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); out.alpha_composite(im.crop((0, 0, W, SCREEN - NAV)), (0, NAV))
    s.text(out, lt.x, NAV / 2, cut, tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); out.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return out


def draw_wifisec(s):
    """The Security picker of the Join Wi-Fi Network page (patch/wifipage.c ws_open): the widgets of ui/m1plus_wifisec.bin, the check on the default row."""
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_wifisec.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    y = NAV + ST.CM
    for k in range(3):
        r = by[f'ws_row{k}']
        im.alpha_composite(s.img(r.get('style:normal:bg_image')), (0, y))
        l = by[f'ws_label{k}']; s.text(im, l.x + 2, y + ST.ROW_H / 2, s.shown(l), 21)
        c = by[f'ws_check{k}']
        if c.get('visible') != 'false': im.alpha_composite(s.img(c.get('image')), (c.x, y + c.y))
        if k < 2: d.rectangle((l.x, y + 51, 309, y + 51), fill=rgb(ST.CARD_HAIR_RGB))
        y += ST.ROW_H
    lt = by['label_title']; tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, s.shown(lt), tpx)
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):
        g = s.img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    return im


def sheet(panels, path):
    pad = 14
    wid = sum(im.width for _, im in panels) + pad * (len(panels) + 1)
    hei = max(im.height for _, im in panels) + 44 + pad
    out = Image.new('RGB', (wid, hei), (0x2A,) * 3); d = ImageDraw.Draw(out)
    x = pad
    for title, im in panels:
        d.text((x, 22), title, fill=(0xCC,) * 3, font=PI.ANN); out.paste(im.convert('RGB'), (x, 44)); x += im.width + pad
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.save(path, optimize=True); print('wrote', path, out.size)


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    s = PI.Side(sys.argv[1], True, 'en_US'); s.mark = lambda *a: None
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(build.ROOT, 'out', 'preview', 'settings-mock-3.png')
    sheet([('Settings, first screen', draw_page(s, 'm1plus_settings')),
           ('Settings, whole list (red = screen bottom)', draw_page(s, 'm1plus_settings', full=True)),
           ('Settings > Home Screen', draw_page(s, 'm1plus_homeset')),
           ('Settings > Library', draw_page(s, 'm1plus_library')),
           ('Settings > Library, whole list', draw_page(s, 'm1plus_library', full=True)),
           ('Settings > Now Playing', draw_page(s, 'm1plus_npset')),
           ('Settings > Now Playing > Theme', draw_page(s, 'm1plus_tapetheme')),
           ('Settings > Developer', draw_page(s, 'm1plus_developer')),
           ('Settings > Developer > Cache', draw_page(s, 'm1plus_cache')),
           ('Cache > Missing',draw_covlist(s, 'Missing Covers', [('Kind of Blue', 'Miles Davis'), ('Music Has the Right to Children', 'Boards of Canada'), ('Homogenic', 'Björk'), ('Selected Ambient Works 85-92', 'Aphex Twin'), ('Dummy', 'Portishead'), ('Blue in Green (Remastered, Mono Version)', 'Miles Davis'), ('Mezzanine', 'Massive Attack')])),
           ('Cache > No art', draw_covlist(s, 'No Art', [('Pastel Blues', 'Nina Simone'), ('Kid A', 'Radiohead')])),
           ('Cache > empty',draw_covlist(s, 'No Art', [])),
           ('Settings > General', draw_page(s, 'm1plus_general')),
           ('Settings > General > Keyboards', draw_page(s, 'm1plus_keyboards')),
           ('Settings > General > About (first screen)', draw_page(s, 'm1plus_about')),
           ('Settings > Wi-Fi', draw_wifi(s, True, WIFI_NETS)),
           ('Settings > Wi-Fi, scrolled', draw_wifi(s, True, WIFI_NETS, scroll=116)),
           ('Settings > Wi-Fi, long names', draw_wifi(s, True, [('TwentyCharactersLong 5G', 4, True, True, True), ('A very long network name of 32 b', 3, True, True, False), ('一个很长的无线网络名字', 3, True, False, False)] + WIFI_NETS[3:])),
           ('Settings > Wi-Fi, joining', draw_wifi(s, True, WIFI_NETS, scanning=False, joining=True)),
           ('Settings > Wi-Fi, off', draw_wifi(s, False)),
           ('Wi-Fi > info (saved)', draw_wifiinfo(s, 'Studio', [('Security', 'WPA2/WPA3')])),
           ('Wi-Fi > info (connected)', draw_wifiinfo(s, 'Home', [('Security', 'WPA/WPA2'), ('IP Address', '192.168.1.42'), ('Router', '192.168.1.1')], auto=False)),
           ('Wi-Fi > info (not saved)', draw_wifiinfo(s, 'Cafe Open', [('Security', 'Open')], saved=False)),
           ('Wi-Fi > info (long name)', draw_wifiinfo(s, 'TwentyCharactersLong 5G', [('Security', 'WPA2')])),
           ('Wi-Fi > info (longest name)', draw_wifiinfo(s, 'A very long network name of 32 b', [('Security', 'WPA2')], saved=False)),
           ('Wi-Fi > Join Wi-Fi Network > Security', draw_wifisec(s)),
           ('Settings > Appearance', draw_page(s, 'm1plus_appearance')),
           ('Settings > Appearance > Accent', draw_page(s, 'm1plus_accent')),
           ('Settings > Appearance > Background', draw_page(s, 'm1plus_background')),
           ('Settings > Appearance > Lock Screen', draw_page(s, 'm1plus_lockscreen')),
           ('Settings > Lock Screen > Player Style', draw_page(s, 'm1plus_lockstyle')),
           ('Settings > Lock Screen > Wallpaper', draw_lockwall(s)),
           ('Settings > Lock Screen > Custom Wallpaper', draw_lockinfo(s)),
           ('Card Script > View Log', draw_cardlog(s, CARDLOG_SAMPLE)),
           ('Card Script > View Script', draw_cardlog(s, CARDSRC_SAMPLE, 'm1plus_cardsrc')),
           ('Wallpaper, Default only (empty folder)', draw_lockwall(s, entries=1, chosen=0)),
           ('Settings > Battery', draw_page(s, 'm1plus_battery')),
           ('Settings > Battery > Charge Limit', draw_page(s, 'm1plus_chargelimit')),
           ('Settings > Display', draw_page(s, 'm1plus_display')),
           ('Settings > Display > Screen Timeout', draw_page(s, 'm1plus_lighttime')),
           ('Settings > Display > LED Light', draw_page(s, 'm1plus_ledlight')),
           ('Settings > Buttons & Power', draw_page(s, 'm1plus_keyspower')),
           ('Buttons & Power > Button Lock', draw_page(s, 'm1plus_keylock')),
           ('Buttons & Power > Auto-Shutdown', draw_page(s, 'm1plus_shutdown')),
           ('Settings > Playback > Continue Playing', draw_page(s, 'm1plus_nextalbum')),
           ], out)
    # Buttons & Power (docs/modules/keyspower.md): the Settings list with the new System row, the page and its two pickers, in English and in two long languages (out/preview/keyspower/)
    for loc, tag in (('en_US', 'en'), ('ge_DE', 'de'), ('ru_RU', 'ru')):
        t = PI.Side(sys.argv[1], True, loc); t.mark = lambda *a: None
        tr = lambda k: t.strings.get(k, k)
        sheet([('Settings, whole list', draw_page(t, 'm1plus_settings', full=True)),
               ('Buttons & Power', draw_page(t, 'm1plus_keyspower', state={'values': {'pod_value0': tr('Both'), 'pod_value3': '5min'}, 'switches': {'pod_switch1': True}})),
               ('Button Lock', draw_page(t, 'm1plus_keylock')),
               ('Auto-Shutdown', draw_page(t, 'm1plus_shutdown'))], os.path.join(os.path.dirname(out), 'keyspower', f'keyspower-{tag}.png'))
    # Playback Settings (docs/modules/playset.md): the Settings list, the page (whole) and three of its pickers, in English and in two long languages (out/preview/playset/)
    for loc, tag in (('en_US', 'en'), ('ge_DE', 'de'), ('ru_RU', 'ru')):
        t = PI.Side(sys.argv[1], True, loc); t.mark = lambda *a: None
        tr = lambda k: t.strings.get(k, k)
        sheet([('Settings, whole list', draw_page(t, 'm1plus_settings', full=True, state={'values': {'pod_value0': tr('Off'), 'pod_value1': tr('Off'), 'pod_value5': tr('Rock')}})),
               ('Playback', draw_page(t, 'm1plus_playset', full=True, state={'values': {'pod_value0': tr('Repeat All'), 'pod_value1': tr('Off'), 'pod_value3': tr('Location'), 'pod_value5': '5 s'}, 'switches': {'pod_switch2': True, 'pod_switch4': False}})),
               ('Crossfade, on', draw_page(t, 'm1plus_psxfade', full=True, state={**XFADE_ON, 'xf_text': '5 ' + tr('seconds')})),
               ('Crossfade, 1 second', draw_page(t, 'm1plus_psxfade', full=True, state={**XFADE_ON, 'vol': 1, 'xf_text': '1 ' + tr('second')})),
               ('Crossfade, off', draw_page(t, 'm1plus_psxfade', full=True, state=XFADE_OFF)),
               ('Volume & Sound', draw_page(t, 'm1plus_psvolume', full=True, state={'values': {'pod_value0': tr('Low'), 'pod_value1': '80', 'pod_value2': tr('Memory'), 'pod_value3': tr('Off'), 'pod_value4': 'L3', 'pod_value6': tr('Medium')}, 'switches': {'pod_switch5': True}})),
               ('Output', draw_page(t, 'm1plus_psoutput', full=True, state={'values': {'pod_value1': tr('D2P'), 'pod_value3': tr('Variable')}, 'switches': {'pod_switch4': False}})),
               ('Max Volume', draw_page(t, 'm1plus_psmaxvol', state={'vol_text': '80', 'vol': 80})),
               ('Volume (status bar tap): 42, Max 80', draw_page(t, 'm1plus_volume', full=True, state=VOLUME_STATES(tr)[0])),
               ('Volume: 6, Max 80 (low fill)', draw_page(t, 'm1plus_volume', full=True, state=VOLUME_STATES(tr)[1])),
               ('Playlist Cover: Sunburst', draw_page(t, 'm1plus_plcover', full=True, state={'cover': 3, 'switches': {'pod_switch0': True}})),
               ('Playlist Cover: Albums (Name on Cover dimmed)', draw_page(t, 'm1plus_plcover', full=True, state={'cover': 0, 'switches': {'pod_switch0': False}, 'pod_label0.color': '#606060'})),
               ('Volume: Bluetooth, no Max', draw_page(t, 'm1plus_volume', full=True, state=VOLUME_STATES(tr)[2])),
               ('Default Volume (Volume Memory off)', draw_page(t, 'm1plus_psbootvol', state={'vol_text': '30', 'vol': 30, 'switches': {'pod_switch0': False}})),
               ('Default Volume (Volume Memory on)', draw_page(t, 'm1plus_psbootvol', state={'vol_text': '30', 'vol': 30, 'vol_dim': True, 'switches': {'pod_switch0': True}})),
               ('Channel Balance', draw_page(t, 'm1plus_psbal', state={'vol_text': 'L3', 'vol': 7})),
               ('Crossfeed', draw_page(t, 'm1plus_psxfeed', state={'shown': {'pod_check2'}})),
               ('Play Mode', draw_page(t, 'm1plus_psmode'))], os.path.join(os.path.dirname(out), 'playset', f'playset-{tag}.png'))
    # LED Light with Dynamic chosen, and the Theme page with one theme of each palette group (docs/modules/display.md "Sample Rate"; the note under Theme's title is set at run time: the preview sets it the same way) (out/preview/rgb/)
    for loc, tag in (('en_US', 'en'), ('zh_CN', 'zh_CN'), ('ge_DE', 'de')):
        t = PI.Side(sys.argv[1], True, loc); t.mark = lambda *a: None
        tr = lambda k: t.strings.get(k, k)
        led = {'shown': {'pod_check3'}, 'values': {'pod_value5': tr('Reference')}, 'switches': {'pod_switch4': True}}
        theme = lambda note, at: {'shown': {f'pod_check{at}'}, 'texts': {'pod_note0_t': note}}
        sheet([('LED Light, Dynamic', draw_page(t, 'm1plus_ledlight', state=led)),
               ('Theme: Reference', draw_page(t, 'm1plus_rgbtheme', full=True, state=theme('Red to blue to green as the sample rate rises', 2))),
               ('Theme: Heartbeat', draw_page(t, 'm1plus_rgbtheme', full=True, state=theme('Rose to lavender to lime as the sample rate rises', 4))),
               ('Theme: Candle', draw_page(t, 'm1plus_rgbtheme', full=True, state=theme('Warm amber, the same for every file', 0)))], os.path.join(os.path.dirname(out), 'rgb', f'rgb-{tag}.png'))
    # The pages of the second stock-settings round (docs/modules/settings.md): System list, Sleep Timer (off, running), Language, Display, Buttons & Power, Date & Time and its pickers (out/preview/stock2/)
    dim = {'pod_label2.color': '#606060', 'pod_label3.color': '#606060'}   # Set Automatically on: Date and Time dimmed (approximate grey)
    on = {'values': {'pod_value1': 'Auckland', 'pod_value2': '2026-11-15', 'pod_value3': '14:05', **dim}, 'switches': {'pod_switch0': True, 'pod_switch4': True}}
    run = {'shown': {'pod_check3'}, 'values': {'pod_value7': '0:23'}}
    s2 = os.path.join(os.path.dirname(out), 'stock2')
    for name, im in (('settings', draw_page(s, 'm1plus_settings', full=True)), ('general', draw_page(s, 'm1plus_general', full=True)), ('developer', draw_page(s, 'm1plus_developer', full=True)), ('sleeptimer-off', draw_page(s, 'm1plus_sleeptimer', full=True)), ('sleeptimer-running', draw_page(s, 'm1plus_sleeptimer', full=True, state=run)),
                     ('language', draw_page(s, 'm1plus_language', full=True)), ('display', draw_page(s, 'm1plus_display')), ('keyspower', draw_page(s, 'm1plus_keyspower', full=True)),
                     ('datetime-manual', draw_page(s, 'm1plus_datetime')), ('datetime-auto', draw_page(s, 'm1plus_datetime', state=on)), ('timezone', draw_page(s, 'm1plus_timezone', state={'shown': {'pod_check0'}})),
                     ('dtdate', draw_page(s, 'm1plus_dtdate', state={'values': {'pod_value0': '2026', 'pod_value1': '11', 'pod_value2': '15'}})),
                     ('dttime', draw_page(s, 'm1plus_dttime', state={'values': {'pod_value0': '14', 'pod_value1': '05'}})), ('dtyear', draw_page(s, 'm1plus_dtyear', state={'shown': {'pod_check4'}})),
                     ('playset', draw_page(s, 'm1plus_playset', full=True)), ('psvolume', draw_page(s, 'm1plus_psvolume', full=True)), ('psoutput', draw_page(s, 'm1plus_psoutput', full=True)), ('library', draw_page(s, 'm1plus_library', full=True)), ('libupdate', draw_page(s, 'm1plus_libupdate', full=True)), ('cardrun', draw_page(s, 'm1plus_cardrun', full=True)), ('cardrun-running', draw_page(s, 'm1plus_cardrun', full=True, state={'values': {'pod_value0': 'Running 0:12', 'pod_label1.text': 'Stop'}})), ('cardlog', draw_cardlog(s, CARDLOG_SAMPLE)), ('cardsrc', draw_cardlog(s, CARDSRC_SAMPLE, 'm1plus_cardsrc')), ('netservice', draw_page(s, 'm1plus_netservice', full=True, state={'switches': {'pod_switch0': True}})), ('wifitransfer', draw_page(s, 'm1plus_wifitransfer', full=True, state=WT_STATE)), ('wifitransfer-qr', draw_page(s, 'm1plus_wifitransfer', full=True, state=WT_QR_STATE))):
        os.makedirs(s2, exist_ok=True); im.save(os.path.join(s2, name + '.png')); print('wrote', os.path.join(s2, name + '.png'))
    for loc, tag in (('ge_DE', 'de'), ('ru_RU', 'ru'), ('zh_CN', 'zh'), ('th_TH', 'th'), ('fr_FR', 'fr')):   # the Wi-Fi Transfer page in the long languages (out/preview/stock2/wifitransfer-<tag>.png)
        t = PI.Side(sys.argv[1], True, loc); t.mark = lambda *a: None
        draw_page(t, 'm1plus_wifitransfer', full=True, state=WT_STATE).save(os.path.join(s2, f'wifitransfer-{tag}.png')); print('wrote', os.path.join(s2, f'wifitransfer-{tag}.png'))
        draw_page(t, 'm1plus_wifitransfer', full=True, state=WT_QR_STATE).save(os.path.join(s2, f'wifitransfer-qr-{tag}.png'))   # the pill's longer label
        draw_page(t, 'm1plus_general', full=True).save(os.path.join(s2, f'general-{tag}.png')); print('wrote', os.path.join(s2, f'general-{tag}.png'))   # General's labels
    # Light Mode (docs/modules/accent.md): the same pages with the hooks' colours and images (tools/palette.py); the Settings page with Light Mode On, and the picker
    lit = os.path.join(os.path.dirname(out), 'settings-light.png')
    sheet([('Light Mode: Settings, first screen', draw_page(s, 'm1plus_settings', lit=True)),
           ('Settings, whole list', draw_page(s, 'm1plus_settings', full=True, lit=True)),
           ('Settings > Appearance > Background', draw_page(s, 'm1plus_background', lit=True)),
           ('Settings > Home Screen', draw_page(s, 'm1plus_homeset', lit=True)),
           ('Settings > Library', draw_page(s, 'm1plus_library', lit=True)),
           ('Settings > General > Keyboards', draw_page(s, 'm1plus_keyboards', lit=True)),
           ('Settings > General > About (first screen)', draw_page(s, 'm1plus_about', lit=True)),
           ], lit)


if __name__ == '__main__':
    main()
