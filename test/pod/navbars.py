"""The glass navbars of OUR pages (docs/modules/navbar.md): the M1+ Music menu and sub-pages, Albums, Artists, Playlists, Cover Flow's bar: an opaque bar, a glass Back
disc at x 8, the title from x 58, the right-hand actions as one glass capsule on main's slots (46 px buttons at x 168 / 214, Now Playing 60 px at x 260; the glass ends
at x 311, 21 px right of Now Playing's glyph column 290; a lone Now Playing is a disc), a soft fade under the bar. Stock pages are NOT restyled: every stock asset
(ui, styles, images, strings) and the code-built navbars of the stock pages (their builders' bytes in demo) are byte-identical to main's build V2.1oC, pinned by the
digests in test/navbars-stock.sha256. What this work adds or changes is named in EXEMPT (our pages, our images, the plain stock album page's ui file, the About
page's release tag)."""
import glob, hashlib, os
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)
import awtk_strings, awtk_ui, mod_icons, mod_overlays, pod_i18n, pod_ui

HERE = os.path.dirname(os.path.abspath(__file__))
DIGESTS = os.path.join(os.path.dirname(HERE), 'navbars-stock.sha256')
NEW_IMAGES = ('pod_nav_', 'pod_sb_', 'nb_fade', 'ah_', 'pl_glass', 'pl_ic_', 'rm_', 'sg_', 'vs_', 'np_', 'dm_', 'dp_', 'pod_ic_', 'ipod_', 'tape_', 'vinyl_', 'pm_sheet', 'qk_', 'pod_ci_', 'pod_cd_', 'pod_cdl_', 'pod_chev', 'pod_check', 'se_', 'fo_ic_', 'pod_es_', 'rn_', 'wf_', 'pq_glass')      # the images this work adds or changes (all ours; ah_*: the album page's buttons, tint and navbar; np_*: Now Playing's glyphs and discs; pl_*: the Playlists page's menu, docs/modules/playlists.md; sg_*: the Songs page's); dm_ / dp_: the Daily Mix card and page; pod_ic_*: the menu and settings row glyphs (tools/mod_icons.py POD_ROWS); ipod_*: the Pod page's click wheel; tape_*: the Tape page's pictures
OVERLAY_UI = ('confirminfo_dialog.bin', 'rippercompleted_dialog.bin', 'cardupdate_dialog.bin', 'formatcard_dialog.bin', 'dialog_autoshutdown.bin')   # the ui files tools/mod_overlays.py restyles (docs/modules/overlays.md; their window themes in styles/ stay stock)
OUR_FILES = ('about_page.bin', 'albuminfo_page.bin', 'lyrics.ttf')  # lyrics.ttf: the lyrics' bold face (docs/modules/lyrics.md, a second font file next to default.ttf); the About page (the digest was taken when it carried the release tag; it is stock again, our own About page is m1plus_about) and the plain stock album page (its ui file: the navbar's y, as allmusic_page's)
# the code-built stock navbars: (first, last + 1) of the builders' bytes in demo (the album pages' two, Folders, Artists/Genres/Composers, stock Playlists)
BUILDERS = ((0x524e4c, 0x5251e0), (0x526a3c, 0x527010), (0x5312dc, 0x5316c0), (0x535188, 0x5357c0), (0x53d5f8, 0x53d900))


def stock_digests(assets):
    """{area: sha256 of the sorted (relative path, file sha256) list} over assets/ (release/assets), without our pages and images (ui/m1plus_*, NEW_IMAGES) and
    OUR_FILES, and 'demo-builders': the bytes of the stock pages' navbar builders in demo."""
    out = {}
    for area in ('default/raw/ui', 'default/raw/styles', 'default/raw/images', 'default/raw/strings', 'default/raw/fonts'):
        h = hashlib.sha256()
        for f in sorted(glob.glob(os.path.join(assets, area, '**', '*'), recursive=True)):
            if not os.path.isfile(f): continue
            rel = os.path.relpath(f, assets); name = os.path.basename(f)
            if (area.endswith('/ui') and name.startswith('m1plus_')) or name in OUR_FILES or (area.endswith('/ui') and name in OVERLAY_UI) or (name.endswith('.png') and name[:-4] in mod_overlays.NAMES) or (area.endswith('/images') and name.startswith(NEW_IMAGES)): continue
            data = open(f, 'rb').read()
            if area.endswith('/strings'):   # the string tables without OUR keys (tools/pod_i18n.py TEXT, which every feature adds to) the other stock keys and their texts only
                data = awtk_strings.serialize([kv for kv in awtk_strings.parse(data) if kv[0] not in pod_i18n.TEXT])
            h.update(rel.encode() + b'\0' + hashlib.sha256(data).digest())
        out[area] = h.hexdigest()
    return out


def builder_digest(demo):
    h = hashlib.sha256()
    for a, b in BUILDERS: h.update(demo[pod.fileoff(demo, a):pod.fileoff(demo, b - 4) + 4])
    return h.hexdigest()


def run(ctx):
    expect = ctx.expect
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    assets = os.path.join(WORK, 'rootfs', 'release', 'assets')
    xx = os.path.join(raw, 'images', 'xx')

    # ------------------------------------------------------------------ stock pages are main's
    want = dict(l.split()[::-1] for l in open(DIGESTS) if l.strip() and not l.startswith('#'))
    got = stock_digests(assets)
    expect(not os.path.exists(os.path.join(assets, 'theme1')), 'stock theme1 is not in the rootfs (tools/mod_space.py; it is safe only with the config_init clamp, tools/themeoff.py)')
    got['demo-builders'] = builder_digest(open(DEMO, 'rb').read())
    expect(got == want, f'every stock ui / style / image / string / font file and the stock pages\' navbar builders in demo are byte-identical to main\'s build: {[k for k in got if got[k] != want.get(k)]} differ ({ {k: got[k] for k in got if got[k] != want.get(k)} }: the new digests, for test/navbars-stock.sha256 when the change is intended)')

    # ------------------------------------------------------------------ our pages
    stock_ui = os.path.join(raw, 'ui')
    pods = {os.path.basename(f)[:-4]: awtk_ui.parse(open(f, 'rb').read()) for f in glob.glob(os.path.join(stock_ui, 'm1plus_*.bin'))}
    expect(len(pods) == len(pod_pages.PAGES), f'{len(pods)} M1+ Music pages (with the Songs and Daily Mix pages)')
    D = mod_icons.GLASS_H
    slot_w, play_x, play_w = O['NAV_VIEW_W'], pod_ui.NAV_PLAY_X, pod_ui.NAV_PLAY_W
    expect((O['NAV_CF_X'], O['NAV_VIEW_X'], slot_w, play_x, play_w) == (168, 214, 46, 260, 60) == (pod_ui.NAV_CF_X, pod_ui.NAV_VIEW_X, pod_ui.NAV_VIEW_W, 260, 60),
           'the slots are main\'s: 168 and 214, 46 wide, Now Playing (260, 60 wide)')
    for name, root in sorted(pods.items()):
        nav = next((c for c in root.children if c.name == 'navigationbar_view'), None)
        if nav is None: continue
        k = {c.name: c for c in nav.children}
        back, play, lbl = k['btn_return'], k['btn_backtoplayer'], k['label_title']
        group = sorted([k[n] for n in ('btn_coverflow', 'btn_more', 'btn_albumview', 'btn_artisttype', 'btn_settings', 'btn_search', 'btn_sort', 'btn_select', 'btn_globe', 'btn_plactions', 'btn_bprev', 'btn_bnext') if n in k and not (n == 'btn_coverflow' and name == 'm1plus_songs') and k[n].get('visible') != 'false'], key=lambda c: c.x) + [play]   # (a hidden button shares a slot with one that shows)
        capsule = len(group) > 1
        ok = (back.x, back.y, back.w, back.h) == (7, 0, 44, 50) and back.get('style:normal:icon') == 'ah_nav_back' and back.get('style:pressed:icon') == 'ah_nav_back_down'
        if capsule:
            pos = [mod_icons.NAV_VIEW_POS[c.get('style:normal:icon')] for c in group[:-1]]
            ok = ok and all(a.x + a.w == b.x for a, b in zip(group, group[1:])) and (play.x, play.w) == (260, 60) and play.get('style:normal:icon') == 'ah_nav_play' \
                and all(c.w == 46 and (c.y, c.h) == (0, 50) for c in group[:-1]) and pos == {4: ['left', 'middle', 'middle'], 3: ['left', 'middle'], 2: ['left']}[len(group)] \
                and group[0].x + (2 if pos[0] == 'left' else 0) == {4: 124, 3: 170, 2: 216}[len(group)]
        else:
            ok = ok and (play.x, play.w, play.y, play.h) == (260, 60, 0, 50) and play.get('style:normal:icon') == 'ah_nav_np' and play.x + 9 + D == 311
        first = min(c.x for c in nav.children if c.name not in ('label_title', 'btn_return') and c.get('visible') != 'false')
        ok = ok and lbl.x == 58 and lbl.x + lbl.w <= first and back.x + (back.w - D) // 2 == 8 and (50 - D) // 2 == 4
        expect(ok, f'{name}: Back is the glass disc at x 8, y 4 (a 44 x 50 button at x 7), {"the capsule " + str([(c.name, c.x) for c in group]) + " abuts on main\'s slots and its glass ends at x 311, Now Playing its right cap" if capsule else "Now Playing the disc at x 269 .. 311"}, the title from x 58 ends before the first button')
        expect('btn_allalbums' not in k, f'{name}: no All albums button')
        if name == 'm1plus_podcasts':
            expect('btn_select' not in k and 'btn_more' in k, f'{name}: no Select button of its own any more (Select is a sheet row on the Downloads page)')
        if 'btn_songs' in k:
            s = k['btn_songs']
            expect((s.x, s.w, s.y, s.h) == (O['NAV_VIEW_X'], slot_w, 0, 50) and s.x + s.w == play.x and s.get('visible') == 'false' and s.get('style:normal:icon') == 'pod_nav_songs'
                   and mod_icons.NAV_VIEW_POS['pod_nav_songs'] == 'left' and play.get('style:normal:icon') == 'ah_nav_np',
                   f'{name}: the hidden Songs button is the left cap on the 214 slot, abutting Now Playing (the disc in the asset; the code makes it the right cap)')
        fades = [c for c in root.children if c.name == pod_ui.NB_FADE_NAME]
        listed = any(c.y == 50 and c.h >= 300 for c in root.children if c.type == 'list_view')
        expect(len(fades) == (1 if listed else 0) and all((f.x, f.y, f.w, f.h) == (0, 50, 320, mod_icons.NB_FADE[2]) and f.get('sensitive') == 'false' and f.get('clickable') == 'false' and f.get('image') == 'nb_fade' for f in fades),
               f'{name}: {"one insensitive fade at (0, 50)" if listed else "no fade (no list under the bar)"}')

    # only the Extras page has the Settings button: the left cap of [Settings | Now Playing] on the 214 slot, the title ending at 214
    with_btn = sorted(name for name, root in pods.items() if any(c.name == 'btn_settings' for c in root.walk()))
    nav = next(c for c in pods['m1plus_extras'].children if c.name == 'navigationbar_view')
    cb = next(c for c in nav.children if c.name == 'btn_settings')
    lb = next(c for c in nav.children if c.name == 'label_title')
    expect(with_btn == ['m1plus_extras'] and (cb.x, cb.y, cb.w, cb.h) == (214, 0, 46, 50) and cb.get('style') == 'img_btn_style' and cb.get('enable') == 'true'
           and cb.get('style:normal:icon') == cb.get('style:over:icon') == 'pod_nav_settings' and cb.get('style:pressed:icon') == 'pod_nav_settings_down'
           and lb.x + lb.w == 214, 'only the Extras page has btn_settings: a 46 px button on the 214 slot with the pod_nav_settings pieces, the title ends at 214')
    vol = awtk_ui.parse(open(os.path.join(stock_ui, 'dialog', 'volume_dialog.bin'), 'rb').read())
    expect(all(vol.get(f'style:{st}:border_color') == '#00000000' for st in ('normal', 'disable', 'focused')) and (vol.x, vol.y, vol.w, vol.h) == (0, 0, 320, 42),
           'volume_dialog: the 42 px strip\'s border is transparent (it was black at y 41, through the full-page screen\'s Back disc)')
    # ------------------------------------------------------------------ images
    for n, pos in mod_icons.NAV_VIEW_POS.items():
        for suffix, pressed in (('', False), ('_down', True)):
            expect(same_pixels(os.path.join(xx, n + suffix + '.png'), mod_icons.capsule_piece(pos, mod_icons.NAV_VIEW[n], pressed)),
                   f'{n}{suffix}.png is the {pos} glass piece with its glyph, pixel for pixel')
    png = asset_image('nb_fade')
    col = [png.getpixel((0, y)) for y in range(png.height)]
    expect(png.size == (320, mod_icons.NB_FADE[2]) and all(c[:3] == (0, 0, 0) for c in col) and [c[3] for c in col] == [mod_icons.nb_fade_alpha(y) for y in range(png.height)]
           and all(a[3] >= b[3] for a, b in zip(col, col[1:])) and col[0][3] >= 225 and col[-1][3] <= 2 and col[12][3] <= 8,
           f'nb_fade.png: black, alpha {col[0][3]} at the bar down to {col[-1][3]}, eased so a first row at rest stays clear (alpha {col[12][3]} at row 12)')

    # ------------------------------------------------------------------ the fade never darkens content at rest (scroll offset 0)
    # Where each page's first content ink is under the bar (window y minus 50), from the built assets and the content geometry; the fade's alpha there must be
    # <= FADE_REST_MAX unless the fade starts hidden (then patch/albums.c and patch/playlists.c show it only while yoffset > 0: tests in albums.py / playlists.py).
    FADE_REST_MAX = 8
    alpha_at = lambda y: col[y][3] if 0 <= y < len(col) else 0
    rest = {}
    for name, root in sorted(pods.items()):
        fade = next((c for c in root.children if c.name == pod_ui.NB_FADE_NAME), None)
        if fade is None: continue
        hidden_fade = fade.get('visible') == 'false' and fade.get('sensitive') == 'false'
        if any(c.name.endswith('_scrollview') and c.name[:-len('scrollview')] in ('albums_', 'playlists_') for c in root.walk()):
            ink = min(O['GRID_ROW_GAP'], O['LIST_ART_Y'])               # the grid's first cover, the list mode's first cover
        else:
            sv = next((c for c in root.walk() if c.type == 'scroll_view'), None)
            first = min(sv.children, key=lambda c: c.y) if sv and sv.children else None
            if first is None: continue
            tops = [(first.h - 21) // 2]                                # the label (21 px, centred)
            tops += [w.y for w in first.walk() if w.type == 'image' and w.name.startswith('pod_switch')]   # the on / off switch
            ink = min(tops)
        rest[name] = (ink, 0 if hidden_fade else alpha_at(ink))
    expect(len(rest) >= 9 and all(a <= FADE_REST_MAX for _, a in rest.values()),
           f'at scroll offset 0 no page\'s content is under the fade (alpha <= {FADE_REST_MAX}): {rest}')

    # ------------------------------------------------------------------ hit tests on the built pages (demo's own widget_find_target)
    m = sibling('rows').RowMachine()
    mark = m.next   # every hit test lays the whole page out again in scratch memory: each starts from here (nothing of a layout outlives its test)
    for pg in ('m1plus_settings.bin', 'm1plus_artists.bin', 'm1plus_albums.bin', 'm1plus_playlists.bin', 'm1plus_songs.bin'):
        a = asset_tree(os.path.join(stock_ui, pg))
        lst = next(c for c in a.children if c.y == 50 and c.h >= 300)
        sv = next((c for c in lst.children if c.name.endswith('scrollview')), lst)
        sv.children = [Node(f'row{i}', 0, 52 * i, 310, 52) for i in range(8)]
        def tgt(x, y, a=a):
            m.next = mark
            return stock_target(m, a, x, y)[-1]
        play = node(a, 'btn_backtoplayer')
        bad = [(x, y, tgt(x, y)) for x, y in ((8, 6), (29, 25), (49, 45)) if tgt(x, y) != 'btn_return']
        bad += [(x, y, tgt(x, y)) for x, y in ((play.x + 10, 6), (play.x + 30, 25), (311, 45)) if tgt(x, y) != 'btn_backtoplayer']
        expect(not bad, f'{pg}: the disc corners and centres of Back and Now Playing reach their buttons ({bad})')
        expect(all(tgt(x, y) == 'row0' for x in (20, 160, 280 if pg in ('m1plus_songs.bin', 'm1plus_artists.bin') else 300) for y in (50, 55, 62, 69)) and all(tgt(x, y) != pod_ui.NB_FADE_NAME for x in (0, 160, 319) for y in range(50, 70)),
               f'{pg}: the first row takes touches through the whole fade, which never gets one')
