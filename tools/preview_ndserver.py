#!/usr/bin/env python3
"""Mock-up of the Navidrome Server page and its Sign In page (patch/ndserver.c, docs/modules/subsonic.md): a PIL approximation built on preview_keyboard.py's pad and
preview_settings.py's cards page. The widgets, their positions, colours and sizes are read from ui/m1plus_ndserver.bin and ui/m1plus_ndlogin.bin; the text, the dots, the caret, the spinner
frame and the error line are placed as the payload does.

  preview_ndserver.py WORKDIR OUTDIR

WORKDIR is a built tree (work/mod-release). Writes nd-server.png (the Server page with a saved login) and nd-signin-*.png (320 x 480) to OUTDIR: the first row of a new setup, the password row
ready to sign in, the wait, a wrong password and an edit of a saved login.
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui
import preview_icons as PI, preview_keyboard as PKV, preview_settings as PS

W, H, BAR = PKV.W, PKV.H, PKV.BAR
WHITE = PKV.WHITE
LOGIN = 'm1plus_ndlogin'
PLACEHOLDER = ('Server URL', 'Username', 'Password')


def server_page(s):
    """The Server page with a saved login: the values are the host, the user and four dots (patch/ndserver.c ns_refresh)."""
    state = {'values': {'pod_value0': 'nd.example:4533', 'pod_value1': 'alice', 'pod_value2': '••••'}}
    im = PS.draw_page(s, 'm1plus_ndserver', state=state).convert('RGBA')
    ImageDraw.Draw(im).rectangle((54, 0, 252, PS.NAV - 1), fill=(0, 0, 0, 255))   # the navbar's small title is hidden on this page (the large one speaks)
    return im


def signin_page(s, pg, texts, focus, shown=False, saved_pw=False, touched=False, key='Next', dim=True, page='abc', status=None, spin=0):
    """The Sign In page: texts = the three fields' values; the field sits on row `focus` (text and caret), the other rows are labels (value or the grey placeholder), the password as dots (four for a kept
    saved one) or its text with the eye open; key = the action key's label, dim = it is dimmed; status = ('busy'|'error', text) under the card."""
    root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', LOGIN + '.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    PI.status_bar(s, im)
    def paint(d, k):
        d.line(k(20, BAR + 17, 13, BAR + 25, 20, BAR + 33), fill=WHITE + (255,), width=int(2.5 * PKV.SS), joint='curve')
        c = by['nl_card']
        d.rounded_rectangle(k(c.x, BAR + c.y, c.x + c.w, BAR + c.y + c.h), radius=int(c.get('style:normal:round_radius')) * PKV.SS, fill=PKV.rgb(c.get('style:normal:bg_color')) + (255,))
        for n in ('nl_hair0', 'nl_hair1'):
            h = by[n]
            d.rectangle(k(h.x, BAR + h.y, h.x + h.w, BAR + h.y + h.h), fill=PKV.rgb(h.get('style:normal:bg_color')) + (255,))
    im.alpha_composite(PKV.layer(paint))
    s.text(im, 36, BAR + 25, s.shown(by['label_title']), 22)
    def fitted(text, room):
        off, prefix = 0, ''
        while True:
            t = prefix + text[off:]
            w = s.font.width(t, 18)
            if w <= room or off >= len(text): return t, w
            off += 1; prefix = '…'
    def shown_text(i):
        t = texts[i]
        return ('•' * len(t) if i == 2 and not shown else t)
    car = by['kb_caret']
    for i in range(3):
        y = BAR + 56 + 48 * i + 24
        if i == focus:
            t, w = fitted(shown_text(i), PK_TW)
            if texts[i]: s.text(im, 24, y, t, 18, WHITE)
            else: s.text(im, 24, y, PLACEHOLDER[i], 18, PKV.rgb(by[f'nl_h{i}'].get('style:normal:text_color')))
            cx = 24 + (w + 1 if texts[i] else 0)
            ImageDraw.Draw(im).rectangle((cx, BAR + 56 + 48 * i + car.y, cx + car.w - 1, BAR + 56 + 48 * i + car.y + car.h - 1), fill=WHITE)
            if texts[i] and i == 1:   # (the address and password fields are KB_PASSWORD: no clear button)
                c = s.img(by['kb_clear'].get('style:normal:icon')); cl = by['kb_clear']
                im.alpha_composite(c, (24 + cl.x + (cl.w - c.width) // 2, int(y - c.height / 2)))
        elif texts[i] or (i == 2 and saved_pw and not touched):
            t, _ = fitted(shown_text(i) if texts[i] else '••••', 272 if i != 2 else 232)
            s.text(im, 24, y, t, 18, WHITE)
        else:
            s.text(im, 24, y, PLACEHOLDER[i], 18, PKV.rgb(by[f'nl_h{i}'].get('style:normal:text_color')))
    eye = by['nl_eye']; g = s.img('wf_eye' if shown else 'wf_eyeoff')
    im.alpha_composite(g, (eye.x + (eye.w - g.width) // 2, BAR + eye.y + (eye.h - g.height) // 2))
    if status:
        kind, text = status
        if kind == 'busy':
            sp = by['nl_spin']; im.alpha_composite(s.img(f'wf_spin{spin & 7}'), (sp.x, BAR + sp.y))
            b = by['nl_busy']; s.text(im, b.x, BAR + b.y + b.h / 2, text, int(b.get('style:normal:font_size')), PKV.rgb(b.get('style:normal:text_color')))
        else:
            e = by['nl_err']; s.text(im, e.x, BAR + e.y + e.h / 2, text, int(e.get('style:normal:font_size')), PKV.rgb(e.get('style:normal:text_color')))
    PKV.keyboard(pg, im, page, go=(key, dim))
    return im


PK_TW = 232


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True)
    pg = PKV.Page(s)
    os.makedirs(a.outdir, exist_ok=True)
    panels = [('nd-server', server_page(s)),
              ('nd-signin-new', signin_page(s, pg, ['http://', '', ''], 0)),
              ('nd-signin-user', signin_page(s, pg, ['http://nd.example:4533', 'Al', ''], 1, dim=False, page='abc')),
              ('nd-signin-ready', signin_page(s, pg, ['http://nd.example:4533', 'alice', 'hunter22'], 2, key='Sign In', dim=False)),
              ('nd-signin-wait', signin_page(s, pg, ['http://nd.example:4533', 'alice', 'hunter22'], 2, key='Sign In', dim=True, status=('busy', 'Connecting…'), spin=2)),
              ('nd-signin-wrong', signin_page(s, pg, ['http://nd.example:4533', 'alice', 'hunter22'], 2, key='Sign In', dim=False, status=('error', 'Incorrect username or password'))),
              ('nd-signin-edit', signin_page(s, pg, ['https://nd.example:4533', 'alice', ''], 0, saved_pw=True, key='Sign In', dim=False))]
    for name, im in panels: im.convert('RGB').save(os.path.join(a.outdir, name + '.png'))
    print('wrote', len(panels), 'panels to', a.outdir)


if __name__ == '__main__':
    main()
