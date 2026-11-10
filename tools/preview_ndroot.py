#!/usr/bin/env python3
"""Mock-up of the Subsonic root page (patch/ndroot.c, docs/modules/subsonic.md): a PIL approximation. The widgets, their positions, glyphs and sizes are read from ui/m1plus_ndroot.bin; the
status line, the footer, the capsule and the "..." card are placed as the payload does (the card is the shared one, preview_icons.view_card).

  preview_ndroot.py WORKDIR OUTDIR

WORKDIR is a built tree (work/mod-release). Writes nd-root-*.png (320 x 450) to OUTDIR: connected, syncing, offline, scrolled (the small title in the navbar, the footer), the "..." card open,
the card while a sync runs, and the page with no server saved (the empty state).
"""
import argparse, os, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import awtk_ui
import preview_icons as PI, preview_songs as PS, preview_settings as PST

W, NAV, SCREEN = PST.W, PST.NAV, PST.SCREEN
GREY = (0xAA, 0xAA, 0xAA)


def status_text(s, state, ago=5, songs=2431):
    """The status line's words for a state (patch/ndroot.c nr_line)."""
    if state == 'syncing': return PS.tr(s, 'Syncing…')
    if state == 'notconnected': return PS.tr(s, 'Not Connected')
    return s.strings.get('Synced %s', 'Synced %s').replace('%s', s.strings.get('%dm ago', '%dm ago').replace('%d', str(ago)))


def page(s, state='connected', scroll=0, search=True, card=False, syncing_card=False, signed=True):
    root = awtk_ui.parse(open(os.path.join(s.tree, PI.RAW, 'ui', 'm1plus_ndroot.bin'), 'rb').read())
    by = {w.name: w for w in root.walk() if w.name}
    im = Image.new('RGBA', (W, SCREEN), (0, 0, 0, 255))
    if not signed:
        big = by['nd_es_big']
        s.text(im, big.x, NAV + big.h / 2, PS.tr(s, 'Subsonic'), 32)
        for n in ('nd_es_icon', 'nd_es_title', 'nd_es_text', 'nd_es_pill', 'nd_es_dl'):
            w = by[n]
            if w.type == 'image': g = s.img(w.get('image')); im.alpha_composite(g, (w.x + (w.w - g.width) // 2, w.y + (w.h - g.height) // 2))
            elif n.endswith('pill') or n.endswith('dl'):
                from PIL import ImageDraw
                ImageDraw.Draw(im).rounded_rectangle((w.x, w.y, w.x + w.w - 1, w.y + w.h - 1), radius=w.h // 2, fill=(0x1E, 0x1E, 0x1E))
                s.text(im, w.x + w.w // 2, w.y + w.h / 2, PS.tr(s, s.shown(w)), 18, anchor='m')
            else: s.text(im, w.x + (w.w // 2 if n != 'nd_es_text' else 0), w.y + 12, PS.fit(s, PS.tr(s, s.shown(w)), 18, w.w), 18, (255, 255, 255) if n == 'nd_es_title' else (0x8E, 0x8E, 0x93), anchor='m' if n == 'nd_es_title' else 'l')
    else:
        y = NAV - scroll
        for c in by['pod_scrollview'].children:
            if c.name == 'nd_top':
                big, st, ic = by['nd_big'], by['nd_status'], by['nd_st_icon']
                s.text(im, big.x, y + big.h / 2, PS.tr(s, 'Subsonic'), 32)
                g = s.img('wf_spin2') if state == 'syncing' else s.img('nd_st_ok' if state == 'connected' else 'nd_st_off')
                im.alpha_composite(g, (ic.x, y + ic.y))
                s.text(im, st.x, y + st.y + st.h / 2, s.clip(status_text(s, state), 15, st.w), 15, GREY)
            elif c.name.startswith('pod_row'):
                for t in c.children:
                    if t.type == 'image': g = s.img(t.get('image')); im.alpha_composite(g, (t.x, y + t.y))
                    elif t.name.startswith('pod_label'): s.text(im, t.x, y + c.h / 2, PS.tr(s, s.shown(t)), 21)
                    elif t.name.startswith('pod_hair'):
                        from PIL import ImageDraw
                        ImageDraw.Draw(im).rectangle((t.x, y + t.y, t.x + t.w - 1, y + t.y), fill=(0x22, 0x22, 0x22))
            elif c.name == 'nd_end':
                f = by['nd_foot']
                s.text(im, f.x, y + f.y + f.h / 2, s.strings.get('%d songs', '%d songs').replace('%d', '2431'), 15, (0x9C, 0x9C, 0x9C))
            y += c.h
    # the navbar over the list: Back, the small title once the large one has gone, the capsule
    from PIL import ImageDraw
    ImageDraw.Draw(im).rectangle((0, 0, W - 1, NAV - 1), fill=(0, 0, 0))
    o = PI.offsets()
    PS.glass(s, im, 'ah_nav_back', 7, 44); PS.glass(s, im, 'ah_nav_play', 260, 60)
    has_search = signed and search
    PS.glass(s, im, 'pod_nav_moremid' if has_search else 'pod_nav_more', 214)
    if has_search: PS.glass(s, im, 'pod_nav_search', o['NAV_CF_X'])
    if signed and scroll >= o['SG_COLLAPSE']:
        px = PI.title_px(s.tree)
        s.text(im, o['NAV_TITLE_X'], 25, PS.fit(s, PS.tr(s, 'Subsonic'), px, (o['NAV_CF_X'] if has_search else 214) - o['NAV_TITLE_X']), px)
    if card:
        im.alpha_composite(Image.new('RGBA', im.size, (0, 0, 0, 0x82)))
        rows = [('Sync Now', 'pod_ic_vsrefresh', False, None), ('Server Settings', 'pod_ic_vsserver', False, None)] if signed else [('Server Settings', 'pod_ic_vsserver', False, None)]
        PI.view_card(s, im, rows, f'vs_glass{len(rows)}', (), 0 if syncing_card else None)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('workdir'); ap.add_argument('outdir')
    a = ap.parse_args()
    s = PI.Side(a.workdir, True)
    os.makedirs(a.outdir, exist_ok=True)
    panels = [('nd-root-connected', page(s)), ('nd-root-syncing', page(s, 'syncing')), ('nd-root-offline', page(s, 'offline')), ('nd-root-notconnected', page(s, 'notconnected')),
              ('nd-root-scrolled', page(s, scroll=60)), ('nd-root-card', page(s, card=True)), ('nd-root-nosearch', page(s, search=False)), ('nd-root-empty', page(s, signed=False, search=False)),
              ('nd-root-empty-card', page(s, signed=False, card=True))]
    for name, im in panels: im.convert('RGB').save(os.path.join(a.outdir, name + '.png'))
    print('wrote', len(panels), 'panels to', a.outdir)


if __name__ == '__main__':
    main()
