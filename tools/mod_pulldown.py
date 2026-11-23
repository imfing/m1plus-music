#!/usr/bin/env python3
"""The pull-down control centre: its status bar the real one, its text one step smaller (V2.1gB, docs/ui.md).

ui/dialog/dropdown_dialog.bin (the dialog has no page theme, styles/ has no
dropdown_dialog.bin) carries its own copy of the status bar (view_sysbar) and the tile captions:

  view_sysbar    laid out from the table the real bar (ui/system_bar.bin) uses, tools/statusbar.py: left group
                 at x 10, 4 px spacing, the volume number 16 px middle in 30 px, the clock 104..194 at 18 px, the
                 right group 4 px spacing and clear of the battery; the bar black as the real one
  pod_tile_*,    the eight tiles of ours (Sleep Timer, Settings, Equalizer, Power Off, AirPlay, DLNA, Wi-Fi Transfer, Screenshot: patch/pulldown.c shows them in the slots the saved file names): an
  pod_cap_*      image and a caption in view_switchs, added hidden and insensitive, the caption a copy of label_playset with the tile's text
  label_*        the eight tile captions (Wi-Fi, Bluetooth, Buttons lock, gain, USB mode, output,
                 Playback / System Setting): 71 x 36 boxes (stock 57 x 40) 5 px under the disc, top aligned, word-wrapped,
                 16 px #B0B0B0 (disabled #555555; stock 18 / 16 px white)
  img_*, label_* the tile images 56 x 56 (stock 50) round the stock centres, rows 100 apart as stock: x 21 / 95 / 169 / 243, y 11 / 111; no card under them, the discs sit on the panel
  pod_grabber    an image (drop_grabber: Now Playing's 36 x 5 pill, white at alpha 110, baked) at (142, 328) in the dialog, insensitive
  pod_cc2        page 2 (the pull-down has two pages, a left / right swipe swaps them whole): a view at (10, 44) 300 x 274 holding the cards pod_cc2_top (Now Playing), _left (four discs), _right1 (Equalizer),
                 _right2 (Sleep) (flat #1C1C1E, radius 26 / 22) with their widgets (CC2_LABELS, CC2_IMAGES, CC2_DISCS, CC2_TEXTS), and pod_cc2_dot0 / _dot1: 6 px page dots at (151 / 163, 319), images drop_dot_on / drop_dot_off; all hidden and insensitive, patch/pulldown.c shows them
  the dialog     background black at 92 % (PANEL_ALPHA; stock #141414); the status bar copy stays opaque black

pgbar_battery shows no number there (show_text false, stock), the slider and the icons have no text.
The caption boxes are 71 px wide (stock 57) around the new tile's centre (the tiles are 74 px apart, so
3 px stay between neighbours): "Bluetooth" is 60 px at 16, so in 57 AWTK broke it as "Bluetoot/h".
  view_backlight the brightness card: a flat #1C1C1E card, radius 26, 300 x 52 at (10, 265) (stock: a 300 x 50 black pill image at y 266), holding stock's own
                 widgets by stock's names (image0, image1, slider_backlight) laid out as the Display page's brightness card (pod_ui.bright_control): the
                 slider's absolute y 266 .. 316 is stock's, only its x (58 .. 258) and look change
The tool measures what it
sets with the shared text model (awtk_text.StbText: truncated advances + 1 px per glyph) in the
tree's own font, so it must run after the font step:

  - "100" (the widest volume) must fit label_volume (30 px);
  - "12:59 PM" (the widest clock) must fit bar_dclock;
  - every tile caption in English and Simplified Chinese (strings/en_US.bin, zh_CN.bin, the keys
    demo sets @0x4743c8..) must wrap into the 32 px box (lines x font size), greedy word wrap as
    AWTK breaks lines, and no Latin word may be broken inside; the other languages are reported
    (several overflow or break words already in stock).

Usage: mod_pulldown.py SRC_WORKDIR OUT_WORKDIR     (OUT == SRC edits in place)
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statusbar, pod_i18n, awtk_strings
from modlib import clone_workdir, edit_ui
from awtk_text import Ttf, awtk_width
from pod_roles import SURFACE_RGB, SUB_RGB

RAW = 'rootfs/release/assets/default/raw'
DIALOG = 'ui/dialog/dropdown_dialog.bin'
FONT = 'rootfs/release/assets/default/raw/fonts/default.ttf'
STATES = ('normal', 'disable', 'focused')
# old -> new inline font sizes: every caption 16 px (stock 18, disabled and focused 16; main's pull-down uses 16 / 14)
CAPTION_PX = 16
TILE = {18: CAPTION_PX, 16: CAPTION_PX}
CAPTION_RGB, CAPTION_DIS_RGB = SUB_RGB, '#555555'     # secondary text; a disabled tile's caption
PANEL_RGB, PANEL_ALPHA = '#000000', 0.92                # the dialog's background: black at this opacity (stock #141414); the cards and discs are opaque
PANEL_BG = f'{PANEL_RGB}{round(255 * PANEL_ALPHA):02X}'
CARD_X = 10                                             # the brightness card's x
TILE_PX = 56                                            # the tile images: stock 50 x 50, grown round the same centres
COLS_X, ROWS_Y = (21, 95, 169, 243), (11, 111)          # the 56 px tiles' x (stock 24 + 74 k, minus 3) and y in view_switchs (stock rows 14 and 114, 100 apart as now)
CAP_DX, CAP_DY, CAP_H = -7, TILE_PX + 5, 36             # a caption box from its tile: 71 wide centred on it, 5 px under the disc, two rows of 16 px (CAP_MT + 16 + CAP_SPACER + 16)
# AWTK's wrapped label (tools/mod_nowplaying.py, before LYR_DEFAULT_MARGIN) wraps to the box less margin_left / margin_right and draws a row only while it ends inside the box less
# margin_bottom; rows are font + spacer apart (default 2, tools/pod_pins.py). Every margin defaults to 2: the captions set left, right and bottom to 0 and keep the top 2.
CAP_MT, CAP_SPACER, CAP_MARGINS = 2, 2, ('margin_left', 'margin_right', 'margin_bottom')
BL_Y, BL_R = 265, 26                                    # the brightness card's y in the dialog (the slider inside keeps stock's screen y 266 .. 316) and radius; it is ROW_H high, CARD_W wide, at CARD_X
STOCK_BL = ((10, 266, 300, 50), (20, 15, 20, 20), (260, 15, 20, 20), (50, 0, 200, 50))   # stock's view_backlight and its image0, image1, slider_backlight (pinned)
GRAB = ('pod_grabber', 142, 328, 36, 5, 'drop_grabber')    # the grabber, a child of the dialog: name, x, y, w, h, image (the dialog is 340 high); a baked, antialiased copy of Now Playing's pill (mod_icons DROP_GRABBER)
IMGS = ('img_wifiswitch', 'img_btswitch', 'img_keylockswitch', 'img_gainswitch', 'img_usbmode', 'img_outputswitch', 'img_playset', 'img_sysset')   # TILES' images, in the same order
STOCK_X, STOCK_Y = (24, 98, 172, 246), (14, 114)        # where the stock tiles are (pinned)
TILES = ('label_wifi', 'label_bt', 'label_lock', 'label_gain', 'label_usbmode', 'label_outputway',
         'label_playset', 'label_sysset')
# the tile captions' string keys (demo @0x4743c8..0x474b70: widget_set_tr_text on the labels above)
TILE_KEYS = ('wifiset_wifi', 'wifiset_bt', 'system_keylock', 'gain_high', 'gain_low', 'sset_outputway',
             'playset', 'sysset', 'usbmode_audio', 'usbmode_dac', 'usbmode_storge')
# the tiles of ours: (image, caption, the image's picture, the caption's English text), after the stock tile it follows (the places are patch/pulldown.c's: a shown tile takes a slot)
OWN = (('pod_tile_sleep', 'pod_cap_sleep', 'drop_sleep', 'Sleep Timer'), ('pod_tile_settings', 'pod_cap_settings', 'drop_settings', 'Settings'),
       ('pod_tile_eq', 'pod_cap_eq', 'drop_equalizer', 'Equalizer'), ('pod_tile_power', 'pod_cap_power', 'drop_power', 'Power Off'),
       ('pod_tile_airplay', 'pod_cap_airplay', 'drop_airplay', 'AirPlay'), ('pod_tile_dlna', 'pod_cap_dlna', 'drop_dlna', 'DLNA'),
       ('pod_tile_transfer', 'pod_cap_transfer', 'drop_transfer', 'Wi-Fi Transfer'),
       ('pod_tile_shot', 'pod_cap_shot', 'drop_shot', 'Screenshot'))
CAPTION_OWN_PX = {'Screenshot': 15}   # a caption of ours set smaller than CAPTION_PX: the word is 74 px at 16 in the 71 px text width (71 at 15 fits)
MUST_FIT = ('en_US', 'zh_CN')
VOLUME_MAX, CLOCK_MAX = '100', '12:59 PM'
TILE_W = 71                              # caption box width (stock 57)


def check(ok, msg):
    if not ok: raise SystemExit(f'mod_pulldown: {msg}')


def strings(path, keys):
    """key -> text from an AWTK strings/*.bin (a table of NUL-terminated key, value pairs)."""
    d = open(path, 'rb').read(); out = {}
    for k in keys:
        i = d.find(b'\0' + k.encode() + b'\0')
        if i < 0: continue
        j = i + len(k) + 2
        out[k] = d[j:d.index(b'\0', j)].decode('utf-8')
    return out


def wrap(ttf, text, px, width):
    """Lines of a word-wrapped label: break after spaces, before and after CJK characters, and
    inside a word that is wider than the box on its own (AWTK's line breaker does the same)."""
    toks, cur = [], ''
    for ch in text:
        if ch == ' ': toks.append(cur + ' '); cur = ''
        elif ord(ch) >= 0x2e80:
            if cur: toks.append(cur); cur = ''
            toks.append(ch)
        else: cur += ch
    if cur: toks.append(cur)
    lines, line = [], ''
    for t in toks:
        if awtk_width(ttf, (line + t).rstrip(), px) <= width: line += t; continue
        if line.strip(): lines.append(line.rstrip())
        line = ''
        while awtk_width(ttf, t.rstrip(), px) > width:
            k = len(t)
            while k > 1 and awtk_width(ttf, t[:k], px) > width: k -= 1
            lines.append(t[:k]); t = t[k:]
        line = t
    if line.strip(): lines.append(line.rstrip())
    return lines


def split_words(ttf, text, px, width):
    """Latin words wider than the box (AWTK would break them inside)."""
    return [t for t in text.split(' ') if t.isascii() and awtk_width(ttf, t, px) > width]


def caption_rows(n, px):
    """The height n wrapped rows of a caption need from its box's top: the top margin, then rows CAP_SPACER apart (no bottom margin)."""
    return CAP_MT + n * px + (n - 1) * CAP_SPACER


def resize(w, table, states=STATES):
    """Every state that sets a font size gets the table's smaller one; returns {old: new}."""
    done = {}
    for st in states:
        v = w.get(f'style:{st}:font_size')
        if v is None: continue
        check(int(v) in table, f'{w.name}: unexpected {st} font size {v}')
        w.set(f'style:{st}:font_size', str(table[int(v)])); done[int(v)] = table[int(v)]
    check(done, f'{w.name}: no inline font size')
    return done


def add_own(root):
    """Our eight tiles in view_switchs after the stock widgets: the image (56 x 56, the stock tiles' new size, picture of the flat disc style, clickable) and its caption (a copy of label_playset
    with the tile's text), at the first slot and its caption offset; hidden and insensitive. A tile not shown stays so; patch/pulldown.c moves, shows and binds the shown ones."""
    from awtk_ui import Widget
    view, img, cap = root.find('view_switchs'), root.find('img_wifiswitch'), root.find('label_playset')
    check(view is not None and img is not None and cap is not None and cap in view.children and img in view.children, 'view_switchs / the first tile / label_playset missing')
    for name, capname, image, english in OWN:
        tile = Widget('image', img.x, img.y, img.w, img.h, [('name', name), ('draw_type', 'default'), ('image', image), ('clickable', 'true')])
        label = Widget('label', img.x + cap.x - root.find('img_playset').x, img.y + cap.y - root.find('img_playset').y, cap.w, cap.h,
                       [('name', capname)] + [p for p in cap.props if p[0] != 'name'] + [pod_i18n.text_prop(english)])
        for st in STATES:
            if english in CAPTION_OWN_PX and label.get(f'style:{st}:font_size') is not None: label.set(f'style:{st}:font_size', str(CAPTION_OWN_PX[english]))
        for w in (tile, label):
            w.set('visible', 'false'); w.set('sensitive', 'false'); view.children.append(w)


CC2 = ('pod_cc2', 10, 44, 300, 274)    # page 2's container (name, x, y, w, h in the dialog): the area from the status bar to the brightness card's bottom; hidden and insensitive, patch/pulldown.c shows it
CC2_CARDS = (('pod_cc2_top', 0, 0, 300, 120, 26), ('pod_cc2_left', 0, 129, 144, 145, 26),
             ('pod_cc2_right1', 152, 129, 148, 68, 22), ('pod_cc2_right2', 152, 206, 148, 68, 22))   # the placeholder cards (name, x, y, w, h, radius) in the container's coordinates
DOTS = (('pod_cc2_dot0', 153, 320, 4, 4), ('pod_cc2_dot1', 163, 320, 4, 4))   # the page dots (name, x, y, w, h) side by side over the grabber, Now Playing's size and pitch (4 px, 10 apart; centres 155 and 165); drop_dot_on / drop_dot_off, hidden and insensitive
CC2_LABELS = (('pod_cc2_title', 120, 11, 134, 22, 18, '#FFFFFF', 'left'), ('pod_cc2_artist', 120, 33, 134, 20, 15, '#8A8A8E', 'left'),
              ('pod_cc2_elapsed', 120, 99, 80, 16, 12, '#8A8A8E', 'left'), ('pod_cc2_remain', 207, 99, 80, 16, 12, '#8A8A8E', 'right'))   # the Now Playing card's labels (name, x, y, w, h, px, colour, align) in the container: title and artist clip at 134 px, the times 12 px (y centres 66, 87, 151 of the dialog)
CC2_IMAGES = (('pod_cc2_fav', 256, 10, 32, 32, 'drop_cc_fav'), ('pod_cc2_prev', 138, 47, 44, 44, 'drop_cc_prev'), ('pod_cc2_play', 182, 47, 44, 44, 'drop_cc_play'),
              ('pod_cc2_next', 226, 47, 44, 44, 'drop_cc_next'))   # the favourite disc (centre (282, 70) of the dialog) and the transport (centres x 170 / 214 / 258, 44 apart so the touch targets meet, y 113); baked images, clickable
CC2_TOP = ('pod_cc2_top', 'button')   # the Now Playing card is a button (a tap opens Now Playing); its cover and progress bar are painted by patch/pulldown.c
CC2_BUTTONS = ('pod_cc2_top', 'pod_cc2_right1', 'pod_cc2_right2')   # the cards that take a tap (buttons with the same look pressed); the left card is a plain view under its four discs
CC2_DISCS = (('pod_cc2_playmode', 9, 138, 54, 'drop_cc_pm_order'), ('pod_cc2_upnext', 80, 138, 54, 'drop_cc_upnext'), ('pod_cc2_artistgo', 9, 210, 54, 'drop_cc_artist'),
             ('pod_cc2_albumgo', 80, 210, 54, 'drop_cc_album'), ('pod_cc2_eqdisc', 164, 141, 44, 'drop_cc_eq'), ('pod_cc2_sleepdisc', 164, 218, 44, 'drop_cc_sleep'))   # the lower cards' discs (name, x, y, px, image) in the container: four 54 px discs centred at (46, 209) (117, 209) (46, 281) (117, 281) of the dialog (the first three clickable, the card's two are not: the card is the button), a 44 px disc 12 px in from each right card
CC2_TEXTS = (('pod_cc2_eqtitle', 218, 142, 17, '#FFFFFF'), ('pod_cc2_eqsub', 218, 166, 14, '#8A8A8E'), ('pod_cc2_sleeptitle', 218, 219, 17, '#FFFFFF'), ('pod_cc2_sleepsub', 218, 243, 14, '#8A8A8E'))   # the right cards' two lines (name, x, y, px, colour), 74 px wide: the title centred 10 px above the card's middle, the sub line 12 below
CC2_LIVE = (('pod_cc2_live_l', 120, 90, 54, 4, 'drop_cc_live_l'), ('pod_cc2_live_r', 234, 90, 54, 4, 'drop_cc_live_r'))   # radio's LIVE divider at the progress bar's place (Radio Now Playing's two fading capsules, name, x, y, w, h, image in the container): the bar's x 130 .. 297 of the dialog less the LIVE label's 44 px and an 8 px gap each side
CC2_LIVE_TEXT = ('pod_cc2_live', 182, 84, 44, 16, 13)   # the LIVE label (name, x, y, w, h, px), white, centred on the bar's middle x 214; the three are hidden and insensitive until a station connects or plays
CC2_TITLES = {'pod_cc2_eqtitle': 'Equalizer', 'pod_cc2_sleeptitle': 'Sleep'}   # their fixed words (tr_text keys); the sub lines are set by patch/pulldown.c
NEW = (GRAB[0], CC2[0]) + tuple(c[0] for c in CC2_CARDS) + tuple(d[0] for d in CC2_DISCS) + tuple(t[0] for t in CC2_TEXTS) + tuple(l[0] for l in CC2_LABELS) + tuple(i[0] for i in CC2_IMAGES) + tuple(d[0] for d in DOTS) + tuple(l[0] for l in CC2_LIVE) + (CC2_LIVE_TEXT[0],)   # the widgets this step adds besides the tiles of ours


def add_cards(root):
    """The grabber (the dialog's last child): an image of the baked pill, insensitive, so a touch reaches the dialog's own drag handlers as before. The panel's colour is set here too: black at PANEL_ALPHA,
    and the brightness card is restyled."""
    from awtk_ui import Widget
    view = root.find('view_switchs')
    check(view is not None and root.find('view_backlight') in root.children, 'view_switchs / view_backlight missing')
    check(root.get('style:normal:bg_color') == '#141414', 'the dialog\'s stock background is not #141414')
    root.set('style:normal:bg_color', PANEL_BG)
    restyle_backlight(root)
    name, x, y, w, h, image = GRAB
    grab = Widget('image', x, y, w, h, [('name', name), ('draw_type', 'default'), ('image', image), ('sensitive', 'false')])
    add_page2(root)   # (before the grabber: it stays the last child)
    root.children.append(grab)


def add_page2(root):
    """Control Center page 2: a container over x 10 .. 309, y 44 .. 317 holding placeholder cards, and the two page dots; all hidden and insensitive (the hook shows them on a swipe).
    The status bar copy and the grabber stay on both pages. The dots are baked images: a 6 px round fill renders square on the device."""
    from awtk_ui import Widget
    name, x, y, w, h = CC2
    box = Widget('view', x, y, w, h, [('name', name)])
    for cname, cx, cy, cw, ch, r in CC2_CARDS:
        top = cname in CC2_BUTTONS
        card = Widget(CC2_TOP[1] if top else 'view', cx, cy, cw, ch, [('name', cname)] + ([('enable', 'true')] if top else []))
        for st in STATES + (('pressed', 'over', 'selected') if top else ()):
            card.set(f'style:{st}:bg_color', SURFACE_RGB); card.set(f'style:{st}:border_width', '0'); card.set(f'style:{st}:round_radius', str(r))
            if top: card.set(f'style:{st}:text_color', '#FFFFFF')
        box.children.append(card)
    for lname, lx, ly, lw, lh, px, rgb, align in CC2_LABELS:
        lab = Widget('hscroll_label', lx, ly, lw, lh, [('name', lname), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        for st in STATES:
            lab.set(f'style:{st}:font_size', str(px)); lab.set(f'style:{st}:text_color', rgb); lab.set(f'style:{st}:text_align_h', align); lab.set(f'style:{st}:text_align_v', 'middle')
        box.children.append(lab)
    for dname, dx, dy, dpx, image in CC2_DISCS:
        click = dname in ('pod_cc2_playmode', 'pod_cc2_upnext', 'pod_cc2_artistgo', 'pod_cc2_albumgo')
        box.children.append(Widget('image', dx, dy, dpx, dpx, [('name', dname), ('draw_type', 'default'), ('image', image)] + ([('clickable', 'true')] if click else [('sensitive', 'false')])))
    for tname, tx, ty, px, rgb in CC2_TEXTS:
        lab = Widget('hscroll_label', tx, ty, 74, 22 if px == 17 else 18, [('name', tname), ('text', ''), ('only_parent_focus', 'true'), ('ellipses', 'true'), ('sensitive', 'false')])
        if tname in CC2_TITLES: lab.props.append(pod_i18n.text_prop(CC2_TITLES[tname]))
        for st in STATES:
            lab.set(f'style:{st}:font_size', str(px)); lab.set(f'style:{st}:text_color', rgb); lab.set(f'style:{st}:text_align_h', 'left'); lab.set(f'style:{st}:text_align_v', 'middle')
        box.children.append(lab)
    for iname, ix, iy, iw, ih, image in CC2_IMAGES:
        box.children.append(Widget('image', ix, iy, iw, ih, [('name', iname), ('draw_type', 'default'), ('image', image), ('clickable', 'true')]))
    for lname, lx, ly, lw, lh, image in CC2_LIVE:
        box.children.append(Widget('image', lx, ly, lw, lh, [('name', lname), ('draw_type', 'default'), ('image', image), ('sensitive', 'false'), ('visible', 'false')]))
    tname, tx, ty, tw, th, tpx = CC2_LIVE_TEXT
    lab = Widget('label', tx, ty, tw, th, [('name', tname), pod_i18n.text_prop('LIVE'), ('sensitive', 'false'), ('visible', 'false')])
    for st in STATES:
        lab.set(f'style:{st}:font_size', str(tpx)); lab.set(f'style:{st}:text_color', '#FFFFFF'); lab.set(f'style:{st}:text_align_h', 'center'); lab.set(f'style:{st}:text_align_v', 'middle')
    box.children.append(lab)
    root.children.append(box)
    for dname, dx, dy, dw, dh in DOTS:
        root.children.append(Widget('image', dx, dy, dw, dh, [('name', dname), ('draw_type', 'default'), ('image', 'drop_dot_off')]))
    for n in (name,) + tuple(d[0] for d in DOTS):   # (the cards inside the container stay visible: the container is what is hidden)
        root.find(n).set('visible', 'false'); root.find(n).set('sensitive', 'false')


def restyle_backlight(root):
    """view_backlight becomes the brightness card: stock's pill image and corner styles go, the fill is SURFACE_RGB, and the three children (kept by name, with stock's range and value) are laid out
    by the Display page's own code (pod_ui.bright_control), so the two cannot drift."""
    import pod_ui, pod_settings as ST
    bl = root.find('view_backlight')
    kids = [bl.find(n) for n in ('image0', 'image1', 'slider_backlight')]
    check(all(kids) and bl.children == kids and kids[2].type == 'slider', 'view_backlight is not stock\'s (image0, image1, slider_backlight)')
    check(tuple((w.x, w.y, w.w, w.h) for w in [bl] + kids) == STOCK_BL, f'view_backlight\'s stock places are not the pinned ones: {[(w.x, w.y, w.w, w.h) for w in [bl] + kids]}')
    check(bl.get('style:normal:bg_image') == 'backlight_bg' and kids[2].get('max') in (None, '100'), 'view_backlight: unexpected stock look or slider range')
    check((CARD_X, ST.CARD_W, ST.ROW_H) == (10, 300, 52) and BL_Y + pod_ui.BRIGHT_SLIDER_Y == STOCK_BL[0][1] and BL_Y + ST.ROW_H + 8 <= GRAB[2], 'the brightness card is not where this step puts it')
    for key in [k for k, _ in bl.props if k.startswith('style:')]: bl.remove(key)
    for st in STATES:
        bl.set(f'style:{st}:bg_color', SURFACE_RGB); bl.set(f'style:{st}:border_width', '0'); bl.set(f'style:{st}:round_radius', str(BL_R))
    bl.x, bl.y, bl.w, bl.h = CARD_X, BL_Y, ST.CARD_W, ST.ROW_H
    pod_ui.bright_control(kids[0], kids[2], kids[1], 0)


def edit(root, ttf, texts, report):
    shape = [(w.type, w.name, w.x, w.y, w.w, w.h) for w in root.walk()]
    bright = {w.name for w in root.find('view_backlight').walk()}   # (restyled by restyle_backlight)
    sysbar = root.find('view_sysbar')
    check(sysbar is not None and all(sysbar.find(n) is not None for n in statusbar.NAMES), 'unexpected pull-down layout')
    # the pull-down's copy of the status bar is laid out from the real bar's table (tools/statusbar.py): identical
    # positions, sizes and styles, on the real bar's black
    statusbar.apply(sysbar)
    for st in statusbar.STATES: sysbar.set(f'style:{st}:bg_color', statusbar.BAR_BG)
    vol, clock = sysbar.find('label_volume'), sysbar.find('bar_dclock')
    px = int(vol.get('style:normal:font_size')); need = awtk_width(ttf, VOLUME_MAX, px)
    check(need <= vol.w, f'"{VOLUME_MAX}" needs {need} px at {px}, label_volume is {vol.w}')
    cpx = int(clock.get('style:normal:font_size')); cw = awtk_width(ttf, CLOCK_MAX, cpx)
    check(cw <= clock.w, f'"{CLOCK_MAX}" needs {cw} px at {cpx}, the clock box is {clock.w}')
    report.append(f'status bar as the real one (statusbar.py): "{VOLUME_MAX}" {need}/{vol.w} px at {px}, "{CLOCK_MAX}" {cw}/{clock.w} px at {cpx}')
    want = {}   # name -> (x, y, w, h) of every stock tile image and caption after this step
    for i, name in enumerate(TILES):
        w = root.find(name); check(w is not None and w.type == 'label', f'{name} missing')
        img = root.find(IMGS[i]); col, row = i % 4, i // 4
        check(img is not None and (img.x, img.y, img.w, img.h) == (STOCK_X[col], STOCK_Y[row], 50, 50) and (w.x, w.y, w.h) == (img.x - 3, img.y + 54, 40),
              f'{name}: the stock tile / caption places are not the pinned ones ({img and (img.x, img.y, img.w, img.h)}, {(w.x, w.y, w.w, w.h)})')
        spx = int(w.get('style:normal:font_size'))
        check(w.w == 57, f'{name}: unexpected caption width {w.w}')
        img.x, img.y, img.w, img.h = COLS_X[col], ROWS_Y[row], TILE_PX, TILE_PX     # the same centres: the disc grows by 3 px each side
        w.x, w.y, w.w, w.h = img.x + CAP_DX, img.y + CAP_DY, TILE_W, CAP_H          # before measuring: fits() reads w.w and w.h
        want[img.name], want[w.name] = (img.x, img.y, img.w, img.h), (w.x, w.y, w.w, w.h)
        changed = resize(w, TILE)
        for st in STATES:   # secondary text, from the top of the box so a one-line and a two-line caption start at the same height
            w.set(f'style:{st}:text_color', CAPTION_DIS_RGB if st == 'disable' else CAPTION_RGB)
            w.set(f'style:{st}:text_align_v', 'top')
            for m in CAP_MARGINS: w.set(f'style:{st}:{m}', '0')
        tpx = int(w.get('style:normal:font_size'))
        fits = lambda t, px, bw=w.w: caption_rows(len(wrap(ttf, t, px, bw)), px) <= w.h
        for lang in MUST_FIT:
            for k, t in texts[lang].items():
                px = CAPTION_OWN_PX.get(k, tpx)
                check(not split_words(ttf, t, px, w.w), f'{lang} {k} {t!r}: a word is wider than {w.w} px at {px}')
                check(fits(t, px), f'{lang} {k} {t!r} does not fit {w.w}x{w.h} at {px}: {wrap(ttf, t, px, w.w)}')
        if name == TILES[0]:   # the boxes are all the same size: count once
            over = lambda px, bw: sorted(f'{l}:{k}' for l, kv in texts.items() for k, t in kv.items() if not fits(t, px, bw))
            report.append(f'tile captions over {w.h} px: {len(over(spx, 57))} at {spx} px x 57 (stock), {len(over(tpx, w.w))} at {tpx} px x {w.w} '
                          f'(none in {"/".join(MUST_FIT)}); still over: {", ".join(over(tpx, w.w))}')
    report.append(f'tiles {changed}')
    add_own(root)
    add_cards(root)
    after = [(w.type, w.name, w.x, w.y, w.w, w.h) for w in root.walk() if w.name not in (statusbar.LO_WIDGET, statusbar.SYNC_WIDGET, statusbar.SLEEP_WIDGET, statusbar.EQ_WIDGET) and not w.name.startswith(('pod_tile_', 'pod_cap_')) and w.name not in NEW]   # (the Line Out pill, the sync and sleep timer icons and the EQ mark statusbar.apply adds are the new widgets)
    bar_names = {w.name for w in sysbar.walk()}
    moved = [a for a, b in zip(shape, after) if a != b and a[1] not in bar_names and a[1] not in want and a[1] not in bright]   # the bar's own widgets, the eight tiles and their captions (checked below)
    now = {w.name: (w.x, w.y, w.w, w.h) for w in root.walk()}
    check(all(now[n] == g for n, g in want.items()) and len(want) == 16, f'the tiles and captions are not where this step puts them: {[n for n, g in want.items() if now[n] != g]}')
    check(len(shape) == len(after) and not moved, f'widgets moved: {moved}')


def apply(work):
    ttf = Ttf(os.path.join(work, FONT))
    langs = os.path.join(work, RAW, 'strings')
    texts = {f[:-4]: strings(os.path.join(langs, f), TILE_KEYS) for f in sorted(os.listdir(langs)) if f.endswith('.bin')}
    check(all(len(texts[l]) == len(TILE_KEYS) for l in MUST_FIT), 'tile caption strings missing')
    for lang, kv in texts.items():   # the captions of ours (keys of ours: the English text is the key, the table is the language's own; a stock key's text is the stock table's, Sleep Timer's powerm_sleep)
        for _, _, _, english in OWN:
            key = pod_i18n.key_for(english)
            if key is None: kv[english] = english   # a brand (AirPlay, DLNA): the same text in every language, measured as it is
            elif key == english: kv[english] = pod_i18n.TEXT[english][pod_i18n.table_for(lang)]
            else:   # (de_DE, es_ES and pl_PL are 11-string stubs the strings step does not use as a table)
                stock = dict(awtk_strings.load(os.path.join(langs, lang + '.bin'))).get(key)
                if stock is not None: kv[key] = stock
    out = []
    path = os.path.join(work, RAW, DIALOG)
    report = []
    old, new, _ = edit_ui(path, lambda root: edit(root, ttf, texts, report))
    out.append(f'{os.path.relpath(path, work)}: {len(old)} -> {len(new)} bytes')
    out += [f'  {r}' for r in report]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src'); ap.add_argument('out')
    a = ap.parse_args()
    clone_workdir(a.src, a.out)
    for line in apply(a.out): print('pulldown:', line)


if __name__ == '__main__': main()
