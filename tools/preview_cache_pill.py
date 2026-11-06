#!/usr/bin/env python3
"""Mockups of the Home cache pill and the status-bar sync icon (docs/modules/homecover.md; approximate, not AWTK). Design A of the foreground-cache banner
(tools/preview_cache_banner.py of that branch): a 40 px capsule, x 12 w 296, #1C1C1C, 15 px #AAAAAA text, the list shifted down by the block; here with a thin progress
bar inside (the Podcasts refresh dialog's track #FFFFFF33 / fill #EBEBEB) and a stop button, and the static sync icon (Lucide refresh-cw) in view_bar_right of the status bar, right after the Bluetooth box.

  uv run python -I tools/preview_cache_pill.py TREE [OUTDIR]     (TREE: a built tree, e.g. out/dev/<tag>/tree; default OUTDIR out/mockups/cache-pill)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw
import preview, pod_ui as U, preview_dailymix as PD, preview_icons as PI, mod_icons as M, awtk_ui

K = 4
CARD, GREY, WHITE, FILL, BTN = (0x1C,) * 3, (0xAA,) * 3, (255, 255, 255), (0xEB,) * 3, (0x2C, 0x2C, 0x2E)
TOP = getattr(U, 'HOME_PAD', 10)
PILL_H, PILL_X, PILL_W, BLOCK = 40, 12, 296, 48        # capsule, its x / width, and the block the list moves down by (capsule + 8 air)
BAR = 30                                               # the status bar's height (PI.BAR)
ICON = 18                                              # the sync icon's canvas (as bar_digital 18 x 18; ink 16 at the 1.5 px status stroke)


def rr(im, box, r, fill):
    x0, y0, x1, y1 = box; w, h = x1 - x0, y1 - y0
    m = Image.new('L', (w * K, h * K), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * K - 1, h * K - 1), radius=r * K, fill=255)
    a = fill[3] if len(fill) == 4 else 255
    layer = Image.new('RGBA', (w, h), tuple(fill[:3]) + (255,))
    layer.putalpha(m.resize((w, h), Image.LANCZOS).point(lambda v: v * a // 255))
    im.alpha_composite(layer, (x0, y0))


def pill(s, text, frac, button):
    """The capsule strip (320 x BLOCK): text on the upper line, a 4 px bar under it; button: a 28 px circle with a white x at the right end (text and bar stop short of it)."""
    im = Image.new('RGBA', (320, BLOCK), (0, 0, 0, 255))
    rr(im, (PILL_X, 0, PILL_X + PILL_W, PILL_H), PILL_H // 2, CARD)
    x0 = PILL_X + 18; right = PILL_X + PILL_W - (48 if button else 18)
    s.text(im, x0, 14, s.clip(text, 15, right - x0), 15, GREY)
    bw = right - x0
    rr(im, (x0, 26, x0 + bw, 30), 2, (255, 255, 255, 0x33))
    if frac is not None: rr(im, (x0, 26, x0 + max(4, int(bw * frac)), 30), 2, FILL)   # (None: the waiting state, an empty bar)
    if button:
        d = 28; bx = PILL_X + PILL_W - 6 - d; by = (PILL_H - d) // 2
        rr(im, (bx, by, bx + d, by + d), d // 2, BTN)
        g = M.glyph_fit('x', 14, 14, WHITE, 0, 1.5)
        im.alpha_composite(g, (bx + (d - 14) // 2, by + (d - 14) // 2))
    return im


def home(s, strip, sec, bar_args):
    base = preview.minibar_page(s, *bar_args, shelf=(preview.SHELF_ALBUMS,), daily=sec, scroll=0).convert('RGBA')
    if strip is None: return base
    page = Image.new('RGBA', base.size, (0, 0, 0, 255))
    page.paste(base.crop((0, TOP, 320, 450 - TOP)), (0, TOP + BLOCK))
    page.alpha_composite(strip, (0, TOP))
    page.paste(base.crop((0, U.MB_Y - 2, 320, 450)), (0, U.MB_Y - 2))
    return page


def status_bar(s, tree, icon=None, vol='50'):
    """The real bar at 320 x 30 with the sync icon shown (or not): the right group is stacked right to left from the battery gap, Wi-Fi, [sync icon], Bluetooth (its 47 px box ends in the glyph),
    as view_bar_right lays it out with pod_sync visible after img_btclass (SyncLink hidden). Drawn by tools/preview_icons.py asset_bar, whose Bluetooth and Wi-Fi are erased and placed again."""
    sysbar = awtk_ui.parse(open(os.path.join(tree, PI.RAW, 'ui', 'system_bar.bin'), 'rb').read())
    im = Image.new('RGBA', (320, BAR), (0, 0, 0, 255))
    PI.asset_bar(s, sysbar, im, vol=vol)
    ImageDraw.Draw(im).rectangle((88, 0, 112, BAR - 1), fill=(0, 0, 0))     # the digital-out glyph asset_bar draws (the real one shows only on digital out)
    right = sysbar.find('view_bar_right'); sizes = {c.name: c.w for c in right.children}
    ImageDraw.Draw(im).rectangle((195, 0, right.x + right.w - 1, BAR - 1), fill=(0, 0, 0))
    x = right.x + right.w
    for name, img in (('img_wifi', s.img('bar_wifi3')), ('pod_sync', icon), ('img_btclass', s.img('bar_btcon'))):
        if img is None: continue
        x -= sizes[name]; im.alpha_composite(img, (x + sizes[name] - img.width if name != 'pod_sync' else x, (BAR - img.height) // 2)); x -= 4
    return im


def zoom(im, box, k=4):
    c = im.crop(box); return c.resize((c.width * k, c.height * k), Image.NEAREST)


def main():
    tree = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(preview.build.ROOT, 'out', 'mockups', 'cache-pill')
    os.makedirs(out, exist_ok=True)
    s = PD.side(tree)
    sec = PD.section_image(s, PD.PALETTES[0][1])
    bar_args = ('Blue in Green (Remastered, Mono Version)', 'Miles Davis', (70, 110, 190))
    items = []
    def save(name, cap, im):
        p = os.path.join(out, name); im.convert('RGB').save(p); print('wrote', p, im.size); items.append((cap, im.convert('RGB')))
    icon = M.glyph_fit('refresh-cw', ICON, ICON, WHITE, 1, 1.5)
    def with_bar(page, ic):   # the status bar (30 px) above the 450 px window, as on the 480 px screen
        p = Image.new('RGBA', (320, BAR + page.height), (0, 0, 0, 255)); p.paste(status_bar(s, tree, ic), (0, 0)); p.paste(page, (0, BAR)); return p
    save('home-now.png', 'Home today (no pill, no icon)', with_bar(home(s, None, sec, bar_args), None))
    for tag, text, frac in (('waiting', 'Checking library...', None), ('covers', 'Preparing covers 120/840', 120 / 840), ('tracks', 'Measuring tracks 300/4000', 300 / 4000)):
        save(f'pill-{tag}-b.png', f'{tag}: pill with x + icon right of Bluetooth', with_bar(home(s, pill(s, text, frac, True), sec, bar_args), icon))
    # the status bar's right half, 4x: no icon, icon shown (vol 50), icon shown with a 100 volume label
    rows = [zoom(status_bar(s, tree, ic, vol=v), (140, 0, 320, BAR)) for ic, v in ((None, '50'), (icon, '50'), (icon, '100'))]
    sheet = Image.new('RGB', (rows[0].width, len(rows) * (BAR * 4 + 8)), (0x2A,) * 3)
    for i, r in enumerate(rows): sheet.paste(r.convert('RGB'), (0, i * (BAR * 4 + 8)))
    save('icons-4x.png', 'status bar right half 4x: no icon, icon shown, icon shown (vol 100)', sheet)
    # a non-Home page: the Settings menu page (any page shows the same global bar)
    try:
        pg = preview.menu_page(s, None, home=False).convert('RGBA')
        save('other-page.png', 'other page (global bar, icon shown)', with_bar(pg, icon))
    except Exception as e: print('other page skipped', e)
    sheet = PD.labelled(items, 4)
    p = os.path.join(out, 'contact-sheet.png'); sheet.save(p); print('wrote', p, sheet.size)


if __name__ == '__main__':
    main()
