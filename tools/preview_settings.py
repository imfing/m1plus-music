#!/usr/bin/env python3
"""The Settings pages (iOS style grouped cards, docs/modules/settings.md "Cards"), drawn from the built tree's own ui assets: the cards, rows, glyphs, hairlines, headers and notes are the
widgets tools/pod_ui.py build_cards_page made from the numbers of tools/pod_settings.py (shared with the tests), with the font, images and navbar of the tree. A value takes the room its text
needs and the row's label gets the rest, as patch/m1plus.c value_fit does. Approximate (PIL, not AWTK); the sample state (values, switches, checks) is what a typical device shows.

  out/preview/settings-mock-3.png   Settings (first screen and whole list), Home Screen, Library, Now Playing, Theme, Developer, Keyboards, About

Usage: uv run python -I tools/preview_settings.py WORKDIR [OUT.png]     (en_US; WORKDIR e.g. work/mod-release after a build)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
import awtk_ui, build, palette, preview_icons as PI, pod_settings as ST

W, NAV, SCREEN = 320, 50, 450
RAW = PI.RAW

# What a typical device shows: widget name -> text (values), name -> on (switches), name -> shown (checks, the hidden card), per page key.
STATE = {
    'm1plus_settings': {'values': {'pod_value0': 'Off', 'pod_value1': 'Off', 'pod_value5': 'Repeat All', 'pod_value6': 'Off', 'pod_value7': 'Off'}},
    'm1plus_appearance': {'values': {'pod_value0': 'Neutral'}},
    'm1plus_background': {'shown': {'pod_check1'}},
    'm1plus_accent': {'shown': {'pod_check0'}},
    'm1plus_battery': {'values': {'pod_value1': '80%'}, 'switches': {'pod_switch0': True}},
    'm1plus_chargelimit': {'shown': {'pod_check0'}},
    'm1plus_nextalbum': {'shown': {'pod_check0'}},
    'm1plus_lockscreen': {'switches': {'pod_switch0': True, 'pod_switch2': True}, 'values': {'pod_value3': 'Large Cover'}},
    'm1plus_lockstyle': {'shown': {'pod_check0'}},
    'm1plus_homeset': {'switches': {'pod_switch0': True, 'pod_switch1': True}},
    'm1plus_library': {'switches': {'pod_switch2': True, 'pod_switch3': True, 'pod_switch4': False}},
    'm1plus_npset': {'values': {'pod_value0': 'Chrome'}},
    'm1plus_tapetheme': {'shown': {'pod_check1'}},
    'm1plus_developer': {'switches': {'pod_switch0': True}},
    'm1plus_about': {'values': {'pod_value0': 'V2.1pM', 'pod_value1': 'V2.1', 'pod_value2': 'Shanling M1 Plus', 'pod_value3': 'M1P2305A01234', 'pod_value4': '98:b3:ec:4a:7c:1e',
                                'pod_value5': '192.168.1.42', 'pod_value6': '119.25 GB', 'pod_value7': '87.41 GB'}},
    'm1plus_keyboards': {'switches': {'pod_switch0': True, 'pod_switch1': False}},
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
    pal: an optional palette object (tools/preview_accent.py: .ink(rgb), .image(side, name), .base): every colour and image goes through the model of tools/palette.py as the hooks
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
    kids = [c for c in sv.children if c.name not in hidden and c.get('visible') != 'false']   # the list_view layouter stacks the visible children (it ignores their y)
    end = sum(c.h for c in kids)
    base = ink((0, 0, 0))
    im = Image.new('RGBA', (W, max(SCREEN, NAV + end) if full else SCREEN), base + (255,)); d = ImageDraw.Draw(im)
    y = NAV
    for c in kids:
        if c.type == 'list_item':
            lab = next(t for t in c.children if t.name.startswith('pod_label'))
            draw_row(s, im, d, c, y, values, switches, shown, ink, img, pal, pal is not None and pressed is not None and s.shown(lab) == pressed)
        draw_text_item(s, im, c, y, ink)
        y += c.h
    d.rectangle((0, 0, W - 1, NAV - 1), fill=base)   # the list is under the navbar: it clips at its top
    lt = next(w for w in root.walk() if w.name == 'label_title'); tpx = PI.title_px(s.tree)
    s.text(im, lt.x, NAV / 2, s.clip(s.shown(lt), tpx, lt.w), tpx, ink((255, 255, 255)))
    for name, bx, bw in (('ah_nav_back', 7, 44), ('ah_nav_np', 260, 60)):   # the glass navbar: Back (7, 0, 44, 50), Now Playing's round glass (260, 0, 60, 50)
        g = img(name); im.alpha_composite(g, (bx + (bw - g.width) // 2, (NAV - g.height) // 2))
    if full and im.height > SCREEN:
        for x in range(0, W, 8): d.line((x, SCREEN, x + 3, SCREEN), fill=(0xFF, 0x50, 0x50))
    return im


def draw_text_item(s, im, c, y, ink=lambda c: c):
    """A header or a note (a view holding a grey label) at y."""
    for t in c.children:   # a header or a note: its grey label
        if c.type == 'view' and t.type == 'hscroll_label':
            px = int(style(t, 'font_size'))
            s.text(im, t.x, y + t.y + t.h / 2, s.clip(s.shown(t), px, t.w), px, ink(rgb(style(t, 'text_color'))))
        elif c.type == 'view' and t.type == 'label':   # a wrapping note: by words, from the top, ST.WRAP_LINE apart
            px, line, k = int(style(t, 'font_size')), '', 0
            for word in s.shown(t).split():
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
    s.text(im, label.x, y + (label.y + label.h / 2 if sub else row.h / 2), s.clip(s.shown(label), 21, lab_w), 21, ink((255, 255, 255)))
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
        if conn: im.alpha_composite(s.img('wf_spin1' if joining else 'wf_check'), (by['wf_chk0'].x + (3 if joining else 0), y + by['wf_chk0'].y + (3 if joining else 0)))
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
    lt = by['label_title']; tpx = PI.title_px(s.tree)
    s.text(out, lt.x, NAV / 2, title, tpx)
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
           ('Settings > Now Playing', draw_page(s, 'm1plus_npset')),
           ('Settings > Now Playing > Theme', draw_page(s, 'm1plus_tapetheme')),
           ('Settings > Developer', draw_page(s, 'm1plus_developer')),
           ('Settings > Developer > Cache', draw_page(s, 'm1plus_cache')),
           ('Cache > Missing',draw_covlist(s, 'Missing Covers', [('Kind of Blue', 'Miles Davis'), ('Music Has the Right to Children', 'Boards of Canada'), ('Homogenic', 'Björk'), ('Selected Ambient Works 85-92', 'Aphex Twin'), ('Dummy', 'Portishead'), ('Blue in Green (Remastered, Mono Version)', 'Miles Davis'), ('Mezzanine', 'Massive Attack')])),
           ('Cache > No art', draw_covlist(s, 'No Art', [('Pastel Blues', 'Nina Simone'), ('Kid A', 'Radiohead')])),
           ('Cache > empty',draw_covlist(s, 'No Art', [])),
           ('Settings > Keyboards', draw_page(s, 'm1plus_keyboards')),
           ('Settings > About (first screen)', draw_page(s, 'm1plus_about')),
           ('Settings > Wi-Fi', draw_wifi(s, True, WIFI_NETS)),
           ('Settings > Wi-Fi, scrolled', draw_wifi(s, True, WIFI_NETS, scroll=116)),
           ('Settings > Wi-Fi, joining', draw_wifi(s, True, WIFI_NETS, scanning=False, joining=True)),
           ('Settings > Wi-Fi, off', draw_wifi(s, False)),
           ('Wi-Fi > info (saved)', draw_wifiinfo(s, 'Studio', [('Security', 'WPA2/WPA3')])),
           ('Wi-Fi > info (connected)', draw_wifiinfo(s, 'Home', [('Security', 'WPA/WPA2'), ('IP Address', '192.168.1.42'), ('Router', '192.168.1.1')], auto=False)),
           ('Wi-Fi > info (not saved)', draw_wifiinfo(s, 'Cafe Open', [('Security', 'Open')], saved=False)),
           ('Wi-Fi > Join Wi-Fi Network > Security', draw_wifisec(s)),
           ('Settings > Appearance', draw_page(s, 'm1plus_appearance')),
           ('Settings > Appearance > Accent', draw_page(s, 'm1plus_accent')),
           ('Settings > Appearance > Background', draw_page(s, 'm1plus_background')),
           ('Settings > Appearance > Lock Screen', draw_page(s, 'm1plus_lockscreen')),
           ('Settings > Lock Screen > Player Style', draw_page(s, 'm1plus_lockstyle')),
           ('Settings > Lock Screen > Wallpaper', draw_lockwall(s)),
           ('Settings > Lock Screen > Custom Wallpaper', draw_lockinfo(s)),
           ('Wallpaper, Default only (empty folder)', draw_lockwall(s, entries=1, chosen=0)),
           ('Settings > Battery', draw_page(s, 'm1plus_battery')),
           ('Settings > Battery > Charge Limit', draw_page(s, 'm1plus_chargelimit')),
           ('Settings > Playback > Continue Playing', draw_page(s, 'm1plus_nextalbum')),
           ], out)
    # Light Mode (docs/modules/accent.md): the same pages with the hooks' colours and images (tools/palette.py); the Settings page with Light Mode On, and the picker
    lit = os.path.join(os.path.dirname(out), 'settings-light.png')
    sheet([('Light Mode: Settings, first screen', draw_page(s, 'm1plus_settings', lit=True)),
           ('Settings, whole list', draw_page(s, 'm1plus_settings', full=True, lit=True)),
           ('Settings > Appearance > Background', draw_page(s, 'm1plus_background', lit=True)),
           ('Settings > Home Screen', draw_page(s, 'm1plus_homeset', lit=True)),
           ('Settings > Library', draw_page(s, 'm1plus_library', lit=True)),
           ('Settings > Keyboards', draw_page(s, 'm1plus_keyboards', lit=True)),
           ('Settings > About (first screen)', draw_page(s, 'm1plus_about', lit=True)),
           ], lit)


if __name__ == '__main__':
    main()
