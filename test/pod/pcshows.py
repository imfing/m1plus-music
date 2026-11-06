"""The Podcasts Shows page (round 2 of the revamp; patch/podcasts.c with patch/pcnet.c and patch/pcmodel.c, docs/modules/podcasts.md "The Shows page"): the large title that collapses into the navbar, the
refresh line in every state and its tap (the guards, the progress dialog, the downloads that pause), Continue Listening (hidden, one to three items, the order, the tap that resumes), the
Downloads row and its level, the grid of every show (captions in each case, no badge, the order, a tap that opens the Show page, a subscription with nothing downloaded), the "..." sheet (Import from
Card only while subscriptions.txt exists, no Add Show; the "..." hidden when the sheet would be empty), the empty library, the Feeds level gone, every layout number against the shared model
(tools/pod_show.py shows_layout), the strings' widths in the 13 languages and the screen-off rule. The compiled payload runs under Unicorn; the card is a dict of paths."""
import importlib.util, os, sys
from harness import *   # noqa: F401,F403  (test/patch.py initialises the harness before loading a module)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'tools'))
FEEDS = os.path.join(ROOT, 'test', 'data', 'feeds')


def sibling(name):
    mod = sys.modules.get(f'podtest_{name}')
    if mod is None:
        spec = importlib.util.spec_from_file_location(f'podtest_{name}', os.path.join(HERE, name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f'podtest_{name}'] = mod
        spec.loader.exec_module(mod)
    return mod


PCP, PCN = sibling('podcasts'), sibling('pcnet')
import mod_icons, pod_i18n, pod_show, pod_ui   # noqa: E402

PN, CA = PCN.PN, PCN.CA
RP, ROW = PCP.ROOT, PCP.ROW
NOW = 1800000000
F = {k: f'https://f.example/{k}' for k in ('alpha', 'one', 'two', 'three')}
DAY = 86400
GC, GT, GS = O['GRID_COVER'], O['GRID_TITLE_H'], O['GRID_SUB_H']


def sw(): return sibling('pcshow')   # (loaded when needed: it loads pcdl, which loads this module)


def hash_of(s): return PCP.pc_hash(s)


def fn(m, name, **kw): return m.call(PSYMS[name], count=2000000, **kw)


def card(m):
    """Alpha Show (two files, a feed, refreshed an hour ago), bravo (files, no feed), Sub One (a feed, never refreshed, two episodes not downloaded), Sub Two (a feed, refreshed 2 days ago).
    The newest episodes: Sub One now less 5000 s, bravo and Alpha Show in 2023, Sub Two none: the grid reads Sub One, bravo, Alpha Show, Sub Two."""
    PCP.page_card(m)
    m.put(f'{RP}/Alpha Show/.show', f'M1PLUS-SHOW 1\ntitle=Alpha Show\nfeed={F["alpha"]}\nimage=\nchecked={NOW - 3600}\n'.encode())
    m.put(f'{RP}/Sub One/.show', f'M1PLUS-SHOW 1\ntitle=Sub One\nfeed={F["one"]}\nimage=\nchecked=0\n'.encode())
    m.put(f'{RP}/Sub One/.episodes', (PCP.EPS_HEAD + f'g=s1\tp={NOW - 5000}\td=600\tl=1000\tf=a.mp3\tt=Remote A\tu=https://e/a.mp3\ng=s2\tp={NOW - 9000}\td=1200\tf=b.mp3\tt=Remote B\tu=https://e/b.mp3\n').encode())
    m.put(f'{RP}/Sub Two/.show', f'M1PLUS-SHOW 1\ntitle=Sub Two\nfeed={F["two"]}\nimage=\nchecked={NOW - 2 * DAY}\n'.encode())
    m.present.add(CA)
    m.wall = NOW


ORDER = ['Sub One', 'bravo', 'Alpha Show', 'Sub Two']


def style_px(m):
    m.px = {m.widgets[n]: px for n, px, *_ in pod_ui.PS_STYLES}
    m.px.update({m.widgets[n]: px for n, px in (('label_row_title', 21), ('label_row_sub', 18))})
    m.px.update({m.widgets['pg_sh_speed_vl']: pod_ui.PS_SHEET_PX, m.widgets['pg_sh_refresh_vl']: pod_ui.PS_SHEET_PX})


def machine(extra=None, cardf=card):
    """The page machine with the real font's widths for the style labels, not opened."""
    m = PCP.page_machine(lambda mm: (cardf(mm), extra(mm) if extra else None), sw().SM)
    style_px(m)
    m.images['p_default'] = (16, 16, bytes((90, 90, 90, 255)) * 256)
    m.load_image = 0
    m.curl_site = lambda url, o: {'rc': 6}
    m.wifi = 4
    return m


def opened(extra=None, cardf=card):
    m = machine(extra, cardf)
    assert m.call(PSYMS['podcasts_open'], count=40000000) == 0
    return m


def pn_set(m, **kw):
    """Poke the worker's status record (patch/pcnet.c): busy, done, total, gen, cur and statuses=[(feed hash, code, fresh)]."""
    base = PSYMS['pn']
    for k, off in (('busy', 0), ('done', 4), ('total', 8), ('gen', 12), ('cur', 16)):
        if k in kw: m.setword(base + off, kw[k])
    for i, (feed, code, fresh) in enumerate(kw.get('statuses', [])):
        m.setword(base + 20 + 12 * i, feed); m.setword(base + 24 + 12 * i, fresh); m.setword(base + 28 + 12 * i, code)


def tick(m):
    m.screen(True)
    return m.call(PSYMS['pg_tick'], a0=0, count=40000000)


def flags(m, name):
    return m.props.get((m.widgets[name], 'visible'), 1), m.props.get((m.widgets[name], 'sensitive'), 1)


def toasts(m): return [c[1] for c in m.calls if c[0] == 'toast']


def refg(m):
    """The page goes behind another and comes back (the events the window gets): the Shows level is read again."""
    for ev in ('EVT_WINDOW_TO_BG', 'EVT_WINDOW_TO_FG'):
        fn_, ctx_ = m.bound[(m.window, O[ev])]
        m.call(fn_, a0=ctx_, a1=0, count=40000000)


def progress(m, path, pos, length=3000):
    """An episode the player has played to pos (the page's timer notes its place: the ring now has it first)."""
    rec = m.track(path); m.pt = (pos, length, 1); m.status = 2; m.clock += 40000
    m.note(rec)


EP = lambda show, f: f'{RP}/{show}/{f}'


def grid(m):
    """[(title, caption)] of the grid's cells in order, read from frames scrolled 100 px apart (a text is drawn only wholly in view)."""
    cells = {}
    for off in range(0, max(m.props.get((m.sv, 'virtual_h'), 0) - 300, 100), 100):
        _, texts, styles, _ = PCP.paint(m, off)
        for (t, r), s in zip(texts, styles):
            if s == 'label_ps_gtitle': cells.setdefault((r[0], r[1] + off), [None, None])[0] = t
            elif s == 'label_ps_gsub': cells.setdefault((r[0], r[1] + off - GT), [None, None])[1] = t
    return [tuple(v) for _, v in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0]))]


def fixed(s):
    try: return s.encode('latin-1').decode('utf-8') if s else s
    except (UnicodeDecodeError, UnicodeEncodeError): return s


def texts_of(m, style, off=0):
    return [(t, r) for (t, r), s in zip(*PCP.paint(m, off)[1:3]) if s == style]


def lay(m, n=4, line=True, cont=0): return pod_show.shows_layout(n, line, cont)


def sources():
    return {f: open(os.path.join(ROOT, 'patch', f), encoding='utf-8').read() for f in sorted(os.listdir(os.path.join(ROOT, 'patch'))) if f.endswith(('.c', '.h'))}


def layout_tests(ctx):
    """Every number of the page against the shared model: the content's height in each configuration, the refresh line, the Library rows, the grid, Continue Listening and the headers."""
    expect = ctx.expect
    o = O
    m = opened()
    L = lay(m)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and ('widget_resize', m.view, 320, L['h']) in m.calls and L['y_shelf'] == 0, f'four shows, a feed, nothing partly played: no Continue Listening, the content is {L["h"]} px')
    gridend = L['y_grid'] + 2 * pod_show.grid_pitch()
    expect(L['y_shows'] == o['PP_LINE_Y'] + o['PP_LINE_PITCH'] and L['y_grid'] == L['y_shows'] + o['PP_HEAD_PITCH'] and L['y_dl'] == gridend + o['PP_LIB_GAP'] and L['y_sub'] == L['y_dl'] + o['PC_ROW_H'] and L['y_sav'] == L['y_sub'] + o['PC_ROW_H'] and L['h'] == L['y_sav'] + o['PC_ROW_H'] + o['PP_BOTTOM'],
           'the Shows header PP_LINE_PITCH under the line, the grid, then PP_LIB_GAP (24) of air and the Library rows (Downloads, Subscriptions, Saved) as the last section')
    L0 = lay(m, line=False)
    expect(L0['y_shows'] == o['PP_LINE_Y'] + o['PP_NOLINE_PITCH'] and L0['y_sub'] == 0 and L0['y_dl'] == L0['y_grid'] + 2 * pod_show.grid_pitch() + o['PP_LIB_GAP'] and L0['y_sav'] == L0['y_dl'] + o['PC_ROW_H'] and L0['h'] == L0['y_sav'] + o['PC_ROW_H'] + o['PP_BOTTOM'],
           'with no feed there is no refresh line and no Subscriptions row: the Shows header PP_NOLINE_PITCH under the title, the Downloads row and Saved at the end')
    Le = lay(m, n=0)
    expect(Le['y_dl'] == Le['y_grid'] and Le['y_sub'] == Le['y_dl'] + o['PC_ROW_H'], 'no show: no gap, the rows follow the top block')
    # the refresh line: "Updated 1h ago · " in the grey 15 px style, the white word right after it
    grey = texts_of(m, 'label_ps_meta')
    white = texts_of(m, 'label_ps_line')
    gw = sw().font().width('Updated 1h ago · ', 15)
    expect(len(grey) == 1 and grey[0][0] == 'Updated 1h ago · ' and grey[0][1][:2] == (o['PP_LINE_X'], o['PP_LINE_Y']) and grey[0][1][3] == o['PP_LINE_H']
           and white[0][0] == 'Refresh' and white[0][1][0] == o['PP_LINE_X'] + gw and white[0][1][1] == o['PP_LINE_Y'], f'the refresh line: grey "Updated 1h ago · " at (16, 52), the white "Refresh" after it ({grey}, {white})')
    # the Library rows: the atlas' tiles, the chevrons, the titles and grey lines, the hairlines
    LO = max(0, L['h'] - 400)   # (the Library rows close the page: the frame scrolled to the bottom)
    bl, texts, styles, fills = PCP.paint(m, LO)
    tiles = sorted(tuple(b[2]) + (tuple(b[1][:2]),) for b in bl if tuple(b[1]) == (0, 0, o['PA_TILE_PX'], o['PA_TILE_PX']))
    chev = sorted(tuple(b[2]) for b in bl if tuple(b[1]) == (0, 0, 10, 16))   # the shared chevron bitmap
    expect(tiles == [(o['PP_DL_TILE_X'], L['y_dl'] - LO + o['PP_DL_TILE_Y'], 44, 44, (0, 0)), (o['PP_DL_TILE_X'], L['y_sub'] - LO + o['PP_DL_TILE_Y'], 44, 44, (0, 0)), (o['PP_DL_TILE_X'], L['y_sav'] - LO + o['PP_DL_TILE_Y'], 44, 44, (0, 0))]
           and chev == [(o['PP_DL_CHEV_X'], L[k] - LO + (o['PC_ROW_H'] - 1 - 16) // 2, 10, 16) for k in ('y_dl', 'y_sub', 'y_sav')] and o['PP_DL_CHEV_X'] == o['LIST_CHEV_X'] and o['PP_DL_TEXT_X'] + o['PP_DL_TEXT_W'] == o['LIST_CHEV_X'] - 10,
           f'three Library rows: the download, podcast and bookmark tiles (images of their own) at x 16, a chevron each ({tiles}, {chev})')
    rows = [(t, s, r) for (t, r), s in zip(texts, styles) if s in ('label_row_title', 'label_row_sub')]
    want = [('Downloads', 'label_row_title', (o['PP_DL_TEXT_X'], L['y_dl'] - LO + o['LIST_TITLE_Y'], o['PP_DL_TEXT_W'], o['LIST_TITLE_H'])), ('5 episodes', 'label_row_sub', (o['PP_DL_TEXT_X'], L['y_dl'] - LO + o['LIST_SUB_Y'], o['PP_DL_TEXT_W'], o['LIST_SUB_H'])),
            ('Subscriptions', 'label_row_title', (o['PP_DL_TEXT_X'], L['y_sub'] - LO + o['LIST_TITLE_Y'], o['PP_DL_TEXT_W'], o['LIST_TITLE_H'])), ('3 shows', 'label_row_sub', (o['PP_DL_TEXT_X'], L['y_sub'] - LO + o['LIST_SUB_Y'], o['PP_DL_TEXT_W'], o['LIST_SUB_H'])),
            ('Saved', 'label_row_title', (o['PP_DL_TEXT_X'], L['y_sav'] - LO + o['LIST_TITLE_Y'], o['PP_DL_TEXT_W'], o['LIST_TITLE_H'])), ('No saved episodes', 'label_row_sub', (o['PP_DL_TEXT_X'], L['y_sav'] - LO + o['LIST_SUB_Y'], o['PP_DL_TEXT_W'], o['LIST_SUB_H']))]
    expect(sorted(rows) == sorted(want), f'their titles (21 px) and grey lines (18 px) from x 72 ({rows})')
    expect(all((o['LIST_HAIR'], o['PP_DL_TEXT_X'], L[k] - LO + o['PC_ROW_H'] - 1, 320 - o['PP_DL_TEXT_X'], 1) in fills for k in ('y_dl', 'y_sub', 'y_sav')), 'a hairline under each from its text')
    # the grid: cover, title and grey line of each cell where the model puts them
    got = grid(m)
    expect([t for t, _ in got] == ORDER, f'the grid lists every show, most recently updated first ({got})')
    bl, texts, styles, _ = PCP.paint(m, 300)
    covers = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (GC, GC)]
    expect(covers == [(x, y - 300, GC, GC) for x, y, _, _ in (pod_show.grid_cell(i, L['y_grid']) for i in range(4)) if 0 <= y - 300 and y - 300 + GC <= 400] and len(covers) == 2,
           f'a {GC} px cover at each cell\'s place ({covers})')
    cells = [pod_show.grid_cell(i, L['y_grid']) for i in range(4)]
    boxes = {t: r for (t, r), s in zip(texts, styles) if s == 'label_ps_gtitle'}
    expect(boxes == {t: (x, ty - 300, GC, GT) for t, (x, y, ty, sy) in zip(ORDER, cells) if 0 <= ty - 300 and ty - 300 + GT <= 400}, f'the titles in boxes of {GC} x {GT} under the covers ({boxes})')
    subs = {t: r for (t, r), s in zip(texts, styles) if s == 'label_ps_gsub'}
    expect(all(r[2:] == (GC, GS) for r in subs.values()) and sorted(r[:2] for r in subs.values()) == sorted((x, sy - 300) for x, y, ty, sy in cells if 0 <= sy - 300 and sy - 300 + GS <= 400), f'the grey lines in boxes of {GC} x {GS} under the titles ({subs})')
    # the large title (a widget of the content) and the grid's x: the Albums grid's margins
    expect([c[0] for c in cells] == [o['GRID_MARGIN'], o['GRID_MARGIN'] + GC + o['GRID_GAP']] * 2, 'two columns of 144 px covers, the Albums grid\'s margins and gap')
    # Continue Listening, a download running and every header together
    def full(extra=None):
        mm = opened(extra)
        progress(mm, EP('Alpha Show', 'ep1.mp3'), 600); progress(mm, EP('bravo', 'b2.mp3'), 300); progress(mm, EP('bravo', 'b1.mp3'), 100, 1200)
        DL = sibling('pcdl')
        DL.poke_slot(mm, 0, 'Sub One', 'a.mp3', 2, seq=1)
        mm.setword(DL.pn_at(DL.DKEY), DL.key_of('Sub One', 'a.mp3')); mm.setword(DL.pn_at(DL.DGOT), 420000); mm.setword(DL.pn_at(DL.DTOTAL), 1000000)
        mm.setword(DL.pn_at(DL.KIND), 2); mm.setword(DL.pn_at(0), 1); mm.setword(DL.pn_at(DL.DSEQ), 10)
        refg(mm)
        return mm
    m = full()
    L3 = lay(m, cont=3)
    expect(m.props.get((m.sv, 'virtual_h')) == L3['h'] and L3['y_shelf'] == o['PP_LINE_Y'] + o['PP_LINE_PITCH'] and L3['y_shows'] == L3['y_shelf'] + o['PP_HEAD_PITCH'] + o['PP_SHELF_PITCH_Y'] + o['PP_SEC_GAP']
           and L3['y_grid'] == L3['y_shows'] + o['PP_HEAD_PITCH'], f'with three items: the blocks stack as the model says ({L3})')
    bl, texts, styles, fills = PCP.paint(m, 0)
    heads = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_ps_sech']
    expect(heads[:1] == [('Continue Listening', (o['PP_HEAD_X'], L3['y_shelf'], 320 - 2 * o['PP_HEAD_X'], o['PP_HEAD_H']))], f'the Continue Listening header, 20 px white ({heads})')
    heads = [(t, r) for (t, r), s in zip(*PCP.paint(m, 100)[1:3]) if s == 'label_ps_sech']
    expect(('Shows', (o['PP_SHOWS_X'], L3['y_shows'] - 100, 320 - 2 * o['PP_SHOWS_X'], o['PP_HEAD_H'])) in heads, f'the Shows header, scrolled into view ({heads})')
    sc = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (o['PP_SHELF_ART'], o['PP_SHELF_ART'])]
    expect(sc == [(pod_show.shelf_item(i, L3['y_shelf'])[0], pod_show.shelf_item(i, L3['y_shelf'])[1], 92, 92) for i in range(3)], f'three 92 px covers at x 14, 114, 214 ({sc})')
    st = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_ps_stitle']
    sl = [(t, r) for (t, r), s in zip(texts, styles) if s == 'label_ps_sleft']
    expect([r for _, r in st] == [(pod_show.shelf_item(i, L3['y_shelf'])[0], pod_show.shelf_item(i, L3['y_shelf'])[2], o['PP_SHELF_W'], o['PP_SHELF_TITLE_H']) for i in range(3)]
           and [r for _, r in sl] == [(pod_show.shelf_item(i, L3['y_shelf'])[0], pod_show.shelf_item(i, L3['y_shelf'])[3], o['PP_SHELF_W'], o['PP_SHELF_LEFT_H']) for i in range(3)], 'each item\'s title (14 px) and what is left (13 px grey) under its cover')
    LO3 = L3['h'] - 400
    dt = {s: (t, r) for (t, r), s in zip(*PCP.paint(m, LO3)[1:3]) if s in ('label_row_title', 'label_row_sub') and r[1] < L3['y_sub'] - LO3}
    expect(dt['label_row_title'] == ('Downloads', (o['PP_DL_TEXT_X'], L3['y_dl'] - LO3 + o['LIST_TITLE_Y'], o['PP_DL_TEXT_W'], o['LIST_TITLE_H']))
           and dt['label_row_sub'] == ('Downloading 42%', (o['PP_DL_TEXT_X'], L3['y_dl'] - LO3 + o['LIST_SUB_Y'], o['PP_DL_TEXT_W'], o['LIST_SUB_H'])), f'the Downloads row: its title and the running download\'s line ({dt})')
    # the three tiles are images of their own, the atlas holds the chevron where the offsets say
    from PIL import Image
    a = Image.open(os.path.join(mod_icons.PNG, 'pc_atlas.png')).convert('RGBA')
    tl = {n: Image.open(os.path.join(mod_icons.PNG, n + '.png')).convert('RGBA') for n in ('pod_ic_dltile', 'pod_ic_subtile', 'pod_ic_savetile')}
    expect((mod_icons.PA_TILE_PX, mod_icons.PA_CHEV) == (o['PA_TILE_PX'], o['PA_CHEV']) and 'PA_TILE_X' not in o and all(t.size == (44, 44) for t in tl.values())
           and all(t.getpixel((22, 4)) == (0x1e, 0x1e, 0x1e, 255) and t.getpixel((0, 0))[3] == 0 and any(p[:3] != (0x1e, 0x1e, 0x1e) and p[3] == 255 for p in t.crop((8, 8, 36, 36)).getdata()) for t in tl.values())
           and len({t.tobytes() for t in tl.values()}) == 3 and a.getpixel((22, 112 + 22))[3] == 0
           and a.crop((o['PA_CHEV'] * 16, o['PA_G_Y'], o['PA_CHEV'] * 16 + 16, o['PA_G_Y'] + 16)).getbbox() is not None, 'pod_ic_dltile, pod_ic_subtile and pod_ic_savetile are the #1E1E1E rounded square (clear corners) with a glyph each; the atlas no longer holds a tile and has the grey chevron at the number of offsets.inc')
    expect(not os.path.exists(os.path.join(mod_icons.PNG, 'pod_nav_feeds.png')) and os.path.isfile(os.path.join(mod_icons.PNG, 'pc_ic_import.png')) and not os.path.exists(os.path.join(mod_icons.PNG, 'pod_ic_subs.png')), 'the sheet\'s Import glyph is committed; the Feeds button\'s and the old Subscriptions row\'s are gone')
    # n shows
    for n in (1, 2, 3, 5, 9):
        mm = opened(lambda x, n=n: [x.put(f'{RP}/Extra {i}/e.mp3', b'', 10 + i) for i in range(n)], lambda x: PCP.page_card(x))
        expect(mm.props.get((mm.sv, 'virtual_h')) == lay(mm, n + 2, False)['h'], f'{n + 2} shows, no feed: the content is {lay(mm, n + 2, False)["h"]} px')


def title_tests(ctx):
    """The Shows, Downloads and Subscriptions levels have a large heading at the top of their content (x SG_TITLE_X, SG_TITLE_W wide); once it has scrolled away (SG_COLLAPSE) the navbar's small title shows, cut before the leftmost button; the search level has no title; select mode keeps "N Selected"."""
    expect = ctx.expect
    m = opened()
    t, big, fade = m.widgets['label_title'], m.widgets['pg_big'], m.widgets['img_nb_fade']
    resized = lambda mm: [c[2] for c in mm.calls if c[0] == 'widget_resize' and c[1] == mm.widgets['label_title']]
    expect(m.props.get((t, 'visible')) == 0 and m.props.get((big, 'visible'), 1) == 1 and m.props.get((fade, 'visible'), 0) == 0 and PCP.title_text(m) == 'Podcasts' and m.wtext.get(t) == 'Podcasts' and resized(m)[-1:] == [O['NAV_VIEW_X'] + O['NAV_VIEW_W'] - O['NAV_TITLE_X']],
           f'at rest: the large Podcasts heading is there, the navbar\'s title (the same words) is hidden and ends at Now Playing (no "..." here), no fade ({PCP.title_text(m)} {resized(m)} {m.props.get((t, "visible"))})')
    fn_, ctx_ = m.bound[(m.sv, O['EVT_SCROLL'])]
    def scroll(off):
        m.props[(m.sv, 'yoffset')] = off; m.setword(m.sv + PCP.SC_YOFF, off)
        m.call(fn_, a0=ctx_, a1=0, count=4000000)
    # (the content is only so high: the scroll offsets are what the scroll view would give)
    for off, on in ((O['SG_COLLAPSE'] - 1, 0), (O['SG_COLLAPSE'], 1), (O['SG_COLLAPSE'] + 1, 1), (200, 1)):
        scroll(off)
        expect(m.props.get((t, 'visible')) == on and m.props.get((big, 'visible'), 1) == 1 and m.props.get((fade, 'visible')) == 1, f'at offset {off}: the heading scrolls with the content, the navbar\'s small title is {"shown" if on else "hidden"} (the fade is on for the rows under the bar)')
    scroll(0)
    expect(m.props.get((t, 'visible')) == 0 and m.props.get((fade, 'visible')) == 0, 'scrolled back: the small title and the fade off')
    scroll(300)
    x, y, _ = PCP.show_at(m, 'bravo')
    PCP.tap(m, x, y, off=300)
    expect(PCP.title_text(m) == 'bravo' and m.props.get((big, 'visible'), 1) == 0 and m.props.get((fade, 'visible')) == 0, 'a Show page: its own title, the large heading hidden')
    PCP.click(m, 'btn_return')
    expect(m.props.get((big, 'visible'), 1) == 1 and m.props.get((m.sv, 'yoffset')) == 300 and m.props.get((t, 'visible')) == 1 and m.wtext.get(t) == 'Podcasts', 'Back: the Shows level where it was (300), the navbar\'s small title shows')
    # the Downloads level: its heading, whatever the offset
    m = opened()
    DL = sibling('pcdl')
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 1, seq=1); m.setword(DL.pn_at(12), 5); tick(m)
    PCP.tap_downloads(m)
    expect(PCP.title_text(m) == 'Downloads' and m.props.get((m.widgets['label_title'], 'visible')) == 0 and m.props.get((m.widgets['pg_big'], 'visible'), 1) == 1 and m.wtext.get(m.widgets['label_title']) == 'Downloads' and resized(m)[-1:] == [O['NAV_VIEW_X'] - O['NAV_TITLE_X']],
           'the Downloads level: the large Downloads heading at rest, the small title (the same words, ending at the "...") hidden')
    scroll(O['SG_COLLAPSE'] + 1)
    expect(m.props.get((m.widgets['label_title'], 'visible')) == 1 and m.props.get((m.widgets['pg_big'], 'visible'), 1) == 1, 'past SG_COLLAPSE the Downloads page\'s small title shows')
    scroll(0)
    # every level in turn, the capsule's four pieces on the Shows level: the heading is the large widget at (SG_TITLE_X, 0), the navbar's title is hidden at rest, nothing is moved or resized on the heading
    m = opened(lambda x: x.put('/mnt/mmc/podcasts.opml', b'<opml><body><outline xmlUrl="https://n.example/rss" text="N"/></body></opml>'))
    big, nav = m.widgets['pg_big'], m.widgets['label_title']
    def level(name, heading):
        shown = m.props.get((big, 'visible'), 1) == 1 and m.props.get((nav, 'visible'), 0) == 0
        expect(not [c for c in m.calls if c[0] in ('widget_move', 'widget_resize') and c[1] == big] and shown == (heading is not None) and (heading is None or PCP.title_text(m) == heading),
               f'{name}: heading {heading!r} in the large label, the navbar title hidden at rest ({PCP.title_text(m)})')
    level('Shows', 'Podcasts')
    expect(flags(m, 'btn_more') == (1, 1) and flags(m, 'btn_globe') == (0, 0), 'the Shows level has the "..." capsule piece (and no globe: Podcast Search is off)')
    PCP.tap_downloads(m); level('Downloads', 'Downloads')
    PCP.click(m, 'btn_return')
    tap_row(m, "Subscriptions"); level('Subscriptions', 'Subscriptions')
    PCP.click(m, 'btn_return')
    PCP.tap_show(m, 'bravo'); level('Show', None)
    expect(PCP.title_text(m) == 'bravo', 'the Show page keeps its own navbar title label, as before')
    PCP.click(m, 'btn_return')
    # the empty library has the heading too
    m = opened(lambda mm: mm.folder('/mnt/mmc/Music'), lambda mm: None)
    expect(m.props.get((m.widgets['label_title'], 'visible')) == 0 and m.props.get((m.widgets['pg_big'], 'visible'), 1) == 1 , 'no show: the large heading, the navbar\'s title hidden')


def line_tests(ctx):
    """The refresh line: its words in every state, its tap (the guards, the progress dialog, the downloads that pause), its touch height; hidden when no show has a feed."""
    expect = ctx.expect
    WSJ = open(os.path.join(FEEDS, 'wsj-3items.xml'), 'rb').read()
    HEAD = open(os.path.join(FEEDS, 'headlines-3items.xml'), 'rb').read()
    def line(m, off=0):
        g = texts_of(m, 'label_ps_meta', off)
        u = fixed   # (the harness hands the payload's UTF-8 bytes over as latin-1 characters)
        return u(g[0][0] if g else None), u(([t for t, _ in texts_of(m, 'label_ps_line', off)] or [None])[0])
    m = opened()
    expect(line(m) == ('Updated 1h ago · ', 'Refresh'), f'refreshed an hour ago: "Updated 1h ago · Refresh" ({line(m)})')
    for checked, want in ((0, 'Never refreshed · '), (NOW - 30, 'Updated Just now · '), (NOW - 3 * DAY, 'Updated 3d ago · ')):
        mm = opened(lambda x, c=checked: [x.put(f'{RP}/{d}/.show', f'M1PLUS-SHOW 1\ntitle={d}\nfeed={F[k]}\nimage=\nchecked={c}\n'.encode()) for d, k in (('Alpha Show', 'alpha'), ('Sub One', 'one'), ('Sub Two', 'two'))])
        expect(line(mm) == (want, 'Refresh'), f'the newest refresh of any show says it: {want!r} ({line(mm)})')
    expect(texts_of(m, 'label_ps_meta')[0][1][3] == O['PP_LINE_H'], 'the line is PP_LINE_H high')
    # running: "Refreshing 2/5…", with no Refresh word
    pn_set(m, busy=1, done=2, total=5, cur=hash_of(F['one']), gen=3)
    tick(m)
    expect(line(m) == ('Refreshing 2/5…', None), f'a refresh under way: "Refreshing 2/5…" and no word to tap ({line(m)})')
    pn_set(m, busy=0, gen=4)
    tick(m)
    expect(line(m)[1] == 'Refresh', 'it ended: the line is back')
    # hidden: no feed
    m2 = opened(cardf=lambda x: PCP.page_card(x))
    expect(line(m2) == (None, None) and lay(m2, 2, False)['y_line'] == 0, 'no show has a feed: no refresh line')
    # the tap: the guards
    m = opened(lambda mm: mm.fs.pop(f'{RP}/Sub One/.episodes'))
    m.wifi = -1
    PCP.tap_line(m)
    expect(toasts(m) == ['No Wi-Fi'] and 'pthread_create' not in m.names(), 'a tap with no Wi-Fi: the toast says so, nothing starts')
    m.wifi = 4; m.wall = 1700000000
    PCP.tap_line(m)
    expect(toasts(m) == ['Set the date first'], 'a clock that was never set: "Set the date first"')
    m.wall = NOW; m.present.discard(CA)
    PCP.tap_line(m)
    expect(toasts(m) == ['Certificates missing'], 'no CA bundle: "Certificates missing"')
    # the tap that works: the worker and the dialog
    m.present.add(CA); m.thread = None
    seen = []
    def site(url, o):
        seen.append(url)
        return {'body': {F['alpha']: WSJ, F['one']: HEAD}.get(url, b'<html></html>')}
    m.curl_site = site
    PCP.tap_line(m)
    expect(m.thread is not None and toasts(m) == [] and flags(m, 'pod_pd_scrim') == (1, 1) and flags(m, 'pod_pd_card') == (1, 1) and flags(m, 'pod_pd_cancel') == (1, 1),
           'a tap on the line: the worker starts (three feeds) and the progress dialog with its Cancel opens, modal')
    expect(line(m)[0] == 'Refreshing 0/3…', f'the line says "Refreshing 0/3…" ({line(m)})')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    expect([u for u in seen if u in F.values()] == [F['alpha'], F['one'], F['two']], 'the feeds are fetched in the grid\'s order (the most recently updated first: here Alpha Show, then the two with no episode, by title)')
    m.calls = []
    m.screen(True)
    m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    expect(flags(m, 'pod_pd_card') == (0, 0) and toasts(m) == ['2 updated, 1 failed'], f'the worker is done: the dialog closes with its line ({toasts(m)})')
    got = grid(m)
    expect([t for t, _ in got] == ['Alpha Show', 'The Headlines', 'bravo', 'Sub Two'] and got[0][1] == '3 new' and got[1][1] == '3 new' and got[3][1] == 'Not a podcast feed',
           f'the page read the files the worker wrote: Sub One is named by its feed (The Headlines), the order is by the newest episode, the captions say what the refresh found ({got})')
    expect(f'{RP}/The Headlines/.episodes' in m.fs and not [p for p in m.fs if p.startswith(f'{RP}/Sub One/')], 'the folder of a first refresh was renamed after the show')
    m.calls = []; m.thread = None
    PCP.tap_line(m)
    expect(m.thread is not None and m.names().count('pthread_create') == 1, 'a second tap, once the first refresh is done, starts again')
    pn_set(m, busy=1)
    m.calls = []
    PCP.tap_line(m)
    expect('pthread_create' not in m.names() and toasts(m) == [], 'while a refresh runs the line does nothing (no second thread, no toast)')
    # the line is a touch 44 px high across the page, and nothing else near it takes it
    mid = O['PP_LINE_Y'] + O['PP_LINE_H'] // 2
    for y, x, want in ((mid - O['PP_LINE_HIT'] // 2, 300, True), (mid + O['PP_LINE_HIT'] // 2 - 1, 5, True), (mid - O['PP_LINE_HIT'] // 2 - 1, 100, False), (mid + O['PP_LINE_HIT'] // 2, 100, False)):
        m = opened(); m.thread = None; m.calls = []
        PCP.tap(m, x, y)
        started = 'pthread_create' in m.names()
        expect(started == want, f'a touch at ({x}, {y}): {"starts" if want else "does not start"} a refresh (the touch is {O["PP_LINE_HIT"]} px high around the text)')
    # downloads pause for the refresh, it starts when their thread has stopped
    DL = sibling('pcdl')
    m = opened(lambda mm: mm.put(f'{RP}/Sub One/a.mp3.part', b'x' * 1000))
    m.curl_site = DL.server(DL.DATA)
    PCP.tap_show(m, 'Sub One'); PCP.act(m, 0)
    th = m.thread
    PCP.click(m, 'btn_return')
    m.calls = []; m.thread = None
    PCP.tap_line(m)
    expect(m.word(DL.pn_at(DL.DPAUSE)) == 1 and m.thread is None and m.props.get((m.widgets['pod_pd_scrim'], 'visible'), 0) == 0 and line(m) == ('Waiting', None),
           'a tap while a download runs: the downloads are asked to pause, no refresh thread and no dialog yet, the line says Waiting')
    DL.work(m, th)
    m.calls = []
    tick(m)
    expect(m.thread and m.thread[0] == PSYMS['pn_main'] and flags(m, 'pod_pd_scrim') == (1, 1), 'the page\'s tick starts the refresh and opens the dialog once the download thread has stopped')


def cont_tests(ctx):
    """Continue Listening: hidden without a partly played episode; one, two, three items; more than three: the three most recently played; the tap resumes; played and vanished ones do not show."""
    expect = ctx.expect
    o = O
    A1, A2, B1, B2, B3 = (EP('Alpha Show', 'ep1.mp3'), EP('Alpha Show', 'ep2.mp3'), EP('bravo', 'b1.mp3'), EP('bravo', 'b2.mp3'), EP('bravo', 'b3.mp3'))
    def shelf(m):
        return [(t, r) for (t, r), s in zip(*PCP.paint(m, 0)[1:3]) if s == 'label_ps_stitle'], [t for t, r in texts_of(m, 'label_ps_sleft')], [t for t, _ in texts_of(m, 'label_ps_sech')]
    def discs(m):
        return [tuple(b[2]) for b in PCP.paint(m, 0)[0] if b[1] == (o['PA_PLAYB_X'], o['PA_PLAYB_Y'], o['PA_PLAYB_PX'], o['PA_PLAYB_PX'])]
    m = opened()
    expect(shelf(m) == ([], [], ['Shows']) and m.props.get((m.sv, 'virtual_h')) == lay(m)['h'], 'nothing partly played: no Continue Listening (the Shows header follows the Library rows)')
    expect(discs(m) == [], 'no Continue Listening row: no play disc is drawn')
    progress(m, A1, 3000 * 0 + 300, 3000)
    m.call(PSYMS['pc_mark'], a0=hash_of(A2), a1=1, count=30000000)   # played: not an item
    refg(m)
    st, left, heads = shelf(m)
    expect([t for t, _ in st] == ['ep1'] and left == ['45m left'] and heads == ['Continue Listening', 'Shows'] and m.props.get((m.sv, 'virtual_h')) == lay(m, cont=1)['h'],
           f'one item (a played one is none): its title and the time left, its header (the Shows header follows it) ({st}, {left}, {heads})')
    progress(m, B2, 600, 1200)
    refg(m)
    st, left, heads = shelf(m)
    expect([t for t, _ in st] == ['Bravo 2', 'ep1'] and left == ['10m left', '45m left'], f'two items, the most recently played first ({[t for t, _ in st]}, {left})')
    progress(m, B1, 100, 600)
    refg(m)
    st, left, _ = shelf(m)
    expect([t for t, _ in st] == ['Bravo 1', 'Bravo 2', 'ep1'] and left == ['9m left', '10m left', '45m left'] and len(st) == 3, f'three items ({[t for t, _ in st]}, {left})')
    progress(m, B3, 1000, 3600)
    refg(m)
    st, left, _ = shelf(m)
    expect([t for t, _ in st] == ['Bravo 3', 'Bravo 1', 'Bravo 2'] and m.props.get((m.sv, 'virtual_h')) == lay(m, cont=3)['h'], f'four partly played: only the three most recent ({[t for t, _ in st]}), the oldest left out')
    expect([r[0] for _, r in st] == [14, 114, 214] and all(r[2] == o['PP_SHELF_W'] for _, r in st), 'in a static row at x 14, 114, 214, 92 px wide: no horizontal scrolling')
    ys = lay(m, cont=3)['y_shelf']
    want = [pod_show.shelf_play(i, ys) + (o['PA_PLAYB_PX'], o['PA_PLAYB_PX']) for i in range(3)]
    covers = [pod_show.shelf_item(i, ys)[:2] for i in range(3)]
    expect(discs(m) == want and want[0] == (14 + 92 - 6 - 28, ys + o['PP_HEAD_PITCH'] + 92 - 6 - 28, 28, 28)
           and all(d[0] + 28 + 6 == c[0] + 92 and d[1] + 28 + 6 == c[1] + 92 for d, c in zip(want, covers)),
           f'a 28 px play disc on each of the three covers, 6 px from its right and bottom edges ({discs(m)})')
    # an item that ends (played) or whose file is gone is no item
    progress(m, B3, 3500, 3600)
    refg(m)
    st, _, _ = shelf(m)
    expect(m.state(hash_of(B3))[0] == 2 and [t for t, _ in st] == ['Bravo 3', 'Bravo 1', 'Bravo 2'][1:] + ['ep1'], f'an episode played to its end leaves the row, the next older one takes its place ({[t for t, _ in st]})')
    del m.fs[B1]
    refg(m)
    st, _, _ = shelf(m)
    expect([t for t, _ in st] == ['Bravo 2', 'ep1'], f'a partly played episode whose file is gone is skipped ({[t for t, _ in st]})')
    # the covers: one a tick, items first
    m = opened()
    progress(m, A1, 300); progress(m, B2, 600, 1200)
    refg(m)
    m.loads.clear()
    for _ in range(3): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect([u for u in m.loads if u.startswith('file://')][:1] == [f'file://{RP}/Alpha Show/cover.jpg'], 'the covers load one a tick, Continue Listening\'s first (Alpha Show is the one with a picture)')
    bl, *_ = PCP.paint(m, 0)
    cv = [b for b in bl if tuple(b[2][2:]) == (92, 92)]
    expect(len(cv) == 2 and cv[0][0] != cv[1][0], 'the item of the show with a picture shows it, the other the placeholder disc')
    data, w, h = m.bitmaps[cv[1][0]]
    expect((w, h) == (92, 92) and m.u.mem_read(data + (46 * w + 46) * 4, 1)[0] == 0xc8, 'the cover is the 600 px picture reduced to 92')
    # the tap resumes: the queue of the show's files, from the place
    m = opened()
    progress(m, B2, 600, 1200)
    refg(m)
    m.calls = []; m.pt = (0, 1200, 1)
    PCP.tap(m, 14 + 10, lay(m, cont=1)['y_shelf'] + o['PP_HEAD_PITCH'] + 10)
    nav = [c for c in m.calls if c[0] == 'navigator_to_with_context']
    q, idx = m.played
    paths = [m.read_cstr(m.word(r + O['REC_PATH'])) for r in q]
    expect(len(nav) == 1 and nav[0][1] == 'playing_page' and paths == [B3, B2, B1] and idx == 1 and m.state(hash_of(B2)) == (1, 600, 1200),
           f'a tap on the item plays that episode as the Show page\'s resume pill does (class 1, the show\'s files in the list\'s order, its place kept) ({paths}, {idx})')
    expect(PCP.title_text(m) == 'Podcasts' and m.props.get((m.sv, 'virtual_h')) == lay(m, cont=1)['h'], 'the page stays on the Shows level (its episodes are let go again)')
    # a tap on the item when its file went: nothing starts
    m = opened()
    progress(m, B2, 600, 1200)
    refg(m)
    del m.fs[B2]; m.calls = []
    PCP.tap(m, 14 + 10, lay(m, cont=1)['y_shelf'] + o['PP_HEAD_PITCH'] + 10)
    expect(not [c for c in m.calls if c[0] == 'navigator_to_with_context' and c[1] == 'playing_page'] and toasts(m) == ['Storage unavailable'], 'a file that has gone since: "Storage unavailable", nothing starts')
    # the row follows the ring: when the playing item reaches its end, the page reads the row again
    m = opened()
    progress(m, A1, 300)
    refg(m)
    progress(m, A1, 2990, 3000)
    tick(m)
    expect(not texts_of(m, 'label_ps_stitle') and m.props.get((m.sv, 'virtual_h')) == lay(m)['h'], 'an item that is played while the page is in front: the next tick takes the row away')


def settle(m, n=90):
    """The loader's ticks: the covers, then the totals scan (a show a tick)."""
    for _ in range(n): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)


def lib(m, off=None):
    """[(title, grey line)] of the Library rows in a frame, top to bottom (the rows close the page: by default the frame scrolled to the bottom)."""
    if off is None: off = max(0, m.props.get((m.sv, 'virtual_h'), 0) - 400)
    t = sorted((r[1], x) for x, r in texts_of(m, 'label_row_title', off))
    s = sorted((r[1], x) for x, r in texts_of(m, 'label_row_sub', off))
    return [(a, b) for (_, a), (_, b) in zip(t, s)]


def tap_row(m, name, **kw):
    """A tap on the Library row called name (found by its title in the frame)."""
    y, off = PCP.lib_row_at(m, name)
    return PCP.tap(m, 150, y, off=off, **kw)


def library_tests(ctx):
    """The Library rows (Downloads always, Subscriptions while a show has a feed): their grey lines in every state, the totals scan, their taps and press fills, the screen-off rule."""
    expect = ctx.expect
    DL = sibling('pcdl')
    o = O
    A1, A2 = EP('Alpha Show', 'ep1.mp3'), EP('Alpha Show', 'ep2.mp3')
    m = opened()
    L = lay(m)
    expect([a for a, _ in lib(m)] == ['Downloads', 'Subscriptions', 'Saved'] and not [c for c in m.calls if c[0] == 'widget_set_text_utf8' and 'Downloads (' in str(c)], 'a card with subscriptions: both rows are there (nothing queued does not hide Downloads)')
    m2 = opened(cardf=lambda x: PCP.page_card(x))
    expect([a for a, _ in lib(m2)] == ['Downloads', 'Saved'] and lay(m2, 2, False)['y_sub'] == 0, 'no show has a feed: the Downloads row and Saved (the Subscriptions row needs a subscription)')
    # idle: the count at once, the size when the totals scan has finished
    expect(lib(m) == [('Downloads', '5 episodes'), ('Subscriptions', '3 shows'), ('Saved', 'No saved episodes')], f'idle: "5 episodes" at once, "3 shows", nothing saved ({lib(m)})')
    m = opened(lambda mm: mm.sizes.update({A1: 100 << 20, A2: 50 << 20}))
    settle(m)
    expect(lib(m)[0] == ('Downloads', '5 episodes · 150 MB'), f'the totals scan has run: "5 episodes · 150 MB" ({lib(m)})')
    m = opened(lambda mm: mm.sizes.update({A1: 1503238554, A2: 50 << 20}))
    settle(m)
    expect(lib(m)[0] == ('Downloads', '5 episodes · 1.4 GB'), f'from a gigabyte on one decimal: "5 episodes · 1.4 GB" ({lib(m)})')
    one = opened(lambda mm: mm.put(f'{RP}/Only/o.mp3', b'x', 5), lambda x: None)
    expect(lib(one) == [('Downloads', '1 episode'), ('Saved', 'No saved episodes')], f'one file: "1 episode" ({lib(one)})')
    nothing = opened(lambda mm: mm.put(f'{RP}/Fresh/.show', f'M1PLUS-SHOW 1\ntitle=Fresh\nfeed={F["three"]}\nimage=\nchecked=0\n'.encode()), lambda x: None)
    expect(lib(nothing) == [('Downloads', 'No downloads'), ('Subscriptions', '1 show'), ('Saved', 'No saved episodes')], f'a subscription with nothing downloaded: "No downloads", "1 show" ({lib(nothing)})')
    # the totals scan: one show a tick, nothing once it is done, never in the dark, the old figure stays until the new one is complete
    m = opened(lambda mm: mm.sizes.update({A1: 100 << 20}))
    walks = []
    for _ in range(16):
        m.call(PSYMS['pg_on_load'], a0=0, count=40000000)   # (a call starts the call log afresh)
        walks.append(len([c for c in m.calls if c[0] == 'opendir']))
    expect(sum(walks) == 4 and max(walks) == 1 and walks[-4:] == [0] * 4, f'the four shows are walked, one a tick, and then a tick reads nothing ({walks})')
    m = opened(lambda mm: mm.sizes.update({A1: 100 << 20}))
    m.screen(False); m.calls = []
    settle(m, 6)
    expect(not [c for c in m.calls if c[0] in ('opendir', '__xstat')], 'dark: the loader walks no folder')
    m.screen(True)
    settle(m)
    expect(lib(m)[0][1] == '5 episodes · 100 MB', f'the first lit ticks finish the scan ({lib(m)})')
    m.sizes[A1] = 40 << 20
    PCP.tap_show(m, 'bravo')
    PCP.click(m, 'btn_return')
    expect(lib(m)[0][1] == '5 episodes · 100 MB', f'back from a show page the scan starts again; its old figure stays until it is complete ({lib(m)})')
    settle(m)
    expect(lib(m)[0][1] == '5 episodes · 40 MB', f'... and is replaced when it is ({lib(m)})')
    # the states of the worker: running beats waiting beats paused
    m = opened()
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 1, seq=1); DL.poke_slot(m, 1, 'Sub One', 'b.mp3', 1, seq=2); m.setword(DL.pn_at(12), 5)
    tick(m)
    expect(lib(m)[0] == ('Downloads', '2 waiting') and m.props.get((m.sv, 'virtual_h')) == L['h'], 'two queued, none running: "2 waiting" (the page is not made again for it)')
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 2, seq=1); m.setword(DL.pn_at(DL.DKEY), DL.key_of('Sub One', 'a.mp3')); m.setword(DL.pn_at(DL.DGOT), 100000); m.setword(DL.pn_at(DL.DTOTAL), 1000000)
    m.setword(DL.pn_at(DL.KIND), 2); m.setword(DL.pn_at(0), 1); m.setword(DL.pn_at(DL.DGEN), 9)
    tick(m)
    expect(lib(m)[0] == ('Downloads', 'Downloading 9%'), f'one running: "Downloading 9%" ({lib(m)})')
    m.setword(DL.pn_at(DL.DGOT), 420000); m.setword(DL.pn_at(DL.DGEN), 10)
    m.calls = []
    tick(m)
    expect(lib(m)[0] == ('Downloads', 'Downloading 42%') and not [c for c in m.calls if c[0] in ('opendir', '__xstat')], 'a step of progress moves the line (the card is not read)')
    m = opened(lambda mm: mm.put(f'{RP}/Sub One/a.mp3.part', b'half'))
    settle(m)
    expect(lib(m)[0] == ('Downloads', '1 paused'), f'a .part nothing holds: "1 paused" ({lib(m)})')
    DL.poke_fail(m, 0, 'Sub One', 'b.mp3', PN['NET']); m.setword(DL.pn_at(12), 5)
    tick(m)
    expect(lib(m)[0] == ('Downloads', '2 paused'), f'a failed download counts as paused (a tap on its row goes on): "2 paused" ({lib(m)})')
    DL.poke_slot(m, 0, 'Sub One', 'c.mp3', 1, seq=3)
    expect(lib(m)[0] == ('Downloads', '1 waiting'), f'one waiting beats the paused ones ({lib(m)})')
    # a tap on each row opens its page; Back returns where the Shows level was
    m = opened()
    LO = L['h'] - 400   # (the rows close the page: scrolled to the bottom)
    PCP.tap(m, 150, L['y_dl'] + 20, off=LO)
    expect(PCP.title_text(m) == 'Downloads' and flags(m, 'btn_more')[0] in (0, 1) and m.props.get((m.widgets['pg_big'], 'visible'), 1) == 1, 'a tap on the Downloads row opens the Downloads page')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and m.props.get((m.sv, 'yoffset')) == LO and m.props.get((m.sv, 'virtual_h')) == L['h'] and 'navigator_back' not in m.names(), 'Back returns to the Shows level, scrolled as it was left')
    PCP.tap(m, 150, L['y_sub'] + 20, off=LO)
    expect(PCP.title_text(m) == 'Subscriptions', 'a tap on the Subscriptions row opens the Subscriptions page')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and m.props.get((m.sv, 'yoffset')) == LO, 'Back returns to the Shows level where it was')
    PCP.tap(m, 150, L['y_dl'] - 2, off=LO); PCP.tap(m, 150, L['y_sav'] + o['PC_ROW_H'] + 2, off=LO)
    expect(PCP.title_text(m) == 'Podcasts', 'a touch just above the rows or just under them opens nothing')
    m = opened()
    for key, label in (('y_dl', 'Downloads'), ('y_sub', 'Subscriptions')):
        m.setword(m.sv + PCP.SC_YOFF, LO); m.setword(m.view + 4, -LO & 0xffffffff)
        m.touch('down', 100, PCP.SCREEN_Y0 + L[key] + 20 - LO, 1000, fn='pg_on_down')
        _, _, _, fills = PCP.paint(m, LO)
        expect((o['LIST_PRESS'], 0, L[key] - LO, 320, o['PC_ROW_H'] - 1) in fills and len([f for f in fills if f[0] == o['LIST_PRESS']]) == 1, f'a finger on the {label} row fills it, and only it, in the list row\'s press colour')
        m.touch('abort', 100, PCP.SCREEN_Y0 + L[key] + 20 - LO, 1010, fn='pg_on_abort')
    # the covers of the grid survive a visit to a level: no decode again
    m = opened()
    for _ in range(8): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    m.loads.clear()
    PCP.tap_show(m, 'bravo'); PCP.click(m, 'btn_return')
    for _ in range(4): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not [u for u in m.loads if u.startswith('file://')], 'a visit to a Show page and back: the covers are still there, nothing is decoded again')
    # the queue coming and going does not make the page again
    m = opened()
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 1, seq=1); m.setword(DL.pn_at(12), 5); tick(m)
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 0); m.setword(DL.pn_at(12), 6); tick(m)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and [a for a, _ in lib(m)] == ['Downloads', 'Subscriptions', 'Saved'], 'a download that comes and goes: the Library rows stay, the content is the same height')


def grid_tests(ctx):
    """The grid: captions in each case, no badge on a cover, the order, a tap opens the Show page, a subscription with nothing downloaded is listed."""
    expect = ctx.expect
    m = opened()
    got = grid(m)
    expect(got == [('Sub One', 'Never refreshed'), ('bravo', 'Local · 3 episodes'), ('Alpha Show', 'Updated today'), ('Sub Two', 'Updated 2d ago')],
           f'the captions: a subscription never refreshed, a local show\'s files, a refresh within a day, a refresh two days ago ({got})')
    h = {k: hash_of(v) for k, v in F.items()}
    pn_set(m, gen=7, statuses=[(h['alpha'], PN['OK'], 3), (h['one'], PN['NOWIFI'], 0), (h['two'], PN['OK'], 0)])
    tick(m)
    got = grid(m)
    expect(got[0][1] == 'No Wi-Fi' and got[2][1] == '3 new' and got[3][1] == 'Updated 2d ago' and got[1][1] == 'Local · 3 episodes', f'what the last refresh found: its error in words, "3 new", else the age ({got})')
    words = {PN['NOWIFI']: 'No Wi-Fi', PN['NOCLOCK']: 'Set the date first', PN['NOCERT']: 'Certificates missing', PN['CERT']: 'Certificate problem', PN['NET']: "Can't connect", PN['GONE']: 'Feed not found',
             PN['HTTP']: 'Server error', PN['NOTFEED']: 'Not a podcast feed', PN['STORAGE']: 'Storage unavailable', PN['MEM']: 'Not enough memory'}
    for gen, (code, word) in enumerate(words.items(), 20):
        pn_set(m, gen=gen, statuses=[(h['one'], code, 0)])
        tick(m)
        cap = grid(m)[0][1]
        expect(cap == word or (cap.endswith('…') and word.startswith(cap[:-1])), f'result {code}: "{word}" ({cap!r}; a word wider than the 144 px column ends in an ellipsis: width_tests lists them)')
    pn_set(m, gen=40, statuses=[(h['one'], PN['OK'], 2)])
    tick(m)
    expect(grid(m)[0][1] == '2 new', 'a first refresh that found two: "2 new"')
    pn_set(m, gen=41, statuses=[(h['one'], PN['OK'], 0)])
    tick(m)
    expect(grid(m)[0][1] == 'Never refreshed', 'refreshed with nothing new and no time on the show file yet: still "Never refreshed"')
    one = lambda mm: mm.put(f'{RP}/Only/o.mp3', b'x', 5)
    mm = opened(one, lambda x: PCP.page_card(x))
    full = 'Local · 1 episode'
    fits = sw().font().width(full, pod_show.PX['label_ps_gsub']) <= GC   # (the emulated canvas measures 8 px a character, so a caption the payload keeps whole may be cut by the grid here: only its start is compared)
    cap = grid(mm)[-1]
    expect(cap[0] == 'Only' and (cap[1].startswith('Local · 1') if fits else cap[1] == 'Local'), f'one file, no feed: the marker and the count where they fit the cover, else the marker alone ({cap})')
    # no badge: nothing is painted over a cover but the cover
    bl, *_ = PCP.paint(m, 120)
    cover_boxes = [tuple(b[2]) for b in bl if tuple(b[2][2:]) == (GC, GC)]
    inside = [b for b in bl if tuple(b[2][2:]) != (GC, GC) and any(c[0] <= b[2][0] < c[0] + GC and c[1] <= b[2][1] < c[1] + GC for c in cover_boxes)]
    expect(cover_boxes and not inside, 'no badge or count on a cover: nothing but the cover is drawn over it')
    for fills in (PCP.paint(m, 120)[3],):
        expect(not [f for f in fills if f[1] >= 0 and any(c[0] <= f[1] < c[0] + GC and c[1] <= f[2] < c[1] + GC for c in cover_boxes) and f[0] >> 24], 'and no fill over a cover')
    # a tap opens the Show page; every kind of show opens
    L = lay(m)
    m = opened()
    PCP.tap_show(m, 'Alpha Show')
    expect(PCP.title_text(m) == 'Alpha Show' and PCP.all_cells(m)[0]['title'] == ['ep2'], 'a tap on a cover opens that show\'s page (its episodes)')
    PCP.click(m, 'btn_return')
    PCP.tap_show(m, 'Sub One')
    c = PCP.all_cells(m)
    expect(PCP.title_text(m) == 'Sub One' and [c[i]['pill'] for i in range(2)] == ['1 MB', 'Download'], 'a subscription with nothing downloaded is listed and opens: its episodes are download cells')
    PCP.click(m, 'btn_return')
    expect(PCP.title_text(m) == 'Podcasts' and 'navigator_back' not in m.names(), 'Back goes to the Shows level, not out of the page')
    # a tap on the caption is a tap on the show; the gap between the columns and the air under the last row are not
    m = opened()
    cells = [pod_show.grid_cell(i, L['y_grid']) for i in range(4)]
    x, y, ty, sy = cells[1]
    PCP.tap(m, x + 5, sy + 5)
    expect(PCP.title_text(m) == 'bravo', 'a tap on the grey line under a cover opens its show too')
    m = opened()
    PCP.tap(m, cells[0][0] + GC + 2, cells[0][1] + 20)
    PCP.tap(m, 100, L['h'] - 3)
    expect(PCP.title_text(m) == 'Podcasts', 'the gap between the columns and the air at the end open nothing')
    # the order: the newest episode, remote or local; ties by title
    def ties(mm):
        for d in ('Beta', 'alpha2', 'Zed'): mm.put(f'{RP}/{d}/.episodes', (PCP.EPS_HEAD + 'g=a\tp=5000\tf=a.mp3\tt=A\tu=https://e/a\n').encode())
        mm.put(f'{RP}/Late/.episodes', (PCP.EPS_HEAD + 'g=a\tp=3000\tf=a.mp3\tt=A\tu=https://e/a\ng=b\tp=9000\tt=Newest, not downloaded\tu=https://e/b\n').encode())
    m = opened(ties, lambda x: None)
    expect([t for t, _ in grid(m)] == ['Late', 'alpha2', 'Beta', 'Zed'], f'the newest episode (a remote one counts) decides; equal dates by title, case aside ({[t for t, _ in grid(m)]})')


def sheet_tests(ctx):
    """The "..." sheet of the Shows level: Import from Card is its only row, so the "..." shows only while the card has something to import (the Subscriptions page is a Library row now); no Add Show row."""
    expect = ctx.expect
    WSJ = open(os.path.join(FEEDS, 'wsj-3items.xml'), 'rb').read()
    m = opened(None, PCP.page_card)
    expect(flags(m, 'btn_more') == (0, 0) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np' and m.props[(m.widgets['btn_backtoplayer'], 'style:pressed:icon')] == 'ah_nav_np_down',
           'without an import source the sheet would be empty: the "..." is hidden and out of the hit test, Now Playing is the plain disc')
    m = opened()
    PCP.click(m, 'btn_more')
    expect(flags(m, 'btn_more') == (0, 0) and m.props.get((m.widgets['pg_sh_card'], 'visible'), 0) == 0 and flags(m, 'btn_globe') == (0, 0) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_np',
           'with subscriptions and nothing to import the "..." is hidden too (Subscriptions is a Library row): Now Playing is the plain disc, and a stray click opens no sheet')
    sub_txt = f'{RP}/subscriptions.txt'
    m = opened(lambda mm: mm.put(sub_txt, f'{F["three"]}\n'.encode()))
    expect(flags(m, 'btn_more') == (1, 1) and m.props[(m.widgets['btn_backtoplayer'], 'style:normal:icon')] == 'ah_nav_play' and m.props[(m.widgets['btn_backtoplayer'], 'style:pressed:icon')] == 'ah_nav_play_down',
           'with subscriptions.txt: [... | Now Playing], one capsule (the "..." is a middle piece only beside the globe)')
    PCP.click(m, 'btn_more')
    shown = [r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)]
    expect(shown == ['import'] and flags(m, 'pg_sh_card') == (1, 1) and flags(m, 'pg_sh_scrim') == (1, 1) and m.props.get((m.widgets['pg_sh_card'], 'style:normal:bg_image')) == 'pc_sheet1'
           , f'the sheet has one row, Import from Card (the one-row glass) ({shown})')
    ys = {r: [c for c in m.calls if c[0] == 'widget_move' and c[1] == m.widgets[f'pg_sh_{r}']][-1][3] for r in shown}
    expect(ys == {'import': 0}, f'Import from Card is the row at the card\'s top ({ys})')
    expect('pg_sh_add' not in m.widgets and 'Add Show' not in pod_i18n.TEXT and not [r for r in PCP.SHEET_ROWS if 'add' in r], 'there is no Add Show row until search exists')
    # Back and the scrim close it
    PCP.click(m, 'btn_return')
    expect(flags(m, 'pg_sh_card') == (0, 0) and 'navigator_back' not in m.names(), 'Back closes the sheet first')
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_scrim')
    expect(flags(m, 'pg_sh_card') == (0, 0), 'a tap on the scrim closes it')
    # Import: the existing import, its refresh and its dialog
    m.curl_site = lambda url, o: {'body': WSJ}
    m.thread = None; m.calls = []
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_import')
    expect(toasts(m) == ['1 added'] and m.thread is not None and flags(m, 'pod_pd_card') == (1, 1) and flags(m, 'pg_sh_card') == (0, 0), 'Import from Card: the new address is added ("1 added"), the sheet closes, the shows never refreshed are refreshed and the dialog opens')
    expect(f'{RP}/f.example-{hash_of(F["three"]):08x}/.show' in m.fs, 'a folder and a show file named by the host and the address\'s hash')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    names = [t for t, _ in grid(m)]
    expect(len(names) == 5 and fn(m, 'pn_busy') == 0, f'five shows in the grid now ({names})')
    m.calls = []; m.thread = None
    PCP.click(m, 'btn_more'); PCP.click(m, 'pg_sh_import')
    expect(toasts(m) == ['Nothing new to import'] and m.thread is None, 'importing again: "Nothing new to import"')
    # the file goes: the "..." goes with it at the next read
    del m.fs[sub_txt]
    refg(m)
    PCP.click(m, 'btn_more')
    expect(flags(m, 'btn_more') == (0, 0) and m.props.get((m.widgets['pg_sh_card'], 'visible'), 0) == 0, 'subscriptions.txt removed: the "..." goes with it after the page is read, and a click opens no sheet')
    # no sheet under the dialog or in select mode of another level
    m = opened(lambda mm: mm.put(sub_txt, f'{F["three"]}\n'.encode()))
    PCP.tap_show(m, 'bravo')
    expect(flags(m, 'btn_more') == (1, 1), 'on a Show page the "..." is its own sheet\'s')
    PCP.click(m, 'btn_more')
    expect(flags(m, 'pg_sh_import') == (0, 0) and flags(m, 'pg_sh_speed') == (1, 1), 'the Show page\'s sheet has no Import row')


def gone_tests(ctx):
    """The Feeds level and everything only it used are gone: its button, its rows, its strings, its code."""
    expect = ctx.expect
    m = opened()
    expect('btn_feeds' not in m.widgets and 'label_row_act' not in m.widgets, 'the page opens without a Feeds button or an action-row style (it looks for neither)')
    tree = awtk_ui.parse(open(os.path.join(WORK, 'rootfs', 'release/assets/default/raw/ui/m1plus_podcasts.bin'), 'rb').read())
    expect(tree.find('btn_feeds') is None and tree.find('label_row_act') is None, 'the asset has no Feeds button and no action-row style')
    gone = ('Feeds', 'Refresh All', 'Import shows', 'Up to date', 'Refreshing', 'Nothing downloaded yet. Open Feeds, at the top right.', 'No episodes yet. Refresh the feed in Feeds.',
            'No subscriptions. List one feed address per line in subscriptions.txt in Podcasts on the card, then open Feeds again.')
    expect(not [k for k in gone if k in pod_i18n.TEXT], f'the Feeds level\'s strings are gone from the tables ({[k for k in gone if k in pod_i18n.TEXT]})')
    src = sources()
    dead = [(f, w) for f, s in src.items() for w in ('L_FEEDS', 'pg_load_feeds', 'pg_feeds_tap', 'pg_feed_texts', 'pg_feed_retext', 'PG_ROW_', 'btn_feeds', 'pod_nav_feeds', 'from_feeds', 'label_row_act') if w in s]
    expect(not dead, f'no trace of the Feeds level in the payload ({dead})')
    expect('pod_nav_feeds' not in open(os.path.join(ROOT, 'tools', 'pod_ui.py')).read() and 'NAV_FEEDS_ICON' not in open(os.path.join(ROOT, 'tools', 'pod_ui.py')).read(), 'nor in the asset builder')


def empty_tests(ctx):
    """The empty library: the hint says how to start; Import appears in the "..." when subscriptions.txt exists; the Show level's hint for a subscription with no episode."""
    expect = ctx.expect
    hint = PCP.EMPTY_HINT
    m = opened(lambda mm: mm.folder('/mnt/mmc/Music'), lambda mm: None)
    st = m.widgets['label_status']
    expect(('widget_set_tr_text', st, hint) in m.calls and flags(m, 'label_status')[0] == 1 and m.props.get((m.view, 'visible')) == 0 and flags(m, 'btn_more') == (0, 0),
           'nothing at all: the hint (subscriptions.txt in Podcasts, or show folders; Import from Card in the menu) and no "..."')
    m = opened(lambda mm: (mm.put(f'{RP}/subscriptions.txt', b'https://x.example/rss\n'), mm.present.add(CA), setattr(mm, 'wall', NOW)), lambda mm: None)
    expect(flags(m, 'label_status')[0] == 1 and flags(m, 'btn_more') == (1, 1) and [t for t, _ in texts_of(m, 'label_ps_gtitle')] == [], 'subscriptions.txt and no show: the hint stays and the "..." has Import')
    PCP.click(m, 'btn_more')
    expect([r for r in PCP.SHEET_ROWS if flags(m, f'pg_sh_{r}') == (1, 1)] == ['import'], 'its sheet: Import from Card')
    m.curl_site = lambda url, o: {'rc': 6}
    m.thread = None
    PCP.click(m, 'pg_sh_import')
    expect(toasts(m) == ['1 added'] and m.thread is not None, 'and it works with no show yet')
    m.call(m.thread[0], a0=m.thread[1], count=1 << 40)
    m.screen(True); m.call(PSYMS['pg_dlg_tick'], a0=0, count=40000000)
    expect(flags(m, 'label_status')[0] == 0 and len(grid(m)) == 1, 'the imported show is listed and the hint is gone')
    # a subscription with no episode: its page's hint
    m = opened(lambda mm: mm.put(f'{RP}/Fresh/.show', f'M1PLUS-SHOW 1\ntitle=Fresh\nfeed={F["three"]}\nimage=\nchecked=0\n'.encode()), lambda mm: None)
    PCP.tap_show(m, 'Fresh')
    expect('No episodes yet. Choose Refresh Feed in the menu at the top right.' in PCP.hint(m), 'a subscription not refreshed yet opens a page that says how to fill it')
    # no memory
    m = machine(); m.calloc_fail = True
    m.call(PSYMS['podcasts_open'], count=40000000)
    expect(('widget_set_tr_text', m.widgets['label_status'], 'Not enough memory') in m.calls, 'no memory: the page says so')


def width_tests(ctx):
    """The page's strings in the 13 languages in the real font: the refresh line, the headers, the Continue Listening lines, the Downloads row, the grid's captions."""
    expect = ctx.expect
    fnt = sw().font()
    o = O
    worst = {}
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        tr = lambda key, n=None, t=t: (pod_i18n.TEXT[key][t].replace('%d', str(n)) if n is not None else pod_i18n.TEXT[key][t])
        when = [tr('Just now'), tr('%dm ago', 59), tr('%dh ago', 23), tr('%dd ago', 6), tr('Oct %d', 23) + tr(', %d', 2025)]
        line_a = [fnt.width(tr('Updated %s').replace('%s', w) + ' · ', 15) + fnt.width(tr('Refresh'), 15) for w in when]
        line_b = [fnt.width(w + ' · ', 15) + fnt.width(tr('Refresh'), 15) for w in when]
        line_n = fnt.width(tr('Never refreshed') + ' · ', 15) + fnt.width(tr('Refresh'), 15)
        prog = fnt.width(pod_i18n.TEXT['Refreshing %d/%d…'][t].replace('%d', '40', 1).replace('%d', '40', 1), 15)
        heads = max(fnt.width(tr('Continue Listening'), 20), fnt.width(tr('Shows'), 20))
        left = max(fnt.width(tr('%dm left', 99), 13), fnt.width(tr('Play'), 13))
        left599 = fnt.width(tr('%dm left', 599), 13)
        dlt = fnt.width(tr('Downloads') + ' (40)', 21)
        head = max(fnt.width(tr(k), o['PP_TITLE_PX']) for k in ('Podcasts', 'Downloads', 'Subscriptions'))
        dls = max(fnt.width(tr('Downloading') + ' 100%', 18), fnt.width(tr('Downloading') + ' ' + tr('%d MB', 999), 18), fnt.width(tr('Waiting'), 18))
        caps = {k: fnt.width(k_, 15) for k, k_ in (('new', tr('%d new', 99)), ('today', tr('Updated today')), ('neverc', tr('Never refreshed')), ('eps', tr('%d episodes', 999)), ('ago', (lambda a, b: a if fnt.width(a, 15) <= GC else b)(tr('Updated %s').replace('%s', tr('%dd ago', 6)), tr('%dd ago', 6))))}
        worst[loc] = dict(line=max(a if a <= 320 - 2 * o['PP_LINE_X'] else b for a, b in zip(line_a, line_b)), never=line_n, prog=prog, heads=heads, left=left, left599=left599, dlt=dlt, dls=dls, head=head, **caps)
    room = 320 - 2 * o['PP_LINE_X']
    expect(all(w['line'] <= room and w['never'] <= room for w in worst.values()), f'the refresh line fits {room} px in every language, the age alone when "Updated <age>" would not ({[l for l, w in worst.items() if w["line"] > room or w["never"] > room]})')
    expect(all(w['prog'] <= room for w in worst.values()), f'"Refreshing 40/40…" fits the line ({[l for l, w in worst.items() if w["prog"] > room]})')
    expect(all(w['heads'] <= 320 - 2 * o['PP_HEAD_X'] for w in worst.values()), 'the headers fit one line')
    expect(all(w['head'] <= o['SG_TITLE_W'] for w in worst.values()), f'the large headings (Podcasts, Downloads, Subscriptions at {o["PP_TITLE_PX"]} px) fit the page in every language ({[(l, w["head"]) for l, w in worst.items() if w["head"] > o["SG_TITLE_W"]]})')
    expect(all(w['left'] <= o['PP_SHELF_W'] for w in worst.values()), f'"99m left" fits an item\'s 92 px in every language ({[(l, w["left"]) for l, w in worst.items() if w["left"] > o["PP_SHELF_W"]]}); a longer one (French and Russian from 100 minutes\' 3 digits) ends in an ellipsis')
    expect(all(w['dlt'] <= o['PP_DL_TEXT_W'] and w['dls'] <= o['PP_DL_TEXT_W'] for w in worst.values()), f'"Downloads (40)" and the running line fit the row ({[(l, w["dlt"], w["dls"]) for l, w in worst.items() if w["dlt"] > o["PP_DL_TEXT_W"] or w["dls"] > o["PP_DL_TEXT_W"]]})')
    over = {k: [(l, w[k]) for l, w in worst.items() if w[k] > GC] for k in ('new', 'today', 'neverc', 'eps', 'ago')}
    expect(not any(over.values()), f'the grid\'s grey lines fit {GC} px without an ellipsis, "Updated <age>" giving way to the age alone where it would not ({over})')
    errs = {code: [(l, fnt.width(pod_i18n.TEXT[k][pod_i18n.table_for(l)], 15)) for l in pod_i18n.LOCALES if fnt.width(pod_i18n.TEXT[k][pod_i18n.table_for(l)], 15) > GC] for code, k in
            (('No Wi-Fi', 'No Wi-Fi'), ('date', 'Set the date first'), ('certs', 'Certificates missing'), ('cert', 'Certificate problem'), ('net', "Can't connect"), ('gone', 'Feed not found'), ('http', 'Server error'),
             ('notfeed', 'Not a podcast feed'), ('storage', 'Storage unavailable'), ('mem', 'Not enough memory'))}
    print('  error words wider than the 144 px caption (they end in an ellipsis there; the toast has them whole):', {k: [x for x in v] for k, v in errs.items() if v})
    print('  widest per string (px):', {k: max((w[k], l) for l, w in worst.items()) for k in ('line', 'never', 'prog', 'heads', 'left', 'dlt', 'dls', 'new', 'today', 'neverc', 'eps', 'ago')})


def off_tests(ctx):
    """The screen-off rule: a dark tick reads and paints nothing on the Shows level (the next lit one does), no cover is decoded and no timer is added; the refresh dialog's own timer stops."""
    expect = ctx.expect
    m = opened()
    for _ in range(8): m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    L = lay(m)
    m.screen(False); m.calls = []; m.loads.clear()
    DL = sibling('pcdl')
    DL.poke_slot(m, 0, 'Sub One', 'a.mp3', 1, seq=1); m.setword(DL.pn_at(12), 5)
    m.call(PSYMS['pg_tick'], a0=0, count=40000000)
    expect(m.props.get((m.sv, 'virtual_h')) == L['h'] and not [c for c in m.calls if c[0] in ('widget_invalidate_force', 'widget_set_tr_text', 'widget_resize', 'widget_set_prop_int', 'opendir', '__xstat')],
           'dark: the tick does not read the shows again, no repaint, no card read')
    m.call(PSYMS['pg_on_load'], a0=0, count=40000000)
    expect(not m.loads, 'dark: the cover loader decodes nothing')
    tick(m)
    expect(lib(m)[0] == ('Downloads', '1 waiting') and m.props.get((m.sv, 'virtual_h')) == L['h'], 'the next lit tick: the Downloads row says 1 waiting (it is read from the queue at every paint)')
    # a page that comes back to the front while dark is read at the first lit tick
    m = opened()
    progress(m, EP('Alpha Show', 'ep1.mp3'), 300)
    m.screen(False); m.calls = []
    fn_, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_BG'])]; m.call(fn_, a0=ctx_, a1=0, count=4000000)
    fn_, ctx_ = m.bound[(m.window, O['EVT_WINDOW_TO_FG'])]; m.call(fn_, a0=ctx_, a1=0, count=4000000)
    expect(not texts_of(m, 'label_ps_stitle') and not [c for c in m.calls if c[0] in ('opendir', '__xstat')], 'back in front with the screen off: nothing is read')
    tick(m)
    expect([t for t, _ in texts_of(m, 'label_ps_stitle')] == ['ep1'], 'the first lit tick reads it: Continue Listening has its item')
    # the refresh line is made from live state at every paint (no timer of its own)
    m = opened()
    expect(not [c for c in m.calls if c[0] == 'timer_add' and c[1] not in (PSYMS['pg_tick'], PSYMS['pg_on_load'])], 'the page adds only its tick and the loader (page-scoped), nothing for the line or the shelf')


def caption_tests(ctx):
    """The "Local" marker of a show with no feed: it fits the grid's cover in all 13 languages (with the count where that fits too), the order has no sections, and each caption box is the cover's width."""
    expect = ctx.expect
    font = sw().font()
    px = pod_show.PX['label_ps_gsub']
    fit = []
    for loc in pod_i18n.LOCALES:
        t = pod_i18n.table_for(loc)
        marker = pod_i18n.TEXT['Local'][t]
        wm = font.width(marker, px)
        expect(wm <= GC, f'{loc}: the marker alone ("{marker}", {wm} px) fits the {GC} px cover')
        full = f'{marker} · ' + pod_i18n.TEXT['%d episodes'][t] % 12
        if font.width(full, px) <= GC: fit.append(loc)
    print(f'  "Local · 12 episodes" fits the {GC} px cover in {len(fit)} of {len(pod_i18n.LOCALES)} languages:', fit)
    m = opened()
    got = grid(m)
    expect([c[0] for c in got] == ORDER, f'the order is unchanged, no sections ({[c[0] for c in got]})')
    for t, r in PCP.drawn(m, 0, style='label_ps_gsub'):
        expect(r[2] == GC, f'the caption box is the cover\'s width ({r})')


SECTIONS = [layout_tests, title_tests, line_tests, cont_tests, library_tests, grid_tests, caption_tests, sheet_tests, gone_tests, empty_tests, width_tests, off_tests]


def run(ctx):
    for f in SECTIONS: f(ctx)
