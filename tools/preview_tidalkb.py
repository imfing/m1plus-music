#!/usr/bin/env python3
"""Approximate PIL mock-up of stock's Tidal > Search page with our keyboard embedded (patch/tidalkb.c, docs/modules/tidalkb.md). Not pixel-exact AWTK.

  preview_tidalkb.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release). The page is the tree's ui/tidal/tidal_serach_page.bin: the toolbar (navigationbar_view and its Back button, stock's), the search bar
listitem_ssid with its search_bg pill (stock's) and our field in it (the geometry, font size and colours the asset says; the text and the caret placed as patch/keyboard.c does), and the pad
(the keyboard page's own widgets, drawn by preview_keyboard.keyboard). The history rows and the results are stand-ins (the stock lists are filled at run time).

Panels: the page as it opens (pad up, hint), typing "all in", a long text, after Search (the pad hidden, the results visible, the bar keeps the text), and a tap on the bar (the pad back).
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui
import cdefs
import preview_icons as PI
import preview_keyboard as PKV

W, H, BAR = PKV.W, PKV.H, PKV.BAR
TK = cdefs.defines(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'patch', 'tidalkb.h'))
GREY = (0xAA, 0xAA, 0xAA)
HISTORY = ['hard fork', 'the daily', 'all in']


def rgb(c): return PKV.rgb(c)


def room_text(s, text, px):
    """What patch/keyboard.c kb_refresh shows in TK_TEXT_W: the text, or its end after an ellipsis; and its width."""
    off, prefix = 0, ''
    while True:
        t = prefix + text[off:]
        w = s.font.width(t, px)
        if w <= TK['TK_TEXT_W'] or off >= len(text): return t, w
        off += 1; prefix = '…'


def page(s, kb, root, text, pad, results=False):
    """The Tidal search page: status bar, toolbar, bar with the field, then the history (typing) or the results, then the pad."""
    im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    PI.status_bar(s, im)
    nav, bar = root.find('navigationbar_view'), root.find('listitem_ssid')
    f, hint, txt, car, clear = (root.find(n) for n in ('kb_field', 'kb_hint', 'kb_text', 'kb_caret', 'kb_clear'))
    back = s.img('return')
    im.alpha_composite(back, (max(0, (33 - back.width) // 2), BAR + (nav.h - back.height) // 2))
    im.alpha_composite(s.img('search_bg'), (bar.x, BAR + bar.y))
    px = int(txt.get('style:normal:font_size'))
    x0, y_mid = bar.x + f.x + txt.x, BAR + bar.y + f.h / 2
    if text:
        t, w = room_text(s, text, px)
        s.text(im, x0, y_mid, t, px, rgb(txt.get('style:normal:text_color')))
        c = s.img(clear.get('style:normal:icon'))
        im.alpha_composite(c, (bar.x + f.x + clear.x + (clear.w - c.width) // 2, int(y_mid - c.height / 2)))
        cx = x0 + w + 1
    else:
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))   # the label clips at its box (206 px): a hint wider than that is cut, not shortened
        s.text(layer, x0, y_mid, s.strings.get('Search Tidal', 'Search Tidal'), px, rgb(hint.get('style:normal:text_color')))
        im.alpha_composite(layer.crop((0, 0, bar.x + f.x + hint.w, H)), (0, 0))
        cx = x0
    if pad:
        ImageDraw.Draw(im).rectangle((cx, BAR + bar.y + car.y, cx + car.w - 1, BAR + bar.y + car.y + car.h - 1), fill=rgb(car.get('style:normal:bg_color')))
    d = ImageDraw.Draw(im)
    top = BAR + 50
    if results:
        for i, (name, by, col) in enumerate((('All In', 'Tidal', (0x8A, 0x2B, 0x2B)), ('All In The Mind', 'Tidal', (0x2B, 0x5A, 0x8A)), ('All in the Industry', 'Tidal', (0x6A, 0x4A, 0x9A)))):
            y = top + 44 + i * 64
            d.rounded_rectangle((12, y + 6, 64, y + 58), radius=6, fill=col)
            s.text(im, 74, y + 22, name, 19); s.text(im, 74, y + 44, by, 16, GREY)
            d.line((74, y + 63, 320, y + 63), fill=(0x22, 0x22, 0x22))
        for i, tab in enumerate(('Tracks', 'Artist', 'Album')):
            s.text(im, 53 + i * 107, top + 22, tab, 18, (0x00, 0xFF, 0xFF) if i == 0 else GREY, 'm')
        d.line((0, top + 42, W, top + 42), fill=(0x11, 0x11, 0x11), width=4)
    else:
        s.text(im, 15, top + 22, 'History record', 18)
        for i, h in enumerate(HISTORY):
            y = top + 44 + i * 44
            s.text(im, 15, y + 22, h, 18); d.line((0, y + 43, W, y + 43), fill=(0x11, 0x11, 0x11))
    if pad:
        PKV.keyboard(kb, im, 'abc' if text else 'ABC')
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    kb = PKV.Page(s)
    root = awtk_ui.parse(open(os.path.join(a.workdir, PI.RAW, 'ui', 'tidal', 'tidal_serach_page.bin'), 'rb').read())
    long_text = 'all in with chamath jason sacks and friedberg'
    panels = [('Opens: pad up, hint', page(s, kb, root, '', True)),
              ('Typing "all in"', page(s, kb, root, 'all in', True)),
              ('A long text: its end', page(s, kb, root, long_text, True)),
              ('After Search: pad hidden, results', page(s, kb, root, 'all in', False, results=True)),
              ('Tap on the bar: pad back', page(s, kb, root, 'all in', True, results=False))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (W + pad) + pad, H + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (W + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out, colors=256)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
