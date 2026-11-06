#!/usr/bin/env python3
"""out/preview/icons.png: the icon set before (the stock tree) and after (the release tree), 1:1 device pixels, with a
3x zoom strip. Markers on the "after" side: blue C = custom Tabler-style SVG, orange K = stock image kept.

  preview_icons.py BEFORE_TREE AFTER_TREE OUT.png        (unpacked work trees; venv python)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
import mod_icons as M
import awtk_strings
from stb_raster import StbFont

from awtk_ui import RAW
W, BAR = 320, 30
WHITE = (255, 255, 255)
ANN = ImageFont.load_default(13); ANN_B = ImageFont.load_default(16)

class Side:
    def __init__(self, tree, after, locale='en_US'):
        self.tree = tree; self.d = os.path.join(tree, RAW, 'images/xx'); self.after = after
        self.font = StbFont(os.path.join(tree, RAW, 'fonts/default.ttf'))
        self.strings = dict(awtk_strings.load(os.path.join(tree, RAW, 'strings', locale + '.bin')))   # the language shown (a strings table name)
    def shown(self, w):
        """The text of an asset widget as the app shows it: its tr_text key through the language's table (the key itself
        when the table lacks it, as locale_info_tr does), else its text."""
        k = w.get('tr_text')
        return self.strings.get(k, k) if k is not None else w.get('text')
    def clip(self, text, px, room):
        """An hscroll_label that is not scrolling: the text cut with an ellipsis where it passes its box."""
        while self.font.width(text, px) > room and len(text) > 1: text = text[:-2] + '…' if text.endswith('…') else text[:-1] + '…'
        return text
    def img(self, n): return Image.open(os.path.join(self.d, n + '.png')).convert('RGBA')
    def text(self, im, x, y_mid, s, px, rgb=WHITE, anchor='l'):
        w = self.font.width(s, px)
        if anchor == 'm': x -= w // 2
        elif anchor == 'r': x -= w
        self.font.draw(im, int(x), int(y_mid - px / 2), s, px, rgb + (255,))
    def mark(self, im, name, x, y):
        """C / K marker for custom / kept-stock icons (after side only)."""
        if not self.after: return
        kind = KIND.get(name)
        if kind:
            ImageDraw.Draw(im).text((x, y), kind, fill=(90, 170, 255) if kind == 'C' else (255, 150, 40), font=ANN)

def kinds():
    k = {}
    for n, _, g in M.HOME + M.SETTINGS + M.LISTS:
        if g is None: k[n] = 'K'
        elif M.is_custom(g): k[n] = 'C'; k[n + '_down'] = 'C'
    k['m1plus'] = 'C'
    for n, g in list(M.PULLDOWN.items()) + list(M.STATUS.items()):
        if M.is_custom(g): k[n] = 'C'
    return k
KIND = kinds()

def status_bar(s, im, y0=0, bg=(0, 0, 0), vol='50', pct='86%'):
    ImageDraw.Draw(im).rectangle((0, y0, W - 1, y0 + BAR - 1), fill=bg)
    x = 10
    for n in ('bar_play', 'bar_vol3'):
        ic = s.img(n); im.alpha_composite(ic, (x, y0 + (BAR - ic.height) // 2)); x += ic.width + 4
    s.text(im, x, y0 + BAR / 2, vol, 16); s.text(im, 149, y0 + BAR / 2, '12:59 PM', 18, anchor='m')
    im.alpha_composite(s.img('bar_btcon'), (173, y0 + 5)); im.alpha_composite(s.img('bar_wifi3'), (224, y0 + 7))
    s.text(im, 292, y0 + BAR / 2, pct, 16, anchor='r'); im.alpha_composite(s.img('bar_power'), (296, y0 + 8))

def asset_bar(s, bar, im, y0=0, vol='100', clock='12:59 PM', lo=False):
    """A status bar drawn from its asset widgets (the system_bar window or the pull-down's view_sysbar): the left group
    stacked from its children_layout, the clock centred in its box, the right group right-aligned to its view's edge, the
    battery outline over its fill; the bar's own bg_color (black when it has none). Same images, fonts and offsets as the
    device draws, so two bars that differ in the asset differ here."""
    import re
    bg = (bar.get('style:normal:bg_color') or '#000000').lstrip('#')[:6]
    ImageDraw.Draw(im).rectangle((0, y0, W - 1, y0 + BAR - 1), fill=tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4)))
    def group(view, right):
        m = re.search(r'x=(\d+)', view.get('children_layout') or ''); sp = int(re.search(r's=(\d+)', view.get('children_layout')).group(1))
        kids = [c for c in view.children if c.name not in ('img_synclink', 'pod_shot', 'pod_pct', 'pod_pct_dd', 'pod_sync', 'pod_lo' if not lo else 'label_volume')]      # SyncLink is only drawn while connected; the Screenshot camera while it counts down, the Battery Percentage when it is on (preview.shot_bars), the sync icon while a build runs
        total = sum(c.w for c in kids) + sp * (len(kids) - 1)
        x = view.x + view.w - total if right else view.x + int(m.group(1)) if m else view.x
        for c in kids:
            if c.type == 'image':
                name = {'pod_lo': 'pod_bar_lo', 'img_playstate': 'bar_play', 'img_volume': 'bar_vol3', 'img_digital': 'bar_digital', 'img_btclass': 'bar_btcon', 'img_wifi': 'bar_wifi3'}[c.name]
                ic = s.img(name); im.alpha_composite(ic, (x + (c.w - ic.width) // 2 if c.get('draw_type') in ('icon', 'center') else x, y0 + (BAR - ic.height) // 2))
            else:   # label_volume
                s.text(im, x, y0 + BAR / 2, vol, int(c.get('style:normal:font_size')))
            x += c.w + sp
    group(bar.find('view_bar_left'), False); group(bar.find('view_bar_right'), True)
    clk = bar.find('bar_dclock'); s.text(im, clk.x + clk.w / 2, y0 + BAR / 2, clock, int(clk.get('style:normal:font_size')), anchor='m')
    img = bar.find('img_battery'); im.alpha_composite(s.img('bar_power'), (img.x, y0 + img.y))
    pg = bar.find('pgbar_battery'); ImageDraw.Draw(im).rectangle((pg.x, y0 + pg.y, pg.x + pg.w * 86 // 100 - 1, y0 + pg.y + pg.h - 1), fill=WHITE)

def lineout_bars(s):
    """The Line Out pill (patch/lineout.c) as the device shows it, 3x: the real bar with Line Out off (the volume number) and on (the pill in label_volume's place; the digital-out glyph follows it), then the
    pull-down's own bar copy with Line Out on, on the pull-down's #141414 panel."""
    import awtk_ui
    sysbar = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'system_bar.bin'), 'rb').read())
    dd = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui/dialog/dropdown_dialog.bin'), 'rb').read()).find('view_sysbar')
    rows = []
    for b, lo in ((sysbar, False), (sysbar, True), (dd, True)):
        one = Image.new('RGBA', (W, BAR), (0, 0, 0, 255)); asset_bar(s, b, one, lo=lo, vol='50'); rows.append(one)
    out = Image.new('RGB', (W, len(rows) * BAR + 6 * (len(rows) - 1)), (0x2A, 0x2A, 0x2A))
    for i, one in enumerate(rows): out.paste(one.convert('RGB'), (0, i * (BAR + 6)))
    return out.resize((out.width * 3, out.height * 3), Image.NEAREST)

def bars_compare(s):
    """The real status bar (system_bar.bin) over the pull-down's bar in the dropdown dialog, 1:1 on the pull-down's
    #141414 panel, then the difference from the real bar (x 16: all black when they match). Returns (image, they match)."""
    import awtk_ui
    from PIL import ImageChops
    sysbar = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'system_bar.bin'), 'rb').read())
    bars = [sysbar]
    dd = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui/dialog/dropdown_dialog.bin'), 'rb').read())
    bars.append(dd.find('view_sysbar'))
    drawn = []
    for b in bars:
        one = Image.new('RGBA', (W, BAR), (0, 0, 0, 255)); asset_bar(s, b, one); drawn.append(one)
    diffs = [ImageChops.difference(drawn[0].convert('RGB'), o.convert('RGB')).point(lambda v: min(255, v * 16)) for o in drawn[1:]]
    out = Image.new('RGBA', (W, 3 * BAR + 2 * 6), (0x14, 0x14, 0x14, 255))
    for i, one in enumerate(drawn + [d.convert('RGBA') for d in diffs]): out.alpha_composite(one, (0, i * (BAR + 6)))
    return out, all(not d.getbbox() for d in diffs)

def home(s, page):
    """A Home page (English: ids 1..17, 6 per page). The sixth slot of page 3 is the M1+ Music icon patch/home.c adds
    (after side); the stock side shows the HiFi store there (zh_CN only), the way the old preview did."""
    im = Image.new('RGBA', (W, 330), (0, 0, 0, 255)); status_bar(s, im)
    tiles = [t for t in M.HOME if t[0] != 'hifimusic'] + [('m1plus' if s.after else 'hifimusic', 'M1+ Music', None)]
    for i, (n, label, g) in enumerate(tiles[page * 6:(page + 1) * 6]):
        cx, cy = 60 + (i % 3) * 100, BAR + 24 + (i // 3) * 140
        if n == 'hifimusic': label = 'HiFi (zh_CN)'
        im.alpha_composite(s.img(n), (cx - 33, cy)); s.mark(im, n, cx - 33, cy)
        px = 18
        while s.font.width(label, px) > 98 and px > 12: px -= 1
        s.text(im, cx, cy + 86, label, px, anchor='m')
    return im

def settings(s):
    cell = 45; im = Image.new('RGBA', (W, 7 * cell + 6), (0, 0, 0, 255))
    for k, (n, _, g) in enumerate(M.SETTINGS):
        x, y = (k % 7) * 45 + 4, (k // 7) * cell + 4
        im.alpha_composite(s.img(n), (x, y)); s.mark(im, n, x + 30, y - 3)
    return im

def pulldown(s):
    im = Image.new('RGBA', (W, 290), (0x14, 0x14, 0x14, 255)); status_bar(s, im, bg=(0x14, 0x14, 0x14), vol='100')
    tiles = [('drop_wifiopen', 'Wi-Fi'), ('drop_bt', 'Bluetooth'), ('drop_keylockopen', 'Key lock'), ('drop_eqopen', 'EQ'),
             ('drop_usbaudio', 'USB audio'), ('drop_usbdac', 'USB DAC'), ('drop_usbstorage', 'USB storage'),
             ('drop_playset', 'Play set'), ('drop_syssetdown', 'Settings (off)'), ('drop_wifi', 'Wi-Fi (off)'),
             ('drop_keylock', 'Lock (off)'), ('drop_btopen', 'BT (on)')]
    for k, (n, label) in enumerate(tiles):
        x, y = 12 + (k % 4) * 76, 40 + (k // 4) * 78
        im.alpha_composite(s.img(n), (x, y)); s.mark(im, n.replace('open', ''), x + 38, y)
        s.text(im, x + 25, y + 62, label, 12, anchor='m')
    for n, x in (('drop_lighticon0', 30), ('drop_lighticon1', 270)):
        im.alpha_composite(s.img(n), (x, 262))
    return im

def lists(s):
    im = Image.new('RGBA', (W, 70), (0, 0, 0, 255)); x = 6
    for n in ('icon_folder', 'icon_playlist', 'icon_artist', 'icon_genre', 'icon_composer', 'icon_cdalbum'):
        im.alpha_composite(s.img(n), (x, 6)); s.mark(im, n, x + 26, 2); x += 42
    x = 6
    for n in M.COVERS[:1]:
        im.alpha_composite(s.img(n), (258, 6)); x += 70
    return im

def title_px(tree):
    """The navbar title size: the tree's navbar_label_white style (22 stock, 20 since V2.1jA)."""
    import awtk_style
    th = awtk_style.parse(open(os.path.join(tree, RAW, 'styles/default.bin'), 'rb').read())
    return th.find('label', 'navbar_label_white', 'normal')[0].get('font_size')

def home_pad():
    """HOME_PAD of patch/offsets.inc: the Home instance's air above the first and below the last row."""
    import re
    m = re.search(r'#define HOME_PAD (\d+)', open(os.path.join(M.ROOT, 'patch', 'offsets.inc')).read())
    return int(m.group(1))

def pod_page(s, key, tree_rows=8, home=False, first=0, title=None, icon=None, order=None, switches=None, arrows=None, values=None, root=None):
    """A mock of an M1+ Music rows page from the tree's ui asset: navbar title, then each list_item row
    (icon image, label, chevron) on black with the 1 px #222222 hairline. home=True: the Home instance of the
    menu, no navbar at all (the payload hides it) and the list from y HOME_PAD to HOME_PAD above the 450 px window's bottom.
    title / icon: what the payload sets at run time (the Artists page's title and toggle glyph); the toggle button, if the
    asset has one (btn_artisttype), is drawn centred in its place.
    order: the row names top to bottom as patch/menu.c arranged them (hidden rows are left out; default: the asset's order);
    switches: {switch image name: on} (the Settings and Main Menu pages set them at run time); arrows: the up-arrow buttons shown;
    values: {value label name: text} (the Cover Flow settings page's Sort value, as the payload sets it).
    root: a widget tree to draw instead of the tree's own file (a design preview of a page the build does not have yet)."""
    import awtk_ui
    root = root or awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', key + '.bin'), 'rb').read())
    pad = home_pad()
    top = pad if home else 50
    im = Image.new('RGBA', (W, 450 if home else 50 + tree_rows * 52), (0, 0, 0, 255)); d = ImageDraw.Draw(im)
    if not home:
        lt = next(w for w in root.walk() if w.name == 'label_title')
        title = title or s.shown(lt)
        s.text(im, 36, 25, s.clip(title, title_px(s.tree), lt.w), title_px(s.tree))
        im.alpha_composite(s.img('return'), (14, 14))
        tog = next((w for w in root.walk() if w.name in ('btn_artisttype', 'btn_settings')), None)
        if tog and icon != '':   # a capsule piece on the 214 slot: Now Playing is its right cap (ah_nav_play, the whole 60 x 50 button), else the stock glyph
            np_ = s.img('ah_nav_play'); im.alpha_composite(np_, (260 + (60 - np_.width) // 2, (50 - np_.height) // 2))
        else: im.alpha_composite(s.img('back_to_player'), (278, 13))
        if tog and icon != '':   # icon '': the payload hides the toggle (Genres, Composers)
            ic = s.img(icon or tog.get('style:normal:icon'))
            im.alpha_composite(ic, (tog.x + (tog.w - ic.width) // 2, (tog.h - ic.height) // 2))
    items = [w for w in root.walk() if w.type == 'list_item']
    if order is not None:   # (the Extras pages' order also names section headers, pod_hdr<group>: plain views, tools/pod_ui.py extras_headers)
        named = {w.name: w for w in root.walk()}
        items = [named[n] for n in order]
    items = items[first:first + tree_rows + sum(1 for w in items if w.type != 'list_item')]   # a header takes no row of the panel's height
    yy = top
    for k, r in enumerate(items):
        y = yy if order is not None else top + r.y - (items[0].y if first else 0)
        if y >= im.height: break
        if r.type != 'list_item':   # a section header: its caption (a small grey label) on the strip, r.h high
            cap = r.children[0]
            s.text(im, cap.x, y + cap.y + cap.h / 2, s.clip(s.shown(cap), int(cap.get('style:normal:font_size')), cap.w), int(cap.get('style:normal:font_size')),
                   tuple(int(cap.get('style:normal:text_color')[i:i + 2], 16) for i in (1, 3, 5)))
            yy += r.h
            continue
        yy += 52
        hair = next((c for c in r.children if c.name == 'pod_hair'), None)     # the rows' own inset hairline, else the theme's full-width one
        d.rectangle(((hair.x if hair else 0), y + 51, W - 1, y + 51), fill=(0x22, 0x22, 0x22))
        for c in r.children:
            if c.type == 'hscroll_label': s.text(im, c.x, y + 26, s.clip(s.shown(c), 21, c.w), 21)
            elif c.type == 'image' and c.name.startswith('pod_switch'):
                on = (switches or {}).get(c.name, c.get('image') == 'sset_on')
                im.alpha_composite(s.img('sset_on' if on else 'sset_off'), (c.x, y + c.y))
            elif c.type == 'label' and c.name.startswith('pod_value'):   # a value row's grey value, right aligned (the payload sets its text by key)
                text = (values or {}).get(c.name) or s.shown(c)
                s.text(im, c.x + c.w, y + 26, text, int(c.get('style:normal:font_size')), (0xAA,) * 3, 'r')
            elif c.type == 'button':
                if arrows is None or c.name in arrows:
                    ic = s.img(c.get('style:normal:icon')); im.alpha_composite(ic, (c.x + (c.w - ic.width) // 2, y + (c.h - ic.height) // 2))
            elif c.type == 'image' and c.get('image') != 'right_arrow': im.alpha_composite(s.img(c.get('image')), (c.x, y + c.y))
            elif c.type == 'image': ic = s.img(c.get('image')); im.alpha_composite(ic, (c.x + (c.w - ic.width) // 2, y + (c.h - ic.height) // 2))   # (draw_type icon: centred in the widget)
    if home: d.rectangle((0, 450 - pad, W - 1, 449), fill=(0, 0, 0))     # the list ends HOME_PAD above the screen edge
    return im

def offsets():
    """The numeric #defines of patch/offsets.inc (the Albums grid's geometry)."""
    import re
    return {m.group(1): int(m.group(2), 0) for m in re.finditer(r'^#define (\w+) (-?(?:0x[0-9a-fA-F]+|\d+))u?\b', open(os.path.join(M.ROOT, 'patch', 'offsets.inc')).read(), re.M)}

ALBUMS = [('Kind of Blue', 'Miles Davis', (70, 110, 190)), ('A Love Supreme', 'John Coltrane', (190, 140, 60)),
          ('Abbey Road', 'The Beatles', (90, 160, 110)), ('The Dark Side of the Moon', 'Pink Floyd', (60, 40, 110)),
          ('Rumours', 'Fleetwood Mac', (170, 90, 80)), ('Thriller', 'Michael Jackson', None),
          ('OK Computer', 'Radiohead', (110, 130, 150)), ('Blue', 'Joni Mitchell', (50, 90, 170)),
          ('Nevermind', 'Nirvana', (60, 150, 190)), ('Pet Sounds', 'The Beach Boys', (200, 170, 110)),
          ('日本語のアルバム名前', 'ユーミン', (150, 80, 140)), ('Low', 'David Bowie', (120, 120, 90))]

def sample_cover(rgb, size):
    """A stand-in cover: a diagonal gradient of rgb; None is the stock placeholder disc (no cache file)."""
    im = Image.new('RGB', (size, size)); d = ImageDraw.Draw(im)
    if rgb is None:
        d.rectangle((0, 0, size, size), fill=(0x2B,) * 3); c = size // 2
        d.ellipse((c - size * 0.42, c - size * 0.42, c + size * 0.42, c + size * 0.42), fill=(0x40,) * 3)
        d.ellipse((c - size * 0.12, c - size * 0.12, c + size * 0.12, c + size * 0.12), fill=(0x2B,) * 3)
        return im.convert('RGBA')
    for y in range(size):
        k = 0.55 + 0.45 * (1 - y / size)
        d.line((0, y, size, y), fill=tuple(int(v * k) for v in rgb))
    d.ellipse((size * 0.25, size * 0.25, size * 0.75, size * 0.75), outline=tuple(min(255, v + 70) for v in rgb), width=max(1, size // 30))
    return im.convert('RGBA')

def save_compact(im, path, colors=128):
    """A palette PNG (median cut, no dither): the previews are flat UI, and docs/ history keeps every regeneration."""
    im.convert('RGB').quantize(colors, Image.Quantize.MEDIANCUT).save(path, optimize=True)

def albums_navbar(s, im, to):
    """The Albums page's navbar (Back, title, Now Playing) with the mode toggle, flush left of Now Playing (NAV_VIEW_X),
    showing the glyph of the mode it switches to."""
    o = offsets()
    s.text(im, 36, 25, 'Albums', title_px(s.tree))
    im.alpha_composite(s.img('return'), (14, 14))
    im.alpha_composite(s.img('back_to_player'), (278, 13))
    c = s.img('pod_nav_coverflow')   # the Cover Flow button, flush left of the toggle
    im.alpha_composite(c, (o['NAV_CF_X'] + (o['NAV_CF_W'] - c.width) // 2, (o['NAV_H'] - c.height) // 2))
    n = 'pod_nav_' + to
    im.alpha_composite(s.img(n), (o['NAV_VIEW_X'] + (o['NAV_VIEW_W'] - s.img(n).width) // 2, (o['NAV_H'] - s.img(n).height) // 2))

def rounded(c, r, k=4):
    """Cover image c with r px rounded corners (drawn k times larger and reduced), as patch/grid.c rounds the Albums covers."""
    n = c.width
    mask = Image.new('L', (n * k, n * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n * k - 1, n * k - 1), radius=r * k, fill=255)
    c = c.copy(); c.putalpha(mask.resize((n, n), Image.LANCZOS))
    return c

def albums_grid(s, scroll=0):
    """ui/m1plus_albums.bin as patch/albums.c paints it: GRID_COLS covers a row, a one-line title (ellipsis) under each."""
    o = offsets(); W_, H_ = 320, 450
    im = Image.new('RGBA', (W_, H_), (0, 0, 0, 255)); albums_navbar(s, im, 'list')
    cover, gap, m, tg, th, sh = o['GRID_COVER'], o['GRID_GAP'], o['GRID_MARGIN'], o['GRID_TITLE_GAP'], o['GRID_TITLE_H'], o['GRID_SUB_H']
    rgap = o['GRID_ROW_GAP']
    pitch = cover + tg + th + sh + rgap
    def cut(text, px):
        while s.font.width(text, px) > cover and len(text) > 1:      # the ellipsis cut, as al_fit
            text = text[:-2] + '…' if text.endswith('…') else text[:-1] + '…'
        return text
    for a, (title, artist, rgb) in enumerate(ALBUMS * 2):
        x, top = m + (a % o['GRID_COLS']) * (cover + gap), 50 + rgap + (a // o['GRID_COLS']) * pitch - scroll
        if top >= H_ or top + cover + tg + th + sh <= 50: continue
        c = rounded(sample_cover(rgb, cover), o['GRID_R'])
        y0, y1 = max(50, top), min(H_, top + cover)
        if y1 > y0: im.alpha_composite(c.crop((0, y0 - top, cover, y1 - top)), (x, y0))
        ty = top + cover + tg
        if ty >= 50 and ty + th <= H_:
            s.text(im, x, ty + th / 2, cut(title, 18), 18)
        if ty + th >= 50 and ty + th + sh <= H_:
            s.text(im, x, ty + th + sh / 2, cut(artist, 15), 15, (0xAA, 0xAA, 0xAA))
    return im

PLAYLISTS = [('Road Trip', 12, (0, 1, 2, 3)), ('Late Night', 31, (4, 6)), ('日本語のプレイリスト', 8, (10, 6, 7)), ('Focus', 40, (8,)),
             ('Workout with a very long name', 1, ()), ('Evening Jazz', 27, (0, 1, 2, 3, 4, 5, 6)), ('Favourites', 118, (9, 11))]   # name, tracks, the albums with a cover (indexes into ALBUMS)

def mosaic(rgbs, size, r):
    """A playlist's tile as patch/grid.c grid_mosaic composes it: no cover is the placeholder disc, one the cover itself, 2..4 repeat to fill the
    quadrants (A B / B A, A B / C A, A B / C D), the corners rounded as the Albums covers."""
    n = min(len(rgbs), 4)
    if n == 0: return rounded(sample_cover(None, size), r)
    if n == 1: return rounded(sample_cover(rgbs[0], size), r)
    quad = {2: (0, 1, 1, 0), 3: (0, 1, 2, 0), 4: (0, 1, 2, 3)}[n]
    im = Image.new('RGBA', (size, size)); h = size // 2
    for q, k in enumerate(quad): im.paste(sample_cover(rgbs[k], h), ((q & 1) * h, (q >> 1) * h))
    return rounded(im, r)

def playlists_grid(s, menu=False, pressed=3, list_mode=False, row_pressed=1, select=None, pick=False):
    """ui/m1plus_playlists.bin as patch/playlists.c paints it: the Albums grid's cells (a mosaic cover, the playlist's name in 18 px, "N tracks" in
    15 px #AAAAAA) under a navbar with the "..." button; menu=True: the popup card open (row `pressed` held down) under the button. select: the set of marked
    playlists (indexes into PLAYLISTS) in select mode (the menu's Delete Playlists): the glass x, "N Selected", Select All, a mark on every cell or row (the list's rows
    and texts 30 px to the right), the bar with the Delete pill."""
    import awtk_ui
    o = offsets(); W_, H_ = 320, 450
    root = awtk_ui.parse(open(os.path.join(s.tree, RAW, 'ui', 'm1plus_playlists.bin'), 'rb').read())
    im = Image.new('RGBA', (W_, H_), (0, 0, 0, 255))
    shift = o['SG_SEL_COL'] if select is not None else 0
    if select is not None:   # select mode's navbar (the Songs page's): the glass x, "N Selected", Select All at the right
        import preview_songs as PS
        PS.glass(s, im, 'ah_nav_close', 7, 44)
        s.text(im, o['NAV_TITLE_X'], 25, s.strings.get('%d Selected', '%d Selected').replace('%d', str(len(select))), title_px(s.tree))
        sa = s.strings.get('Select All', 'Select All'); s.text(im, o['SG_SELALL_X'] + 104 - 8 - s.font.width(sa, 18), 25, sa, 18)
    elif pick:   # the Add to Playlist picker (patch/playlists.c pick mode): Back and the title only, list mode
        s.text(im, o['NAV_TITLE_X'], 25, s.strings.get('Add to Playlist', 'Add to Playlist'), title_px(s.tree))
        import preview_songs as PS
        PS.glass(s, im, 'ah_nav_back', 7, 44)   # the asset's btn_return: the glass disc
    else:
        s.text(im, 36, 25, s.shown(root.find('label_title')), title_px(s.tree))
        im.alpha_composite(s.img('return'), (14, 14)); im.alpha_composite(s.img('back_to_player'), (278, 13))
        more = root.find('btn_more'); ic = s.img(more.get('style:normal:icon'))
        im.alpha_composite(ic, (more.x + (more.w - ic.width) // 2, (more.h - ic.height) // 2))
        tog = root.find('btn_albumview'); ic = s.img('pod_nav_grid' if list_mode else tog.get('style:normal:icon'))   # the glyph of the view a tap switches to
        im.alpha_composite(ic, (tog.x + (tog.w - ic.width) // 2, (tog.h - ic.height) // 2))
    def mark(x, y, a):   # a select mark (the stock images, 26 px)
        mk = s.img('selected' if a in select else 'unselect'); im.alpha_composite(mk, (x, y))
    def bar():   # the bar: black, a #222222 hairline, the Delete pill across it
        import preview_songs as PS
        d_ = ImageDraw.Draw(im); d_.rectangle((0, H_ - o['SG_BAR_H'], W_ - 1, H_ - 1), fill=(0, 0, 0)); d_.rectangle((0, H_ - o['SG_BAR_H'], W_ - 1, H_ - o['SG_BAR_H']), fill=PS.HAIR)
        PS.pill(s, im, o['SG_PILL_X0'], H_ - o['SG_BAR_H'] + (o['SG_BAR_H'] - o['SG_PILL_H']) // 2, PS.tr(s, 'Delete'), s.img('sg_trash'), w=o['PL_BAR_PILL_W'])
    if list_mode:   # 64 px rows as patch/grid.c grid_list_paint draws them: 52 px mosaic, name 21 px, count 18 px #AAAAAA, hairline, the pressed row
        d = ImageDraw.Draw(im); rh = o['LIST_ROW_H']
        def lcut(text, px):
            while s.font.width(text, px) > o['LIST_TEXT_W'] - shift and len(text) > 1: text = text[:-2] + '…' if text.endswith('…') else text[:-1] + '…'
            return text
        rows = [(s.strings.get('New playlist', 'New playlist'), None, []), (s.strings.get('Favorites', 'Favorites'), None, [])] + PLAYLISTS if pick else PLAYLISTS   # the picker's first rows make a playlist and add to Favourites: no count
        for r, (name, tracks, albums) in enumerate(rows):
            y = 50 + r * rh
            if y + rh > H_: break
            if r == row_pressed: d.rectangle((0, y, W_ - 1, y + rh - 2), fill=(0x33, 0x33, 0x33))
            d.rectangle((0, y + rh - 1, W_ - 1, y + rh - 1), fill=(0x22, 0x22, 0x22))
            if pick and r < 2:   # New playlist (a white plus, pl_plus) and Favorites (a white star, pl_star) on a dark rounded square, the title alone and centred in the row
                ax, ay, A = o['LIST_ART_X'], y + o['LIST_ART_Y'], o['LIST_ART']
                d.rounded_rectangle((ax, ay, ax + A - 1, ay + A - 1), o['LIST_R'], fill=(0x2C, 0x2C, 0x2E))
                if r == 0:
                    d.rectangle((ax + A // 2 - 10, ay + A // 2 - 1, ax + A // 2 + 9, ay + A // 2), fill=(255, 255, 255)); d.rectangle((ax + A // 2 - 1, ay + A // 2 - 10, ax + A // 2, ay + A // 2 + 9), fill=(255, 255, 255))
                else:   # the filled five-point star of pl_make_star: outer radius 10.5 px, inner 4.75, centre 0.5 px below the art box's, 24 px square centred in the box
                    import math
                    k, bx, by = 8, ax + (A - 24) // 2, ay + (A - 24) // 2
                    pts = [((12 + (10.5 if i % 2 == 0 else 4.75) * math.sin(i * math.pi / 5)) * k, (12.5 - (10.5 if i % 2 == 0 else 4.75) * math.cos(i * math.pi / 5)) * k) for i in range(10)]
                    big = Image.new('L', (24 * k, 24 * k), 0); ImageDraw.Draw(big).polygon(pts, fill=255)
                    im.paste(Image.new('RGBA', (24, 24), (255, 255, 255, 255)), (bx, by), big.resize((24, 24), Image.LANCZOS))
                s.text(im, o['LIST_TEXT_X'] + shift, y + (rh - o['LIST_TITLE_H']) // 2 + o['LIST_TITLE_H'] / 2, lcut(name, 21), 21)
                continue
            im.alpha_composite(mosaic([ALBUMS[i][2] for i in albums if ALBUMS[i][2]], o['LIST_ART'], o['LIST_R']), (o['LIST_ART_X'] + shift, y + o['LIST_ART_Y']))
            s.text(im, o['LIST_TEXT_X'] + shift, y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] / 2, lcut(name, 21), 21)
            count = s.strings.get('%d track' if tracks == 1 else '%d tracks', '%d tracks').replace('%d', str(tracks))
            if tracks is not None: s.text(im, o['LIST_TEXT_X'] + shift, y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] / 2, lcut(count, 18), 18, (0xAA, 0xAA, 0xAA))
            if select is not None: mark(o['LIST_ART_X'] + (shift - 6 - o['SG_MARK']) // 2, y + (rh - o['SG_MARK']) // 2, r)
        if select is not None: bar()
        return im
    cover, gap, m, tg, th, sh = o['GRID_COVER'], o['GRID_GAP'], o['GRID_MARGIN'], o['GRID_TITLE_GAP'], o['GRID_TITLE_H'], o['GRID_SUB_H']
    pitch = cover + tg + th + sh + o['GRID_ROW_GAP']
    def cut(text, px):
        while s.font.width(text, px) > cover and len(text) > 1: text = text[:-2] + '…' if text.endswith('…') else text[:-1] + '…'
        return text
    for a, (name, tracks, albums) in enumerate(PLAYLISTS):
        x, top = m + (a % o['GRID_COLS']) * (cover + gap), 50 + o['GRID_ROW_GAP'] + (a // o['GRID_COLS']) * pitch
        if top >= H_: continue
        c = mosaic([ALBUMS[i][2] for i in albums if ALBUMS[i][2]], cover, o['GRID_R'])
        y1 = min(H_, top + cover)
        im.alpha_composite(c.crop((0, 0, cover, y1 - top)), (x, top))
        if select is not None and top + cover - o['SG_MARK'] - 6 + o['SG_MARK'] <= H_: mark(x + cover - o['SG_MARK'] - 6, top + cover - o['SG_MARK'] - 6, a)
        ty = top + cover + tg
        if ty + th <= H_: s.text(im, x, ty + th / 2, cut(name, 18), 18)
        if ty + th + sh <= H_:
            count = s.strings.get('%d track' if tracks == 1 else '%d tracks', '%d tracks').replace('%d', str(tracks))
            s.text(im, x, ty + th + sh / 2, cut(count, 15), 15, (0xAA, 0xAA, 0xAA))
    if menu:   # the scrim's dim, the card fitted to the language as pl_fit does, the glass stretched as patch3_x does, the rows' hairlines and pressed band
        card = root.find('pl_card')
        dim = card_rgba(root.find('pl_scrim').get('style:normal:bg_color'))
        im.alpha_composite(Image.new('RGBA', (W_, H_), dim))
        rows = [root.find(f'pl_item{i}') for i in range(o['PL_MENU_ROWS'])]
        labs = [next(c for c in row.children if c.type == 'hscroll_label') for row in rows]
        cw = max(o['PL_CARD_MIN'], min(o['PL_CARD_MAX'], max(s.font.width(s.shown(lab), 18) for lab in labs) + o['PL_TEXT_X'] + o['PL_TEXT_R']))
        cx = o['PL_CARD_RIGHT'] - cw
        g = s.img(card.get('style:normal:bg_image')); t = g.width // 3
        glass = Image.new('RGBA', (cw, g.height))
        glass.paste(g.crop((0, 0, t, g.height)), (0, 0)); glass.paste(g.crop((g.width - t, 0, g.width, g.height)), (cw - t, 0))
        glass.paste(g.crop((t, 0, g.width - t, g.height)).resize((cw - 2 * t, g.height)), (t, 0))
        im.alpha_composite(glass, (cx, card.y))
        for i, (row, lab) in enumerate(zip(rows, labs)):
            y = card.y + row.y
            if i == pressed: im.alpha_composite(Image.new('RGBA', (cw, row.h), card_rgba(row.get('style:pressed:bg_color'))), (cx, y))
            if row.get('style:normal:border') == 'top': im.alpha_composite(Image.new('RGBA', (cw, 1), card_rgba(row.get('style:normal:border_color'))), (cx, y))
            ic = next(c for c in row.children if c.type == 'image')
            im.alpha_composite(s.img(ic.get('image')), (cx + ic.x, y + ic.y))
            s.text(im, cx + lab.x, y + row.h / 2, s.clip(s.shown(lab), 18, cw - o['PL_TEXT_X'] - o['PL_TEXT_R']), 18)
    if select is not None: bar()
    return im

def card_rgba(c):
    """An AWTK '#RRGGBBAA' (or '#RRGGBB') colour as a PIL RGBA tuple."""
    return tuple(int(c[i:i + 2], 16) for i in range(1, len(c), 2)) + ((255,) if len(c) == 7 else ())

def albums_list(s, pressed=1):
    """ui/m1plus_albums.bin in list mode as patch/albums.c paints it: LIST_ROW_H rows, a LIST_ART px cover, the album (21 px)
    and the artist (18 px, #AAAAAA) cut with an ellipsis at LIST_TEXT_W, a hairline under each row, row `pressed` held down."""
    o = offsets(); H_ = 450
    im = Image.new('RGBA', (W, H_), (0, 0, 0, 255)); d = ImageDraw.Draw(im); albums_navbar(s, im, 'grid')
    rh = o['LIST_ROW_H']
    def cut(text, px):
        while s.font.width(text, px) > o['LIST_TEXT_W'] and len(text) > 1:      # the ellipsis cut, as al_fit
            text = text[:-2] + '…' if text.endswith('…') else text[:-1] + '…'
        return text
    for r, (title, artist, rgb) in enumerate(ALBUMS * 2):
        y = 50 + r * rh
        if y >= H_: break
        if r == pressed: d.rectangle((0, y, W - 1, y + rh - 2), fill=(0x33, 0x33, 0x33))
        d.rectangle((0, y + rh - 1, W - 1, y + rh - 1), fill=(0x22, 0x22, 0x22))
        im.alpha_composite(rounded(sample_cover(rgb, o['LIST_ART']), o['LIST_R']), (o['LIST_ART_X'], y + o['LIST_ART_Y']))
        if y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] <= H_:     # a text not wholly in the view is not drawn
            s.text(im, o['LIST_TEXT_X'], y + o['LIST_TITLE_Y'] + o['LIST_TITLE_H'] / 2, cut(title, 21), 21)
        if y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] <= H_:
            s.text(im, o['LIST_TEXT_X'], y + o['LIST_SUB_Y'] + o['LIST_SUB_H'] / 2, cut(artist, 18), 18, (0xAA, 0xAA, 0xAA))
    return im.crop((0, 0, W, H_))

def zoom_strip(s):
    names = ['bar_play', 'bar_pause', 'bar_vol0', 'bar_vol1', 'bar_vol2', 'bar_vol3', 'bar_vol4', 'bar_wifi1', 'bar_wifi2',
             'bar_wifi3', 'bar_wifi4', 'bar_bt', 'bar_btcon', 'bar_digital', 'bar_power']
    im = Image.new('RGBA', (len(names) * 28, 26), (0, 0, 0, 255)); x = 2
    for n in names:
        ic = s.img(n); ic = ic.crop((0, 0, min(ic.width, 26), ic.height)) if n.startswith('bar_bt') is False else ic
        if n in ('bar_bt', 'bar_btcon'): ic = ic.crop((ic.width - 24, 0, ic.width, ic.height))
        im.alpha_composite(ic, (x, (26 - ic.height) // 2)); x += 28
    return im.resize((im.width * 3, 78), Image.NEAREST)

def main():
    before, after, out = sys.argv[1:4]
    sides = [('stock', Side(before, False)), ('release (Tabler Icons)', Side(after, True))]
    sections = [('Home page 1', lambda s: home(s, 0)), ('Home page 2', lambda s: home(s, 1)), ('Home page 3 (after: with the M1+ Music icon)', lambda s: home(s, 2)),
                ('M1+ Music menu (opened from the grid icon)', lambda s: pod_page(s, 'm1plus_menu', 8)), ('M1+ Music > Extras page', lambda s: pod_page(s, 'm1plus_extras', 7)),
                ('M1+ Music > Shuffle page', lambda s: pod_page(s, 'm1plus_shuffle', 3)),
                ('Settings icons (46)', settings), ('Pull-down', pulldown), ('List placeholders', lists)]
    pad = 14
    heights = [330, 330, 330, 50 + 8 * 52, 50 + 4 * 52, 50 + 3 * 52, 7 * 45 + 6, 290, 70]
    sh = Image.new('RGBA', (2 * W + 3 * pad, 30 + sum(h + 26 for h in heights) + 3 * 78 // 3 + 96), (0x2A, 0x2A, 0x2A, 255))
    d = ImageDraw.Draw(sh)
    d.text((pad, 6), 'Icons before / after, 1:1 device pixels. Markers (after): blue C = custom Tabler-style SVG, orange K = stock image kept. Zoom strip: status icons at 3x.', fill=WHITE, font=ANN)
    y = 30
    for (title, fn), h in zip(sections, heights):
        d.text((pad, y), title, fill=(0xAA,) * 3, font=ANN_B); y += 22
        for i, (_, s) in enumerate(sides): sh.alpha_composite(fn(s), (pad + i * (W + pad), y))
        y += h + 4
    d.text((pad, y), 'Status bar icons 3x: ' + sides[0][0] + ' above, ' + sides[1][0] + ' below', fill=(0xAA,) * 3, font=ANN_B); y += 22
    for _, s in sides: sh.alpha_composite(zoom_strip(s), (pad, y)); y += 84
    save_compact(sh.crop((0, 0, sh.width, y)), out); print('wrote', out)

if __name__ == '__main__': main()
