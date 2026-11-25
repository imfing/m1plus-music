#!/usr/bin/env python3
"""Preview of the generated playlist covers (docs/modules/plcover.md): the five styles over four palettes at 144 px with the grid's rounded corners, from the
integer model (tools/pod_plcover.py, the code patch/plcover.c mirrors). Approximate, not AWTK; sample tones.

  uv run python -I tools/preview/preview_plcover.py WORKDIR [OUTDIR]       (WORKDIR: the built release tree, work/mod-release; default OUTDIR out/preview)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from PIL import Image
import preview_icons as PI, pod_plcover as P, pod_wrap

SIDE, GAP, LABEL, SEED = 144, 14, 22, 20261123
A = PI.ALBUMS
PALETTES = [('Kind of Blue', [A[0][2], A[7][2], A[6][2]]), ('A Love Supreme', [A[1][2], A[4][2], A[0][2]]),
            ('Abbey Road', [A[2][2], A[1][2]]), ('Grey', [(120, 120, 120), (60, 60, 60)]), ('One tone', [A[4][2]]), ('No tone', [])]


def cover(style, tones, side=SIDE, seed=SEED):
    return PI.rounded(P.to_image(P.art(style, tones, seed, side)).convert('RGBA'), 8)


def put_name(s, im, x, y, side, name, px):
    """The name on a cover (patch/grid.c grid_plc_name): white, top left, inset 8 % of the side, at most two lines wrapped by pod_wrap (the payload's algorithm) at the style's size, lines 22 px apart from 120 px covers and 18 below."""
    inset, pitch = side * 8 // 100, 22 if side >= 120 else 18
    for k, line in enumerate(pod_wrap.wrap_font(s.font, name, px, side - 2 * inset, 2)):
        s.text(im, x + inset, y + inset + k * pitch + pitch / 2, line, px)


def sheet(s):
    styles = range(P.SOLID, P.BAND + 1)
    w, h = GAP + len(PALETTES) * (SIDE + GAP), GAP + len(styles) * (SIDE + LABEL + GAP)
    im = Image.new('RGBA', (w, h), (0x2A, 0x2A, 0x2A, 255))
    for r, st in enumerate(styles):
        for c, (name, tones) in enumerate(PALETTES):
            x, y = GAP + c * (SIDE + GAP), GAP + r * (SIDE + LABEL + GAP)
            s.text(im, x, y + 9, f'{P.NAMES[st]}  {name}' if c == 0 else name, 14, (0xBB,) * 3)
            im.alpha_composite(cover(st, tones), (x, y + LABEL))
    return im.convert('RGB')


NAMES = ('Road Trip', 'Late Night Jazz Sessions Vol. 3 (Live)', '\u5348\u591c\u7231\u60c5\u6b4c\u66f2\u7cbe\u9009\u96c6\u00b7\u5b89\u9759\u7684\u591c\u665a\u5fc5\u5907')


def named_sheet(s):
    """The styles over the first two palettes with a short, a long and a CJK name at the Songs header's 160 px (18 px text) and at the Cover page's 88 px (14 px)."""
    im = Image.new('RGBA', (GAP + len(NAMES) * 270, 5 * (160 + GAP) + GAP), (0x2A, 0x2A, 0x2A, 255))
    for r, st in enumerate(range(P.SOLID, P.BAND + 1)):
        for c, name in enumerate(NAMES):
            for j, (side, px) in enumerate(((160, 18), (88, 14))):
                x = GAP + c * 270 + (0 if j == 0 else 160 + GAP)
                y = GAP + r * (160 + GAP)
                im.alpha_composite(cover(st, PALETTES[c % 2][1] if st != P.BAND else PALETTES[2][1], side=side), (x, y))
                put_name(s, im, x, y, side, name, px)
    return im.convert('RGB')


def main():
    work = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(HERE)), 'out', 'preview')
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, 'plcover.png')
    sheet(PI.Side(work, True)).save(path)
    print('wrote', path)
    path = os.path.join(out, 'plcover-names.png')
    named_sheet(PI.Side(work, True)).save(path)
    print('wrote', path)


if __name__ == '__main__': main()
