#!/usr/bin/env python3
"""Mock-up of the scrobble upload settings (patch/scrobpage.c, docs/modules/scrobble.md "Settings"): the Library page's Scrobbling row, the Scrobbling page, the ListenBrainz page
and the Last.fm page in their states, drawn by preview_settings.py's cards page from the built tree's own assets (ui/m1plus_library.bin, ui/m1plus_scrobbling.bin, ui/m1plus_listenbrainz.bin, ui/m1plus_lastfm.bin).
Approximate (PIL, not AWTK).

  preview_scrobble.py WORKDIR OUTDIR

WORKDIR is a built tree (out/dev/<tag>/tree, work/mod-release). Writes to OUTDIR: scrobble-library.png (the whole Library page), scrobble-library-card.png (the Library page scrolled to its end: the Scrobbling row),
scrobble-page.png (the Scrobbling page), scrobble-lb-notset / -checking / -name / -invalid.png (the ListenBrainz page: the Account
row and its note) and scrobble-lf-notset / -name / -failed.png (the Last.fm page), and scrobble-sheet.png (all of them side by side).
"""
import argparse, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pod_pages as P
import preview_icons as PI, preview_settings as PS

LIB, SCR, LB, LF = P.LIBRARY_PAGE.key, P.SCROBBLING_PAGE.key, P.LB_PAGE.key, P.LF_PAGE.key
ROWS = [r.label for r in P.LIBRARY_PAGE.rows]
SROWS = [r.label for r in P.SCROBBLING_PAGE.rows]


def library_state():
    sw = {f'pod_switch{ROWS.index(n)}': on for n, on in (('Index Rail', True), ('Section Headers', True), ('Landscape', False), ('Volume Buttons', False))}
    return {'switches': sw, 'values': {f'pod_value{ROWS.index("Scrobbling")}': 'On'}}


def scrobbling_state(value):
    return {'switches': {f'pod_switch{SROWS.index(n)}': True for n in ('Scrobbling', 'Auto Upload')},
            'values': {f'pod_value{SROWS.index("ListenBrainz")}': value, f'pod_value{SROWS.index("Last.fm")}': value}}


def lb_state(account): return {'values': {'pod_value0': account}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True)
    os.makedirs(a.outdir, exist_ok=True)
    whole = PS.draw_page(s, LIB, full=True, state=library_state())
    card = Image.new('RGBA', (PS.W, PS.SCREEN), (0, 0, 0, 255))   # the page scrolled to its end: the navbar of the top over the last screen of the list
    card.alpha_composite(whole.crop((0, whole.height - (PS.SCREEN - PS.NAV), PS.W, whole.height)), (0, PS.NAV))
    card.alpha_composite(whole.crop((0, 0, PS.W, PS.NAV)), (0, 0))
    panels = [('scrobble-library', whole), ('scrobble-library-card', card), ('scrobble-page', PS.draw_page(s, SCR, state=scrobbling_state('rob'))),
              ('scrobble-lb-notset', PS.draw_page(s, LB, state=lb_state(s.strings.get('Not Set', 'Not Set')))),
              ('scrobble-lb-checking', PS.draw_page(s, LB, state=lb_state(s.strings.get('Checking…', 'Checking…')))),
              ('scrobble-lb-name', PS.draw_page(s, LB, state=lb_state('rob'))),
              ('scrobble-lb-invalid', PS.draw_page(s, LB, state=lb_state('Invalid Token'))),
              ('scrobble-lf-notset', PS.draw_page(s, LF, state=lb_state(s.strings.get('Not Set', 'Not Set')))),
              ('scrobble-lf-name', PS.draw_page(s, LF, state=lb_state('rob'))),
              ('scrobble-lf-failed', PS.draw_page(s, LF, state=lb_state('Sign-in Failed')))]
    for name, im in panels: im.convert('RGB').save(os.path.join(a.outdir, name + '.png'))
    shown = panels[1:]
    sheet = Image.new('RGB', (len(shown) * (PS.W + 10) - 10, PS.SCREEN), (40, 40, 40))
    for i, (_, im) in enumerate(shown): sheet.paste(im.convert('RGB'), (i * (PS.W + 10), 0))
    sheet.save(os.path.join(a.outdir, 'scrobble-sheet.png'))
    print('wrote', len(panels) + 1, 'images to', a.outdir)


if __name__ == '__main__':
    main()
