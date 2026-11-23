"""Glass pieces (mod_icons.glass_image, the Home mini bar's pane): the shared glass stays as it was, and the navbar glass buttons are the generator's output. (The album page's
Play pill and Shuffle disc and Now Playing's star and More discs are solid or flat, not glass: test/pod/albumpage.py, test/pod/nowplaying.py.)"""
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import mod_icons
from PIL import Image


def run(ctx):
    expect = ctx.expect
    def shipped(n): return open(asset_path(n), 'rb').read()
    G = mod_icons.glass_image
    def over(im, x, y, bg):
        p = im.getpixel((x, y)); return tuple(round((p[3] * c + (255 - p[3]) * bg) / 255) for c in p[:3])

    # the shared glass is untouched: the mini bar and the lock card are still the generator's output with the same arguments
    for n, im in (('mb_glass', G(*mod_icons.GLASS, False)), ('mb_glass_down', G(*mod_icons.GLASS, True)), ('lk_card', G(*mod_icons.GLASS_CARD, fill=mod_icons.GLASS_CARD_FILL))):
        expect(same_pixels(shipped(n), im), f'{n}.png is still glass_image output, pixel for pixel')

    # ---- the navbar's glass buttons (mod_icons.ah_nav_images; docs/modules/navbar.md): every image as wide as the real button it sits in
    N, H_, GL = mod_icons.AH_NAV_NAMES, mod_icons.GLASS_H, mod_icons.GLASS_GLYPH
    gen = mod_icons.ah_nav_images()
    expect(H_ == 42 and sorted(gen) == sorted(N) and len(N) == 2 * (len(mod_icons.AH_NAV_PIECES) + 1) and all(same_pixels(shipped(n), gen[n]) for n in N),
           f'the {len(N)} ah_nav_* PNGs are the generator\'s output pixel for pixel')
    # the select mode's chrome (mod_icons.selbar_images): the Select All glass (patch3_x) and the bottom capsule's slots (normal, pressed, dimmed), shipped pixel for pixel
    sel = mod_icons.selbar_images()
    expect(sorted(sel) == mod_icons.SELBAR_NAMES and len(sel) == 2 + 3 * len(mod_icons.SELBAR_PIECES) and all(same_pixels(shipped(n), sel[n]) for n in sel)
           and all(asset_image(n).size == (60, 42) for n in sel if n.startswith('sg_bar_')) and asset_image('sg_selall_glass').size == (72, 42),
           'the select mode\'s glass images are the generator\'s output: Select All 72 x 42, every bar slot 60 x 42 (capsule cuts of 120 / 60 px)')
    # independent of mod_icons.glass_piece: (width, glass columns, glyph centre) of every image, and its capsule (image columns) when it is a slice: the Pod pages' right cap of the 141 px capsule, its glass from 7 (the slots' 7 px shift)
    want = {'ah_nav_back': (42, 0, 42, 21), 'ah_nav_close': (42, 0, 42, 21), 'ah_nav_done': (42, 0, 42, 21), 'ah_nav_np': (60, 9, 51, 30), 'ah_nav_set': (60, 9, 51, 30),
            'ah_nav_play': (60, 7, 51, 30, (-90, 51))}
    PD = 36   # a pressed slice: the rest glass and a white disc of PD px, 14 % opaque, on the glyph's centre (3 px of glass above and below)
    def highlight(out, cx):
        d = mod_icons.disc(PD, (255, 255, 255)); d.putalpha(d.getchannel('A').point(lambda v: round(v * 0.14)))
        out.alpha_composite(d, (cx - PD // 2, (H_ - PD) // 2)); return out
    def ref_of(n, pressed):
        w, x0, x1, cx, *cap = want[n]
        out = Image.new('RGBA', (w, H_), (0, 0, 0, 0))
        if cap:
            (c0, c1), = cap
            out.alpha_composite(G(c1 - c0, H_, 21, False).crop((x0 - c0, 0, x1 - c0, H_)), (x0, 0))
            return highlight(out, cx) if pressed else out
        out.alpha_composite(G(x1 - x0, H_, 21, pressed), (x0, 0)); return out
    expect((mod_icons.NAV_PRESS_D, mod_icons.NAV_PRESS_ALPHA) == (PD, 0.14), 'a pressed capsule piece\'s highlight: a white disc of 36 px, 14 % opaque')
    bad = []
    for n in N:
        base = n[:-5] if n.endswith('_down') else n
        im, r = asset_image(n), ref_of(base, n.endswith('_down'))
        glyph = [(x, y) for y in range(im.height) for x in range(im.width) if im.getpixel((x, y)) != r.getpixel((x, y))]
        gx0, gx1, gy0, gy1 = min(p[0] for p in glyph), max(p[0] for p in glyph), min(p[1] for p in glyph), max(p[1] for p in glyph)
        ok = (im.size == r.size and gx1 - gx0 + 1 <= GL and gy1 - gy0 + 1 <= GL
              and abs((gx0 + gx1) / 2 - want[base][3]) <= 1.5 and abs((gy0 + gy1) / 2 - H_ / 2) <= 1.5)
        if not ok: bad.append(n)
    expect(not bad, f'every ah_nav_* image is its glass (a disc, or a cap of a capsule, pressed with the round highlight) at its columns with a glyph of at most {GL} px centred on its column, otherwise the glass byte for byte ({bad})')
    # the Pod pages' capsule pieces (pod_nav_*) glue into ONE capsule: Cover Flow / "..." (46 at x 168), toggle (46 at 214), Now Playing (60 at 260): glass 170 .. 311
    plain = lambda pos, pressed=False: mod_icons.capsule_piece(pos, None, pressed)
    # every piece drawn where AWTK puts it (its image centred on its button: a slot's 60 px image at slot - 7, Now Playing's at 260), window columns from x0
    def glued_at(pieces, x0):
        out = Image.new('RGBA', (320 - x0, H_), (0, 0, 0, 0))
        for p, x in pieces:
            im, bw = plain(p), (60 if p == 'right' else 46)
            out.alpha_composite(im, (x + (bw - im.width) // 2 - x0, 0))
        return out
    def capsule_at(c0, x0):
        full = Image.new('RGBA', (320 - x0, H_), (0, 0, 0, 0)); full.alpha_composite(G(311 - c0, H_, 21), (c0 - x0, 0)); return full
    expect(list(capsule_at(177, 161).getdata()) == list(glued_at((('left', 168), ('middle', 214), ('right', 260)), 161).getdata()),
           f'Cover Flow | toggle | Now Playing: the three pieces on main\'s 46 / 46 / 60 px slots glue into the 134 x {H_} capsule (x 177 .. 311) exactly, no seam')
    # the Songs page's navbar is "..." (left cap, 214) | Now Playing, as on Artists, and on an artist's songs Cover Flow | "..." (middle) | Now Playing, as on Albums; Select takes the "..." place where its card would hold Select alone; the Sort piece is gone
    expect(not {'pod_nav_songsort'} & (set(mod_icons.NAV_VIEW) | set(mod_icons.NAV_VIEW_POS)) and 'NAV_SEARCH_X' not in O
           and mod_icons.NAV_VIEW_POS['pod_nav_select'] == 'middle' and mod_icons.NAV_VIEW['pod_nav_select'] == 'list-checks'
           and mod_icons.NAV_VIEW_POS['pod_nav_more'] == 'left' and mod_icons.NAV_VIEW_POS['pod_nav_moremid'] == 'middle',
           'the Songs capsule is [... | Now Playing] (or [Cover Flow | ... | Now Playing]); where the card would hold Select alone the "..." is Select (pod_nav_select as the middle piece after Search / Cover Flow); the Sort middle is gone')
    # the Albums page's capsule is the three slots 168 / 214 / 260: Cover Flow (left), "..." (middle), Now Playing (right), the pieces glued as above; no Search, so no middle Cover Flow piece
    expect(mod_icons.NAV_VIEW_POS['pod_nav_coverflow'] == 'left' and mod_icons.NAV_VIEW_POS['pod_nav_moremid'] == 'middle' and 'pod_nav_coverflowmid' not in mod_icons.NAV_VIEW
           and 'pod_nav_coverflowmid' not in mod_icons.NAV_VIEW_POS and mod_icons.NAV_VIEW_POS['pod_nav_search'] == 'left', 'Cover Flow | ... | Now Playing: left, middle, right pieces; the Cover Flow middle piece is gone with the Search button')
    # a genre's songs have no Search (the stock navbar leaves it out for class 0xff09): Select as the left cap (pod_nav_selectl, runtime icon of btn_select at 214) and Now Playing, an 88 px capsule, glass 223 .. 311
    expect(list(capsule_at(223, 207).getdata()) == list(glued_at((('left', 214), ('right', 260)), 207).getdata()),
           f'Select (left cap) | Now Playing: the two pieces of the slots 214 / 260 glue into the 88 x {H_} capsule (x 223 .. 311) exactly, no seam')
    expect(mod_icons.NAV_VIEW_POS['pod_nav_selectl'] == 'left' and mod_icons.NAV_VIEW['pod_nav_selectl'] == 'list-checks',
           'pod_nav_selectl is the left-cap piece of the list-checks glyph')
    # the Extras page's Settings button: the same left cap (so Settings | Now Playing glues as the two-piece capsule above), with the Lucide sliders-horizontal glyph the Settings row's icon uses
    expect(mod_icons.NAV_VIEW_POS['pod_nav_settings'] == 'left' and mod_icons.NAV_VIEW['pod_nav_settings'] == 'sliders-horizontal'
           and mod_icons.POD_ROWS['Settings'][1] == 'sliders-horizontal' and mod_icons.capsule_piece('left', 'sliders-horizontal', False).size == (60, H_)
           and list(mod_icons.capsule_piece('left', 'sliders-horizontal', True).getdata()) != list(mod_icons.capsule_piece('left', 'sliders-horizontal', False).getdata()),
           'pod_nav_settings is the left-cap piece of sliders-horizontal, the Settings row\'s glyph; its _down differs (the round highlight)')
    # Cover Flow's artist page: Songs (left cap at 214) | Now Playing (ah_nav_play, set at run time): the same two pieces as the Artists page's "...", one 95 px capsule
    expect(mod_icons.NAV_VIEW_POS['pod_nav_listl'] == 'left' and 'pod_nav_allalbums' not in mod_icons.NAV_VIEW and 'pod_nav_allalbums' not in mod_icons.NAV_VIEW_POS
           and mod_icons.NAV_VIEW_POS['pod_nav_more'] == 'left' and 'pod_nav_artist' not in mod_icons.NAV_VIEW and 'pod_nav_albumartist' not in mod_icons.NAV_VIEW_POS and O['NAV_VIEW_X'] + O['NAV_VIEW_W'] == 260,
           'Cover Flow\'s artist page: Songs is a left cap at 214 and Now Playing (ah_nav_play) the right cap at 260 (glued exactly as Select | Now Playing above, glass 223 .. 311); no All albums disc')
    # a pressed slice is the rest slice but for a round highlight on its glyph, inside its button and its glass: the capsule keeps one pane, no lit block
    slices = [(f'pod {p}', plain(p), plain(p, True), mod_icons.CAPSULE_PIECES[p][3], mod_icons.CAPSULE_PIECES[p][1:3], mod_icons.NAV_SLOT_W if p != 'right' else 60)
              for p in ('left', 'middle', 'right')]
    bad = []
    for n, rest, down, cx, (x0, x1), bw in slices:
        diff = [(x, y) for y in range(H_) for x in range(rest.width) if rest.getpixel((x, y)) != down.getpixel((x, y))]
        lo = (rest.width - bw) // 2   # the button's first image column
        inside = all((x + 0.5 - cx) ** 2 + (y + 0.5 - H_ / 2) ** 2 <= (PD / 2 + 1) ** 2 for x, y in diff)   # its anti-aliased edge
        lit = sum(down.getpixel((cx, 6))[:3]) > sum(rest.getpixel((cx, 6))[:3]) and down.getpixel((cx, 2)) == rest.getpixel((cx, 2))
        if not (diff and inside and lit and x0 <= cx - PD // 2 and cx + PD // 2 <= x1 and lo <= cx < lo + bw): bad.append(n)
    expect(not bad, f'a pressed capsule piece differs from its rest piece only in a {PD} px disc on its glyph (lighter; the rim untouched), inside its glass, the glyph inside its button ({bad})')
    expect(mod_icons.NAV_SLOT_W + mod_icons.NAV_SLOT_W + mod_icons.NAV_PLAY_W == 152 and 177 + 134 == 311 == 290 + 21 and mod_icons.NAV_SHIFT == 7
           and [s + 23 + 7 for s in (122, 168, 214)] + [290] == [152, 198, 244, 290],
           'the capsule ends 21 px (the cap radius) right of Now Playing\'s glyph column 290; its slots are 168 + 46 + 46 = 260, Now Playing at 260 (main\'s); '
           'each slot\'s glyph 7 px right of its centre, so the glyphs are 46 apart up to Now Playing\'s (152 / 198 / 244 / 290)')
    for n, pos in mod_icons.NAV_VIEW_POS.items():
        for sfx, pressed in (('', False), ('_down', True)):
            im, r = asset_image(n + sfx), plain(pos, pressed)
            glyph = [(x, y) for y in range(im.height) for x in range(im.width) if im.getpixel((x, y)) != r.getpixel((x, y))]
            cx = 37
            expect(im.size == r.size and glyph and abs((min(p[0] for p in glyph) + max(p[0] for p in glyph)) / 2 - cx) <= 1.5 and max(p[1] for p in glyph) - min(p[1] for p in glyph) + 1 <= GL,
                   f'{n}{sfx}: the {pos} piece with its glyph on the slot\'s centre column + 7 ({cx} in its 60 px image)')
    # contrast of the white glyphs over the glass over pure white / black
    rep = []
    for pressed in (False, True):
        for bgv in (255, 0):
            worst_ = 99
            for n in [*N, *(k + s for k in mod_icons.NAV_VIEW_POS for s in ('', '_down'))]:
                if n.endswith('_down') != pressed: continue
                base = n[:-5] if n.endswith('_down') else n
                im = asset_image(n)
                r = ref_of(base, pressed) if base in want else plain(mod_icons.NAV_VIEW_POS[base], pressed)
                pts = [(x, y) for y in range(im.height) for x in range(im.width) if im.getpixel((x, y)) != r.getpixel((x, y)) and im.getpixel((x, y))[3] >= 250]
                worst_ = min(worst_, min(contrast((255, 255, 255), over(r, x, y, bgv)) for x, y in pts))
            rep.append(f'{"pressed" if pressed else "rest"}/{"white" if bgv else "black"}: {worst_:.2f}')
            expect(worst_ >= 4.5, f'the white glyphs of the navbar buttons over glass over pure {"white" if bgv else "black"}, {"pressed" if pressed else "rest"}: {worst_:.2f}:1 (>= 4.5)')
    print('  navbar buttons glyph contrast: ' + '; '.join(rep))
