"""Built assets: the M1+ Music pages are dark with light text and inside the window, the default wallpaper, the icon set and the battery art."""
import hashlib, os, re, struct
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

DARK = ('#000000', '#1E1E1E', '#2A2A2A', '#00000000')


def is_dark(c): return c in DARK or (len(c) >= 7 and int(c[1:3], 16) < 0x40 and int(c[3:5], 16) < 0x40 and int(c[5:7], 16) < 0x40)
def is_light(c): return len(c) >= 7 and min(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)) >= 0xa0


def run(ctx):
    expect = ctx.expect
    ui_dir = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui')

    # 25. Contrast in the built assets: every button we style inline has a dark background and
    #     light text in every widget state (theme-styled navbar buttons excepted).
    for asset_name in ('m1plus_menu.bin', 'm1plus_cover.bin', 'm1plus_artists.bin', 'm1plus_shuffle.bin', 'm1plus_settings.bin', 'm1plus_library.bin', 'm1plus_homeset.bin'):
        tree = awtk_ui.parse(open(os.path.join(ui_dir, asset_name), 'rb').read())
        for w in tree.walk():
            if w.type == 'list_item':   # rows: stock's widget and theme styles, as sysset's rows
                labs = [c for c in w.children if c.type == 'hscroll_label']
                expect(w.get('style') == 'list_item_style' and labs
                       and labs[0].get('style') == 'srlabel_leftwhite21_style',
                       f'{asset_name}:{w.name} is a stock-styled row')
            if w.type != 'button' or w.get('style'): continue
            if w.name.startswith('vs_item'): continue   # the "..." card's rows press as a translucent white over the card's glass (test/pod/albums.py card_asset_tests)
            bad = [st for st in STATES if not is_dark(w.get(f'style:{st}:bg_color', ''))
                   or not is_light(w.get(f'style:{st}:text_color', ''))]
            expect(not bad, f'{asset_name}:{w.name} is dark with light text in every state ({bad})')
        for w in tree.children:   # the window's own children (scroll content may extend below)
            expect(w.y + w.h <= CLIENT_H,
                   f'{asset_name}:{w.name or w.type} ends inside the 450 px window ({w.y}+{w.h})')

    # 25b. Every image a UI file names exists: a widget's image / icon / bg_image / fg_image (also in a style state) is a file of the built tree (a removed or renamed image shows nothing on the device).
    have = {os.path.splitext(f)[0] for _, _, fs in os.walk(os.path.join(WORK, 'rootfs', 'release/assets')) for f in fs}
    missing = sorted({(a, w.name, v) for a in os.listdir(ui_dir) if a.startswith('m1plus_') and a.endswith('.bin')
                      for w in awtk_ui.parse(open(os.path.join(ui_dir, a), 'rb').read()).walk() for k, v in w.props
                      if k.rsplit(':', 1)[-1] in ('image', 'icon', 'bg_image', 'fg_image') and v and v not in have})
    expect(not missing, f'every image the m1plus_*.bin widgets name is in the built tree ({missing[:6]})')

    # 39. The default lock screen wallpaper: screensaver_default.png (the resource name demo keeps as
    #     SCREENSAVERPATH when no custom picture is set) is the drawn bokeh field, a 320x480 PNG
    #     under 16 KB; the other files are left alone and no theme shadows it.
    assets = os.path.join(WORK, 'rootfs', 'release', 'assets')
    img = os.path.join(assets, 'default', 'raw', 'images', 'xx', 'screensaver_default.png')
    data = open(img, 'rb').read()
    expect(data[:8] == b'\x89PNG\r\n\x1a\n' and struct.unpack('>II', data[16:24]) == (320, 480) and len(data) <= 16000,
           f'screensaver_default.png is a 320x480 PNG of {len(data)} bytes (<= 16,000)')
    import mod_wallpaper
    expect(hashlib.sha256(data).hexdigest() == mod_wallpaper.ASSET_SHA, 'it is assets/bokeh-320x480.png')
    expect(not any(f.startswith('screensaver_default.') for t in os.listdir(assets) if t != 'default'
                   for _, _, fs in os.walk(os.path.join(assets, t)) for f in fs),
           'no other theme carries a screensaver_default that would shadow it')
    expect(os.path.getsize(os.path.join(os.path.dirname(img), 'screensaver_default1.png')) == 521927, 'screensaver_default1.png is untouched')
    lock = awtk_ui.parse(open(os.path.join(ui_dir, 'screensaver_page.bin'), 'rb').read())
    expect(any(w.name == 'img_screensaver' for w in lock.walk()), 'the lock screen still has the img_screensaver the app feeds')

    # 39b. The lock screen's glass card (mod_icons.glass_image, mod_lockscreen): the card's whole look is lk_card, no fill or radius of
    #      its own; the mini bar's glass PNGs are still the generator's output pixel for pixel (the generator is shared); the white title
    #      (7:1) and the #DDDDDD artist (4.5:1) hold over every pixel of their boxes with the glass over pure white and pure black.
    import mod_icons
    from PIL import Image
    xx = os.path.join(assets, 'default', 'raw', 'images', 'xx')
    card = lock.find('view_bottomview')
    expect(all(card.get(f'style:{st}:bg_image') == 'lk_card' and card.get(f'style:{st}:bg_color') == '#00000000'
               and card.get(f'style:{st}:round_radius') is None for st in ('normal', 'disable', 'focused')),
           'the lock card is the lk_card glass image, no fill or radius of its own')
    for n, pressed in (('mb_glass', False), ('mb_glass_down', True)):
        expect(same_pixels(os.path.join(mod_icons.PNG, n + '.png'), mod_icons.glass_image(*mod_icons.GLASS, pressed))
               and open(os.path.join(xx, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read(),
               f'{n}.png is the glass generator output, pixel for pixel (size {mod_icons.GLASS[:2]}, r {mod_icons.GLASS[2]})')
    lk = Image.open(os.path.join(xx, 'lk_card.png')).convert('RGBA')
    expect(same_pixels(os.path.join(mod_icons.PNG, 'lk_card.png'), mod_icons.glass_image(*mod_icons.GLASS_CARD, fill=mod_icons.GLASS_CARD_FILL))
           and lk.size == (card.w, card.h) == mod_icons.GLASS_CARD[:2] and lk.getpixel((0, 0))[3] == 0 and lk.getpixel((card.w - 1, card.h - 1))[3] == 0
           and 0.6 * 255 <= lk.getpixel((card.w // 2, card.h - 3))[3] <= 0.8 * 255,
           f'lk_card.png is {lk.size} (the card), translucent, the corners transparent, the generator output')
    lc = lambda im, x, y, bg: tuple(round((im.getpixel((x, y))[3] * c + (255 - im.getpixel((x, y))[3]) * bg) / 255) for c in im.getpixel((x, y))[:3])
    hexrgb = lambda s: tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))
    worst = {}      # (label, background level) -> worst ratio over the label's box
    for lab in ('view_scrlabel_title', 'view_scrlabel_artist'):
        w = lock.find(lab); hexc = hexrgb(w.get('style:normal:text_color'))
        for bg in (255, 0):
            worst[lab, bg] = min(contrast(hexc, lc(lk, x, y, bg)) for y in range(w.y, w.y + w.h) for x in range(w.x, w.x + w.w, 2))
    wt, wa = worst['view_scrlabel_title', 255], worst['view_scrlabel_artist', 255]
    print(f'  lock card glass over white: title >= {wt:.2f}:1, artist >= {wa:.2f}:1; over black: {worst["view_scrlabel_title", 0]:.1f}:1, {worst["view_scrlabel_artist", 0]:.1f}:1')
    expect(wt >= 7 and wa >= 4.5, f'over a pure white wallpaper: the white title {wt:.2f}:1 (>= 7), the #DDDDDD artist {wa:.2f}:1 (>= 4.5)')
    expect(worst['view_scrlabel_title', 0] >= 7 and worst['view_scrlabel_artist', 0] >= 4.5, 'and over a pure black one')

    # 40. The icon set: every replaced stock image is the committed Tabler PNG, byte for byte; the
    #     row icons the menu and the Shuffle page use are added and every row names one of them.
    import battery_art, mod_battery, mod_icons
    img_dir = os.path.join(WORK, mod_icons.IMG)
    names = mod_icons.replaced_names()
    # the three battery state images are the unified battery drawing, not Tabler
    own = {n: battery_art.png(battery_art.STATUS, s) for n, s in mod_battery.STATE.items()}
    tabler = [n for n in names if n not in own]
    differ = [n for n in tabler if open(os.path.join(img_dir, n + '.png'), 'rb').read() != open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read()]
    expect(not differ and len(tabler) > 100, f'{len(tabler)} replaced images are the committed PNGs (differ: {differ[:3]})')
    expect(all(open(os.path.join(img_dir, n + '.png'), 'rb').read() == png for n, png in own.items() if n in names) or not set(own) & set(names),
           'the status bar battery images are battery_art.png(STATUS)')
    added = mod_icons.pod_names()
    expect(all(open(os.path.join(img_dir, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read() for n in added),
           f'the {len(added)} M1+ Music row icons are added from the committed PNGs')
    used = set()
    for key in mod_icons.POD_UI:
        tree = awtk_ui.parse(open(os.path.join(ui_dir, key + '.bin'), 'rb').read())
        for row in [w for w in tree.walk() if w.type == 'list_item']:
            ic = [c for c in row.children if c.name == 'pod_icon']
            expect(len(ic) == 1 and ic[0].get('image') in added and ic[0].get('sensitive') == 'false',
                   f'{key}:{row.name} has one insensitive icon image from the added set')
            used.update(c.get('image') for c in ic)
            lab = next(c for c in row.children if c.type == 'hscroll_label'); hair = [c for c in row.children if c.name == 'pod_hair']
            expect((ic[0].x, ic[0].w, ic[0].h) == (16, 24, 24) and ic[0].y == (row.h - 24) // 2 and lab.x == 56
                   and len(hair) == 1 and (hair[0].x, hair[0].y, hair[0].w, hair[0].h) == (56, row.h - 1, min(row.w, 310) - 56, 1) and hair[0].get('sensitive') == 'false'
                   and all(hair[0].get(f'style:{st}:bg_color') == '#222222' for st in mod_icons.ROW_STATES)
                   and all(row.get(f'style:{st}:border_width') == '0' for st in mod_icons.ROW_STATES) and row.get('style') == 'list_item_style',
                   f'{key}:{row.name}: bare 24 px glyph at x 16, title at x 56, the #222222 hairline inset to x 56 (the theme\'s full-width one off), pressed band is the stock style\'s')
    expect(used | {'pod_ic_tape', 'pod_ic_vinyl', 'pod_ic_art', 'pod_ic_sleep'} == set(mod_icons.pod_row_names()), 'every added row icon is used by a row (pod_ic_tape, pod_ic_vinyl, pod_ic_art, pod_ic_sleep: the Tape, Vinyl, Find Cover & Lyrics and Sleep Timer rows of Now Playing\'s More dialog, tests/pod/playmore.py)')
    # the Home grid icon (patch/home.c builds the widget): its two 66x66 images and the style that names them
    import awtk_style
    for n in mod_icons.POD_HOME:
        im = mod_icons.read_png(os.path.join(img_dir, n + '.png'))
        expect(n in added and im.size == (66, 66), f'{n}.png is added (66x66, the stock Home icon size)')
    th = awtk_style.parse(open(os.path.join(WORK, mod_icons.HOME_STYLES), 'rb').read())
    items = th.find('image', mod_icons.POD_HOME_STYLE)
    expect([i.state for i in items] == [i.state for i in th.find('image', 'home_tidal_style')] and
           all(i.get('bg_image') == mod_icons.POD_HOME[i.state == 'pressed'] for i in items),
           'home_m1plus_style has the five states of the stock icon styles: m1plus, m1plus_down when pressed')
    expect(th.items.index(items[-1]) + 1 == min(k for k, i in enumerate(th.items) if i.widget == 'image' and i.style > mod_icons.POD_HOME_STYLE) and
           th.find('image', 'home_tidal_style')[0].get('bg_image') == 'tidal',
           'inserted in the stock sort order, and the Tidal icon keeps its image names')
    tidal = {i.get('bg_image') for i in th.find('image', 'home_tidal_style')}
    expect(tidal == {'tidal', 'tidal_down'} and all(
               open(os.path.join(img_dir, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read()
               and mod_icons.read_png(os.path.join(img_dir, n + '.png')).size == (66, 66) and n in {h[0] for h in mod_icons.HOME} | {h[0] + '_down' for h in mod_icons.HOME}
               for n in tidal),
           'every state of home_tidal_style shows the generated brand-tidal disc (tidal, tidal_down: 66x66, not the stock files)')
    expect(dict((n, g) for n, _, g in mod_icons.HOME)['tidal'] == 'T:brand-tidal' and mod_icons.POD_ROWS['Tidal'][1] == 'T:brand-tidal',
           'the Home grid and the Extras row both use Tabler\'s brand-tidal (Lucide has no Tidal)')
    lucide, tabler_used = mod_icons.used_glyphs()
    expect(tabler_used == ['a-b', 'brand-tidal', 'circle-check'] and
           all(os.path.isfile(os.path.join(mod_icons.LUCIDE_SVG, n + '.svg')) for n in lucide) and
           not any(os.path.isfile(os.path.join(mod_icons.CUSTOM, n + '.svg')) for n in lucide),
           f'the set is Lucide ({len(lucide)} committed SVGs) with three Tabler glyphs; no custom SVG shadows a Lucide name')
    expect(os.path.isfile(os.path.join(mod_icons.LUCIDE, 'LICENSE')) and mod_icons.HOME_GLYPH == 38 and mod_icons.DISC_SW == 1.75
           and (mod_icons.BARE_PX, mod_icons.BARE_SW) == (24, 2.0) and mod_icons.POD_ICON == 24 and mod_icons.POD_TEXT_X == 56 == mod_icons.HAIR_X,
           'Home discs: Lucide at stroke 1.75, glyph canvas 38 px on the 66 px discs; list icons bare: 24 px canvas, stroke 2.0 px, title and hairline from x 56')
    # bare glyphs: no disc behind the 40 x 40 settings icons, white ink only, centred
    from PIL import Image
    for n, _, g in mod_icons.SETTINGS + mod_icons.LISTS:
        im = Image.open(os.path.join(mod_icons.PNG, n + '.png')).convert('RGBA'); bb = im.getchannel('A').getbbox()
        px = [p for p in im.getdata() if p[3]]
        expect(im.size == (40, 40) and bb and 8 <= bb[0] and bb[2] <= 32 and 8 <= bb[1] and bb[3] <= 32 and all(p[:3] == (255, 255, 255) for p in px),
               f'{n}: a bare white glyph inside the 24 px box of the 40 x 40 image ({bb})')
    expect({n: g for n, _, g in mod_icons.SETTINGS if g.startswith('badge:')} ==
           {'pset_dac': 'badge:DAC', 'pset_dsdoutput': 'badge:DSD', 'sset_dsdoutput': 'badge:DSD', 'pset_replaygain': 'badge:RG'},
           'the DAC, DSD output and ReplayGain settings icons are redrawn text badges')
    chev = {n: (Image.open(os.path.join(mod_icons.PNG, n + '.png')).convert('RGBA')) for n in ('right_arrow', 'right_arrow_down')}
    expect({p[:3] for p in chev['right_arrow'].getdata() if p[3] == 255} <= {(0x8A,) * 3} and {p[:3] for p in chev['right_arrow_down'].getdata() if p[3] == 255} <= {(0x6E,) * 3},
           'the list chevron is #8A8A8A, #6E6E6E pressed')
    ref = mod_icons.pod_chevron((0x8A,) * 3)
    expect(chev['right_arrow'].size == (13, 22) and chev['right_arrow'].crop((3, 3, 13, 19)).tobytes() == ref.tobytes() and chev['right_arrow'].getbbox() is not None
           and Image.open(os.path.join(mod_icons.PNG, 'pod_chev.png')).convert('RGBA').tobytes() == ref.tobytes(),
           'right_arrow (13 x 22, the glyph right aligned: ink at 3..13) and pod_chev are pixel for pixel the shared chevron of patch/common.c pod_make_chevron')
    # the Settings rows' icons: Now Playing's wave is the navbar button's glyph (Lucide audio-lines), Shanling Home's mark is cut
    # from the pinned stock shutdown screen (the committed disc is what the derivation makes), the rest are existing mappings
    glyphs = {n: g for n, g, _ in mod_icons.GLYPHS}
    expect(mod_icons.POD_ROWS['Now Playing'][1] == glyphs['back_to_player'] == 'audio-lines','the Now Playing row uses the wave glyph of the navbar\'s Now Playing button')
    mark = Image.open(os.path.join(mod_icons.PNG, mod_icons.card_name(mod_icons.SHANLING) + '.png')).convert('RGBA')
    expect(mod_icons.CARD_GLYPHS['Open Shanling Home'] == mod_icons.SHANLING and mark.tobytes() == mod_icons.bare_icon(mod_icons.SHANLING, mod_icons.POD_ICON).tobytes(),
           'the Shanling Home row has the brand mark derived from the stock shutdown screen (pinned), bare')
    ink = [p for p in mark.getdata() if p[3] > 200]; bb = mark.getchannel('A').getbbox()
    expect(len(ink) > 60 and mark.size == (24, 24) and bb[2] - bb[0] == 24 and all(p[:3] == (255, 255, 255) for p in ink),
           f'the mark is white ink 24 px wide, thickened to about 2 px strokes ({len(ink)} solid px, box {bb})')
    expect(mod_icons.POD_ROWS['Settings'][1] == 'sliders-horizontal' and not {'Play Settings', 'Start in: M1+ Music', 'Start in M1+ Music', 'Cover Flow landscape', 'Customize'} & set(mod_icons.POD_ROWS)
           and not any(k.startswith('pod_nav_rotate') for k in mod_icons.NAV_VIEW) and 'm1plus_settings' not in mod_icons.POD_UI,
           'the menu item Settings has the sliders glyph; the Settings pages are cards with their own glyphs (CARD_GLYPHS), not POD_ROWS rows')
    expect(mod_icons.POD_ROWS['Cover Flow'][1] == '+coverflow' and mod_icons.NAV_VIEW['pod_nav_coverflow'] == '+coverflow',
           'the custom Cover Flow glyph on the menu row and the navbar button')
    cg = mod_icons.CARD_GLYPHS
    expect(cg['Home Screen'] == 'house' and cg['Boot to M1+ Music'] == 'power' and cg['Developer'] == 'code' and cg['All Playback Settings'] == 'headphones'
           and cg['Landscape'] == 'rotate-cw-square' and cg['Wi-Fi'] == 'wifi' and cg['Bluetooth'] == 'bluetooth',
           'card rows: Home Screen house, Boot to power, Playback headphones, Developer code, Landscape rotate, Wi-Fi, Bluetooth')
    import pod_pages
    for page in pod_pages.PAGES:   # every Settings row but the pickers' has a glyph, drawn at 20 px in a 24 px image
        if page.kind == 'cards':
            for r in page.rows:
                if pod_pages.row_kind(r) not in ('check', 'info') and r.action not in (pod_pages.ACT_CCLIST, pod_pages.ACT_SFOLD, pod_pages.ACT_UPDATE, pod_pages.ACT_REGION): expect(r.label in cg, f'{page.key}: {r.label} has a card glyph')
    for n in mod_icons.CARD_IMAGES:
        im = Image.open(os.path.join(mod_icons.PNG, n + '.png')).convert('RGBA')
        expect(im.size == {'pod_chev': (mod_icons.CARD_CHEVRON[1], mod_icons.CARD_CHEVRON[2]), 'pod_check': (20, 20), **{p: (320, 52) for p in mod_icons.CARD_PIECE_IMAGES}, **{p: (320, mod_icons.CARD_TALL) for p in mod_icons.CARD_TALL_IMAGES}}.get(n, (24, 24)) and im.getchannel('A').getbbox(), f'{n} is a drawn image of its size')
    lock_imgs = {n: open(os.path.join(img_dir, n + '.png'), 'rb').read() for n in ('screens_battery', 'screens_charge', 'screens_lowbattery')}
    expect(all(lock_imgs[n] == battery_art.png(battery_art.LOCK, s) for n, s in
               (('screens_battery', 'normal'), ('screens_charge', 'charge'), ('screens_lowbattery', 'low'))),
           'the lock screen battery images are battery_art.png(LOCK)')

    # 41. Now Playing: the np_* images are the committed PNGs (tools/mod_icons.py draws them); the page's own checks are
    #     in test/pod/nowplaying.py.
    np_names = mod_icons.np_names()
    expect(all(open(os.path.join(img_dir, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read() for n in np_names),
           f'the {len(np_names)} np_* glyphs are the committed PNGs')

    # 42. The queue drawer (ui/dialog/playqueue_dialog.bin, V2.1kE): compact rows built from the template (44 px; the code
    #     reads row_height for its scroll offset), the playing row (srlabel_item_gold20_style, set by the row bind @0x47a19c)
    #     white 20 px against muted 18 px, a quieter left border, a header hairline, a dark bottom button; widgets and
    #     the drawer's position and animation unchanged.
    import awtk_style
    stock_ui = awtk_ui.parse(open(os.path.join(paths.find_stock(paths.ZIP), 'rootfs/release/assets/default/raw/ui/dialog/playqueue_dialog.bin'), 'rb').read())
    pq = awtk_ui.parse(open(os.path.join(ui_dir, 'dialog/playqueue_dialog.bin'), 'rb').read())
    expect([(w.type, w.name) for w in pq.walk()] == [(w.type, w.name) for w in stock_ui.walk()], 'the drawer has the stock widgets')
    dlg = pq.find('playqueue_dialog'); sdlg = stock_ui.find('playqueue_dialog')
    expect((dlg.x, dlg.y, dlg.w, dlg.h) == (sdlg.x, sdlg.y, sdlg.w, sdlg.h) and dlg.get('animation') == sdlg.get('animation'),
           'its position, size and slide-in animation are stock')
    rh = int(pq.find('queue_table_client').get('row_height'))
    trow, rbtn, rlab = (pq.find(n) for n in ('queue_table_row', 'btn_table_row', 'scrlabel_name'))
    expect(rh == 44 and trow.h == rh and 40 <= rbtn.h <= rh - 4 and rlab.h == rbtn.h and rlab.y == 0 and rbtn.w == trow.w == 230,
           f'rows are {rh} px: the table row, a {rbtn.h} px button and its label (touch target >= 40)')
    sb = pq.find('scroll_bar_m'); tc = pq.find('queue_table_client')
    expect(tc.w + sb.w == 240 + 0 and sb.x == tc.w, 'the row column and the scroll bar still fill the 240 px drawer')
    expect(all(int(rlab.get(f'style:{st}:font_size')) == 18 for st in ('normal', 'disable', 'focused')), 'row text 18 px')
    expect(dlg.get('style:normal:border_color') == '#3A3A3A', 'a quiet left border')
    head = pq.find('list_item')
    expect(head.h == 64 and head.get('style:normal:border') == 'bottom' and head.get('style:normal:border_width') == '1', 'a hairline under the 64 px mode header')
    btm = pq.find('button')
    expect((btm.y, btm.h) == (396, 44) and btm.get('style:normal:bg_color') == '#1E1E1E' and btm.get('style:pressed:bg_color') == '#333333',
           'the bottom button keeps its 44 px target in the dark button colours')
    # touches by demo's own hit test: a row button in the template column, the bottom button, the scroll bar, the header
    m = Machine()
    tree = asset_tree(os.path.join(ui_dir, 'dialog/playqueue_dialog.bin'))
    tree.x, tree.y, tree.w, tree.h = 80, 30, 240, 450      # where the slide-in animation ends
    for nm, h in (('table_view', 322), ('queue_table_client', 322), ('scroll_bar_m', 322)): node(tree, nm).h = h   # the layouts' h=-128 / 100%
    node(tree, 'list_item').w = 240
    node(tree, 'queue_table_row').flags |= F_VISIBLE      # the template row is hidden: runtime clones are not
    for x, y, want in ((100, 64 + 20, 'btn_table_row'), (120, 396 + 22, 'button'), (235, 200, 'scroll_bar_m'), (50, 30, 'list_item')):
        got = stock_target(m, tree, 80 + x, 30 + y)
        expect(want in got, f'a touch at ({x}, {y}) in the drawer lands on {want} ({got})')
    th = awtk_style.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/styles/playqueue_dialog.bin'), 'rb').read())
    white = [i for i in th.items if (i.widget, i.style) == ('hscroll_label', 'srlabel_item_white_style')]
    gold = [i for i in th.items if (i.widget, i.style) == ('hscroll_label', 'srlabel_item_gold20_style')]
    expect(white and gold and all(i.get('font_size') == 18 for i in white) and all(i.get('font_size') == 20 for i in gold)
           and all(i.color('text_color') == '#FFFFFFFF' for i in gold) and all(i.color('text_color') != '#FFFFFFFF' for i in white),
           'other rows muted 18 px, the playing row white 20 px')

    # 41. The product name and the About row. "M1+ Music" is what the user sees: no old name ("M1 Pod", "M1+ Pod") is left
    #     in our ui files, the 16 string tables, demo's payload or the Home icon; the internal name is m1plus (m1pod is gone). About keeps
    #     its seven stock rows in their order (FW. Version still the stock literal) (the tag is on our About page).
    import build
    raw = os.path.join(WORK, 'rootfs', 'release/assets/default/raw')
    old_names = (b'M1 Pod', b'M1+ Pod')
    has_old = lambda p: any(n in open(p, 'rb').read() for n in old_names)
    stale = sorted(os.path.relpath(os.path.join(d, f), raw) for sub in ('ui', 'strings') for d, _, fs in os.walk(os.path.join(raw, sub))
                   for f in fs if has_old(os.path.join(d, f)))
    demo = open(os.path.join(WORK, 'rootfs', 'release/bin/demo'), 'rb').read()
    expect(not stale and not any(n in demo for n in old_names) and demo.count(b'M1+ Music\0') >= 1,
           f'no user-visible old name (M1 Pod, M1+ Pod) is left in our ui files, the string tables or demo ({stale})')
    menu = awtk_ui.parse(open(os.path.join(ui_dir, 'm1plus_menu.bin'), 'rb').read())
    expect(b'M1+ Music' in open(os.path.join(ui_dir, 'm1plus_menu.bin'), 'rb').read() and menu.find('label_title') is not None,
           'the menu navbar title is M1+ Music')
    expect(os.path.exists(os.path.join(ui_dir, 'm1plus_menu.bin')) and b'/mnt/data/m1plus-start' in demo and b'/mnt/mmc/m1plus-off' in demo,
           'the internal name is m1plus: m1plus_menu.bin, /mnt/data/m1plus-start, /mnt/mmc/m1plus-off')
    old_files = sorted(os.path.relpath(os.path.join(d, f), raw) for d, _, fs in os.walk(raw) for f in fs if 'm1pod' in f)
    expect(not old_files and b'm1pod' not in demo, f'the old internal name m1pod is gone: no asset is named so, demo has no such string ({old_files})')
    expect(re.fullmatch(r'V2\.1(z[A-Z]+|-\d+\.\d+\.\d+)', build.TAG) is not None, f'the tag comes from tools/build.py ({build.TAG})')
    about = awtk_ui.parse(open(os.path.join(ui_dir, 'systemset/about_page.bin'), 'rb').read())
    expect(about.find('listitem7') is None and len(about.find('about_scrollview').children) == 7, 'the stock About page keeps its seven rows (our own About page, m1plus_about, shows the tag and the values: tools/mod_about.py is gone)')
    stock_len = os.path.getsize(os.path.join(paths.find_stock(paths.ZIP), 'rootfs', 'release/bin/demo'))   # the payload is appended after the stock file's length
    expect(demo.count(b'V2.1\0') >= 1 and build.TAG.encode() + b'\0' not in demo[:stock_len] and build.about(build.TAG).encode() + b'\0' in demo[stock_len:], 'demo\'s own data still carries the stock version literal V2.1 (FW. Version), not our tag (only the appended payload has it: the iPod About row)')

    # 51. The on/off switch (sset_on / sset_off): no text, a pill track and a round knob, the stock 57x28 canvas.
    from PIL import Image
    import mod_theme
    for name in ('sset_on', 'sset_off'):
        im = Image.open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx', name + '.png')).convert('RGBA')
        on = name == 'sset_on'; track, knob = mod_theme.TOGGLE_COLOURS[on]
        a = im.getchannel('A')
        expect(im.size == (57, 28) and a.getbbox() == (11, 2, 57, 26), f'{name}: the stock 57x28 canvas, a 46x24 pill right-aligned in it, x 11..57, y 2..26 ({im.size}, {a.getbbox()})')
        kx = 11 + 46 - 3 - 9 if on else 11 + 3 + 9               # the 18 px knob's centre, 3 px in: right when on, left when off
        expect(im.getpixel((kx, 14))[:3] == knob and im.getpixel((68 - kx, 14))[:3] == track,
               f'{name}: knob {knob} on the {"right" if on else "left"}, track {track} on the other side')
        expect(im.getpixel((12, 14))[3] > 200 and im.getpixel((55, 14))[3] > 200 and im.getpixel((11, 2))[3] == 0 and im.getpixel((56, 25))[3] == 0
               and im.getpixel((11, 25))[3] == 0 and im.getpixel((56, 2))[3] == 0 and im.getpixel((5, 14))[3] == 0,
               f'{name}: a pill (the corners are clear, the ends solid, nothing left of x 11)')
        soft = sum(1 for v in a.getdata() if 0 < v < 255); lit = {p[:3] for p in im.getdata() if p[3] == 255}
        expect(soft >= 30 and {track, knob} <= lit and len(lit) > 2, f'{name}: anti-aliased ({soft} partly covered pixels, {len(lit)} opaque colours: track, knob and the blend of the knob\'s rim)')
        # the track's rim keeps the track colour (no dark fringe from the transparent side of the mask)
        rim = [p for p in im.getdata() if 0 < p[3] < 255 and p[:3] != track]
        expect(not rim, f'{name}: the pill\'s edge pixels are the track colour with partial alpha ({len(rim)} stray)')
    on_l, off_l = mod_theme.TOGGLE_COLOURS[True][0], mod_theme.TOGGLE_COLOURS[False][0]
    lum_ = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    expect(lum_(on_l) > 200 and lum_(off_l) < 70 and lum_(mod_theme.TOGGLE_COLOURS[True][1]) < 40 and 100 < lum_(mod_theme.TOGGLE_COLOURS[False][1]) < 160,
           'on: an off-white track with a dark knob; off: a dark grey track with a grey knob (read by brightness and side)')
    for name in ('pset_dual', 'pset_high'):
        expect(os.path.exists(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx', name + '.png')), f'{name}: still there')

    # 52. The pull-down's status bar is the real one (tools/statusbar.py lays both out): the same widgets, in the same order, at
    #     the same positions and sizes, with the same images, fonts, colours, alignment and spacing; the
    #     bar sits at y 0 of the dialog (open at y 0 of the screen) on the real bar's black, so nothing jumps when it opens.
    import statusbar
    from awtk_text import Ttf, StbText
    real = awtk_ui.parse(open(os.path.join(ui_dir, 'system_bar.bin'), 'rb').read())
    skip = {'value'}                                   # the battery fill's level is set at run time
    def sig(w, clock_h=True):
        props = tuple(sorted((k, v) for k, v in w.props if k not in skip and not (w.type == 'view' and k.startswith('style:') and 'bg_color' in k)))
        return (w.type, w.name, w.x, w.y, w.w, w.h if (clock_h or w.name != 'bar_dclock') else None, props)
    # the one difference by design: the Screenshot countdown's camera (pod_shot, hidden, patch/shot.h) is in the real bar only; the pull-down covers
    # the bar while it is open, and the payload looks the camera up in the window manager's tree (the real bar), so the pull-down gets no copy
    # and the Battery Percentage label (pod_pct in the real bar, pod_pct_dd in the pull-down's: hidden, test/pod/battery.py checks both)
    def own(bar): return [w for w in bar.walk() if w is not bar and w.name not in ('pod_shot', 'pod_pct', 'pod_pct_dd')]
    ref = [sig(w) for w in own(real)]
    font = Ttf(os.path.join(WORK, 'rootfs/release/assets/default/raw/fonts/default.ttf'))
    dd = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/dialog/dropdown_dialog.bin'), 'rb').read())
    pb = dd.find('view_sysbar')
    # the pull-down's own view_sysbar and the system_bar window: the clock's h differs in the file only (h=100% resolves to 30 under its self_layout)
    got = [sig(w, False) for w in own(pb)]
    want = [sig(w, False) for w in own(real)]
    expect(got == want and [w.name for w in own(pb)] == [w.name for w in own(real)] and not any(w.name == 'pod_shot' for w in pb.walk()),
           f'the pull-down\'s bar has the real bar\'s {len(want)} widgets in order, with the same geometry, images, fonts, colours, alignment and layouts'
           + ('' if got == want else f' (differs: {[(a[1], a[2:]) for a, b in zip(got, want) if a != b][:3]})'))
    expect((pb.x, pb.y, pb.w, pb.h) == (0, 0, 320, 30) and real.h == 30 and (dd.x, dd.y) == (0, -340)
           and all(pb.get(f'style:{st}:bg_color') == '#000000' for st in ('normal', 'disable', 'focused')) and real.get('style:normal:bg_color') == '#000000',
           'the bar is 320x30 at the dialog\'s top edge, black as the real bar')
    vol, clk, lv, rv = (pb.find(n) for n in ('label_volume', 'bar_dclock', 'view_bar_left', 'view_bar_right'))
    expect(all(vol.get(f'style:{st}:font_size') == '16' and vol.get(f'style:{st}:text_align_v') == 'middle' for st in ('normal', 'disable', 'focused'))
           and clk.get('style:normal:font_size') == '18' and (clk.x, clk.w) == (104, 90) and lv.get('children_layout') == 'default(r=1,c=0,x=10,s=4)'
           and rv.get('children_layout') == 'default(r=1,c=0,a=right,s=4)' and pb.find('img_battery').x + 22 == 310,
           'volume 16 px middle, clock 18 px at x 104 (90 wide), left group from x 10, right group 4 px apart, battery outline ends 10 px from the edge')
    expect(StbText(font, 16).layout('100')[1] <= vol.w and StbText(font, 18).layout('12:59 PM')[1] <= clk.w,
           '"100" fits the volume label and "12:59 PM" (12 h mode) the clock box in the shipped font')
    expect(ref and all(real.find(n) is not None for n in statusbar.NAMES), 'the real bar still has every widget the stock code looks up')
