"""The track rows' "..." menu (patch/rowmenu.c, patch/songs.c, patch/albumpage.c, docs/modules/rowmenu.md): the asset (the scrim and the five-row glass card, last in both pages), the
grey "..." painted at the right end of the rows (the rail's side of the Songs page, the text width it takes), the taps (a tap on it opens the menu; a drag, a press that leaves it, a row
tap elsewhere, select mode and a page without the widgets do not), the bottom sheet (the asset's place for every row, every language fits, closed by the scrim), the three rows
(Play Next / Play After through upnext_add with a one-row deque holding the tapped row, Add to Playlist through the page's one-row selection and picker) and the toast of every status.
The compiled payload runs under Unicorn; upnext_add and picker_open are trapped (their own tests are test/pod/upnext.py and test/pod/picker.py)."""
import importlib.util, io, os, struct, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


SG, AB = sibling('songs'), sibling('albumpage')

ROW, MORE_W, DOTS = O['LIST_ROW_H'], O['RM_MORE_W'], O['RM_DOTS_PX']
RIGHT, RIGHT_RAIL, GAP = O['RM_MORE_RIGHT'], O['RM_MORE_RIGHT_RAIL'], O['RM_TEXT_GAP']
PLROW = O['PM_ROW_H']
CARD_H = 5 * PLROW
CARD_Y = 450 - CARD_H                                   # the sheet sits on the window's foot (window y 200..450)
LABEL_W = 320 - pod_ui.RM_TEXT_X - pod_ui.RM_TEXT_R    # 250: Now Playing's More sheet's label box (48..298)
EN = ('Play Next', 'Play After', 'Add to Playlist', 'Favorite', 'Get Info')
WIDGETS = ('rm_scrim', 'rm_card', 'rm_item0', 'rm_item1', 'rm_item2', 'rm_item3', 'rm_item4', 'rm_label0', 'rm_label1', 'rm_label2', 'rm_label3', 'rm_label4', 'rm_icon2', 'rm_icon3')
SEL_VEC = pod.DATA['SEL_VEC'][0]
UI_SONGS = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_songs.bin') if WORK else None
UI_ALBUM = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_album.bin') if WORK else None
ADDED, STARTED, EMPTY, STREAM, FOLDER, PODCAST, MISSING, FULL, MEMORY, DLNA = 1, 2, -1, -2, -3, -4, -5, -6, -7, -8
TOASTS = {STREAM: 'Not available while streaming', FOLDER: 'Not available for folder playback', PODCAST: 'Not available for podcasts', MISSING: 'Storage unavailable', FULL: 'Queue is full',
          MEMORY: 'Not enough memory', DLNA: 'Not available while DLNA is on', EMPTY: 'Adding Failed'}


class Trap:
    """upnext_add (the rows deque as it is at the call, `after`, the status the test wants) and picker_open (class, count, the marks) answered by the test; each recorded in calls and
    in up_calls / pk_calls."""
    up_ret, pk_ret = ADDED, -1

    def trap_setup(self):
        self.up_calls, self.pk_calls, self.si_calls = [], [], []
        self.handlers[PSYMS['songinfo_open']] = 'songinfo_open'
        self.up_ret, self.pk_ret = ADDED, -1
        self.handlers[PSYMS['upnext_add']] = 'upnext_add'
        self.handlers[PSYMS['picker_open']] = 'picker_open'
        self.strings['msg_addfailed'] = 'Adding Failed'

    def _hook(self, u, address, size, _):
        name = self.handlers.get(address)
        if name not in ('upnext_add', 'picker_open', 'songinfo_open'): return super()._hook(u, address, size, _)
        a0, a1, a2 = (u.reg_read(r) for r in (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2))
        if name == 'songinfo_open':
            self.si_calls.append(a0); self.calls.append(('songinfo_open', a0)); ret = 0
        elif name == 'upnext_add':
            rows = list(self.deques.get(a0, []))
            self.up_calls.append((rows, a1)); self.calls.append(('upnext_add', a1, len(rows))); ret = self.up_ret
        else:
            self.pk_calls.append((a0, a1, bytes(self.u.mem_read(a2, (a1 + 7) // 8)))); self.calls.append(('picker_open', a0, a1)); ret = self.pk_ret
        u.reg_write(UC_MIPS_REG_V0, ret & 0xffffffff); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA))


def dots_pixels():
    """The asset's rm_dots as the harness' decoder gives it: opaque pixels, the red channel the coverage (cc_decode flattens the image over black)."""
    return b''.join(struct.pack('<4B', c, c, c, 255) for y in range(DOTS) for x in range(DOTS) for c in [(x * 11 + y * 7) % 250 + 3])


def with_menu(m, cls, texts=EN):
    """The machine gets the asset's widgets of the menu and the "..." image; cls is Trap's class on top of the machine's own."""
    m.__class__ = type('RM' + type(m).__name__, (Trap, type(m)), {})
    m.trap_setup()
    for n in WIDGETS: Machine.widget(m, n)
    m.images['rm_dots'] = (DOTS, DOTS, dots_pixels())
    for i, t in enumerate(texts): m.wtext[m.widgets[f'rm_label{i}']] = t.encode('utf-8').decode('latin-1')
    return m


# ---- the Songs page
LETTERS = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliet']


def songs(menu=True, plain=False, titles=LETTERS):
    """The Songs page (the library in title order: sections, the A-Z rail) or, plain, the Favourites list (no sections, no rail), with the menu's widgets."""
    m = SG.list_machine(titles, O['CLASS_FAV']) if plain else SG.songs_machine(titles)
    if menu: with_menu(m, 0)
    if plain: m.call(PSYMS['songs_open_list'], a0=O['HOME_FAV'], count=900000000)
    else: SG.open_page(m)
    SG.settle(m)
    m.calls = []
    return m


def lay_of(m, plain, n=len(LETTERS)):
    return SG.Layout(SG.letters_of(LETTERS[:n]) if not plain else ['A'] * n, sections=not plain)


def dot_blits(blits): return [b for b in blits if b[2][2:] == (DOTS, DOTS) and b[1] == (0, b[1][1], DOTS, b[1][3])]
def titles_of(texts, names=LETTERS): return {t: r for t, r in texts if t in names}
def toasts(calls): return [c[1] for c in calls if c[0] == 'toast']


def card_of(m):
    """The menu's widgets the payload moved or resized (none: the asset places the sheet), and whether the card is shown."""
    ours = {m.widgets[n] for n in m.widgets if n.startswith('rm_')}
    return [c for c in m.calls if c[0] in ('widget_move', 'widget_resize') and c[1] in ours], SG.vis(m, 'rm_card')


def asset_tests(ctx):
    """1. The asset of both pages: the scrim and the card last, the card a bottom sheet in Now Playing's More sheet's glass, the three rows (24 px glyph at x 14, label from x 48, a hairline
    above every row but the first), hidden and insensitive; the images; white labels keep 7:1 on the glass and the grey "..." 3:1 on black; the Developer test rows are gone."""
    expect = ctx.expect
    import mod_icons
    for ui_path, name in ((UI_SONGS, 'Songs'), (UI_ALBUM, 'album')):
        tree = awtk_ui.parse(open(ui_path, 'rb').read())
        kids = [c.name for c in tree.children]
        scrim, card = tree.find('rm_scrim'), tree.find('rm_card')
        items = [tree.find(f'rm_item{i}') for i in range(5)]
        labels = [tree.find(f'rm_label{i}') for i in range(5)]
        icons = [tree.find(f'rm_icon{i}') for i in range(5)]
        expect(kids[-2:] == ['rm_scrim', 'rm_card'] and tree.children[-2] is scrim and tree.children[-1] is card, f'{name}: the menu\'s scrim and card are the window\'s last children (above the list, the bars and the navbar)')
        expect(scrim.type == 'button' and (scrim.x, scrim.y, scrim.w, scrim.h) == (0, 0, 320, 450) and all(scrim.get(f'style:{st}:bg_color') == pod_ui.PL_DIM == '#00000082' for st in pod_ui.STATES),
               f'{name}: the scrim is the full window\'s #00000082 dim, a button (a tap closes the menu)')
        expect((card.x, card.y, card.w, card.h) == (0, CARD_Y, 320, CARD_H) == (0, 200, 320, 250)
               and all(card.get(f'style:{st}:bg_image') == 'rm_glass' and card.get(f'style:{st}:bg_image_draw_type') == 'default' and card.get(f'style:{st}:bg_color') == '#00000000'
                       and card.get(f'style:{st}:round_radius') is None for st in pod_ui.STATES),
               f'{name}: the card is a 320 x 250 bottom sheet (five 50 px rows) on the window\'s foot, the glass drawn 1:1 over no fill')
        expect(all(w.get('visible') == 'false' and w.get('sensitive') == 'false' for w in (scrim, card)), f'{name}: the scrim and the card start hidden and insensitive')
        expect([(i.type, i.x, i.y, i.h, i.w) for i in items] == [('button', 0, k * PLROW, PLROW, 320) for k in range(5)]
               and all(i.get(f'style:{st}:bg_color') == ('#FFFFFF10' if st == 'pressed' else '#00000000') and i.get(f'style:{st}:text_color') == '#FFFFFF' for i in items for st in pod_ui.STATES)
               and all(i.get(f'style:{st}:border') == ('top' if k else 'none') and i.get(f'style:{st}:border_width') == ('1' if k else '0')
                       and i.get(f'style:{st}:border_color') == ('#FFFFFF22' if k else '#00000000') for k, i in enumerate(items) for st in pod_ui.STATES),
               f'{name}: five transparent full-width 50 px rows, pressed 6 % white, the sheet\'s 13 % white hairline above every row but the first')
        expect([ic.get('image') for ic in icons] == ['rm_ic_next', 'rm_ic_after', 'rm_ic_add', 'rm_ic_fav', 'rm_ic_info'] == [n for n, _ in mod_icons.RM_MENU_ICONS] and mod_icons.RM_FAV_ON == ('rm_ic_unfav', 'star')
               and [g for _, g in mod_icons.RM_MENU_ICONS] == ['list-start', 'list-end', 'list-plus', 'star', 'info']
               and all((ic.x, ic.y, ic.w, ic.h) == (14, 13, 24, 24) and ic.get('sensitive') == 'false' for ic in icons),
               f'{name}: Lucide list-start, list-end, list-plus, star and info, 24 px at x 14 (the More sheet\'s own rows, pod_tape_icon)')
        expect(all(lb.x == 48 and lb.w == LABEL_W == 250 and lb.get('sensitive') == 'false' and lb.get('style:normal:font_size') == '18' and lb.get('style:normal:text_color') == '#FFFFFF'
                   for lb in labels) and [pod_i18n.shown_english(lb) for lb in labels] == list(EN),
               f'{name}: the labels start at x 48, 18 px white: Play Next, Play After, Add to Playlist')
    # the images: the glass is the generator's, five rows high; the glyphs and the dots are in the tree
    xx = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/images/xx')
    w, h, r = mod_icons.GLASS_ROWMENU
    raw_ = open(os.path.join(xx, 'rm_glass.png'), 'rb').read()
    gen = mod_icons.glass_image(w, h, r, fill=mod_icons.GLASS_SHEET_FILL, top_only=True)
    expect(raw_ == open(os.path.join(mod_icons.PNG, 'rm_glass.png'), 'rb').read() and same_pixels(raw_, gen) and (w, h, r) == (320, CARD_H, 18) and r == mod_icons.GLASS_SHEET[2],
           'rm_glass.png is the generator\'s: 320 x 250 (the sheet\'s height), Now Playing\'s sheet: 18 px top corners only, the sheet\'s fill')
    expect(all(open(os.path.join(xx, n + '.png'), 'rb').read() == open(os.path.join(mod_icons.PNG, n + '.png'), 'rb').read() for n, _ in mod_icons.RM_MENU_ICONS + (mod_icons.RM_FAV_ON, mod_icons.RM_DOTS)),
           'the five glyphs, the filled star and rm_dots are the committed PNGs')
    expect(mod_icons.RM_DOTS == ('rm_dots', 'ellipsis') and mod_icons.RM_DOTS_PX == DOTS == 24 and O['RM_DOTS_RGB'] == 0x8c8c8c,
           'the "..." is the Lucide ellipsis at 24 px in #8C8C8C')
    from PIL import Image
    g = Image.open(io.BytesIO(raw_)).convert('RGBA')
    press, worst = 0x10 / 255, 99
    for level in (0, 125):   # over black, and over white under the 130/255 dim
        for pressed in (False, True):
            for k in range(5):
                for y in range(k * PLROW + (PLROW - 22) // 2, k * PLROW + (PLROW + 22) // 2):
                    p = g.getpixel((w // 2, y)); al = p[3] / 255
                    c = [al * p[i] + (1 - al) * level for i in range(3)]
                    if pressed: c = [press * 255 + (1 - press) * v for v in c]
                    worst = min(worst, contrast((255, 255, 255), c))
    expect(worst >= 7, f'white labels on the glass: worst {worst:.1f}:1 over black and over white under the dim, at rest and pressed (floor 7:1)')
    grey = contrast((0x8c, 0x8c, 0x8c), (0, 0, 0))
    expect(grey >= 3, f'the grey "..." on the black page: {grey:.1f}:1 (floor 3:1), no accent colour')
    # the two temporary Developer rows (Settings > Developer > Test: Play Next / Play After) and their log are gone
    expect(not hasattr(pod_pages, 'ACT_UPNEXT_NEXT') and not hasattr(pod_pages, 'ACT_UPNEXT_AFTER') and 'upnext_test' not in PSYMS
           and not any(r.label.startswith('Test:') for r in pod_pages.HOMESET_PAGE.rows + pod_pages.DEVELOPER_PAGE.rows if hasattr(r, 'label'))
           and not any(k.startswith('Test: Play') or k == 'Up Next Test' for k in pod_i18n.TEXT) and 'ACT_UPNEXT_NEXT' not in O,
           'the Developer test rows, their action ids, their text and upnext_test are gone')
    src = '\n'.join(open(os.path.join(ROOT, 'patch', f), encoding='utf-8').read() for f in os.listdir(os.path.join(ROOT, 'patch')) if f.endswith(('.c', '.h', '.inc')))
    expect('queue-probe' not in src and 'upnext_test' not in src, 'no source mentions the probe log or the test entry')
    # every text of the menu exists in the 13 languages (the build adds them to the tables; the i18n tests check the rest)
    keys = list(EN) + ['Undo Favorite', 'Added to Favorites', 'Removed from Favorites', 'Playing Next', 'Added to Queue'] + [TOASTS[k] for k in (STREAM, FOLDER, PODCAST, MISSING, FULL, MEMORY, DLNA)]
    expect(all(k in pod_i18n.TEXT and set(pod_i18n.TEXT[k]) == set(pod_i18n.LOCALES) for k in keys) and 'msg_addfailed' in pod_i18n.STOCK, 'the menu\'s labels, confirmations and refusals have a translation in all 13 languages')


def paint_tests(ctx):
    """2. The "..." on the rows: where it is painted (the Songs page with and without the rail, the album page), the text width it takes, none in select mode, with a page
    without the widgets."""
    expect = ctx.expect
    tx = O['LIST_TEXT_X']
    for plain, right, what in ((False, RIGHT_RAIL, 'beside the A-Z rail'), (True, RIGHT, 'at the right edge (no rail)')):
        dx = right - DOTS if not plain else right - MORE_W + (MORE_W - DOTS) // 2   # flush right beside the rail, centred in the zone otherwise
        m = songs(plain=plain)
        lay = lay_of(m, plain)
        blits, texts, styles, fills = SG.paint(m)
        dots = dot_blits(blits)
        zone = right - MORE_W
        shown = sorted(b[2][1] for b in dots)
        want = sorted(lay.row_y(i) + (ROW - 1 - DOTS) // 2 for i in range(len(LETTERS)) if lay.row_y(i) + ROW <= SG.VIEW_H)
        expect(shown == want and all(b[2][0] == dx for b in dots) and all(b[0] == dots[0][0] for b in dots) and len(want) >= 3,
               f'{what}: every row in view has its "..." at x {dx} (a {MORE_W} px zone ending at {right}; {"flush with its right edge" if not plain else "centred"}), centred above the hairline ({shown} vs {want})')
        t = titles_of(texts)
        room = right - MORE_W - GAP - tx
        expect(t and all(r[2] == room for r in t.values()) and room == (188 if plain else 162),
               f'{what}: the titles are {room} px wide ({sorted({r[2] for r in t.values()})}), cut where the "..." begins')
        dst = dots[0][2]
        expect(dst[0] == dx and dst[0] >= zone and dst[0] + DOTS <= right and zone - tx - room == GAP, f'{what}: the text ends {GAP} px before the zone, the dots are inside it')
        # the bitmap: the image's coverage as the alpha, #8C8C8C
        data, bw, bh = m.bitmaps[dots[0][0]]
        px = struct.unpack(f'<{DOTS * DOTS}I', bytes(m.u.mem_read(data, DOTS * DOTS * 4)))
        cov = [c for y in range(DOTS) for x in range(DOTS) for c in [(x * 11 + y * 7) % 250 + 3]]
        expect((bw, bh) == (DOTS, DOTS) and all(p == c << 24 | 0x8c8c8c for p, c in zip(px, cov)), 'the "..." bitmap: #8C8C8C with the image\'s coverage as its alpha')
        # select mode: no "...", the text back to x 296
        SG.pick(m, 'select')
        blits, texts, styles, fills = SG.paint(m)
        t = titles_of(texts)
        expect(not dot_blits(blits) and t and all(r[2] == (O["LIST_HAIR_END"] if plain else SG.TEXT_END) - tx - O["SG_SEL_COL"] for r in t.values()), f'select mode: no "..." and the text ends at the hairline end (284 with the rail) ({sorted({r[2] for r in t.values()})})')
        SG.click(m, 'btn_return')
        blits, texts, styles, fills = SG.paint(m)
        t = titles_of(texts)
        expect(dot_blits(blits) and all(r[2] == room for r in t.values()), f'{what}: leaving select mode brings the "..." and the narrower text back')
    # the order of the library changes the rail: a sort that has no sections takes the "..." to the edge and the text wider
    m = songs()
    m.call(PSYMS['sg_on_item'], a0=1, a1=0, count=900000000)
    blits, texts, styles, fills = SG.settle(m)
    t = titles_of(texts)
    expect(dot_blits(blits) and all(b[2][0] == RIGHT - MORE_W + (MORE_W - DOTS) // 2 for b in dot_blits(blits)) and all(r[2] == 188 for r in t.values()),
           f'another sort order (a plain list, no rail): the "..." at the right edge, titles 188 px ({sorted({r[2] for r in t.values()})})')
    # missing widgets: no "...", the old widths, and a tap there plays
    for what, kw in (('the asset has no menu', dict(menu=False)),):
        m = songs(**kw)
        lay = lay_of(m, False)
        blits, texts, styles, fills = SG.paint(m)
        t = titles_of(texts)
        expect(not dot_blits(blits) and t and all(r[2] == SG.TEXT_END - tx for r in t.values()), f'{what}: no "...", the text ends at the hairline\'s end (284 with the rail)')
        calls = SG.tap(m, 252, lay.row_y(2) + 30)
        expect(any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls) and SG.vis(m, 'vs_card') == (0, 0), f'{what}: a tap where the "..." would be plays the song')
    # the album page
    for kw, what in ((dict(), 'the album page'),):
        m = AB.album_machine()
        with_menu(m, 0)
        r, calls = AB.open_album(m)
        AB.scroll_to(m, 300)
        blits, texts, fills = AB.paint(m)
        ty = {t: rect for (t, rect), st in texts if st == 'label_row_title'}
        names = [t for t in ty if t in AB.NAMES]
        nr = len(names)
        dots = dot_blits(blits)
        ys = sorted(b[2][1] for b in dots)
        want = [AB.row_y(i) - 300 + (ROW - 1 - DOTS) // 2 for i in range(6)]
        expect(nr >= 3 and ys == want and all(b[2][0] == RIGHT - MORE_W + (MORE_W - DOTS) // 2 for b in dots),
               f'{what}: a "..." at x {RIGHT - MORE_W + (MORE_W - DOTS) // 2} on every track ({ys})')
        expect(all(ty[t][2] == RIGHT - MORE_W - GAP - (12 + O['ROW_NUM_W'] + O['AB_NUM_GAP']) for t in names), f'{what}: the titles end {GAP} px before the zone (x 262): {sorted({ty[t][2] for t in names})}')
        AB.click(m, 'btn_select')
        blits, texts, fills = AB.paint(m)
        ty = {t: rect for (t, rect), st in texts if st == 'label_row_title' and t in AB.NAMES}
        expect(not dot_blits(blits) and ty and all(rect[2] == 298 - (12 + O['ROW_NUM_W'] + O['AB_NUM_GAP'] + O['SG_SEL_COL']) for rect in ty.values()), 'album select mode: no "...", the titles end at 298')


def touch_tests(ctx):
    """3. Taps: the "..." opens the menu on the right row; a tap elsewhere in the row plays; a drag, a press that leaves the zone or that moves, and select mode do not open it."""
    expect = ctx.expect
    for plain, zx, other, what in ((False, 252, 120, 'Songs (rail)'), (True, 288, 120, 'a list (no rail)')):
        m = songs(plain=plain)
        lay = lay_of(m, plain)
        i = 2
        y = lay.row_y(i) + 30
        calls = SG.tap(m, zx, y)
        mv, shown = card_of(m)
        expect(shown == (1, 1) and SG.vis(m, 'rm_scrim') == (1, 1) and mv is not None and not any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls)
               and not any(c[0] == 'loadSongList' for c in calls), f'{what}: a tap on the "..." opens the menu (scrim and card shown) and plays nothing ({mv})')
        SG.click(m, 'rm_scrim')
        expect(SG.vis(m, 'rm_card') == (0, 0) and SG.vis(m, 'rm_scrim') == (0, 0), f'{what}: the scrim closes the menu')
        calls = SG.tap(m, other, y)
        expect(any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls) and SG.vis(m, 'rm_card') == (0, 0), f'{what}: a tap elsewhere on the row still plays the song')
        z0 = (RIGHT_RAIL if not plain else RIGHT) - MORE_W
        calls = SG.tap(m, z0 - 1, y)
        expect(any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls) and SG.vis(m, 'rm_card') == (0, 0), f'{what}: one pixel left of the zone (x {z0 - 1}) plays')
        calls = SG.tap(m, z0, y)
        expect(SG.vis(m, 'rm_card') == (1, 1), f'{what}: the zone\'s first pixel (x {z0}) opens the menu')
        SG.click(m, 'rm_scrim')
        # a drag: moved past the threshold, then released in the zone; an abort (the scroll_view took the drag) then a release
        SG.touch(m, 'down', zx, SG.SCREEN_Y0 + y, 'sg_on_down')
        SG.touch(m, 'up', zx, SG.SCREEN_Y0 + y + 14, 'sg_on_up', 1080)
        expect(SG.vis(m, 'rm_card') == (0, 0) and not any(c[0] == 'navigator_to_with_context' for c in m.calls), f'{what}: a press that moves (14 px) opens nothing and plays nothing')
        SG.touch(m, 'down', zx, SG.SCREEN_Y0 + y, 'sg_on_down')
        SG.touch(m, 'abort', zx, SG.SCREEN_Y0 + y, 'sg_on_abort')
        SG.touch(m, 'up', zx, SG.SCREEN_Y0 + y, 'sg_on_up', 1080)
        expect(SG.vis(m, 'rm_card') == (0, 0) and not any(c[0] == 'navigator_to_with_context' for c in m.calls), f'{what}: a drag the scroll_view took (abort) then a release opens nothing')
        SG.touch(m, 'down', z0 + 3, SG.SCREEN_Y0 + y, 'sg_on_down')
        SG.touch(m, 'up', z0 - 2, SG.SCREEN_Y0 + y, 'sg_on_up', 1080)
        expect(SG.vis(m, 'rm_card') == (0, 0) and not any(c[0] == 'navigator_to_with_context' for c in m.calls), f'{what}: a press that began on the "..." and ended off it (5 px) does nothing')
        SG.touch(m, 'down', z0 - 2, SG.SCREEN_Y0 + y, 'sg_on_down')
        SG.touch(m, 'up', z0 + 3, SG.SCREEN_Y0 + y, 'sg_on_up', 1080)
        expect(SG.vis(m, 'rm_card') == (0, 0), f'{what}: one that began off the zone is a row tap (it plays; it never opens the menu)')
        # the header and the air below the last row are not rows
        calls = SG.tap(m, zx, 60)
        expect(SG.vis(m, 'rm_card') == (0, 0), f'{what}: the title block has no "..."')
        # select mode: the tap marks the row
        SG.pick(m, 'select')
        calls = SG.tap(m, zx, y)
        expect(SG.vis(m, 'rm_card') == (0, 0) and ('widget_set_text_utf8', m.widgets['label_title'], '1 Selected') in calls, f'{what}: in select mode a tap in that place marks the row (1 Selected), no menu')
    # an A-Z section header or the pinned header never opens it
    m = songs()
    lay = lay_of(m, False)
    SG.tap(m, 252, lay.hdr_y(1) + 14)
    expect(SG.vis(m, 'rm_card') == (0, 0), 'a section header opens nothing')
    # the album page
    m = AB.album_machine()
    with_menu(m, 0)
    AB.open_album(m)
    AB.scroll_to(m, 300)
    AB.paint(m)
    y = AB.row_y(2) - 300 + 30
    calls = AB.tap(m, 288, y)
    expect(SG.vis(m, 'rm_card') == (1, 1) and not any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls), 'album page: a tap on the "..." opens the menu and plays nothing')
    SG.click(m, 'rm_scrim')
    calls = AB.tap(m, 150, y)
    expect(any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls) and SG.vis(m, 'rm_card') == (0, 0), 'album page: a tap elsewhere plays the track')
    AB.touch(m, 'down', 288, y, 'ab_on_down'); AB.touch(m, 'up', 288, y + 14, 'ab_on_up', 1080)
    expect(SG.vis(m, 'rm_card') == (0, 0), 'album page: a drag opens nothing')
    AB.touch(m, 'down', 288, y, 'ab_on_down'); AB.touch(m, 'abort', 288, y, 'ab_on_abort'); AB.touch(m, 'up', 288, y, 'ab_on_up', 1080)
    expect(SG.vis(m, 'rm_card') == (0, 0), 'album page: an abort then a release opens nothing')
    AB.click(m, 'btn_select')
    AB.tap(m, 288, y)
    expect(SG.vis(m, 'rm_card') == (0, 0), 'album page: select mode, no menu')


def menu_tests(ctx):
    """4. The sheet: shown in the asset's place for any row, every language fits, the scrim; the five rows and every status."""
    expect = ctx.expect
    # the sheet: the asset's place for every row, on both pages (the payload moves and resizes nothing)
    m = songs(plain=True)
    lay = lay_of(m, True)
    for i in range(6):
        SG.tap(m, 288, lay.row_y(i) + 30)
        moved, shown = card_of(m)
        expect(not moved and shown == (1, 1) and SG.vis(m, 'rm_scrim') == (1, 1), f'Songs row {i}: the sheet and the scrim show, nothing moved or resized ({moved})')
        SG.click(m, 'rm_scrim')
        m.calls = []
    for off, row in ((300, 1), (0, 0), (384, 0)):
        m = AB.album_machine()
        with_menu(m, 0)
        AB.open_album(m)
        AB.scroll_to(m, off)
        AB.paint(m)
        ry = AB.row_y(row) - off
        AB.tap(m, 288, max(ry + 30, 10))   # (a row half under the navbar is tapped where it shows)
        moved, shown = card_of(m)
        expect(not moved and shown == (1, 1), f'album page, row {row} at window y {ry}: the sheet shows, nothing moved or resized ({moved})')
        m.calls = []
    # every language's labels fit the 250 px box (the row's label is cut with an ellipsis otherwise)
    import awtk_strings
    from awtk_text import Ttf, StbText
    raw = os.path.join(WORK, 'rootfs', 'release', 'assets', 'default', 'raw')
    font = Ttf(os.path.join(raw, 'fonts', 'default.ttf'))
    widest = max((StbText(font, pod_ui.RM_LABEL_PX).layout(dict(awtk_strings.load(os.path.join(raw, 'strings', loc + '.bin')))[k])[1], loc, k)
                 for loc in pod_i18n.LOCALES for k in EN + ('Undo Favorite',))
    expect(widest[0] <= LABEL_W, f'the longest label ({widest[1]} {widest[2]!r}, {widest[0]:.0f} px) fits the {LABEL_W} px box')

    # the rows
    for page in ('songs', 'album'):
        for after, row_item in ((0, 'rm_item0'), (1, 'rm_item1')):
            for status in (ADDED, STARTED, EMPTY, STREAM, FOLDER, PODCAST, MISSING, FULL, MEMORY, DLNA):
                if page == 'songs':
                    m = songs(plain=True); rows_ = m.songs; y = SG.TOP + 3 * ROW + 30; x = 288
                    row = 3
                else:
                    m = AB.album_machine(); with_menu(m, 0); AB.open_album(m); AB.scroll_to(m, 300); AB.paint(m); rows_ = m.songs; row = 2
                    y = AB.row_y(row) - 300 + 30; x = 288
                m.up_ret = status; m.calls = []
                (SG if page == 'songs' else AB).tap(m, x, y)
                m.calls = []
                m.click(row_item)
                calls = list(m.calls)
                names = [c[0] for c in calls]
                what = f'{page}, {"Play After" if after else "Play Next"}, status {status}'
                ok_rows = m.up_calls and m.up_calls[-1][1] == after and m.up_calls[-1][0] == [rows_[row]]
                expect(len(m.up_calls) == 1 and ok_rows, f'{what}: upnext_add({after}) with a one-row deque holding the tapped row ({m.up_calls})')
                ti = [i for i, n in enumerate(names) if n == 'toast']
                order = names.index('upnext_add') < names.index('deque_destroy') < max(i for i, c in enumerate(calls) if c[0] == 'widget_set_visible' and c[1] == m.widgets['rm_card'] and c[2] == 0)
                want = ('Added to Queue' if after else 'Playing Next') if status == ADDED else None if status == STARTED else TOASTS[status]
                expect(order and names.count('deque_destroy') == 1 and SG.vis(m, 'rm_card') == (0, 0) and SG.vis(m, 'rm_scrim') == (0, 0)
                       and bool(ti and ti[0] > names.index('deque_destroy')) == (want is not None), f'{what}: the deque is destroyed and the menu closed, then the toast')
                expect(toasts(calls) == ([want] if want else []), f'{what}: the toast is {want!r} ({toasts(calls)})')
                expect(not any(c[0] == 'navigator_to_with_context' and c[1] == 'playing_page' for c in calls) and not any(c[0] in ('loadSongList', 'window_open') for c in calls),
                       f'{what}: nothing else opens (a started queue plays, the page stays)')
        # Add to Playlist: the page's one-row selection and picker
        for pk in (1, -1):
            if page == 'songs':
                m = songs(plain=True); row = 3; y = SG.TOP + row * ROW + 30; cls, count = O['CLASS_FAV'], len(LETTERS); T = SG
            else:
                m = AB.album_machine(); with_menu(m, 0); AB.open_album(m); AB.scroll_to(m, 300); AB.paint(m); row = 2; y = AB.row_y(row) - 300 + 30; T = AB
                cls, count = m.word(pod.DATA['G_CLASS_TYPE'][0]), 8
            m.pk_ret = pk
            T.tap(m, 288, y)
            m.calls = []
            m.click('rm_item2')
            calls = list(m.calls)
            marks = bytes(1 << (row & 7) if i == row >> 3 else 0 for i in range((count + 7) // 8))
            what = f'{page}, Add to Playlist (the picker {"opens" if pk > 0 else "cannot open"})'
            expect(m.pk_calls and m.pk_calls[-1] == (cls, count, marks) and SG.vis(m, 'rm_card') == (0, 0) and SG.vis(m, 'rm_scrim') == (0, 0) and not toasts(calls),
                   f'{what}: the picker gets the list\'s class {cls:#x}, {count} songs and the one mark ({m.pk_calls[-1] if m.pk_calls else None}); the menu is closed')
            expect(not m.up_calls and not any(c[0] == 'upnext_add' for c in calls), f'{what}: upnext_add is not called')
            if pk > 0:
                expect(not any(c[0] in ('select_recordinit', 'set_selectindex') for c in calls) and not any(c[0] == 'navigator_to_with_context' and c[1] == 'playlist_page' for c in calls),
                       f'{what}: our picker, not the stock one')
            else:
                expect([c[1] for c in calls if c[0] == 'set_selectindex'] == [row] and ('select_recordinit', count) in calls
                       and ('navigator_to_with_context', 'playlist_page', O['PICKER_ADD'] | cls) in calls,
                       f'{what}: the stock picker gets the stock selection vector with that row alone ({[c for c in calls if c[0] in ("set_selectindex", "select_recordinit")]})')
            # the next Add carries only its own row (the page keeps no mark behind)
            if page == 'songs':
                m.pk_ret = 1; SG.click(m, 'rm_scrim') if SG.vis(m, 'rm_scrim')[0] else None
                SG.tap(m, 288, SG.TOP + 5 * ROW + 30); m.click('rm_item2')
                want_marks = bytes(1 << (5 & 7) if i == 5 >> 3 else 0 for i in range((count + 7) // 8))
                expect(m.pk_calls[-1][2] == want_marks, f'{what}: a second Add carries only its own row ({m.pk_calls[-1][2].hex()})')
    # the menu closes when the list is read again (its row is an index of the old one) and with the window; a second tap on the scrim does nothing
    m = songs(plain=True)
    SG.tap(m, 288, SG.TOP + 30)
    m.calls = []
    m.call(PSYMS['sg_on_fg'], a0=0, a1=0, count=900000000)
    SG.click(m, 'rm_scrim')
    expect(SG.vis(m, 'rm_card') == (0, 0) and names_count(m, 'deque_destroy') <= 1, 'the scrim closes the menu once')
    SG.tap(m, 288, SG.TOP + 30)
    m.calls = []
    m.call(PSYMS['sg_on_bg'], a0=0, a1=0, count=900000000)
    expect(SG.vis(m, 'rm_card') == (0, 0) and ('deque_destroy',) in m.calls, 'the window going behind another closes the menu and drops the row\'s copy')
    SG.tap(m, 288, SG.TOP + 30)
    m.calls = []
    m.call(PSYMS['sg_on_destroy'], count=4000000)
    expect(('deque_destroy',) in m.calls, 'closing the page with the menu open frees the row\'s copy')
    expect(len(m.bitmaps) == 0, f'and every bitmap, the "..." included ({len(m.bitmaps)} left)')


def names_count(m, name): return sum(1 for c in m.calls if c[0] == name)


def row_machine(page):
    """(machine, page module, row, y): a page with the menu's widgets and a row in view (the Favourites-class list, or the album page scrolled)."""
    if page == 'songs':
        m = songs(plain=True); row = 3; y = SG.TOP + row * ROW + 30; T = SG
    else:
        m = AB.album_machine(); with_menu(m, 0); AB.open_album(m); AB.scroll_to(m, 300); AB.paint(m); row = 2; y = AB.row_y(row) - 300 + 30; T = AB
    return m, T, row, y


def fav_info_tests(ctx):
    """5. Favorite (a toggle on stock's myfav: the label and the star follow the row's state at every open, the call is checkFavExist then addMyFav / deleteMusicFromFav on the row's copy, the toast
    confirms) and Get Info (songinfo_open on the row's record, then the copy goes), on both pages."""
    expect = ctx.expect
    for page in ('songs', 'album'):
        m, T, row, y = row_machine(page)
        lab, ic = m.widgets['rm_label3'], m.widgets['rm_icon3']
        rec = m.songs[row]
        key = (m.read_cstr(m.word(rec + O['REC_NAME'])), m.read_cstr(m.word(rec + O['REC_PATH'])))
        other = m.songs[row + 1]
        okey = (m.read_cstr(m.word(other + O['REC_NAME'])), m.read_cstr(m.word(other + O['REC_PATH'])))
        expect(key != okey and key[1], f'{page}: the test rows differ ({key}, {okey})')
        T.tap(m, 288, y)
        expect(m.wtext[lab] == 'Favorite' and m.props.get((ic, 'image')) == 'rm_ic_fav' and ('checkFavExist',) + key in m.calls and SG.vis(m, 'rm_card') == (1, 1),
               f'{page}: a track that is not a favourite: the row reads "Favorite" with the outline star (one checkFavExist on the row)')
        m.calls = []
        m.click('rm_item3')
        calls = list(m.calls)
        names = [c[0] for c in calls]
        expect(m.fav_rows == [key + (m.read_cstr(m.word(rec + O['REC_TITLE'])),)] and names.count('addMyFav') == 1 and 'deleteMusicFromFav' not in names and toasts(calls) == ['Added to Favorites'],
               f'{page}: Favorite adds the row to myfav (addMyFav) and toasts "Added to Favorites" ({m.fav_rows}, {toasts(calls)})')
        expect(SG.vis(m, 'rm_card') == (0, 0) and SG.vis(m, 'rm_scrim') == (0, 0) and names.count('deque_destroy') == 1 and not m.up_calls and not m.pk_calls and not m.si_calls
               and not any(c[0] == 'window_open' or c[:2] == ('navigator_to_with_context', 'playing_page') for c in calls), f'{page}: the menu is closed and its copy freed; nothing else opens')
        T.tap(m, 288, y)
        expect(m.wtext[lab] == 'Undo Favorite' and m.props.get((ic, 'image')) == 'rm_ic_unfav', f'{page}: the same row now reads "Undo Favorite" with the filled star')
        m.calls = []
        m.click('rm_item3')
        calls = list(m.calls)
        expect(m.fav_rows == [] and [c[0] for c in calls].count('deleteMusicFromFav') == 1 and 'addMyFav' not in [c[0] for c in calls] and toasts(calls) == ['Removed from Favorites'],
               f'{page}: Undo Favorite removes it (deleteMusicFromFav) and toasts "Removed from Favorites" ({m.fav_rows}, {toasts(calls)})')
        m.fav_rows.append(okey + ('x',))
        T.tap(m, 288, y)
        expect(m.wtext[lab] == 'Favorite' and m.props.get((ic, 'image')) == 'rm_ic_fav', f'{page}: another track being a favourite does not change this row (the key is the row\'s own)')
        SG.click(m, 'rm_scrim')
        # a tap that changes nothing (the call failed) says so
        m2, T2, row2, y2 = row_machine(page)
        T2.tap(m2, 288, y2)
        orig = m2.__class__
        class Stuck(orig):
            def _hook(self, u, address, size, _):
                if self.handlers.get(address) == 'addMyFav':
                    self.calls.append(('addMyFav',)); u.reg_write(UC_MIPS_REG_V0, 0); u.reg_write(UC_MIPS_REG_PC, u.reg_read(UC_MIPS_REG_RA)); return
                return super()._hook(u, address, size, _)
        m2.__class__ = Stuck
        m2.calls = []
        m2.click('rm_item3')
        expect(toasts(m2.calls) == ['Adding Failed'] and m2.fav_rows == [] and SG.vis(m2, 'rm_card') == (0, 0), f'{page}: an add that stores nothing toasts "Adding Failed" ({toasts(m2.calls)})')
        # Get Info
        m, T, row, y = row_machine(page)
        rec = m.songs[row]
        T.tap(m, 288, y)
        m.calls = []
        m.click('rm_item4')
        calls = list(m.calls)
        names = [c[0] for c in calls]
        expect(m.si_calls == [rec], f'{page}: Get Info calls songinfo_open once, on the row\'s record ({m.si_calls})')
        expect(names.index('songinfo_open') < names.index('deque_destroy') and names.count('deque_destroy') == 1 and SG.vis(m, 'rm_card') == (0, 0) and SG.vis(m, 'rm_scrim') == (0, 0)
               and not toasts(calls) and not m.up_calls and not m.pk_calls and 'addMyFav' not in names, f'{page}: the menu closes, the page opens on the row\'s copy, then the copy is freed; no toast')


LS_DL_NONE, LS_DL_WAIT, LS_DL_ACTIVE, LS_DL_DONE, LS_DL_FAILED = range(5)
ACT_DOWNLOAD, ACT_DELETE_DL, ACT_FAVORITE, ACT_CANCEL_DL, ACT_UNFAVORITE = 1, 2, 3, 4, 5
LS_SONGS_PAGE, LS_FAVORITES = 2, 4


class Src:
    """One page over a fake library source with the menu's widgets, the same way for the album page and the Songs page: rec(i), row state, act answers, what the source was asked."""
    def __init__(self, page):
        self.page = page
        if page == 'album':
            self.m = m = AB.fake_machine(n=6)
            with_menu(m, 0)
            m.call(PSYMS['album_open_src'], a0=m.src, a1=AB.ALBUMS, a2=m.fake_row, count=900000000)
            self.T, self.recs = AB, m.fake_tracks
            AB.scroll_to(m, 300); AB.paint(m)
        else:
            m = SG.list_machine(['Stock'])
            with_menu(m, 0)
            self.recs = SG.src_records(m, ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot'])
            src = SG.fake_source(m, {LS_FAVORITES: self.recs})
            m.top_main = m.window
            m.call(PSYMS['songs_open_src'], a0=src, a1=LS_FAVORITES, a2=m.cstr('Favorites'), count=900000000)
            SG.settle(m)
            m.top_main = 0   # (no top window: the confirm dialog's scrim needs a mapped one)
            self.m, self.T = m, SG
        self.m.calls = []

    def y(self, i): return (AB.row_y(i) - 300 if self.page == 'album' else SG.TOP + i * ROW) + 30

    def state(self, i, dl=0, pct=0, dsd=0, fav=0, offline=0):
        (self.m.row_of if self.page == 'album' else self.m.fake['rows'])[self.recs[i]] = (dl, pct, dsd, fav, offline)

    def acts(self): return self.m.acts if self.page == 'album' else self.m.fake['acts']
    def acts_dd(self): return self.m.acts_dd if self.page == 'album' else self.m.fake['acts_dd']   # deques destroyed before each act
    def queued(self): return self.m.queued if self.page == 'album' else self.m.fake['queued']

    def set(self, **kw):
        for k, v in kw.items():
            if self.page == 'album': setattr(self.m, k, v)
            else: self.m.fake[k] = v

    def open(self, i):
        self.m.calls = []
        self.T.tap(self.m, 288, self.y(i))
        return SG.vis(self.m, 'rm_card') == (1, 1)

    def words(self):
        m = self.m
        return [m.wtext[m.widgets[f'rm_label{k}']] for k in range(5)], m.props.get((m.widgets['rm_icon2'], 'image')), m.props.get((m.widgets['rm_icon3'], 'image'))


def source_tests(ctx):
    """6. A source's row sheet (ND-14), on the album page and the Songs page: the third row is Download / Cancel Download / Remove Download by the row's state, Favorite / Undo Favorite from the
    source's flag, Play Next / Play After hand the source's queue record (a stream address, never nd://) to upnext_add, an undownloaded DSD row asks "Download to Play?" instead, Download / Cancel /
    Remove / Favorite go through src->act, Get Info opens the page for the row; the stock sheet still reads Add to Playlist."""
    expect = ctx.expect
    for page in ('album', 'songs'):
        # the words and glyphs by state
        want = [(dict(), 'Download', 'rm_ic_dl', 'Favorite', 'rm_ic_fav'), (dict(dl=LS_DL_FAILED), 'Download', 'rm_ic_dl', 'Favorite', 'rm_ic_fav'),
                (dict(dl=LS_DL_WAIT), 'Cancel Download', 'rm_ic_cxdl', 'Favorite', 'rm_ic_fav'), (dict(dl=LS_DL_ACTIVE, pct=42), 'Cancel Download', 'rm_ic_cxdl', 'Favorite', 'rm_ic_fav'),
                (dict(dl=LS_DL_DONE, fav=1), 'Remove Download', 'rm_ic_rmdl', 'Undo Favorite', 'rm_ic_unfav'), (dict(fav=1), 'Download', 'rm_ic_dl', 'Undo Favorite', 'rm_ic_unfav')]
        for st, third, icon, fav, favicon in want:
            S = Src(page)
            S.state(2, **st)
            ok = S.open(2)
            labels, i2, i3 = S.words()
            expect(ok and labels == ['Play Next', 'Play After', third, fav, 'Get Info'] and i2 == icon and i3 == favicon and 'checkFavExist' not in S.m.names(),
                   f'{page} {st}: the sheet reads {labels}, third glyph {i2}, star {i3}, no stock favourite call')
        # Download / Cancel / Remove through src->act
        for st, item, what, name in ((dict(), 'rm_item2', ACT_DOWNLOAD, 'Download'), (dict(dl=LS_DL_ACTIVE), 'rm_item2', ACT_CANCEL_DL, 'Cancel Download'), (dict(dl=LS_DL_WAIT), 'rm_item2', ACT_CANCEL_DL, 'Cancel Download'),
                                     (dict(dl=LS_DL_DONE), 'rm_item2', ACT_DELETE_DL, 'Remove Download')):
            S = Src(page)
            S.state(2, **st); S.open(2); S.m.calls = []
            S.m.click(item)
            expect(S.acts() == [(S.recs[2], what)] and SG.vis(S.m, 'rm_card') == (0, 0) and not S.m.up_calls and not S.m.pk_calls and not toasts(S.m.calls) and not S.queued(),
                   f'{page}, {name}: src->act({what}) on the row, the menu closes, no queue and no picker ({S.acts()})')
        # Favorite
        for fav, act_ret, toast in ((0, 0, 'Added to Favorites'), (1, 0, 'Removed from Favorites'), (0, -1, None)):
            S = Src(page)
            S.set(act_ret=act_ret); S.state(3, fav=fav); S.open(3); S.m.calls = []
            S.m.click('rm_item3')
            names = [c[0] for c in S.m.calls]
            expect(S.acts() == [(S.recs[3], ACT_UNFAVORITE if fav else ACT_FAVORITE)] and toasts(S.m.calls) == ([toast] if toast else []) and not {'addMyFav', 'deleteMusicFromFav'} & set(names) and SG.vis(S.m, 'rm_card') == (0, 0),
                   f'{page}, Favorite (star {fav}, act {act_ret}): src->act(LS_ACT_FAVORITE, or LS_ACT_UNFAVORITE when the sheet showed Undo Favorite), toast {toast!r}, no stock myfav call ({S.acts()}, {toasts(S.m.calls)})')
            expect(S.acts_dd() == [0] and [c[0] for c in S.m.calls].count('deque_destroy') == 1,
                   f'{page}, Favorite: the record is freed after src->act has read it, not before ({S.acts_dd()}, {[c[0] for c in S.m.calls].count("deque_destroy")} destroyed)')
        # Play Next / Play After: the source's queue record through upnext_add
        for after, item, ok_toast in ((0, 'rm_item0', 'Playing Next'), (1, 'rm_item1', 'Added to Queue')):
            S = Src(page)
            S.open(1); S.m.calls = []
            S.m.click(item)
            m = S.m
            rows = m.up_calls[-1][0] if m.up_calls else []
            paths = [m.read_cstr(m.word(r + O['REC_PATH'])) for r in rows]
            names = [c[0] for c in m.calls]
            expect(S.queued() == [S.recs[1]] and len(m.up_calls) == 1 and m.up_calls[0][1] == after and len(paths) == 1 and paths[0].startswith('http://') and 'nd://' not in paths[0]
                   and toasts(m.calls) == [ok_toast] and SG.vis(m, 'rm_card') == (0, 0) and names.count('deque_destroy') == 2 and not [c for c in m.calls if c[0] == 'confirm'],
                   f'{page}, {"Play After" if after else "Play Next"}: the source\'s queue record ({paths}) goes to upnext_add({after}), toast {ok_toast!r}, both deques freed')
            S = Src(page)
            S.set(queue_none=True); S.open(1); S.m.calls = []
            S.m.click(item)
            expect(S.queued() == [S.recs[1]] and not S.m.up_calls and not toasts(S.m.calls) and SG.vis(S.m, 'rm_card') == (0, 0), f'{page}, {after}: a source that cannot queue the row (it says why itself): nothing added, no second toast')
        S = Src(page)
        S.m.up_ret = STREAM
        S.open(1); S.m.calls = []; S.m.click('rm_item0')
        expect(toasts(S.m.calls) == ['Not available while streaming'], f'{page}: upnext_add\'s refusal is toasted as for a local row ({toasts(S.m.calls)})')
        # DSD: not downloaded asks to download (no queue record); downloaded queues
        for item in ('rm_item0', 'rm_item1'):
            S = Src(page)
            S.state(2, dsd=1); S.set(act_ret=0); S.m.confirm_yes = False
            S.open(2); S.m.calls = []; S.m.top_main = 0   # (no top window: the confirm dialog's scrim needs a mapped one)
            S.m.click(item)
            ask = [c for c in S.m.calls if c[0] == 'confirm']
            title = 'Charlie' if page == 'songs' else 'Remote 2'
            expect(len(ask) == 1 and ask[0][1] == f'Download to Play?\nDSD tracks play from the card. {title}, ? MB.' and not S.queued() and not S.m.up_calls and not S.acts() and SG.vis(S.m, 'rm_card') == (0, 0),
                   f'{page}, {item}: an undownloaded DSD row asks "Download to Play?" (Cancel: nothing), no queue record ({[a[1:] for a in ask]})')
            S = Src(page)
            S.state(2, dsd=1); S.set(act_ret=0); S.m.confirm_yes = True
            S.open(2); S.m.calls = []; S.m.top_main = 0
            S.m.click(item)
            expect(S.acts() == [(S.recs[2], ACT_DOWNLOAD)] and not S.m.up_calls and not S.queued(), f'{page}, {item}: Download in the confirm queues the file through src->act ({S.acts()})')
            S = Src(page)
            S.state(2, dsd=1, dl=LS_DL_DONE)
            S.open(2); S.m.calls = []
            S.m.click(item)
            expect(S.queued() == [S.recs[2]] and len(S.m.up_calls) == 1 and not [c for c in S.m.calls if c[0] == 'confirm'], f'{page}, {item}: a DSD file on the card queues like any other row')
        # Get Info
        S = Src(page)
        S.open(4); S.m.calls = []
        S.m.click('rm_item4')
        expect(S.m.si_calls == [S.recs[4]] and SG.vis(S.m, 'rm_card') == (0, 0) and not S.acts() and not toasts(S.m.calls), f'{page}: Get Info opens the page on the row ({S.m.si_calls})')
        # a row that is not a track has no sheet on the Songs page
    # a download's progress moves the source gen: the sheet stays open, the rows redraw, the list is read once the sheet has closed
    for page in ('album', 'songs'):
        S = Src(page)
        S.state(2, dl=LS_DL_ACTIVE, pct=10)
        S.open(2)
        on_gen = PSYMS['ab_on_gen'] if page == 'album' else PSYMS['sg_on_gen']
        reads = lambda: sum(1 for c in S.m.calls if c[0] == 'fake_ap_list') if page == 'album' else len(S.m.fake['asked'])
        n0 = reads()
        if page == 'songs': S.m.top_main = S.m.window   # (the page is on top: sg_on_gen reads only then)
        if page == 'album': S.m.gen += 1
        else: S.m.fake['gen'] += 1
        S.m.calls = []
        S.m.call(on_gen, count=900000000)
        expect(SG.vis(S.m, 'rm_card') == (1, 1) and reads() == (n0 if page == 'songs' else 0) and 'timer_add' in S.m.names(),
               f'{page}: gen moved while the sheet is open: the sheet stays and the list is not read ({SG.vis(S.m, "rm_card")}, {reads()})')
        S.m.click('rm_scrim')
        S.m.calls = []
        S.m.call(on_gen, count=900000000)
        expect(SG.vis(S.m, 'rm_card') == (0, 0) and reads() == (n0 + 1 if page == 'songs' else 1), f'{page}: once the sheet has closed the list is read again ({reads()})')
    # the stock sheet reads Add to Playlist again (a source's words are set at every open)
    m, T, row, y = row_machine('album')
    T.tap(m, 288, y)
    expect(m.wtext[m.widgets['rm_label2']] == 'Add to Playlist' and m.props.get((m.widgets['rm_icon2'], 'image')) == 'rm_ic_add', 'the stock sheet: the third row is Add to Playlist with its own glyph')


SECTIONS = [asset_tests, paint_tests, touch_tests, menu_tests, fav_info_tests, source_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
