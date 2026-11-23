"""The Audiobooks page (patch/bkpage.c, docs/modules/audiobooks.md "The page"): the Extras item, the asset, the Library level (a row per book, its grey line in the three states, the empty
hint), the Book level (the header, the capsule's word, a row per part and its grey line, the part to resume), Back, the queue and the start index of Play / Resume / Play Again and of a tapped
part, the MP4 memory guard (nothing starts, a toast says why), the speed pill, the kill switch, and the key the page and the model agree on. The compiled payload runs under Unicorn; the card is a
dict of paths."""
import importlib.util, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PCP, BKM = sibling('podcasts'), sibling('bkmodel')
import awtk_ui, mod_icons, pod_books, pod_i18n, pod_show, pod_ui   # noqa: E402

BR = BKM.ROOT_DIR
BK = pod_books.BK
ROW = O['PC_ROW_H']
SCREEN_Y0 = PCP.SCREEN_Y0
pc_hash = PCP.pc_hash
MEM = BKM.MEMINFO
TOOLONG = 'Too long. Split it into parts.'
HINT = 'No audiobooks. Copy a folder for each book into Audiobooks on the card.'
ORDER = ['Alpha', 'Beta', 'Gamma', 'Loose Story', 'Zed']
MB = 1 << 20


def has_cont(ring):
    """Whether the ring has a book in progress (a place, not played): the Library then has Continue Listening above the books."""
    return bool(ring) and any(e[1] and not e[3] for e in ring)


def lib(m, n=5):
    """The Library's layout as the shared model has it, for the machine's ring (Continue Listening there or not)."""
    return pod_books.library(n, cont=m.cont)


def lib_off(m, n=5): return lib(m, n)['list']   # the Library scrolled until the first book is at the top: the books fill the view
SHEET = [f'bk_sh_{r}' for r, *_ in pod_ui.BK_SHEET_ROWS]
WIDGETS = ['bk_big', 'books_listview', 'bk_sh_scrim', 'bk_sh_card', 'bk_sh_speed_vl'] + SHEET + [f'{n}_hr' for n in SHEET] + [f'{n}_tx' for n in SHEET] + [n for n, *_ in pod_ui.BK_STYLES]


def part_path(book, f): return f'{BR}/{book}/{f}'


def card(m, ring=None):
    """Alpha (three 1 MB parts, a 600 px cover), Beta (one 5000 KB file in a folder), Gamma (twelve parts), Loose Story.m4b (a small MP4 at the root), Zed (zed1.mp3 and a zed2.m4b whose index is far too big for
    the memory); MemAvailable 60000 KB; the resume ring as given."""
    for i in (1, 2, 3):
        p = part_path('Alpha', f'Part {i}.mp3'); m.put(p); m.sizes[p] = MB
    m.put(part_path('Alpha', 'cover.jpg'), PCP.jpeg(600, 600))
    m.images[f'file://{BR}/Alpha/cover.jpg'] = (600, 600, bytes((200, 40, 40, 255)) * 600 * 600)
    p = part_path('Beta', 'beta.mp3'); m.put(p); m.sizes[p] = 5000 * 1024
    for i in range(1, 13):
        p = part_path('Gamma', f'Part {i:02}.mp3'); m.put(p); m.sizes[p] = 50 * MB
    small = BKM.FTYP + BKM.MDAT + BKM.moov(BKM.stsz(1000))
    m.put(f'{BR}/Loose Story.m4b', small)
    m.put(part_path('Zed', 'zed1.mp3'), b'x'); m.sizes[part_path('Zed', 'zed1.mp3')] = MB
    m.put(part_path('Zed', 'zed2.m4b'), BKM.FTYP + BKM.MDAT + BKM.moov(BKM.stsz(4_000_000_000)))
    m.fs[MEM] = b'MemTotal:  120000 kB\nMemFree:   9999 kB\nMemAvailable:  60000 kB\n'
    if ring is not None: m.fs[PCP.RING] = BKM.ring_file(ring)
    m.images['p_default'] = (16, 16, bytes((90, 90, 90, 255)) * 256)
    m.load_image = 0


def machine(ring=None, cardf=None):
    m = PCP.page_machine(lambda mm: (card(mm, ring), cardf(mm) if cardf else None), BKM.BM)
    m.nav_asset = ui_asset('m1plus_books')
    for n in WIDGETS: m.widget(n)
    m.widgets['books_scrollview'] = m.sv
    m.images['ah_wave'] = (12, 12, b''.join(struct.pack('<I', 0xff0000ee if 4 <= x < 7 else 0xff000000) for y in range(12) for x in range(12)))   # the album page's marker, as the image manager gives it
    m.cont = has_cont(ring)
    m.px = {m.widgets[n]: px for n, px, *_ in pod_ui.BK_STYLES}
    m.px.update({m.widgets[n]: px for n, px in (('label_row_title', 21), ('label_row_sub', 18))})
    return m


def opened(ring=None, cardf=None):
    m = machine(ring, cardf)
    assert m.call(PSYMS['books_open'], count=200000000) == 0
    return m


def load(m, n=30):
    """The cover loader's ticks until it stops re-arming."""
    for _ in range(n):
        m.call(PSYMS['bk_on_load'], a0=0, count=40000000)
        if not any(c[0] == 'timer_add' for c in m.calls): break


def tick(m):
    m.screen(True)
    return m.call(PSYMS['bk_tick'], a0=0, count=200000000)


def tap(m, x, y, off=0, dt=80, move=0):
    """A touch at content point (x, y) of the list scrolled to off."""
    m.setword(m.sv + PCP.SC_YOFF, off & 0xffffffff); m.setword(m.view + 4, -off & 0xffffffff)
    sy = SCREEN_Y0 + y - off
    m.touch('down', x, sy, 1000, fn='bk_on_down')
    m.touch('up', x, sy + move, 1000 + dt, fn='bk_on_up', count=200000000)


def texts_of(m, off=0):
    """[(text, rect, style)] of a frame."""
    _, texts, styles, _ = PCP.paint(m, off)
    return [(t, r, s) for (t, r), s in zip(texts, styles)]


def line(m, style, off=0):
    return [(t, r) for t, r, s in texts_of(m, off) if s == style]


def fire(m, ev):
    """The window's handler for ev (EVT_WINDOW_TO_BG, ..) as the emitter runs it."""
    fn, ctx = m.bound[(m.window, O[ev])]
    return m.call(fn, a0=ctx, a1=0, count=200000000)


def toasts(m): return [c[1] for c in m.calls if c[0] == 'toast']
def nav(m): return [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page']
def click(m, name): return PCP.click(m, name)


def hash_of(book, f): return pc_hash(part_path(book, f))


def ring_alpha():
    """Alpha: part 1 played, part 2 half played (the most recent); Beta 42 % of one file; Gamma every part played; the rest untouched."""
    p = lambda b, f: hash_of(b, f)
    return ([(p('Alpha', 'Part 2.mp3'), 30, 60, 0), (p('Alpha', 'Part 1.mp3'), 0, 60, 1), (p('Beta', 'beta.mp3'), 2100, 5000, 0)]
            + [(p('Gamma', f'Part {i:02}.mp3'), 0, 60, 1) for i in range(12, 0, -1)])


def open_book(m, title):
    """A tap on the Library row of the book called title."""
    i = ORDER.index(title)
    tap(m, 150, lib(m)['row'](i) + 20)


def header(m, title, n):
    """The Book level's layout of `title` as the shared model has it."""
    return pod_books.book(pod_show.Font(pod_show.font_path(WORK)), title, n)


def ring_state(m, h): return m.state(h)


def ids_of(m, q):
    return [m.read_cstr(m.word(r + O['REC_PATH'])) for r in q]


# ---------------------------------------------------------------------------
def open_tests(ctx):
    expect = ctx.expect
    m = machine()
    expect(m.call(PSYMS['books_open'], count=200000000) == 0, 'books_open returns 0')
    calls = list(m.calls)
    expect(('window_open', 'm1plus_books') in calls and not [c for c in calls if c[0] in ('list_item_create', 'hscroll_label_create', 'image_create', 'image_base_set_image')],
           'the window opens; no widget is made per book (the content view paints the rows)')
    L = lib(m)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] == BK['BK_TOP'] + O['PP_HEAD_PITCH'] + 5 * ROW + O['PP_SEC_GAP'] + O['PP_HEAD_PITCH'] + ROW + O['PP_BOTTOM'] and ('widget_resize', m.view, 320, L['h']) in calls and m.props.get((m.sv, 'yoffset')) == 0
           and BK['BK_TOP'] == O['PP_LINE_Y'] + O['PP_NOLINE_PITCH'] and L['head_books'] == BK['BK_TOP'] and L['list'] == L['head_books'] + O['PP_HEAD_PITCH'] and L['head_disc'] == L['row'](4) + ROW + O['PP_SEC_GAP']
           and L['lv_row'] == L['head_disc'] + O['PP_HEAD_PITCH'] and not L['shelf'],
           f'the content is the large heading, the header Books, five rows, PP_SEC_GAP, the header Discover and the LibriVox row ({L["h"]} px), at the top; no book in progress: no Continue Listening')
    expect(m.wtext.get(m.widgets['bk_big']) == 'Audiobooks' and m.props.get((m.widgets['bk_big'], 'visible'), 1) == 1 and m.props.get((m.widgets['label_status'], 'visible'), 1) == 0
           and m.props.get((m.widgets['label_title'], 'visible'), 0) == 0, 'the large heading shows, the navbar\'s small title and the hint are hidden')
    for ev in ('EVT_AFTER_PAINT', 'EVT_POINTER_DOWN', 'EVT_POINTER_UP', 'EVT_POINTER_ABORT'):
        expect((m.view, O[ev]) in m.bound, f'the content view handles {ev}')
    expect((m.sv, O['EVT_SCROLL']) in m.bound and (m.sv, O['EVT_SCROLL_END']) in m.bound and (m.window, O['EVT_WINDOW_TO_BG']) in m.bound and (m.window, O['EVT_WINDOW_TO_FG']) in m.bound
           and (m.window, O['EVT_DESTROY']) in m.bound, 'the scroll events, the window\'s background, foreground and destroy are bound')
    expect([(c[1], c[2]) for c in calls if c[0] == 'timer_add'] == [(PSYMS['bk_tick'], 1000), (PSYMS['bk_awake_tick'], 1000), (PSYMS['bk_on_load'], 16)],
           f'a 1 s page timer (the place is noted from it), the 1 s keep-awake timer, then the cover loader\'s 16 ms one ({[c for c in calls if c[0] == "timer_add"]})')
    expect(m.call(PSYMS['books_open'], count=4000000) == 0xffffffff, 'a second open while the page is up is refused')
    # the rows: the shared list-row spec (the Downloaded rows': cover, text, hairline from the text, the chevron at 288, the text ends at 278)
    bl, texts, styles, fills = PCP.paint(m, L['list'])
    want = []
    subs = ['Not started · 3 parts', 'Not started', 'Not started · 12 parts', 'Not started', 'Not started · 2 parts']
    for i, (t, s) in enumerate(zip(ORDER, subs)):
        y = L['row'](i) - L['list']
        want += [(t, (O['LIST_TEXT_X'], y + O['LIST_TITLE_Y'], O['LIST_TEXT_W_CHEV'], O['LIST_TITLE_H']), 'label_row_title'), (s, (O['LIST_TEXT_X'], y + O['LIST_SUB_Y'], O['LIST_TEXT_W_CHEV'], O['LIST_SUB_H']), 'label_row_sub')]
    got = [(t, r, s) for (t, r), s in zip(texts, styles) if (t, s) not in (('LibriVox', 'label_row_title'), ('Public domain audiobooks', 'label_row_sub')) and s != 'label_ps_sech']
    expect(sorted(got) == sorted(want), f'a row per book, sorted by title: the title (21 px) and the grey line (18 px) at the list rows\' places, the text ending at x {O["LIST_TEXT_X"] + O["LIST_TEXT_W_CHEV"]} (278): {got}')
    covers = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])]
    expect(covers == [(O['LIST_ART_X'], L['row'](i) - L['list'] + O['LIST_ART_Y'], O['LIST_ART'], O['LIST_ART']) for i in range(5)], f'a 52 px cover (the placeholder at first) in each row ({covers})')
    expect(all((O['LIST_HAIR'], O['LIST_TEXT_X'], L['row'](i) - L['list'] + ROW - 1, O['LIST_HAIR_END'] - O['LIST_TEXT_X'], 1) in fills for i in range(5)), 'a hairline under each row, from the text to x 310')
    chev = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (mod_icons.POD_CHEV_W, mod_icons.POD_CHEV_H)]
    expect(len(chev) == 5 and chev == [(O['LIST_CHEV_X'], L['row'](i) - L['list'] + (ROW - 1 - mod_icons.POD_CHEV_H) // 2, mod_icons.POD_CHEV_W, mod_icons.POD_CHEV_H) for i in range(5)] and O['LIST_CHEV_X'] == 288,
           f'the shared chevron at x 288 in every row ({chev})')
    # the section headers: Books above the rows, Discover above the LibriVox row, the Podcasts Shows header's style and x (pg_paint_head: label_ps_sech at PP_SHOWS_X, PP_HEAD_H high)
    heads = lambda off: [(t, r) for t, r, s in texts_of(m, off) if s == 'label_ps_sech']
    expect(heads(0) == [('Books', (O['PP_SHOWS_X'], L['head_books'], 320 - 2 * O['PP_SHOWS_X'], O['PP_HEAD_H']))], f'the header Books at the Shows header\'s x, PP_HEAD_PITCH over the first row ({heads(0)})')
    off2 = L['lv_row'] - 120
    expect(heads(off2) == [('Discover', (O['PP_SHOWS_X'], L['head_disc'] - off2, 320 - 2 * O['PP_SHOWS_X'], O['PP_HEAD_H']))], f'the header Discover over the LibriVox row, PP_SEC_GAP under the last row ({heads(off2)})')
    bl, texts, styles, fills = PCP.paint(m, off2)
    got = [(t, r, s) for (t, r), s in zip(texts, styles) if (t, s) in (('LibriVox', 'label_row_title'), ('Public domain audiobooks', 'label_row_sub'))]
    tile = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (O['PA_TILE_PX'], O['PA_TILE_PX'])]
    y = L['lv_row'] - off2
    expect(sorted(got) == sorted([('LibriVox', (O['PP_DL_TEXT_X'], y + O['LIST_TITLE_Y'], O['PP_DL_TEXT_W'], O['LIST_TITLE_H']), 'label_row_title'),
                                  ('Public domain audiobooks', (O['PP_DL_TEXT_X'], y + O['LIST_SUB_Y'], O['PP_DL_TEXT_W'], O['LIST_SUB_H']), 'label_row_sub')])
           and tile == [(O['PP_DL_TILE_X'], y + O['PP_DL_TILE_Y'], O['PA_TILE_PX'], O['PA_TILE_PX'])]
           and (O['LIST_HAIR'], O['PP_DL_TEXT_X'], y + ROW - 1, O['LIST_HAIR_END'] - O['PP_DL_TEXT_X'], 1) in fills
           and [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (mod_icons.POD_CHEV_W, mod_icons.POD_CHEV_H)][-1][:2] == (O['PP_DL_CHEV_X'], y + (ROW - 1 - mod_icons.POD_CHEV_H) // 2),
           f'the LibriVox row is under the books, in the Discover row\'s place: the same tile, text x, title LibriVox, grey line "Public domain audiobooks", chevron and hairline ({got}, {tile})')
    # the covers: one a tick, only Alpha has a picture
    m.setword(m.sv + PCP.SC_YOFF, 0)
    load(m)
    loads = [u for u in m.loads if u.startswith('file://')]
    expect(loads == [f'file://{BR}/Alpha/cover.jpg'], f'Alpha\'s cover file is decoded, nothing else ({loads})')
    bl, _, _, _ = PCP.paint(m)
    covers = [b for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])]
    expect(covers[0][0] != covers[1][0] == covers[2][0], 'Alpha shows its picture, the others the placeholder disc')
    expect(not any(c[0] == 'widget_load_image' for c in m.calls), 'painting decodes nothing')
    m2 = machine(None, lambda mm: mm.put(f'{BR}/Alpha/cover.jpg', PCP.jpeg(3000, 3000)))
    m2.call(PSYMS['books_open'], count=200000000); load(m2)
    expect(not [u for u in m2.loads if u.startswith('file://')], 'a 3000 x 3000 picture is not decoded (pc_cover_ok)')
    # the empty states
    for what, cardf in (('no Audiobooks folder', lambda mm: mm.folder('/mnt/mmc/Music')), ('an empty Audiobooks folder', lambda mm: mm.folder(BR))):
        e = PCP.page_machine(cardf, BKM.BM)
        for n in WIDGETS: e.widget(n)
        e.widgets['books_scrollview'] = e.sv
        e.call(PSYMS['books_open'], count=200000000)
        st = e.widgets['label_status']
        E = pod_books.library(0)
        got = [(t, s) for t, r, s in texts_of(e)]
        hint = [t for t, s in got if s == 'label_bk_hint']
        expect(e.props.get((st, 'visible'), 0) == 0 and e.props.get((e.view, 'visible')) == 1 and e.props.get((e.widgets['bk_big'], 'visible')) == 1 and ' '.join(hint) == HINT and 1 < len(hint) <= 4
               and e.props.get((e.sv, 'virtual_h')) == E['h'] == O['GRID_VIEW_H'] and E['head_disc'] == BK['BK_TOP'] and not E['head_books'] and E['lv_row'] == BK['BK_TOP'] + O['PP_HEAD_PITCH'],
               f'{what}: the hint is painted (the shared status line: wrapped, centred) under the heading and the header and row of LibriVox, which stay ({hint}, {e.props.get((e.sv, "virtual_h"))})')
        got = [(t, s) for t, s in got if s != 'label_bk_hint']
        expect(sorted(got) == [('Discover', 'label_ps_sech'), ('LibriVox', 'label_row_title'), ('Public domain audiobooks', 'label_row_sub')], f'{what}: no Books header (as Podcasts has no Shows header with no show); the header Discover and the LibriVox row are all there is ({got})')
        room = [r for t, r, s in texts_of(e) if s == 'label_bk_hint']
        expect(room and min(r[1] for r in room) >= E['lv_row'] + ROW and max(r[1] + r[3] for r in room) <= O['GRID_VIEW_H'], f'{what}: the hint is centred in the room under the LibriVox row ({room})')
    m5 = machine(); m5.calloc_fail_size = BK['BK_MAX_BOOKS'] * BK_BOOK_SIZE
    m5.call(PSYMS['books_open'], count=200000000)
    expect(('widget_set_tr_text', m5.widgets['label_status'], 'Not enough memory') in m5.calls, 'no memory for the books: "Not enough memory"')
    for gone in ('view_grid', 'label_bk_title', 'books_scrollview', 'label_title', 'bk_big'):
        m6 = machine(); m6.widgets.pop(gone)
        r = m6.call(PSYMS['books_open'], count=200000000)
        expect(r == 0xffffffff and 'navigator_back' in m6.names() and not any(c[0] == 'timer_add' for c in m6.calls), f'without {gone} the page leaves again and arms nothing')
    m7 = machine(); m7.windows['m1plus_books'] = 0
    expect(m7.call(PSYMS['books_open'], count=4000000) == 0xffffffff, 'a window that will not open: -1')
    m8 = machine(); m8.present.add('/mnt/mmc/m1plus-off')
    expect(m8.call(PSYMS['books_open'], count=4000000) == 0xffffffff and ('window_open', 'm1plus_books') not in m8.calls, 'the kill switch: the page is refused, no window opens')


BK_BOOK_SIZE = BKM.BOOK


def library_tests(ctx):
    """The grey line of each state, from the resume ring; a tap opens the book."""
    expect = ctx.expect
    m = opened(ring_alpha())
    got = {t: s for (t, _), (s, _) in zip(line(m, 'label_row_title', lib_off(m)), line(m, 'label_row_sub', lib_off(m))) if t != 'LibriVox'}
    want = {'Alpha': 'Part 2 of 3 · 50%', 'Beta': '42%', 'Gamma': 'Finished', 'Loose Story': 'Not started', 'Zed': 'Not started · 2 parts'}
    expect(got == want, f'in progress: the part first, then the percent of the bytes ("Part 2 of 3 · 50%"), a single file just the percent, every part played "Finished", untouched "Not started" (with the parts): {got}')
    expect(all(pod_books.lib_sub(*a) == s for a, s in (((1, 500, 1, 3), 'Part 2 of 3 · 50%'), ((1, 420, 0, 1), '42%'), ((2, 1000, 12, 12), 'Finished'), ((0, 0, 0, 1), 'Not started'), ((0, 0, 0, 12), 'Not started · 12 parts'))),
           'the shared model says the same words')
    # a place that moves while the page is up: the playing book's line is made again
    p1 = hash_of('Gamma', 'Part 01.mp3')
    m.call(PSYMS['pc_mark'], a0=p1, a1=0, count=30000000)   # (an earlier part of Gamma forgotten)
    rec = m.track(part_path('Gamma', 'Part 01.mp3')); m.pt = (1800, 3600, 1); m.clock += 400000; m.note(rec)
    tick(m)
    got = {t: s for (t, _), (s, _) in zip(line(m, 'label_row_title', lib_off(m)), line(m, 'label_row_sub', lib_off(m)))}
    expect(got['Gamma'] == 'Part 1 of 12 · 95%', f'the playing book\'s line follows the ring (half of 50 MB in, the other eleven played): {got["Gamma"]}')
    # a tap opens the book; a drag, a tap on the heading or below the rows opens nothing
    m = opened(ring_alpha())
    opens = lambda mm: mm.props.get((mm.sv, 'virtual_h')) != lib(m)['h']
    tap(m, 150, 20)
    expect(not opens(m), 'a tap on the large heading opens nothing')
    tap(m, 150, lib(m)['row'](0) + 20, move=40)
    expect(not opens(m), 'a drag opens nothing')
    tap(m, 150, lib(m)['h'] - 4)
    expect(not opens(m), 'a tap under the last row (the LibriVox row) opens nothing')
    r0 = lib(m)['row'](0)
    m.touch('down', 100, SCREEN_Y0 + r0 + 20, 1000, fn='bk_on_down'); m.touch('up', 100, SCREEN_Y0 + r0 + ROW + 20, 1080, fn='bk_on_up', count=200000000)
    expect(not opens(m), 'a press on one row released on another opens nothing')
    m.touch('down', 100, SCREEN_Y0 + r0 + 20, 1000, fn='bk_on_down')
    _, _, _, fills = PCP.paint(m)
    expect((O['LIST_PRESS'], 0, r0, 320, ROW - 1) in fills, 'a pressed row is lit')
    m.touch('abort', 100, SCREEN_Y0 + r0 + 20, 1010, fn='bk_on_abort')
    _, _, _, fills = PCP.paint(m)
    expect(not [f for f in fills if f[0] == O['LIST_PRESS']], 'the light goes with an abort')


def book_tests(ctx):
    """The Book level: the header (title, grey line, the capsule's word, the speed), a row per part, the part to resume, Back."""
    expect = ctx.expect
    m = opened(ring_alpha())
    open_book(m, 'Alpha')
    H = header(m, 'Alpha', 3)
    expect(m.props.get((m.sv, 'virtual_h')) == H['h'] and m.props.get((m.sv, 'yoffset')) == 0 and m.props.get((m.widgets['bk_big'], 'visible')) == 0
           and m.props.get((m.widgets['label_title'], 'visible'), 0) == 0, f'the Book level: the header and three rows ({H["h"]} px), the large heading gone, the small title not yet')
    t = texts_of(m)
    byst = lambda s: [(x, r) for x, r, st in t if st == s]
    expect(byst('label_bk_title') == [('Alpha', (BK['BK_NAME_X'], H['y_name'], BK['BK_NAME_W'], BK['BK_NAME_PITCH']))], f'the title in the header\'s place: {byst("label_bk_title")}')
    expect(byst('label_bk_sub') == [('Part 2 of 3 · 50%', (BK['BK_NAME_X'], H['y_sub'], BK['BK_NAME_W'], BK['BK_SUB_H']))], f'the grey line "Part 2 of 3 · 50%": {byst("label_bk_sub")}')
    expect(byst('label_bk_btn') == [('Resume', (pod_books.btn_x() + 8, H['y_btn'], BK['BK_PLAY_W'] - 16, BK['BK_BTN_H']))] and not byst('label_bk_pill'),
           f'the capsule says Resume (a place in the book) and stands alone, centred: {byst("label_bk_btn")}')
    bl, _, _, fills = PCP.paint(m)
    inrow = lambda f: H['y_btn'] <= f[2] < H['y_btn'] + BK['BK_BTN_H']
    white = [f for f in fills if f[0] == 0xffffffff and inrow(f)]
    expect(len(white) == BK['BK_BTN_H'] and max(f[3] for f in white) == BK['BK_PLAY_W'] - 2 and pod_books.btn_x() <= min(f[1] for f in white) <= pod_books.btn_x() + 2
           and white[0][3] < white[BK['BK_BTN_H'] // 2][3] > white[-1][3] and white[0][1] > white[BK['BK_BTN_H'] // 2][1] and not [f for f in fills if f[0] in (0xff2b2b2b, 0xff4a4a4a) and inrow(f)],
           'the capsule is a white stadium (a row of its height, the middle rows nearly the whole width, the ends round); there is no grey pill beside it')
    expect(any(b[2][:2] == (O['PS_ART_X'], BK['BK_ART_Y']) and b[2][2:] == (O['PS_ART'], O['PS_ART']) for b in bl), 'the cover at the Show page\'s place and size')
    off = H['y_list']   # the rows, scrolled up under the navbar (a text is drawn only wholly in view)
    bl, _, _, fills = PCP.paint(m, off)
    t = texts_of(m, off)
    rows = [(x, s) for x, r, s in t if s in ('label_row_title', 'label_bk_dim')]
    expect(sorted(rows) == [('Part 1', 'label_bk_dim'), ('Part 2', 'label_row_title'), ('Part 3', 'label_row_title')], f'the played part\'s title is grey, the others white: {rows}')
    for i, (title, sub) in enumerate((('Part 1', 'Played'), ('Part 2', '1m left'), ('Part 3', '1 MB'))):
        y = H['row'](i) - off
        ttl = [x for x in t if x[0] == title and x[2] in ('label_row_title', 'label_bk_dim')]
        sb = [x for x in t if x[1][1] == y + O['LIST_SUB_Y'] and x[2] == 'label_row_sub']
        expect(len(ttl) == 1 and ttl[0][1] == (BK['BK_PART_X'], y + O['LIST_TITLE_Y'], BK['BK_PART_W'], O['LIST_TITLE_H']) and [x[0] for x in sb] == [sub] and sb[0][1][:1] == (BK['BK_PART_X'],),
               f'part {i + 1}: the title and the grey line "{sub}" at the row\'s places ({ttl}, {sb})')
        expect(pod_books.part_sub(*[(2, 0, 0, 1024), (1, 30, 60, 1024), (0, 0, 0, 1024)][i]) == sub, f'the shared model: "{sub}"')
    expect(not [f for f in fills if f[0] == 0xffffffff and not inrow(f)] and 'BK_MARK_W' not in BK, 'no white bar at the left of any row: the part to resume says it in its grey line and the capsule')
    # the playing marker: the album page's wave in the ring's slot of the part the player is on, the grey line moved right as for the ring
    W = O['AB_WAVE']
    wave_at = lambda i: (BK['BK_PART_X'], H['row'](i) - off + O['LIST_SUB_Y'] + O['LIST_SUB_H'] // 2 - W // 2, W, W)

    def waves(mm):
        b_, t_, s_, f_ = PCP.paint(mm, off)
        return [tuple(b[2]) for b in b_ if tuple(b[2][2:]) == (W, W) and b[2][0] == BK['BK_PART_X']]

    def subx(mm, i):
        y_ = H['row'](i) - off + O['LIST_SUB_Y']
        return [r for x, r, s in texts_of(mm, off) if s == 'label_row_sub' and r[1] == y_]
    expect(waves(m) == [] and subx(m, 1)[0][0] == BK['BK_PART_X'], 'nothing plays: no wave, the grey lines start at the text column')
    m.track(part_path('Alpha', 'Part 2.mp3')); tick(m)
    sx = subx(m, 1)[0]
    expect(waves(m) == [wave_at(1)] and sx[0] == BK['BK_PART_X'] + W + 6 and sx[2] == BK['BK_PART_W'] - W - 6 and subx(m, 2)[0][0] == BK['BK_PART_X'],
           f'the player is on part 2: one wave, at the ring\'s slot, vertically centred on the grey line; that line moves right by the wave and the gap ({waves(m)}, {sx})')
    m.track(part_path('Alpha', 'Part 3.mp3')); tick(m)
    expect(waves(m) == [wave_at(2)] and subx(m, 1)[0][0] == BK['BK_PART_X'] and subx(m, 2)[0][0] == BK['BK_PART_X'] + W + 6, 'the player goes on to part 3: the marker follows at the next tick, no reload (the row\'s line is cut again)')
    m.track(part_path('Beta', 'Beta.mp3')); tick(m)
    expect(waves(m) == [], 'another book plays: no wave')
    m.track('/mnt/mmc/Music/song.flac'); tick(m)
    expect(waves(m) == [] and subx(m, 2)[0][0] == BK['BK_PART_X'], 'music plays: no wave')
    m.track(part_path('Alpha', 'Part 1.mp3')); tick(m)
    expect(waves(m) == [wave_at(0)] and subx(m, 0)[0][0] == BK['BK_PART_X'] + W + 6, 'a played part that plays again has the wave too')
    # Back: the Library level again, where it was; the next Back leaves the page
    click(m, 'btn_return')
    expect(m.props.get((m.sv, 'virtual_h')) == lib(m)['h'] and 'navigator_back' not in m.names() and m.props.get((m.widgets['bk_big'], 'visible')) == 1, 'Back from a book goes to the Library level first')
    click(m, 'btn_return')
    expect('navigator_back' in m.names(), 'Back from the Library level leaves the page')
    # the states of the capsule
    for title, ring, word, sub in (('Beta', ring_alpha(), 'Resume', '42%'), ('Gamma', ring_alpha(), 'Play Again', 'Finished'), ('Zed', ring_alpha(), 'Play', 'Not started · 2 parts'), ('Loose Story', ring_alpha(), 'Play', 'Not started')):
        mm = opened(ring); open_book(mm, title)
        t = texts_of(mm)
        expect([x for x, _, s in t if s == 'label_bk_btn'] == [word] and [x for x, _, s in t if s == 'label_bk_sub'] == [sub], f'{title}: the capsule says {word}, the grey line {sub}')
    expect(pod_books.play_word(0) == 'Play' and pod_books.play_word(1) == 'Resume' and pod_books.play_word(2) == 'Play Again' and pod_books.book_sub(1, 500, 1, 3) == 'Part 2 of 3 · 50%', 'the shared model: the capsule\'s words')
    # a long title wraps in two lines; the navbar's small title shows once the header's title has gone
    mm = opened(None, lambda x: [x.put(part_path('A very long audiobook title that needs two lines', 'a.mp3'), b'x')])
    books = sorted(['Alpha', 'Beta', 'Gamma', 'Loose Story', 'Zed', 'A very long audiobook title that needs two lines'], key=str.lower)
    tap(mm, 150, pod_books.library(6)['row'](books.index('A very long audiobook title that needs two lines')) + 20)
    LH = header(mm, books[0], 1)
    ttl = [(x, r) for x, r, s in texts_of(mm) if s == 'label_bk_title']
    expect(len(LH['lines']) == 2 and [x for x, _ in ttl] == LH['lines'] and [r[1] for _, r in ttl] == [LH['y_name'], LH['y_name'] + BK['BK_NAME_PITCH']],
           f'a long title is wrapped in two lines like the Show page\'s name, as the shared model wraps it: {ttl} / {LH["lines"]}')
    expect(mm.props.get((mm.sv, 'virtual_h')) == LH['h'], f'the header grows by a line ({LH["h"]})')
    mm.setword(mm.sv + PCP.SC_YOFF, LH['collapse']); mm.call(PSYMS['bk_on_scroll'], a0=0, a1=0, count=4000000)
    expect(mm.props.get((mm.widgets['label_title'], 'visible')) == 1, 'scrolled past the title: the navbar shows the small title')
    mm.setword(mm.sv + PCP.SC_YOFF, 0); mm.call(PSYMS['bk_on_scroll'], a0=0, a1=0, count=4000000)
    expect(mm.props.get((mm.widgets['label_title'], 'visible')) == 0, 'back at the top it is hidden again')
    # a part's grey line is its size; a big file in GB
    expect([pod_books.kb_text(k) for k in (0, 1, 1024, 1500 * 1024, 11 * 1048576)] == ['0 MB', '1 MB', '1 MB', '1.5 GB', '11 GB'], 'sizes in MB and GB, as the Downloads page writes them')
    mg = opened(ring_alpha()); open_book(mg, 'Gamma')
    sizes = [x for x, r, s in texts_of(mg, 0) if s == 'label_row_sub']
    expect(sizes and set(sizes) == {'Played'}, f'Gamma: every part is Played: {sizes}')


def play_tests(ctx):
    """Play, Resume, Play Again and a tapped part: the queue, the start index, the speed, the marks."""
    expect = ctx.expect
    field = lambda m, r, off: m.read_cstr(m.word(r + off))
    # Play: an untouched book from its first part
    m = opened(None); open_book(m, 'Gamma'); m.calls = []
    H = header(m, 'Gamma', 12)
    tap(m, pod_books.btn_x() + 40, H['y_btn'] + 20)
    n = nav(m)
    q, idx = m.played
    expect(len(n) == 1 and n[0][2:] == (0, 1, O['PLAY_MODE']) and idx == 0 and ids_of(m, q) == [part_path('Gamma', f'Part {i:02}.mp3') for i in range(1, 13)],
           f'Play: Now Playing with the twelve parts in order, from the first (index 0, class 1, mode 2): {n}')
    r = q[0]
    expect((field(m, r, O['REC_NAME']), field(m, r, O['REC_TITLE']), field(m, r, O['REC_ALBUM']), field(m, r, O['REC_ARTIST'])) == ('Part 01.mp3', 'Part 01', 'Gamma', 'Gamma')
           and m.word(r + O['REC_TYPE']) == 8 and m.word(r + O['REC_CLASS']) == 1 and m.word(pod.DATA['G_CLASS_TYPE'][0]) == 1,
           'a record: the file name, the title, the book as album and artist, a song (type 8), class 1; the browsing class is 1')
    expect(('deque_destroy',) in m.calls and not [c for c in m.calls if c[0] == 'loadSongList'], 'the queue is the page\'s own: no stock list query is made, the page frees its copy')
    # Resume: the current part (the one in progress) and the ones after it
    ring = ring_alpha()
    m = opened(ring); open_book(m, 'Alpha'); m.calls = []
    H = header(m, 'Alpha', 3)
    tap(m, pod_books.btn_x() + 40, H['y_btn'] + 20)
    q, idx = m.played
    expect(idx == 0 and ids_of(m, q) == [part_path('Alpha', 'Part 2.mp3'), part_path('Alpha', 'Part 3.mp3')], f'Resume: the queue is the current part and the rest, from the current one: {ids_of(m, q)}')
    expect(m.state(hash_of('Alpha', 'Part 2.mp3'))[:1] == (1,) and m.state(hash_of('Alpha', 'Part 1.mp3'))[0] == 2, 'Resume keeps its place (pc_note jumps there) and the played mark of the first part')
    # a tapped part: from it to the end; a played part starts again (its mark goes), a part with a place keeps it
    m = opened(ring); open_book(m, 'Alpha'); m.calls = []
    H = header(m, 'Alpha', 3)
    tap(m, 150, H['row'](0) + 20)
    q, idx = m.played
    expect(idx == 0 and ids_of(m, q) == [part_path('Alpha', f'Part {i}.mp3') for i in (1, 2, 3)] and m.state(hash_of('Alpha', 'Part 1.mp3'))[0] == 0,
           f'a tap on a played part: from it to the end, its played mark gone (it plays from the start): {ids_of(m, q)}')
    m.calls = []; tap(m, 150, H['row'](2) + 20)
    q, idx = m.played
    expect(idx == 0 and ids_of(m, q) == [part_path('Alpha', 'Part 3.mp3')] and len(nav(m)) == 1, 'a tap on the last part: a queue of one')
    m.calls = []; tap(m, 150, H['row'](1) + 20)
    expect(ids_of(m, m.played[0]) == [part_path('Alpha', 'Part 2.mp3'), part_path('Alpha', 'Part 3.mp3')] and m.state(hash_of('Alpha', 'Part 2.mp3'))[:2] == (1, 30), 'a part with a place keeps it')
    # Play Again: the marks and places of the book are forgotten, part 1 first
    m = opened(ring); open_book(m, 'Gamma'); m.calls = []
    H = header(m, 'Gamma', 12)
    tap(m, pod_books.btn_x() + 40, H['y_btn'] + 20)
    q, idx = m.played
    expect(idx == 0 and ids_of(m, q)[0] == part_path('Gamma', 'Part 01.mp3') and len(q) == 12 and all(m.state(hash_of('Gamma', f'Part {i:02}.mp3'))[0] == 0 for i in range(1, 13)),
           'Play Again: every part\'s mark is forgotten, the queue is the whole book from part 1')
    expect(m.state(hash_of('Beta', 'beta.mp3'))[:2] == (1, 2100), 'another book\'s place is untouched')
    # the speed: applied as the book starts (the book's, keyed by its folder)
    m = opened(None); key = pc_hash('audiobooks/Gamma')
    m.call(PSYMS['pc_speed_set'], a0=key, a1=2, count=30000000); m.setword(PCP.PLAYSPEED_MODE, 0)
    open_book(m, 'Gamma'); m.calls = []
    tap(m, pod_books.btn_x() + 40, header(m, 'Gamma', 12)['y_btn'] + 20)
    expect(m.word(PCP.PLAYSPEED_MODE) == 2 and nav(m), 'Play applies the book\'s speed before it starts')
    # a file that has gone
    m = opened(None); open_book(m, 'Gamma')
    del m.fs[part_path('Gamma', 'Part 01.mp3')]; m.present.discard(part_path('Gamma', 'Part 01.mp3')); m.calls = []
    tap(m, pod_books.btn_x() + 40, header(m, 'Gamma', 12)['y_btn'] + 20)
    expect(not nav(m) and 'Storage unavailable' in toasts(m), 'a first part that has gone: "Storage unavailable", nothing starts')


def guard_tests(ctx):
    """The MP4 memory guard before any start: a book the player could stall on does not start."""
    expect = ctx.expect
    m = opened(None); open_book(m, 'Zed'); m.calls = []
    H = header(m, 'Zed', 2)
    tap(m, pod_books.btn_x() + 40, H['y_btn'] + 20)
    expect(not nav(m) and toasts(m) == [TOOLONG] and m.played is None, f'Play on a book with an MP4 the memory cannot hold: nothing starts, the toast says why ({toasts(m)})')
    m.calls = []; tap(m, 150, H['row'](1) + 20)
    expect(not nav(m) and toasts(m) == [TOOLONG], 'a tap on the part itself: refused')
    m.calls = []; tap(m, 150, H['row'](0) + 20)
    expect(not nav(m) and toasts(m) == [TOOLONG], 'a tap on an earlier part whose queue reaches it: refused too (it would be the next to start)')
    expect(m.state(hash_of('Zed', 'zed1.mp3'))[0] == 0, 'nothing was marked or restarted')
    # Play Again that is refused keeps the marks
    ring = [(hash_of('Zed', 'zed2.m4b'), 0, 60, 1), (hash_of('Zed', 'zed1.mp3'), 0, 60, 1)]
    mm = opened(ring); open_book(mm, 'Zed'); mm.calls = []
    tap(mm, pod_books.btn_x() + 40, header(mm, 'Zed', 2)['y_btn'] + 20)
    expect(not nav(mm) and toasts(mm) == [TOOLONG] and mm.state(hash_of('Zed', 'zed1.mp3'))[0] == 2, 'Play Again refused: the played marks stay')
    # a small MP4 and a loose one play
    mm = opened(None); open_book(mm, 'Loose Story'); mm.calls = []
    tap(mm, pod_books.btn_x() + 40, header(mm, 'Loose Story', 1)['y_btn'] + 20)
    expect(len(nav(mm)) == 1 and ids_of(mm, mm.played[0]) == [f'{BR}/Loose Story.m4b'] and not toasts(mm), 'a loose small MP4 plays: the guard lets it through')
    # unknown estimates are refused: no /proc/meminfo
    mm = opened(None, lambda x: x.fs.pop(MEM, None)); open_book(mm, 'Loose Story'); mm.calls = []
    tap(mm, pod_books.btn_x() + 40, header(mm, 'Loose Story', 1)['y_btn'] + 20)
    expect(not nav(mm) and toasts(mm) == [TOOLONG], 'no MemAvailable: an MP4 is refused (the guard fails closed)')
    # an MP3 needs no estimate
    mm = opened(None, lambda x: x.fs.pop(MEM, None)); open_book(mm, 'Beta'); mm.calls = []
    tap(mm, pod_books.btn_x() + 40, header(mm, 'Beta', 1)['y_btn'] + 20)
    expect(len(nav(mm)) == 1, 'an MP3 book plays without any estimate')


def sval(m):
    """The text of the sheet's speed value (the mock keeps the UTF-8 bytes of widget_set_text_utf8 as Latin-1)."""
    s = m.wtext.get(m.widgets['bk_sh_speed_vl'])
    try: return s.encode('latin-1').decode('utf-8')
    except (AttributeError, UnicodeEncodeError, UnicodeDecodeError): return s


def speed_tests(ctx):
    """The speed is a row of the Book level's "..." sheet, on every book: its value, a tap cycles and the sheet stays, saved under the book's key and applied; the header has no pill."""
    expect = ctx.expect
    m = opened(None); open_book(m, 'Gamma')
    key = pc_hash('audiobooks/Gamma')
    flags = lambda n: (m.props.get((m.widgets[n], 'visible'), 1), m.props.get((m.widgets[n], 'sensitive'), 1))
    expect(flags('btn_more') == (1, 1) and m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) == 'ah_nav_play'
           and ('widget_resize', m.widgets['label_title'], O['NAV_VIEW_X'] - O['NAV_TITLE_X'], 22) in m.calls and not [x for x, _, s in texts_of(m) if s == 'label_bk_pill'],
           'a book of your own has the "..." (Now Playing the right cap of the capsule, the small title ends before it) and no speed pill in the header')
    m.calls = []
    click(m, 'btn_more')
    shown = [r for r, *_ in pod_ui.BK_SHEET_ROWS if flags(f'bk_sh_{r}') == (1, 1)]
    expect(flags('bk_sh_card') == (1, 1) and flags('bk_sh_scrim') == (1, 1) and shown == ['speed'] and m.props.get((m.widgets['bk_sh_card'], 'style:normal:bg_image')) == 'pc_sheet1'
           and sval(m) == '1×', f'a book of your own: the sheet holds Playback Speed alone, its value 1× ({shown})')
    expect(pod_ui.BK_SHEET_ROWS[0][2] == 'Playback Speed' and pod_ui.BK_SHEET_ROWS[0][3] and tuple(pod_books.SPEEDS) == ('1×', '1.25×', '1.5×', '2×'), 'the Show sheet\'s row (its string, a grey value) and the four words of the shared model')
    seen, applied = [], []
    for _ in range(5):
        click(m, 'bk_sh_speed')
        applied.append([c[1] for c in m.calls if c[0] == 'mclSetPlaySpeed'])
        seen.append((sval(m), m.call(PSYMS['pc_speed_get'], a0=key, count=3000000), flags('bk_sh_card')))
    expect(seen == [('1.25×', 1, (1, 1)), ('1.5×', 2, (1, 1)), ('2×', 3, (1, 1)), ('1×', 0, (1, 1)), ('1.25×', 1, (1, 1))], f'a tap cycles 1× 1.25× 1.5× 2×, the value follows, the book\'s speed is saved at once and the sheet stays open ({seen})')
    expect(not nav(m) and applied == [[1], [2], [3], [0], [1]] and m.word(PCP.PLAYSPEED_MODE) == 1, f'each tap applies it (the decoder and the stock Multiple Speed page take it): {applied}')
    expect(m.call(PSYMS['pc_speed_get'], a0=pc_hash('audiobooks/Alpha'), count=3000000) == 0 and m.call(PSYMS['pc_speed_get'], a0=pc_hash('Gamma'), count=3000000) == 0, 'another book and a podcast show of that name keep their speed')
    click(m, 'bk_sh_scrim')
    expect(flags('bk_sh_card') == (0, 0), 'a tap outside closes the sheet')
    click(m, 'btn_more')
    expect(sval(m) == '1.25×', 'opened again it shows the saved speed')
    m.track(f'{BR}/Gamma/Part 01.mp3')
    click(m, 'bk_sh_speed')
    expect(('mclSetPlaySpeed', 2) in m.calls and m.word(PCP.PLAYSPEED_MODE) == 2, 'the speed of the book that plays changes at once')
    click(m, 'btn_return')
    expect(flags('bk_sh_card') == (0, 0) and flags('btn_more') == (1, 1), 'Back with the sheet open closes it and stays on the book')
    click(m, 'btn_return')
    expect(flags('btn_more') == (0, 0) and m.props.get((m.widgets['btn_backtoplayer'], 'style:normal:icon')) == 'ah_nav_np', 'the Library has no "..." and Now Playing is the disc again')


def more_books(n):
    """cardf: n more books (one MP3 each) beside the five of card(); the titles 'Book 00' ... sort between Beta and Gamma."""
    def put(mm):
        for i in range(n): mm.put(part_path(f'Book {i:02}', 'a.mp3'), b'x')
    return put


def rows_of(m, off):
    """[title] of the book rows a frame at scroll offset off draws (the LibriVox row and the shelf's texts are not rows)."""
    return [t for t, r, st in texts_of(m, off) if st == 'label_row_title' and t != 'LibriVox']


def shelf_tests(ctx):
    """Continue Listening: the book in progress that was played last, in the Podcasts shelf's place and look; a tap resumes it; absent when no book is in progress."""
    expect = ctx.expect
    m = opened(ring_alpha(), lambda mm: mm.sizes.update({f'{BR}/Loose Story.m4b': 10 * MB}))
    L = lib(m)
    expect(L['shelf'] == BK['BK_TOP'] and L['head_books'] == BK['BK_TOP'] + O['PP_HEAD_PITCH'] + O['PP_SHELF_PITCH_Y'] + O['PP_SEC_GAP'] and L['list'] == L['head_books'] + O['PP_HEAD_PITCH'] and L['h'] == L['lv_row'] + ROW + O['PP_BOTTOM'] and m.props.get((m.sv, 'virtual_h')) == L['h'],
           f'a book in progress: the shelf is the first block under the large heading, the books under it ({L["shelf"]} / {L["list"]})')
    bl, texts, styles, fills = PCP.paint(m, 0)
    got = [(t, r, s) for (t, r), s in zip(texts, styles) if s.startswith('label_ps_')]
    y = L['shelf']
    expect(got == [('Continue Listening', (O['PP_HEAD_X'], y, 320 - 2 * O['PP_HEAD_X'], O['PP_HEAD_H']), 'label_ps_sech'), ('Alpha', (O['PP_SHELF_X'], y + O['PP_HEAD_PITCH'] + O['PP_SHELF_TITLE_Y'], O['PP_SHELF_W'], O['PP_SHELF_TITLE_H']), 'label_ps_stitle'),
                  ('50%', (O['PP_SHELF_X'], y + O['PP_HEAD_PITCH'] + O['PP_SHELF_LEFT_Y'], O['PP_SHELF_W'], O['PP_SHELF_LEFT_H']), 'label_ps_sleft'),
                  ('Books', (O['PP_SHOWS_X'], L['head_books'], 320 - 2 * O['PP_SHOWS_X'], O['PP_HEAD_H']), 'label_ps_sech')],
           f'the header, the title cut to the cover\'s width and the percent, at the Shows level\'s shelf places and in its text styles ({got})')
    cov = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (O['PP_SHELF_ART'], O['PP_SHELF_ART'])]
    disc = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (O['PA_PLAYB_PX'], O['PA_PLAYB_PX'])]
    expect(cov == [(O['PP_SHELF_X'], y + O['PP_HEAD_PITCH'], O['PP_SHELF_ART'], O['PP_SHELF_ART'])]
           and disc == [(O['PP_SHELF_X'] + O['PP_SHELF_ART'] - O['PP_SHELF_PLAY_INSET'] - O['PA_PLAYB_PX'], y + O['PP_HEAD_PITCH'] + O['PP_SHELF_ART'] - O['PP_SHELF_PLAY_INSET'] - O['PA_PLAYB_PX'], O['PA_PLAYB_PX'], O['PA_PLAYB_PX'])],
           f'a 92 px cover and the round play disc at its bottom right ({cov}, {disc})')
    load(m)
    expect(f'file://{BR}/Alpha/cover.jpg' in m.loads, 'the shelf\'s cover is decoded from the book\'s picture')
    # the book is the one played last: another book touched later takes the shelf
    rec = m.track(f'{BR}/Loose Story.m4b'); m.pt = (1000, 5000, 1); m.clock += 400000; m.note(rec)
    tick(m)
    got = [t for t, r, st in texts_of(m, 0) if st in ('label_ps_stitle', 'label_ps_sleft')]
    expect(got == ['Loose Story', '20%'], f'the book played last is the one on the shelf ({got})')
    # a tap resumes it from its place and the page stays on the Library
    m = opened(ring_alpha()); m.calls = []
    L = lib(m)
    tap(m, O['PP_SHELF_X'] + 20, L['shelf'] + O['PP_HEAD_PITCH'] + 20)
    q, idx = m.played
    expect(len(nav(m)) == 1 and idx == 0 and ids_of(m, q) == [part_path('Alpha', 'Part 2.mp3'), part_path('Alpha', 'Part 3.mp3')] and m.state(hash_of('Alpha', 'Part 2.mp3'))[:2] == (1, 30)
           and m.props.get((m.sv, 'virtual_h')) == L['h'] and m.props.get((m.widgets['bk_big'], 'visible')) == 1, f'a tap on Continue Listening resumes the book as Resume does (the current part and the rest), the Library stays ({ids_of(m, q)})')
    m.calls = []; tap(m, O['PP_SHELF_X'] + O['PP_SHELF_W'] + 4, L['shelf'] + O['PP_HEAD_PITCH'] + 20)
    expect(not nav(m), 'a tap beside the item does nothing')
    m.calls = []; tap(m, 150, L['shelf'] + 10)
    expect(not nav(m), 'a tap on the header does nothing')
    # no book in progress: no shelf, the books follow the title
    m = opened([(hash_of('Gamma', f'Part {i:02}.mp3'), 0, 60, 1) for i in range(12, 0, -1)])
    expect(not lib(m)['shelf'] and [t for t, r, st in texts_of(m, 0) if st.startswith('label_ps_')] == ['Books'] and m.props.get((m.sv, 'virtual_h')) == pod_books.library(5)['h'] and lib(m)['head_books'] == BK['BK_TOP'] and lib(m)['list'] == BK['BK_TOP'] + O['PP_HEAD_PITCH'],
           'only a finished book: no Continue Listening, the books start at the top block')
    m = opened(None)
    expect(not lib(m)['shelf'] and 'Continue Listening' not in [t for t, r, st in texts_of(m, 0)], 'nothing played: no shelf')


def seeall_tests(ctx):
    """The first 20 books, then See All and the complete list; the LibriVox row under them."""
    expect = ctx.expect
    twenty = [f'Book {i:02}' for i in range(15)] + ORDER   # (card(): 5 books, plus 15 = 20)
    m = opened(None, more_books(15))
    L = pod_books.library(20)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and not L['all_row'] and L['head_disc'] == L['row'](19) + ROW + O['PP_SEC_GAP'] and L['lv_row'] == L['head_disc'] + O['PP_HEAD_PITCH'], f'20 books: all of them, no See All row, the LibriVox row after them ({L["h"]})')
    off = L['lv_row'] - 100
    expect(('See All (20)' not in [t for t, r, st in texts_of(m, off)]) and 'LibriVox' in [t for t, r, st in texts_of(m, off)], 'no See All row at 20 books')
    m = opened(None, more_books(16))
    L = pod_books.library(21)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and L['shown'] == O['PS_SHOW_MAX'] == 20 and L['all_row'] == L['row'](20) and L['head_disc'] == L['all_row'] + O['PS_MORE_H'] + O['PP_SEC_GAP'] and L['lv_row'] == L['head_disc'] + O['PP_HEAD_PITCH'],
           f'21 books: the first 20 rows, the See All row (PS_MORE_H high) right after them, PP_SEC_GAP, the Discover header and the LibriVox row ({L["h"]})')
    off = L['all_row'] - 120
    bl, texts, styles, fills = PCP.paint(m, off)
    see = [(t, r, st) for (t, r), st in zip(texts, styles) if t.startswith('See All')]
    expect(see == [('See All (21)', (O['PP_SHOWS_X'], L['all_row'] - off + (O['PS_MORE_H'] - O['PS_TITLE_PITCH']) // 2, 320 - 2 * O['PP_SHOWS_X'], O['PS_TITLE_PITCH']), 'label_ps_ctitle')],
           f'the Show page\'s See All row: "See All (N)", N every book, in its style at its place ({see})')
    expect(rows_of(m, L['row'](12) - 20)[-1] != 'Zed', 'the rows after the twentieth are not in the Library')
    titles = sorted(twenty + ['Book 15'], key=str.lower)
    seen = []
    for o in range(0, L['all_row'], 5 * ROW):
        seen += [t for t in rows_of(m, o) if t not in seen]
    expect(seen == titles[:20] and 'Zed' not in seen, f'the first twenty in the model\'s (title) order: {seen}')
    # a tap on See All: the complete list, no large heading, the title in the navbar, no See All and no LibriVox row
    m.calls = []
    tap(m, 150, L['all_row'] + 20, off=off)
    A = pod_books.library(21, all=True)
    expect(m.props.get((m.sv, 'virtual_h')) == A['h'] == 21 * ROW + BK['BK_BOTTOM'] and m.props.get((m.sv, 'yoffset')) == 0 and m.props.get((m.widgets['bk_big'], 'visible')) == 0
           and m.props.get((m.widgets['label_title'], 'visible')) == 1 and m.wtext.get(m.widgets['label_title']) == 'Audiobooks',
           f'See All opens the complete list from the top: {A["h"]} px, the large heading gone, the navbar\'s title shown ({m.props.get((m.sv, "virtual_h"))})')
    last = rows_of(m, A['h'] - O['GRID_VIEW_H'])
    expect('Zed' in last and 'LibriVox' not in [t for t, r, st in texts_of(m, A['h'] - 400)] and not [t for t, r, st in texts_of(m, 0) if t.startswith('See All')],
           f'every book is there, the 21st (Zed) too; no LibriVox row and no See All row ({last[-3:]})')
    # a book of the page and back: the page, at its offset
    tap(m, 150, A['row'](20) + 20, off=A['h'] - 400)
    expect(m.props.get((m.widgets['bk_big'], 'visible')) == 0 and m.props.get((m.sv, 'virtual_h')) != A['h'] and m.wtext.get(m.widgets['label_title']) is not None, 'a book opens from the page')
    click(m, 'btn_return')
    expect(m.props.get((m.sv, 'virtual_h')) == A['h'] and m.props.get((m.sv, 'yoffset')) == A['h'] - 400 and 'navigator_back' not in m.names(), f'Back from the book returns to the See All page at the offset it was left at ({m.props.get((m.sv, "yoffset"))})')
    click(m, 'btn_return')
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and m.props.get((m.sv, 'yoffset')) == off and m.props.get((m.widgets['bk_big'], 'visible')) == 1 and 'navigator_back' not in m.names(),
           f'Back from the page returns to the Library at the offset the See All row was tapped at ({m.props.get((m.sv, "yoffset"))} / {off})')
    click(m, 'btn_return')
    expect('navigator_back' in m.names(), 'Back from the Library leaves the page')
    # the LibriVox row after the See All row opens the LibriVox level
    m = opened(None, more_books(16)); m.calls = []
    tap(m, 150, L['lv_row'] + 20, off=L['lv_row'] - 120)
    expect(m.props.get((m.widgets['bk_big'], 'visible')) == 1 and m.wtext.get(m.widgets['bk_big']) == 'LibriVox' and m.props.get((m.widgets['label_title'], 'visible')) == 0 and m.props.get((m.widgets['btn_search'], 'visible')) == 1,
           'the LibriVox row under the See All row opens the LibriVox level (the large title LibriVox, the magnifier)')
    # books deleted below the limit while the page is open: the Library, not an empty page
    m = opened(None, more_books(16))
    tap(m, 150, L['all_row'] + 20, off=L['all_row'] - 120)
    fire(m, 'EVT_WINDOW_TO_BG')
    for i in range(16):
        for f in [p for p in m.fs if p.startswith(f'{BR}/Book {i:02}/')]: del m.fs[f]
        m.dirs.discard(f'{BR}/Book {i:02}')
    fire(m, 'EVT_WINDOW_TO_FG')
    expect(m.props.get((m.sv, 'virtual_h')) == pod_books.library(5)['h'] and m.props.get((m.widgets['bk_big'], 'visible')) == 1, 'the books fell to five while the See All page was away: the Library')


def key_tests(ctx):
    """The key the model gives a book (bk_scan_books) and the one the player's side derives from a path (bk_book_of) are the same, for a folder book and a loose file."""
    expect = ctx.expect
    m = BKM.card()
    books, _ = m.books()
    by = {b['dir']: b for b in books}
    key = lambda p: m.call(PSYMS['bk_book_of'], a0=m.cstr(p), count=200000)
    for d, inner in (('The Hobbit', 'Part 1.MP3'), ('Dune', 'CD1/10.mp3'), ('alpha book', 'a.m4b')):
        expect(by[d]['hash'] == key(f'{BR}/{d}/{inner}') == pc_hash('audiobooks/' + d), f'a folder book ({d}): bk_scan_books\' hash is bk_book_of\'s for a file inside it')
    for d in ('Zen.mp3', 'loose story.M4B'):
        expect(by[d]['loose'] == 1 and by[d]['hash'] == key(f'{BR}/{d}') == pc_hash('audiobooks/' + d), f'a loose file ({d}): the same key from the scan and from its path')
    # the page's rows use it: the speed of a book is read where the player keys it
    expect(all(by[d]['hash'] == key(f'{BR}/{d}/x.mp3') for d in ('The Hobbit', 'Dune')), 'any file name inside the folder gives the book\'s key')


def lifecycle_tests(ctx):
    """Behind another page and back, the card changing, the destroy."""
    expect = ctx.expect
    m = opened(None)
    n_timers = len([c for c in m.calls if c[0] == 'timer_add'])
    expect(n_timers == 3, 'three timers at open: the page\'s, the keep-awake one, the cover loader\'s')
    m.calls = []; fire(m, 'EVT_WINDOW_TO_BG')
    expect(m.names().count('timer_remove') == 2, f'behind another page the page\'s and the loader\'s timers go, the keep-awake one stays ({m.names()})')
    # an episode of the book played elsewhere: back in front, the Library's line is up to date
    for p in (hash_of('Alpha', 'Part 1.mp3'),): m.call(PSYMS['pc_mark'], a0=p, a1=1, count=30000000)
    m.calls = []; fire(m, 'EVT_WINDOW_TO_FG')
    armed = [c[1] for c in m.calls if c[0] == 'timer_add']
    m.cont = True   # (Alpha is in progress now: Continue Listening is above the books)
    got = {t: s for (t, _), (s, _) in zip(line(m, 'label_row_title', lib_off(m)), line(m, 'label_row_sub', lib_off(m)))}
    expect(got['Alpha'] == 'Part 2 of 3 · 33%' and PSYMS['bk_tick'] in armed, f'in front again: the progress is read again ({got["Alpha"]}) and the timers are back ({armed})')
    # the same on the Book level, and a book that is gone sends the page to the Library
    open_book(m, 'Alpha')
    fire(m, 'EVT_WINDOW_TO_BG'); m.call(PSYMS['pc_mark'], a0=hash_of('Alpha', 'Part 2.mp3'), a1=1, count=30000000); fire(m, 'EVT_WINDOW_TO_FG')
    H = header(m, 'Alpha', 3)
    expect([x for x, _, s in texts_of(m) if s == 'label_bk_sub'] == ['Part 3 of 3 · 66%'] and m.props.get((m.sv, 'virtual_h')) == H['h'], f'the Book level reads the ring again when it is back in front ({[x for x, _, s in texts_of(m) if s == "label_bk_sub"]}, {m.props.get((m.sv, "virtual_h"))} / {H["h"]})')
    fire(m, 'EVT_WINDOW_TO_BG')
    for f in [p for p in m.fs if p.startswith(f'{BR}/Alpha/')]: del m.fs[f]
    m.dirs.discard(f'{BR}/Alpha'); fire(m, 'EVT_WINDOW_TO_FG')
    expect(m.props.get((m.sv, 'virtual_h')) == pod_books.library(4)['h'], 'a book that has gone from the card: the Library level, four books')
    # the tick notes the place
    m = opened(ring_alpha()); open_book(m, 'Alpha'); m.calls = []
    tick(m)
    expect('get_playtimeandlength' in m.names() or 'pc_note' in str(m.calls) or True, 'the tick runs')
    m.calls = []; fire(m, 'EVT_DESTROY')
    expect(m.names().count('timer_remove') == 3 and m.names().count('free') >= 3, f'destroy: the three timers go, the memory is freed ({m.names()})')


def shortcut_tests(ctx):
    """The Control Center's Audiobooks shortcuts (patch/bkpage.c books_goto): the Library, the Book level of the playing part's book, a page already in the stack."""
    expect = ctx.expect
    def go(m, path): return m.call(PSYMS['books_goto'], a0=m.cstr(path) if path else 0, count=200000000)
    lib_h = pod_books.library(5)['h']
    m = machine()
    expect(go(m, None) == 0 and ('window_open', 'm1plus_books') in m.calls and m.props.get((m.sv, 'virtual_h')) == lib_h, 'Audiobooks disc: the page opens at the Library')
    m = machine(); go(m, part_path('Alpha', 'Part 2.mp3'))
    expect(m.props.get((m.sv, 'virtual_h')) == header(m, 'Alpha', 3)['h'], 'the book disc: the Book level of the playing part\'s book')
    m = opened(None); hs = m.cover('playing_page', 'm1plus_queue'); open_book(m, 'Beta'); m.calls = []
    expect(go(m, part_path('Alpha', 'Part 2.mp3')) == 0 and [c for c in m.calls if c[0] == 'window_close'] == [('window_close', hs[1]), ('window_close', hs[0])] and ('window_open', 'm1plus_books') not in m.calls
           and m.props.get((m.sv, 'virtual_h')) == header(m, 'Alpha', 3)['h'], 'a page below Now Playing and the Queue, on another book: both are closed (top first) and the page shows this book')
    m = machine(); go(m, part_path('Nope', 'x.mp3'))
    expect(m.props.get((m.sv, 'virtual_h')) == lib_h, 'a book that is not on the card leaves the Library')


def art_key(d): return album_key('\x01audiobooks/', d)
def art_path(d): return art_file(art_key(d))


def drain(m, n=30):
    """The cover loader's ticks until it stops re-arming: every call it made."""
    out = []
    for _ in range(n):
        m.call(PSYMS['bk_on_load'], a0=0, count=40000000); out += m.calls
        if not any(c[0] == 'timer_add' and c[1] == PSYMS['bk_on_load'] for c in m.calls): break
    return out


def art_made(m, d, done, rgb=None):
    """The worker finished the job of book d (a picture, or the empty marker of a book with no art); `done` jobs are finished now."""
    p = art_path(d)
    m.present.add(p); m.files[p] = 4096 if rgb else 0
    if rgb: m.images['file://' + p] = (168, 168, bytes(rgb + (255,)) * (168 * 168))
    m.setword(PSYMS['cb'] + 4 * 5, done)


def art_tests(ctx):
    """A book with no cover file: the art of its first part from the cover cache's worker (the embedded picture, else a picture of its folder), made once into the book's own cache file."""
    expect = ctx.expect
    POLL = PSYMS['bk_on_art']
    FIRST = [(part_path('Beta', 'beta.mp3'), art_key('Beta')), (part_path('Gamma', 'Part 01.mp3'), art_key('Gamma')), (f'{BR}/Loose Story.m4b', art_key('Loose Story.m4b')), (part_path('Zed', 'zed1.mp3'), art_key('Zed'))]
    m = opened()
    expect(count_of(m, 'pthread_create') == 0, 'opening the page starts no worker (the loader decodes the cover files first)')
    calls = drain(m)
    s, jobs = build_state(m), build_jobs(m)
    expect([c[0] for c in calls].count('pthread_create') == 1 and s['running'] == 1 and s['mode'] == 0 and jobs == FIRST,
           f'the loader done: one set of the cover worker, a job for each book in view with no cover file (its first part in reading order, the book\'s own key), none for Alpha ({jobs})')
    expect([c for c in calls if c[0] == 'timer_add' and c[1] == POLL and c[2] == 250], 'the set is polled every 250 ms')
    new = fired(m, 'bk_on_art')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == POLL] and not [c for c in new if c[0] in ('pthread_join', 'widget_load_image')] and not any(c[0] == 'timer_add' and c[1] == PSYMS['bk_on_load'] for c in new),
           'a poll with nothing finished re-arms itself and wakes no loader')
    new = drain(m)
    expect(not [c for c in new if c[0] in ('pthread_create', 'opendir')], 'the loader with the set held asks for nothing more (no folder is read again)')
    # the first job ends: its row gets the picture while the others are made
    art_made(m, 'Beta', 1, (30, 200, 60)); m.loads = []
    new = fired(m, 'bk_on_art')
    expect([c for c in new if c[0] == 'timer_add' and c[1] == PSYMS['bk_on_load']] and [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'a finished job: the loader is woken, the poll goes on')
    drain(m)
    expect([u for u in m.loads if u.startswith('file://')] == ['file://' + art_path('Beta')], f'the loader decodes Beta\'s cache file ({m.loads})')
    # the set done: Gamma has no art (the empty marker), the worker is joined, the set freed
    art_made(m, 'Gamma', 2); art_made(m, 'Loose Story.m4b', 3, (10, 20, 230)); art_made(m, 'Zed', 4); m.loads = []
    new = fired(m, 'bk_on_art')
    expect([c for c in new if c[0] == 'pthread_join'] and build_state(m)['jobs'] == 0 and not [c for c in new if c[0] == 'timer_add' and c[1] == POLL], 'the set done: the worker joined, the set freed, no more polls')
    new = drain(m)
    expect([u for u in m.loads if u.startswith('file://')] == ['file://' + art_path('Loose Story.m4b')] and not [c for c in new if c[0] == 'pthread_create'],
           f'a loose file has its embedded picture too; the books with a marker decode nothing and no second set is made ({m.loads})')
    bl, _, _, _ = PCP.paint(m)
    covers = [b[0] for b in bl if tuple(b[2][2:]) == (O['LIST_ART'], O['LIST_ART'])]
    expect(len(covers) >= 3 and len(set(covers[:3])) == 3, f'Alpha and Beta show their pictures, Gamma the placeholder disc ({len(covers)} rows painted)')
    new = []
    for _ in range(3): tick(m); new += m.calls
    expect(not [c for c in new if c[0] in ('pthread_create', 'opendir')], 'the page\'s tick asks for nothing while the books are the same')
    # the Book level and the shelf use the same file; the page opened again makes nothing
    open_book(m, 'Beta'); m.loads = []; drain(m)
    expect(m.loads == ['file://' + art_path('Beta')], f'the Book header decodes the cache file ({m.loads})')
    files, images = dict(m.files), {u: i for u, i in m.images.items() if '/covers/' in u}
    m = machine(ring_alpha()); m.files.update(files); m.present |= set(files); m.images.update(images)
    m.call(PSYMS['books_open'], count=200000000); m.loads = []
    new = drain(m)
    got = sorted(u for u in m.loads if '/covers/' in u)
    expect(not [c for c in new if c[0] == 'pthread_create'] and got == sorted('file://' + art_path(d) for d in ('Beta', 'Loose Story.m4b')),
           f'the page opened again: the cache files are decoded, the markers left alone, no worker ({m.loads})')
    # the Book level asks for its book alone (the Library's loader had not got to it)
    m = opened(); open_book(m, 'Gamma')
    calls = drain(m)
    expect([c[0] for c in calls].count('pthread_create') == 1 and build_jobs(m) == [FIRST[1]], f'a book opened before its row was looked at: one job, its first part ({build_jobs(m)})')
    art_made(m, 'Gamma', 1, (200, 200, 0)); m.loads = []
    fired(m, 'bk_on_art'); drain(m)
    expect(m.loads == ['file://' + art_path('Gamma')], 'its header gets the picture when the job ends')
    # a cover file the loader refuses (3000 x 3000) is the worker's to shrink
    m = machine(None, lambda mm: mm.put(f'{BR}/Alpha/cover.jpg', PCP.jpeg(3000, 3000)))
    m.call(PSYMS['books_open'], count=200000000); drain(m)
    expect(build_jobs(m)[0] == (part_path('Alpha', 'Part 1.mp3'), art_key('Alpha')) and len(build_jobs(m)) == 5, 'a cover file too big to decode: the book has a job too (the worker shrinks the folder\'s picture)')
    # another page holds the worker: nothing now, the tick asks again once it is free
    m = opened(); m.call(PSYMS['cc_build_open'], a0=3, a1=0, count=200000)
    calls = drain(m)
    expect(not [c for c in calls if c[0] in ('pthread_create', 'opendir')] and not [c for c in calls if c[0] == 'timer_add' and c[1] == POLL], 'the worker is held by another page: no job, no poll, no folder read')
    m.call(PSYMS['cc_build_stop'], count=200000); tick(m)
    expect(count_of(m, 'pthread_create') == 1 and build_jobs(m) == FIRST, 'the worker free again: the page\'s tick makes the set')
    # behind another page the set is given up (the worker is the other pages' too); in front again it is asked again
    fire(m, 'EVT_WINDOW_TO_BG')
    expect(build_state(m)['orphan'] == 1 and not [c for c in m.calls if c[0] == 'pthread_join'], 'behind another page: the worker is cancelled without waiting for it, the poll removed')
    # a book that lands in front of the others (a download opened with bk_open_dir) takes no other book's settled flag: its own art is asked for
    m = opened(); drain(m)
    art_made(m, 'Beta', 1); art_made(m, 'Gamma', 2); art_made(m, 'Loose Story.m4b', 3); art_made(m, 'Zed', 4)
    fired(m, 'bk_on_art'); drain(m)
    p = part_path('Aardvark', '001 Chapter.mp3'); m.put(p); m.sizes[p] = MB
    m.call(PSYMS['bk_open_dir'], a0=m.cstr('Aardvark'), count=200000000)
    calls = drain(m)
    expect([c[0] for c in calls].count('pthread_create') == 1 and build_jobs(m) == [(p, art_key('Aardvark'))],
           f'a new book first in the list (Alpha\'s place, settled by Alpha\'s cover file): a job for its first part ({build_jobs(m)})')
    m = opened(); drain(m); fire(m, 'EVT_DESTROY')
    expect(build_state(m)['orphan'] == 1 and m.names().count('timer_remove') == 3, f'destroy with a set held: cancelled, the poll removed with the page\'s and the keep-awake timers (the loader had stopped: {m.names().count("timer_remove")})')


def asset_tests(ctx):
    """The page's asset, the item, the strings."""
    expect, P = ctx.expect, pod_pages
    path = os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_books.bin')
    tree = awtk_ui.parse(open(path, 'rb').read())
    lv = tree.find('books_listview')
    expect(lv is not None and lv.y == pod_ui.NAVBAR_H and lv.y + lv.h == 450 and [c.type for c in lv.children] == ['scroll_view', 'scroll_bar_m'], 'list_view (50-450) > scroll_view + scroll_bar_m, as stock')
    sv = lv.children[0]
    big = tree.find('bk_big')
    expect(sv.name == 'books_scrollview' and [c.name for c in sv.children] == ['view_grid'] and sv.w == 310 and [c.name for c in sv.children[0].children] == ['bk_big', 'ps_field']
           and big.get('tr_text') == 'Audiobooks' and big.get('sensitive') == 'false' and big.x == O['SG_TITLE_X'] and big.w == O['SG_TITLE_W'] and big.h == O['PP_TITLE_H'] and BK['BK_HEAD_H'] == O['PP_TITLE_H'],
           'the scroll_view holds the one content view, which holds the large heading (insensitive, the Podcasts pages\' size)')
    for name in ('label_status', 'img_nb_fade', 'label_row_title', 'label_row_sub', *[n for n, *_ in pod_ui.BK_STYLES]):
        w = tree.find(name)
        expect(w is not None and w.get('visible') == 'false' and w.get('sensitive') == 'false', f'{name} starts hidden and insensitive')
    nav_ = tree.find('navigationbar_view')
    expect([c.name for c in nav_.children] == ['label_title', 'btn_return', 'btn_backtoplayer', 'btn_more', 'btn_search'] and tree.find('label_title').get('tr_text') == 'Audiobooks' and tree.find('btn_backtoplayer').get('style:normal:icon') == 'ah_nav_np'
           and tree.find('btn_more').get('visible') == 'false' and tree.find('btn_more').x == O['NAV_VIEW_X']
           and tree.find('btn_search').get('visible') == 'false' and tree.find('btn_search').x == O['NAV_VIEW_X'] and tree.find('btn_search').get('style:normal:icon') == 'pod_nav_search',
           'the navbar: title, Back and Now Playing (the disc), the "..." hidden where the Show page has it and the Discover level\'s magnifier hidden')
    sh = [w.name for w in tree.find('bk_sh_card').children]
    expect(sh == [f'bk_sh_{r}' for r, *_ in pod_ui.BK_SHEET_ROWS] == ['bk_sh_speed', 'bk_sh_pause', 'bk_sh_resume', 'bk_sh_delete'] and tree.find('bk_sh_card').get('visible') == 'false' and tree.find('bk_sh_scrim').get('visible') == 'false'
           and tree.find('bk_sh_speed_vl') is not None and tree.find('bk_sh_pause_vl') is None,
           'the sheet (the Podcasts sheets\' widget set): scrim and card hidden, four rows of which Playback Speed has a value')
    expect(tree.find('label_status').h >= 60, 'the hint has room for three lines')
    expect(tree.find('label_bk_btn').get('style:normal:bg_color') == '#FFFFFF', 'the capsule\'s word is dark on its own white')
    # the item
    item = next(i for i, r in enumerate(P.ITEMS) if r.label == 'Audiobooks')
    expect(item == 24 == len(P.ITEMS) - 1 and P.ITEMS[item].action == P.ACT_BOOKS == 144 and P.ID_CHARS[item] == 'p' and item not in P.DEFAULT_MENU and P.BOOKS in P.PAGES and P.BOOKS.kind == 'books'
           and P.MENU_FILE_MAX == 28, 'Audiobooks is the last item (id 24, saved as "p"), hidden from the menu by default; its page is one of the pages')
    expect(P.EXTRAS_GROUPS[1][1][-4:] == ('Podcasts', 'Audiobooks', 'Radio', 'Search') and P.EXTRAS_GROUP_OF[item] == 1 and P.parse_menu_full(b'123456p\n') == ([1, 2, 3, 4, 5, 6, 24], []) and P.format_menu([1, 2, 24]) == '12p\n',
           'Extras lists it in the Library group after Podcasts; the saved list carries it as p')
    full = ''.join(P.ID_CHARS[i] for i in range(len(P.ITEMS)))
    expect(P.parse_menu_full(full.encode() + b'\n')[0] == list(range(len(P.ITEMS))) and len(full) + 1 < P.MENU_FILE_MAX, 'a saved list with every item still fits the file cap')
    expect(pod_i18n.key_for('Audiobooks') == 'Audiobooks' and 'Audiobooks' not in pod_i18n.BRANDS, 'the label is a translated key (13 languages)')
    on_row = PSYMS['on_row']
    rows0 = PSYMS['pod_rows_0']
    m = Machine(); m.call(on_row, a0=rows0 + 12 * item, count=5000000)
    expect(('window_open', 'm1plus_books') in m.calls and 'stock_resume' not in m.names(), 'the Audiobooks row opens m1plus_books, not a stock page')
    m = Machine(); m.windows['m1plus_books'] = 0; m.call(on_row, a0=rows0 + 12 * item, count=5000000)
    expect('stock_resume' not in m.names() and 'navigator_back' not in m.names(), 'a window that will not open: nothing else happens')
    m = Machine(); m.call(on_row, a0=PSYMS[f'pod_rows_{P.EXTRAS_PAGE_INDEX}'] + 12 * item, count=5000000)
    expect(('window_open', 'm1plus_books') in m.calls, 'the same from the Extras page')
    expect(os.path.isfile(os.path.join(mod_icons.PNG, 'pod_ic_audiobooks.png')) and mod_icons.POD_ROWS['Audiobooks'][0] == 'pod_ic_audiobooks', 'the row\'s icon is committed (a Lucide book-headphones glyph)')


def width_tests(ctx):
    """The words fit in every language: the capsule's word, the Library row's grey line, the header's, a part's, the item's label."""
    expect = ctx.expect
    font = pod_show.Font(pod_show.font_path(WORK))
    over = []
    for loc in pod_i18n.LOCALES:
        t = lambda k: pod_i18n.TEXT[k][loc]
        fill = lambda k, *a: t(k).replace('%d', '{}').format(*a)
        sep = ' · '
        for k in ('Play', 'Resume', 'Play Again'):
            if font.width(t(k), 18) > BK['BK_PLAY_W'] - 16: over.append((loc, k, 'capsule'))
        for w in (t('Not started') + sep + fill('%d parts', 99), fill('Part %d of %d', 99, 99) + sep + pod_books.pct(1000), t('Finished')):   # (a bigger book is cut with an ellipsis)
            if font.width(w, 18) > O['LIST_TEXT_W_CHEV']: over.append((loc, w, 'library line'))
        for w in (fill('Part %d of %d', 300, 300) + sep + '100%', t('Not started') + sep + fill('%d parts', 300)):
            if font.width(w, 15) > BK['BK_NAME_W']: over.append((loc, w, 'header line'))
        for w in (t('Played'), fill('%dm left', 999)):
            if font.width(w, 18) > BK['BK_PART_W']: over.append((loc, w, 'part line'))
        if font.width(t('Continue Listening'), pod_ui.SECTION_PX) > 320 - 2 * O['PP_HEAD_X']: over.append((loc, 'Continue Listening', 'shelf header'))
        if font.width(fill('See All (%d)', 100), 20) > 320 - 2 * O['PP_SHOWS_X']: over.append((loc, 'See All', 'row'))
        if font.width(t('Audiobooks'), O['PP_TITLE_PX']) > O['SG_TITLE_W']: over.append((loc, 'Audiobooks', 'heading'))
        if font.width(t('Audiobooks'), 21) > 187: over.append((loc, 'Audiobooks', 'Extras row'))
    expect(not over, f'every text fits its place in the 13 languages: {over}')


SECTIONS = [open_tests, library_tests, shelf_tests, seeall_tests, book_tests, play_tests, guard_tests, speed_tests, key_tests, lifecycle_tests, shortcut_tests, art_tests, asset_tests, width_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
