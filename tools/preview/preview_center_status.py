#!/usr/bin/env python3
"""DESIGN PREVIEW: the pages' empty line and loading spinner, before (centred in the window, y 225) and after (centred in the room under the header the page keeps:
tools/pod_ui.py room_y, patch/libsrc.c ls_room, docs/modules/ui-rules.md "Empty and loading states").

  preview_center_status.py WORKDIR [OUTDIR]      (WORKDIR: a built tree, work/mod-release; OUTDIR defaults to out/preview)

Writes OUTDIR/center-status.png: before / after pairs. The headers are simplified (the navbar's glass and, where the page keeps it, the large title). Not pixel-exact AWTK."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preview_podcasts_revamp as R
import preview_center_hints as H
import preview_icons as PI
import mod_icons as M
import pod_show, pod_ui
from stb_raster import _paste

NAV, STAT = R.NAV, R.STAT
SPIN = 14


def page(s, title, text, new, px=20):
    """One frame: `title` the large title the page keeps over no rows ('' for none), `text` the line (None: the spinner)."""
    fr = H.simple_page(s, title, 0)
    top = NAV + (R.O['SG_TITLE_H'] if title else 0)
    mid = pod_ui.room_y(0, top) if new else pod_ui.CLIENT_H // 2   # the block's centre, window y
    if text is None: _paste(fr, M.wifi_spinner(0), (R.W - SPIN) // 2, STAT + mid - SPIN // 2)
    else: s.text(fr, R.W // 2, STAT + mid, text, px, H.SUB_RGB, 'm')
    return fr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir', nargs='?', default='out/preview')
    a = ap.parse_args()
    R.FONT, R.IMGS = pod_show.Font(pod_show.font_path(a.workdir)), M.podcast_images()
    s = PI.Side(a.workdir, True)
    pages = [('Library Artists, empty', '', 'Update Local Music first', 20),
             ('Radio: Loading...', '', 'Loading…', 18),
             ('Folders: Empty folder', '', 'Empty folder', 20),
             ('Navidrome Artists, loading', 'Artists', None, 20),
             ('Navidrome Playlists, empty', 'Playlists', 'No playlists', 20),
             ('Navidrome Songs, loading', 'Songs', None, 20)]
    frames = []
    for name, title, text, px in pages:
        for new in (False, True):
            frames.append((name + '\n' + ('AFTER: centred under the header' if new else 'BEFORE: centred in the window'), page(s, title, text, new, px)))
    os.makedirs(a.outdir, exist_ok=True)
    R.assemble(frames, 4, os.path.join(a.outdir, 'center-status.png'))


if __name__ == '__main__': main()
