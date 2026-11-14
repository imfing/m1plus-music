#!/usr/bin/env python3
"""DESIGN PREVIEW: the Podcasts pages' empty-page hint and Loading... / Searching... line, before (left-aligned under the header) and after (centred in the room under it;
tools/pod_show.py hint_layout, docs/modules/podcasts.md "The hint").

  preview_center_hints.py WORKDIR [OUTDIR]      (WORKDIR: a built tree, work/mod-release; OUTDIR defaults to out/preview)

Writes OUTDIR/center-hints.png: before / after pairs. The headers of Search, Downloads and Subscriptions are the real ones of preview_podcasts_revamp.py; the Discover and Show headers
are simplified (a large title and a control / cover block of the right height). Not pixel-exact AWTK."""
import argparse, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preview_podcasts_revamp as R
import preview_icons as PI
import mod_icons as M
import pod_show, pod_wrap
from pod_roles import SUB_RGB as _SUB
SUB_RGB = tuple(int(_SUB[i:i + 2], 16) for i in (1, 3, 5))
from stb_raster import _paste

O, NAV, STAT = R.O, R.NAV, R.STAT


def hint(s, fr, top, text, new, busy=False):
    """Paint the hint on frame fr; top: the header's bottom in content coordinates (the content starts under the 50 px navbar)."""
    o = O
    px = 20
    room = R.W - 2 * o['PP_LINE_X'] - (o['PS_SPIN_PX'] + o['PS_SPIN_GAP'] if busy else 0)
    lines = pod_wrap.wrap_font(s.font, text, px, room, 4)
    base = STAT + NAV
    if new:
        L = pod_show.hint_layout(top, [s.font.width(l, px) for l in lines], busy)
        pos, spin = L['lines'], L['spin']
    else:
        sx = o['PS_SPIN_PX'] + o['PS_SPIN_GAP'] if busy else 0
        pos = [(o['PP_LINE_X'] + sx, top + 8 + k * o['PS_TITLE_PITCH']) for k in range(len(lines))]
        spin = (o['PP_LINE_X'], top + 8 + (o['PS_TITLE_PITCH'] - o['PS_SPIN_PX']) // 2) if busy else None
    for l, (x, y) in zip(lines, pos): s.text(fr, x, base + y + o['PS_TITLE_PITCH'] / 2, l, px, SUB_RGB)
    if spin: _paste(fr, M.wifi_spinner(0), spin[0], base + spin[1])
    return fr


def simple_page(s, title, top, block=None):
    """A simplified header: the navbar's glass, the large title, and `block` (a callable drawing under the title) down to content y `top`."""
    win = Image.new('RGBA', (R.W, R.WIN), (0, 0, 0, 255))
    s.text(win, O['SG_TITLE_X'], NAV + O['PP_TITLE_H'] / 2, title, O['PP_TITLE_PX'], R.WHITE)
    if block: block(win)
    R.PS.glass(s, win, 'ah_nav_back', 7, 44); R.capsule(s, win, 'none')
    return R.frame(s, win, None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir', nargs='?', default='out/preview')
    a = ap.parse_args()
    R.FONT, R.IMGS = pod_show.Font(pod_show.font_path(a.workdir)), M.podcast_images()
    s = PI.Side(a.workdir, True)
    o = O
    disc_top, srch_top = o['DC_TOP'], o['PQ_TOP']
    seg = pod_show.discover_layout(0)['seg']

    def segment(win):
        R.rrect(win, seg[0], NAV + seg[1], seg[2], seg[3], seg[3] // 2, (0x1C, 0x1C, 0x1E, 255))
        s.text(win, seg[0] + seg[2] // 4, NAV + seg[1] + seg[3] / 2, 'Shows', 15, R.WHITE, 'm'); s.text(win, seg[0] + 3 * seg[2] // 4, NAV + seg[1] + seg[3] / 2, 'Episodes', 15, R.GREY, 'm')

    show_top = 250

    def cover(win):
        R.rrect(win, 80, NAV + 8, 160, 160, 12, (0x55, 0x66, 0x88, 255))
        s.text(win, R.W // 2, NAV + 190, 'Night Talk', 22, R.WHITE, 'm'); R.rrect(win, 110, NAV + 208, 100, 28, 14, (255, 255, 255, 255))

    pages = [('Discover: Loading...', lambda: simple_page(s, 'Discover', disc_top, segment), disc_top, 'Loading…', True),
             ('Search: Searching...', lambda: R.search_page(s, [], [], 'all in'), srch_top, 'Searching…', True),
             ('Search: No results', lambda: R.search_page(s, [], [], 'all in'), srch_top, 'No results', False),
             ('Downloads: No downloads', lambda: R.downloads_page(s, [], [], line='0 episodes · 18 GB free'), o['PDL_LINE_PITCH'], 'No downloads', False),
             ('Subscriptions: No subscriptions', lambda: R.subs_page(s, []), o['PP_TITLE_H'], 'No subscriptions', False),
             ('Show page, no episodes', lambda: simple_page(s, '', show_top, cover), show_top, 'No episodes yet. Choose Refresh Feed in the menu at the top right.', False)]
    frames = []
    for name, mk, top, text, busy in pages:
        for new in (False, True):
            frames.append((name + '\n' + ('AFTER: centred' if new else 'BEFORE: left, under the header'), hint(s, mk(), top, text, new, busy)))
    os.makedirs(a.outdir, exist_ok=True)
    R.assemble(frames, 4, os.path.join(a.outdir, 'center-hints.png'))


if __name__ == '__main__': main()
