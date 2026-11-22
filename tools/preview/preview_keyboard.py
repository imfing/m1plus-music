#!/usr/bin/env python3
"""Approximate PIL mock-up of the on-screen keyboard (patch/keyboard.c, docs/modules/keyboard.md) against stock's T9 popup. Not pixel-exact AWTK.

  preview_keyboard.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release): the font, the status bar art, stock's keyboard icons and ui/m1plus_keyboard.bin come from it. The QWERTY panels draw the real
asset: the field, the pad and every key's rectangle, colour, label and glyph are read from the tree (the lowercase page; the other pages use tools/pod_keyboard.py's layout,
which test/pod/keyboard.py holds the payload to), the text and caret as patch/keyboard.c places them (the stb width, a text too wide shows its end after an ellipsis).
Panels (the second block: Settings > General > Keyboards with Chinese (Pinyin) on): the language key on the English layer, the Chinese layer typing nihao (with a candidate held), after a commit with the predictions,
a long sentence with its first word taken, the row scrolled, the 123 page with the key, Settings and its Keyboards page. The candidate lists are the real engine's answers (test/pod/pinyin.py).
Stock ui/user_keyboard.bin's letter page at the tree's own positions (its pages are laid out 640 px wide in a 320 px popup; drawn clipped, as an unscaled AWTK would
show it), then the empty field (shift on), typing with a key held, the 123 page, the #+= page, a long text, and the results after Search with the keyboard gone.
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import awtk_ui
import pod_keyboard as PK
import preview_icons as PI, preview_settings as PS

W, H, SS, BAR = 320, 480, 4, 30
GREY = (0x8E, 0x8E, 0x93); WHITE = (255, 255, 255)
RECENT = ['hard fork', 'the daily']
RESULTS = [('All-In with Chamath, Jason, Sacks & Friedberg', 'All-In Podcast, LLC', (0x8A, 0x2B, 0x2B), True),
           ('All In The Mind', 'ABC listen', (0x2B, 0x5A, 0x8A), False),
           ('All in the Industry', 'Shari Bayer', (0x6A, 0x4A, 0x9A), False),
           ('All In On Data', 'Tom Davenport', (0x2B, 0x7A, 0x5A), False),
           ('Allin Talks', 'Allin Studio', (0x8A, 0x6A, 0x2B), False)]


def rgb(c): return PI.card_rgba(c)[:3]


def layer(paint):
    """Shapes drawn at SS x by paint(draw, k) (k scales coordinates), returned smoothed at 1 x."""
    big = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
    paint(ImageDraw.Draw(big), lambda *v: [int(round(x * SS)) for x in v])
    return big.resize((W, H), Image.LANCZOS)


class Page:
    """The keyboard asset: widgets by name with their screen position (the window starts under the 30 px status bar)."""
    def __init__(self, s):
        self.s = s
        self.root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', 'm1plus_keyboard.bin'), 'rb').read())
        self.pad = self.root.find('kb_pad'); self.field = self.root.find('kb_field')
        self.fill = lambda n, st='normal': rgb(self.root.find(n).get(f'style:{st}:bg_color'))
    def px(self, n, key='font_size'): return int(self.root.find(n).get(f'style:normal:{key}'))


def keys_of(pg, page, lang=False, zh=False, go=None, fr=False, tag=None):
    """[(name, label, x, y, w, kind)] in window coordinates for a page: char keys k0.., then the function keys that show (lang: the language key; zh: the Chinese layer's letter page)."""
    lay = PK.layout(page, lang=lang, zh=zh, fr=fr)
    up = page == 'ABC'
    out = [(f'kb_k{i}', c, x, y + pg.pad.y, w, 'key') for i, (c, x, y, w) in enumerate(lay['keys'])]
    names = {'shift': ('kb_shifton' if up else 'kb_shift', 'on' if up else 'fn'), 'sym': ('kb_sym', 'fn'), 'del': ('kb_del', 'fn'), 'mode': ('kb_mode', 'fn'), 'lang': ('kb_lang', 'fn'), 'space': ('kb_space', 'key'), 'go': ('kb_go', 'fn')}
    label = {'sym': "'" if zh and page == 'abc' else '#+=' if page == '123' else '123', 'lang': tag or PK.LANG_TAGS[1 if zh else 0], 'mode': 'ABC' if page in ('123', '#+=') else '123', 'space': pg.s.shown(pg.root.find('kb_space')), 'go': go[0] if go else pg.s.shown(pg.root.find('kb_go'))}
    for role, (x, y, w) in lay['fn'].items():
        n, kind = names[role]
        out.append((n, label.get(role, ''), x, y + pg.pad.y, w, kind))
    return out


def keyboard(pg, im, page, held=None, lang=False, zh=False, go=None, fr=False, tag=None, acc=None):
    s = pg.s
    keys = keys_of(pg, page, lang, zh, go, fr, tag)
    top = BAR + pg.pad.y
    def paint(d, k):
        d.rectangle(k(0, top, W, H), fill=pg.fill('kb_pad') + (255,))
        for name, lab, x, y, w, kind in keys:
            node = pg.root.find(name)
            d.rounded_rectangle(k(x, BAR + y, x + w, BAR + y + PK.KB_KH), radius=int(node.get('style:normal:round_radius')) * SS, fill=pg.fill(name) + (255,))
    im.alpha_composite(layer(paint))
    for name, lab, x, y, w, kind in keys:
        node = pg.root.find(name)
        icon = node.get('style:normal:icon')
        cy = BAR + y + PK.KB_KH / 2
        if icon:
            g = s.img(icon); im.alpha_composite(g, (int(x + (w - g.width) // 2), int(cy - g.height / 2)))
        elif lab:
            px = int(node.get('style:normal:font_size'))
            ink = rgb(PK.KB_DIM if go and go[1] and name == 'kb_go' else node.get('style:normal:text_color'))   # (go = (label, dimmed): the password page's Join)
            s.text(im, x + w / 2, cy - (1 if len(lab) == 1 and lab.islower() else 0), lab, px, ink, 'm')
    if held and acc is not None:   # the long-press accent strip in place of the balloon: variants in slot order (reversed on a right-side key), the selected one on a darker pill
        name, lab, x, y, w, _ = next(kk for kk in keys if kk[1] == held and kk[0].startswith('kb_k'))
        v = PK.accents(held); n = len(v)
        ax, ay, aw, ah, rev = PK.acc_rect(x, w, y - pg.pad.y, n)
        bar, hl, a0 = pg.root.find('kb_acc'), pg.root.find('kb_acc_h'), pg.root.find('kb_a0')
        slot = n - 1 - acc if rev else acc
        def strip_paint(d, k):
            d.rounded_rectangle(k(ax, BAR + ay, ax + aw, BAR + ay + ah), radius=int(bar.get('style:normal:round_radius')) * SS, fill=rgb(bar.get('style:normal:bg_color')) + (255,))
            hx = ax + PK.ACC_PAD + slot * PK.ACC_CELL
            d.rounded_rectangle(k(hx, BAR + ay + PK.ACC_PAD, hx + PK.ACC_CELL, BAR + ay + ah - PK.ACC_PAD), radius=int(hl.get('style:normal:round_radius')) * SS, fill=rgb(hl.get('style:normal:bg_color')) + (255,))
        im.alpha_composite(layer(strip_paint))
        for i in range(n):
            s.text(im, ax + PK.ACC_PAD + i * PK.ACC_CELL + PK.ACC_CELL / 2, BAR + ay + ah / 2, v[n - 1 - i] if rev else v[i], int(a0.get('style:normal:font_size')), WHITE, 'm')
    elif held:   # the key pop-up: the stem over the key, the balloon above it with the letter large
        name, lab, x, y, w, _ = next(kk for kk in keys if kk[1] == held and kk[0].startswith('kb_k'))
        bx, by, sx, sy, sw, sh = PK.pop_rect(x, y - pg.pad.y, w, pg.pad.y)
        stem, pop, glyph = pg.root.find('kb_stem'), pg.root.find('kb_pop'), pg.root.find('kb_pop_l')
        def pops(d, k):
            d.rounded_rectangle(k(sx, BAR + sy, sx + sw, BAR + sy + sh), radius=int(stem.get('style:normal:round_radius')) * SS, fill=rgb(stem.get('style:normal:bg_color')) + (255,))
            d.rounded_rectangle(k(bx, BAR + by, bx + pop.w, BAR + by + pop.h), radius=int(pop.get('style:normal:round_radius')) * SS, fill=rgb(pop.get('style:normal:bg_color')) + (255,))
        im.alpha_composite(layer(pops))
        s.text(im, bx + pop.w / 2, BAR + by + pop.h / 2, lab, int(glyph.get('style:normal:font_size')), WHITE, 'm')


def shown_text(s, text, px):
    """What patch/keyboard.c kb_refresh shows: the text, or its end after an ellipsis when it is wider than the room; and its width."""
    off, prefix = 0, ''
    while True:
        t = prefix + text[off:]
        w = s.font.width(t, px)
        if w <= PK.FIELD_TEXT_W or off >= len(text): return t, w
        off += 1; prefix = '…'


def strip_bar(s, pg, im, pinyin, cands, hot=None, sx=0):
    """The Chinese layer's candidate strip as patch/keyboard.c zh_render lays it out: the pinyin (its end after an ellipsis when wider than its room), a divider, then the candidates side by side
    (each as wide as its text plus 12 px a side, at least 36, at most 230), scrolled sx px, clipped to the view right of the divider; hot: the pressed candidate's highlight."""
    top = BAR + PK.STRIP_Y
    py = pg.root.find('kb_py'); hl = pg.root.find('kb_chl')
    def paint(d, k): d.rectangle(k(0, top, W, top + PK.STRIP_H), fill=pg.fill('kb_strip') + (255,))
    im.alpha_composite(layer(paint))
    x0 = 0
    if pinyin:
        t, off = pinyin, 0
        while s.font.width(t, PK.PY_PX) > PK.PY_MAX and off < len(pinyin):
            off += 1; t = '…' + pinyin[off:]
        w = s.font.width(t, PK.PY_PX)
        s.text(im, PK.PY_X, top + PK.STRIP_H / 2, t, PK.PY_PX, rgb(py.get('style:normal:text_color')))
        x0 = PK.PY_X + w + PK.PY_X
        def divider(d, k): d.rectangle(k(x0 - PK.PY_X // 2, top + PK.SEP_Y, x0 - PK.PY_X // 2 + 1, top + PK.SEP_Y + PK.SEP_H), fill=pg.fill('kb_sep') + (255,))
        im.alpha_composite(layer(divider))
    tmp = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    off = 0
    for i, c in enumerate(cands):
        w = min(max(s.font.width(c, PK.CAND_PX) + 2 * PK.CAND_PAD, PK.CAND_MIN), PK.CAND_MAXW)
        x = x0 + off - sx
        if i == hot:
            def light(d, k, x=x, w=w): d.rounded_rectangle(k(x + 2, top + PK.CHL_Y, x + w - 2, top + PK.CHL_Y + PK.CHL_H), radius=int(hl.get('style:normal:round_radius')) * SS, fill=pg.fill('kb_chl') + (255,))
            tmp.alpha_composite(layer(light))
        s.text(tmp, x + PK.CAND_PAD, top + PK.STRIP_H / 2, c, PK.CAND_PX, WHITE)
        off += w
    tmp.paste((0, 0, 0, 0), (0, 0, x0, H))
    im.alpha_composite(tmp)


def screen(s, pg, text, page=None, held=None, hint='Shows, e.g. All-In', title='Search', lang=False, zh=False, strip=None, fr=False, tag=None, acc=None, name=False):
    """Status bar, the navbar (Back chevron, title), the field and, when page is given, the pad (lang: with the language key, zh: the Chinese layer; strip: (pinyin, candidates) above the pad).
    name: a name entry (KB_DONE), the field on the card's one row as patch/keyboard.c kb_name_row places it, no capsule or magnifier."""
    im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    PI.status_bar(s, im)
    cap, card = pg.root.find('kb_capsule'), pg.root.find('kb_card')
    mag, clear = pg.root.find('kb_mag'), pg.root.find('kb_clear')
    if name:   # the field's own box: x is that far left of the text origin (PK.FIELD_TEXT_X), the clear button at its right end
        fx, fy, fw = PK.NAME_X - PK.FIELD_TEXT_X, PK.NAME_Y + PK.NAME_DY, PK.NAME_FIELD_W + PK.FIELD_TEXT_X
        cx0 = fw - PK.FIELD_CLEAR_W
    else:
        fx, fy, fw, cx0 = pg.field.x, pg.field.y, pg.field.w, clear.x
    def paint(d, k):
        d.line(k(20, BAR + 17, 13, BAR + 25, 20, BAR + 33), fill=WHITE + (255,), width=int(2.5 * SS), joint='curve')   # the navbar's Back chevron (the glass disc is the real asset's)
        if name: d.rounded_rectangle(k(card.x, BAR + card.y, card.x + card.w, BAR + card.y + card.h), radius=int(card.get('style:normal:round_radius')) * SS, fill=pg.fill('kb_card') + (255,))
        else: d.rounded_rectangle(k(cap.x, BAR + cap.y, cap.x + cap.w, BAR + cap.y + cap.h), radius=int(cap.get('style:normal:round_radius')) * SS, fill=pg.fill('kb_capsule') + (255,))
    im.alpha_composite(layer(paint))
    s.text(im, 36, BAR + 25, title, 22)
    if not name: im.alpha_composite(s.img(mag.get('image')), (cap.x + mag.x + (mag.w - 16) // 2, BAR + cap.y + mag.y))
    tx, ty = fx + PK.FIELD_TEXT_X, BAR + fy + PK.FIELD_H / 2
    px = pg.px('kb_text')
    if text:
        t, w = shown_text(s, text, px)
        s.text(im, tx, ty, t, px, rgb(pg.root.find('kb_text').get('style:normal:text_color')))
        c = s.img(clear.get('style:normal:icon')); im.alpha_composite(c, (fx + cx0 + (clear.w - c.width) // 2, int(ty - c.height / 2)))
        cx = tx + w + 1
    else:
        s.text(im, tx, ty, hint, px, rgb(pg.root.find('kb_hint').get('style:normal:text_color')))
        cx = tx
    if page:
        car = pg.root.find('kb_caret')
        ImageDraw.Draw(im).rectangle((cx, BAR + fy + car.y, cx + car.w - 1, BAR + fy + car.y + car.h - 1), fill=rgb(car.get('style:normal:bg_color')))
        keyboard(pg, im, page, held, lang, zh, fr=fr, tag=tag, acc=acc, go=('Done', False) if name else None)
        if strip: strip_bar(s, pg, im, *strip)
    return im


def other_page(s, pg, name='', focus='name', sec='WPA2/WPA3', password='', shown=False, error=False, page='ABC'):
    """The Join Wi-Fi Network page (patch/wifipage.c wo_open, docs/modules/wifi.md "The Other Network flow"): the widgets of ui/m1plus_wifiother.bin, the keyboard's field on the row being typed in (the text, the grey
    placeholder while the name is empty, dots or the text for the password), the other row as a static label, card 2 one or two rows by the security, the action key (Next on the Name of a secured network, Join otherwise;
    dimmed until it can work)."""
    root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', 'm1plus_wifiother.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    secured = sec != 'None'
    im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    PI.status_bar(s, im)
    def paint(d, k):
        d.line(k(20, BAR + 17, 13, BAR + 25, 20, BAR + 33), fill=WHITE + (255,), width=int(2.5 * SS), joint='curve')
        for n in ('wo_card0', 'wo_card1b' if secured else 'wo_card1a'):
            c = by[n]
            d.rounded_rectangle(k(c.x, BAR + c.y, c.x + c.w, BAR + c.y + c.h), radius=int(c.get('style:normal:round_radius')) * SS, fill=rgb(c.get('style:normal:bg_color')) + (255,))
        if secured:
            h = by['wo_hair']
            d.rectangle(k(h.x, BAR + h.y, h.x + h.w, BAR + h.y + h.h), fill=rgb(h.get('style:normal:bg_color')) + (255,))
    im.alpha_composite(layer(paint))
    s.text(im, 36, BAR + 25, 'Join Wi-Fi Network', 22)
    def label(n, text, colour=None):
        w = by[n]
        s.text(im, w.x + 2, BAR + w.y + w.h / 2, text, int(w.get('style:normal:font_size')), colour or rgb(w.get('style:normal:text_color')))
    label('wo_name_l', 'Name')
    label('wo_sec_l', 'Security')
    sv = by['wo_sec_v']
    s.text(im, sv.x + sv.w - 2 - s.font.width(sec, 18), BAR + sv.y + sv.h / 2, sec, 18, rgb(sv.get('style:normal:text_color')))
    ch = by['wo_chev']; g = s.img(ch.get('image'))
    im.alpha_composite(g, (ch.x, BAR + ch.y))
    if secured: label('wo_pass_l', 'Password')
    def fitted(text, room):
        off, prefix = 0, ''
        while True:
            t = prefix + text[off:]
            w = s.font.width(t, 18)
            if w <= room or off >= len(text): return t, w
            off += 1; prefix = '…'
    pw_text = password if shown else '•' * len(password)
    f, car = by['kb_field'], by['kb_caret']
    if focus == 'name':
        t, w = fitted(name, 156)
        fx, fy, caret_x = 100, 56, 100 + (w + 1 if name else 0)
        if name:
            s.text(im, fx, BAR + fy + 24, t, 18, WHITE)
            c = s.img(by['kb_clear'].get('style:normal:icon')); cl = by['kb_clear']
            im.alpha_composite(c, (fx + cl.x + (cl.w - c.width) // 2, int(BAR + fy + 24 - c.height / 2)))
        else:
            s.text(im, fx, BAR + fy + 24, 'Network Name', 18, rgb(by['wo_name_h'].get('style:normal:text_color')))
        if secured and password:
            t2, _ = fitted(pw_text, 118)
            s.text(im, 144, BAR + 164 + 24, t2, 18, WHITE)
        cy = fy
    else:
        t, w = fitted(pw_text, 118)
        fx, fy, caret_x = 144, 164, 144 + (w + 1 if password else 0)
        if password: s.text(im, fx, BAR + fy + 24, t, 18, WHITE)
        if name:
            t2, _ = fitted(name, 156)
            s.text(im, 100, BAR + 56 + 24, t2, 18, WHITE)
        else:
            s.text(im, 100, BAR + 56 + 24, 'Network Name', 18, rgb(by['wo_name_h'].get('style:normal:text_color')))
        cy = fy
    ImageDraw.Draw(im).rectangle((caret_x, BAR + cy + car.y, caret_x + car.w - 1, BAR + cy + car.y + car.h - 1), fill=WHITE)
    del f
    if secured:
        eye = by['wo_eye']; g = s.img('wf_eye' if shown else 'wf_eyeoff')
        im.alpha_composite(g, (eye.x + (eye.w - g.width) // 2, BAR + eye.y + (eye.h - g.height) // 2))
    if error and secured:
        er = by['wo_err']
        s.text(im, er.x + 2, BAR + er.y + er.h / 2, 'Incorrect password', int(er.get('style:normal:font_size')), rgb(er.get('style:normal:text_color')))
    name_ok = 1 <= len(name.encode()) <= 32
    ok = name_ok and (focus == 'name' or 8 <= len(password) <= 63)
    keyboard(pg, im, page, go=('Next' if focus == 'name' and secured else 'Join', not ok))
    return im


def password_page(s, pg, text, shown=False, error=False, name='Sam’s iPhone', dim=None, page='abc'):
    """The Wi-Fi password page (patch/wifipage.c wk_open, docs/modules/wifi.md "The password page"): the widgets of ui/m1plus_wifipass.bin, the field's text as keyboard_attach places it (dots or the text, the end after an ellipsis
    when wider than 118 px), the keyboard's pad below with Join as its action key (dimmed until the password is valid)."""
    root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', 'm1plus_wifipass.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    PI.status_bar(s, im)
    def paint(d, k):
        d.line(k(20, BAR + 17, 13, BAR + 25, 20, BAR + 33), fill=WHITE + (255,), width=int(2.5 * SS), joint='curve')
        c = by['wk_card']
        d.rounded_rectangle(k(c.x, BAR + c.y, c.x + c.w, BAR + c.y + c.h), radius=int(c.get('style:normal:round_radius')) * SS, fill=rgb(c.get('style:normal:bg_color')) + (255,))
    im.alpha_composite(layer(paint))
    s.text(im, 36, BAR + 25, 'Enter Password', 22)
    ln = by['wk_line']
    s.text(im, ln.x + ln.w / 2, BAR + ln.y + ln.h / 2, f'Enter the password for “{name}”', ln.w and int(ln.get('style:normal:font_size')), rgb(ln.get('style:normal:text_color')), 'm')
    lab = by['wk_label']
    s.text(im, lab.x + 2, BAR + lab.y + lab.h / 2, 'Password', int(lab.get('style:normal:font_size')))
    f, tx = by['kb_field'], by['kb_text']
    shown_t = ('•' * len(text)) if not shown else text
    off, prefix = 0, ''
    while True:
        t = prefix + shown_t[off:]
        w = s.font.width(t, 18)
        if w <= f.w - 2 or off >= len(shown_t): break
        off += 1; prefix = '…'
    if text: s.text(im, f.x + tx.x, BAR + f.y + f.h / 2, t, 18, WHITE)
    cx = f.x + (w + 1 if text else 0)
    car = by['kb_caret']
    ImageDraw.Draw(im).rectangle((cx, BAR + f.y + car.y, cx + car.w - 1, BAR + f.y + car.y + car.h - 1), fill=WHITE)
    eye = by['wk_eye']; g = s.img('wf_eye' if shown else 'wf_eyeoff')
    im.alpha_composite(g, (eye.x + (eye.w - g.width) // 2, BAR + eye.y + (eye.h - g.height) // 2))
    if error:
        er = by['wk_err']
        s.text(im, er.x + 2, BAR + er.y + er.h / 2, 'Incorrect password', int(er.get('style:normal:font_size')), rgb(er.get('style:normal:text_color')))
    ok = len(text) >= 8 if dim is None else not dim
    keyboard(pg, im, page, go=('Join', not ok))
    return im


def magnifier(d, k, x, y, rgb_, r=5):
    d.ellipse(k(x - r, y - r, x + r, y + r), outline=rgb_, width=int(1.6 * SS))
    d.line(k(x + r * 0.7, y + r * 0.7, x + r * 1.7, y + r * 1.7), fill=rgb_, width=int(1.8 * SS))


def results_page(s, pg, text, list_kind='results'):
    """After Search: the keyboard is gone, the field keeps the text without a caret, the results (stand-ins) below."""
    im = screen(s, pg, text)
    def paint(d, k):
        for i, (_, _, col, sub) in enumerate(RESULTS):
            y = 132 + i * 64
            d.rounded_rectangle(k(12, y + 6, 64, y + 58), radius=6 * SS, fill=col)
            cx, cy = 298, y + 32
            if sub: d.line(k(cx - 7, cy, cx - 2, cy + 5, cx + 7, cy - 5), fill=WHITE, width=int(2.2 * SS), joint='curve')
            else:
                d.ellipse(k(cx - 11, cy - 11, cx + 11, cy + 11), outline=WHITE, width=int(1.6 * SS))
                d.line(k(cx - 5, cy, cx + 5, cy), fill=WHITE, width=int(1.8 * SS)); d.line(k(cx, cy - 5, cx, cy + 5), fill=WHITE, width=int(1.8 * SS))
            d.line(k(74, y + 63, 320, y + 63), fill=(0x22, 0x22, 0x22), width=SS)
    im.alpha_composite(layer(paint))
    for i, (name, by, _, _) in enumerate(RESULTS):
        y = 132 + i * 64
        s.text(im, 74, y + 22, s.clip(name, 19, 200), 19)
        s.text(im, 74, y + 44, s.clip(by, 16, 200), 16, GREY)
    return im


def stock_t9(s, pg, text):
    """Stock's popup at its tree positions: the black candidate strip, then the letter page's buttons with their icons."""
    im = screen(s, pg, text)
    root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', 'user_keyboard.bin'), 'rb').read())
    pop = root.find('user_keyboard'); y0 = H - pop.h
    d = ImageDraw.Draw(im)
    d.rectangle((0, y0, W - 1, H - 1), fill=(0x33, 0x33, 0x33)); d.rectangle((0, y0, W - 1, y0 + 52), fill=(0, 0, 0))
    page = root.find('letter'); py = y0 + root.find('pages').y
    for b in page.children:
        img = b.get('style:normal:bg_image') or b.get('style:normal:icon')
        if not img: continue
        ic = s.img(img)
        if ic.width < b.w and b.get('style:normal:bg_image'): ic = ic.resize((b.w - 6, ic.height))
        im.alpha_composite(ic, (b.x + (b.w - ic.width) // 2, py + b.y + (b.h - ic.height) // 2))
    return im


def keyboards_page(s, fr, zh):
    """Settings > General > Keyboards: English (always on, the row dimmed to 60 % by the payload), French (AZERTY) and Chinese (Pinyin) switches."""
    im = PS.draw_page(s, 'm1plus_keyboards', state={'switches': {'pod_switch0': True, 'pod_switch1': fr, 'pod_switch2': zh}}).convert('RGBA')
    row = im.crop((10, 60, 310, 60 + 52))
    dim = Image.blend(Image.new('RGBA', row.size, (0, 0, 0, 255)), row, 153 / 255)
    im.paste(dim, (10, 60))
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    pg = Page(s)
    long_text = 'all in with chamath jason sacks and friedberg'
    # what the engine says (test/pod/pinyin.py runs demo's own code on the shipped dictionary; these are its answers)
    nihao = ['你好', '你', '拟', '尼', '呢', '泥', '妳', '妮', '腻', '逆', '倪', '昵']
    after_nihao = ['啊', '吗', '像', '的', '了', '好', '多', '久', '吧', '看']
    rest = ['喜欢听博客', '喜欢', '喜欢听', '系', '西', '洗', '戏', '喜', '係', '细', '吸', '希']
    panels = [('Stock T9 (tree as laid out)', stock_t9(s, pg, '')),
              ('Name entry (KB_DONE): Rename Playlist, empty', screen(s, pg, '', 'ABC', hint='Enter a playlist name', title='Rename Playlist', name=True)),
              ('Name entry (KB_DONE): a name typed', screen(s, pg, 'Road Trip', 'abc', title='Rename Playlist', name=True)),
              ('Empty field, shift on', screen(s, pg, '', 'ABC')),
              ('Typing, "n" held', screen(s, pg, 'all i', 'abc', held='n')),
              ('123 page', screen(s, pg, 'all in', '123')),
              ('#+= page', screen(s, pg, 'all in', '#+=')),
              ('A long text: its end', screen(s, pg, long_text, 'abc')),
              ('After Search', results_page(s, pg, 'all in')),
              ('Chinese on: English layer with the language key', screen(s, pg, '', 'ABC', lang=True)),
              ('French on: English layer, the key reads FR', screen(s, pg, '', 'ABC', lang=True, tag=PK.FR_TAG)),
              ('French layer: AZERTY capitals', screen(s, pg, '', 'ABC', lang=True, fr=True, tag='EN')),
              ('French layer: typing, "e" held', screen(s, pg, 'bonjour', 'abc', held='e', lang=True, fr=True, tag='EN')),
              ('French layer: "e" held 500 ms, second variant under the finger', screen(s, pg, 'bonjour', 'abc', held='e', lang=True, fr=True, tag='EN', acc=1)),
              ('English capital "O" held: seven variants grow left', screen(s, pg, '', 'ABC', held='O', lang=True, tag=PK.FR_TAG, acc=2)),
              ('French layer: "a" held at the left edge', screen(s, pg, 'bonjour', 'abc', held='a', lang=True, fr=True, tag='EN', acc=0)),
              ('Chinese layer: typing nihao (a candidate held)', screen(s, pg, '', 'abc', lang=True, zh=True, strip=('ni hao', nihao, 2))),
              ('Space took the first: what follows it', screen(s, pg, '你好', 'abc', lang=True, zh=True, strip=('', after_nihao))),
              ('woxihuantingboke, the first word taken', screen(s, pg, '我', 'abc', lang=True, zh=True, strip=('xi huan ting bo ke', rest))),
              ('Row scrolled 80 px', screen(s, pg, '', 'abc', lang=True, zh=True, strip=('ni hao', nihao, None, 80))),
              ('Chinese layer, 123 page (the key stays)', screen(s, pg, '你好', '123', lang=True, zh=True)),
              ('Wi-Fi password: empty (Join dimmed)', password_page(s, pg, '')),
              ('Wi-Fi password: 8 characters', password_page(s, pg, 'hunter22')),
              ('Wi-Fi password: shown', password_page(s, pg, 'hunter22', shown=True)),
              ('Wi-Fi password: wrong', password_page(s, pg, '', error=True)),
              ('Join Wi-Fi Network: empty (Next dimmed)', other_page(s, pg, '')),
              ('Join Wi-Fi Network: a name', other_page(s, pg, 'Hidden net', page='abc')),
              ('Join Wi-Fi Network: the password', other_page(s, pg, 'Hidden net', 'pass', password='hunter22', page='abc')),
              ('Join Wi-Fi Network: wrong password', other_page(s, pg, 'Hidden net', 'pass', error=True, page='abc')),
              ('Join Wi-Fi Network: None', other_page(s, pg, 'Hidden net', sec='None', page='abc')),
              ('Security picker (the check follows)', PS.draw_wifisec(s)),
              ('Settings', PS.draw_page(s, 'm1plus_settings').convert('RGBA')),
              ('Settings > General > Keyboards, all off', keyboards_page(s, False, False)),
              ('Settings > General > Keyboards, French and Chinese on', keyboards_page(s, True, True))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (W + pad) + pad, H + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (W + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out, colors=256)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
