#!/usr/bin/env python3
"""Approximate PIL mock-up of the Add to Playlist picker (patch/playlists.c pick mode, docs/modules/picker.md): the Playlists page in list mode under a
navbar with Back and the title only, the first rows "New playlist" (a plus) and "Favorites" (a star), no count, then the playlists; one panel at rest, one with a row
held down, and one where Favorites and two playlists hold every song being added (the grey tick). Not pixel-exact AWTK.

  preview_picker.py WORKDIR OUT.png [--lang CODE]

WORKDIR is a built tree (work/mod-release); the rows are preview_icons.playlists_grid(pick=True), the layout model the Playlists page's list mode uses.
"""
import argparse, os, sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import preview_icons as PI


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('out'); ap.add_argument('--lang', default='en_US')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True, a.lang)
    panels = [('Add to Playlist: at rest', PI.playlists_grid(s, list_mode=True, row_pressed=-1, pick=True)),
              ('A playlist row held down', PI.playlists_grid(s, list_mode=True, row_pressed=3, pick=True)),
              ('Already there: the grey tick', PI.playlists_grid(s, list_mode=True, row_pressed=-1, pick=True, have=('Favorites', 'Evening Jazz', 'Late Night')))]
    pad, lab = 12, 20
    sheet = Image.new('RGB', (len(panels) * (320 + pad) + pad, 450 + lab + 2 * pad), (0x2A, 0x2A, 0x2A)); d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panels):
        x = pad + i * (320 + pad)
        d.text((x, pad), title, fill=(0xAA,) * 3, font=PI.ANN); sheet.paste(im.convert('RGB'), (x, pad + lab))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    PI.save_compact(sheet, a.out)
    print('wrote', a.out, sheet.size)


if __name__ == '__main__': main()
